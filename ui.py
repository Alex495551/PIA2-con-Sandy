"""Utilidades de interfaz compartidas por todas las páginas (estilo, encabezados, caché del día)."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from core import db, servicio
from core.carga_datos import fmt_fecha

INK = "#0d1117"
MUTED = "#6b7280"
LINEA = "#e5e7eb"
AZUL = "#2f80ed"
VERDE = "#12a150"
GRIS = "#8c96a8"
AMBAR = "#e0a100"
ROJO = "#d92d20"

COLOR_ESTADO_POS = {
    "LLENA": VERDE,
    "SALDO BAJO": AMBAR,
    "VACIA": "#dbe3ee",
    "OCUPADA POR OTRO CODIGO": ROJO,
    "BLOQUEADA": "#7c3aed",
    "SE LLENA CON REABASTECIMIENTO": AZUL,
    "SIN COLUMNAS ASIGNADAS": GRIS,
    "SIN ASIGNAR": "#f3f4f6",
    "OCUPADA SIN ASIGNAR": "#f08a4b",
}

CSS = f"""
<style>
html, body, .stApp {{ font-family: 'Inter', 'Segoe UI', system-ui, sans-serif; }}
[data-testid="stIconMaterial"], span[class*="material-symbols"] {{ font-family: 'Material Symbols Rounded' !important; }}
.block-container {{ padding-top: 2rem; max-width: 1400px; }}
h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
.pk-sub {{ color: {MUTED}; margin: -0.6rem 0 1.2rem 0; font-size: 0.98rem; }}
.pk-card {{ border: 1px solid {LINEA}; border-radius: 12px; padding: 14px 16px; background: #fff; }}
.pk-card .v {{ font-size: 1.9rem; font-weight: 700; color: {INK}; line-height: 1.1; }}
.pk-card .t {{ color: {MUTED}; font-size: 0.82rem; text-transform: uppercase; letter-spacing: .04em; }}
.pk-chip {{ display:inline-block; padding:2px 10px; margin:0 6px 6px 0; border-radius:999px; font-size:.78rem; color:#fff; }}
.pk-paso {{ border-left: 3px solid {AZUL}; padding: 2px 0 2px 12px; margin: 6px 0; color: {INK}; }}
</style>
"""


def iniciar(titulo: str, subtitulo: str = "", icono: str = "📦") -> None:
    try:  # si app.py ya lo llamó, se ignora
        st.set_page_config(page_title=f"{titulo} · Picking Nestlé", page_icon=icono, layout="wide")
    except st.errors.StreamlitAPIException:
        pass
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(f"{icono} {titulo}")
    if subtitulo:
        st.markdown(f'<div class="pk-sub">{subtitulo}</div>', unsafe_allow_html=True)
    with st.sidebar:
        st.caption("Sistema de picking Nestlé · réplica del Excel v6 (VBA v5.2)")
        ruta = db.ruta_db()
        st.caption(f"Base de datos: {ruta.name}")


def tarjeta(titulo: str, valor, color: str = INK) -> str:
    return (f'<div class="pk-card"><div class="t">{titulo}</div>'
            f'<div class="v" style="color:{color}">{valor}</div></div>')


def fila_tarjetas(items: list[tuple[str, object, str]]) -> None:
    cols = st.columns(len(items))
    for c, (t, v, col) in zip(cols, items):
        c.markdown(tarjeta(t, v, col), unsafe_allow_html=True)


def entero(x) -> str:
    try:
        return f"{int(round(float(x))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(x)


def _mtime() -> int:
    r = db.ruta_db()
    return r.stat().st_mtime_ns if r.exists() else 0


@st.cache_resource(show_spinner="Calculando el estado del día…")
def _dia_cache(mtime: int, conteo: bool):
    return servicio.calcular_dia(con_conteo=conteo)


def dia(con_conteo: bool = False) -> servicio.Dia:
    """Estado calculado del día (se recalcula solo cuando cambia la base de datos)."""
    return _dia_cache(_mtime(), con_conteo)


def para_mostrar(df: pd.DataFrame, fechas: tuple[str, ...] = ()) -> pd.DataFrame:
    """Copia lista para st.dataframe: fechas dd/mm/aaaa y enteros sin decimales."""
    d = df.copy()
    for c in fechas:
        if c in d.columns:
            d[c] = d[c].map(lambda v: fmt_fecha(v) if v not in (None, "") and not pd.isna(v) else "")
    return d


def sin_datos(msg: str = "No hay STOCK cargado. Ve a «Cargar datos» y sube el inventario del Korber.") -> None:
    st.warning(msg)


def boton_descarga(etiqueta: str, datos: bytes, nombre: str, mime: str, **kw):
    return st.download_button(etiqueta, datos, file_name=nombre, mime=mime, **kw)


MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HOY = dt.date.today

