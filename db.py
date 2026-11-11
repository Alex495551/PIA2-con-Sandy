"""Persistencia en SQLite (data/picking.db). Cada tabla del Excel es una tabla SQL."""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

import pandas as pd

from .config import CONFIG_DEFECTO

RAIZ = Path(__file__).resolve().parent.parent
RUTA_DB_DEFECTO = RAIZ / "data" / "picking.db"

COLUMNAS = {
    "maestro": ["codigo", "descripcion", "cajas_paleta", "uma", "fuente", "bloque", "n_ubic", "columnas"],
    "pedidos": ["pedido", "destino", "fecha", "codigo", "lote", "cantidad", "usar_clie", "estado", "asignado",
                "pendiente", "observacion", "id_linea"],
    "abast_cliente": ["fila", "codigo", "texto", "lote", "cantidad", "ubicacion", "fecha", "estado", "paleta",
                      "destino"],
    "conteo_zona": ["material", "texto", "lote", "um", "sap", "alfrimac", "conteo", "diferencia", "obs"],
    "asignaciones": ["id_linea", "pedido", "destino", "fecha_despacho", "codigo", "descripcion", "lote", "vence",
                     "id_paleta", "ubicacion", "bloque", "columna", "nivel", "profundidad", "zona", "tipo_salida",
                     "cajas", "uma", "orden_recorrido", "estado", "fecha_proceso", "origen"],
    "historial": ["id_linea", "pedido", "destino", "fecha_despacho", "codigo", "descripcion", "lote", "vence",
                  "id_paleta", "ubicacion", "bloque", "columna", "nivel", "profundidad", "zona", "tipo_salida",
                  "cajas", "uma", "orden_recorrido", "estado", "fecha_proceso", "fecha_cierre", "origen"],
    "hist_pedidos": ["pedido", "destino", "fecha", "codigo", "lote", "cantidad", "usar_clie", "estado", "asignado",
                     "pendiente", "observacion", "id_linea", "fecha_cierre"],
    "stock": [],      # columnas del Korber tal cual llegan
    "entradas": [],   # columnas del reporte OP_ENTRADAS tal cual llegan
    "cargas": ["archivo_tipo", "nombre", "filas", "fecha_carga"],
}


def ruta_db() -> Path:
    return Path(os.environ.get("PICKING_DB", RUTA_DB_DEFECTO))


def conectar() -> sqlite3.Connection:
    r = ruta_db()
    r.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(r)
    con.execute("CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)")
    return con


def _a_sql(v):
    """Valores que SQLite no entiende (fechas, NaN, numpy) -> texto/número simples."""
    if v is None:
        return None
    if isinstance(v, (dt.datetime, pd.Timestamp)):
        return None if pd.isna(v) else v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float) and pd.isna(v):
        return None
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            return _a_sql(v.item())
        except Exception:
            return str(v)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def leer(tabla: str) -> pd.DataFrame:
    cols = COLUMNAS.get(tabla, [])
    with conectar() as con:
        try:
            df = pd.read_sql_query(f'SELECT * FROM "{tabla}"', con)
        except Exception:
            return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df.astype(object).where(df.notna(), None)


def guardar(tabla: str, df: pd.DataFrame, agregar: bool = False) -> None:
    """Reemplaza (o agrega a) la tabla con el DataFrame dado."""
    cols = COLUMNAS.get(tabla) or list(df.columns)
    d = df.copy()
    for c in cols:
        if c not in d.columns:
            d[c] = None
    d = d[cols].astype(object)
    d = d.apply(lambda col: col.map(_a_sql))
    d = d.astype(object).where(d.notna(), None)
    with conectar() as con:
        d.to_sql(tabla, con, if_exists="append" if agregar else "replace", index=False)


def vaciar(tabla: str) -> None:
    with conectar() as con:
        con.execute(f'DROP TABLE IF EXISTS "{tabla}"')


def get_config() -> dict:
    cfg = copy.deepcopy(CONFIG_DEFECTO)
    with conectar() as con:
        for k, v in con.execute("SELECT clave, valor FROM config"):
            try:
                cfg[k] = json.loads(v)
            except (TypeError, ValueError):
                cfg[k] = v
    return cfg


def set_config(valores: dict) -> None:
    with conectar() as con:
        for k, v in valores.items():
            con.execute("INSERT INTO config (clave, valor) VALUES (?, ?) "
                        "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (k, json.dumps(v)))


def registrar_carga(tipo: str, nombre: str, filas: int) -> None:
    df = pd.DataFrame([{"archivo_tipo": tipo, "nombre": nombre, "filas": filas,
                        "fecha_carga": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
    guardar("cargas", df, agregar=True)


def ultima_carga(tipo: str) -> dict | None:
    df = leer("cargas")
    df = df[df["archivo_tipo"] == tipo]
    return None if df.empty else df.iloc[-1].to_dict()
