"""
Generates a new weekly journal entry from the template.

Run order each Sunday:
  1. Refresh open picks prices
  2. Fetch macro market data (yfinance + FRED)
  3. Pull research data (earnings calendar, analyst moves, price targets)
  4. Build picks scorecard sections
  5. Fill template and write entry file
"""

from datetime import date, timedelta
from pathlib import Path

from scripts.fetch_data import (
    fetch_yfinance_levels,
    fetch_fred_series,
    format_scoreboard_table,
)
from scripts.config import YFINANCE_TICKERS, FRED_SERIES

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = _PROJECT_ROOT / "templates" / "weekly.md"
ENTRIES_DIR   = _PROJECT_ROOT / "entries"


def _target_week(today: date) -> tuple[date, date, int, int]:
    """
    Return (monday, sunday, iso_year, iso_week) for the most recently
    completed ISO week (Mon–Sun). If today is Sunday, it's the current week.
    """
    if today.weekday() == 6:
        sunday = today
    else:
        sunday = today - timedelta(days=(today.weekday() + 1) % 7)

    monday   = sunday - timedelta(days=6)
    iso_year, iso_week, _ = sunday.isocalendar()
    return monday, sunday, iso_year, iso_week


def generate_entry(force: bool = False) -> Path:
    """
    Create a new weekly journal entry. Returns the path to the created file.
    Raises FileExistsError if the entry already exists and force=False.
    """
    today  = date.today()
    monday, sunday, iso_year, iso_week = _target_week(today)
    week_str   = f"{iso_year}-W{iso_week:02d}"
    filename   = f"{week_str}.md"
    entry_path = ENTRIES_DIR / filename

    if entry_path.exists() and not force:
        raise FileExistsError(
            f"{entry_path} already exists. Use --force to overwrite."
        )

    friday = sunday - timedelta(days=1)

    # ── 1. Refresh live prices on all open picks ──────────────────────────────
    print("\n[1/4] Refreshing open picks prices …")
    try:
        from scripts.picks import refresh_prices
        refresh_prices()
    except Exception as e:
        print(f"  [warn] Could not refresh picks prices: {e}")

    # ── 2. Fetch macro market data ────────────────────────────────────────────
    print(f"\n[2/4] Fetching macro data for week ending {friday.isoformat()} …")
    yf_data    = fetch_yfinance_levels(YFINANCE_TICKERS, friday)
    fred_data  = fetch_fred_series(FRED_SERIES, friday)
    scoreboard = format_scoreboard_table(yf_data, fred_data)

    # ── 3. Pull research data ─────────────────────────────────────────────────
    print("\n[3/4] Pulling earnings calendar and analyst data …")
    try:
        from scripts.research import (
            get_all_tracked_tickers,
            format_earnings_radar,
            format_analyst_moves_table,
            format_price_targets_table,
        )
        tracked         = get_all_tracked_tickers()
        earnings_radar  = format_earnings_radar(tracked, weeks_ahead=3)
        analyst_moves   = format_analyst_moves_table(tracked)
        price_targets   = format_price_targets_table(tracked)
    except Exception as e:
        print(f"  [warn] Research data failed: {e}")
        earnings_radar = analyst_moves = price_targets = \
            "*Research data unavailable — run `python cli.py research` to debug.*"

    # ── 4. Build picks scorecard sections ─────────────────────────────────────
    print("\n[4/4] Building picks scorecard …")
    try:
        from scripts.scorecard import (
            format_new_picks_table,
            format_open_picks_table,
            format_closed_picks_table,
            format_track_record_summary,
        )
        new_picks_table    = format_new_picks_table(week_str)
        open_picks_table   = format_open_picks_table()
        closed_picks_table = format_closed_picks_table(since_date=monday)
        track_record       = format_track_record_summary()
    except Exception as e:
        print(f"  [warn] Scorecard generation failed: {e}")
        placeholder        = "*Scorecard unavailable — check picks data.*"
        new_picks_table    = placeholder
        open_picks_table   = placeholder
        closed_picks_table = placeholder
        track_record       = placeholder

    # ── 5. Fill template ──────────────────────────────────────────────────────
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    date_range    = f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"

    filled = (
        template_text
        .replace("{{WEEK_NUMBER}}",          week_str)
        .replace("{{DATE_RANGE}}",           date_range)
        .replace("{{SCOREBOARD_TABLE}}",     scoreboard)
        .replace("{{EARNINGS_RADAR}}",       earnings_radar)
        .replace("{{ANALYST_MOVES}}",        analyst_moves)
        .replace("{{PRICE_TARGETS}}",        price_targets)
        .replace("{{NEW_PICKS_TABLE}}",      new_picks_table)
        .replace("{{OPEN_PICKS_TABLE}}",     open_picks_table)
        .replace("{{CLOSED_PICKS_TABLE}}",   closed_picks_table)
        .replace("{{TRACK_RECORD_SUMMARY}}", track_record)
    )

    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
    entry_path.write_text(filled, encoding="utf-8")
    return entry_path
