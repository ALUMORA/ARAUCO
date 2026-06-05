"""
FX Cobertura Dashboard — Flask App
Gestión de exposición cambiaria con coberturas de opciones (Garman-Kohlhagen 1983)
"""

from flask import Flask, render_template, request, jsonify
import json, math, os, uuid
from datetime import datetime, date
import numpy as np
from scipy.stats import norm

app = Flask(__name__)
app.secret_key = "cobertura2026"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TXN_FILE = os.path.join(BASE_DIR, "transactions.json")

# In-memory fallback for read-only environments (e.g. Vercel serverless)
_MEM_STORE: list = []
_USE_MEM = False

# ── Macro Data ─────────────────────────────────────────────────────────────────
MACRO_DATA = {
    "usd_mxn":      {"actual": 17.34, "forecast_low": 17.5, "forecast_high": 18.5},
    "inflacion_mx": {"actual": 4.53, "meta": 3.0, "techo": 4.0},
    "inflacion_us": {"actual": 3.80, "core": 2.8},
    "tasa_banxico": {"actual": 6.50, "pico_2023": 11.25},
    "tasa_fed":     {"actual": 3.625, "rango_low": 3.50, "rango_high": 3.75},
    "pib_mx":       {"q1_2026": -0.8, "forecast_2026": 1.1},
    "pib_us":       {"forecast_2026": 1.5, "actual_2025": 2.0},
}

CHART_DATA = {
    "inflacion": {
        "labels": ["2024","Q1-25","Q2-25","Q3-25","Q4-25","Abr-26","Fcst Q4-26"],
        "mx": [4.66, 3.98, 4.2, 4.45, 4.6, 4.53, 3.5],
        "us": [3.4, 2.9, 2.7, 2.8, 2.9, 3.8, 3.5],
    },
    "tasas": {
        "labels": ["Mar-24","Jun-24","Sep-24","Dic-24","Mar-25","Jun-25","Sep-25","Dic-25","Mar-26","May-26"],
        "banxico": [11.25, 11.0, 10.75, 10.0, 9.0, 8.0, 7.25, 6.75, 6.75, 6.5],
        "fed":     [5.25, 5.25, 5.0, 4.5, 4.25, 3.75, 3.75, 3.625, 3.625, 3.625],
    },
    "fx": {
        "labels": ["Ene-26","Feb-26","Mar-26","Abr-26","May-26","Jun-26","Ago-26","Oct-26","Dic-26"],
        "spot":      [17.1, 17.2, 17.25, 17.3, 17.34, None, None, None, None],
        "consenso":  [None, None, None, None, 17.34, 17.4, 17.6, 17.9, 18.0],
        "pesimista": [None, None, None, None, 17.34, 17.5, 17.8, 18.2, 18.47],
    },
    "pib": {
        "labels": ["MX 2024","MX 2025e","MX Q1-26","MX Fcst 26","EE.UU. 24","EE.UU. 25","EE.UU. Fcst 26"],
        "valores": [1.5, -0.6, -0.8, 1.1, 2.9, 2.0, 1.7],
    },
}

# ── Storage ────────────────────────────────────────────────────────────────────
def load_txns():
    global _USE_MEM
    if _USE_MEM:
        return list(_MEM_STORE)
    if os.path.exists(TXN_FILE):
        try:
            with open(TXN_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_txns(txns):
    global _USE_MEM, _MEM_STORE
    if _USE_MEM:
        _MEM_STORE[:] = txns
        return
    try:
        with open(TXN_FILE, "w", encoding="utf-8") as f:
            json.dump(txns, f, indent=2, ensure_ascii=False)
    except OSError:
        # Filesystem read-only (Vercel). Fall back to in-memory store.
        _USE_MEM = True
        _MEM_STORE[:] = txns

# ── FX Live Data ───────────────────────────────────────────────────────────────
FX_TICKERS  = {"USD": "USDMXN=X", "EUR": "EURMXN=X", "CAD": "CADMXN=X", "GBP": "GBPMXN=X"}
FX_FALLBACK = {"USD": 17.34, "EUR": 18.70, "CAD": 12.70, "GBP": 21.90}
FX_VOL_FB   = {"USD": 0.12, "EUR": 0.10, "CAD": 0.09, "GBP": 0.11}
FX_RF       = {"USD": 0.03625, "EUR": 0.04, "CAD": 0.0275, "GBP": 0.0525}
_FX_CACHE   = {}

def fetch_fx(currency):
    if currency == "MXN":
        return {"spot": 1.0, "vol_30d": 0.0, "source": "identity"}
    cached = _FX_CACHE.get(currency)
    if cached and (datetime.now() - cached["ts"]).seconds < 300:
        return cached["data"]
    try:
        import yfinance as yf
        h = yf.Ticker(FX_TICKERS.get(currency, f"{currency}MXN=X")).history(period="1mo")["Close"]
        spot = float(h.iloc[-1])
        lr = np.log(h / h.shift(1)).dropna()
        vol = float(lr.std() * np.sqrt(252)) if len(lr) > 1 else FX_VOL_FB.get(currency, 0.12)
        data = {"spot": spot, "vol_30d": vol, "source": "live"}
    except Exception:
        data = {"spot": FX_FALLBACK.get(currency, 17.34),
                "vol_30d": FX_VOL_FB.get(currency, 0.12), "source": "fallback"}
    _FX_CACHE[currency] = {"data": data, "ts": datetime.now()}
    return data

# ── Garman-Kohlhagen 1983 ──────────────────────────────────────────────────────
def gk_option(S, K, r_d, r_f, sigma, T, opt_type):
    if T <= 1e-9 or sigma <= 1e-9:
        intrinsic = max(S - K, 0) if opt_type == "call" else max(K - S, 0)
        return {"price": intrinsic, "delta": 1.0 if opt_type == "call" else -1.0}
    d1 = (math.log(S / K) + (r_d - r_f + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if opt_type == "call":
        price = S * math.exp(-r_f * T) * norm.cdf(d1) - K * math.exp(-r_d * T) * norm.cdf(d2)
        delta = math.exp(-r_f * T) * norm.cdf(d1)
    else:
        price = K * math.exp(-r_d * T) * norm.cdf(-d2) - S * math.exp(-r_f * T) * norm.cdf(-d1)
        delta = -math.exp(-r_f * T) * norm.cdf(-d1)
    return {"price": price, "delta": delta}

def calc_premium(txn):
    c = txn["moneda"]
    if c == "MXN":
        return {"premium_unit": 0, "premium_total_mxn": 0, "premium_pct": 0,
                "spot": 1.0, "vol_30d": 0, "source": "identity"}
    fx = fetch_fx(c)
    S_spot, sigma = fx["spot"], fx["vol_30d"]
    T = max((datetime.strptime(txn["fecha"], "%Y-%m-%d").date() - date.today()).days / 365.0, 1 / 365)
    # Obligación (payable) → necesitas comprar divisa → CALL
    # Derecho (receivable) → recibirás divisa → PUT
    opt_type = "call" if txn["tipo"] == "obligacion" else "put"
    opt = gk_option(S_spot, float(txn["strike"]), 0.065, FX_RF.get(c, 0.03), sigma, T, opt_type)
    unit = opt["price"]
    total = unit * float(txn["monto"])
    return {
        "premium_unit":      round(unit, 4),
        "premium_total_mxn": round(total, 2),
        "premium_pct":       round(unit / S_spot * 100, 4) if S_spot > 0 else 0,
        "spot":              round(S_spot, 4),
        "vol_30d":           round(sigma, 4),
        "option_type":       opt_type,
        "T":                 round(T, 4),
        "delta":             round(opt["delta"], 4),
        "source":            fx["source"],
    }

# ── Monte Carlo (GBM, 500 sim) ─────────────────────────────────────────────────
def run_monte_carlo(currency, target_dates_str, n_sim=500):
    fx = fetch_fx(currency)
    spot, sigma = fx["spot"], fx["vol_30d"]
    mu = 0.065 - FX_RF.get(currency, 0.03)   # risk-neutral drift
    today = date.today()
    parsed = [datetime.strptime(d, "%Y-%m-%d").date() for d in target_dates_str]
    total_days = max((max(parsed) - today).days, 1)
    n_steps = min(total_days, 252)
    dt = (total_days / 365.0) / n_steps

    np.random.seed(42)
    paths = np.zeros((n_sim, n_steps + 1))
    paths[:, 0] = spot
    for t in range(1, n_steps + 1):
        z = np.random.standard_normal(n_sim)
        paths[:, t] = paths[:, t - 1] * np.exp((mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * z)

    idx = np.linspace(0, n_steps, min(60, n_steps + 1), dtype=int)
    labels = [
        date.fromordinal(today.toordinal() + int(i * total_days / n_steps)).strftime("%Y-%m-%d")
        for i in idx
    ]

    txn_dist = {}
    for d_str in target_dates_str:
        d = datetime.strptime(d_str, "%Y-%m-%d").date()
        step = min(int(max((d - today).days, 0) / total_days * n_steps), n_steps)
        f = paths[:, step]
        txn_dist[d_str] = {k: round(float(v), 4) for k, v in {
            "p5": np.percentile(f, 5), "p25": np.percentile(f, 25),
            "p50": np.percentile(f, 50), "p75": np.percentile(f, 75),
            "p95": np.percentile(f, 95), "mean": np.mean(f), "std": np.std(f),
        }.items()}

    return {
        "currency":  currency,
        "spot":      round(spot, 4),
        "sigma":     round(sigma, 4),
        "labels":    labels,
        "p5":        [round(float(np.percentile(paths[:, i], 5)), 4) for i in idx],
        "p25":       [round(float(np.percentile(paths[:, i], 25)), 4) for i in idx],
        "p50":       [round(float(np.percentile(paths[:, i], 50)), 4) for i in idx],
        "p75":       [round(float(np.percentile(paths[:, i], 75)), 4) for i in idx],
        "p95":       [round(float(np.percentile(paths[:, i], 95)), 4) for i in idx],
        "txn_dist":  txn_dist,
    }

# ── Natural Hedge Detection ────────────────────────────────────────────────────
def detect_natural_hedges(txns, window=30):
    by_c = {}
    for t in txns:
        c = t["moneda"]
        if c not in by_c:
            by_c[c] = {"obligaciones": [], "derechos": []}
        by_c[c]["obligaciones" if t["tipo"] == "obligacion" else "derechos"].append(t)
    result = []
    for currency, flows in by_c.items():
        for obl in flows["obligaciones"]:
            d1 = datetime.strptime(obl["fecha"], "%Y-%m-%d").date()
            for der in flows["derechos"]:
                d2 = datetime.strptime(der["fecha"], "%Y-%m-%d").date()
                diff = abs((d1 - d2).days)
                if diff <= window:
                    m = min(float(obl["monto"]), float(der["monto"]))
                    result.append({
                        "obl_id": obl["id"], "der_id": der["id"],
                        "currency": currency, "days_diff": diff,
                        "monto_neteado": round(m, 2),
                        "pct_obl": round(m / float(obl["monto"]) * 100, 1),
                        "pct_der": round(m / float(der["monto"]) * 100, 1),
                    })
    return result

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/macro")
def api_macro():
    return jsonify({"macro": MACRO_DATA, "charts": CHART_DATA})

@app.route("/api/market")
def api_market():
    return jsonify({c: fetch_fx(c) for c in ["USD", "EUR", "CAD", "GBP"]})

@app.route("/api/transactions", methods=["GET"])
def get_transactions():
    return jsonify(load_txns())

@app.route("/api/transactions", methods=["POST"])
def add_transaction():
    d = request.get_json()
    txns = load_txns()
    txn = {
        "id":           str(uuid.uuid4())[:8],
        "nombre":       d["nombre"],
        "monto":        float(d["monto"]),
        "tipo":         d["tipo"],       # obligacion | derecho
        "moneda":       d["moneda"],     # USD | MXN | EUR | CAD | GBP
        "strike":       float(d["strike"]),
        "fecha":        d["fecha"],
        "cobertura_pct": 0,
        "prima":        None,
    }
    try:
        txn["prima"] = calc_premium(txn)
    except Exception as e:
        txn["prima"] = {"error": str(e), "premium_total_mxn": 0, "premium_pct": 0, "spot": 0, "vol_30d": 0}
    txns.append(txn)
    save_txns(txns)
    return jsonify(txn), 201

@app.route("/api/transactions/<tid>", methods=["DELETE"])
def del_transaction(tid):
    save_txns([t for t in load_txns() if t["id"] != tid])
    return jsonify({"ok": True})

@app.route("/api/transactions/<tid>/hedge", methods=["POST"])
def set_hedge(tid):
    pct = float(request.get_json().get("pct", 0))
    txns = load_txns()
    for t in txns:
        if t["id"] == tid:
            t["cobertura_pct"] = max(0.0, min(100.0, pct))
    save_txns(txns)
    return jsonify({"ok": True})

@app.route("/api/recalculate", methods=["POST"])
def recalculate():
    _FX_CACHE.clear()
    txns = load_txns()
    for t in txns:
        try:
            t["prima"] = calc_premium(t)
        except Exception as e:
            t["prima"] = {"error": str(e), "premium_total_mxn": 0}
    save_txns(txns)
    return jsonify(txns)

@app.route("/api/montecarlo")
def api_montecarlo():
    txns = load_txns()
    if not txns:
        return jsonify({})
    results = {}
    for c in set(t["moneda"] for t in txns if t["moneda"] != "MXN"):
        dates = [t["fecha"] for t in txns if t["moneda"] == c]
        try:
            results[c] = run_monte_carlo(c, dates)
        except Exception as e:
            results[c] = {"error": str(e)}
    return jsonify(results)

@app.route("/api/summary")
def api_summary():
    txns = load_txns()
    total_prima = exp_sin = exp_con = 0.0
    for t in txns:
        spot = fetch_fx(t["moneda"])["spot"]
        mxn_val = float(t["monto"]) * spot
        pct = t.get("cobertura_pct", 0) / 100
        prima_full = (t.get("prima") or {}).get("premium_total_mxn", 0) or 0
        total_prima += prima_full * pct
        exp_sin += mxn_val
        exp_con += mxn_val * (1 - pct)
    saved = exp_sin - exp_con
    return jsonify({
        "total_prima_mxn":   round(total_prima, 2),
        "exposure_sin":      round(exp_sin, 2),
        "exposure_con":      round(exp_con, 2),
        "exposure_ahorrada": round(saved, 2),
        "pct_cubierto":      round(saved / exp_sin * 100, 1) if exp_sin > 0 else 0,
    })

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n  FX Cobertura Dashboard")
    print("  http://localhost:5000\n")
    app.run(debug=True, port=5000)
