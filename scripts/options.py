"""
Black-Scholes option pricer and Greeks calculator.
Pure Python — no scipy dependency.

Usage:
    from scripts.options import compute_greeks, estimate_iv
    g = compute_greeks(spot=215.33, strike=220, expiry=date(2026,6,20), iv=0.45)
    print(g.price, g.delta, g.theta_daily)
"""

import math
from datetime import date


# ── Math helpers ───────────────────────────────────────────────────────────────

def _norm_pdf(x: float) -> float:
    return (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x)


def _norm_cdf(x: float) -> float:
    """Abramowitz & Stegun rational approximation — accurate to 7 decimal places."""
    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937
                + t * (-1.821255978 + t * 1.330274429))))
    cdf = 1.0 - _norm_pdf(x) * poly
    return cdf if x >= 0.0 else 1.0 - cdf


# ── IV estimation ──────────────────────────────────────────────────────────────

# Beta tiers vs VIX: individual stock vol ≈ VIX × multiplier
_HIGH_BETA = {'NVDA','TSLA','AMD','SMCI','PLTR','MSTR','COIN','MRNA','SHOP','SQ','HOOD'}
_MID_BETA  = {'META','AMZN','GOOGL','MSFT','AAPL','CRM','NFLX','UBER','ABNB','SNOW'}
_LOW_BETA  = {'JPM','GS','MS','BAC','XOM','CVX','JNJ','PG','KO','WMT','V','MA'}

def estimate_iv(ticker: str, vix_override: float | None = None) -> float:
    """
    Estimate implied volatility for a ticker using VIX × beta multiplier.
    Falls back to VIX 16.70 if live fetch fails.

    Returns IV as a decimal (e.g. 0.42 = 42%).
    """
    if vix_override is not None:
        vix = vix_override
    else:
        try:
            import yfinance as yf
            h = yf.Ticker('^VIX').history(period='2d')['Close']
            vix = float(h.iloc[-1])
        except Exception:
            vix = 16.70  # fallback from cached scoreboard

    ticker = ticker.upper()
    if ticker in _HIGH_BETA:
        mult = 2.7
    elif ticker in _MID_BETA:
        mult = 1.9
    elif ticker in _LOW_BETA:
        mult = 1.25
    else:
        mult = 2.1

    return round(vix / 100.0 * mult, 4)


# ── Main Greeks calculator ─────────────────────────────────────────────────────

class GreeksResult:
    """
    Results from Black-Scholes pricer.

    Attributes:
        price        — theoretical premium per share (mid-market)
        delta        — Δ directional exposure (0-1 calls, -1 to 0 puts)
        gamma        — Γ rate of delta change per $1 move
        theta_daily  — Θ daily time decay in $ per share (negative = costs you)
        vega_1pct    — ν value change per +1% IV move in $ per share
        break_even   — underlying price needed at expiry to break even
        leverage     — spot / premium (effective leverage ratio)
        iv_used      — actual IV used in the calculation
        rho          — ρ rate sensitivity (per 1% rate change)
        intrinsic    — max(0, S-K) for calls, max(0, K-S) for puts
        time_value   — price - intrinsic
    """
    __slots__ = ('price','delta','gamma','theta_daily','vega_1pct',
                 'break_even','leverage','iv_used','rho','intrinsic','time_value')

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}

    def __repr__(self):
        return (f"GreeksResult(price=${self.price:.2f}  Δ={self.delta:+.3f}  "
                f"Γ={self.gamma:.4f}  Θ={self.theta_daily:+.3f}/day  "
                f"ν={self.vega_1pct:.3f}/1%  BE=${self.break_even:.2f}  "
                f"lev={self.leverage:.1f}×  IV={self.iv_used*100:.1f}%)")


def compute_greeks(
    spot:      float,
    strike:    float,
    expiry:    date,
    iv:        float,
    r:         float = 0.053,    # risk-free rate — use 10Y yield as proxy
    opt_type:  str   = 'call',   # 'call' or 'put'
    as_of:     date | None = None,
) -> GreeksResult:
    """
    Compute Black-Scholes option price and all Greeks.

    Args:
        spot      — current underlying price
        strike    — option strike price
        expiry    — option expiration date
        iv        — implied volatility as decimal (e.g. 0.42 = 42%)
        r         — risk-free rate (default: 5.3% = current 10Y proxy)
        opt_type  — 'call' or 'put'
        as_of     — pricing date (defaults to today)

    Returns:
        GreeksResult with price, delta, gamma, theta_daily, vega_1pct,
        break_even, leverage, iv_used, rho, intrinsic, time_value
    """
    if as_of is None:
        as_of = date.today()

    T = (expiry - as_of).days / 365.0

    # Intrinsic value
    intrinsic = max(0.0, spot - strike) if opt_type == 'call' else max(0.0, strike - spot)

    if T <= 0:
        # Expired option — only intrinsic remains
        price = intrinsic
        delta = 1.0 if (opt_type == 'call' and spot > strike) else \
                (-1.0 if (opt_type == 'put' and spot < strike) else 0.0)
        return GreeksResult(price=price, delta=delta, gamma=0.0, theta_daily=0.0,
                            vega_1pct=0.0, break_even=strike + price if opt_type == 'call'
                            else strike - price, leverage=spot / max(price, 0.01),
                            iv_used=iv, rho=0.0, intrinsic=intrinsic, time_value=0.0)

    iv   = max(iv, 0.005)  # floor at 0.5%
    sq_T = math.sqrt(T)
    discount = math.exp(-r * T)

    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * T) / (iv * sq_T)
    d2 = d1 - iv * sq_T

    if opt_type == 'call':
        Nd1, Nd2   = _norm_cdf(d1),  _norm_cdf(d2)
        Nd1_, Nd2_ = _norm_cdf(-d1), _norm_cdf(-d2)
        price = max(spot * Nd1 - strike * discount * Nd2, 0.01)
        delta = Nd1
        rho   = strike * T * discount * Nd2 / 100
    else:
        Nd1_, Nd2_ = _norm_cdf(-d1), _norm_cdf(-d2)
        Nd1,  Nd2  = _norm_cdf(d1),  _norm_cdf(d2)
        price = max(strike * discount * Nd2_ - spot * Nd1_, 0.01)
        delta = Nd1 - 1.0
        rho   = -strike * T * discount * Nd2_ / 100

    pdf_d1 = _norm_pdf(d1)
    gamma  = pdf_d1 / (spot * iv * sq_T)

    # Theta: $ per calendar day (negative = daily cost of holding)
    theta = (
        -spot * pdf_d1 * iv / (2.0 * sq_T)
        - r * strike * discount * (Nd2 if opt_type == 'call' else -Nd2_)
    ) / 365.0

    # Vega: $ change per +1% IV increase
    vega_1pct = spot * pdf_d1 * sq_T / 100.0

    break_even = strike + price if opt_type == 'call' else strike - price
    leverage   = spot / price
    time_value = price - intrinsic

    return GreeksResult(
        price       = round(price,       2),
        delta       = round(delta,       3),
        gamma       = round(gamma,       4),
        theta_daily = round(theta,       3),
        vega_1pct   = round(vega_1pct,   3),
        break_even  = round(break_even,  2),
        leverage    = round(leverage,    1),
        iv_used     = iv,
        rho         = round(rho,         4),
        intrinsic   = round(intrinsic,   2),
        time_value  = round(time_value,  2),
    )


def option_pnl_at_target(
    premium_paid:  float,
    spot_target:   float,
    strike:        float,
    expiry:        date,
    iv_exit:       float,
    r:             float = 0.053,
    opt_type:      str   = 'call',
    days_to_exit:  int   = 14,      # assume mid-trade exit not at expiry
    as_of:         date | None = None,
) -> dict:
    """
    Estimate option P&L if underlying hits your price target before expiry.
    Uses BS to price the option at the target date/price.
    """
    if as_of is None:
        as_of = date.today()
    exit_date = date.fromordinal(as_of.toordinal() + days_to_exit)
    exit_greeks = compute_greeks(spot_target, strike, expiry, iv_exit, r, opt_type, exit_date)
    pnl_per_share = exit_greeks.price - premium_paid
    pnl_pct       = pnl_per_share / premium_paid * 100
    return {
        'exit_premium':    round(exit_greeks.price, 2),
        'pnl_per_share':   round(pnl_per_share, 2),
        'pnl_pct':         round(pnl_pct, 1),
        'rr_on_premium':   round(pnl_per_share / premium_paid * (premium_paid / premium_paid), 2),
    }
