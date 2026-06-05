"""
Arauco Exposure Research Dashboard — Flask App
Equipo 1 TEC GDL · International Financial Management 2026
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import json
import math

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
        "icon": "📜",
        "titulo": "Revisión USMCA 2026",
        "nivel": "ALTO",
        "clase": "rla",
        "color_border": "rgba(239,68,68,.4)",
        "descripcion": "Renegociación activa entre México, EE.UU. y Canadá. Alta incertidumbre sobre aranceles a bienes industriales. México bajo presión en acero y aluminio.",
        "impacto": "Aranceles a paneles desde Zitácuaro y Chihuahua eliminarían la ventaja competitiva del nearshoring para Arauco.",
    },
    {
        "icon": "💵",
        "titulo": "Deuda USD ~$7.2B",
        "nivel": "ALTO",
        "clase": "rla",
        "color_border": "rgba(239,68,68,.4)",
        "descripcion": "La deuda está denominada en USD. Con la Fed en pausa y el diferencial de tasas comprimiéndose, el costo relativo aumenta con la depreciación del MXN.",
        "impacto": "La proyección 17.5–18.5 MXN/USD implica presión adicional en H2-2026 sobre el servicio de la deuda expresado en pesos.",
    },
    {
        "icon": "📊",
        "titulo": "Contracción PIB México Q1-2026",
        "nivel": "ALTO",
        "clase": "rla",
        "color_border": "rgba(239,68,68,.4)",
        "descripcion": "México contrajo –0.8% en Q1-2026. Banxico revisó forecast 2026 a 1.0–1.2%. Austeridad fiscal, incertidumbre comercial y desaceleración industrial.",
        "impacto": "Menor demanda de muebles y construcción. Plantas MX dependen más del canal de exportación a EE.UU.",
    },
    {
        "icon": "💱",
        "titulo": "Volatilidad USD/MXN",
        "nivel": "MEDIO",
        "clase": "rlm",
        "color_border": "rgba(245,158,11,.4)",
        "descripcion": "El diferencial de tasas se comprimió de ~7.6% a ~2.875%. Carry trade en retroceso. Consenso: depreciación moderada hacia 17.5–18.5 a fin de 2026.",
        "impacto": "(1) Ingresos USD generan menos pesos. (2) Insumos USD más baratos. (3) Competitividad exportadora mejora con depreciación.",
    },
    {
        "icon": "🛢️",
        "titulo": "Energía y Geopolítica EE.UU.-Irán",
        "nivel": "MEDIO",
        "clase": "rlm",
        "color_border": "rgba(245,158,11,.4)",
        "descripcion": "Conflicto EE.UU.-Irán elevó el WTI a ~$84/barril. Inflación energética global +17.9%. Mantiene a la Fed restrictiva.",
        "impacto": "Eleva costos de transporte y energía en plantas MX y norteamericanas. Impide recortes Fed → costo USD debt elevado.",
    },
    {
        "icon": "📉",
        "titulo": "Pulpa BHKP en Mínimos Cíclicos",
        "nivel": "MEDIO",
        "clase": "rlm",
        "color_border": "rgba(245,158,11,.4)",
        "descripcion": "BHKP cotiza en USD 480–520/ton (FOEX). El segmento Pulpa representa ~50% de los ingresos de Arauco.",
        "impacto": "Presión en márgenes. Mayor importancia relativa del segmento Paneles MX para compensar debilidad en pulpa.",
    },
    {
        "icon": "🏠",
        "titulo": "Construcción Residencial EE.UU.",
        "nivel": "MEDIO",
        "clase": "rlm",
        "color_border": "rgba(245,158,11,.4)",
        "descripcion": "Tasas hipotecarias elevadas desaceleran el mercado de vivienda americano. Recuperación no esperada antes de 2027.",
        "impacto": "Demanda reducida de OSB y paneles estructurales en 8 plantas norteamericanas de Arauco.",
    },
    {
        "icon": "🏭",
        "titulo": "Boom Nearshoring",
        "nivel": "OPORTUNIDAD",
        "clase": "rlo",
        "color_border": "rgba(0,200,255,.35)",
        "descripcion": "México atrajo USD 40.9B de IED en 9M-2025 (+14.5% a/a). La guerra EE.UU.-China redirige manufactura a México. Greenfield se triplicó a $6.56B.",
        "impacto": "Plantas Zitácuaro, Chihuahua y Durango son proveedores estratégicos de instalaciones industriales nearshoring.",
    },
    {
        "icon": "🌿",
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

# ── Options Pricing ───────────────────────────────────────────────────────────

def gk_option(S, K, r_d, r_f, sigma, T, option_type):
    """Garman-Kohlhagen 1983. option_type='call'|'put'. Returns dict {price,delta,d1,d2}."""
    from scipy.stats import norm
    if T <= 1e-9 or sigma <= 1e-9:
        intrinsic = max(S - K, 0) if option_type == "call" else max(K - S, 0)
        return {"price": intrinsic, "delta": 1.0 if option_type == "call" else -1.0, "d1": 0.0, "d2": 0.0}
    d1 = (math.log(S / K) + (r_d - r_f + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == "call":
        price = S * math.exp(-r_f * T) * norm.cdf(d1) - K * math.exp(-r_d * T) * norm.cdf(d2)
        delta = math.exp(-r_f * T) * norm.cdf(d1)
    else:
        price = K * math.exp(-r_d * T) * norm.cdf(-d2) - S * math.exp(-r_f * T) * norm.cdf(-d1)
        delta = -math.exp(-r_f * T) * norm.cdf(-d1)
    return {"price": price, "delta": delta, "d1": d1, "d2": d2}


def fetch_usdmxn(fallback=17.30):
    """Spot live + vol histórica 30d de Yahoo Finance. Returns {spot, vol_30d, source}."""
    try:
        import yfinance as yf
        import numpy as np
        ticker = yf.Ticker("USDMXN=X")
        h1d = ticker.history(period="1d")
        spot = float(h1d["Close"].iloc[-1]) if not h1d.empty else fallback
        h1mo = ticker.history(period="1mo")["Close"]
        log_ret = np.log(h1mo / h1mo.shift(1)).dropna()
        vol_30d = float(log_ret.std() * np.sqrt(252)) if len(log_ret) > 1 else 0.12
        return {"spot": spot, "vol_30d": vol_30d, "source": "live"}
    except Exception:
        return {"spot": fallback, "vol_30d": 0.12, "source": "fallback"}


@app.route("/opciones")
def opciones():
    """Calculadora de Opciones FX — Garman-Kohlhagen 1983."""
    return render_template("opciones.html", macro=MACRO_DATA)


@app.route("/api/opciones", methods=["POST"])
def api_opciones():
    """Pricing endpoint: GK 1983 + spot/vol live de yfinance."""
    try:
        import numpy as np
        p        = request.get_json()
        position = p["position"]            # 'receivables' | 'payables' | 'interest'
        notional = float(p["notional"])     # USD total expuesto
        hedge    = float(p["hedge"])        # USD a cubrir
        K        = float(p["strike"])       # USD/MXN
        r_d      = float(p["rate_mxn"])
        r_f      = float(p["rate_usd"])
        hm       = int(p["horizon_months"])
        T        = hm / 12.0

        mkt   = fetch_usdmxn(fallback=MACRO_DATA["usd_mxn"]["actual"])
        S     = mkt["spot"]
        sigma = mkt["vol_30d"]

        opt_type = "put" if position == "receivables" else "call"
        opt      = gk_option(S, K, r_d, r_f, sigma, T, opt_type)

        premium_unit = opt["price"]                         # MXN por USD de nocional
        premium_usd  = premium_unit * hedge / S             # costo total en USD
        premium_pct  = (premium_usd / notional * 100) if notional > 0 else 0.0
        F            = S * math.exp((r_d - r_f) * T)
        break_even   = (K - premium_unit) if opt_type == "put" else (K + premium_unit)

        # Payoff curve — 60 puntos entre 0.70·S y 1.30·S
        S_arr = np.linspace(S * 0.70, S * 1.30, 60)
        eff   = (np.maximum(S_arr, K) - premium_unit if opt_type == "put"
                 else np.minimum(S_arr, K) + premium_unit)

        return jsonify({
            "spot":         round(S, 4),
            "vol_30d":      round(sigma, 4),
            "vol_source":   mkt["source"],
            "option_type":  opt_type,
            "premium_unit": round(premium_unit, 4),
            "premium_usd":  round(premium_usd, 2),
            "premium_pct":  round(premium_pct, 4),
            "delta":        round(opt["delta"], 4),
            "forward":      round(F, 4),
            "break_even":   round(break_even, 4),
            "payoff_x":     [round(v, 4) for v in S_arr.tolist()],
            "payoff_eff":   [round(v, 4) for v in eff.tolist()],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n🐧  Kowalski, Analysis! — Arauco Dashboard iniciando...")
    print("    URL: http://localhost:5000")
    print("    Contraseña: ARAUCO\n")
    app.run(debug=True, port=5000)
