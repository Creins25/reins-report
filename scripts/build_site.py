"""
Static site builder — professional editorial design with options support.

Generates website/index.html with:
  · Options pick cards (Greeks, premium, break-even, IV, leverage)
  · SVG sparkline charts per pick (30-day price + entry/stop/target lines)
  · Auto-generated market narrative from scoreboard data
  · Barron's-style white editorial layout

Run:  python cli.py site build
Open: python cli.py site open
"""

import re
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

_PROJECT_ROOT   = Path(__file__).resolve().parent.parent
WEBSITE_DIR     = _PROJECT_ROOT / "website"
ENTRIES_DIR     = _PROJECT_ROOT / "entries"
NEWSLETTERS_DIR = _PROJECT_ROOT / "newsletters"

# ── CSS ────────────────────────────────────────────────────────────────────────

CSS = """
:root {
  --bg:           #ffffff;
  --bg-alt:       #f7f7f5;
  --bg-stripe:    #fafaf8;
  --bg-header:    #0d1f35;
  --border:       #e3e3e0;
  --border-mid:   #ccccca;
  --text:         #111111;
  --text-sec:     #3a3a3a;
  --text-muted:   #6b6b6b;
  --text-light:   #aaaaaa;
  --gold:         #b8960c;
  --gold-bg:      #fdf8e8;
  --gold-border:  #e2cb6a;
  --navy:         #0d1f35;
  --gain:         #15803d;
  --gain-bg:      #f0fdf4;
  --gain-border:  #bbf7d0;
  --loss:         #b91c1c;
  --loss-bg:      #fef2f2;
  --loss-border:  #fecaca;
  --blue:         #1d4ed8;
  --blue-bg:      #eff6ff;
  --blue-border:  #bfdbfe;
  --orange:       #c2410c;
  --orange-bg:    #fff7ed;
  --orange-border:#fed7aa;
  --purple:       #7c3aed;
  --purple-bg:    #f5f3ff;
  --purple-border:#ddd6fe;
  --radius:       4px;
  --shadow-sm:    0 1px 4px rgba(0,0,0,0.07);
  --shadow:       0 2px 10px rgba(0,0,0,0.09);
}

* { margin:0; padding:0; box-sizing:border-box; }
html { -webkit-font-smoothing:antialiased; }
body {
  background: var(--bg-alt);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
  font-size: 14px;
  line-height: 1.65;
}
a { color:var(--gold); text-decoration:none; }
a:hover { text-decoration:underline; }

/* ── Masthead ──────────────────────────────────────────────── */
.masthead { background:var(--bg-header); border-bottom:3px solid var(--gold); }
.masthead-inner {
  max-width:1100px; margin:0 auto; padding:22px 32px;
  display:flex; align-items:flex-end; justify-content:space-between;
  gap:16px; flex-wrap:wrap;
}
.pub-eyebrow { font-size:9.5px; font-weight:800; letter-spacing:.22em;
  text-transform:uppercase; color:var(--gold); margin-bottom:5px; }
.pub-name { font-size:27px; font-weight:800; color:#fff;
  font-family:Georgia,'Times New Roman',serif; letter-spacing:-.3px; }
.pub-tagline { font-size:12px; color:rgba(255,255,255,.45); margin-top:3px; font-style:italic; }
.masthead-right { text-align:right; }
.pub-week { font-size:19px; font-weight:700; color:#fff;
  font-family:Georgia,serif; margin-bottom:3px; }
.pub-date { font-size:12px; color:rgba(255,255,255,.5); }

/* ── Ticker strip ──────────────────────────────────────────── */
.ticker-strip {
  background:#fff; border-bottom:1px solid var(--border);
  overflow:hidden; height:33px; display:flex; align-items:center;
}
.ticker-track { display:flex; animation:scroll-ticker 50s linear infinite; white-space:nowrap; }
@keyframes scroll-ticker { 0%{transform:translateX(0)} 100%{transform:translateX(-50%)} }
.ticker-item {
  display:inline-flex; align-items:center; gap:7px; padding:0 22px;
  font-size:11.5px; font-family:'SF Mono','Fira Code',Consolas,monospace;
  border-right:1px solid var(--border); color:var(--text-muted);
}
.t-sym { font-weight:700; color:var(--text); letter-spacing:.03em; }
.t-val { color:var(--text); }
.t-chg.up   { color:var(--gain); }
.t-chg.down { color:var(--loss); }
.t-chg.flat { color:var(--text-muted); }

/* ── Page wrapper ──────────────────────────────────────────── */
.page-wrap { max-width:1100px; margin:0 auto; padding:36px 24px 90px; }
section { margin-bottom:52px; }
.section-label {
  font-size:9.5px; font-weight:800; letter-spacing:.22em;
  text-transform:uppercase; color:var(--text-muted);
  padding-bottom:9px; border-bottom:2px solid var(--gold); margin-bottom:22px;
}

/* ── Market overview ───────────────────────────────────────── */
.market-overview {
  background:#fff; border:1px solid var(--border);
  border-left:5px solid var(--gold); border-radius:var(--radius);
  padding:26px 30px; margin-bottom:28px; box-shadow:var(--shadow-sm);
}
.overview-kicker { font-size:9.5px; font-weight:800; letter-spacing:.2em;
  text-transform:uppercase; color:var(--gold); margin-bottom:9px; }
.overview-theme { font-size:21px; font-weight:700; color:var(--navy);
  line-height:1.3; margin-bottom:13px; font-family:Georgia,serif; }
.overview-body { font-size:13.5px; color:var(--text-sec); line-height:1.75; }
.overview-body p { margin-bottom:10px; }
.overview-body p:last-child { margin-bottom:0; }

/* ── About panel ───────────────────────────────────────────── */
.about-panel {
  background:var(--bg-header); border-radius:var(--radius);
  padding:20px 28px; margin-bottom:44px;
  display:flex; align-items:center; gap:22px; box-shadow:var(--shadow-sm); flex-wrap:wrap;
}
.about-avatar {
  width:50px; height:50px; background:var(--gold); border-radius:50%;
  display:flex; align-items:center; justify-content:center;
  font-size:20px; font-weight:900; color:var(--bg-header); flex-shrink:0;
  font-family:Georgia,serif;
}
.about-body { flex:1; min-width:200px; }
.about-name { font-size:14px; font-weight:700; color:#fff; margin-bottom:4px; }
.about-desc { font-size:12px; color:rgba(255,255,255,.6); line-height:1.55; }
.about-tags { display:flex; gap:7px; margin-top:10px; flex-wrap:wrap; }
.about-tag { font-size:9.5px; font-weight:700; letter-spacing:.06em;
  text-transform:uppercase; padding:3px 10px;
  border:1px solid rgba(184,150,12,.45); border-radius:20px; color:var(--gold); }

/* ── Track record ──────────────────────────────────────────── */
.stats-row { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; }
.stat-card { background:#fff; border:1px solid var(--border);
  border-radius:var(--radius); padding:18px 16px; box-shadow:var(--shadow-sm); }
.stat-val { font-size:30px; font-weight:800; line-height:1; margin-bottom:6px;
  font-family:Georgia,serif; }
.stat-val.gain  { color:var(--gain); }
.stat-val.loss  { color:var(--loss); }
.stat-val.navy  { color:var(--navy); }
.stat-val.muted { color:var(--text-muted); }
.stat-val.gold  { color:var(--gold); }
.stat-lbl { font-size:9.5px; font-weight:800; letter-spacing:.14em;
  text-transform:uppercase; color:var(--text-muted); }

/* ── Pick cards ────────────────────────────────────────────── */
.picks-list { display:flex; flex-direction:column; gap:20px; }
.pick-card { background:#fff; border:1px solid var(--border);
  border-radius:var(--radius); box-shadow:var(--shadow-sm); overflow:hidden; }
.pick-card::before { content:''; display:block; height:4px; }
.pick-card.long::before  { background:linear-gradient(90deg,#15803d,#4ade80); }
.pick-card.short::before { background:linear-gradient(90deg,#b91c1c,#f87171); }

.pick-header {
  display:flex; align-items:center; justify-content:space-between;
  padding:16px 22px 14px; border-bottom:1px solid var(--border);
  background:var(--bg-alt); flex-wrap:wrap; gap:10px;
}
.pick-title-group { display:flex; align-items:baseline; gap:12px; }
.pick-ticker { font-size:24px; font-weight:800; color:var(--navy);
  font-family:Georgia,serif; letter-spacing:-.5px; }
.pick-sub { font-size:12px; color:var(--text-muted); }
.pick-badges { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }

.badge { display:inline-block; font-size:9.5px; font-weight:800;
  letter-spacing:.12em; text-transform:uppercase; padding:4px 11px; border-radius:3px; }
.b-long    { background:var(--gain-bg);   color:var(--gain);   border:1px solid var(--gain-border); }
.b-short   { background:var(--loss-bg);   color:var(--loss);   border:1px solid var(--loss-border); }
.b-call    { background:var(--purple-bg); color:var(--purple); border:1px solid var(--purple-border); }
.b-put     { background:var(--loss-bg);   color:var(--loss);   border:1px solid var(--loss-border); }
.b-equity  { background:var(--blue-bg);   color:var(--blue);   border:1px solid var(--blue-border); }
.b-high    { background:var(--navy);      color:#fff; }
.b-above   { background:var(--gain-bg);   color:var(--gain);   border:1px solid var(--gain-border); }
.b-moderate{ background:var(--blue-bg);   color:var(--blue);   border:1px solid var(--blue-border); }
.b-spec    { background:var(--orange-bg); color:var(--orange); border:1px solid var(--orange-border); }
.b-explore { background:var(--bg-alt);    color:var(--text-muted); border:1px solid var(--border); }

.pick-body { padding:18px 22px 20px; }

/* Equity metrics row */
.pick-metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:18px; }
.metric label { display:block; font-size:9px; font-weight:800; letter-spacing:.14em;
  text-transform:uppercase; color:var(--text-muted); margin-bottom:3px; }
.metric-val { font-size:15.5px; font-weight:700;
  font-family:'SF Mono',Consolas,monospace; color:var(--text);
  display:flex; align-items:center; gap:5px; }
.metric-val.gain { color:var(--gain); }
.metric-val.loss { color:var(--loss); }

.pnl-pill { font-size:10.5px; font-weight:700; padding:1px 6px; border-radius:3px;
  font-family:'SF Mono',Consolas,monospace; }
.pnl-pill.gain { background:var(--gain-bg); color:var(--gain); }
.pnl-pill.loss { background:var(--loss-bg); color:var(--loss); }
.pnl-pill.flat { background:var(--bg-alt);  color:var(--text-muted); }

/* Progress bar */
.pick-progress { margin-bottom:16px; }
.progress-row { display:flex; justify-content:space-between;
  font-size:10.5px; font-family:'SF Mono',Consolas,monospace; margin-bottom:5px; color:var(--text-muted); }
.progress-row .p-stop   { color:var(--loss); }
.progress-row .p-rr     { font-weight:700; }
.progress-row .p-target { color:var(--gain); }
.progress-track { height:5px; background:var(--bg-alt); border:1px solid var(--border);
  border-radius:3px; overflow:hidden; }
.progress-fill { height:100%; border-radius:3px; transition:width .5s ease; }
.progress-fill.gain { background:linear-gradient(90deg,#86efac,var(--gain)); }
.progress-fill.loss { background:linear-gradient(90deg,var(--loss),#fca5a5); }
.progress-fill.flat { background:var(--border-mid); }

/* Options block */
.options-block {
  background:var(--purple-bg); border:1px solid var(--purple-border);
  border-radius:var(--radius); padding:14px 18px; margin-bottom:16px;
}
.options-title {
  font-size:9px; font-weight:800; letter-spacing:.18em;
  text-transform:uppercase; color:var(--purple); margin-bottom:12px;
}
.options-row { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:12px; }
.opt-item label { display:block; font-size:9px; font-weight:700; letter-spacing:.1em;
  text-transform:uppercase; color:rgba(124,58,237,.6); margin-bottom:2px; }
.opt-item .opt-val { font-size:14px; font-weight:700;
  font-family:'SF Mono',Consolas,monospace; color:var(--navy); }
.opt-item .opt-val.purple { color:var(--purple); }
.opt-item .opt-val.loss   { color:var(--loss); }
.opt-item .opt-val.gain   { color:var(--gain); }

/* Greeks table */
.greeks-row { display:flex; gap:0; border:1px solid var(--purple-border);
  border-radius:var(--radius); overflow:hidden; }
.greek-cell { flex:1; padding:8px 10px; border-right:1px solid var(--purple-border);
  background:#fff; text-align:center; }
.greek-cell:last-child { border-right:none; }
.greek-sym { font-size:12px; font-weight:700; color:var(--purple);
  font-family:Georgia,serif; display:block; }
.greek-name { font-size:8.5px; font-weight:600; letter-spacing:.08em;
  text-transform:uppercase; color:rgba(124,58,237,.5); display:block; margin-bottom:3px; }
.greek-val { font-size:12px; font-weight:700;
  font-family:'SF Mono',Consolas,monospace; color:var(--navy); }
.greek-val.neg { color:var(--loss); }
.greek-val.pos { color:var(--gain); }

/* Sizing + meta */
.pick-sizing-row { display:flex; gap:22px; padding:10px 0;
  border-top:1px solid var(--border); border-bottom:1px solid var(--border);
  margin-bottom:14px; font-size:11.5px; color:var(--text-muted); flex-wrap:wrap; }
.pick-sizing-row strong { color:var(--navy); }
.size-pill { background:var(--gold-bg); border:1px solid var(--gold-border);
  color:var(--gold); font-size:10px; font-weight:800; letter-spacing:.06em;
  padding:2px 8px; border-radius:3px; text-transform:uppercase; }

/* Thesis */
.pick-thesis { font-size:13px; color:var(--text-sec); line-height:1.7; }
.pick-catalyst { margin-top:9px; font-size:11.5px; font-weight:600; color:var(--navy); }
.pick-catalyst::before { content:'⚡ '; }

/* Entry timing */
.entry-timing {
  margin-top:14px; padding:12px 16px;
  background:#fffbeb; border:1px solid #fde68a;
  border-left:4px solid #d97706; border-radius:var(--radius);
}
.entry-timing-title {
  font-size:9px; font-weight:800; letter-spacing:.18em; text-transform:uppercase;
  color:#92400e; margin-bottom:5px;
}
.entry-timing-body { font-size:12.5px; color:#78350f; line-height:1.65; }

/* Sparkline chart */
.pick-chart {
  margin-top:16px; padding-top:16px; border-top:1px solid var(--border);
}
.chart-label { font-size:9px; font-weight:800; letter-spacing:.16em;
  text-transform:uppercase; color:var(--text-light); margin-bottom:8px; }
.chart-wrap { position:relative; }
.chart-legend { display:flex; gap:16px; margin-top:6px; font-size:10.5px; }
.legend-item { display:flex; align-items:center; gap:4px; color:var(--text-muted); }
.legend-dot { width:10px; height:2px; border-radius:1px; }

/* ── Tables ────────────────────────────────────────────────── */
.table-wrap { background:#fff; border:1px solid var(--border);
  border-radius:var(--radius); overflow-x:auto; box-shadow:var(--shadow-sm); }
table { width:100%; border-collapse:collapse; }
thead tr { border-bottom:2px solid var(--border-mid); }
thead th { padding:10px 14px; text-align:left; font-size:9px; font-weight:800;
  letter-spacing:.16em; text-transform:uppercase; color:var(--text-muted);
  background:var(--bg-alt); white-space:nowrap; }
thead th.r { text-align:right; }
tbody tr { border-bottom:1px solid var(--border); transition:background .12s; }
tbody tr:last-child { border-bottom:none; }
tbody tr:hover { background:var(--bg-stripe); }
tbody td { padding:9px 14px; font-size:12.5px;
  font-family:'SF Mono',Consolas,monospace; color:var(--text); }
tbody td.nm  { font-family:inherit; font-weight:600; font-size:13px; }
tbody td.mu  { color:var(--text-muted); font-family:inherit; font-size:12px; }
tbody td.r   { text-align:right; }
tbody td.sh  { background:var(--gold-bg); color:var(--gold); font-family:inherit;
  font-size:9px; font-weight:800; letter-spacing:.16em; text-transform:uppercase;
  padding:6px 14px; border-bottom:1px solid var(--gold-border); }
.up   { color:var(--gain); }
.down { color:var(--loss); }
.flat { color:var(--text-muted); }

/* ── Prose ─────────────────────────────────────────────────── */
.prose-card { background:#fff; border:1px solid var(--border);
  border-radius:var(--radius); padding:28px 32px; box-shadow:var(--shadow-sm);
  font-size:14px; line-height:1.82; color:var(--text-sec); }
.prose-card h3 { font-size:9.5px; font-weight:800; letter-spacing:.22em;
  text-transform:uppercase; color:var(--gold); margin:26px 0 10px;
  padding-bottom:7px; border-bottom:1px solid var(--border); }
.prose-card h3:first-child { margin-top:0; }
.prose-card p  { margin-bottom:13px; }
.prose-card em { color:var(--text-muted); font-style:italic; }
.prose-card strong { color:var(--text); font-weight:600; }
.prose-card ul { padding-left:20px; margin-bottom:13px; }
.prose-card li { margin-bottom:4px; }

/* ── Footer ────────────────────────────────────────────────── */
footer { background:var(--bg-header); color:rgba(255,255,255,.38);
  text-align:center; padding:30px 24px; font-size:11px; line-height:1.8; margin-top:50px; }
.footer-inner { max-width:700px; margin:0 auto; }
footer .disclaimer { margin-bottom:10px; }
footer .pub-credit { font-size:10px; color:rgba(255,255,255,.2); letter-spacing:.05em; }

/* ── Live indicator ────────────────────────────────────────── */
#live-indicator { font-size:10.5px; letter-spacing:.07em; }
.live-pulse {
  display:inline-block; width:7px; height:7px; border-radius:50%;
  background:#4ade80; margin-right:5px; vertical-align:middle;
  animation:pulse-green 2s ease-in-out infinite;
}
@keyframes pulse-green {
  0%,100% { opacity:1; transform:scale(1); }
  50%      { opacity:.35; transform:scale(.7); }
}

/* ── Responsive ────────────────────────────────────────────── */
@media (max-width:700px) {
  .masthead-inner  { flex-direction:column; gap:10px; }
  .masthead-right  { text-align:left; }
  .page-wrap       { padding:20px 14px 60px; }
  .pick-metrics    { grid-template-columns:repeat(2,1fr); }
  .options-row     { grid-template-columns:repeat(2,1fr); }
  .about-panel     { flex-direction:column; }
  .stats-row       { grid-template-columns:repeat(2,1fr); }
  .greeks-row      { flex-wrap:wrap; }
  .greek-cell      { flex:1 1 40%; }
}
"""

# ── Helpers ────────────────────────────────────────────────────────────────────

def _pnl_class(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "flat"
    return "gain" if float(val) > 0 else ("loss" if float(val) < 0 else "flat")

def _pnl_str(val, suffix="%") -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    return f"{float(val):+.1f}{suffix}"

def _chg_class(s: str) -> str:
    s = s.strip()
    if s in ("N/A", "—", ""):
        return "flat"
    return "up" if s.startswith("+") else ("down" if s.startswith("-") else "flat")

def _range_pct(entry, current, stop, target, direction="long") -> float:
    try:
        e, c, s, t = float(entry), float(current), float(stop), float(target)
        if direction == "short":
            total, moved = e - s, e - c
        else:
            total, moved = t - e, c - e
        return max(0.0, min(100.0, moved / total * 100)) if total > 0 else 0.0
    except Exception:
        return 0.0

def _risk_reward(entry, stop, target, direction="long") -> tuple[str, float]:
    try:
        e, s, t = float(entry), float(stop), float(target)
        risk   = (e - s) if direction == "long" else (s - e)
        reward = (t - e) if direction == "long" else (e - t)
        if risk <= 0:
            return "R/R —", 0.0
        ratio = reward / risk
        return f"R/R {ratio:.1f}:1", ratio
    except Exception:
        return "R/R —", 0.0

def _conviction_badge(n) -> tuple[str, str]:
    try:
        n = int(n)
    except Exception:
        return "—", "b-explore"
    if n >= 5: return "High Conviction", "b-high"
    if n >= 4: return "Strong",          "b-above"
    if n >= 3: return "Moderate",        "b-moderate"
    if n >= 2: return "Speculative",     "b-spec"
    return "Exploratory", "b-explore"

def _safe(v, decimals=2, prefix="$") -> str:
    try:
        return f"{prefix}{float(v):,.{decimals}f}"
    except Exception:
        return "—"

def _safe_f(v, decimals=3, fallback="—") -> str:
    try:
        return f"{float(v):.{decimals}f}"
    except Exception:
        return fallback

# ── Sparkline chart ────────────────────────────────────────────────────────────

def _build_sparkline(ticker: str, entry: float, stop: float, target: float,
                     is_option: bool = False) -> str:
    """
    Generate an inline SVG price chart from 30-day yfinance history.
    Shows price line + entry (blue), stop (red dashed), target (green dashed) lines.
    """
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="30d")["Close"].dropna()
        prices = [float(p) for p in hist.values]
        if len(prices) < 5:
            return ""
    except Exception:
        return ""

    W, H, PX, PY = 560, 120, 14, 12

    # Include stop/target in the Y range so they're always visible
    all_vals  = prices + [stop, target, entry]
    mn = min(all_vals) * 0.995
    mx = max(all_vals) * 1.005
    rng = mx - mn if mx != mn else 1.0

    def tx(i):   return PX + (i / max(len(prices) - 1, 1)) * (W - 2 * PX)
    def ty(p):   return H - PY - ((p - mn) / rng) * (H - 2 * PY)

    entry_y  = ty(entry)
    stop_y   = ty(stop)
    target_y = ty(target)

    # Build polyline points
    pts = " ".join(f"{tx(i):.1f},{ty(p):.1f}" for i, p in enumerate(prices))

    # Gradient fill under curve
    last_x  = tx(len(prices) - 1)
    last_y  = ty(prices[-1])
    fill_pts = f"{tx(0):.1f},{H-PY} {pts} {last_x:.1f},{H-PY}"

    gain_color = "#15803d"
    loss_color = "#b91c1c"
    line_color = "#0d1f35"

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {W} {H}" style="width:100%;height:100px;display:block;overflow:visible">
  <defs>
    <linearGradient id="fill-{ticker}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{line_color}" stop-opacity="0.07"/>
      <stop offset="100%" stop-color="{line_color}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <!-- fill under curve -->
  <polygon points="{fill_pts}" fill="url(#fill-{ticker})"/>
  <!-- Target line -->
  <line x1="{PX}" y1="{target_y:.1f}" x2="{W-PX}" y2="{target_y:.1f}"
        stroke="{gain_color}" stroke-width="1.2" stroke-dasharray="5,3" opacity="0.7"/>
  <text x="{W-PX+2}" y="{target_y:.1f}" dy="4" font-size="9" fill="{gain_color}"
        font-family="monospace" font-weight="700">${target:.0f}</text>
  <!-- Entry line -->
  <line x1="{PX}" y1="{entry_y:.1f}" x2="{W-PX}" y2="{entry_y:.1f}"
        stroke="#1d4ed8" stroke-width="1" stroke-dasharray="3,3" opacity="0.6"/>
  <text x="{W-PX+2}" y="{entry_y:.1f}" dy="4" font-size="9" fill="#1d4ed8"
        font-family="monospace">${entry:.0f}</text>
  <!-- Stop line -->
  <line x1="{PX}" y1="{stop_y:.1f}" x2="{W-PX}" y2="{stop_y:.1f}"
        stroke="{loss_color}" stroke-width="1.2" stroke-dasharray="5,3" opacity="0.7"/>
  <text x="{W-PX+2}" y="{stop_y:.1f}" dy="4" font-size="9" fill="{loss_color}"
        font-family="monospace">${stop:.0f}</text>
  <!-- Price line -->
  <polyline points="{pts}" fill="none" stroke="{line_color}"
            stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
  <!-- Last price dot -->
  <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3.5" fill="{line_color}"/>
</svg>"""

    return f"""
    <div class="pick-chart">
      <div class="chart-label">30-Day Price — {ticker}</div>
      <div class="chart-wrap">{svg}</div>
      <div class="chart-legend">
        <span class="legend-item"><span class="legend-dot" style="background:#15803d;height:2px;border-top:1px dashed #15803d;background:none;border-color:#15803d"></span>Target ${target:.0f}</span>
        <span class="legend-item"><span class="legend-dot" style="border-top:1px dashed #1d4ed8;background:none"></span>Entry ${entry:.0f}</span>
        <span class="legend-item"><span class="legend-dot" style="border-top:1px dashed #b91c1c;background:none"></span>Stop ${stop:.0f}</span>
      </div>
    </div>"""

# ── Auto market narrative ──────────────────────────────────────────────────────

def _auto_narrative(scoreboard_rows: list[dict]) -> str:
    """
    Auto-generate a professional 3-paragraph market narrative from scoreboard data.
    Used when the user hasn't yet written the Narrative section in the journal entry.
    """
    data = {r['name'].strip('*').strip(): r for r in scoreboard_rows}

    def v(name):
        return data.get(name, {}).get('close', 'N/A')
    def w(name):
        return data.get(name, {}).get('chg_1w', 'N/A')
    def y(name):
        return data.get(name, {}).get('chg_ytd', 'N/A')

    spx_w = w('SPX');  spx_v = v('SPX');  spx_y = y('SPX')
    ndx_w = w('NDX');  ndx_v = v('NDX');  ndx_y = y('NDX')
    rut_w = w('RUT');  rut_v = v('RUT')
    vix_v = v('VIX');  vix_w = w('VIX')
    us10y = v('US10Y'); us2y = v('US2Y'); spread = v('2s10s')
    move  = v('MOVE');  move_w = w('MOVE')
    wti_v = v('WTI');   wti_w = w('WTI');  wti_y = y('WTI')
    gold_v = v('Gold'); gold_w = w('Gold')
    xlf_y = y('XLF');  xlk_y = y('XLK')
    dxy_v = v('DXY');  dxy_w = w('DXY')

    # Regime classification
    try:
        vix_num = float(str(vix_v).replace('%',''))
        if vix_num < 15:   vol_regime = "an exceptionally low volatility"
        elif vix_num < 20: vol_regime = "a subdued volatility"
        elif vix_num < 28: vol_regime = "a moderately elevated volatility"
        else:              vol_regime = "a high volatility"
    except Exception:
        vol_regime = "a normal volatility"

    spx_dir  = "had a solid week" if str(spx_w).startswith('+') else "pulled back"
    ndx_move = "led the market again" if str(ndx_w).startswith('+') else "lagged the broader tape"
    rut_read = "breadth is expanding beyond the mega caps" if str(rut_w).startswith('+') else "small caps are still lagging the large cap leaders"
    wti_read = "sold off hard" if str(wti_w).startswith('-') else "pushed higher"
    gold_read = "softened" if str(gold_w).startswith('-') else "moved up"

    p1 = (
        f"Stocks {spx_dir} this week. The S&P 500 closed at {spx_v}, up {spx_w} on the week "
        f"and {spx_y} for the year. The Nasdaq {ndx_move} at {ndx_v} ({ndx_w} on the week, "
        f"{ndx_y} year to date), which tells you technology is still the engine driving this "
        f"market in 2026. The Russell 2000 moved {rut_w} this week, which means {rut_read}. "
        f"That is a good sign. When small caps participate it usually means the rally has real legs."
    )

    p2 = (
        f"The VIX closed at {vix_v}, moving {vix_w} on the week. We are in {vol_regime} environment "
        f"right now. The MOVE index, which measures bond market volatility, came in at {move} "
        f"({move_w} this week), so both stock and rates volatility are calm. That is the ideal "
        f"setup for the options positions we are holding. The 10 year Treasury is sitting at {us10y} "
        f"and the yield curve spread between 2s and 10s is {spread}. The curve has been steepening "
        f"which is genuinely good news for bank earnings and net interest margins."
    )

    p3 = (
        f"On the commodities and currency side, WTI crude {wti_read} to {wti_v} this week ({wti_w}, "
        f"{wti_y} year to date). Oil pulling back takes one inflation risk off the table and makes "
        f"it easier for the Fed to hold rates steady. Gold {gold_read} to {gold_v} ({gold_w} this "
        f"week), which fits the risk-on mood where people are not rushing to buy safe havens. "
        f"The dollar index is at {dxy_v} ({dxy_w} this week) and basically going nowhere, so "
        f"foreign exchange is not a big headwind for company earnings right now. The one thing "
        f"worth watching is the gap between financials (XLF {xlf_y} year to date) and technology "
        f"(XLK {xlk_y} year to date). That spread is extreme and it is the foundation for the "
        f"JPM trade in the portfolio."
    )

    return f"<p>{p1}</p><p>{p2}</p><p>{p3}</p>"


# ── Parsers ────────────────────────────────────────────────────────────────────

def _parse_scoreboard(entry_text: str) -> list[dict]:
    pattern = r'## 1\. Cross-Asset Scoreboard.*?\n(.*?)(?=\n---|\Z)'
    match   = re.search(pattern, entry_text, re.DOTALL)
    if not match:
        return []
    rows = []
    for line in match.group(1).split('\n'):
        if not line.startswith('|'):
            continue
        cols = [c.strip() for c in line.split('|')[1:-1]]
        if not cols or cols[0].startswith('---') or cols[0].startswith('Instrument'):
            continue
        if len(cols) >= 4:
            rows.append({'name': cols[0], 'close': cols[1] if len(cols)>1 else '',
                         'chg_1w': cols[2] if len(cols)>2 else '',
                         'chg_ytd': cols[3] if len(cols)>3 else ''})
    return rows

def _read_section(text: str, keyword: str) -> str:
    pattern = rf'##[^#\n]*{re.escape(keyword)}[^\n]*\n\n(.*?)(?=\n---|\Z)'
    match   = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    body = match.group(1).strip()
    if body.startswith("*") and ("fill" in body.lower() or "not yet" in body.lower()):
        return ""
    return body

def _md_to_html(md: str) -> str:
    lines  = md.split('\n')
    output = []
    for line in lines:
        line = line.rstrip()
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        line = re.sub(r'\*(.+?)\*',     r'<em>\1</em>', line)
        line = re.sub(r'`(.+?)`',       r'<code>\1</code>', line)
        if line.startswith('- '):
            output.append(f'<li>{line[2:]}</li>')
        elif line == '':
            output.append('')
        else:
            output.append(line)
    html = '\n'.join(output)
    html = re.sub(r'(<li>.*?</li>\n)+', lambda m: f'<ul>{m.group()}</ul>', html, flags=re.DOTALL)
    result = []
    for para in html.split('\n\n'):
        para = para.strip()
        if not para:
            continue
        result.append(para if para.startswith('<') else f'<p>{para}</p>')
    return '\n'.join(result)

# ── Ticker bar ─────────────────────────────────────────────────────────────────

_TICKER_KEYS = ["SPX","NDX","VIX","US10Y","DXY","Gold","WTI","NVDA","AMZN","META","JPM"]

def _build_ticker_html(rows: list[dict]) -> str:
    lookup = {r['name'].strip('*').strip(): r for r in rows}
    items  = []
    for label in _TICKER_KEYS:
        row = lookup.get(label)
        if not row:
            continue
        close = row.get('close','—')
        chg   = row.get('chg_1w','')
        cls   = _chg_class(chg)
        items.append(
            f'<div class="ticker-item">'
            f'<span class="t-sym">{label}</span>'
            f'<span class="t-val">{close}</span>'
            f'<span class="t-chg {cls}">{chg}</span>'
            f'</div>'
        )
    content = ''.join(items)
    return (f'<div class="ticker-strip">'
            f'<div class="ticker-track">{content}{content}</div>'
            f'</div>')

# ── Section builders ───────────────────────────────────────────────────────────

def _build_stats_html(stats: dict) -> str:
    total  = stats.get("total_picks", 0)
    open_n = stats.get("open_picks", 0)
    closed = stats.get("closed_picks", 0)
    wr     = f"{stats['win_rate']*100:.0f}%" if stats.get("win_rate") is not None else "—"
    wr_cls = "gain" if stats.get("win_rate") and stats["win_rate"] > 0.5 else "muted"
    aw     = f"{stats['avg_winner']:+.1f}%" if stats.get("avg_winner") else "—"
    al     = f"{stats['avg_loser']:+.1f}%"  if stats.get("avg_loser")  else "—"
    cards  = [(str(total),"Total Picks","navy"),(str(open_n),"Open","gold"),
              (str(closed),"Closed","muted"),(wr,"Win Rate",wr_cls),
              (aw,"Avg Winner","gain"),(al,"Avg Loser","loss")]
    html   = '<div class="stats-row">'
    for val, label, cls in cards:
        html += (f'<div class="stat-card">'
                 f'<div class="stat-val {cls}">{val}</div>'
                 f'<div class="stat-lbl">{label}</div>'
                 f'</div>')
    html += '</div>'
    return html


def _build_options_block(row) -> str:
    """Render the purple options block with Greeks for call/put picks."""
    opt_type = str(row.get('instrument_type','')).lower()
    if opt_type not in ('call','put'):
        return ''

    strike      = _safe(row.get('strike',''))
    expiry      = str(row.get('expiry',''))[:10]
    premium     = _safe(row.get('premium_paid',''))
    break_even  = _safe(row.get('break_even',''))
    leverage    = _safe_f(row.get('leverage',''), 1, '—')
    delta       = _safe_f(row.get('delta',''), 3, '—')
    gamma       = _safe_f(row.get('gamma',''), 4, '—')
    theta       = _safe_f(row.get('theta_daily',''), 3, '—')
    vega        = _safe_f(row.get('vega_1pct',''), 3, '—')
    iv_pct      = f"{float(row.get('iv_used',0))*100:.1f}%" if row.get('iv_used') not in ('',[],None) and str(row.get('iv_used','')) != '' else '—'

    try:
        theta_val = float(row.get('theta_daily',0))
        theta_cls = 'neg' if theta_val < 0 else 'pos'
    except Exception:
        theta_cls = ''

    try:
        delta_val = float(row.get('delta',0))
        delta_cls = 'pos' if delta_val > 0 else 'neg'
    except Exception:
        delta_cls = ''

    type_label = opt_type.upper()

    return f"""
    <div class="options-block">
      <div class="options-title">{type_label} Option Details — Max Loss = Premium Paid</div>
      <div class="options-row">
        <div class="opt-item">
          <label>Strike</label>
          <div class="opt-val purple">{strike}</div>
        </div>
        <div class="opt-item">
          <label>Expiry</label>
          <div class="opt-val">{expiry}</div>
        </div>
        <div class="opt-item">
          <label>Premium Paid</label>
          <div class="opt-val purple">{premium}/share</div>
        </div>
        <div class="opt-item">
          <label>Break-Even at Expiry</label>
          <div class="opt-val">{break_even}</div>
        </div>
      </div>
      <div class="options-row" style="margin-bottom:12px">
        <div class="opt-item">
          <label>IV Used</label>
          <div class="opt-val">{iv_pct}</div>
        </div>
        <div class="opt-item">
          <label>Leverage</label>
          <div class="opt-val purple">{leverage}×</div>
        </div>
        <div class="opt-item">
          <label>Max Loss</label>
          <div class="opt-val loss">{premium}/share</div>
        </div>
        <div class="opt-item">
          <label>Contract = 100 shares</label>
          <div class="opt-val">×100</div>
        </div>
      </div>
      <div class="greeks-row">
        <div class="greek-cell">
          <span class="greek-name">Delta</span>
          <span class="greek-sym">Δ</span>
          <div class="greek-val {delta_cls}">{delta}</div>
        </div>
        <div class="greek-cell">
          <span class="greek-name">Gamma</span>
          <span class="greek-sym">Γ</span>
          <div class="greek-val">{gamma}</div>
        </div>
        <div class="greek-cell">
          <span class="greek-name">Theta / day</span>
          <span class="greek-sym">Θ</span>
          <div class="greek-val {theta_cls}">{theta}</div>
        </div>
        <div class="greek-cell">
          <span class="greek-name">Vega / 1% IV</span>
          <span class="greek-sym">ν</span>
          <div class="greek-val pos">+{vega}</div>
        </div>
      </div>
    </div>"""


def _build_entry_timing(row) -> str:
    """Render the amber entry-timing callout box if entry_note is present."""
    note = str(row.get("entry_note", "")).strip()
    if not note:
        return ""
    return f"""
    <div class="entry-timing">
      <div class="entry-timing-title">📅 When to Buy — Entry Timing &amp; Disclaimer</div>
      <div class="entry-timing-body">{note}</div>
    </div>"""


def _build_picks_html(picks_df: pd.DataFrame) -> str:
    if picks_df.empty:
        return '<p style="color:var(--text-muted);font-style:italic">No open positions.</p>'

    html = '<div class="picks-list">'
    for _, row in picks_df.iterrows():
        direction   = str(row.get("direction","long")).lower()
        instrument  = str(row.get("instrument_type","equity")).lower()
        pnl         = row.get("live_pnl_pct")
        pnl_cls     = _pnl_class(pnl)
        pnl_disp    = _pnl_str(pnl)
        days        = int(row["days_held"]) if pd.notna(row.get("days_held")) else 0
        conv_label, conv_cls = _conviction_badge(row.get("conviction", 3))
        rr_str, _   = _risk_reward(row["entry_price"], row["stop_price"], row["target_price"], direction)
        pct         = _range_pct(row["entry_price"], row["current_price"],
                                 row["stop_price"],  row["target_price"], direction)
        thesis      = str(row.get("thesis","")).strip()
        catalyst    = str(row.get("catalyst","")).strip()
        sector      = str(row.get("sector","")).strip()
        horizon     = str(row.get("time_horizon","")).title()
        ticker      = str(row.get("ticker",""))
        pick_id     = str(row.get("pick_id","")).replace("-","")  # safe CSS id

        # Risk display
        risk_pct = row.get("account_risk_pct","")
        try:
            risk_display = f'<span class="size-pill">{float(risk_pct):.1f}% of account</span>'
        except (ValueError, TypeError):
            risk_display = '<span style="color:var(--text-light);font-size:11px">—</span>'

        # Instrument badge
        if instrument == 'call':
            inst_badge = '<span class="badge b-call">CALL</span>'
        elif instrument == 'put':
            inst_badge = '<span class="badge b-put">PUT</span>'
        else:
            inst_badge = '<span class="badge b-equity">EQUITY</span>'

        # Options block
        options_html = _build_options_block(row)

        # Sparkline chart
        entry  = float(row['entry_price'])
        stop   = float(row['stop_price'])
        target = float(row['target_price'])
        chart_html = _build_sparkline(ticker, entry, stop, target,
                                       is_option=(instrument in ('call','put')))

        html += f"""
        <div class="pick-card {direction}">
          <div class="pick-header">
            <div class="pick-title-group">
              <div class="pick-ticker">{ticker}</div>
              <div class="pick-sub">{sector} · {horizon}</div>
            </div>
            <div class="pick-badges">
              <span class="badge b-{direction}">{direction.upper()}</span>
              {inst_badge}
              <span class="badge {conv_cls}">{conv_label}</span>
            </div>
          </div>
          <div class="pick-body">
            <div class="pick-metrics">
              <div class="metric">
                <label>Entry (Underlying)</label>
                <div class="metric-val">{_safe(row['entry_price'])}</div>
              </div>
              <div class="metric">
                <label>Current &amp; P&amp;L</label>
                <div id="cp-wrap-{pick_id}" class="metric-val {pnl_cls}">
                  <span id="cp-{pick_id}">{_safe(row['current_price'])}</span>
                  <span id="pnl-{pick_id}" class="pnl-pill {pnl_cls}">{pnl_disp}</span>
                </div>
              </div>
              <div class="metric">
                <label>Target</label>
                <div class="metric-val gain">{_safe(row['target_price'])}</div>
              </div>
              <div class="metric">
                <label>Stop</label>
                <div class="metric-val loss">{_safe(row['stop_price'])}</div>
              </div>
            </div>

            <div class="pick-progress">
              <div class="progress-row">
                <span class="p-stop">{_safe(row['stop_price'])} stop</span>
                <span class="p-rr">{rr_str}</span>
                <span class="p-target">{_safe(row['target_price'])} target</span>
              </div>
              <div class="progress-track">
                <div id="pfill-{pick_id}" class="progress-fill {pnl_cls}" style="width:{pct:.1f}%"></div>
              </div>
            </div>

            {options_html}

            <div class="pick-sizing-row">
              <span><strong>Position size:</strong> {risk_display}</span>
              <span><strong>Days held:</strong> {days}d</span>
              <span><strong>Instrument:</strong> {instrument.title()}</span>
            </div>

            {'<div class="pick-thesis">' + thesis + '</div>' if thesis else ''}
            {'<div class="pick-catalyst">' + catalyst + '</div>' if catalyst else ''}

            {_build_entry_timing(row)}

            {chart_html}
          </div>
        </div>
        """
    html += '</div>'
    return html


def _build_scoreboard_html(rows: list[dict]) -> str:
    if not rows:
        return "<p style='color:var(--text-muted)'>No scoreboard data.</p>"
    html = ('<div class="table-wrap"><table>'
            '<thead><tr><th>Instrument</th><th class="r">Close</th>'
            '<th class="r">1W Chg</th><th class="r">YTD Chg</th>'
            '</tr></thead><tbody>')
    for row in rows:
        name = row['name'].strip('*').strip()
        if row.get('close','') == '' and row.get('chg_1w','') == '':
            label = re.sub(r'\*+','',name).strip()
            label = re.sub(r'\s*\(.*?\)','',label).strip()
            html += f'<tr><td class="sh" colspan="4">{label}</td></tr>'
            continue
        c1 = _chg_class(row.get('chg_1w',''))
        c2 = _chg_class(row.get('chg_ytd',''))
        html += (f'<tr><td class="nm">{name}</td>'
                 f'<td class="r">{row.get("close","—")}</td>'
                 f'<td class="r {c1}">{row.get("chg_1w","—")}</td>'
                 f'<td class="r {c2}">{row.get("chg_ytd","—")}</td></tr>')
    html += '</tbody></table></div>'
    return html

# ── Main build ─────────────────────────────────────────────────────────────────

def _current_week_str() -> str:
    """
    Return the best available ISO week string.
    Prefers the current week if an entry file exists, otherwise the most
    recent week that HAS an entry file. Never imports new_week (avoids
    pulling in fredapi which is not needed for site builds).
    """
    today = date.today()
    iso   = today.isocalendar()
    # Walk back up to 8 weeks to find the latest entry file
    for offset in range(8):
        check_date = today - timedelta(days=7 * offset)
        ci = check_date.isocalendar()
        w  = f"{ci.year}-W{ci.week:02d}"
        if (ENTRIES_DIR / f"{w}.md").exists():
            return w
    # Absolute fallback: just use today's ISO week
    return f"{iso.year}-W{iso.week:02d}"


def build_site(week_str: str | None = None) -> Path:
    """Generate website/index.html. Returns output path."""
    from scripts.picks import get_open_picks, compute_track_record

    if week_str is None:
        week_str = _current_week_str()

    entry_path      = ENTRIES_DIR     / f"{week_str}.md"
    newsletter_path = NEWSLETTERS_DIR / f"{week_str}.md"
    entry_text = entry_path.read_text(encoding="utf-8")      if entry_path.exists()      else ""
    nl_text    = newsletter_path.read_text(encoding="utf-8") if newsletter_path.exists() else entry_text

    scoreboard_rows = _parse_scoreboard(entry_text)

    try:
        open_picks = get_open_picks()
    except Exception:
        open_picks = pd.DataFrame()

    try:
        stats = compute_track_record()
    except Exception:
        stats = {"total_picks":0,"open_picks":0,"closed_picks":0,
                 "win_rate":None,"avg_winner":None,"avg_loser":None}

    # Build picks JSON for the client-side live-price updater
    _picks_js_list = []
    if not open_picks.empty:
        for _, _pr in open_picks.iterrows():
            try:
                _picks_js_list.append({
                    "id":        str(_pr.get("pick_id","")).replace("-",""),
                    "ticker":    str(_pr.get("ticker","")),
                    "entry":     float(_pr.get("entry_price", 0)),
                    "direction": str(_pr.get("direction","long")).lower(),
                    "stop":      float(_pr.get("stop_price",  0)),
                    "target":    float(_pr.get("target_price", 0)),
                })
            except Exception:
                pass
    picks_json = json.dumps(_picks_js_list)

    # Prose — fall back to auto-generated narrative if not written yet
    written_narrative = _read_section(nl_text, "Narrative")
    if written_narrative:
        narrative_html = _md_to_html(written_narrative)
        narrative_src  = "analyst"
    else:
        narrative_html = _auto_narrative(scoreboard_rows)
        narrative_src  = "auto"

    written_view = _read_section(nl_text, "My View")
    my_view_html = _md_to_html(written_view) if written_view else (
        "<em>My View section not yet written — fill it in the journal entry.</em>"
    )

    # Header metadata
    hm       = re.search(r'# (.+?) · (.+)', entry_text)
    week_lbl = hm.group(1).strip() if hm else week_str
    date_rng = hm.group(2).strip() if hm else ""
    tm       = re.search(r'\*\*Theme:\*\*\s*(.*)', entry_text)
    raw_theme = tm.group(1).strip() if tm else "Theme not yet set. Fill it in the journal entry."
    theme = raw_theme.strip('*').strip()

    # Build components
    ticker_html     = _build_ticker_html(scoreboard_rows)
    stats_html      = _build_stats_html(stats)
    picks_html      = _build_picks_html(open_picks)
    scoreboard_html = _build_scoreboard_html(scoreboard_rows)

    auto_note = (
        ' <span style="font-size:9px;color:var(--text-light);'
        'font-style:italic;font-weight:400">(auto-generated from scoreboard data — '
        'write section 6 in your journal to override)</span>'
        if narrative_src == "auto" else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="60">
  <title>The Reins Report · {week_lbl}</title>
  <style>{CSS}</style>
  <script>
  // ── Live price updater ───────────────────────────────────────────────────────
  // Fetches real-time quotes from Yahoo Finance every 30 s during market hours.
  // Updates Current price, P&L %, and progress bar in-place without a page reload.
  (function() {{
    // Picks embedded at build time — each has id, ticker, entry, direction, stop, target
    var PICKS = {picks_json};

    // Market-hours check in ET (works in any browser timezone)
    function isMarketOpen() {{
      var etStr = new Date().toLocaleString('en-US', {{timeZone:'America/New_York'}});
      var et    = new Date(etStr);
      var day   = et.getDay();                        // 0=Sun 6=Sat
      if (day === 0 || day === 6) return false;
      var mins  = et.getHours() * 60 + et.getMinutes();
      return mins >= 570 && mins < 960;               // 9:30 – 16:00 ET
    }}

    // Update the live-indicator badge in the masthead
    function setIndicator(open) {{
      var el = document.getElementById('live-indicator');
      if (!el) return;
      el.innerHTML = open
        ? '<span class="live-pulse"></span><span style="color:#4ade80;font-weight:700">LIVE PRICES</span>'
        : '<span style="color:rgba(255,255,255,.35)">⚫ MARKET CLOSED</span>';
    }}

    // Format a number as "$1,234.56"
    function fmt(n) {{
      return '$' + n.toFixed(2).replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',');
    }}

    // Push a fresh price into one pick card
    function updateCard(pick, price) {{
      var cpEl   = document.getElementById('cp-'      + pick.id);
      var pnlEl  = document.getElementById('pnl-'     + pick.id);
      var wrapEl = document.getElementById('cp-wrap-' + pick.id);
      var fillEl = document.getElementById('pfill-'   + pick.id);
      if (!cpEl) return;

      var pct  = pick.direction === 'short'
                   ? (pick.entry - price) / pick.entry * 100
                   : (price - pick.entry) / pick.entry * 100;
      var cls  = pct > 0.005 ? 'gain' : (pct < -0.005 ? 'loss' : 'flat');
      var sign = pct >= 0 ? '+' : '';

      cpEl.textContent = fmt(price);
      if (pnlEl)  {{ pnlEl.textContent = sign + pct.toFixed(1) + '%';
                     pnlEl.className   = 'pnl-pill ' + cls; }}
      if (wrapEl)   wrapEl.className   = 'metric-val ' + cls;
      if (fillEl) {{
        var total = pick.direction === 'short'
                      ? pick.entry - pick.stop
                      : pick.target - pick.entry;
        var moved = pick.direction === 'short'
                      ? pick.entry - price
                      : price - pick.entry;
        var w = total > 0 ? Math.max(0, Math.min(100, moved / total * 100)) : 0;
        fillEl.style.width  = w.toFixed(1) + '%';
        fillEl.className    = 'progress-fill ' + cls;
      }}
    }}

    // Fetch all tickers in one Yahoo Finance batch request; fall back to corsproxy
    function fetchAll() {{
      if (!PICKS || !PICKS.length) return;
      var syms = PICKS.map(function(p){{ return p.ticker; }}).join(',');
      var url  = 'https://query1.finance.yahoo.com/v7/finance/quote?symbols=' + syms
               + '&fields=regularMarketPrice';

      function applyPrices(data) {{
        var results = ((data.quoteResponse || {{}}).result) || [];
        var byTick  = {{}};
        results.forEach(function(r) {{ byTick[r.symbol] = r.regularMarketPrice; }});
        PICKS.forEach(function(pick) {{
          if (byTick[pick.ticker] != null) updateCard(pick, byTick[pick.ticker]);
        }});
      }}

      fetch(url, {{mode:'cors'}})
        .then(function(r) {{ return r.json(); }})
        .then(applyPrices)
        .catch(function() {{
          // CORS blocked — route through corsproxy.io
          fetch('https://corsproxy.io/?' + encodeURIComponent(url))
            .then(function(r) {{ return r.json(); }})
            .then(applyPrices)
            .catch(function() {{ /* silently ignore offline failures */ }});
        }});
    }}

    // Main tick: check market, update indicator, fetch prices if open
    function tick() {{
      var open = isMarketOpen();
      setIndicator(open);
      if (open) fetchAll();
    }}

    // Kick off on load then every 30 s
    if (document.readyState === 'loading') {{
      document.addEventListener('DOMContentLoaded', function() {{ tick(); setInterval(tick, 30000); }});
    }} else {{
      tick(); setInterval(tick, 30000);
    }}
  }})();
  </script>
</head>
<body>

<header class="masthead">
  <div class="masthead-inner">
    <div>
      <div class="pub-eyebrow">Independent Research · Carter Reins</div>
      <div class="pub-name">The Reins Report</div>
      <div class="pub-tagline">Systematic equity &amp; macro research — not financial advice</div>
    </div>
    <div class="masthead-right">
      <div class="pub-week">{week_lbl}</div>
      <div class="pub-date">{date_rng} · Updated {date.today().strftime('%b %d, %Y')}</div>
      <div id="live-indicator" style="margin-top:6px;color:rgba(255,255,255,.4)">⚫ MARKET CLOSED</div>
    </div>
  </div>
</header>

{ticker_html}

<div class="page-wrap">

  <div class="market-overview">
    <div class="overview-kicker">Market Structure · {week_lbl}</div>
    <div class="overview-theme">{theme}</div>
    <div class="overview-body">{narrative_html}</div>
  </div>

  <div class="about-panel">
    <div class="about-avatar">CR</div>
    <div class="about-body">
      <div class="about-name">Carter Reins — Analyst &amp; Portfolio Researcher</div>
      <div class="about-desc">
        Three years of active trading across equities, options, and macro markets.
        I run a systematic framework that looks at market regime first, then hunts for
        setups where the fundamentals and the price action line up cleanly. Every pick
        needs at least a 3 to 1 reward to risk ratio before it makes the cut. One
        high-conviction position per week. Maximum portfolio drawdown I will tolerate is 3 percent.
      </div>
      <div class="about-tags">
        <span class="about-tag">3 Yrs Active Trading</span>
        <span class="about-tag">Quant Framework</span>
        <span class="about-tag">Options + Equity</span>
        <span class="about-tag">Risk-First</span>
        <span class="about-tag">Macro Research</span>
      </div>
    </div>
  </div>

  <section>
    <div class="section-label">📊 Track Record</div>
    {stats_html}
  </section>

  <section>
    <div class="section-label">📈 Open Positions — Live Scorecard</div>
    {picks_html}
  </section>

  <section>
    <div class="section-label">🌐 Cross-Asset Scoreboard</div>
    {scoreboard_html}
  </section>

  <section>
    <div class="section-label">🔍 Market Narrative &amp; My View{auto_note}</div>
    <div class="prose-card">
      <h3>The Story This Week</h3>
      {narrative_html}
      <h3>My View</h3>
      {my_view_html}
    </div>
  </section>

</div>

<footer>
  <div class="footer-inner">
    <div class="disclaimer">
      All content reflects personal research and opinion only. Nothing on this page
      constitutes financial advice, a recommendation to buy or sell any security, or
      a solicitation of any kind. Past performance does not guarantee future results.
      Options involve significant risk and are not suitable for all investors.
    </div>
    <div class="pub-credit">The Reins Report · {date.today().year} · Independent Research</div>
  </div>
</footer>

</body>
</html>"""

    WEBSITE_DIR.mkdir(parents=True, exist_ok=True)
    out = WEBSITE_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    return out
