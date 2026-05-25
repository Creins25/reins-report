"""
Central configuration for all tickers and data series.
Edit this file to add, remove, or rename instruments in your journal.
"""

# ---------------------------------------------------------------------------
# yfinance tickers
# Key: display name used in the scoreboard table
# Value: yfinance ticker symbol
# ---------------------------------------------------------------------------
YFINANCE_TICKERS = {
    # Equities
    "SPX":    "^GSPC",
    "NDX":    "^NDX",
    "RUT":    "^RUT",
    # Sector ETFs
    "XLF":    "XLF",
    "XLE":    "XLE",
    "XLK":    "XLK",
    "XLY":    "XLY",
    "XLP":    "XLP",
    # FX  (yfinance convention: XXXYYY=X for spot, DX-Y.NYB for ICE DXY)
    "DXY":    "DX-Y.NYB",
    "EURUSD": "EURUSD=X",
    "USDJPY": "JPY=X",
    "USDCNH": "USDCNH=X",
    # Credit proxy ETFs (note: price return only, not total return)
    "HYG":    "HYG",
    "LQD":    "LQD",
    # Commodities (front-month futures)
    "WTI":    "CL=F",
    "Gold":   "GC=F",
    "Copper": "HG=F",
    # Volatility
    "VIX":    "^VIX",
    # MOVE index — may return N/A if not available via yfinance
    "MOVE":   "^MOVE",
}

# ---------------------------------------------------------------------------
# FRED series IDs
# Key: display name used in the scoreboard table
# Value: FRED series ID
# Requires FRED_API_KEY in .env
# ---------------------------------------------------------------------------
FRED_SERIES = {
    "US2Y":  "DGS2",    # 2-Year Treasury Constant Maturity Rate (%)
    "US10Y": "DGS10",   # 10-Year Treasury Constant Maturity Rate (%)
    # DTWEXBGS = Trade Weighted USD Index: Broad Goods & Services (proxy for DXY)
    # This has a reporting lag of ~1 week; useful for trend context.
    "DXY_FRED": "DTWEXBGS",
}

# ---------------------------------------------------------------------------
# Scoreboard display order
# Determines the row order in the generated Markdown table.
# Each entry: (display_name, source, decimals, unit)
#   source:   "yf" | "fred"
#   decimals: int — how many decimal places to show
#   unit:     "" | "%" | "bps" — appended to the raw value display
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# GICS-style sector list — used for validation when adding stock picks
# ---------------------------------------------------------------------------
SECTORS = [
    "Tech",
    "Financials",
    "Healthcare",
    "Energy",
    "Industrials",
    "Consumer Discretionary",
    "Consumer Staples",
    "Communication Services",
    "Utilities",
    "Real Estate",
    "Materials",
]

SCOREBOARD_ROWS = [
    # --- Rates ---
    ("US2Y",    "fred", 2, "%"),
    ("US10Y",   "fred", 2, "%"),
    # 2s10s spread is computed, not fetched — handled in format_scoreboard_table
    ("2s10s",   "computed", 0, "bps"),
    ("MOVE",    "yf",  1, ""),
    # --- Equities ---
    ("SPX",     "yf",  1, ""),
    ("NDX",     "yf",  1, ""),
    ("RUT",     "yf",  1, ""),
    ("XLF",     "yf",  2, ""),
    ("XLE",     "yf",  2, ""),
    ("XLK",     "yf",  2, ""),
    ("XLY",     "yf",  2, ""),
    ("XLP",     "yf",  2, ""),
    # --- FX ---
    ("DXY",     "yf",  2, ""),
    ("EURUSD",  "yf",  4, ""),
    ("USDJPY",  "yf",  2, ""),
    ("USDCNH",  "yf",  4, ""),
    # --- Credit ---
    ("HYG",     "yf",  2, ""),    # proxy for HY spreads
    ("LQD",     "yf",  2, ""),    # proxy for IG spreads
    # --- Commodities ---
    ("WTI",     "yf",  2, ""),
    ("Gold",    "yf",  1, ""),
    ("Copper",  "yf",  4, ""),
    # --- Vol ---
    ("VIX",     "yf",  2, ""),
]
