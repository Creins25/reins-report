"""
Newsletter generator.

Reads the private journal entry, extracts the prose sections (Narrative,
My View) that the user wrote, and combines them with auto-generated data
sections into a clean, publishable Markdown file saved to newsletters/.

The newsletter is the public face of the journal — it strips private
sections (Post-Mortem details, Reading Log, stop levels) and adds a
subscriber footer and disclaimer.
"""

import re
from datetime import date
from pathlib import Path

_PROJECT_ROOT    = Path(__file__).resolve().parent.parent
NEWSLETTERS_DIR  = _PROJECT_ROOT / "newsletters"
TEMPLATE_PATH    = _PROJECT_ROOT / "templates" / "newsletter.md"
ENTRIES_DIR      = _PROJECT_ROOT / "entries"


# ── Section extractor ─────────────────────────────────────────────────────────

def _extract_section(entry_text: str, keyword: str) -> str:
    """
    Pull the body of a section whose ## header contains keyword.
    Returns everything between that header and the next --- divider.
    """
    pattern = rf'##[^#\n]*{re.escape(keyword)}[^\n]*\n\n(.*?)(?=\n---|\Z)'
    match   = re.search(pattern, entry_text, re.DOTALL | re.IGNORECASE)
    if not match:
        return f"*({keyword} section not yet written in the journal — add it there first.)*"
    # Strip placeholder italic text like *Not yet written…*
    body = match.group(1).strip()
    if body.startswith("*") and "fill" in body.lower():
        return f"*({keyword} section not yet written.)*"
    return body


def _extract_theme(entry_text: str) -> str:
    """Pull the theme line from the header."""
    match = re.search(r'\*\*Theme:\*\*\s*(.*)', entry_text)
    if not match:
        return "*Theme not yet set.*"
    return match.group(1).strip()


# ── Newsletter generator ──────────────────────────────────────────────────────

def generate_newsletter(week_str: str, journal_path: Path | None = None) -> str:
    """
    Build the newsletter Markdown string for a given week.

    journal_path: path to the journal entry. Defaults to entries/{week_str}.md.
    """
    if journal_path is None:
        journal_path = ENTRIES_DIR / f"{week_str}.md"

    if not journal_path.exists():
        raise FileNotFoundError(
            f"Journal entry not found: {journal_path}\n"
            f"Run 'python cli.py new' first to generate the entry."
        )

    entry_text = journal_path.read_text(encoding="utf-8")

    # ── Pull prose sections the user wrote ────────────────────────────────────
    theme     = _extract_theme(entry_text)
    narrative = _extract_section(entry_text, "Narrative")
    my_view   = _extract_section(entry_text, "My View")

    # ── Pull auto-generated data sections already in the entry ────────────────
    scoreboard     = _extract_section(entry_text, "Cross-Asset Scoreboard")
    earnings_radar = _extract_section(entry_text, "Earnings Radar")
    analyst_intel  = _extract_section(entry_text, "Analyst Intelligence")
    new_picks      = _extract_section(entry_text, "New This Week")
    open_picks     = _extract_section(entry_text, "Running Scorecard")
    track_record   = _extract_section(entry_text, "Track Record")

    # ── Parse date range from entry header ────────────────────────────────────
    header_match = re.search(r'# .+? · (.+)', entry_text)
    date_range   = header_match.group(1).strip() if header_match else ""
    year         = date.today().year

    # ── Load and fill newsletter template ─────────────────────────────────────
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Newsletter template not found: {TEMPLATE_PATH}")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    newsletter = (
        template
        .replace("{{WEEK_NUMBER}}",     week_str)
        .replace("{{DATE_RANGE}}",      date_range)
        .replace("{{THEME}}",           theme)
        .replace("{{SCOREBOARD}}",      scoreboard)
        .replace("{{EARNINGS_RADAR}}",  earnings_radar)
        .replace("{{ANALYST_INTEL}}",   analyst_intel)
        .replace("{{NARRATIVE}}",       narrative)
        .replace("{{MY_VIEW}}",         my_view)
        .replace("{{NEW_PICKS}}",       new_picks)
        .replace("{{OPEN_PICKS}}",      open_picks)
        .replace("{{TRACK_RECORD}}",    track_record)
        .replace("{{YEAR}}",            str(year))
    )

    return newsletter


def export_newsletter(week_str: str, journal_path: Path | None = None) -> Path:
    """
    Generate and save the newsletter to newsletters/{week_str}.md.
    Returns the output path.
    """
    NEWSLETTERS_DIR.mkdir(parents=True, exist_ok=True)
    content      = generate_newsletter(week_str, journal_path)
    output_path  = NEWSLETTERS_DIR / f"{week_str}.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path
