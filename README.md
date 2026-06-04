# Arauco Exposure Research Dashboard

Equipo 1 TEC GDL — International Financial Management 2026

## Archivos del proyecto

```
ARRAUCOS APP/
├── app.py              ← Servidor Flask (Python) — app principal
├── requirements.txt    ← Dependencias (solo: flask)
├── index.html          ← Versión standalone (sin Python, abre directo en navegador)
├── templates/
│   ├── base.html       ← Layout base con nav, Kowalski y estilos
│   ├── home.html       ← Página de inicio con contraseña
│   ├── menu.html       ← Menú principal
│   ├── macro.html      ← Variables macroeconómicas + gráficas
│   ├── riesgos.html    ← Mapa de riesgos + semáforo
│   └── cobertura.html  ← Estrategia de cobertura FX
└── static/             ← (para imágenes, CSS extra, etc.)
```

## Opción A — Abrir sin Python (más fácil)

Haz doble clic en `index.html` → se abre en el navegador directamente.

## Opción B — Ejecutar con Flask (recomendado para desarrollo)

1. Instala Python desde https://python.org (marca "Add to PATH")
2. Abre una terminal en esta carpeta y ejecuta:

```bash
pip install flask
python app.py
```

3. Abre http://localhost:5000 en tu navegador
4. Contraseña de acceso: **arauco2026**

## Páginas disponibles

| Ruta         | Descripción                          |
|--------------|--------------------------------------|
| `/`          | Home — acceso con contraseña         |
| `/menu`      | Menú de navegación                   |
| `/macro`     | Variables macroeconómicas + gráficas |
| `/riesgos`   | Mapa de riesgos y oportunidades      |
| `/cobertura` | Estrategia de cobertura FX           |
| `/api/macro` | JSON con todos los datos macro       |
| `/api/charts`| JSON con series históricas           |
| `/api/risks` | JSON con mapa de riesgos             |

## Para actualizar los datos

Edita las variables en `app.py`:
- `MACRO_DATA` — todos los indicadores clave
- `CHART_DATA` — series históricas para las gráficas
- `RISKS` — tarjetas de riesgo/oportunidad
- `HEDGING` — instrumentos de cobertura
- `EQUIPO` — integrantes del equipo
- `ACCESS_PASSWORD` — contraseña de acceso

## Contraseña

`arauco2026` (cámbiala en `app.py` → variable `ACCESS_PASSWORD`)
