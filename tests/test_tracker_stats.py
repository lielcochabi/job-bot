"""
Tests for tracker.get_tracker_stats()
"""
from job_bot.tracker import get_tracker_stats


def _make_jobs(*statuses: str) -> list[dict]:
    """Helper: build a list of minimal job dicts with the given statuses."""
    return [{"Status": s} for s in statuses]


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

def test_empty_returns_zeros():
    result = get_tracker_stats([])
    assert result["total"] == 0
    assert result["by_status"] == {}
    assert result["response_rate"] == 0.0
    assert result["success_rate"] == 0.0


# ---------------------------------------------------------------------------
# total
# ---------------------------------------------------------------------------

def test_total_count():
    jobs = _make_jobs("Applied", "Applied", "Denied")
    assert get_tracker_stats(jobs)["total"] == 3


# ---------------------------------------------------------------------------
# by_status
# ---------------------------------------------------------------------------

def test_by_status_counts():
    jobs = _make_jobs("Applied", "Applied", "Interview", "Denied")
    stats = get_tracker_stats(jobs)
    assert stats["by_status"]["Applied"] == 2
    assert stats["by_status"]["Interview"] == 1
    assert stats["by_status"]["Denied"] == 1


def test_by_status_missing_status_treated_as_unknown():
    jobs = [{"Status": None}, {"Status": ""}]
    stats = get_tracker_stats(jobs)
    assert stats["by_status"].get("Unknown", 0) == 2


# ---------------------------------------------------------------------------
# response_rate
# ---------------------------------------------------------------------------

def test_response_rate_zero_when_no_responses():
    jobs = _make_jobs("Applied", "Applied", "Manual - Pending")
    assert get_tracker_stats(jobs)["response_rate"] == 0.0


def test_response_rate_partial():
    # 2 out of 4 got responses
    jobs = _make_jobs("Applied", "Applied", "Denied", "Interview")
    assert get_tracker_stats(jobs)["response_rate"] == 50.0


# ---------------------------------------------------------------------------
# success_rate
# ---------------------------------------------------------------------------

def test_success_rate_zero_when_only_denied():
    jobs = _make_jobs("Denied", "Denied", "Applied")
    assert get_tracker_stats(jobs)["success_rate"] == 0.0


def test_success_rate_counts_interview_and_accepted():
    # Interview + Accepted = 2 out of 4
    jobs = _make_jobs("Applied", "Denied", "Interview", "Accepted")
    assert get_tracker_stats(jobs)["success_rate"] == 50.0


# ---------------------------------------------------------------------------
# Rounding
# ---------------------------------------------------------------------------

def test_rates_are_rounded_to_one_decimal():
    # 1 out of 3 = 33.333...%
    jobs = _make_jobs("Applied", "Applied", "Interview")
    stats = get_tracker_stats(jobs)
    assert stats["response_rate"] == 33.3
    assert stats["success_rate"] == 33.3
