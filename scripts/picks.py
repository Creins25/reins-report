"""
Persistent stock picks ledger.

The ledger lives at data/picks_ledger.csv and is the single source of truth
for every pick ever made. Never edit it manually — use these functions.

P&L convention:
  Long:  (current - entry) / entry * 100
  Short: (entry - current) / entry * 100
"""

import uuid
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = _PROJECT_ROOT / "data" / "picks_ledger.csv"

LEDGER_COLUMNS = [
    "pick_id", "date_added", "week_added", "ticker", "direction",
    "entry_price", "current_price", "target_price", "stop_price",
    "conviction", "time_horizon", "sector", "thesis", "catalyst",
    "account_risk_pct",                  # % of account risked (e.g. 1.0)
    "entry_note",                        # plain-English buy window + disclaimer
    # ── Options fields (blank for equity picks) ───────────────────────────────
    "instrument_type",   # "equity" | "call" | "put"
    "strike",            # option strike price
    "expiry",            # option expiry date YYYY-MM-DD
    "premium_paid",      # cost per share at entry ($)
    "delta",             # Δ — directional exposure
    "gamma",             # Γ — delta sensitivity
    "theta_daily",       # Θ — daily decay ($ per share, negative)
    "vega_1pct",         # ν — value change per +1% IV
    "iv_used",           # implied vol used for pricing (decimal)
    "break_even",        # underlying price for zero P&L at expiry
    "leverage",          # spot / premium (effective leverage)
    # ─────────────────────────────────────────────────────────────────────────
    "status", "date_closed", "close_price", "close_reason", "realized_pnl_pct",
]

# Valid values for constrained fields
VALID_DIRECTIONS = ["long", "short"]
VALID_HORIZONS   = ["short", "medium", "long"]
VALID_STATUSES   = ["open", "closed_winner", "closed_loser", "closed_stopped"]
VALID_REASONS    = ["target_hit", "stop_hit", "thesis_broken", "time_expired", "manual", "delisted"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_ledger() -> pd.DataFrame:
    """Load the CSV ledger, returning an empty DataFrame if it doesn't exist yet."""
    if not LEDGER_PATH.exists():
        return pd.DataFrame(columns=LEDGER_COLUMNS)

    df = pd.read_csv(LEDGER_PATH, dtype=str).fillna("")

    # Convert numeric columns — empty strings become NaN, which is correct
    for col in ["entry_price", "current_price", "target_price", "stop_price",
                "conviction", "realized_pnl_pct", "close_price",
                "account_risk_pct",
                "strike", "premium_paid", "delta", "gamma",
                "theta_daily", "vega_1pct", "iv_used", "break_even", "leverage"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _save_ledger(df: pd.DataFrame) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(LEDGER_PATH, index=False)


def _compute_live_pnl(entry: float, current: float, direction: str) -> float | None:
    """Return live P&L % for a single pick. Returns None if inputs are invalid."""
    if pd.isna(entry) or pd.isna(current) or entry == 0:
        return None
    if direction.lower() == "short":
        return (entry - current) / entry * 100
    return (current - entry) / entry * 100


def _get_friday_close(ticker: str) -> tuple[float, date]:
    """
    Fetch the most recent Friday closing price for a ticker.
    Returns (price, actual_date).
    Raises ValueError if no data is found.
    """
    today = date.today()
    # Most recent Friday on or before today
    days_since_friday = (today.weekday() - 4) % 7
    friday = today - timedelta(days=days_since_friday)

    t = yf.Ticker(ticker)
    # Download a 2-week window to ensure we catch the Friday
    hist = t.history(
        start=friday - timedelta(days=7),
        end=friday + timedelta(days=1),
        auto_adjust=True,
    )

    if hist.empty:
        raise ValueError(f"No price data found for ticker '{ticker}'")

    # yf.Ticker.history() returns a tz-aware index (NYSE timezone).
    # Strip tz info so we can compare against a plain date.
    hist.index = hist.index.tz_convert("UTC").tz_localize(None).normalize()
    hist = hist[hist.index <= pd.Timestamp(friday)]

    if hist.empty:
        raise ValueError(f"No price data for '{ticker}' on or before {friday}")

    price = float(hist["Close"].iloc[-1])
    actual_date = hist.index[-1].date()
    return price, actual_date


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_pick(
    ticker: str,
    direction: str,
    target: float,
    stop: float,
    conviction: int,
    horizon: str,
    sector: str,
    thesis: str,
    catalyst: str,
    account_risk_pct: float | None = None,
    entry_note: str = "",              # plain-English buy window + disclaimer
    # Options fields (all optional — leave blank for equity picks)
    instrument_type: str   = "equity",
    strike:          float | None = None,
    expiry:          str   | None = None,   # YYYY-MM-DD
    premium_paid:    float | None = None,
    delta:           float | None = None,
    gamma:           float | None = None,
    theta_daily:     float | None = None,
    vega_1pct:       float | None = None,
    iv_used:         float | None = None,
    break_even:      float | None = None,
    leverage:        float | None = None,
) -> tuple[str, float]:
    """
    Add a new pick to the ledger.

    Entry price is automatically set to the most recent Friday close.
    Returns (pick_id, entry_price).
    """
    ticker = ticker.upper().strip()

    # Fetch and validate entry price before writing anything
    print(f"  [fetch] Looking up Friday close for {ticker} …")
    entry_price, price_date = _get_friday_close(ticker)
    print(f"  Entry price: ${entry_price:.2f} ({price_date})")

    today = date.today()
    iso = today.isocalendar()
    week_str = f"{iso.year}-W{iso.week:02d}"
    pick_id = str(uuid.uuid4())[:8]  # 8-char prefix — readable, low collision risk

    new_row = {
        "pick_id":        pick_id,
        "date_added":     today.isoformat(),
        "week_added":     week_str,
        "ticker":         ticker,
        "direction":      direction.lower(),
        "entry_price":    round(entry_price, 4),
        "current_price":  round(entry_price, 4),  # same as entry at add time
        "target_price":   round(float(target), 4),
        "stop_price":     round(float(stop), 4),
        "conviction":     int(conviction),
        "time_horizon":   horizon.lower(),
        "sector":         sector,
        "thesis":         thesis.strip(),
        "catalyst":       catalyst.strip(),
        "account_risk_pct": round(float(account_risk_pct), 2) if account_risk_pct is not None else "",
        "entry_note":      entry_note.strip(),
        "instrument_type": instrument_type,
        "strike":          round(float(strike), 2)    if strike       is not None else "",
        "expiry":          str(expiry)                if expiry       is not None else "",
        "premium_paid":    round(float(premium_paid), 2) if premium_paid is not None else "",
        "delta":           round(float(delta), 3)    if delta        is not None else "",
        "gamma":           round(float(gamma), 4)    if gamma        is not None else "",
        "theta_daily":     round(float(theta_daily), 3) if theta_daily is not None else "",
        "vega_1pct":       round(float(vega_1pct), 3) if vega_1pct   is not None else "",
        "iv_used":         round(float(iv_used), 4)  if iv_used      is not None else "",
        "break_even":      round(float(break_even), 2) if break_even  is not None else "",
        "leverage":        round(float(leverage), 1) if leverage     is not None else "",
        "status":         "open",
        "date_closed":    "",
        "close_price":    "",
        "close_reason":   "",
        "realized_pnl_pct": "",
    }

    df = _load_ledger()
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    _save_ledger(df)

    return pick_id, entry_price


def refresh_prices() -> pd.DataFrame:
    """
    Update current_price for all open picks.

    If a ticker returns no data (delisting/M&A), marks it closed with
    reason='delisted' using the last known current_price.

    Returns the updated ledger DataFrame.
    """
    df = _load_ledger()
    open_mask = df["status"] == "open"

    if not open_mask.any():
        print("  No open picks to refresh.")
        return df

    tickers = df.loc[open_mask, "ticker"].unique().tolist()
    print(f"  [fetch] Refreshing prices for: {', '.join(tickers)}")

    try:
        raw = yf.download(
            tickers,
            period="5d",
            auto_adjust=True,
            progress=False,
        )
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else \
                 raw[["Close"]].rename(columns={"Close": tickers[0]})
    except Exception as e:
        print(f"  [error] Price refresh failed: {e}")
        return df

    for idx in df.index[open_mask]:
        ticker = df.at[idx, "ticker"]
        if ticker not in closes.columns:
            print(f"  [warn] {ticker} missing from response — skipping")
            continue

        series = closes[ticker].dropna()
        if series.empty:
            # No data at all — treat as potentially delisted
            print(f"  [warn] {ticker} has no recent price — marking delisted")
            last_price = df.at[idx, "current_price"]
            _mark_closed_internal(df, idx, "delisted", float(last_price) if pd.notna(last_price) else 0.0)
        else:
            df.at[idx, "current_price"] = round(float(series.iloc[-1]), 4)

    _save_ledger(df)
    return df


def _mark_closed_internal(df: pd.DataFrame, idx: int, reason: str, close_price: float) -> None:
    """Mutates df in place — helper used by refresh_prices and close_pick."""
    entry = float(df.at[idx, "entry_price"])
    direction = df.at[idx, "direction"]
    pnl = _compute_live_pnl(entry, close_price, direction)

    if reason == "target_hit":
        status = "closed_winner"
    elif reason == "stop_hit":
        status = "closed_stopped"
    else:
        status = "closed_winner" if (pnl or 0) > 0 else "closed_loser"

    df.at[idx, "status"]          = status
    df.at[idx, "date_closed"]     = date.today().isoformat()
    df.at[idx, "close_price"]     = round(close_price, 4)
    df.at[idx, "close_reason"]    = reason
    df.at[idx, "realized_pnl_pct"] = round(pnl, 4) if pnl is not None else ""


def close_pick(pick_id: str, reason: str, close_price: float | None = None) -> dict:
    """
    Close an open pick.

    pick_id: the 8-char ID shown when the pick was added (prefix match supported)
    reason:  one of VALID_REASONS
    close_price: if None, uses the current_price already in the ledger

    Returns a dict with the closed pick's summary.
    """
    df = _load_ledger()

    # Support prefix matching on pick_id
    matches = df[(df["pick_id"].str.startswith(pick_id)) & (df["status"] == "open")]
    if matches.empty:
        raise ValueError(f"No open pick found with ID starting with '{pick_id}'")
    if len(matches) > 1:
        ids = matches["pick_id"].tolist()
        raise ValueError(f"Ambiguous ID '{pick_id}' matches: {ids}")

    idx = matches.index[0]
    row = df.loc[idx]

    if close_price is None:
        close_price = float(row["current_price"]) if pd.notna(row["current_price"]) else float(row["entry_price"])

    _mark_closed_internal(df, idx, reason, close_price)
    _save_ledger(df)

    return {
        "pick_id":   df.at[idx, "pick_id"],
        "ticker":    df.at[idx, "ticker"],
        "status":    df.at[idx, "status"],
        "pnl":       df.at[idx, "realized_pnl_pct"],
    }


def get_open_picks() -> pd.DataFrame:
    """
    Return open picks with two computed columns added:
      live_pnl_pct: current unrealized P&L %
      days_held:    integer days since date_added
    Sorted by live_pnl_pct descending.
    """
    df = _load_ledger()
    open_df = df[df["status"] == "open"].copy()

    if open_df.empty:
        return open_df

    open_df["live_pnl_pct"] = open_df.apply(
        lambda r: _compute_live_pnl(r["entry_price"], r["current_price"], r["direction"]),
        axis=1,
    )
    open_df["days_held"] = open_df["date_added"].apply(
        lambda d: (date.today() - date.fromisoformat(d)).days if d else None
    )
    return open_df.sort_values("live_pnl_pct", ascending=False)


def get_closed_picks(year: int | None = None) -> pd.DataFrame:
    """Return closed picks, optionally filtered by the year they were closed."""
    df = _load_ledger()
    closed = df[df["status"].str.startswith("closed_")].copy()

    if year is not None and not closed.empty:
        closed = closed[closed["date_closed"].str.startswith(str(year))]

    if not closed.empty:
        closed["days_held"] = closed.apply(
            lambda r: (date.fromisoformat(r["date_closed"]) - date.fromisoformat(r["date_added"])).days
            if r["date_closed"] and r["date_added"] else None,
            axis=1,
        )
    return closed


def get_picks_closed_since(since_date: date) -> pd.DataFrame:
    """Return picks closed on or after since_date. Used by new_week.py."""
    closed = get_closed_picks()
    if closed.empty:
        return closed
    return closed[closed["date_closed"] >= since_date.isoformat()]


def compute_track_record() -> dict:
    """
    Compute headline performance stats across all closed picks.
    Returns a dict — see format_track_record_summary() for how it's displayed.
    """
    df = _load_ledger()
    open_picks  = df[df["status"] == "open"]
    closed_picks = df[df["status"].str.startswith("closed_")].copy()

    base = {
        "total_picks":  len(df),
        "open_picks":   len(open_picks),
        "closed_picks": len(closed_picks),
    }

    if closed_picks.empty:
        return {**base, "win_rate": None, "avg_winner": None, "avg_loser": None,
                "avg_holding_days": None, "best_pick": None, "worst_pick": None,
                "by_sector": {}}

    closed_picks["realized_pnl_pct"] = pd.to_numeric(closed_picks["realized_pnl_pct"], errors="coerce")
    closed_picks["days_held"] = closed_picks.apply(
        lambda r: (date.fromisoformat(r["date_closed"]) - date.fromisoformat(r["date_added"])).days
        if r["date_closed"] and r["date_added"] else None,
        axis=1,
    )

    winners = closed_picks[closed_picks["realized_pnl_pct"] > 0]
    losers  = closed_picks[closed_picks["realized_pnl_pct"] <= 0]

    best_idx  = closed_picks["realized_pnl_pct"].idxmax()
    worst_idx = closed_picks["realized_pnl_pct"].idxmin()
    best  = closed_picks.loc[best_idx]
    worst = closed_picks.loc[worst_idx]

    # Per-sector win rate
    by_sector = {}
    for sector, grp in closed_picks.groupby("sector"):
        wins = int((grp["realized_pnl_pct"] > 0).sum())
        by_sector[sector] = {"picks": len(grp), "wins": wins,
                             "win_rate": wins / len(grp)}

    return {
        **base,
        "win_rate":        len(winners) / len(closed_picks),
        "avg_winner":      float(winners["realized_pnl_pct"].mean()) if not winners.empty else None,
        "avg_loser":       float(losers["realized_pnl_pct"].mean())  if not losers.empty  else None,
        "avg_holding_days": float(closed_picks["days_held"].mean()),
        "best_pick":       f"{best['ticker']} ({best['realized_pnl_pct']:+.1f}%)",
        "worst_pick":      f"{worst['ticker']} ({worst['realized_pnl_pct']:+.1f}%)",
        "by_sector":       by_sector,
    }
