"""
engine.py - Arauco Mexico - Financial Risk Engine
Pure Python / NumPy / SciPy - zero Flask/Streamlit imports.

References:
  Forward rate  : Covered Interest Rate Parity, continuous compounding
  FX Options    : Garman-Kohlhagen (1983), J. of Int. Money & Finance
  Monte Carlo   : Geometric Brownian Motion, risk-neutral measure
"""

import math
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq


# -- Forward Rate: Covered Interest Rate Parity -----------------------

def forward_rate(S, r_d, r_f, T):
    """F = S * exp((r_d - r_f) * T)"""
    return S * math.exp((r_d - r_f) * T)


def forward_points(S, r_d, r_f, T):
    return forward_rate(S, r_d, r_f, T) - S


# -- Garman-Kohlhagen (1983) FX Option Pricing ------------------------

def _gk_d1d2(S, K, r_d, r_f, sigma, T):
    d1 = (math.log(S / K) + (r_d - r_f + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def gk_call(S, K, r_d, r_f, sigma, T):
    if T <= 1e-9:
        return max(S - K, 0.0)
    d1, d2 = _gk_d1d2(S, K, r_d, r_f, sigma, T)
    return (S * math.exp(-r_f * T) * norm.cdf(d1) -
            K * math.exp(-r_d * T) * norm.cdf(d2))


def gk_put(S, K, r_d, r_f, sigma, T):
    if T <= 1e-9:
        return max(K - S, 0.0)
    d1, d2 = _gk_d1d2(S, K, r_d, r_f, sigma, T)
    return (K * math.exp(-r_d * T) * norm.cdf(-d2) -
            S * math.exp(-r_f * T) * norm.cdf(-d1))


def gk_delta_call(S, K, r_d, r_f, sigma, T):
    if T <= 1e-9:
        return 1.0 if S > K else 0.0
    d1, _ = _gk_d1d2(S, K, r_d, r_f, sigma, T)
    return math.exp(-r_f * T) * norm.cdf(d1)


def gk_delta_put(S, K, r_d, r_f, sigma, T):
    if T <= 1e-9:
        return -1.0 if S < K else 0.0
    d1, _ = _gk_d1d2(S, K, r_d, r_f, sigma, T)
    return -math.exp(-r_f * T) * norm.cdf(-d1)


# -- Zero-Cost Collar --------------------------------------------------

def zccollar_cap_strike(S, K_floor, r_d, r_f, sigma, T):
    """Payer collar: buy call, sell put. Find K_cap given K_floor."""
    put_prem = gk_put(S, K_floor, r_d, r_f, sigma, T)
    def obj(Kc):
        return gk_call(S, Kc, r_d, r_f, sigma, T) - put_prem
    try:
        return brentq(obj, S * 0.999, S * 2.0, xtol=1e-6)
    except ValueError:
        return S * 1.05


def zccollar_floor_strike(S, K_cap, r_d, r_f, sigma, T):
    """Receiver collar: buy put, sell call. Find K_floor given K_cap."""
    call_prem = gk_call(S, K_cap, r_d, r_f, sigma, T)
    def obj(Kf):
        return gk_put(S, Kf, r_d, r_f, sigma, T) - call_prem
    try:
        return brentq(obj, S * 0.4, S * 1.0 - 1e-6, xtol=1e-6)
    except ValueError:
        return S * 0.95


# -- Net USD Exposure --------------------------------------------------

def net_usd_exposure(revenue_mxn, pct_rev_usd, costs_mxn, pct_cost_usd,
                     debt_usd, spot):
    rev_usd  = revenue_mxn * pct_rev_usd / spot
    cost_usd = costs_mxn   * pct_cost_usd / spot
    net      = rev_usd - cost_usd - debt_usd
    return {
        "revenue_usd": rev_usd,
        "cost_usd":    cost_usd,
        "debt_usd":    debt_usd,
        "net_usd":     net,
        "position":    "Receptor (Net Long USD)" if net >= 0 else "Pagador (Net Short USD)",
        "is_receiver": net >= 0,
    }


# -- Scenario P&L -----------------------------------------------------

def get_fx_scenarios(spot, moves):
    return {label: spot * (1 + m) for label, m in moves.items()}


def scenario_pnl(net_usd_monthly, spot_base, fx_scenarios,
                 forward, hedge_ratio, horizon_months):
    total_usd   = net_usd_monthly * horizon_months
    sign        = 1 if total_usd >= 0 else -1
    h_notional  = abs(total_usd) * hedge_ratio
    uh_notional = abs(total_usd) * (1 - hedge_ratio)
    results = []
    for label, S_T in fx_scenarios.items():
        pnl_raw      = sign * total_usd * (S_T - spot_base)
        pnl_fwd      = sign * h_notional  * (forward - spot_base)
        pnl_residual = sign * uh_notional * (S_T - spot_base)
        pnl_hedged   = pnl_fwd + pnl_residual
        results.append({
            "scenario":     label,
            "fx_rate":      S_T,
            "pnl_unhedged": pnl_raw,
            "pnl_hedged":   pnl_hedged,
            "benefit":      pnl_hedged - pnl_raw,
        })
    return results


# -- Monte Carlo GBM --------------------------------------------------

def monte_carlo_fx(S0, r_d, r_f, sigma, T, n_sims=10_000, seed=42):
    rng = np.random.default_rng(seed)
    Z   = rng.standard_normal(n_sims)
    return S0 * np.exp((r_d - r_f - 0.5 * sigma**2) * T + sigma * math.sqrt(T) * Z)


def risk_metrics(S_terminal, net_usd_monthly, spot_base, forward,
                 hedge_ratio, horizon_months, conf_var=0.95):
    total_usd = net_usd_monthly * horizon_months
    sign      = 1 if total_usd >= 0 else -1
    h_n  = abs(total_usd) * hedge_ratio
    uh_n = abs(total_usd) * (1 - hedge_ratio)

    pnl_u = sign * total_usd * (S_terminal - spot_base)
    pnl_h = (sign * h_n  * (forward - spot_base) +
             sign * uh_n * (S_terminal - spot_base))

    def _var_cvar(pnl_arr, conf):
        losses = -pnl_arr
        q = np.percentile(losses, conf * 100)
        return q, losses[losses >= q].mean()

    var_u,  cvar_u  = _var_cvar(pnl_u, conf_var)
    var_h,  cvar_h  = _var_cvar(pnl_h, conf_var)
    cfar_u = float(-np.percentile(pnl_u, (1 - conf_var) * 100))
    cfar_h = float(-np.percentile(pnl_h, (1 - conf_var) * 100))

    vol_u = pnl_u.std()
    vol_h = pnl_h.std()
    vol_reduction = (vol_u - vol_h) / vol_u if vol_u > 0 else 0.0

    return {
        "var_unhedged":   float(var_u),
        "cvar_unhedged":  float(cvar_u),
        "var_hedged":     float(var_h),
        "cvar_hedged":    float(cvar_h),
        "cfar_unhedged":  cfar_u,
        "cfar_hedged":    cfar_h,
        "vol_reduction":  vol_reduction,
        "vol_unhedged":   float(vol_u),
        "vol_hedged":     float(vol_h),
        "mean_unhedged":  float(pnl_u.mean()),
        "mean_hedged":    float(pnl_h.mean()),
        "pnl_unhedged":   pnl_u,
        "pnl_hedged":     pnl_h,
    }


def budget_rate(net_usd_monthly, spot_base, ebitda_annual_usd, horizon_months):
    buffer    = ebitda_annual_usd * (horizon_months / 12)
    total_usd = abs(net_usd_monthly) * horizon_months
    if total_usd < 1:
        return spot_base
    return spot_base + buffer / total_usd


# -- EBITDA FX Sensitivity --------------------------------------------

def ebitda_fx_sensitivity(revenue_mxn, pct_rev_usd, costs_mxn, pct_cost_usd,
                           spot, ebitda_annual_usd, shock_pct=0.05):
    annual_rev_mxn = revenue_mxn * 12

    def ebitda_at(s):
        usd_rev  = annual_rev_mxn * pct_rev_usd / s
        mxn_rev  = annual_rev_mxn * (1 - pct_rev_usd) / s
        usd_cost = costs_mxn * pct_cost_usd / spot * 12
        mxn_cost = costs_mxn * (1 - pct_cost_usd) / s * 12
        return usd_rev + mxn_rev - usd_cost - mxn_cost

    base = ebitda_at(spot)
    up   = ebitda_at(spot * (1 + shock_pct))
    dn   = ebitda_at(spot * (1 - shock_pct))

    return {
        "ebitda_base":   base,
        "ebitda_up":     up,
        "ebitda_dn":     dn,
        "impact_up":     up  - base,
        "impact_dn":     dn  - base,
        "impact_pct_up": (up  - base) / ebitda_annual_usd * 100 if ebitda_annual_usd else 0,
        "impact_pct_dn": (dn  - base) / ebitda_annual_usd * 100 if ebitda_annual_usd else 0,
    }


# -- Resin / Input-Cost Module ----------------------------------------

def resin_cost_buildup(basket, spot):
    items = {}
    total_usd = 0.0
    for name, d in basket.items():
        mo_usd   = d["volume_ton_month"] * d["price_usd_ton"]
        base_usd = d["volume_ton_month"] * d["price_base_usd_ton"]
        items[name] = {
            "volume_ton_month": d["volume_ton_month"],
            "price_usd_ton":    d["price_usd_ton"],
            "monthly_usd":      mo_usd,
            "monthly_mxn":      mo_usd * spot,
            "price_chg_pct":    (d["price_usd_ton"] / d["price_base_usd_ton"] - 1) * 100,
            "vs_base_usd":      mo_usd - base_usd,
        }
        total_usd += mo_usd
    return {
        "items":             items,
        "total_monthly_usd": total_usd,
        "total_monthly_mxn": total_usd * spot,
    }


def resin_shock_impact(basket, shock_pct, spot):
    shocked_basket = {
        n: {**d, "price_usd_ton": d["price_usd_ton"] * (1 + shock_pct.get(n, 0))}
        for n, d in basket.items()
    }
    base    = resin_cost_buildup(basket, spot)
    shocked = resin_cost_buildup(shocked_basket, spot)
    return {
        "base_usd":    base["total_monthly_usd"],
        "shocked_usd": shocked["total_monthly_usd"],
        "delta_usd":   shocked["total_monthly_usd"] - base["total_monthly_usd"],
        "delta_mxn":   (shocked["total_monthly_usd"] - base["total_monthly_usd"]) * spot,
    }


# -- Payoff / Effective Rate Curves -----------------------------------

def effective_rate_forward(S_range, F):
    return np.full_like(S_range, F)


def effective_rate_put_buyer(S_range, K, premium):
    return np.maximum(S_range, K) - premium


def effective_rate_receiver_collar(S_range, K_floor, K_cap, net_premium=0.0):
    return np.clip(S_range, K_floor, K_cap) - net_premium


def derivative_pnl_forward(S_range, F, direction=1):
    return direction * (S_range - F)
