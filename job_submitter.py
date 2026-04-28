"""
Submit job applications via three methods:
  1. LinkedIn Easy Apply (Playwright browser automation)
  2. Email (smtplib — when a contact email is found in the posting)
  3. Manual queue (save to CSV for human review)

The submitter never sends anything without the user's confirmation
unless --auto flag is passed explicitly.
"""
from __future__ import annotations

import csv
import os
import re
import smtplib
import time
import urllib.parse
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import database


# ---------------------------------------------------------------------------
# Email notification (sends to NOTIFY_EMAIL after every application)
# ---------------------------------------------------------------------------

def send_notification(job: dict, method: str) -> None:
    """Send a notification email to NOTIFY_EMAIL after a job is processed."""
    from secrets_manager import get_secret
    notify_email = get_secret("NOTIFY_EMAIL")
    app_password = get_secret("GMAIL_APP_PASSWORD")

    if not notify_email or not app_password:
        return  # silently skip if not configured

    is_manual = method in ("Added to manual queue", "Manual queue")
    score = job.get("match_score", 0)
    url = job.get("url", "")
    title = job.get("title", "?")
    company = job.get("company", "Unknown")

    if is_manual:
        subject = f"[Job Bot] ACTION REQUIRED: Apply manually — {title} @ {company}"
        action_block = f"""\
⚠️  ACTION REQUIRED — The bot could NOT apply automatically.
You need to apply to this job yourself.

👉 Apply here: {url}
"""
    else:
        subject = f"[Job Bot] ✅ Auto-applied: {title} @ {company}"
        action_block = f"""\
✅ The bot submitted your application automatically.
No action needed from you.

Method: {method}
"""

    body = f"""\
{'='*50}
{'⚠️  MANUAL ACTION NEEDED' if is_manual else '✅  AUTO-APPLIED — NO ACTION NEEDED'}
{'='*50}

{action_block}
Position : {title}
Company  : {company}
Location : {job.get('location', 'Unknown')}
Match    : {score:.0f}%
URL      : {url}

---
View all jobs: python main.py status
"""

    try:
        msg = MIMEMultipart()
        msg["From"] = notify_email
        msg["To"] = notify_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(notify_email, app_password)
            server.sendmail(notify_email, notify_email, msg.as_string())

        print(f"    [Notify] Email sent to {notify_email}")
    except Exception as e:
        print(f"    [Notify] Could not send notification: {e}")


def send_whatsapp(job: dict, method: str) -> None:
    """Send a WhatsApp notification via CallMeBot (free, no account needed)."""
    from secrets_manager import get_secret
    phone   = get_secret("WHATSAPP_PHONE")    # e.g. +972523315195
    api_key = get_secret("CALLMEBOT_API_KEY")

    if not phone or not api_key:
        return

    is_manual = method in ("Added to manual queue", "Manual queue")
    title   = job.get("title", "?")
    company = job.get("company", "Unknown")
    score   = job.get("match_score", 0)
    url     = job.get("url", "")

    if is_manual:
        text = (
            f"⚠️ ACTION REQUIRED\n"
            f"{title} @ {company}\n"
            f"Score: {score:.0f}% | Apply yourself:\n{url}"
        )
    else:
        text = (
            f"✅ AUTO-APPLIED\n"
            f"{title} @ {company}\n"
            f"Score: {score:.0f}% | Method: {method}\n{url}"
        )

    try:
        import httpx
        encoded = urllib.parse.quote(text)
        httpx.get(
            f"https://api.callmebot.com/whatsapp.php"
            f"?phone={phone}&text={encoded}&apikey={api_key}",
            timeout=10,
        )
        print(f"    [WhatsApp] Notification sent")
    except Exception as e:
        print(f"    [WhatsApp] Could not send: {e}")


MANUAL_QUEUE_PATH = Path(__file__).parent / "manual_apply.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_email_in_text(text: str) -> Optional[str]:
    matches = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    # Skip generic noreply / privacy addresses
    blocked = {"noreply", "no-reply", "donotreply", "privacy", "legal", "info@linkedin"}
    for m in matches:
        if not any(b in m.lower() for b in blocked):
            return m
    return None


def _best_resume_path() -> Optional[Path]:
    """Return the most recently modified resume file found on Desktop/Downloads/Documents."""
    found = []
    search_dirs = [
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / "Documents",
        Path.home() / "OneDrive" / "Desktop",
        Path.home() / "OneDrive" / "Documents",
    ]
    # Also check for uploaded resume in the bot directory
    bot_dir = Path(__file__).parent
    for p in bot_dir.glob("uploaded_resume*"):
        if p.suffix.lower() in (".pdf", ".docx"):
            found.append(p)

    for d in search_dirs:
        if not d.exists():
            continue
        for p in d.glob("*"):
            if p.suffix.lower() in (".pdf", ".docx") and (
                "resume" in p.name.lower() or "cv" in p.name.lower()
            ):
                found.append(p)
    if not found:
        return None
    return max(found, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------------------
# Method 1: LinkedIn Easy Apply (Playwright)
# ---------------------------------------------------------------------------

def apply_linkedin(
    job: dict,
    profile: dict,
    resume_path: Optional[Path] = None,
    auto: bool = False,
) -> bool:
    """
    Automate LinkedIn Easy Apply.
    Returns True on success.

    NOTE: LinkedIn frequently changes its UI; this may require updates.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("    [LinkedIn] playwright not installed. Run: pip install playwright && playwright install chromium")
        return False

    email = os.environ.get("LINKEDIN_EMAIL", "")
    password = os.environ.get("LINKEDIN_PASSWORD", "")
    if not email or not password:
        print("    [LinkedIn] Missing LINKEDIN_EMAIL / LINKEDIN_PASSWORD in .env")
        return False

    resume = resume_path or _best_resume_path()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)  # visible so user can intervene
        ctx = browser.new_context()
        page = ctx.new_page()

        try:
            # --- Login ---
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            page.fill("#username", email)
            page.fill("#password", password)
            page.click('[type="submit"]')
            page.wait_for_timeout(3000)

            # Handle 2FA / CAPTCHA — wait for user
            if "checkpoint" in page.url or "challenge" in page.url:
                print("    [LinkedIn] 2FA detected. Please complete in browser window (30s)...")
                page.wait_for_url("**/feed**", timeout=60000)

            # --- Navigate to job ---
            page.goto(job["url"], wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # Look for Easy Apply button
            easy_apply_btn = page.query_selector("button.jobs-apply-button")
            if not easy_apply_btn:
                easy_apply_btn = page.query_selector("button:has-text('Easy Apply')")
            if not easy_apply_btn:
                print(f"    [LinkedIn] No Easy Apply button found for: {job['url']}")
                return False

            easy_apply_btn.click()
            page.wait_for_timeout(2000)

            # --- Fill application form (multi-step) ---
            max_steps = 10
            for step in range(max_steps):
                # Upload resume if file input visible
                if resume:
                    file_input = page.query_selector("input[type='file']")
                    if file_input:
                        file_input.set_input_files(str(resume))
                        page.wait_for_timeout(1500)

                # Fill phone if empty
                phone_input = page.query_selector("input[id*='phone']")
                if phone_input and not phone_input.input_value():
                    phone = profile.get("phone", os.environ.get("PHONE_NUMBER", ""))
                    if phone:
                        phone_input.fill(phone)

                # Fill text inputs that are empty (name, email, etc.)
                text_inputs = page.query_selector_all("input[type='text']:visible, input[type='email']:visible")
                for inp in text_inputs:
                    if inp.input_value():
                        continue
                    label_el = page.query_selector(f"label[for='{inp.get_attribute('id')}']")
                    label = label_el.inner_text().lower() if label_el else ""
                    if "email" in label:
                        inp.fill(profile.get("email", email))
                    elif "name" in label:
                        inp.fill(profile.get("name", ""))
                    elif "city" in label or "location" in label:
                        inp.fill(profile.get("city", ""))
                    elif "linkedin" in label:
                        inp.fill(f"https://linkedin.com/in/{profile.get('linkedin_handle', '')}")
                    elif "website" in label or "portfolio" in label:
                        inp.fill(profile.get("website", ""))

                # Check for "Next" or "Submit" button
                next_btn = page.query_selector("button[aria-label*='Continue']")
                submit_btn = page.query_selector("button[aria-label*='Submit']")
                review_btn = page.query_selector("button[aria-label*='Review']")

                if submit_btn:
                    if not auto:
                        print("    [LinkedIn] Ready to submit. Check the browser and press Enter to continue...")
                        input()
                    submit_btn.click()
                    page.wait_for_timeout(3000)
                    print(f"    [LinkedIn] ✓ Applied to: {job['title']} @ {job['company']}")
                    return True

                elif review_btn:
                    review_btn.click()
                    page.wait_for_timeout(2000)

                elif next_btn:
                    next_btn.click()
                    page.wait_for_timeout(2000)
                else:
                    # Unknown form state — pause for human
                    print("    [LinkedIn] Unknown form state. Please complete in browser (60s)...")
                    try:
                        page.wait_for_url("**/apply/**", timeout=60000)
                    except PWTimeout:
                        pass
                    break

            print("    [LinkedIn] Could not complete application automatically.")
            return False

        except PWTimeout as e:
            print(f"    [LinkedIn] Timeout: {e}")
            return False
        except Exception as e:
            print(f"    [LinkedIn] Error: {e}")
            return False
        finally:
            page.wait_for_timeout(2000)
            ctx.close()
            browser.close()


# ---------------------------------------------------------------------------
# Method 2: Email Application
# ---------------------------------------------------------------------------

def apply_email(
    job: dict,
    profile: dict,
    resume_path: Optional[Path] = None,
    auto: bool = False,
) -> bool:
    """Send email application if a contact email is found in the job description."""
    from_email = os.environ.get("EMAIL_ADDRESS", "")
    password = os.environ.get("EMAIL_PASSWORD", "")
    smtp_server = os.environ.get("EMAIL_SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))

    if not from_email or not password:
        return False

    to_email = _find_email_in_text(job.get("description", ""))
    if not to_email:
        return False

    resume = resume_path or _best_resume_path()
    name = profile.get("name", "Candidate")
    role = job.get("title", "the position")
    company = job.get("company", "your company")

    subject = f"Application for {role} — {name}"
    body = f"""\
Dear Hiring Team,

I am writing to express my strong interest in the {role} position at {company}.

{profile.get("summary", "")}

I have attached my resume for your review and would welcome the opportunity to discuss \
how my background aligns with your team's needs.

Thank you for your time and consideration.

Best regards,
{name}
{profile.get("email", from_email)}
"""

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if resume and resume.exists():
        with open(resume, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{resume.name}"')
        msg.attach(part)

    if not auto:
        print(f"    [Email] Ready to send to {to_email} for {role} @ {company}")
        print(f"    [Email] Preview:\n{body[:300]}...")
        confirm = input("    Send? [y/N]: ").strip().lower()
        if confirm != "y":
            print("    [Email] Skipped.")
            return False

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(from_email, password)
            server.sendmail(from_email, to_email, msg.as_string())
        print(f"    [Email] ✓ Sent to {to_email}")
        return True
    except Exception as e:
        print(f"    [Email] Failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Method 3: Manual Queue (save to CSV)
# ---------------------------------------------------------------------------

def queue_manual(job: dict) -> None:
    """Add job to manual review CSV for human application."""
    fields = ["id", "title", "company", "location", "url", "match_score", "salary"]
    write_header = not MANUAL_QUEUE_PATH.exists()

    with open(MANUAL_QUEUE_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(job)

    print(f"    [Manual] Added to {MANUAL_QUEUE_PATH.name}: {job['title']} @ {job.get('company', '?')}")


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def submit_job(
    job: dict,
    profile: dict,
    resume_path: Optional[Path] = None,
    auto: bool = False,
) -> str:
    """
    Try to submit an application for a job.
    Returns: 'applied', 'queued', 'failed'
    """
    url = job.get("url", "")

    import tracker as _tracker

    # Method 1: LinkedIn Easy Apply
    if "linkedin.com" in url:
        success = apply_linkedin(job, profile, resume_path, auto)
        if success:
            database.set_applied(job["id"], "LinkedIn Easy Apply")
            send_notification(job, "LinkedIn Easy Apply")
            send_whatsapp(job, "LinkedIn Easy Apply")
            xlsx = _tracker.add_job(job, "LinkedIn Easy Apply")
            print(f"    [Tracker] Logged to {xlsx.name}")
            return "applied"

    # Method 2: Email (if contact email found)
    if os.environ.get("EMAIL_ADDRESS") and os.environ.get("EMAIL_PASSWORD"):
        success = apply_email(job, profile, resume_path, auto)
        if success:
            database.set_applied(job["id"], "Email")
            send_notification(job, "Email")
            send_whatsapp(job, "Email")
            xlsx = _tracker.add_job(job, "Email")
            print(f"    [Tracker] Logged to {xlsx.name}")
            return "applied"

    # Method 3: Manual queue
    queue_manual(job)
    database.set_applied(job["id"], "Manual queue")
    send_notification(job, "Added to manual queue")
    send_whatsapp(job, "Added to manual queue")
    xlsx = _tracker.add_job(job, "Manual queue")
    print(f"    [Tracker] Logged to {xlsx.name}")
    return "queued"


def submit_all_matched(
    profile: dict,
    resume_path: Optional[Path] = None,
    auto: bool = False,
    max_apply: int = 50,
) -> dict:
    """
    Submit applications for all jobs with status='matched'.
    Returns stats dict.
    """
    jobs = database.get_jobs_by_status("matched")
    if not jobs:
        return {"applied": 0, "queued": 0, "failed": 0}

    applied = queued = failed = 0
    count = 0

    for job in jobs:
        if count >= max_apply:
            print(f"\n  Reached max_apply limit ({max_apply}). Stopping.")
            break

        total = min(len(jobs), max_apply)
        score = job.get('match_score') or 0
        title  = (job.get('title') or '?').encode('ascii','replace').decode()
        company = (job.get('company') or '?').encode('ascii','replace').decode()
        location = (job.get('location') or 'Unknown').encode('ascii','replace').decode()
        salary = (job.get('salary') or '').encode('ascii','replace').decode()
        url = job.get('url') or ''

        # Parse matched skills from stored reason
        matched_skills = []
        try:
            import json as _json
            reason_data = _json.loads(job.get('match_reason') or '{}')
            matched_skills = reason_data.get('matched', [])
        except Exception:
            pass

        print(f"\n{'='*60}")
        print(f"  Job {count+1} of {total}")
        print(f"  Title    : {title}")
        print(f"  Company  : {company}")
        print(f"  Location : {location}")
        if salary:
            print(f"  Salary   : {salary}")
        print(f"  Score    : {score:.0f}%")
        if matched_skills:
            print(f"  Matched  : {', '.join(matched_skills[:8])}")
        print(f"  URL      : {url}")
        print(f"{'='*60}")

        if not auto:
            print("  Options: [y] Apply  [n] Skip  [o] Open in browser  [q] Quit")
            while True:
                action = input("  > ").strip().lower()
                if action == "o":
                    import webbrowser
                    webbrowser.open(url)
                    action = input("  Apply after reviewing? [y/n]: ").strip().lower()
                if action in ("y", "n", "q"):
                    break
                print("  Please enter y, n, o, or q")

            if action == "q":
                print("\n  Stopped.")
                break
            if action != "y":
                print("  Skipped.")
                continue

        result = submit_job(job, profile, resume_path, auto)
        if result == "applied":
            applied += 1
            print(f"  [OK] Applied!")
        elif result == "queued":
            queued += 1
            print(f"  [Queued] Added to manual_apply.csv — apply at the URL above.")
        else:
            failed += 1
        count += 1
        time.sleep(2)

    return {"applied": applied, "queued": queued, "failed": failed}
