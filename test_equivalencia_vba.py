"""Prueba de equivalencia: la app contra la macro real (VBA v5.2 de Picking_Nestle_v6.xlsm).

Los archivos tests/golden/salida_vba_*.json y tests/golden/iffi_*/ se generaron ejecutando la macro
ModPicking.PruebaSilenciosa y GenerarIFFIArchivos en Excel sobre los MISMOS datos (stock, maestro,
abast_cliente, conteo y 4 entradas de prueba) y los MISMOS pedidos (tests/golden/caso_*.json).
 - Caso A: configuración actual del Excel (umbral 5 %, ON ORD = N, sustituir lote = S ...).
 - Caso B: configuración alternativa (umbral 30 %, ON ORD sumado, reabastecer sin descontar ON ORD,
   sin sustitución de lote, sin entradas sin ubicación).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from conftest import GOLDEN, aplicar_caso, cargar_caso


def _n(v):
    """Normaliza un valor para comparar (None == '', números como float, fechas ISO)."""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return ""
    if isinstance(v, (dt.datetime,)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    try:
        return float(s)
    except ValueError:
        return s


def _comparar(nombre, esperado, obtenido, cols, ignorar=()):
    assert len(esperado) == len(obtenido), f"{nombre}: {len(obtenido)} filas, la macro dio {len(esperado)}"
    dif = []
    for i, (e, o) in enumerate(zip(esperado, obtenido)):
        for j, c in enumerate(cols):
            if c in ignorar:
                continue
            if _n(e[j]) != _n(o[j]):
                dif.append(f"{nombre} fila {i + 1} col {c}: macro={e[j]!r} app={o[j]!r}")
    assert not dif, "\n".join(dif[:25]) + f"\n... {len(dif)} diferencias"


@pytest.fixture(params=["A", "B"])
def corrida(request, bd):
    from core import db, servicio

    k = request.param
    resumen = aplicar_caso(cargar_caso(k))
    gold = json.loads((GOLDEN / f"salida_vba_{k}.json").read_text(encoding="utf-8"))
    return k, resumen, gold, servicio, db


def test_lineas_de_pedido(corrida):
    k, resumen, gold, servicio, db = corrida
    ped = db.leer("pedidos")
    obt = [[r.pedido, r.destino, r.fecha, r.codigo, None, r.lote, r.cantidad, None, r.usar_clie, r.estado,
            r.asignado, r.pendiente, r.observacion, r.id_linea] for r in ped.itertuples()]
    cols = ["pedido", "destino", "fecha", "codigo", "desc", "lote", "cantidad", "uma", "clie", "estado",
            "asignado", "pendiente", "observacion", "id_linea"]
    _comparar("PEDIDOS", gold["pedidos"], obt, cols, ignorar=("desc", "uma", "clie"))


def test_asignaciones(corrida):
    k, resumen, gold, servicio, db = corrida
    df = db.leer("asignaciones")
    cols = db.COLUMNAS["asignaciones"]
    obt = df[cols].values.tolist()
    _comparar("ASIGNACIONES", gold["asignaciones"], obt, cols, ignorar=("fecha_proceso",))


def test_reabastecimiento(corrida):
    from core.reabastecimiento import COLS_REAB

    k, resumen, gold, servicio, db = corrida
    dia = servicio.calcular_dia()
    obt = [[r[c] for c in COLS_REAB] for r in dia.reab.filas]
    _comparar("REABASTECIMIENTO", gold["reab"], obt, COLS_REAB)


def test_posiciones_picking(corrida):
    from core.reabastecimiento import COLS_POS

    k, resumen, gold, servicio, db = corrida
    dia = servicio.calcular_dia()
    obt = [[r[c] for c in COLS_POS] for r in dia.reab.posiciones]
    _comparar("POSICIONES", gold["posiciones"], obt, COLS_POS)


def test_estado_abast_cliente(corrida):
    k, resumen, gold, servicio, db = corrida
    ab = db.leer("abast_cliente")
    obt = [[r.codigo, r.texto, r.lote, r.cantidad, r.ubicacion, r.fecha, None, r.estado, r.paleta, r.destino]
           for r in ab.itertuples()]
    _comparar("ABAST_CLIENTE", gold["abast"], obt,
              ["codigo", "texto", "lote", "cant", "ubic", "fecha", "nub", "estado", "paleta", "destino"],
              ignorar=("nub", "cant", "texto"))


def test_conteo_zona(corrida):
    k, resumen, gold, servicio, db = corrida
    cz = db.leer("conteo_zona")
    cols = ["material", "texto", "lote", "um", "sap", "alfrimac", "conteo", "diferencia", "obs"]
    obt = cz[cols].values.tolist()
    # DIFERENCIA CONOCIDA: la fila "Total general" del cliente trae valores pegados que la macro no toca
    # (queda con Exel Alfrimac = 0); la app sí la recalcula. Se compara todo lo demás.
    esoy_total = lambda r: str(r[0]).strip().upper().startswith("TOTAL")  # noqa: E731
    total_app = [r[5] for r in obt if esoy_total(r)]
    suma = sum(r[5] for r in obt if not esoy_total(r) and r[4] is not None)  # filas del cliente (con SAP)
    esperado = [list(r) for r in gold["conteo"]]
    obt = [list(r) for r in obt]
    for lista in (esperado, obt):
        for r in lista:
            if esoy_total(r):
                r[4:8] = [None] * 4
    _comparar("CONTEO_ZONA", esperado, obt, cols, ignorar=("texto",))
    assert total_app and total_app[0] == pytest.approx(suma)


def test_desbloqueos(corrida):
    from core.asignacion import desbloqueos

    k, resumen, gold, servicio, db = corrida
    cfg, ctx, _ = servicio.construir_contexto()
    det, res = desbloqueos(ctx)
    cols = ["Código", "Descripción", "Lote", "ID paleta", "Ubicación", "Hold", "Cajas en paleta",
            "Cajas asignadas", "Pedido(s)", "Destino(s)", "Acción"]
    _comparar("DESBLOQUEOS", gold["desbloq"], [[d[c] for c in cols] for d in det], cols)
    cols2 = ["Código", "Descripción", "Lote a desbloquear", "N° paletas", "Cajas asignadas", "Pedido(s)"]
    _comparar("DESBLOQUEOS resumen", gold["desbloq_res"], [[d[c] for c in cols2] for d in res], cols2)


def test_archivos_iffi(corrida):
    k, resumen, gold, servicio, db = corrida
    esperados = {p.name: p.read_bytes() for p in (GOLDEN / f"iffi_{k}").glob("*.csv")}
    salida = servicio.iffi("", dt.date(2026, 11, 10))
    obtenidos = {s["archivo"]: s["contenido"] for s in salida}
    assert set(obtenidos) == set(esperados), (sorted(obtenidos), sorted(esperados))
    for nombre, contenido in esperados.items():
        assert obtenidos[nombre] == contenido, f"IFFI distinto: {nombre}"
