#!/usr/bin/env python3
"""
Job Application Bot - CLI
Usage:
  python main.py run          Full pipeline: search -> match -> apply
  python main.py search       Only search and store new jobs
  python main.py match        Score unmatched jobs against your resume
  python main.py apply        Submit applications for matched jobs
  python main.py status       Show dashboard stats
  python main.py jobs         List jobs (filter by status)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Force UTF-8 output on Windows (avoids cp1255 encoding errors)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load .env before importing anything that needs API keys
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

import database
import job_searcher
import job_matcher
import job_submitter
import resume_parser

app = typer.Typer(help="Automated job application bot — free, rule-based matching", add_completion=False)
console = Console(force_terminal=True, highlight=False)

# Per-user context — injected by the UI via JOB_BOT_USERNAME env var
_USERNAME = os.environ.get("JOB_BOT_USERNAME")
if _USERNAME:
    database.set_username(_USERNAME)


def load_config() -> dict:
    return database.load_config()


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@app.command()
def search(
    queries: list[str] = typer.Option(None, "--query", "-q", help="Job title / keywords (repeatable)"),
    remote_only: bool = typer.Option(False, "--remote", help="Only include remote jobs"),
    sources: str = typer.Option("", "--sources", help="Comma-separated sources"),
    location: str = typer.Option("", "--location", help="Location mode: israel | remote | worldwide"),
):
    """Search job boards and store new listings in the database."""
    database.init_db()
    cfg = load_config()

    # Determine queries
    if not queries:
        queries = cfg.get("job_titles", [])
    if not queries:
        console.print("[yellow]No job titles configured.[/yellow]")
        console.print("Use [bold]--query[/bold] or set [bold]job_titles[/bold] in config.json")
        raise typer.Exit(1)

    loc = location.lower().strip()
    israel_only = loc == "israel"
    if not remote_only:
        remote_only = (loc == "remote") or cfg.get("remote_only", False)

    enabled_sources = [s.strip() for s in sources.split(",") if s.strip()] if sources else None

    # Auto-expire old jobs before searching
    expiry_days = cfg.get("job_expiry_days", 30)
    expired = database.expire_old_jobs(days=expiry_days)
    if expired:
        console.print(f"  [dim]Removed {expired} expired jobs (older than {expiry_days} days)[/dim]")

    location_label = "Israel (on-site + remote)" if israel_only else ("Remote only" if remote_only else "Worldwide")
    console.print(Panel.fit(
        f"[bold cyan]Searching for:[/bold cyan] {', '.join(queries)}\n"
        f"[bold]Location:[/bold] {location_label}",
        title="[bold]Job Search[/bold]",
    ))

    jobs = job_searcher.search_all_sources(
        queries=queries,
        sources=enabled_sources,
        remote_only=remote_only,
        israel_only=israel_only,
    )
    console.print(f"  Found [bold]{len(jobs)}[/bold] raw listings, saving...")

    new_count = 0
    for job in jobs:
        result = database.upsert_job(
            source=job["source"],
            title=job["title"],
            url=job["url"],
            company=job.get("company", ""),
            location=job.get("location", ""),
            salary=job.get("salary", ""),
            description=job.get("description", ""),
            external_id=job.get("external_id", ""),
        )
        if result is not None:
            new_count += 1

    stats = database.get_stats()
    console.print(f"\n[green][OK][/green] Added [bold]{new_count}[/bold] new jobs (total in DB: {stats['total']})")


# ---------------------------------------------------------------------------
# match
# ---------------------------------------------------------------------------

@app.command()
def match(
    threshold: float = typer.Option(70.0, "--threshold", "-t", help="Minimum score to consider a match (0-100)"),
):
    """Score all unmatched jobs using rule-based matching (free, no API needed)."""
    database.init_db()

    cfg = load_config()
    threshold = cfg.get("match_threshold", threshold)

    # Load skill weights and blacklist from config if provided
    skill_weights = cfg.get("skill_weights", None)
    blacklisted_companies = cfg.get("blacklisted_companies", [])

    # Load resume from database
    console.print("[bold]Loading resume...[/bold]")
    resume_text = database.get_resume_content()
    if not resume_text:
        console.print("[red]No resume found. Upload your resume in Settings → Resume first.[/red]")
        raise typer.Exit(1)

    unmatched = database.get_unmatched_jobs()
    if not unmatched:
        total = database.get_stats()["total"]
        if total > 0:
            console.print("[yellow]All jobs already scored. Run [bold]search[/bold] to fetch new listings.[/yellow]")
        else:
            console.print("[yellow]No jobs in database. Run [bold]search[/bold] first.[/yellow]")
        return

    console.print(Panel.fit(
        f"[bold cyan]Jobs to score:[/bold cyan] {len(unmatched)}\n"
        f"[bold]Match threshold:[/bold] {threshold}%\n"
        f"[bold]Method:[/bold] Rule-based (free)",
        title="[bold]Job Matching[/bold]",
    ))

    result = job_matcher.match_all_unmatched(
        resume_text, threshold=threshold, verbose=True,
        skill_weights=skill_weights, blacklisted_companies=blacklisted_companies
    )

    console.print(
        f"\n[green][OK][/green] Scored {result['processed']} jobs - "
        f"[bold green]{result['matched']} matched[/bold green], "
        f"[dim]{result['skipped']} skipped[/dim]"
    )


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

@app.command()
def apply(
    auto: bool = typer.Option(False, "--auto", help="Auto-submit without confirmation prompts (careful!)"),
    max_apply: int = typer.Option(20, "--max", help="Maximum number of applications to submit"),
):
    """Submit applications to all matched jobs."""
    max_apply = max_apply if isinstance(max_apply, int) else 20
    database.init_db()

    cfg = load_config()

    # Load resume text + extract profile
    console.print("[bold]Extracting profile from resume...[/bold]")
    resume_text = database.get_resume_content()
    if not resume_text:
        console.print("[red]No resume found. Upload your resume in Settings → Resume first.[/red]")
        raise typer.Exit(1)
    try:
        profile = resume_parser.extract_resume_profile(resume_text)
        profile.update({k: v for k, v in cfg.get("profile", {}).items() if v})
    except Exception as e:
        console.print(f"[red]Error reading resume:[/red] {e}")
        raise typer.Exit(1)

    matched = database.get_jobs_by_status("matched")
    if not matched:
        console.print("[yellow]No matched jobs. Run [bold]match[/bold] first.[/yellow]")
        return

    resume_path = job_submitter._best_resume_path()

    console.print(Panel.fit(
        f"[bold cyan]Matched jobs ready:[/bold cyan] {len(matched)}\n"
        f"[bold]Resume:[/bold] {resume_path}\n"
        f"[bold]Auto-submit:[/bold] {auto}",
        title="[bold]Job Applications[/bold]",
    ))

    if not auto:
        console.print("[dim]You'll be prompted before each application. Type 'y' to apply, 'n' to skip, 'q' to quit.[/dim]\n")

    result = job_submitter.submit_all_matched(
        profile=profile,
        resume_path=resume_path,
        auto=auto,
        max_apply=max_apply,
    )

    console.print(
        f"\n[green][OK][/green] Applied: [bold green]{result['applied']}[/bold green] | "
        f"Queued for manual: [bold yellow]{result['queued']}[/bold yellow] | "
        f"Failed: [bold red]{result['failed']}[/bold red]"
    )
    if result["queued"] > 0:
        console.print(f"[dim]Manual queue saved to: {job_submitter.MANUAL_QUEUE_PATH}[/dim]")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status():
    """Show dashboard with application stats."""
    database.init_db()
    stats = database.get_stats()

    table = Table(title="Job Bot Dashboard", box=box.ROUNDED, show_header=True)
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")

    table.add_row("Total jobs found",     str(stats["total"]))
    table.add_row("Awaiting match score", str(stats["found"]),   style="dim")
    table.add_row("Matched (≥70%)",       str(stats["matched"]), style="bold green")
    table.add_row("Skipped (<70%)",       str(stats["skipped"]), style="dim")
    table.add_row("Applied",              str(stats["applied"]), style="bold cyan")
    table.add_row("Failed",               str(stats["failed"]),  style="red")
    table.add_row("Avg match score",      f"{stats['avg_score']}%")

    console.print(table)


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------

@app.command()
def jobs(
    status_filter: str = typer.Option("matched", "--status", "-s",
                                       help="Status filter: found|matched|skipped|applied|failed"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """List jobs filtered by status."""
    database.init_db()
    rows = database.get_jobs_by_status(status_filter)[:limit]

    if not rows:
        console.print(f"[yellow]No jobs with status '{status_filter}'[/yellow]")
        return

    table = Table(title=f"Jobs - {status_filter}", box=box.SIMPLE, show_lines=False)
    table.add_column("Score", width=6, justify="right")
    table.add_column("Title", min_width=25)
    table.add_column("Company", min_width=18)
    table.add_column("Location", min_width=12)
    table.add_column("Source", min_width=10)
    table.add_column("URL", max_width=50, no_wrap=True, style="dim")

    def safe(s: str, n: int) -> str:
        return (s or "")[:n].encode("ascii", errors="replace").decode("ascii")

    for row in rows:
        score = f"{row['match_score']:.0f}" if row["match_score"] is not None else "-"
        table.add_row(
            score,
            safe(row["title"], 40),
            safe(row["company"] or "", 20),
            safe(row["location"] or "", 15),
            row["source"],
            row["url"] or "",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

@app.command()
def setup():
    """Parse resumes and create config.json interactively."""
    database.init_db()

    console.print(Panel.fit("[bold cyan]Job Bot Setup[/bold cyan]"))

    # Parse resumes
    console.print("\n[bold]Step 1: Parsing your resumes[/bold]")
    try:
        text = resume_parser.parse_all_resumes(verbose=True)
        console.print(f"[green][OK][/green] Resume text ready ({len(text)} chars)")
    except Exception as e:
        console.print(f"[red][FAIL] Resume parsing failed:[/red] {e}")
        return

    # Extract profile (rule-based, free)
    console.print("\n[bold]Step 2: Extracting your profile (rule-based)[/bold]")
    profile = resume_parser.extract_resume_profile(text)
    console.print(f"  Name    : {profile.get('name', '?')}")
    console.print(f"  Role    : {profile.get('current_role', '?')}")
    console.print(f"  Exp     : ~{profile.get('experience_years', '?')} yrs")
    console.print(f"  Skills  : {', '.join(profile.get('skills', [])[:10])}")

    # Job titles
    console.print("\n[bold]Step 3: Job search configuration[/bold]")
    default_titles = [profile.get("current_role", "Software Engineer")]
    titles_input = typer.prompt(
        "Job titles to search for (comma-separated)",
        default=", ".join(default_titles),
    )
    titles = [t.strip() for t in titles_input.split(",") if t.strip()]

    remote = typer.confirm("Search remote jobs only?", default=True)
    threshold = typer.prompt("Minimum match score (0-100)", default="70")

    # Contact details
    console.print("\n[bold]Step 4: Your contact details[/bold]")
    phone = typer.prompt("Phone number (for applications)", default="")
    city = typer.prompt("City / Location", default="")
    linkedin = typer.prompt("LinkedIn handle (e.g. johndoe)", default="")
    website = typer.prompt("Portfolio/website URL", default="")

    cfg = {
        "job_titles": titles,
        "remote_only": remote,
        "match_threshold": float(threshold),
        "profile": {
            "name": profile.get("name", ""),
            "email": profile.get("email", ""),
            "phone": phone,
            "city": city,
            "linkedin_handle": linkedin,
            "website": website,
            "summary": profile.get("summary", ""),
        },
    }

    database.save_config(cfg)
    console.print(f"\n[green][OK][/green] Config saved to database")
    console.print("\nNext step: Run [bold]python main.py run[/bold] to start the full pipeline")


# ---------------------------------------------------------------------------
# rematch
# ---------------------------------------------------------------------------

@app.command()
def rematch(
    threshold: float = typer.Option(None, "--threshold", "-t"),
    ai: bool = typer.Option(False, "--ai", help="Use OpenRouter AI for smarter scoring"),
):
    """Reset all job scores and re-run matching with current settings."""
    database.init_db()
    cfg = load_config()
    if threshold is None:
        threshold = cfg.get("match_threshold", 70.0)

    count = database.reset_scores_for_rematch()
    console.print(f"[yellow]Reset {count} jobs for re-matching...[/yellow]")

    skill_weights = cfg.get("skill_weights", None)
    blacklisted_companies = cfg.get("blacklisted_companies", [])

    resume_text = database.get_resume_content()
    if not resume_text:
        resume_text = resume_parser.parse_all_resumes(verbose=False)

    if ai:
        console.print("[cyan]Using AI scoring (OpenRouter Llama 3)...[/cyan]")

    result = job_matcher.match_all_unmatched(
        resume_text, threshold=threshold, verbose=True,
        skill_weights=skill_weights, blacklisted_companies=blacklisted_companies,
        use_ai=ai,
    )
    console.print(
        f"\n[green][OK][/green] Re-scored {result['processed']} jobs — "
        f"[bold green]{result['matched']} matched[/bold green], "
        f"[dim]{result['skipped']} skipped[/dim]"
    )


# ---------------------------------------------------------------------------
# run (full pipeline)
# ---------------------------------------------------------------------------

@app.command()
def run(
    threshold: float = typer.Option(None, "--threshold", "-t"),
    auto: bool = typer.Option(False, "--auto"),
    max_apply: int = typer.Option(20, "--max"),
    remote_only: bool = typer.Option(None, "--remote"),
):
    """Run the full pipeline: search -> match -> apply."""
    max_apply = max_apply if isinstance(max_apply, int) else 20
    threshold = threshold if isinstance(threshold, (int, float)) else None
    database.init_db()
    cfg = load_config()

    if threshold is None:
        threshold = cfg.get("match_threshold", 70.0)

    loc_mode = cfg.get("location_mode", "")
    if remote_only is None:
        remote_only = (loc_mode == "Remote only") or cfg.get("remote_only", False)
    _location_arg = "israel" if loc_mode == "Israel (on-site + remote)" else ("remote" if remote_only else "")

    console.print(Panel.fit(
        "[bold cyan]Job Bot -- Full Pipeline[/bold cyan]\n"
        "search -> match (rule-based, free) -> apply",
        border_style="cyan",
    ))

    # 1. Search
    console.rule("[bold]Phase 1: Search[/bold]")
    queries = cfg.get("job_titles", [])
    if not queries:
        console.print("[red]No job_titles in config.json. Run [bold]python main.py setup[/bold] first.[/red]")
        raise typer.Exit(1)

    search(queries=queries, remote_only=remote_only, sources="", location=_location_arg)  # type: ignore

    # 2. Match
    console.rule("[bold]Phase 2: Match[/bold]")
    match(threshold=threshold)  # type: ignore

    # 3. Apply
    console.rule("[bold]Phase 3: Apply[/bold]")
    apply(auto=auto, max_apply=max_apply)  # type: ignore

    console.rule("[bold]Done[/bold]")
    status()


@app.command()
def menu():
    """Interactive menu — easiest way to use the bot."""
    database.init_db()
    stats = database.get_stats()

    console.print(Panel.fit(
        "[bold cyan]Job Application Bot[/bold cyan]\n"
        f"[dim]Jobs in DB: {stats['total']} | Matched: {stats['matched']} | Applied: {stats['applied']}[/dim]",
        border_style="cyan",
    ))

    options = [
        ("1", "Run full pipeline (search + match + apply)", "run"),
        ("2", "Search new jobs only",                       "search"),
        ("3", "Score / match jobs against your profile",   "match"),
        ("4", "Apply to matched jobs",                     "apply"),
        ("5", "View matched jobs",                         "jobs"),
        ("6", "Dashboard stats",                           "status"),
        ("7", "First-time setup",                          "setup"),
        ("q", "Quit",                                      None),
    ]

    for key, label, _ in options:
        console.print(f"  [bold cyan]{key}[/bold cyan]  {label}")

    choice = input("\nChoose an option: ").strip().lower()

    mapping = {key: cmd for key, _, cmd in options}
    cmd = mapping.get(choice)

    if cmd is None or choice == "q":
        return
    elif cmd == "run":
        run()  # type: ignore
    elif cmd == "search":
        search()  # type: ignore
    elif cmd == "match":
        match()  # type: ignore
    elif cmd == "apply":
        apply()  # type: ignore
    elif cmd == "jobs":
        jobs()  # type: ignore
    elif cmd == "status":
        status()
    elif cmd == "setup":
        setup()


if __name__ == "__main__":
    # No arguments → show the friendly menu instead of help text
    import sys
    if len(sys.argv) == 1:
        sys.argv.append("menu")
    app()
