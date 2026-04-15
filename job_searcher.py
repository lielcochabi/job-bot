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
    """https://remoteok.com/api — returns JSON array of jobs."""
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
            if e.response.status_code in (403, 429):
                raise RateLimited("RemoteOK")
            print(f"  [RemoteOK] Error for '{query}': {e}")
        except RateLimited:
            raise
        except Exception as e:
            print(f"  [RemoteOK] Error for '{query}': {e}")
        time.sleep(1)


# ---------------------------------------------------------------------------
# Source 2: Arbeitnow
# ---------------------------------------------------------------------------

def search_arbeitnow(queries: list[str]) -> Generator[dict, None, None]:
    """https://www.arbeitnow.com/api/job-board-api"""
    seen: set[str] = set()
    for query in queries:
        page = 1
        while page <= 3:
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
                time.sleep(2)  # be polite to avoid rate limiting
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (403, 429):
                    raise RateLimited("Arbeitnow")
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
        while page <= 3:
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
                time.sleep(0.5)
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
                        salary = f"${int(item['salary_min']):,} – ${int(item['salary_max']):,}"
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
                time.sleep(0.5)
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
        kids = kids_resp.json().get("kids", [])[:100]

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
                time.sleep(0.1)
            except Exception:
                continue
    except Exception as e:
        print(f"  [HN Hiring] Error: {e}")


# ---------------------------------------------------------------------------
# Source 6: Remotive (remote tech jobs, free API)
# ---------------------------------------------------------------------------

def search_remotive(queries: list[str]) -> Generator[dict, None, None]:
    """https://remotive.com/api/remote-jobs — free, no auth required."""
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
            if e.response.status_code in (403, 429):
                raise RateLimited("Remotive")
            print(f"  [Remotive] Error for '{query}': {e}")
        except RateLimited:
            raise
        except Exception as e:
            print(f"  [Remotive] Error for '{query}': {e}")
        time.sleep(1)


# ---------------------------------------------------------------------------
# Source 7: Jobicy (remote tech jobs, free API)
# ---------------------------------------------------------------------------

def search_jobicy(queries: list[str]) -> Generator[dict, None, None]:
    """https://jobicy.com/api/v2/remote-jobs — free, no auth required."""
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
            if e.response.status_code in (403, 429):
                raise RateLimited("Jobicy")
            print(f"  [Jobicy] Error for '{query}': {e}")
        except RateLimited:
            raise
        except Exception as e:
            print(f"  [Jobicy] Error for '{query}': {e}")
        time.sleep(1)


# ---------------------------------------------------------------------------
# Source 8: We Work Remotely (RSS feed, free, no auth)
# ---------------------------------------------------------------------------

def search_weworkremotely(queries: list[str]) -> Generator[dict, None, None]:
    """https://weworkremotely.com — parses RSS feeds for programming/devops categories."""
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
        time.sleep(1)


# ---------------------------------------------------------------------------
# Source 9: Working Nomads (JSON API, free, no auth)
# ---------------------------------------------------------------------------

def search_workingnomads(queries: list[str]) -> Generator[dict, None, None]:
    """https://www.workingnomads.com/api/exposed_jobs/ — free JSON API."""
    seen: set[str] = set()
    categories = ["back-end", "dev-ops", "software-development", "game-development"]

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
                seen.add(jurl)
                title = item.get("title", "")
                desc = html.unescape(re.sub(r"<[^>]+>", " ", item.get("description", "")))

                if not _is_tech_job(title, desc):
                    continue

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
        time.sleep(1)


# ---------------------------------------------------------------------------
# Source 10: Himalayas (free API, no auth, remote tech jobs)
# ---------------------------------------------------------------------------

def search_himalayas(queries: list[str]) -> Generator[dict, None, None]:
    """https://himalayas.app/jobs/api — free, no auth, remote jobs only."""
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
                    salary = f"${sal_min:,} – ${sal_max:,}"

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
            if e.response.status_code in (403, 429):
                raise RateLimited("Himalayas")
            print(f"  [Himalayas] Error for '{query}': {e}")
        except RateLimited:
            raise
        except Exception as e:
            print(f"  [Himalayas] Error for '{query}': {e}")
        time.sleep(1)


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------

class RateLimited(Exception):
    """Raised by a source function when it hits a rate limit."""
    pass


def search_all_sources(
    queries: list[str],
    sources: list[str] | None = None,
    remote_only: bool = False,
) -> list[dict]:
    """
    Search all enabled sources and return de-duplicated job listings.
    If a source is rate-limited it is moved to the back of the queue
    and retried once after all other sources finish (with a 30s wait).
    """
    all_sources = ["remoteok", "arbeitnow", "themuse", "adzuna", "hn", "remotive", "jobicy",
                   "weworkremotely", "workingnomads", "himalayas"]
    enabled = set(s.lower() for s in (sources or all_sources))

    jobs: list[dict] = []
    seen_urls: set[str] = set()

    def add(gen):
        for job in gen:
            url = job.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                jobs.append(job)

    # Map name -> (label, function, extra_check)
    source_map = {
        "remoteok":       ("RemoteOK",          lambda: search_remoteok(queries),       True),
        "arbeitnow":      ("Arbeitnow",          lambda: search_arbeitnow(queries),      True),
        "themuse":        ("The Muse",           lambda: search_themuse(queries),        True),
        "adzuna":         ("Adzuna",             lambda: search_adzuna(queries),         bool(os.environ.get("ADZUNA_APP_ID"))),
        "hn":             ("HN Who's Hiring",    lambda: search_hn_hiring(queries),      True),
        "remotive":       ("Remotive",           lambda: search_remotive(queries),       True),
        "jobicy":         ("Jobicy",             lambda: search_jobicy(queries),         True),
        "weworkremotely": ("We Work Remotely",   lambda: search_weworkremotely(queries), True),
        "workingnomads":  ("Working Nomads",     lambda: search_workingnomads(queries),  True),
        "himalayas":      ("Himalayas",          lambda: search_himalayas(queries),      True),
    }

    # Build ordered queue of sources to run
    queue = [name for name in all_sources if name in enabled]
    retried: set[str] = set()

    while queue:
        name = queue.pop(0)
        label, fn, check = source_map[name]

        if not check:
            print(f"  Skipping {label} (no API key in .env)")
            continue

        is_retry = name in retried
        print(f"  Searching {label}{'  [retry]' if is_retry else ''}...")

        try:
            add(fn())
        except RateLimited:
            if not is_retry:
                print(f"  [{label}] Busy — will retry after other sources...")
                retried.add(name)
                queue.append(name)
                time.sleep(2)
            else:
                print(f"  [{label}] Skipped.")
        except Exception as e:
            print(f"  [{label}] Skipped.")

        # If we just finished the main sources and retries are next, wait a bit
        if queue and queue[0] in retried and len([q for q in queue if q not in retried]) == 0:
            print(f"  Waiting 30s before retrying rate-limited sources...")
            time.sleep(30)

    if remote_only:
        keywords = {"remote", "anywhere", "worldwide", "distributed", "wfh"}
        jobs = [
            j for j in jobs
            if j["source"] == "RemoteOK"
            or any(kw in j.get("location", "").lower() for kw in keywords)
            or any(kw in j.get("description", "").lower()[:200] for kw in keywords)
        ]

    return jobs
