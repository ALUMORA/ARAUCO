"""
Arauco Exposure Research Dashboard — Flask App
Equipo 1 TEC GDL · International Financial Management 2026
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import json

try:
    import numpy as np
    from engine import (
        forward_rate, gk_call, gk_put, gk_delta_call, gk_delta_put,
        zccollar_floor_strike, net_usd_exposure, get_fx_scenarios, scenario_pnl,
        monte_carlo_fx, risk_metrics, budget_rate, ebitda_fx_sensitivity,
        resin_cost_buildup, resin_shock_impact,
        effective_rate_put_buyer, effective_rate_receiver_collar,
    )
    _HAS_ENGINE = True
except ImportError:
    _HAS_ENGINE = False

FX_SCENARIO_MOVES = {
    "Peso Fuerte (+10%)": -0.10,
    "Base Case":           0.00,
    "Estrés (+8%)":       +0.08,
    "Crisis (+20%)":      +0.20,
}

CALC_DEFAULTS = {
    "spot": 17.30, "rate_mxn": 0.085, "rate_usd": 0.045, "vol": 0.12,
    "rev_mxn": 850_000_000, "pct_rev_usd": 0.60,
    "cost_mxn": 620_000_000, "pct_cost_usd": 0.45,
    "debt_usd": 1_500_000, "ebitda_annual": 85_000_000,
    "horizon_months": 6, "hedge_ratio": 0.70, "n_sims": 5000,
    "basket": {
        "Urea":    {"volume_ton_month": 3000, "price_usd_ton": 875.0,  "price_base_usd_ton": 575.0},
        "Fenol":   {"volume_ton_month": 2000, "price_usd_ton": 1150.0, "price_base_usd_ton": 950.0},
        "Metanol": {"volume_ton_month": 1500, "price_usd_ton": 450.0,  "price_base_usd_ton": 380.0},
    },
}

app = Flask(__name__)
app.secret_key = "ARAUCO"

# ── Contraseña de acceso ──────────────────────────────────────────────────────
ACCESS_PASSWORD = "ARAUCO"

# ── Datos macroeconómicos (aquí puedes actualizar los valores fácilmente) ─────
MACRO_DATA = {
    "usd_mxn": {
        "actual": 17.34,
        "forecast_low": 17.5,
        "forecast_high": 18.5,
        "label": "USD/MXN Actual",
        "unit": "MXN/USD",
    },
    "inflacion_mx": {
        "actual": 4.53,
        "meta_banxico": 3.0,
        "techo_banxico": 4.0,
        "forecast_q4": 3.5,
        "label": "Inflación México",
        "unit": "%",
    },
    "inflacion_us": {
        "actual": 3.80,
        "core": 2.8,
        "forecast_full_year": 3.5,
        "label": "Inflación EE.UU. (CPI)",
        "unit": "%",
    },
    "tasa_banxico": {
        "actual": 6.50,
        "pico_2023": 11.25,
        "recorte_acumulado_bps": 475,
        "label": "Tasa Banxico",
        "unit": "%",
    },
    "tasa_fed": {
        "actual": 3.625,
        "rango_low": 3.50,
        "rango_high": 3.75,
        "label": "Tasa Fed Funds",
        "unit": "%",
    },
    "desempleo_mx": {
        "actual": 2.4,
        "informalidad": 54.8,
        "subempleo": 7.0,
        "label": "Desempleo México",
        "unit": "%",
    },
    "desempleo_us": {
        "actual": 4.3,
        "nominas_abril": 115000,
        "salario_hora_yoy": 3.6,
        "label": "Desempleo EE.UU.",
        "unit": "%",
    },
    "pib_mx": {
        "q1_2026": -0.8,
        "forecast_2026_low": 1.0,
        "forecast_2026_high": 1.2,
        "label": "PIB México Q1-2026",
        "unit": "%",
    },
    "pib_us": {
        "forecast_2026": 1.5,
        "crecimiento_2025": 2.0,
        "label": "PIB EE.UU. 2026",
        "unit": "%",
    },
    "ied_nearshoring": {
        "monto_9m_2025": 40.9,
        "crecimiento_yoy": 14.5,
        "greenfield": 6.56,
        "label": "IED Nearshoring MX",
        "unit": "USD B",
    },
    "deuda_arauco": {
        "monto": 7.2,
        "divisa": "USD",
        "label": "Deuda USD Arauco",
        "unit": "USD B",
    },
    "pulpa_bhkp": {
        "precio_low": 480,
        "precio_high": 520,
        "precio_mid": 500,
        "label": "Pulpa BHKP FOEX",
        "unit": "USD/ton",
    },
    "wti": {
        "precio": 84,
        "label": "Petróleo WTI",
        "unit": "USD/barril",
    },
}

# ── Series históricas para gráficas ──────────────────────────────────────────
CHART_DATA = {
    "inflacion": {
        "labels": ["2024", "Q1-25", "Q2-25", "Q3-25", "Q4-25", "Abr-26", "Fcst Q4-26"],
        "mx": [4.66, 3.98, 4.2, 4.45, 4.6, 4.53, 3.5],
        "us": [3.4, 2.9, 2.7, 2.8, 2.9, 3.8, 3.5],
    },
    "tasas": {
        "labels": ["Mar-24","Jun-24","Sep-24","Dic-24","Mar-25","Jun-25","Sep-25","Dic-25","Mar-26","May-26"],
        "banxico": [11.25, 11.0, 10.75, 10.0, 9.0, 8.0, 7.25, 6.75, 6.75, 6.5],
        "fed":     [5.25, 5.25, 5.0, 4.5, 4.25, 3.75, 3.75, 3.625, 3.625, 3.625],
    },
    "desempleo": {
        "labels": ["2023","2024","Q1-25","Q2-25","Q3-25","Q4-25","Q1-26","Abr-26"],
        "mx": [2.8, 2.7, 2.5, 2.6, 2.5, 2.4, 2.4, 2.4],
        "us": [3.7, 4.0, 4.0, 4.1, 4.2, 4.2, 4.2, 4.3],
    },
    "pib": {
        "labels": ["MX 2024","MX 2025e","MX Q1-26","MX Fcst 26","EE.UU. 24","EE.UU. 25","EE.UU. Fcst 26"],
        "valores": [1.5, -0.6, -0.8, 1.1, 2.9, 2.0, 1.7],
        "colores_border": ["#60a5fa","#60a5fa","#ef4444","#60a5fa","#10b981","#10b981","#10b981"],
    },
    "fx": {
        "labels": ["Ene-26","Feb-26","Mar-26","Abr-26","May-26","Jun-26","Ago-26","Oct-26","Dic-26"],
        "spot":         [17.1, 17.2, 17.25, 17.3, 17.34, None, None, None, None],
        "consenso":     [None, None, None, None, 17.34, 17.4, 17.6, 17.9, 18.0],
        "pesimista":    [None, None, None, None, 17.34, 17.5, 17.8, 18.2, 18.47],
    },
    "ied": {
        "labels": ["2020","2021","2022","2023","2024","9M-2025"],
        "total":      [29.1, 31.6, 35.3, 36.7, 40.4, 40.9],
        "greenfield": [1.2, 1.5, 1.8, 2.1, 2.3, 6.56],
    },
    "escenarios_deuda": {
        "labels": ["May-26","Jun-26","Jul-26","Ago-26","Sep-26","Oct-26","Nov-26","Dic-26"],
        "optimista":  [100, 99.8, 99.5, 99.3, 99.1, 98.9, 98.7, 98.6],
        "base":       [100, 100.3, 100.9, 101.7, 102.6, 103.5, 104.1, 104.8],
        "pesimista":  [100, 101.2, 103.1, 105.4, 108.0, 110.2, 111.8, 113.0],
        "cobertura":  [100, 100.1, 100.4, 100.8, 101.2, 101.6, 101.9, 102.2],
    },
}

# ── Riesgos ───────────────────────────────────────────────────────────────────
RISKS = [
    {
        "titulo": "Revisión USMCA 2026",
        "nivel": "ALTO",
        "clase": "rla",
        "color_border": "rgba(239,68,68,.4)",
        "descripcion": "Renegociación activa entre México, EE.UU. y Canadá. Alta incertidumbre sobre aranceles a bienes industriales. México bajo presión en acero y aluminio.",
        "impacto": "Aranceles a paneles desde Zitácuaro y Chihuahua eliminarían la ventaja competitiva del nearshoring para Arauco.",
    },
    {
        "titulo": "Deuda USD ~$7.2B",
        "nivel": "ALTO",
        "clase": "rla",
        "color_border": "rgba(239,68,68,.4)",
        "descripcion": "La deuda está denominada en USD. Con la Fed en pausa y el diferencial de tasas comprimiéndose, el costo relativo aumenta con la depreciación del MXN.",
        "impacto": "La proyección 17.5–18.5 MXN/USD implica presión adicional en H2-2026 sobre el servicio de la deuda expresado en pesos.",
    },
    {
        "titulo": "Contracción PIB México Q1-2026",
        "nivel": "ALTO",
        "clase": "rla",
        "color_border": "rgba(239,68,68,.4)",
        "descripcion": "México contrajo –0.8% en Q1-2026. Banxico revisó forecast 2026 a 1.0–1.2%. Austeridad fiscal, incertidumbre comercial y desaceleración industrial.",
        "impacto": "Menor demanda de muebles y construcción. Plantas MX dependen más del canal de exportación a EE.UU.",
    },
    {
        "titulo": "Volatilidad USD/MXN",
        "nivel": "MEDIO",
        "clase": "rlm",
        "color_border": "rgba(245,158,11,.4)",
        "descripcion": "El diferencial de tasas se comprimió de ~7.6% a ~2.875%. Carry trade en retroceso. Consenso: depreciación moderada hacia 17.5–18.5 a fin de 2026.",
        "impacto": "(1) Ingresos USD generan menos pesos. (2) Insumos USD más baratos. (3) Competitividad exportadora mejora con depreciación.",
    },
    {
        "titulo": "Energía y Geopolítica EE.UU.-Irán",
        "nivel": "MEDIO",
        "clase": "rlm",
        "color_border": "rgba(245,158,11,.4)",
        "descripcion": "Conflicto EE.UU.-Irán elevó el WTI a ~$84/barril. Inflación energética global +17.9%. Mantiene a la Fed restrictiva.",
        "impacto": "Eleva costos de transporte y energía en plantas MX y norteamericanas. Impide recortes Fed → costo USD debt elevado.",
    },
    {
        "titulo": "Pulpa BHKP en Mínimos Cíclicos",
        "nivel": "MEDIO",
        "clase": "rlm",
        "color_border": "rgba(245,158,11,.4)",
        "descripcion": "BHKP cotiza en USD 480–520/ton (FOEX). El segmento Pulpa representa ~50% de los ingresos de Arauco.",
        "impacto": "Presión en márgenes. Mayor importancia relativa del segmento Paneles MX para compensar debilidad en pulpa.",
    },
    {
        "titulo": "Construcción Residencial EE.UU.",
        "nivel": "MEDIO",
        "clase": "rlm",
        "color_border": "rgba(245,158,11,.4)",
        "descripcion": "Tasas hipotecarias elevadas desaceleran el mercado de vivienda americano. Recuperación no esperada antes de 2027.",
        "impacto": "Demanda reducida de OSB y paneles estructurales en 8 plantas norteamericanas de Arauco.",
    },
    {
        "titulo": "Boom Nearshoring",
        "nivel": "OPORTUNIDAD",
        "clase": "rlo",
        "color_border": "rgba(0,200,255,.35)",
        "descripcion": "México atrajo USD 40.9B de IED en 9M-2025 (+14.5% a/a). La guerra EE.UU.-China redirige manufactura a México. Greenfield se triplicó a $6.56B.",
        "impacto": "Plantas Zitácuaro, Chihuahua y Durango son proveedores estratégicos de instalaciones industriales nearshoring.",
    },
    {
        "titulo": "Certificaciones FSC/PEFC",
        "nivel": "OPORTUNIDAD",
        "clase": "rlo",
        "color_border": "rgba(0,200,255,.35)",
        "descripcion": "Demanda creciente de materiales certificados en EE.UU. y Europa. Crea barreras de entrada y premios de precio.",
        "impacto": "Ventaja competitiva en mercados premium. Planta Zitácuaro diseñada con estándares ambientales de clase mundial.",
    },
]

# ── Instrumentos de cobertura ─────────────────────────────────────────────────
HEDGING = [
    {
        "num": "01",
        "titulo": "Forwards USD/MXN",
        "descripcion": "Fijar hoy el tipo de cambio para flujos futuros conocidos. Ideal para ingresos de exportación en USD y pagos de deuda programados.",
        "bullets": [
            "Horizonte recomendado: 3–12 meses",
            "Tasa referencia: 17.40–17.60 MXN/USD",
            "% a cubrir: 60–80% de flujos proyectados",
            "Contraparte: bancos con líneas ISDA activas",
        ],
        "pros": ["Certeza de tipo de cambio", "Sin prima"],
        "cons": ["Sin participación en apreciación"],
        "especial": False,
    },
    {
        "num": "02",
        "titulo": "Opciones de Compra USD (USD Call)",
        "descripcion": "Derecho a comprar USD a strike prefijado. Protege contra depreciación MXN sin sacrificar upside.",
        "bullets": [
            "Strike sugerido: 18.00 MXN/USD (OTM)",
            "Vencimiento: diciembre 2026",
            "Prima estimada: 0.8–1.2% del nocional",
            "Activar si el diferencial de tasas continúa comprimiéndose",
        ],
        "pros": ["Cobertura asimétrica", "Upside ilimitado"],
        "cons": ["Costo de prima"],
        "especial": False,
    },
    {
        "num": "03",
        "titulo": "Zero-Cost Collar",
        "descripcion": "Compra de put + venta de call. Financia la prima y define un rango garantizado sin costo neto.",
        "bullets": [
            "Piso (put strike): 17.00 MXN/USD",
            "Techo (call strike): 18.50 MXN/USD",
            "Rango protegido: 17.00–18.50",
            "Costo neto: cero",
        ],
        "pros": ["Sin costo neto", "Rango definido"],
        "cons": ["Cap a la apreciación"],
        "especial": False,
    },
    {
        "num": "04",
        "titulo": "Cobertura Natural",
        "descripcion": "Alinear ingresos y costos en la misma divisa para reducir exposición estructural.",
        "bullets": [
            "Facturar en USD a clientes nearshoring en MX",
            "Negociar insumos críticos en USD vs ingresos USD",
            "Financiar CAPEX MX con créditos MXN (tasas Banxico)",
            "Usar 8 plantas EE.UU. para generar flujos USD",
        ],
        "pros": ["Sin costo directo", "Reduce exposición estructural"],
        "cons": ["No elimina toda la exposición"],
        "especial": False,
    },
    {
        "num": "05",
        "titulo": "Cross-Currency Swap",
        "descripcion": "Intercambio de flujos de deuda USD por MXN a tasa fija. Convierte parte de la deuda USD en deuda MXN.",
        "bullets": [
            "Tramos con vencimiento 2026–2028",
            "Tasa MXN fija ref.: 9.5–10.5%",
            "Nocional sugerido: $500M–$1,000M USD",
            "Horizonte: 2–5 años",
        ],
        "pros": ["Reduce riesgo servicio deuda", "Largo plazo"],
        "cons": ["Complejidad operativa"],
        "especial": False,
    },
    {
        "num": "INTEGRAL",
        "titulo": "Política de Cobertura Recomendada 2026",
        "descripcion": "Estrategia óptima dado: peso fuerte, diferencial en compresión, USMCA incierto, Fed en pausa.",
        "bullets": [
            "60–70% de flujos USD cubiertos con forwards 6–9 meses",
            "20–25% con opciones OTM — protección crisis USMCA",
            "10–15% sin cubrir — capturar apreciación adicional",
            "Revisión trimestral según diferencial tasas y USMCA",
            "Cobertura natural vía facturación USD a nearshoring",
        ],
        "pros": ["Balance óptimo protección/costo", "Flexible ante USMCA"],
        "cons": [],
        "especial": True,
    },
]

# ── Equipo ────────────────────────────────────────────────────────────────────
EQUIPO = [
    {"nombre": "Renata Nikita López Corona",    "matricula": "A01624613"},
    {"nombre": "Roberto Alfonso Díaz Maciel",   "matricula": "A01769427"},
    {"nombre": "Arturo Alejandro Mora Garnica",  "matricula": "A01637219"},
    {"nombre": "Alejandro Martín De la Torre",  "matricula": "A01643778"},
    {"nombre": "Fernanda Espinosa Gómez",        "matricula": "A01734178"},
    {"nombre": "Rodrigo Calderón Huerta",        "matricula": "A01706540"},
]

# ── Login decorator ───────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("autenticado"):
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated

# ── Rutas ─────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    autenticado = session.get("autenticado", False)
    return render_template("home.html", autenticado=autenticado, equipo=EQUIPO)

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if data and data.get("password") == ACCESS_PASSWORD:
        session["autenticado"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Contraseña incorrecta"}), 401

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/menu")
@login_required
def menu():
    return render_template("menu.html", equipo=EQUIPO)

@app.route("/macro")
@login_required
def macro():
    return render_template(
        "macro.html",
        macro=MACRO_DATA,
        charts=json.dumps(CHART_DATA),
    )

@app.route("/riesgos")
@login_required
def riesgos():
    return render_template("riesgos.html", risks=RISKS)

@app.route("/cobertura")
@login_required
def cobertura():
    return render_template(
        "cobertura.html",
        hedging=HEDGING,
        charts=json.dumps(CHART_DATA),
    )

# ── API endpoints (para extender con datos dinámicos) ─────────────────────────
@app.route("/api/macro")
@login_required
def api_macro():
    return jsonify(MACRO_DATA)

@app.route("/api/charts")
@login_required
def api_charts():
    return jsonify(CHART_DATA)

@app.route("/api/risks")
@login_required
def api_risks():
    return jsonify(RISKS)

@app.route("/calculadora")
@login_required
def calculadora():
    return render_template("calculadora.html", defaults=json.dumps(CALC_DEFAULTS))

@app.route("/api/calcular", methods=["POST"])
@login_required
def api_calcular():
    if not _HAS_ENGINE:
        return jsonify({"ok": False, "error": "numpy/scipy no disponibles en este entorno"}), 500
    try:
        p = request.get_json()
        S   = float(p["spot"])
        rd  = float(p["rate_mxn"])
        rf  = float(p["rate_usd"])
        sig = float(p["vol"])
        hm  = int(p["horizon_months"])
        T   = hm / 12
        hr  = float(p["hedge_ratio"])
        ns  = int(p.get("n_sims", 5000))

        rev_mxn      = float(p["rev_mxn"])
        pct_rev_usd  = float(p["pct_rev_usd"])
        cost_mxn     = float(p["cost_mxn"])
        pct_cost_usd = float(p["pct_cost_usd"])
        debt_usd     = float(p["debt_usd"])
        ebitda_ann   = float(p["ebitda_annual"])

        basket    = p.get("basket", CALC_DEFAULTS["basket"])
        shock_pct = {k: float(v) for k, v in p.get("shock_pct", {}).items()}

        # -- Core calculations -----------------------------------------
        F   = forward_rate(S, rd, rf, T)
        exp = net_usd_exposure(rev_mxn, pct_rev_usd, cost_mxn, pct_cost_usd, debt_usd, S)
        sens = ebitda_fx_sensitivity(rev_mxn, pct_rev_usd, cost_mxn, pct_cost_usd, S, ebitda_ann)

        fx_scen = get_fx_scenarios(S, FX_SCENARIO_MOVES)
        scen    = scenario_pnl(exp["net_usd"], S, fx_scen, F, hr, hm)

        K_atm   = F
        c_prem  = gk_call(S, K_atm, rd, rf, sig, T)
        p_prem  = gk_put( S, K_atm, rd, rf, sig, T)
        c_delta = gk_delta_call(S, K_atm, rd, rf, sig, T)
        p_delta = gk_delta_put( S, K_atm, rd, rf, sig, T)

        K_cap_oc = S * 1.04
        K_flr_oc = zccollar_floor_strike(S, K_cap_oc, rd, rf, sig, T)

        S_T = monte_carlo_fx(S, rd, rf, sig, T, ns)
        rm  = risk_metrics(S_T, exp["net_usd"], S, F, hr, hm)
        br  = budget_rate(exp["net_usd"], S, ebitda_ann, hm)

        resin       = resin_cost_buildup(basket, S)
        resin_shock = resin_shock_impact(basket, shock_pct, S) if shock_pct else None

        # -- Payoff curves (80 pts) ------------------------------------
        S_rng = np.linspace(S * 0.70, S * 1.30, 80)
        put_eff    = effective_rate_put_buyer(S_rng, K_atm, p_prem).tolist()
        collar_eff = effective_rate_receiver_collar(S_rng, K_flr_oc, K_cap_oc).tolist()
        s_range    = S_rng.tolist()

        # -- Histogram (50 bins) ----------------------------------------
        pnl_u = rm["pnl_unhedged"] / 1e6
        pnl_h = rm["pnl_hedged"]   / 1e6
        all_v = np.concatenate([pnl_u, pnl_h])
        rng_  = (float(all_v.min()), float(all_v.max()))
        cu, bins = np.histogram(pnl_u, bins=50, range=rng_)
        ch, _    = np.histogram(pnl_h, bins=50, range=rng_)
        mids = ((bins[:-1] + bins[1:]) / 2).tolist()

        return jsonify({
            "ok": True,
            "F": F, "T": T,
            "exp": {k: float(v) for k, v in exp.items() if k != "is_receiver"},
            "exp_is_receiver": exp["is_receiver"],
            "exp_position": exp["position"],
            "sens": {k: float(v) for k, v in sens.items()},
            "scen": [{k: (float(v) if isinstance(v, (int, float)) else v)
                      for k, v in s.items()} for s in scen],
            "options": {
                "K_atm": K_atm, "K_cap_oc": K_cap_oc, "K_flr_oc": K_flr_oc,
                "c_prem": c_prem, "p_prem": p_prem,
                "c_delta": c_delta, "p_delta": p_delta,
            },
            "rm": {
                "var_unhedged":  float(rm["var_unhedged"]),
                "cvar_unhedged": float(rm["cvar_unhedged"]),
                "var_hedged":    float(rm["var_hedged"]),
                "cvar_hedged":   float(rm["cvar_hedged"]),
                "cfar_unhedged": float(rm["cfar_unhedged"]),
                "cfar_hedged":   float(rm["cfar_hedged"]),
                "vol_reduction": float(rm["vol_reduction"]),
            },
            "br": float(br),
            "resin": {
                "total_monthly_usd": float(resin["total_monthly_usd"]),
                "total_monthly_mxn": float(resin["total_monthly_mxn"]),
                "items": {
                    n: {k: float(v) for k, v in d.items()}
                    for n, d in resin["items"].items()
                },
            },
            "resin_shock": {
                "base_usd":    float(resin_shock["base_usd"]),
                "shocked_usd": float(resin_shock["shocked_usd"]),
                "delta_usd":   float(resin_shock["delta_usd"]),
            } if resin_shock else None,
            "payoffs": {
                "S_range": s_range, "put_eff": put_eff, "collar_eff": collar_eff,
                "F": F, "K_atm": K_atm, "K_flr": K_flr_oc, "K_cap": K_cap_oc,
            },
            "histogram": {
                "bin_midpoints": [round(m, 2) for m in mids],
                "counts_u": cu.tolist(),
                "counts_h": ch.tolist(),
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\nArauco Dashboard iniciando...")
    print("    URL: http://localhost:5000")
    print("    Contraseña: ARAUCO\n")
    app.run(debug=True, port=5000)
