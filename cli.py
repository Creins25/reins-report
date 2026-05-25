"""
Macro Markets Weekly Journal — CLI entry point.

JOURNAL
  python cli.py new              Generate this week's journal entry
  python cli.py new --force      Overwrite if it already exists
  python cli.py fetch            Refresh macro data cache only

PICKS
  python cli.py picks add        Interactively add a new stock pick
  python cli.py picks close ID   Close an open pick by ID
  python cli.py picks list       Show all open picks with live P&L
  python cli.py picks record     Show overall track record stats

NEWSLETTER
  python cli.py newsletter generate          Generate newsletter for current week
  python cli.py newsletter generate --week 2026-W21   Specific week
  python cli.py newsletter preview           Print newsletter to terminal

WATCHLIST
  python cli.py watch list       Show current watchlist
  python cli.py watch add TICKER SECTOR    Add ticker to watchlist
  python cli.py watch remove TICKER        Remove ticker from watchlist

RESEARCH
  python cli.py research         Show earnings calendar + analyst moves for all tracked tickers
"""

import sys
from datetime import date
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent))


# ─────────────────────────────────────────────────────────────────────────────
# Root
# ─────────────────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """Macro Markets Weekly Journal."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Journal commands
# ─────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--force", is_flag=True, default=False,
              help="Overwrite existing entry.")
def new(force: bool):
    """Generate a new weekly journal entry with all data pre-populated."""
    from scripts.new_week import generate_entry
    try:
        entry_path = generate_entry(force=force)
        click.echo(f"\n✅ Entry created: {entry_path}")
    except FileExistsError as e:
        click.echo(f"[error] {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"[error] {e}", err=True)
        sys.exit(1)


@cli.command()
def fetch():
    """Refresh macro data cache without creating a new entry."""
    from datetime import timedelta
    from scripts.new_week import _target_week
    from scripts.fetch_data import fetch_yfinance_levels, fetch_fred_series, CACHE_DIR
    from scripts.config import YFINANCE_TICKERS, FRED_SERIES

    today = date.today()
    _monday, sunday, _y, _w = _target_week(today)
    friday = sunday - timedelta(days=1)

    click.echo(f"Refreshing macro cache for week ending {friday.isoformat()} …")
    for f in CACHE_DIR.glob(f"*_{friday.isoformat()}.parquet"):
        f.unlink()
        click.echo(f"  [deleted] {f.name}")

    fetch_yfinance_levels(YFINANCE_TICKERS, friday)
    fetch_fred_series(FRED_SERIES, friday)
    click.echo("✅ Macro cache refreshed.")


@cli.command()
def research():
    """Show earnings calendar + analyst moves for all tracked tickers."""
    import pandas as pd
    from scripts.research import (
        get_all_tracked_tickers,
        fetch_earnings_calendar,
        fetch_analyst_moves,
        fetch_price_targets,
    )

    tickers = get_all_tracked_tickers()
    click.echo(f"\nTracked tickers ({len(tickers)}): {', '.join(tickers)}")

    # Earnings
    click.echo("\n── Upcoming Earnings ────────────────────────────────────────")
    events = fetch_earnings_calendar(tickers, weeks_ahead=3)
    if events:
        click.echo(f"  {'Ticker':<8} {'Date':<12} {'Day':<5} {'EPS Est':>8}")
        click.echo("  " + "─" * 38)
        for e in events:
            eps = f"${e['eps_avg']:.2f}" if e.get("eps_avg") is not None else "N/A"
            click.echo(f"  {e['ticker']:<8} {e['date']:<12} {e['weekday']:<5} {eps:>8}")
    else:
        click.echo("  No earnings in the next 3 weeks for tracked tickers.")

    # Analyst moves
    click.echo("\n── Recent Analyst Moves (30 days) ───────────────────────────")
    df = fetch_analyst_moves(tickers)
    if not df.empty:
        for _, row in df.head(10).iterrows():
            from_to = f"{row['from_grade']} → {row['to_grade']}" if row["from_grade"] else row["to_grade"]
            click.echo(f"  {row['ticker']:<8} {row['date']}  {row['firm']:<20} {row['action'].title():<10} {from_to}")
    else:
        click.echo("  No rating changes found.")

    # Price targets
    click.echo("\n── Consensus Price Targets ──────────────────────────────────")
    pt = fetch_price_targets(tickers)
    if not pt.empty:
        click.echo(f"  {'Ticker':<8} {'Current':>9} {'Mean Target':>12} {'Upside':>8} {'Analysts':>9}")
        click.echo("  " + "─" * 52)
        for _, row in pt.iterrows():
            curr   = f"${row['current']:.2f}"   if row.get("current")      else "N/A"
            mean   = f"${row['target_mean']:.2f}" if row.get("target_mean") else "N/A"
            upside = f"{row['upside_pct']:+.1f}%" if row.get("upside_pct") is not None else "N/A"
            count  = int(row["num_analysts"]) if row.get("num_analysts") else "N/A"
            click.echo(f"  {row['ticker']:<8} {curr:>9} {mean:>12} {upside:>8} {str(count):>9}")
    else:
        click.echo("  No price target data found.")


# ─────────────────────────────────────────────────────────────────────────────
# Picks commands
# ─────────────────────────────────────────────────────────────────────────────

@cli.group()
def picks():
    """Manage your stock picks track record."""
    pass


@picks.command("add")
def picks_add():
    """Interactively add a new stock pick to the ledger."""
    from scripts.picks import add_pick, VALID_DIRECTIONS, VALID_HORIZONS
    from scripts.config import SECTORS

    click.echo("\n── Add New Stock Pick ──────────────────────────────────────")

    ticker    = click.prompt("Ticker").upper().strip()
    direction = click.prompt("Direction", type=click.Choice(VALID_DIRECTIONS, case_sensitive=False))
    target    = click.prompt("Target price", type=float)
    stop      = click.prompt("Stop price",   type=float)
    conviction = click.prompt("Conviction (1–5)", type=click.IntRange(1, 5))
    horizon   = click.prompt("Time horizon", type=click.Choice(VALID_HORIZONS, case_sensitive=False))

    click.echo(f"\nSectors: {', '.join(SECTORS)}")
    sector = click.prompt("Sector")
    sector_match = next((s for s in SECTORS if s.lower() == sector.lower()), None)
    while sector_match is None:
        click.echo(f"  Must be one of: {', '.join(SECTORS)}")
        sector = click.prompt("Sector")
        sector_match = next((s for s in SECTORS if s.lower() == sector.lower()), None)
    sector = sector_match

    thesis          = click.prompt("Thesis (why is it mispriced?)")
    catalyst        = click.prompt("Catalyst (specific, dateable event)")
    account_risk_pct = click.prompt(
        "Account risk % (e.g. 1.5 means risk 1.5% of account on this trade)",
        type=click.FloatRange(0.1, 5.0),
        default=1.0,
    )

    click.echo("")
    try:
        pick_id, entry_price = add_pick(
            ticker=ticker, direction=direction, target=target, stop=stop,
            conviction=conviction, horizon=horizon, sector=sector,
            thesis=thesis, catalyst=catalyst,
            account_risk_pct=account_risk_pct,
        )
    except ValueError as e:
        click.echo(f"[error] {e}", err=True)
        sys.exit(1)

    confirm = click.confirm(
        f"\nAdd {direction.upper()} {ticker} @ ${entry_price:.2f}?", default=True
    )
    if not confirm:
        from scripts.picks import _load_ledger, _save_ledger
        df = _load_ledger()
        _save_ledger(df[df["pick_id"] != pick_id])
        click.echo("Cancelled.")
        return

    click.echo(f"\n✅ Pick added. ID: {pick_id}")
    click.echo(f"   {direction.title()} {ticker} @ ${entry_price:.2f} → target ${target:.2f} / stop ${stop:.2f}")


@picks.command("close")
@click.argument("pick_id")
def picks_close(pick_id: str):
    """Close an open pick. PICK_ID is the 8-char ID from 'picks list'."""
    import pandas as pd
    from scripts.picks import close_pick, VALID_REASONS, _load_ledger

    df      = _load_ledger()
    matches = df[(df["pick_id"].str.startswith(pick_id)) & (df["status"] == "open")]
    if matches.empty:
        click.echo(f"[error] No open pick found with ID starting with '{pick_id}'", err=True)
        sys.exit(1)

    row = matches.iloc[0]
    click.echo(
        f"\nClosing: {row['direction'].title()} {row['ticker']} | "
        f"Entry ${float(row['entry_price']):.2f} | Current ${float(row['current_price']):.2f}"
    )

    reason      = click.prompt("Close reason", type=click.Choice(VALID_REASONS, case_sensitive=False))
    use_current = click.confirm(f"Use current price ${float(row['current_price']):.2f}?", default=True)
    close_price = float(row["current_price"]) if use_current else click.prompt("Close price", type=float)

    result = close_pick(pick_id, reason, close_price)
    pnl    = result["pnl"]
    emoji  = "✅" if isinstance(pnl, float) and pnl > 0 else "❌"
    click.echo(f"\n{emoji} Closed {result['ticker']}: {result['status']} | P&L: {pnl:+.1f}%")


@picks.command("list")
def picks_list():
    """Print all open picks with live P&L."""
    import pandas as pd
    from scripts.picks import get_open_picks, refresh_prices

    click.echo("\nRefreshing prices …")
    refresh_prices()
    open_picks = get_open_picks()

    if open_picks.empty:
        click.echo("No open picks.")
        return

    click.echo(
        f"\n{'ID':<10} {'Ticker':<8} {'Dir':<6} {'Entry':>8} {'Current':>8} "
        f"{'P&L %':>8} {'Days':>5} {'Conv':>5}  Sector"
    )
    click.echo("─" * 82)
    for _, row in open_picks.iterrows():
        pnl  = row["live_pnl_pct"]
        pnl_str = f"{pnl:+.1f}%" if pd.notna(pnl) else "N/A"
        days = int(row["days_held"]) if pd.notna(row.get("days_held")) else "–"
        click.echo(
            f"{row['pick_id']:<10} {row['ticker']:<8} {row['direction'].title():<6} "
            f"${float(row['entry_price']):>7.2f} ${float(row['current_price']):>7.2f} "
            f"{pnl_str:>8} {str(days):>5} {int(row['conviction']):>4}/5  {row['sector']}"
        )


@picks.command("record")
def picks_record():
    """Print overall track record stats."""
    from scripts.picks import compute_track_record

    stats = compute_track_record()
    click.echo("\n── Track Record ─────────────────────────────────────────────")
    click.echo(f"Total picks : {stats['total_picks']}  ({stats['open_picks']} open, {stats['closed_picks']} closed)")

    if stats["closed_picks"] == 0:
        click.echo("Track record builds as picks are closed.")
        return

    wr = f"{stats['win_rate']*100:.0f}%"          if stats["win_rate"]        is not None else "N/A"
    aw = f"{stats['avg_winner']:+.1f}%"           if stats["avg_winner"]      is not None else "N/A"
    al = f"{stats['avg_loser']:+.1f}%"            if stats["avg_loser"]       is not None else "N/A"
    hd = f"{stats['avg_holding_days']:.0f} days"  if stats["avg_holding_days"] is not None else "N/A"

    click.echo(f"Win rate    : {wr}")
    click.echo(f"Avg winner  : {aw}")
    click.echo(f"Avg loser   : {al}")
    click.echo(f"Avg hold    : {hd}")
    click.echo(f"Best pick   : {stats['best_pick'] or 'N/A'}")
    click.echo(f"Worst pick  : {stats['worst_pick'] or 'N/A'}")

    if stats["by_sector"]:
        click.echo("\nBy sector:")
        for sector, s in sorted(stats["by_sector"].items()):
            click.echo(f"  {sector:<26} {s['picks']} pick(s)   {s['win_rate']*100:.0f}% win rate")


# ─────────────────────────────────────────────────────────────────────────────
# Newsletter commands
# ─────────────────────────────────────────────────────────────────────────────

@cli.group()
def newsletter():
    """Generate and preview the public newsletter."""
    pass


@newsletter.command("generate")
@click.option("--week", default=None,
              help="ISO week string, e.g. 2026-W21. Defaults to most recent entry.")
def newsletter_generate(week: str | None):
    """Generate the newsletter for a given week (defaults to most recently generated entry)."""
    from scripts.newsletter import export_newsletter
    from scripts.new_week import _target_week

    if week is None:
        today  = date.today()
        monday, sunday, iso_year, iso_week = _target_week(today)
        week = f"{iso_year}-W{iso_week:02d}"

    click.echo(f"\nGenerating newsletter for {week} …")
    try:
        out = export_newsletter(week)
        click.echo(f"✅ Newsletter saved: {out}")
        click.echo(f"\nTo preview: python cli.py newsletter preview --week {week}")
    except FileNotFoundError as e:
        click.echo(f"[error] {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"[error] {e}", err=True)
        sys.exit(1)


@newsletter.command("preview")
@click.option("--week", default=None,
              help="ISO week string. Defaults to most recently generated entry.")
def newsletter_preview(week: str | None):
    """Print the newsletter to the terminal (generates it first if needed)."""
    from scripts.newsletter import generate_newsletter
    from scripts.new_week import _target_week

    if week is None:
        today  = date.today()
        monday, sunday, iso_year, iso_week = _target_week(today)
        week = f"{iso_year}-W{iso_week:02d}"

    try:
        content = generate_newsletter(week)
        click.echo("\n" + "═" * 70)
        click.echo(content)
        click.echo("═" * 70)
    except FileNotFoundError as e:
        click.echo(f"[error] {e}", err=True)
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Watchlist commands
# ─────────────────────────────────────────────────────────────────────────────

@cli.group()
def watch():
    """Manage your research watchlist."""
    pass


@watch.command("list")
def watch_list():
    """Show all tickers on the watchlist."""
    from scripts.research import load_watchlist
    wl = load_watchlist()
    click.echo(f"\nWatchlist ({len(wl)} tickers):")
    for ticker, sector in sorted(wl.items()):
        click.echo(f"  {ticker:<8}  {sector}")


@watch.command("add")
@click.argument("ticker")
@click.argument("sector")
def watch_add(ticker: str, sector: str):
    """Add TICKER to the watchlist under SECTOR."""
    from scripts.research import load_watchlist, save_watchlist
    from scripts.config import SECTORS

    ticker = ticker.upper().strip()
    sector_match = next((s for s in SECTORS if s.lower() == sector.lower()), None)
    if sector_match is None:
        click.echo(f"[error] Sector must be one of: {', '.join(SECTORS)}", err=True)
        sys.exit(1)

    wl = load_watchlist()
    wl[ticker] = sector_match
    save_watchlist(wl)
    click.echo(f"✅ Added {ticker} ({sector_match}) to watchlist.")


@watch.command("remove")
@click.argument("ticker")
def watch_remove(ticker: str):
    """Remove TICKER from the watchlist."""
    from scripts.research import load_watchlist, save_watchlist

    ticker = ticker.upper().strip()
    wl     = load_watchlist()
    if ticker not in wl:
        click.echo(f"[error] {ticker} is not on the watchlist.", err=True)
        sys.exit(1)
    del wl[ticker]
    save_watchlist(wl)
    click.echo(f"✅ Removed {ticker} from watchlist.")


# ─────────────────────────────────────────────────────────────────────────────
# Site commands
# ─────────────────────────────────────────────────────────────────────────────

@cli.group()
def site():
    """Build and preview the static website."""
    pass


@site.command("build")
@click.option("--week", default=None,
              help="ISO week string, e.g. 2026-W21. Defaults to current week.")
@click.option("--open", "open_browser", is_flag=True, default=False,
              help="Open the site in your default browser after building.")
def site_build(week: str | None, open_browser: bool):
    """Generate website/index.html from the current journal entry and picks ledger."""
    from scripts.build_site import build_site
    import subprocess

    click.echo(f"\nBuilding site{f' for {week}' if week else ''} …")
    try:
        out = build_site(week_str=week)
        click.echo(f"✅ Site built: {out}")
        click.echo(f"\nTo open: open \"{out}\"")
        if open_browser:
            subprocess.run(["open", str(out)], check=False)
    except Exception as e:
        click.echo(f"[error] {e}", err=True)
        raise SystemExit(1)


@site.command("open")
def site_open():
    """Open website/index.html in the default browser (builds first if missing)."""
    import subprocess
    from scripts.build_site import build_site, WEBSITE_DIR

    out = WEBSITE_DIR / "index.html"
    if not out.exists():
        click.echo("Site not built yet — building now …")
        out = build_site()

    click.echo(f"Opening {out} …")
    subprocess.run(["open", str(out)], check=False)


@site.command("watch")
@click.option("--interval", default=60, show_default=True,
              help="Seconds between refresh+rebuild cycles.")
@click.option("--open", "open_browser", is_flag=True, default=True,
              help="Open browser on first build.")
def site_watch(interval: int, open_browser: bool):
    """
    Live-refresh loop: refresh prices + rebuild site every N seconds.

    The site HTML auto-reloads every 60 s, so keeping this running gives
    near-real-time P&L. Stop with Ctrl-C.

    Usage:  python cli.py site watch
    """
    import subprocess, time
    from scripts.build_site import build_site
    from scripts.picks import refresh_prices

    click.echo(f"\n🔄  The Reins Report — live watch mode (interval: {interval}s)")
    click.echo("    Press Ctrl-C to stop.\n")

    first = True
    while True:
        ts = click.style(date.today().isoformat(), fg="cyan")
        click.echo(f"[{ts}] Refreshing prices …", nl=False)
        try:
            refresh_prices()
            click.echo(" done.")
        except Exception as e:
            click.echo(f" [warn] {e}")

        click.echo(f"[{ts}] Rebuilding site …", nl=False)
        try:
            out = build_site()
            click.echo(f" ✅ {out.name}")
        except Exception as e:
            click.echo(f" [error] {e}")

        if first and open_browser:
            subprocess.run(["open", str(out)], check=False)
            first = False

        click.echo(f"    Next refresh in {interval}s …\n")
        time.sleep(interval)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
