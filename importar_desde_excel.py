"""Migra Picking_Nestle_v6.xlsm a la base SQLite de la app (para no perder el historial).

Uso:
    py scripts/importar_desde_excel.py "ruta\\Picking_Nestle_v6.xlsm" [--db ruta\\picking.db] [--sin-historial]

Lee: MAESTRO, CONFIG, HISTORIAL, HIST_PEDIDOS, ABAST_CLIENTE, STOCK, ENTRADAS (y CONTEO_ZONA, PEDIDOS y
ASIGNACIONES si traen datos). Reemplaza el contenido actual de esas tablas.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl  # noqa: E402
import pandas as pd  # noqa: E402


def _filas(ws, desde=1, hasta=None, cols=None):
    for r in ws.iter_rows(min_row=desde, max_row=hasta, max_col=cols, values_only=True):
        yield list(r)


def _vacio(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def importar(ruta: str, sin_historial: bool = False, log=print) -> dict:
    from core import db
    from core.carga_datos import norm, parse_abast, parse_conteo, texto_pedido, num, parse_fecha
    from core.config import CONFIG_DEFECTO

    resumen = {}
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    hojas = set(wb.sheetnames)

    # ---- MAESTRO (A..I: código, desc, cajas/paleta, UMA, fuente, bloque, N ubic., (vacía), columnas) ----
    if "MAESTRO" in hojas:
        filas = []
        for r in _filas(wb["MAESTRO"], 2, cols=9):
            r += [None] * (9 - len(r))
            if _vacio(r[0]):
                continue
            cols = r[8]
            cols = "" if _vacio(cols) or str(cols).startswith("#") else str(cols).strip()
            filas.append({"codigo": norm(r[0]), "descripcion": r[1], "cajas_paleta": r[2], "uma": r[3] or "CJ",
                          "fuente": r[4], "bloque": r[5], "n_ubic": r[6], "columnas": cols})
        db.guardar("maestro", pd.DataFrame(filas, columns=db.COLUMNAS["maestro"]))
        resumen["maestro"] = len(filas)

    # ---- CONFIG ----
    if "CONFIG" in hojas:
        g = list(_filas(wb["CONFIG"], 1, 70, 12))

        def c(fila, col):  # fila/col estilo Excel (1-based)
            try:
                return g[fila - 1][col - 1]
            except IndexError:
                return None

        def sn(v, d):
            return d if _vacio(v) else str(v).strip().upper().startswith("S")

        def tx(v, d):
            return d if _vacio(v) else str(v).strip()

        cfg = {
            "cliente": tx(c(4, 3), "NESTLE"),
            "umbral": float(c(5, 3)) if not _vacio(c(5, 3)) else CONFIG_DEFECTO["umbral"],
            "excluir": tx(c(6, 3), ""),
            "contador_lineas": int(num(c(7, 3))),
            "sumar_on_ord": sn(c(9, 3), False),
            "usar_entradas": sn(c(4, 11), True),
            "entradas_sin_ubic": sn(c(5, 11), True),
            "iffi_consignee": tx(c(6, 11), "NESTLE"), "iffi_soldto": tx(c(7, 11), "NESTLE"),
            "iffi_almacen": tx(c(8, 11), "CLL1"), "iffi_carrier": tx(c(9, 11), "NA"),
            "iffi_freight": tx(c(10, 11), "NA"), "iffi_load": tx(c(11, 11), "PLT"),
            "nivel_picking": int(num(c(14, 11))) or 1, "profundidades": int(num(c(15, 11))) or 2,
            "sust_lote": sn(c(16, 11), True), "reab_ord": sn(c(17, 11), True),
        }
        zonas = [{"bloque": str(c(r, 2)).strip(), "nivel": "*" if _vacio(c(r, 3)) else str(c(r, 3)).strip()}
                 for r in range(11, 71) if not _vacio(c(r, 2))]
        if zonas:
            cfg["zonas_picking"] = zonas
        hold = [{"codigo": str(c(r, 6)).strip(), "significado": tx(c(r, 7), ""), "uso": tx(c(r, 8), "NO")}
                for r in range(11, 51) if not _vacio(c(r, 6))]
        if hold:
            cfg["hold"] = hold
        db.set_config(cfg)
        resumen["config"] = len(cfg)

    # ---- STOCK / ENTRADAS (encabezados en la fila 1) ----
    for hoja, tabla in (("STOCK", "stock"), ("ENTRADAS", "entradas")):
        if hoja not in hojas:
            continue
        it = _filas(wb[hoja], 1, cols=30)
        cab = next(it, [])
        cab = [str(x) for x in cab if not _vacio(x)]
        n = len(cab)
        filas = [r[:n] for r in it if any(not _vacio(x) for x in r[:n])]
        if tabla == "entradas":
            # la hoja viene con fórmulas/filas vacías: solo las que tienen ID de paleta (RCPT LEV4)
            k = cab.index("RCPT LEV4") if "RCPT LEV4" in cab else None
            if k is not None:
                filas = [r for r in filas if not _vacio(r[k])]
        df = pd.DataFrame(filas, columns=cab)
        if len(df):
            db.guardar(tabla, df)
        else:
            db.vaciar(tabla)
        resumen[tabla] = len(df)

    # ---- ABAST_CLIENTE y CONTEO_ZONA (grilla cruda -> parser del cliente) ----
    if "ABAST_CLIENTE" in hojas:
        raw = pd.DataFrame(list(_filas(wb["ABAST_CLIENTE"], 1, cols=12)))
        ab = parse_abast(raw)
        for col in ("estado", "paleta", "destino"):
            ab[col] = None
        db.guardar("abast_cliente", ab)
        resumen["abast_cliente"] = len(ab)
    if "CONTEO_ZONA" in hojas:
        raw = pd.DataFrame(list(_filas(wb["CONTEO_ZONA"], 1, cols=12)))
        try:
            titulo, cz = parse_conteo(raw)
            # se descartan las filas que la macro había agregado al final
            cz = cz[~(cz["obs"].astype(str).str.startswith("Sistema:") & cz["sap"].isna())]
            db.guardar("conteo_zona", cz)
            db.set_config({"conteo_titulo": titulo})
            resumen["conteo_zona"] = len(cz)
        except ValueError as e:
            log(f"  (CONTEO_ZONA omitido: {e})")

    # ---- PEDIDOS / ASIGNACIONES del día (si el Excel no estaba cerrado) ----
    if "PEDIDOS" in hojas:
        filas = []
        for r in _filas(wb["PEDIDOS"], 2, cols=14):
            r += [None] * (14 - len(r))
            if _vacio(r[3]):
                continue
            filas.append({"pedido": texto_pedido(r[0]), "destino": r[1], "fecha": r[2], "codigo": norm(r[3]),
                          "lote": r[5], "cantidad": r[6], "usar_clie": r[8] or "N", "estado": r[9] or None,
                          "asignado": r[10], "pendiente": r[11], "observacion": r[12], "id_linea": r[13]})
        db.guardar("pedidos", pd.DataFrame(filas, columns=db.COLUMNAS["pedidos"]))
        resumen["pedidos"] = len(filas)
    if "ASIGNACIONES" in hojas:
        cols = db.COLUMNAS["asignaciones"]
        filas = [dict(zip(cols, r[:22])) for r in _filas(wb["ASIGNACIONES"], 2, cols=22) if not _vacio(r[0])]
        db.guardar("asignaciones", pd.DataFrame(filas, columns=cols))
        resumen["asignaciones"] = len(filas)

    # ---- HISTORIAL / HIST_PEDIDOS ----
    if not sin_historial:
        if "HISTORIAL" in hojas:
            cols = db.COLUMNAS["historial"]
            filas = [dict(zip(cols, r[:23])) for r in _filas(wb["HISTORIAL"], 2, cols=23) if not _vacio(r[0])]
            db.guardar("historial", pd.DataFrame(filas, columns=cols))
            resumen["historial"] = len(filas)
        if "HIST_PEDIDOS" in hojas:
            filas = []
            for r in _filas(wb["HIST_PEDIDOS"], 2, cols=15):
                r += [None] * (15 - len(r))
                if _vacio(r[3]):
                    continue
                filas.append({"pedido": texto_pedido(r[0]), "destino": r[1], "fecha": r[2], "codigo": norm(r[3]),
                              "lote": r[5], "cantidad": r[6], "usar_clie": r[8], "estado": r[9], "asignado": r[10],
                              "pendiente": r[11], "observacion": r[12], "id_linea": r[13], "fecha_cierre": r[14]})
            db.guardar("hist_pedidos", pd.DataFrame(filas, columns=db.COLUMNAS["hist_pedidos"]))
            resumen["hist_pedidos"] = len(filas)
    for k, v in resumen.items():
        log(f"  {k}: {v} filas")
    return resumen


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xlsm", help="ruta del Picking_Nestle_v6.xlsm")
    ap.add_argument("--db", help="ruta de la base SQLite (por defecto data/picking.db)")
    ap.add_argument("--sin-historial", action="store_true")
    a = ap.parse_args()
    if a.db:
        os.environ["PICKING_DB"] = a.db
    print("Importando", a.xlsm)
    importar(a.xlsm, a.sin_historial)
    print("Listo.")
