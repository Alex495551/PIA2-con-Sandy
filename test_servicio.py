"""Flujo completo con la base real de prueba: procesar, anular, cerrar día, importar PL."""
from __future__ import annotations

import datetime as dt
import io

import openpyxl
import pandas as pd

from conftest import aplicar_caso, cargar_caso


def test_anular_pedido_devuelve_el_stock_y_se_puede_reprocesar(bd):
    from core import db, servicio

    r1 = aplicar_caso(cargar_caso("A"))
    antes = db.leer("asignaciones")
    ped = "8031725435"
    cajas_ped = antes[antes["pedido"].astype(str) == ped]["cajas"].astype(float).sum()
    assert cajas_ped > 0
    r = servicio.anular(ped)
    assert r["borradas"] > 0
    despues = db.leer("asignaciones")
    assert (despues["pedido"].astype(str) == ped).sum() == 0
    assert len(despues) == len(antes) - r["borradas"]
    # las líneas del pedido quedan sin estado y al reprocesar se asignan de nuevo
    lineas = {l.pedido: l for l in servicio.leer_lineas()}
    assert all(l.estado == "" for l in servicio.leer_lineas() if l.pedido == ped)
    servicio.procesar()
    final = db.leer("asignaciones")
    assert final[final["pedido"].astype(str) == ped]["cajas"].astype(float).sum() == cajas_ped


def test_cerrar_dia_pasa_a_historial_y_limpia(bd):
    from core import db, servicio

    aplicar_caso(cargar_caso("A"))
    n_asig, n_hist = len(db.leer("asignaciones")), len(db.leer("historial"))
    n_ped = len(db.leer("pedidos"))
    r = servicio.cerrar_dia(dt.date(2026, 11, 10))
    assert r == {"asignaciones": n_asig, "pedidos": n_ped}
    assert len(db.leer("asignaciones")) == 0 and len(db.leer("pedidos")) == 0
    h = db.leer("historial")
    assert len(h) == n_hist + n_asig
    assert (h["fecha_cierre"] == "2026-11-10").sum() == n_asig
    assert len(db.leer("hist_pedidos")) == n_ped


def test_estado_editable_de_asignaciones(bd):
    from core import db, servicio

    aplicar_caso(cargar_caso("A"))
    assert servicio.actualizar_estados_asignaciones({0: "En picking", 1: "Despachado", 2: "Inventado"}) == 2
    est = db.leer("asignaciones")["estado"].tolist()
    assert est[:3] == ["En picking", "Despachado", "Pendiente"]


def test_importar_pl_formato_control_de_despacho():
    from core.carga_datos import importar_pl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws["C4"], ws["G4"], ws["G6"] = "CHINCHA", dt.datetime(2026, 11, 10), 8031700995
    ws["G8"] = "Cantidad"
    filas = [(12129185, "6252B0882L", 288), (12270284, "", 416), ("TOTAL", "", 5)]
    for i, (c, lote, q) in enumerate(filas, 9):
        ws.cell(row=i, column=2, value=c)
        ws.cell(row=i, column=5, value=lote)
        ws.cell(row=i, column=7, value=q)
    buf = io.BytesIO()
    wb.save(buf)
    lineas = importar_pl(buf, "PL.xlsx")
    assert [(l["pedido"], l["destino"], l["codigo"], l["lote"], l["cantidad"]) for l in lineas] == [
        ("8031700995", "CHINCHA", "12129185", "6252B0882L", 288.0), ("8031700995", "CHINCHA", "12270284", "", 416.0)]
    assert lineas[0]["fecha"] == dt.date(2026, 11, 10)


def test_sin_stock_cargado_no_revienta(tmp_path, monkeypatch):
    monkeypatch.setenv("PICKING_DB", str(tmp_path / "vacia.db"))
    from core import servicio

    assert "error" in servicio.procesar()
    assert servicio.calcular_dia().ctx is None
    assert servicio.indicadores()["lineas"] == 0


def test_stock_con_columnas_faltantes_da_mensaje_claro():
    import pytest

    from core.carga_datos import cargar_stock
    from core.config import construir_cfg

    with pytest.raises(ValueError, match="DISPONIBLE"):
        cargar_stock(pd.DataFrame({"LOC CODE": ["G_01_1_1"], "INVT LEV1": ["1"], "INVT LEV4": ["A"], "HOLD CODE": ["*"]}),
                     construir_cfg({}))
