"""
Search multiple job boards and return raw job listings.
Sources:
  1. RemoteOK (free, no auth, remote jobs)
  2. Arbeitnow (free, EU + remote)
  3. The Muse (free, no auth)
  4. Adzuna (free tier, needs ADZUNA_APP_ID + ADZUNA_API_KEY)
  5. Hacker News "Who's Hiring" (latest monthly thread)
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36"
}

# Keywords that must appear in title OR description for a job to pass the tech filter
_TECH_TITLE_KEYWORDS = {
    "python", "backend", "back-end", "software", "developer", "engineer",
    "fastapi", "django", "flask", "devops", "cloud", "fullstack", "full-stack",
    "node.js", "golang", "typescript", "react", "data engineer", "data scientist",
    "machine learning", "ml engineer", "ai engineer", "infrastructure", "sre",
    "platform engineer", "microservices", "kubernetes", "programmer", "coder",
    "architect", "tech lead", "engineering manager", "r&d", "it specialist",
    "it engineer", "it infrastructure", "working student", "intern",
}

_TECH_DESC_KEYWORDS = {
    "python", "backend", "fastapi", "django", "flask", "postgresql", "redis",
    "microservices", "rest api", "graphql", "docker", "kubernetes", "ci/cd",
}

def _is_tech_job(title: str, description: str) -> bool:
    """
    Return True if:
    - The title contains a tech keyword, OR
    - The title contains a generic tech hint AND description confirms it
    """
    title_lower = title.lower()
    # Direct tech title match
    if any(kw in title_lower for kw in _TECH_TITLE_KEYWORDS):
        return True
    # Fallback: description must have strong tech signal
    desc_lower = description[:500].lower()
    return any(kw in desc_lower for kw in _TECH_DESC_KEYWORDS)


# ---------------------------------------------------------------------------
# Source 1: RemoteOK
# ---------------------------------------------------------------------------

def search_remoteok(queries: list[str]) -> Generator[dict, None, None]:
    """https://remoteok.com/api ג€” returns JSON array of jobs."""
    seen_ids: set[str] = set()
    for query in queries:
        tag = query.lower().replace(" ", "-")
        url = f"https://remoteok.com/api?tag={tag}"
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            for item in data:
                if not isinstance(item, dict) or "id" not in item:
                    continue
                jid = str(item.get("id", ""))
                if jid in seen_ids:
                    continue
                seen_ids.add(jid)
                yield {
                    "source": "RemoteOK",
                    "external_id": jid,
                    "title": item.get("position", ""),
                    "company": item.get("company", ""),
                    "location": "Remote",
                    "salary": item.get("salary", ""),
                    "url": item.get("url", f"https://remoteok.com/l/{jid}"),
                    "description": html.unescape(
                        re.sub(r"<[^>]+>", " ", item.get("description", ""))
                    ),
                }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise RateLimited("RemoteOK", hours=24)
            if e.response.status_code == 429:
                raise RateLimited("RemoteOK", hours=1)
            print(f"  [RemoteOK] Error for '{query}': {e}")
        except RateLimited:
            raise
        except Exception as e:
            print(f"  [RemoteOK] Error for '{query}': {e}")
        time.sleep(0.3)


# ---------------------------------------------------------------------------
# Source 2: Arbeitnow
# ---------------------------------------------------------------------------

def search_arbeitnow(queries: list[str]) -> Generator[dict, None, None]:
    """https://www.arbeitnow.com/api/job-board-api"""
    seen: set[str] = set()
    for query in queries:
        page = 1
        while page <= 2:
            url = "https://www.arbeitnow.com/api/job-board-api"
            try:
                resp = httpx.get(
                    url,
                    params={"search": query, "page": page},
                    headers=HEADERS,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                if not data:
                    break
                for item in data:
                    jurl = item.get("url", "")
                    if jurl in seen:
                        continue
                    seen.add(jurl)
                    title = item.get("title", "")
                    desc = html.unescape(
                        re.sub(r"<[^>]+>", " ", item.get("description", ""))
                    )
                    # Skip non-tech and non-English jobs
                    if not _is_tech_job(title, desc):
                        continue
                    yield {
                        "source": "Arbeitnow",
                        "external_id": item.get("slug", ""),
                        "title": title,
                        "company": item.get("company_name", ""),
                        "location": item.get("location", "Remote"),
                        "salary": "",
                        "url": jurl,
                        "description": desc,
                    }
                page += 1
                time.sleep(0.5)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    raise RateLimited("Arbeitnow", hours=24)
                if e.response.status_code == 429:
                    raise RateLimited("Arbeitnow", hours=1)
                print(f"  [Arbeitnow] Error for '{query}' page {page}: {e}")
                break
            except RateLimited:
                raise
            except Exception as e:
                print(f"  [Arbeitnow] Error for '{query}' page {page}: {e}")
                break


# ---------------------------------------------------------------------------
# Source 3: The Muse
# ---------------------------------------------------------------------------

_MUSE_CATEGORY_MAP = {
    "software engineer": "Software Engineer",
    "backend": "Software Engineer",
    "frontend": "Software Engineer",
    "fullstack": "Software Engineer",
    "data scientist": "Data Science",
    "machine learning": "Data Science",
    "devops": "IT",
    "product manager": "Project Management",
    "designer": "Design and UX",
}

def search_themuse(queries: list[str]) -> Generator[dict, None, None]:
    seen: set[str] = set()
    for query in queries:
        category = None
        ql = query.lower()
        for kw, cat in _MUSE_CATEGORY_MAP.items():
            if kw in ql:
                category = cat
                break

        page = 1
        while page <= 2:
            params: dict = {"page": page, "descending": "true"}
            if category:
                params["category"] = category
            try:
                resp = httpx.get(
                    "https://www.themuse.com/api/public/jobs",
                    params=params,
                    headers=HEADERS,
                    timeout=15,
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
                if not results:
                    break
                for item in results:
                    jurl = item.get("refs", {}).get("landing_page", "")
                    if jurl in seen:
                        continue
                    seen.add(jurl)
                    # Filter by query keyword in title
                    title = item.get("name", "")
                    if query.lower() not in title.lower() and not category:
                        continue
                    locs = item.get("locations", [])
                    location = locs[0].get("name", "Remote") if locs else "Remote"
                    contents = item.get("contents", "")
                    description = html.unescape(re.sub(r"<[^>]+>", " ", contents))
                    yield {
                        "source": "TheMuse",
                        "external_id": str(item.get("id", "")),
                        "title": title,
                        "company": item.get("company", {}).get("name", ""),
                        "location": location,
                        "salary": "",
                        "url": jurl,
                        "description": description,
                    }
                page += 1
                time.sleep(0.2)
            except Exception as e:
                print(f"  [TheMuse] Error for '{query}' page {page}: {e}")
                break


# ---------------------------------------------------------------------------
# Source 4: Adzuna (requires free API key)
# ---------------------------------------------------------------------------

def search_adzuna(queries: list[str], country: str = "us") -> Generator[dict, None, None]:
    app_id = os.environ.get("ADZUNA_APP_ID", "")
    api_key = os.environ.get("ADZUNA_API_KEY", "")
    if not app_id or not api_key:
        return

    seen: set[str] = set()
    for query in queries:
        for page in range(1, 4):
            url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
            try:
                resp = httpx.get(
                    url,
                    params={
                        "app_id": app_id,
                        "app_key": api_key,
                        "what": query,
                        "results_per_page": 20,
                        "content-type": "application/json",
                    },
                    headers=HEADERS,
                    timeout=15,
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
                if not results:
                    break
                for item in results:
                    jurl = item.get("redirect_url", "")
                    if jurl in seen:
                        continue
                    seen.add(jurl)
                    salary = ""
                    if item.get("salary_min") and item.get("salary_max"):
                        salary = f"${int(item['salary_min']):,} ג€“ ${int(item['salary_max']):,}"
                    yield {
                        "source": "Adzuna",
                        "external_id": item.get("id", ""),
                        "title": item.get("title", ""),
                        "company": item.get("company", {}).get("display_name", ""),
                        "location": item.get("location", {}).get("display_name", ""),
                        "salary": salary,
                        "url": jurl,
                        "description": item.get("description", ""),
                    }
                time.sleep(0.3)
            except Exception as e:
                print(f"  [Adzuna] Error for '{query}' page {page}: {e}")
                break


# ---------------------------------------------------------------------------
# Source 5: Hacker News "Who's Hiring"
# ---------------------------------------------------------------------------

def search_hn_hiring(queries: list[str]) -> Generator[dict, None, None]:
    """Parses the latest monthly HN 'Ask HN: Who is hiring?' thread."""
    try:
        # Find latest "Who is hiring" post
        search_resp = httpx.get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "query": "Ask HN: Who is hiring?",
                "tags": "story",
                "numericFilters": "points>100",
            },
            timeout=15,
        )
        search_resp.raise_for_status()
        hits = search_resp.json().get("hits", [])
        if not hits:
            return
        story_id = hits[0]["objectID"]

        # Get all top-level comments
        kids_resp = httpx.get(
            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
            timeout=15,
        )
        kids_resp.raise_for_status()
        kids = kids_resp.json().get("kids", [])[:50]

        for kid_id in kids:
            try:
                comment_resp = httpx.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{kid_id}.json",
                    timeout=10,
                )
                comment = comment_resp.json()
                text = comment.get("text", "")
                if not text:
                    continue
                plain = html.unescape(re.sub(r"<[^>]+>", " ", text))

                # Only yield if any query keyword matches
                matched = any(q.lower() in plain.lower() for q in queries)
                if not matched:
                    continue

                # Try to extract company name (first line usually is "Company | Location | ...")
                first_line = plain.split("\n")[0][:100]
                yield {
                    "source": "HN Hiring",
                    "external_id": str(kid_id),
                    "title": first_line,
                    "company": first_line.split("|")[0].strip() if "|" in first_line else "",
                    "location": "See description",
                    "salary": "",
                    "url": f"https://news.ycombinator.com/item?id={kid_id}",
                    "description": plain[:3000],
                }
            except Exception:
                continue
    except Exception as e:
        print(f"  [HN Hiring] Error: {e}")


# ---------------------------------------------------------------------------
# Source 6: Remotive (remote tech jobs, free API)
# ---------------------------------------------------------------------------

def search_remotive(queries: list[str]) -> Generator[dict, None, None]:
    """https://remotive.com/api/remote-jobs ג€” free, no auth required."""
    seen: set[str] = set()
    for query in queries:
        try:
            resp = httpx.get(
                "https://remotive.com/api/remote-jobs",
                params={"search": query, "limit": 50},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            jobs_data = resp.json().get("jobs", [])
            for item in jobs_data:
                jurl = item.get("url", "")
                if jurl in seen:
                    continue
                seen.add(jurl)
                title = item.get("title", "")
                desc = html.unescape(re.sub(r"<[^>]+>", " ", item.get("description", "")))
                yield {
                    "source": "Remotive",
                    "external_id": str(item.get("id", "")),
                    "title": title,
                    "company": item.get("company_name", ""),
                    "location": item.get("candidate_required_location", "Remote"),
                    "salary": item.get("salary", ""),
                    "url": jurl,
                    "description": desc,
                }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise RateLimited("Remotive", hours=24)
            if e.response.status_code == 429:
                raise RateLimited("Remotive", hours=1)
            print(f"  [Remotive] Error for '{query}': {e}")
        except RateLimited:
            raise
        except Exception as e:
            print(f"  [Remotive] Error for '{query}': {e}")
        time.sleep(0.3)


# ---------------------------------------------------------------------------
# Source 7: Jobicy (remote tech jobs, free API)
# ---------------------------------------------------------------------------

def search_jobicy(queries: list[str]) -> Generator[dict, None, None]:
    """https://jobicy.com/api/v2/remote-jobs ג€” free, no auth required."""
    seen: set[str] = set()
    for query in queries:
        try:
            resp = httpx.get(
                "https://jobicy.com/api/v2/remote-jobs",
                params={"tag": query, "count": 50},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            jobs_data = resp.json().get("jobs", [])
            for item in jobs_data:
                jurl = item.get("url", "")
                if jurl in seen:
                    continue
                seen.add(jurl)
                title = item.get("jobTitle", "")
                desc = html.unescape(re.sub(r"<[^>]+>", " ", item.get("jobDescription", "")))
                yield {
                    "source": "Jobicy",
                    "external_id": str(item.get("id", "")),
                    "title": title,
                    "company": item.get("companyName", ""),
                    "location": item.get("jobGeo", "Remote"),
                    "salary": item.get("annualSalaryMin", ""),
                    "url": jurl,
                    "description": desc,
                }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise RateLimited("Jobicy", hours=24)
            if e.response.status_code == 429:
                raise RateLimited("Jobicy", hours=1)
            print(f"  [Jobicy] Error for '{query}': {e}")
        except RateLimited:
            raise
        except Exception as e:
            print(f"  [Jobicy] Error for '{query}': {e}")
        time.sleep(0.3)


# ---------------------------------------------------------------------------
# Source 8: We Work Remotely (RSS feed, free, no auth)
# ---------------------------------------------------------------------------

def search_weworkremotely(queries: list[str]) -> Generator[dict, None, None]:
    """https://weworkremotely.com ג€” parses RSS feeds for programming/devops categories."""
    import xml.etree.ElementTree as ET

    feeds = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    ]
    seen: set[str] = set()

    for feed_url in feeds:
        try:
            resp = httpx.get(feed_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title_el = item.find("title")
                link_el  = item.find("link")
                desc_el  = item.find("description")
                region_el = item.find("{https://weworkremotely.com}region")

                title = title_el.text if title_el is not None else ""
                # WWR titles are "Company: Role" format
                if ":" in title:
                    company, role = title.split(":", 1)
                    company = company.strip()
                    title = role.strip()
                else:
                    company = ""

                jurl = link_el.text if link_el is not None else ""
                if not jurl or jurl in seen:
                    continue
                seen.add(jurl)

                desc = ""
                if desc_el is not None and desc_el.text:
                    desc = html.unescape(re.sub(r"<[^>]+>", " ", desc_el.text))

                location = region_el.text if region_el is not None else "Remote"

                if not _is_tech_job(title, desc):
                    continue

                yield {
                    "source": "WeWorkRemotely",
                    "external_id": jurl,
                    "title": title,
                    "company": company,
                    "location": location or "Remote",
                    "salary": "",
                    "url": jurl,
                    "description": desc,
                }
        except Exception as e:
            print(f"  [WeWorkRemotely] Error: {e}")
        time.sleep(0.3)


# ---------------------------------------------------------------------------
# Source 9: Working Nomads (JSON API, free, no auth)
# ---------------------------------------------------------------------------

def search_workingnomads(queries: list[str]) -> Generator[dict, None, None]:
    """https://www.workingnomads.com/api/exposed_jobs/ ג€” free JSON API."""
    seen: set[str] = set()
    categories = ["back-end", "dev-ops", "software-development", "game-development",
                  "front-end", "full-stack", "data-science"]

    # Build a lowercase set of query keywords for fast title/desc filtering
    query_words = {w.lower() for q in queries for w in q.lower().split()}

    for category in categories:
        try:
            resp = httpx.get(
                f"https://www.workingnomads.com/api/exposed_jobs/?category={category}",
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            jobs_data = resp.json()
            for item in jobs_data:
                jurl = item.get("url", "")
                if not jurl or jurl in seen:
                    continue

                title = item.get("title", "")
                desc = html.unescape(re.sub(r"<[^>]+>", " ", item.get("description", "")))

                if not _is_tech_job(title, desc):
                    continue

                # Filter: at least one query keyword must appear in title or description
                combined_lower = (title + " " + desc[:300]).lower()
                if not any(w in combined_lower for w in query_words):
                    continue

                seen.add(jurl)
                yield {
                    "source": "WorkingNomads",
                    "external_id": str(item.get("id", "")),
                    "title": title,
                    "company": item.get("company", ""),
                    "location": item.get("region", "Remote"),
                    "salary": item.get("salary", ""),
                    "url": jurl,
                    "description": desc,
                }
        except Exception as e:
            print(f"  [WorkingNomads] Error for '{category}': {e}")
        time.sleep(0.3)


# ---------------------------------------------------------------------------
# Source 10: Himalayas (free API, no auth, remote tech jobs)
# ---------------------------------------------------------------------------

def search_himalayas(queries: list[str]) -> Generator[dict, None, None]:
    """https://himalayas.app/jobs/api ג€” free, no auth, remote jobs only."""
    seen: set[str] = set()
    for query in queries:
        try:
            resp = httpx.get(
                "https://himalayas.app/jobs/api",
                params={"q": query, "limit": 50},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            jobs_data = resp.json().get("jobs", [])
            for item in jobs_data:
                jurl = item.get("applicationLink") or item.get("shortUrl", "")
                if not jurl or jurl in seen:
                    continue
                seen.add(jurl)
                title = item.get("title", "")
                desc = html.unescape(re.sub(r"<[^>]+>", " ", item.get("description", "")))

                if not _is_tech_job(title, desc):
                    continue

                salary = ""
                sal_min = item.get("salaryMin")
                sal_max = item.get("salaryMax")
                if sal_min and sal_max:
                    salary = f"${sal_min:,} ג€“ ${sal_max:,}"

                yield {
                    "source": "Himalayas",
                    "external_id": str(item.get("id", "")),
                    "title": title,
                    "company": item.get("companyName", ""),
                    "location": "Remote",
                    "salary": salary,
                    "url": jurl,
                    "description": desc,
                }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise RateLimited("Himalayas", hours=24)
            if e.response.status_code == 429:
                raise RateLimited("Himalayas", hours=1)
            print(f"  [Himalayas] Error for '{query}': {e}")
        except RateLimited:
            raise
        except Exception as e:
            print(f"  [Himalayas] Error for '{query}': {e}")
        time.sleep(0.3)


# ---------------------------------------------------------------------------
# Source 11: Drushim (Israeli job board ג€” regex HTML scrape, no extra deps)
# ---------------------------------------------------------------------------

def search_drushim(queries: list[str]) -> Generator[dict, None, None]:
    """Scrapes drushim.co.il tech category (cat26) using regex ג€” no lxml needed."""
    import urllib.parse
    seen: set[str] = set()

    for query in queries:
        for page in range(1, 3):
            q_enc = urllib.parse.quote_plus(query)
            url = f"https://www.drushim.co.il/jobs/cat26/?q={q_enc}"
            if page > 1:
                url += f"&page={page}"
            try:
                resp = httpx.get(url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
                body = resp.text

                # Job URLs: /job/{numeric_id}/{slug}/
                matches = re.findall(r'href="(/job/(\d+)/([^"/]+)/)"', body)
                if not matches:
                    break

                for href, job_id, slug in matches:
                    full_url = f"https://www.drushim.co.il{href}"
                    if full_url in seen:
                        continue
                    seen.add(full_url)

                    # Decode slug ג†’ readable title (mix of Hebrew/ASCII)
                    decoded = urllib.parse.unquote(slug).replace('-', ' ').replace('+', ' ')
                    ascii_title = re.sub(r'[^\x20-\x7E]+', ' ', decoded).strip()
                    title = ascii_title if len(ascii_title) > 3 else query

                    yield {
                        "source":      "Drushim",
                        "external_id": job_id,
                        "title":       title,
                        "company":     "",
                        "location":    "Israel",
                        "salary":      "",
                        "url":         full_url,
                        "description": f"{query} position in Israel. Full details at {full_url}",
                    }

                time.sleep(0.5)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    raise RateLimited("Drushim", hours=24)
                if e.response.status_code == 429:
                    raise RateLimited("Drushim", hours=1)
                print(f"  [Drushim] Error for '{query}' page {page}: {e}")
                break
            except RateLimited:
                raise
            except Exception as e:
                print(f"  [Drushim] Error for '{query}' page {page}: {e}")
                break


# ---------------------------------------------------------------------------
# Source 12: Indeed Israel (RSS feed ג€” free, no auth)
# ---------------------------------------------------------------------------

def search_indeed_israel(queries: list[str]) -> Generator[dict, None, None]:
    """Indeed Israel RSS ג€” https://il.indeed.com ג€” no auth required."""
    import urllib.parse
    import xml.etree.ElementTree as ET
    seen: set[str] = set()

    for query in queries:
        q_enc = urllib.parse.quote_plus(query)
        url = f"https://il.indeed.com/rss?q={q_enc}&l=Israel&sort=date&fromage=30"
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 403:
                raise RateLimited("Indeed IL", hours=24)  # hard block
            if resp.status_code == 429:
                raise RateLimited("Indeed IL", hours=1)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            for item in root.findall(".//item"):
                link_el  = item.find("link")
                title_el = item.find("title")
                desc_el  = item.find("description")

                jurl = (link_el.text or "").strip() if link_el is not None else ""
                if not jurl or jurl in seen:
                    continue
                seen.add(jurl)

                raw = (title_el.text or query).strip() if title_el is not None else query
                # Indeed format: "Title - Company - City, Country"
                parts   = raw.split(" - ")
                title   = parts[0].strip() if parts else raw
                company = parts[1].strip() if len(parts) >= 2 else ""
                loc     = parts[2].strip() if len(parts) >= 3 else "Israel"

                desc = ""
                if desc_el is not None and desc_el.text:
                    desc = html.unescape(re.sub(r"<[^>]+>", " ", desc_el.text))

                jk = re.search(r'jk=([a-z0-9]+)', jurl)
                ext_id = jk.group(1) if jk else jurl[-16:]

                yield {
                    "source":      "Indeed IL",
                    "external_id": ext_id,
                    "title":       title,
                    "company":     company,
                    "location":    loc,
                    "salary":      "",
                    "url":         jurl,
                    "description": desc,
                }
        except RateLimited:
            raise   # propagates up ג†’ prints once and skips all remaining queries
        except Exception as e:
            print(f"  [Indeed IL] Error for '{query}': {e}")
        time.sleep(0.4)


# ---------------------------------------------------------------------------
# Source 13: AllJobs (Israel's largest job board ג€” internal JSON API)
# ---------------------------------------------------------------------------

def search_alljobs(queries: list[str]) -> Generator[dict, None, None]:
    """AllJobs.co.il ג€” internal search API (no auth required)."""
    seen: set[str] = set()

    for query in queries:
        for page in range(1, 3):
            try:
                resp = httpx.get(
                    "https://www.alljobs.co.il/SiteApi/Searches/SearchJobsResults",
                    params={"search": query, "page": page,
                            "location": "", "type": "", "field": "", "fromdate": ""},
                    headers={**HEADERS,
                             "Referer":          "https://www.alljobs.co.il/",
                             "X-Requested-With": "XMLHttpRequest"},
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()

                items: list = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = (data.get("Jobs") or data.get("jobs")
                             or data.get("results") or [])
                if not items:
                    break

                for item in items:
                    job_id = str(item.get("Id") or item.get("id")
                                 or item.get("JobId") or "")
                    if not job_id:
                        continue
                    jurl = f"https://www.alljobs.co.il/Job.aspx?jobId={job_id}"
                    if jurl in seen:
                        continue
                    seen.add(jurl)

                    title   = (item.get("Title") or item.get("title")
                               or item.get("JobTitle") or query)
                    company = (item.get("Company") or item.get("company")
                               or item.get("CompanyName") or "")
                    city    = (item.get("City") or item.get("city")
                               or item.get("Location") or "Israel")
                    raw_desc = item.get("Description") or item.get("description") or ""
                    desc    = html.unescape(re.sub(r"<[^>]+>", " ", str(raw_desc))) if raw_desc else ""
                    loc     = (f"{city}, Israel"
                               if city and "israel" not in city.lower() else city)

                    yield {
                        "source":      "AllJobs",
                        "external_id": job_id,
                        "title":       title,
                        "company":     company,
                        "location":    loc,
                        "salary":      "",
                        "url":         jurl,
                        "description": desc,
                    }

                time.sleep(0.4)
            except Exception as e:
                print(f"  [AllJobs] Error for '{query}' page {page}: {e}")
                break


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------

class RateLimited(Exception):
    """Raised by a source function when it hits a rate limit.

    Args:
        source: human-readable source label (must match source_map label key)
        hours:  how long to block this source (1 = 429/retry-after, 24 = 403/hard-block)
    """
    def __init__(self, source: str, hours: float = 1.0):
        self.source = source
        self.hours  = hours
        super().__init__(f"{source} rate-limited for {hours}h")


# Israeli city / location keywords used to filter search results
_ISRAEL_CITIES = {
    "israel", "tel aviv", "tel-aviv", "tlv", "ramat gan", "herzliya", "haifa",
    "beer sheva", "be'er sheva", "jerusalem", "rishon lezion", "petah tikva",
    "netanya", "rehovot", "holon", "bnei brak", "ashdod", "ashkelon",
    "ra'anana", "kfar saba", "modi'in", "eilat", "lod", "ramla",
    "givatayim", "kiryat", "hod hasharon", "yavne", "bat yam",
    "center, israel", "north, israel", "south, israel",
}
_REMOTE_WORDS = {"remote", "anywhere", "worldwide", "distributed", "wfh"}


def _is_israel_relevant(job: dict) -> bool:
    """Return True for Israeli-location jobs or remote jobs (valid for Israeli workers)."""
    src  = job.get("source", "")
    loc  = (job.get("location") or "").lower()
    desc = (job.get("description") or "")[:300].lower()
    # Israeli-native boards always pass
    if src in ("Drushim", "AllJobs", "Indeed IL"):
        return True
    if any(kw in loc  for kw in _REMOTE_WORDS): return True
    if any(kw in desc for kw in _REMOTE_WORDS): return True
    if any(city in loc for city in _ISRAEL_CITIES): return True
    return False


def search_all_sources(
    queries: list[str],
    sources: list[str] | None = None,
    remote_only: bool = False,
    israel_only: bool = False,
) -> list[dict]:
    """
    Search all enabled sources in parallel and return de-duplicated job listings.

    israel_only ג€” use Israeli job boards + global remote boards, then filter
                  results to Israel-based or remote positions.
    remote_only ג€” keep only jobs tagged remote/worldwide.
    """
    all_sources = [
        "remoteok", "arbeitnow", "themuse", "adzuna", "hn",
        "remotive", "jobicy", "workingnomads", "himalayas",
        "drushim", "indeed_il", "alljobs",
    ]

    source_map = {
        "remoteok":      ("RemoteOK",       lambda: list(search_remoteok(queries)),        True),
        "arbeitnow":     ("Arbeitnow",      lambda: list(search_arbeitnow(queries)),       True),
        "themuse":       ("The Muse",       lambda: list(search_themuse(queries)),         True),
        "adzuna":        ("Adzuna",         lambda: list(search_adzuna(queries)),          bool(os.environ.get("ADZUNA_APP_ID"))),
        "hn":            ("HN Hiring",      lambda: list(search_hn_hiring(queries)),       True),
        "remotive":      ("Remotive",       lambda: list(search_remotive(queries)),        True),
        "jobicy":        ("Jobicy",         lambda: list(search_jobicy(queries)),          True),
        "workingnomads": ("Working Nomads", lambda: list(search_workingnomads(queries)),   True),
        "himalayas":     ("Himalayas",      lambda: list(search_himalayas(queries)),       True),
        "drushim":       ("Drushim",        lambda: list(search_drushim(queries)),         True),
        "indeed_il":     ("Indeed IL",      lambda: list(search_indeed_israel(queries)),   True),
        "alljobs":       ("AllJobs",        lambda: list(search_alljobs(queries)),         True),
    }

    # Israel mode: Israeli boards + global remote boards (remote jobs are valid for IL workers)
    if israel_only and sources is None:
        enabled = {"drushim", "indeed_il", "alljobs",
                   "remoteok", "remotive", "jobicy", "himalayas"}
    else:
        enabled = set(s.lower() for s in (sources or all_sources))

    queue = [n for n in all_sources if n in enabled and source_map[n][2]]

    # Check existing rate limits from MongoDB before running any source
    try:
        import database as _db
        active_limits = _db.get_rate_limits()   # {label: {"expires_at": iso, "hours": n}}
    except Exception:
        active_limits = {}

    results_lock = threading.Lock()
    all_jobs: list[dict] = []

    def run_source(name: str) -> tuple[str, list[dict]]:
        from datetime import datetime as _dt
        label, fn, _ = source_map[name]

        # Skip source if still inside its cooldown window
        if label in active_limits:
            exp_iso = active_limits[label]["expires_at"]
            try:
                remaining = _dt.fromisoformat(exp_iso) - _dt.utcnow()
                secs = max(0, remaining.total_seconds())
                hrs  = int(secs // 3600)
                mins = int((secs % 3600) // 60)
                time_str = f"{hrs}h {mins}m" if hrs else f"{mins}m"
            except Exception:
                time_str = "a while"
            print(f"  [{label}] Rate-limited — skipping (available in {time_str})")
            return name, []

        print(f"  Searching {label}...")
        try:
            jobs = fn()
            # Successful run — clear any stale limit
            try:
                _db.clear_rate_limit(label)
            except Exception:
                pass
            print(f"  [{label}] {len(jobs)} jobs found")
            return name, jobs
        except RateLimited as rl:
            try:
                _db.set_rate_limit(label, hours=rl.hours)
            except Exception:
                pass
            print(f"  [{label}] Rate limited — blocked for {rl.hours}h")
            return name, []
        except Exception as e:
            print(f"  [{label}] Error: {e}")
            return name, []

        with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(run_source, name): name for name in queue}
        for future in as_completed(futures, timeout=180):
            try:
                _, jobs = future.result()
                with results_lock:
                    all_jobs.extend(jobs)
            except Exception as e:
                print(f"  Source error: {e}")

    # Deduplicate by URL
    seen_urls: set[str] = set()
    jobs: list[dict] = []
    for job in all_jobs:
        url = job.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            jobs.append(job)

    # Location filtering
    if israel_only:
        jobs = [j for j in jobs if _is_israel_relevant(j)]
    elif remote_only:
        keywords = {"remote", "anywhere", "worldwide", "distributed", "wfh"}
        jobs = [
            j for j in jobs
            if j["source"] == "RemoteOK"
            or any(kw in j.get("location", "").lower() for kw in keywords)
            or any(kw in j.get("description", "").lower()[:200] for kw in keywords)
        ]

    return jobs

