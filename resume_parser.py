"""
Parse resume files (PDF/DOCX) and extract a structured profile.
100% free — uses regex and keyword matching, no AI API calls.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Optional

import database

RESUME_SEARCH_PATHS = [
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "iCloudDrive",
    Path.home() / "iCloudDrive" / "Downloads",
    Path.home() / "OneDrive",
]

# All tech skills we can detect in a resume
_DETECTABLE_SKILLS = [
    "python", "fastapi", "django", "flask", "pydantic",
    "mongodb", "postgresql", "mysql", "redis", "sqlite", "nosql", "sql",
    "docker", "kubernetes", "k8s", "ci/cd", "gitlab", "github actions",
    "aws", "gcp", "azure", "terraform", "linux", "bash",
    "rest api", "restful", "graphql", "openapi", "microservices",
    "llm", "dspy", "langchain", "machine learning", "deep learning",
    "nlp", "openai", "streamlit", "pandas", "numpy", "scikit",
    "javascript", "typescript", "react", "vue", "angular", "node.js",
    "java", "golang", "go ", "rust", "c++", "c#", ".net", "php",
    "git", "unity", "unreal engine", "blueprint", "vr", "xr",
    "html", "css", "tailwind",
]


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_resume_files() -> list[Path]:
    found: list[Path] = []
    patterns = ["*resume*", "*cv*", "*Resume*", "*CV*", "*curriculum*"]
    suffixes = {".pdf", ".docx", ".doc"}

    for search_dir in RESUME_SEARCH_PATHS:
        if not search_dir.exists():
            continue
        for pattern in patterns:
            for f in search_dir.glob(pattern):
                if f.suffix.lower() in suffixes and f not in found:
                    found.append(f)

    return found


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(path: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n".join(pages)
    except Exception as e:
        return f"[PDF parse error: {e}]"


def extract_text_from_docx(path: Path) -> str:
    try:
        from docx import Document
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        return f"[DOCX parse error: {e}]"


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    elif suffix in (".docx", ".doc"):
        return extract_text_from_docx(path)
    return ""


# ---------------------------------------------------------------------------
# Parse all resumes
# ---------------------------------------------------------------------------

def parse_all_resumes(verbose: bool = True) -> str:
    database.init_db()
    files = find_resume_files()

    if not files:
        raise FileNotFoundError(
            "No resume files found. Place your resume PDF/DOCX in Desktop, "
            "Downloads, or Documents and try again."
        )

    if verbose:
        print(f"Found {len(files)} resume file(s):")
        for f in files:
            print(f"  - {f.name}")

    for path in files:
        text = extract_text(path)
        if text and not text.startswith("["):
            database.save_resume(str(path), text)
            if verbose:
                print(f"  [OK] Parsed {path.name} ({len(text)} chars)")

    combined = database.get_resume_content()
    if not combined:
        raise ValueError("Could not extract text from any resume file.")

    return combined


# ---------------------------------------------------------------------------
# Rule-based profile extraction (replaces Claude — 100% free)
# ---------------------------------------------------------------------------

def extract_resume_profile(resume_text: str) -> dict:
    """
    Extract a structured profile dict from raw resume text.
    Uses regex and keyword matching — no API calls required.
    """
    text = resume_text
    text_lower = text.lower()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # --- Name ---
    name = ""
    name_match = re.search(r"(?:Name|NAME)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)", text)
    if name_match:
        name = name_match.group(1).strip()
    else:
        # First short line that looks like a name (2-3 capitalised words)
        for line in lines[:8]:
            words = line.split()
            if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w.isalpha()):
                # Exclude lines that are clearly headings like "Contact Information"
                if not any(kw in line.lower() for kw in ["contact", "information", "resume", "curriculum", "vitae"]):
                    name = line
                    break

    # --- Email ---
    emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    email = emails[0] if emails else ""

    # --- Phone ---
    phones = re.findall(
        r"[\+]?[\d][\d\s\-\.\(\)]{7,15}[\d]", text
    )
    phone = phones[0].strip() if phones else ""

    # --- Skills (keyword scan) ---
    skills = [s for s in _DETECTABLE_SKILLS if s in text_lower]

    # --- GitHub / LinkedIn / Website ---
    github_match = re.search(r"github\.com/([a-zA-Z0-9\-_]+)", text, re.I)
    linkedin_match = re.search(r"linkedin\.com/in/([a-zA-Z0-9\-_]+)", text, re.I)
    website_match = re.search(r"https?://(?!github|linkedin)([^\s,\)]+)", text, re.I)

    github = f"https://github.com/{github_match.group(1)}" if github_match else ""
    linkedin = linkedin_match.group(1) if linkedin_match else ""
    website = website_match.group(0) if website_match else ""

    # --- Experience years (rough estimate from date ranges) ---
    current_year = datetime.datetime.now().year
    year_matches = re.findall(r"\b(20\d{2})\b", text)
    if year_matches:
        years = [int(y) for y in year_matches]
        earliest = min(years)
        exp_years = max(0, current_year - earliest)
    else:
        exp_years = 0

    # --- Current / most recent role (first job title found) ---
    role_keywords = [
        "developer", "engineer", "programmer", "architect", "analyst",
        "scientist", "designer", "intern", "student",
    ]
    current_role = ""
    for line in lines:
        ll = line.lower()
        if any(kw in ll for kw in role_keywords) and len(line) < 60:
            current_role = line
            break

    # --- Summary (first substantial paragraph after "Summary" heading) ---
    summary = ""
    in_summary = False
    for line in lines:
        if re.match(r"^(summary|objective|profile|about me)$", line.lower()):
            in_summary = True
            continue
        if in_summary:
            if len(line) > 40:
                summary = line
                break
            # If we hit another heading, stop
            if line.isupper() or re.match(r"^(education|experience|skills|work)", line.lower()):
                break

    if not summary:
        for line in lines:
            if len(line) > 80:
                summary = line
                break

    # --- Education ---
    education = []
    edu_pattern = re.compile(
        r"(bachelor|master|b\.?sc|m\.?sc|phd|computer science|software engineering|"
        r"information technology|university|college|institute|hit|technion)", re.I
    )
    for line in lines:
        if edu_pattern.search(line) and len(line) < 120:
            education.append(line)
    education = education[:3]

    # --- Companies ---
    companies = []
    company_pattern = re.compile(r"@\s*([A-Z][a-zA-Z0-9 &\-\.]+)|(?:at|@)\s+([A-Z][a-zA-Z0-9 &]+)")
    for m in company_pattern.finditer(text):
        company = (m.group(1) or m.group(2) or "").strip()
        if company and len(company) < 40:
            companies.append(company)
    companies = list(dict.fromkeys(companies))[:5]  # deduplicate

    # --- Spoken / programming languages ---
    spoken = []
    spoken_pattern = re.compile(r"(English|Hebrew|German|French|Spanish|Arabic|Russian|Chinese)", re.I)
    for m in spoken_pattern.finditer(text):
        lang = m.group(1).capitalize()
        if lang not in spoken:
            spoken.append(lang)

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "github": github,
        "linkedin_handle": linkedin,
        "website": website or github,
        "current_role": current_role,
        "experience_years": exp_years,
        "skills": skills,
        "roles": [],
        "companies": companies,
        "education": education,
        "languages": spoken,
        "certifications": [],
        "summary": summary,
    }


if __name__ == "__main__":
    text = parse_all_resumes()
    profile = extract_resume_profile(text)
    import json
    print(json.dumps(profile, indent=2))
