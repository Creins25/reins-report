"""
Data fetching layer: yfinance + FRED.

All API responses are cached to data/cache/ as Parquet files keyed by date,
so re-running the same week doesn't burn API calls.
"""

import os
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

from scripts.config import YFINANCE_TICKERS, FRED_SERIES, SCOREBOARD_ROWS

load_dotenv()

# Path to cache directory (relative to project root, resolved at import time)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = _PROJECT_ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cache_path(label: str, end_date: date) -> Path:
    """Return a consistent Parquet cache path for a given label + date."""
    return CACHE_DIR / f"{label}_{end_date.isoformat()}.parquet"


def _prev_friday(d: date) -> date:
    """Return the most recent Friday on or before d."""
    # weekday(): Mon=0 … Fri=4 … Sun=6
    offset = (d.weekday() - 4) % 7  # days since last Friday
    return d - timedelta(days=offset)


def _ytd_start(d: date) -> date:
    """Return Dec 31 of the prior year (last trading day proxy for YTD base)."""
    return date(d.year - 1, 12, 31)


# ---------------------------------------------------------------------------
# yfinance fetch
# ---------------------------------------------------------------------------

def fetch_yfinance_levels(tickers: dict[str, str], end_date: date) -> pd.DataFrame:
    """
    Fetch Friday close, 1W change %, and YTD change % for each ticker.

    Args:
        tickers: {display_name: yfinance_symbol} — from config.YFINANCE_TICKERS
        end_date: the Friday whose close we want

    Returns:
        DataFrame indexed by display_name with columns:
        [close, prev_close, ytd_base, chg_1w_pct, chg_ytd_pct]
    """
    cache_file = _cache_path("yf", end_date)
    if cache_file.exists():
        print(f"  [cache] yfinance data loaded from {cache_file.name}")
        return pd.read_parquet(cache_file)

    friday = _prev_friday(end_date)
    prev_friday = friday - timedelta(weeks=1)
    ytd_base_date = _ytd_start(friday)

    # Download enough history to cover YTD base + current week
    # yfinance end date is exclusive, so add 1 day
    symbols = list(tickers.values())
    print(f"  [fetch] Downloading {len(symbols)} tickers from yfinance …")

    try:
        raw = yf.download(
            symbols,
            start=ytd_base_date,
            end=friday + timedelta(days=1),
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        print(f"  [error] yfinance download failed: {e}")
        return pd.DataFrame()

    # yfinance returns MultiIndex columns (Price, Ticker) when multiple tickers
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        # Single ticker — wrap in DataFrame with ticker as column name
        closes = raw[["Close"]].rename(columns={"Close": symbols[0]})

    # Reverse-map yfinance symbol → display name
    symbol_to_name = {v: k for k, v in tickers.items()}

    rows = []
    for symbol in symbols:
        name = symbol_to_name.get(symbol, symbol)
        if symbol not in closes.columns:
            rows.append({"name": name, "close": None, "prev_close": None,
                         "ytd_base": None, "chg_1w_pct": None, "chg_ytd_pct": None})
            continue

        col = closes[symbol].dropna()
        if col.empty:
            rows.append({"name": name, "close": None, "prev_close": None,
                         "ytd_base": None, "chg_1w_pct": None, "chg_ytd_pct": None})
            continue

        # Get the closest available date on or before each target date
        def _get_closest(series: pd.Series, target: date):
            idx = series.index.normalize()
            target_ts = pd.Timestamp(target)
            past = series[idx <= target_ts]
            return float(past.iloc[-1]) if not past.empty else None

        close     = _get_closest(col, friday)
        prev_close = _get_closest(col, prev_friday)
        ytd_base  = _get_closest(col, ytd_base_date)

        chg_1w  = ((close / prev_close) - 1) * 100 if close and prev_close else None
        chg_ytd = ((close / ytd_base) - 1) * 100  if close and ytd_base  else None

        rows.append({
            "name":      name,
            "close":     close,
            "prev_close": prev_close,
            "ytd_base":  ytd_base,
            "chg_1w_pct": chg_1w,
            "chg_ytd_pct": chg_ytd,
        })

    df = pd.DataFrame(rows).set_index("name")
    df.to_parquet(cache_file)
    print(f"  [cache] yfinance data saved to {cache_file.name}")
    return df


# ---------------------------------------------------------------------------
# FRED fetch
# ---------------------------------------------------------------------------

def fetch_fred_series(series_ids: dict[str, str], end_date: date) -> pd.DataFrame:
    """
    Fetch rate levels and 1W/YTD changes from FRED.

    Args:
        series_ids: {display_name: FRED_series_id} — from config.FRED_SERIES
        end_date:   the date whose observation we want (closest available)

    Returns:
        DataFrame indexed by display_name with columns:
        [close, prev_close, ytd_base, chg_1w_pct, chg_ytd_pct]
        For rates, close is the level (e.g. 4.32 for 4.32%).
        chg_1w and chg_ytd are absolute changes in basis points (level diff * 100).
    """
    cache_file = _cache_path("fred", end_date)
    if cache_file.exists():
        print(f"  [cache] FRED data loaded from {cache_file.name}")
        return pd.read_parquet(cache_file)

    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        print("  [warn] FRED_API_KEY not set in .env — skipping FRED fetch.")
        return pd.DataFrame()

    try:
        from fredapi import Fred
        fred = Fred(api_key=api_key)
    except ImportError:
        print("  [error] fredapi not installed.")
        return pd.DataFrame()

    friday = _prev_friday(end_date)
    prev_friday = friday - timedelta(weeks=1)
    ytd_base_date = _ytd_start(friday)

    rows = []
    for name, series_id in series_ids.items():
        print(f"  [fetch] FRED {series_id} ({name}) …")
        try:
            # observation_start gives us just the slice we need
            s = fred.get_series(
                series_id,
                observation_start=ytd_base_date,
                observation_end=friday,
            )
            s = s.dropna()

            def _get_closest_fred(series: pd.Series, target: date):
                target_ts = pd.Timestamp(target)
                past = series[series.index <= target_ts]
                return float(past.iloc[-1]) if not past.empty else None

            close     = _get_closest_fred(s, friday)
            prev_close = _get_closest_fred(s, prev_friday)
            ytd_base  = _get_closest_fred(s, ytd_base_date)

            # For rates: 1W change in bps, YTD change in bps
            chg_1w  = (close - prev_close) * 100 if close is not None and prev_close is not None else None
            chg_ytd = (close - ytd_base) * 100  if close is not None and ytd_base  is not None else None

            rows.append({
                "name": name,
                "close": close,
                "prev_close": prev_close,
                "ytd_base": ytd_base,
                "chg_1w_pct": chg_1w,
                "chg_ytd_pct": chg_ytd,
            })
        except Exception as e:
            print(f"  [error] FRED fetch failed for {series_id}: {e}")
            rows.append({"name": name, "close": None, "prev_close": None,
                         "ytd_base": None, "chg_1w_pct": None, "chg_ytd_pct": None})

    df = pd.DataFrame(rows).set_index("name")
    df.to_parquet(cache_file)
    print(f"  [cache] FRED data saved to {cache_file.name}")
    return df


# ---------------------------------------------------------------------------
# Scoreboard table formatter
# ---------------------------------------------------------------------------

def format_scoreboard_table(yf_data: pd.DataFrame, fred_data: pd.DataFrame) -> str:
    """
    Combine yfinance and FRED data into a Markdown table string.

    The row order and display logic follow SCOREBOARD_ROWS in config.py.
    Rate changes (FRED rows) are shown in bps; price changes in %.
    """
    header = (
        "| Instrument | Close | 1W Chg | YTD Chg |\n"
        "|------------|------:|-------:|--------:|"
    )
    lines = [header]

    # Section separators — insert a blank separator row when category changes
    section_breaks = {
        "US2Y": "**Rates**",
        "SPX":  "**Equities**",
        "DXY":  "**FX**",
        "HYG":  "**Credit** *(ETF proxies — price return only)*",
        "WTI":  "**Commodities**",
        "VIX":  "**Vol**",
    }

    def _fmt_val(val, decimals: int, unit: str) -> str:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "N/A"
        return f"{val:.{decimals}f}{unit}"

    def _fmt_chg(val, is_bps: bool) -> str:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "N/A"
        sign = "+" if val >= 0 else ""
        if is_bps:
            return f"{sign}{val:.0f}bps"
        return f"{sign}{val:.2f}%"

    # Compute 2s10s spread once if both rates are available
    us2y_close  = None
    us10y_close = None
    us2y_prev   = None
    us10y_prev  = None
    us2y_ytd    = None
    us10y_ytd   = None
    if not fred_data.empty:
        if "US2Y" in fred_data.index:
            us2y_close = fred_data.loc["US2Y", "close"]
            us2y_prev  = fred_data.loc["US2Y", "prev_close"]
            us2y_ytd   = fred_data.loc["US2Y", "ytd_base"]
        if "US10Y" in fred_data.index:
            us10y_close = fred_data.loc["US10Y", "close"]
            us10y_prev  = fred_data.loc["US10Y", "prev_close"]
            us10y_ytd   = fred_data.loc["US10Y", "ytd_base"]

    spread_close = (us10y_close - us2y_close) * 100 if us10y_close and us2y_close else None
    spread_prev  = (us10y_prev - us2y_prev)   * 100 if us10y_prev  and us2y_prev  else None
    spread_ytd   = (us10y_ytd - us2y_ytd)     * 100 if us10y_ytd   and us2y_ytd   else None

    for display_name, source, decimals, unit in SCOREBOARD_ROWS:
        # Insert section header row
        if display_name in section_breaks:
            lines.append(f"| {section_breaks[display_name]} | | | |")

        # 2s10s spread is computed inline
        if source == "computed" and display_name == "2s10s":
            close_str = _fmt_val(spread_close, 0, "bps")
            chg_1w    = _fmt_chg((spread_close - spread_prev) if spread_close and spread_prev else None, is_bps=True)
            chg_ytd   = _fmt_chg((spread_close - spread_ytd)  if spread_close and spread_ytd  else None, is_bps=True)
            lines.append(f"| 2s10s | {close_str} | {chg_1w} | {chg_ytd} |")
            continue

        # Select data source
        if source == "fred":
            data = fred_data
            is_bps = True   # FRED rate changes reported in bps
        else:
            data = yf_data
            is_bps = False  # yfinance price changes reported in %

        if data.empty or display_name not in data.index:
            lines.append(f"| {display_name} | N/A | N/A | N/A |")
            continue

        row = data.loc[display_name]
        close_str = _fmt_val(row.get("close"), decimals, unit)
        chg_1w    = _fmt_chg(row.get("chg_1w_pct"), is_bps)
        chg_ytd   = _fmt_chg(row.get("chg_ytd_pct"), is_bps)
        lines.append(f"| {display_name} | {close_str} | {chg_1w} | {chg_ytd} |")

    return "\n".join(lines)
