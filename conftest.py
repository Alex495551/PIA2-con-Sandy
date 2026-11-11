"""Fixtures comunes: cada test trabaja con su propia base SQLite temporal (nunca toca data/picking.db)."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden"
sys.path.insert(0, str(RAIZ))


@pytest.fixture()
def bd(tmp_path, monkeypatch):
    """Base temporal con los datos reales del Excel (stock, maestro, abast, conteo, entradas de prueba)."""
    destino = tmp_path / "picking.db"
    shutil.copy(GOLDEN / "base_prueba.db", destino)
    monkeypatch.setenv("PICKING_DB", str(destino))
    return destino


def cargar_caso(nombre: str) -> dict:
    return json.loads((GOLDEN / f"caso_{nombre}.json").read_text(encoding="utf-8"))


def aplicar_caso(caso: dict) -> dict:
    """Escribe pedidos y config del caso en la BD y procesa (igual que 'Procesar pedidos')."""
    import pandas as pd

    from core import db, servicio

    mapa = {"C5": "umbral", "C9": "sumar_on_ord", "K17": "reab_ord", "K16": "sust_lote", "K5": "entradas_sin_ubic"}
    cfg = {}
    for celda, v in caso.get("config", {}).items():
        cfg[mapa[celda]] = (v if isinstance(v, (int, float)) else str(v).upper().startswith("S"))
    if cfg:
        db.set_config(cfg)
    filas = [{"pedido": p["pedido"], "destino": p["destino"], "fecha": p["fecha"], "codigo": p["codigo"],
              "lote": p["lote"], "cantidad": p["cantidad"], "usar_clie": p["usar_clie"]} for p in caso["pedidos"]]
    db.guardar("pedidos", pd.DataFrame(filas, columns=db.COLUMNAS["pedidos"]))
    return servicio.procesar()
