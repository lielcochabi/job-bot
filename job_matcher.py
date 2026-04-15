"""
Rule-based job matcher — completely free, no AI API needed.
Scores jobs 0-100 based on skill match, seniority, location, role type, and language.
Threshold default: 70 (configurable in config.json as match_threshold).
"""
from __future__ import annotations

import json
import re
from typing import Optional

import database

# ---------------------------------------------------------------------------
# Skill weights — edit these to match your own skills
# Higher number = more important to you and more impactful on score
# ---------------------------------------------------------------------------

DEFAULT_SKILL_WEIGHTS: dict[str, int] = {
    # Python ecosystem (your strongest area)
    "python": 15,
    "fastapi": 12,
    "django": 9,
    "flask": 7,
    "pydantic": 5,
    "asyncio": 4,
    # Databases
    "mongodb": 8,
    "postgresql": 6,
    "mysql": 5,
    "redis": 6,
    "nosql": 5,
    "sql": 4,
    # DevOps / Cloud (you have real experience here)
    "docker": 10,
    "kubernetes": 10,
    "k8s": 10,
    "ci/cd": 7,
    "gitlab": 6,
    "github actions": 5,
    "aws": 7,
    "gcp": 6,
    "azure": 5,
    "terraform": 4,
    "linux": 4,
    "bash": 4,
    # APIs & architecture
    "rest api": 7,
    "restful": 6,
    "graphql": 5,
    "openapi": 5,
    "microservices": 6,
    # AI / LLM (you have DSPy experience)
    "llm": 10,
    "dspy": 8,
    "langchain": 7,
    "machine learning": 7,
    "ai": 5,
    "nlp": 6,
    "openai": 5,
    "anthropic": 5,
    "prompt": 4,
    # General dev tools
    "git": 3,
    "streamlit": 5,
    # Game dev (secondary — Unity VR + Unreal Engine)
    "unity": 5,
    "unreal": 5,
    "vr": 4,
    "xr": 4,
    "blueprint": 3,
}

# ---------------------------------------------------------------------------
# Seniority keywords
# ---------------------------------------------------------------------------

_SENIOR_TITLE_WORDS = {
    "senior", "lead", "principal", "staff", "manager", "director",
    "head of", "vp ", "vice president", "architect", "founding engineer",
    "tech lead", "team lead", "engineering manager", "cto", "cpo",
    "sr.", "sr ", "distinguished", "site reliability engineer",
    " v ", " iv ", " iii ",  # "Software Engineer V", "Engineer III"
}

_JUNIOR_TITLE_WORDS = {
    "junior", "intern", "internship", "entry", "entry-level", "entry level",
    "student", "werkstudent", "working student", "graduate", "trainee",
    "apprentice", "jr.", "jr ", "associate", "early career",
    "new grad", "fresh grad",
}

# ---------------------------------------------------------------------------
# Role whitelist — job title MUST match one of these categories to pass
# ---------------------------------------------------------------------------

_ALLOWED_ROLE_KEYWORDS = {
    # Software engineering (general)
    "software engineer", "software developer", "software dev",
    # Backend
    "backend", "back-end", "back end",
    "api developer", "api engineer",
    "python developer", "python engineer",
    "fastapi", "django developer", "django engineer",
    "node developer", "node engineer",
    "java developer", "java engineer",
    "golang developer", "go developer",
    "rust developer", "rust engineer",
    # Fullstack (includes backend work)
    "fullstack", "full stack", "full-stack",
    # DevOps / cloud / infrastructure (backend-adjacent)
    "devops", "platform engineer", "sre", "site reliability",
    "cloud engineer", "infrastructure engineer",
    "solutions architect", "solutions engineer",
    # Game dev
    "game developer", "game engineer", "game dev",
    "unity developer", "unity engineer",
    "unreal developer", "unreal engineer",
    "gameplay engineer", "gameplay developer",
    "vr developer", "xr developer",
    # AI / ML (Liel has LLM/DSPy experience)
    "ml engineer", "machine learning engineer",
    "ai engineer", "llm engineer",
    "data engineer",
    # Intern / student variants of the above
    "werkstudent", "working student", "student developer",
    "intern", "internship", "trainee",
}

# Hard-block list — even if a whitelist keyword matches, reject these
_NON_TECH_TITLES = {
    "sales", "marketing", "recruiter", "recruiting", "accountant",
    "accounting", "finance analyst", "financial analyst", "legal",
    "hr ", "human resources", "content creator", "customer success",
    "product designer", "graphic designer", "ux designer", "ui designer",
    "community manager", "social media", "copywriter", "content writer",
    "business development", "account manager", "office manager",
    "supply chain", "logistics", "quality engineer", "electrical engineer",
    "mechanical engineer", "civil engineer", "lsa engineer",
    "system safety engineer", "supplier quality", "sales manager",
    "customer service", "brand personality", "influencer",
    "administrative", "reception",
}

# ---------------------------------------------------------------------------
# Experience level detection
# ---------------------------------------------------------------------------

# Patterns that mean "requires 3+ years" → hard disqualify
_HIGH_EXP_PATTERNS = [
    r"\b([3-9]|\d{2})\+?\s*years?\s*(of\s+)?(professional\s+)?experience",
    r"\bminimum\s+[3-9]\s*years?",
    r"\bat\s+least\s+[3-9]\s*years?",
    r"\b[3-9]\s*[-–]\s*\d+\s*years?\s*(of\s+)?experience",
    r"\bexperience[:\s]+[3-9]\+?\s*years?",
]

# Patterns that confirm entry/junior level → boost
_LOW_EXP_PATTERNS = [
    r"\b0[-–]2\s*years?",
    r"\b1[-–]2\s*years?",
    r"\bentry[\s\-]level",
    r"\bno\s+experience\s+required",
    r"\bfresh\s+grad",
    r"\bnew\s+grad",
    r"\bjunior\s+developer",
    r"\bjunior\s+engineer",
    r"\bstudent\s+position",
    r"\bwerkstudent",
    r"\bworking\s+student",
    r"\binternship",
]


def _experience_pts(title: str, desc: str) -> tuple[int, str]:
    """
    Returns (points, reason).
    Hard blocks (return -999) if description requires 3+ years experience.
    """
    combined = (title + " " + desc[:1500]).lower()

    # Check for high experience requirements → disqualify entirely
    for pattern in _HIGH_EXP_PATTERNS:
        if re.search(pattern, combined):
            return -999, f"Requires 3+ years experience"

    # Check for explicit entry/junior signals → bonus
    for pattern in _LOW_EXP_PATTERNS:
        if re.search(pattern, combined):
            return 10, "Entry/junior level confirmed"

    return 0, ""


# ---------------------------------------------------------------------------
# Location helpers
# ---------------------------------------------------------------------------

_REMOTE_KEYWORDS = {
    "remote", "anywhere", "worldwide", "global", "distributed",
    "work from home", "wfh", "fully remote", "100% remote", "remote-first",
    "remote first", "remote ok", "remote friendly",
}

_GOOD_REGIONS = {
    "eu", "europe", "emea", "israel", "apac", "international",
    "worldwide", "global",
}

_US_ONLY_PHRASES = [
    "united states only", "us only", "usa only", "us citizens only",
    "must be located in the us", "must be based in the us",
    "north america only", "authorized to work in the us",
    "work authorization in the us",
]

_ONSITE_ONLY_PHRASES = {
    "onsite only", "on-site only", "no remote", "office only",
    "in-office only", "must be in office",
}

# German cities in location field = likely on-site Germany
_GERMAN_CITIES = {
    "munich", "münchen", "berlin", "hamburg", "frankfurt", "cologne",
    "köln", "braunschweig", "osnabrück", "stuttgart", "düsseldorf",
    "hannover", "leipzig", "dresden", "nuremberg", "nürnberg",
    "mannheim", "heidelberg", "karlsruhe", "bremen", "dortmund",
}

# ---------------------------------------------------------------------------
# German language detection — penalise if German proficiency is required
# ---------------------------------------------------------------------------

_GERMAN_REQUIRED_PHRASES = [
    "deutschkenntnisse", "fließend deutsch", "german is required",
    "german language is a must", "german required", "sehr gute deutschkenntnisse",
    "muttersprachliches deutsch", "c1 german", "b2 german",
    "german speaker required", "must speak german",
]

_GERMAN_BODY_PHRASES = [
    "wir suchen", "aufgaben", "anforderungen", "kenntnisse", "erfahrung",
    "stellenanzeige", "bewerbung", "gehalt", "vollzeit", "teilzeit",
    "unbefristete", "bewerben", "lebenslauf",
]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _seniority(title: str) -> str:
    t = title.lower()
    if any(kw in t for kw in _SENIOR_TITLE_WORDS):
        return "senior"
    if any(kw in t for kw in _JUNIOR_TITLE_WORDS):
        return "junior"
    return "mid"


def _is_tech_role(title: str) -> bool:
    """
    Return True only if the title matches an allowed role category
    AND does not match the hard-block list.
    """
    t = title.lower()
    if any(kw in t for kw in _NON_TECH_TITLES):
        return False
    return any(kw in t for kw in _ALLOWED_ROLE_KEYWORDS)


def _location_pts(job: dict) -> int:
    loc = (job.get("location") or "").lower()
    desc_head = (job.get("description") or "")[:500].lower()
    combined = loc + " " + desc_head

    if any(p in combined for p in _US_ONLY_PHRASES):
        return -25
    if any(p in combined for p in _ONSITE_ONLY_PHRASES):
        return -20
    # German city in location without remote mention = on-site Germany
    if any(city in loc for city in _GERMAN_CITIES):
        if not any(kw in combined for kw in _REMOTE_KEYWORDS):
            return -20
    if any(kw in combined for kw in _REMOTE_KEYWORDS | _GOOD_REGIONS):
        return 0
    return -10  # unknown — slight penalty


def _language_pts(desc: str) -> int:
    d = desc[:800].lower()
    # If German is explicitly required → hard penalty
    if any(p in d for p in _GERMAN_REQUIRED_PHRASES):
        return -25
    # If body text is mostly German (job written in German) → penalty
    german_body_hits = sum(1 for p in _GERMAN_BODY_PHRASES if p in d)
    if german_body_hits >= 4:
        return -20
    if german_body_hits >= 2:
        return -10
    return 0


def _skill_pts(job: dict, weights: dict[str, int]) -> tuple[int, list[str]]:
    combined = (
        (job.get("title") or "") + " " + (job.get("description") or "")
    ).lower()

    matched: list[str] = []
    total = 0
    for skill, w in weights.items():
        if skill in combined:
            matched.append(skill)
            total += w

    return min(55, total), matched


def _relevance_bonus(title: str, desc: str) -> int:
    t = title.lower()
    d = desc[:400].lower()
    bonus = 0

    if any(kw in t for kw in ["backend", "back-end", "python developer", "fastapi", "api developer"]):
        bonus += 10
    elif any(kw in t for kw in ["software engineer", "software developer", "full stack", "fullstack"]):
        bonus += 5
    elif any(kw in t for kw in ["devops", "platform engineer", "sre", "cloud engineer"]):
        bonus += 5

    if any(kw in t + " " + d[:100] for kw in ["llm", "ai engineer", "ml engineer", "dspy", "langchain", "agentic"]):
        bonus += 5

    return bonus


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def match_job(
    job: dict,
    resume_text: str,           # kept for API compatibility, not used in rule-based mode
    threshold: float = 70.0,
    skill_weights: Optional[dict[str, int]] = None,
) -> tuple[float, str]:
    """
    Score a job using rule-based logic. Returns (score 0-100, reason_json).
    Signature matches the old Claude-based version for drop-in compatibility.
    """
    title = job.get("title") or ""
    desc = job.get("description") or ""
    weights = skill_weights or DEFAULT_SKILL_WEIGHTS

    # 1. Instant disqualify non-tech roles
    if not _is_tech_role(title):
        return 0.0, json.dumps({
            "reason": f"Non-tech role filtered out: {title[:60]}",
            "matched": [], "missing": [],
        })

    # 2. Experience check — hard block if 3+ years required
    exp_pts, exp_reason = _experience_pts(title, desc)
    if exp_pts == -999:
        return 0.0, json.dumps({
            "reason": exp_reason,
            "matched": [], "missing": [],
        })

    # 3. Skill match (0–55 pts)
    skill_score, matched = _skill_pts(job, weights)

    # 4. Seniority (–30 to +15 pts)
    level = _seniority(title)
    level_pts = {"senior": -30, "junior": 15, "mid": 5}[level]

    # 5. Location (0 to –25 pts)
    loc_pts = _location_pts(job)

    # 6. Language (0 to –25 pts)
    lang_pts = _language_pts(desc)

    # 7. Role relevance bonus (0–15 pts)
    bonus = _relevance_bonus(title, desc)

    # 8. Base: every tech role starts at 20
    base = 20

    total = base + skill_score + level_pts + loc_pts + lang_pts + bonus + exp_pts
    total = round(max(0.0, min(100.0, float(total))), 1)

    reason = json.dumps({
        "score_breakdown": {
            "base": base,
            "skills": skill_score,
            "level": f"{level} ({level_pts:+d}pts)",
            "location": loc_pts,
            "language": lang_pts,
            "relevance_bonus": bonus,
            "experience": exp_pts,
        },
        "matched": matched[:10],
        "reason": (
            f"Seniority: {level}. "
            f"Skills matched: {', '.join(matched[:6]) or 'none'}. "
            f"Location pts: {loc_pts}. "
            + (exp_reason if exp_reason else "")
        ),
    }, ensure_ascii=False)

    return total, reason


# ---------------------------------------------------------------------------
# Batch scorer
# ---------------------------------------------------------------------------

def match_all_unmatched(
    resume_text: str,
    threshold: float = 70.0,
    verbose: bool = True,
    skill_weights: Optional[dict[str, int]] = None,
) -> dict:
    """Score all unscored jobs in the database. Returns stats dict."""
    jobs = database.get_unmatched_jobs()
    if not jobs:
        return {"processed": 0, "matched": 0, "skipped": 0}

    matched_count = 0
    skipped_count = 0

    for i, job in enumerate(jobs, 1):
        if verbose:
            print(
                f"  [{i}/{len(jobs)}] {(job['title'] or '')[:45].encode('ascii','replace').decode()}"
                f" @ {(job.get('company') or 'Unknown')[:20].encode('ascii','replace').decode()}"
            )

        score, reason = match_job(job, resume_text, threshold, skill_weights)
        database.set_match(job["id"], score, reason)

        label = "[MATCH]" if score >= threshold else "[skip] "
        if verbose:
            print(f"         {label} score: {score:.0f}/100")

        if score >= threshold:
            matched_count += 1
        else:
            skipped_count += 1

    return {"processed": len(jobs), "matched": matched_count, "skipped": skipped_count}


def get_match_summary(job: dict) -> dict:
    """Parse stored reason JSON into a human-readable dict."""
    try:
        return json.loads(job.get("match_reason") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {"reason": job.get("match_reason", "")}
