"""
Research layer: earnings calendar, analyst moves, consensus price targets.

Tickers tracked = union of open picks + watchlist (data/watchlist.json).
Results are cached as JSON in data/cache/ to avoid hammering the API on
multiple runs in the same day.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from scripts.picks import _load_ledger

_PROJECT_ROOT  = Path(__file__).resolve().parent.parent
WATCHLIST_PATH = _PROJECT_ROOT / "data" / "watchlist.json"
CACHE_DIR      = _PROJECT_ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Weekday names for display ────────────────────────────────────────────────
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ── Watchlist persistence ────────────────────────────────────────────────────

def load_watchlist() -> dict[str, str]:
    """Load {ticker: sector} from watchlist.json. Creates default if missing."""
    if not WATCHLIST_PATH.exists():
        _DEFAULT = {
            "AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Communication Services",
            "META": "Communication Services", "AMZN": "Consumer Discretionary",
            "TSLA": "Consumer Discretionary", "GS": "Financials", "JPM": "Financials",
            "XOM": "Energy", "MU": "Tech", "DELL": "Tech", "CRM": "Tech",
        }
        save_watchlist(_DEFAULT)
        return _DEFAULT
    with open(WATCHLIST_PATH) as f:
        return json.load(f)


def save_watchlist(wl: dict[str, str]) -> None:
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(dict(sorted(wl.items())), f, indent=2)


def get_all_tracked_tickers() -> list[str]:
    """Return sorted unique list of all tickers we care about."""
    ledger   = _load_ledger()
    picks    = ledger[ledger["status"] == "open"]["ticker"].tolist()
    watchlist = list(load_watchlist().keys())
    return sorted(set(picks + watchlist))


# ── Earnings calendar ────────────────────────────────────────────────────────

def fetch_earnings_calendar(tickers: list[str], weeks_ahead: int = 3) -> list[dict]:
    """
    Return upcoming earnings dates for any ticker that reports within
    weeks_ahead weeks.  Results cached for the current date.
    """
    cache_file = CACHE_DIR / f"earnings_{date.today().isoformat()}.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        # Filter to requested tickers only
        return [r for r in cached if r["ticker"] in tickers]

    today  = date.today()
    cutoff = today + timedelta(weeks=weeks_ahead)
    results = []

    for ticker in tickers:
        try:
            t   = yf.Ticker(ticker)
            cal = t.calendar           # dict or None depending on yf version
            if not cal:
                continue

            # yfinance ≥ 0.2 returns a dict; older returns a DataFrame
            if isinstance(cal, dict):
                raw_dates = cal.get("Earnings Date") or []
                eps_low   = cal.get("Earnings Low",     [None])[0] if isinstance(cal.get("Earnings Low"),     list) else cal.get("Earnings Low")
                eps_high  = cal.get("Earnings High",    [None])[0] if isinstance(cal.get("Earnings High"),    list) else cal.get("Earnings High")
                eps_avg   = cal.get("Earnings Average", [None])[0] if isinstance(cal.get("Earnings Average"), list) else cal.get("Earnings Average")
                rev_avg   = cal.get("Revenue Average",  [None])[0] if isinstance(cal.get("Revenue Average"),  list) else cal.get("Revenue Average")
            else:
                # DataFrame format (older yfinance)
                raw_dates = []
                eps_low = eps_high = eps_avg = rev_avg = None

            for raw in raw_dates:
                earn_date = raw.date() if hasattr(raw, "date") else raw
                if not isinstance(earn_date, date):
                    continue
                if today <= earn_date <= cutoff:
                    results.append({
                        "ticker":   ticker,
                        "date":     earn_date.isoformat(),
                        "weekday":  _WEEKDAYS[earn_date.weekday()],
                        "eps_low":  round(float(eps_low),  2) if eps_low  is not None else None,
                        "eps_high": round(float(eps_high), 2) if eps_high is not None else None,
                        "eps_avg":  round(float(eps_avg),  2) if eps_avg  is not None else None,
                        "rev_avg":  round(float(rev_avg),  0) if rev_avg  is not None else None,
                    })
                    break  # one entry per ticker
        except Exception as e:
            print(f"  [warn] Earnings fetch failed for {ticker}: {e}")

    results.sort(key=lambda x: x["date"])
    # Cache full result (all tracked tickers)
    cache_file.write_text(json.dumps(results, default=str))
    return results


# ── Analyst moves ────────────────────────────────────────────────────────────

def fetch_analyst_moves(tickers: list[str], days: int = 30) -> pd.DataFrame:
    """
    Recent analyst upgrades / downgrades / initiations for each ticker.
    Returns DataFrame sorted by date descending.
    """
    cache_file = CACHE_DIR / f"analyst_moves_{date.today().isoformat()}.parquet"
    if cache_file.exists():
        df = pd.read_parquet(cache_file)
        return df[df["ticker"].isin(tickers)]

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    rows   = []

    for ticker in tickers:
        try:
            t  = yf.Ticker(ticker)
            ud = t.upgrades_downgrades
            if ud is None or ud.empty:
                continue
            # Index may be tz-aware or tz-naive — normalise
            if ud.index.tz is not None:
                recent = ud[ud.index >= cutoff]
            else:
                recent = ud[ud.index >= cutoff.tz_localize(None)]

            for dt, row in recent.iterrows():
                rows.append({
                    "ticker":     ticker,
                    "date":       dt.date().isoformat(),
                    "firm":       row.get("Firm", "Unknown"),
                    "from_grade": row.get("FromGrade", ""),
                    "to_grade":   row.get("ToGrade", ""),
                    "action":     row.get("Action", ""),
                })
        except Exception as e:
            print(f"  [warn] Analyst moves fetch failed for {ticker}: {e}")

    if not rows:
        return pd.DataFrame(columns=["ticker", "date", "firm", "from_grade", "to_grade", "action"])

    df = pd.DataFrame(rows).sort_values("date", ascending=False)
    df.to_parquet(cache_file)
    return df


# ── Consensus price targets ──────────────────────────────────────────────────

def fetch_price_targets(tickers: list[str]) -> pd.DataFrame:
    """
    Analyst consensus price target summary for each ticker.
    Includes current price and implied upside to mean target.
    """
    cache_file = CACHE_DIR / f"price_targets_{date.today().isoformat()}.parquet"
    if cache_file.exists():
        df = pd.read_parquet(cache_file)
        return df[df["ticker"].isin(tickers)]

    # Batch-fetch current prices first
    try:
        raw = yf.download(tickers, period="1d", auto_adjust=True, progress=False)
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else \
                 raw[["Close"]].rename(columns={"Close": tickers[0]})
        current_prices = {
            t: float(closes[t].dropna().iloc[-1])
            for t in tickers if t in closes.columns and not closes[t].dropna().empty
        }
    except Exception:
        current_prices = {}

    rows = []
    for ticker in tickers:
        try:
            t       = yf.Ticker(ticker)
            targets = t.analyst_price_targets
            if not targets:
                continue
            current = current_prices.get(ticker)
            mean    = targets.get("mean")
            upside  = ((mean / current) - 1) * 100 if mean and current else None
            rows.append({
                "ticker":       ticker,
                "current":      round(current, 2) if current else None,
                "target_low":   targets.get("low"),
                "target_mean":  targets.get("mean"),
                "target_high":  targets.get("high"),
                "upside_pct":   round(upside, 1) if upside is not None else None,
                "num_analysts": targets.get("numberOfAnalysts"),
            })
        except Exception as e:
            print(f"  [warn] Price target fetch failed for {ticker}: {e}")

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.to_parquet(cache_file)
    return df


# ── Markdown formatters ──────────────────────────────────────────────────────

def format_earnings_radar(tickers: list[str], weeks_ahead: int = 3) -> str:
    """Markdown table of upcoming earnings for tracked tickers."""
    open_tickers = set(_load_ledger()[_load_ledger()["status"] == "open"]["ticker"].tolist())
    events = fetch_earnings_calendar(tickers, weeks_ahead)

    if not events:
        return "*No earnings from tracked tickers in the next 3 weeks.*"

    lines = [
        "| Ticker | Date | Day | EPS Est | Rev Est | Portfolio? |",
        "|--------|------|:---:|--------:|--------:|:----------:|",
    ]
    for e in events:
        eps_str = f"${e['eps_avg']:.2f}" if e.get("eps_avg") is not None else "N/A"
        rev_str = f"${e['rev_avg']/1e9:.1f}B" if e.get("rev_avg") else "N/A"
        flag    = "✅ Open pick" if e["ticker"] in open_tickers else "👁 Watchlist"
        lines.append(
            f"| **{e['ticker']}** | {e['date']} | {e['weekday']} | "
            f"{eps_str} | {rev_str} | {flag} |"
        )

    return "\n".join(lines)


def format_analyst_moves_table(tickers: list[str]) -> str:
    """Markdown table of recent analyst rating changes (last 30 days)."""
    df = fetch_analyst_moves(tickers)

    if df.empty:
        return "*No analyst rating changes in the last 30 days for tracked tickers.*"

    _ACTION_ICON = {"up": "⬆️", "down": "⬇️", "main": "➡️", "init": "🆕"}
    lines = [
        "| Ticker | Date | Firm | Action | Rating Change |",
        "|--------|------|------|:------:|---------------|",
    ]
    for _, row in df.head(12).iterrows():
        icon     = _ACTION_ICON.get(str(row["action"]).lower(), "")
        from_to  = f"{row['from_grade']} → **{row['to_grade']}**" if row["from_grade"] else f"**{row['to_grade']}**"
        lines.append(
            f"| **{row['ticker']}** | {row['date']} | {row['firm']} | "
            f"{icon} {str(row['action']).title()} | {from_to} |"
        )

    return "\n".join(lines)


def format_price_targets_table(tickers: list[str]) -> str:
    """Markdown table of analyst consensus price targets vs current price."""
    df = fetch_price_targets(tickers)

    if df.empty:
        return "*No consensus price target data available.*"

    lines = [
        "| Ticker | Current | Target Low | Mean | High | Upside | Analysts |",
        "|--------|--------:|-----------:|-----:|-----:|-------:|---------:|",
    ]
    for _, row in df.iterrows():
        def _f(v, fmt="$.2f"):
            return f"${v:{fmt[1:]}}" if v is not None and not (isinstance(v, float) and pd.isna(v)) else "N/A"
        upside_str = f"{row['upside_pct']:+.1f}%" if row.get("upside_pct") is not None else "N/A"
        analysts   = int(row["num_analysts"]) if row.get("num_analysts") else "N/A"
        lines.append(
            f"| **{row['ticker']}** | {_f(row.get('current'))} | "
            f"{_f(row.get('target_low'))} | {_f(row.get('target_mean'))} | "
            f"{_f(row.get('target_high'))} | {upside_str} | {analysts} |"
        )

    return "\n".join(lines)
