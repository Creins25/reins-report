# Macro Markets Weekly Journal

A personal discipline for tracking cross-asset markets every week. Each Sunday, one command generates a pre-filled Markdown entry with Friday closing levels for rates, equities, FX, credit, commodities, and vol — then you write the rest.

---

## Setup

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
# 1. Clone / navigate to the project
cd macro-journal

# 2. Install dependencies
uv sync

# 3. Copy the example env file and add your FRED key
cp .env.example .env
# Then open .env and replace "your_key_here" with your actual key.
# Free key: https://fred.stlouisfed.org/docs/api/api_key.html

# 4. Activate the virtual environment (optional but handy)
source .venv/bin/activate
```

---

## Running

```bash
# Generate this week's entry (run on Sunday after markets close)
python cli.py new

# Force overwrite an existing entry
python cli.py new --force

# Refresh the data cache without creating a new entry
python cli.py fetch
```

The entry is written to `entries/YYYY-WWW.md` (e.g. `entries/2026-W22.md`).

---

## Weekly Workflow

1. **Sunday evening** — run `python cli.py new`
2. Open the generated entry in your editor
3. Fill in the **Theme** line at the top
4. Fill in the **Data Releases** table (actuals vs. consensus — check Bloomberg, Fed website, BLS)
5. Write **Central Bank Watch**, **Narrative**, and **My View**
6. Add any macro **Trade Ideas** and review **Last Week's Post-Mortem** honestly
7. Add stock picks throughout the week with `python cli.py picks add`
8. Log what you read in **Reading Log**
9. Commit to git: `git add entries/ data/picks_ledger.csv && git commit -m "journal: 2026-W22"`

---

## Stock Picks

The picks system gives you a persistent, auditable track record alongside your macro analysis.

### How it works

- Every pick is stored in `data/picks_ledger.csv` — **this is the source of truth**
- Add picks throughout the week with `python cli.py picks add` — it auto-fetches the Friday close as your entry price
- When `python cli.py new` runs on Sunday, it refreshes all open picks prices and auto-populates sections 7–10 of the entry
- Close picks with `python cli.py picks close <ID>` — P&L is computed and locked at that point

### Key rules

- **Never edit the ledger CSV manually** — always use the CLI. The CLI validates tickers and locks entry prices to the Friday close.
- **Commit the ledger to git** — each commit is a timestamped snapshot of your track record. This is your audit trail.
- **Dividends are ignored** — P&L is price return only. Note this when publishing.
- **Splits are handled** — yfinance uses auto-adjusted prices, so splits don't distort historical entry prices.

### Commands

```bash
python cli.py picks add            # Walk through adding a new pick interactively
python cli.py picks close <ID>     # Close a pick (ID shown in 'picks list')
python cli.py picks list           # See all open picks with live P&L
python cli.py picks record         # See overall track record stats
```

---

## Project Structure

```
macro-journal/
├── entries/               ← generated weekly Markdown files
├── templates/
│   └── weekly.md          ← edit this to change the entry structure
├── scripts/
│   ├── config.py          ← all tickers, FRED series IDs, and sector list
│   ├── fetch_data.py      ← yfinance + FRED fetching + macro table formatter
│   ├── new_week.py        ← week-date logic + template filling
│   ├── picks.py           ← picks ledger: add, close, refresh, track record
│   └── scorecard.py       ← Markdown formatters for sections 7–10
├── data/
│   ├── cache/             ← Parquet cache (gitignored, regenerated on demand)
│   └── picks_ledger.csv   ← persistent track record (committed to git)
├── cli.py                 ← Click CLI entry point
├── .env                   ← your FRED API key (gitignored)
└── pyproject.toml         ← uv dependency manifest
```

---

## Roadmap (not built yet)

- **Chart generation** — equity curve chart, sparklines per pick (matplotlib is installed, not wired up yet)
- **Fundamentals enrichment** — P/E, market cap, short interest per pick when adding
- **Stop/target alerts** — notify when a pick hits its stop or target
- **Static site publishing** — convert entries to HTML under a personal domain; `PUBLISH_HOOK` comment marks the injection point
- **LinkedIn / Substack formatter** — strip private sections, reformat Narrative + picks for public distribution
- **Pick backtesting** — replay historical picks against actual price data
