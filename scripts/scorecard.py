"""
Markdown formatters for the stock picks scorecard sections.

These functions are called by new_week.py when generating an entry.
They return ready-to-paste Markdown strings.
"""

from datetime import date

import pandas as pd

from scripts.picks import (
    get_open_picks,
    get_closed_picks,
    get_picks_closed_since,
    compute_track_record,
)


def _pnl_str(val) -> str:
    """Format a P&L value as '+12.3%' or '-8.4%', or 'N/A'."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    return f"{val:+.1f}%"


def _price_str(val, decimals: int = 2) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    return f"${val:.{decimals}f}"


def format_new_picks_table(week_str: str) -> str:
    """
    Section 7: picks added this week (week_added == week_str).
    Returns a Markdown table + per-pick thesis block.
    """
    from scripts.picks import _load_ledger
    df = _load_ledger()
    new_picks = df[df["week_added"] == week_str]

    if new_picks.empty:
        return "*No new picks added this week.*"

    lines = [
        "| Ticker | Direction | Entry | Target | Stop | Conviction | Horizon | Sector |",
        "|--------|-----------|------:|-------:|-----:|-----------:|---------|--------|",
    ]
    for _, row in new_picks.iterrows():
        stars = f"{int(row['conviction'])}/5"
        lines.append(
            f"| **{row['ticker']}** | {row['direction'].title()} | "
            f"{_price_str(row['entry_price'])} | {_price_str(row['target_price'])} | "
            f"{_price_str(row['stop_price'])} | {stars} | "
            f"{row['time_horizon'].title()} | {row['sector']} |"
        )

    # Per-pick thesis blocks below the table
    lines.append("")
    for _, row in new_picks.iterrows():
        lines.append(
            f"**{row['ticker']} ({row['direction'].title()})** "
            f"— *{row['sector']} · {row['time_horizon'].title()} · Conviction {int(row['conviction'])}/5*\n"
        )
        lines.append(f"{row['thesis']}\n")
        lines.append(f"**Catalyst:** {row['catalyst']}\n")

    return "\n".join(lines)


def format_open_picks_table() -> str:
    """
    Section 8: all currently open picks with live unrealized P&L.
    Sorted by live_pnl_pct descending (best performer first).
    """
    open_picks = get_open_picks()

    if open_picks.empty:
        return "*No open picks.*"

    lines = [
        "| Ticker | Direction | Entry | Current | P&L % | Days Held | Conviction | Sector |",
        "|--------|-----------|------:|--------:|------:|----------:|-----------:|--------|",
    ]
    for _, row in open_picks.iterrows():
        days = int(row["days_held"]) if pd.notna(row.get("days_held")) else "–"
        lines.append(
            f"| **{row['ticker']}** | {row['direction'].title()} | "
            f"{_price_str(row['entry_price'])} | {_price_str(row['current_price'])} | "
            f"{_pnl_str(row['live_pnl_pct'])} | {days} | "
            f"{int(row['conviction'])}/5 | {row['sector']} |"
        )

    return "\n".join(lines)


def format_closed_picks_table(since_date: date) -> str:
    """
    Section 9: picks closed since since_date (typically Monday of current week).
    """
    closed = get_picks_closed_since(since_date)

    if closed.empty:
        return "*No picks closed since last entry.*"

    lines = [
        "| Ticker | Direction | Entry | Close | P&L % | Days Held | Reason |",
        "|--------|-----------|------:|------:|------:|----------:|--------|",
    ]
    for _, row in closed.iterrows():
        days = int(row["days_held"]) if pd.notna(row.get("days_held")) else "–"
        lines.append(
            f"| **{row['ticker']}** | {row['direction'].title()} | "
            f"{_price_str(row['entry_price'])} | {_price_str(row['close_price'])} | "
            f"{_pnl_str(row['realized_pnl_pct'])} | {days} | "
            f"{row['close_reason'].replace('_', ' ').title()} |"
        )

    return "\n".join(lines)


def format_track_record_summary() -> str:
    """
    Section 10: headline track record stats as a Markdown block.
    """
    stats = compute_track_record()

    if stats["closed_picks"] == 0:
        return (
            f"**Total picks:** {stats['total_picks']} "
            f"({stats['open_picks']} open, 0 closed)\n\n"
            "*Track record builds as picks are closed.*"
        )

    win_rate = f"{stats['win_rate'] * 100:.0f}%" if stats["win_rate"] is not None else "N/A"
    avg_w    = f"{stats['avg_winner']:+.1f}%" if stats["avg_winner"] is not None else "N/A"
    avg_l    = f"{stats['avg_loser']:+.1f}%"  if stats["avg_loser"]  is not None else "N/A"
    hold_d   = f"{stats['avg_holding_days']:.0f} days" if stats["avg_holding_days"] is not None else "N/A"

    lines = [
        f"| Stat | Value |",
        f"|------|-------|",
        f"| Total picks | {stats['total_picks']} ({stats['open_picks']} open, {stats['closed_picks']} closed) |",
        f"| Win rate | {win_rate} |",
        f"| Avg winner | {avg_w} |",
        f"| Avg loser | {avg_l} |",
        f"| Avg holding period | {hold_d} |",
        f"| Best pick | {stats['best_pick'] or 'N/A'} |",
        f"| Worst pick | {stats['worst_pick'] or 'N/A'} |",
    ]

    # Per-sector breakdown if there's data
    if stats["by_sector"]:
        lines += ["", "**By sector:**", ""]
        lines += ["| Sector | Picks | Win Rate |", "|--------|------:|---------:|"]
        for sector, s in sorted(stats["by_sector"].items()):
            lines.append(f"| {sector} | {s['picks']} | {s['win_rate']*100:.0f}% |")

    return "\n".join(lines)
