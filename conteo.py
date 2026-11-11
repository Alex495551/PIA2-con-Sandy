"""Conteo de la zona de picking (réplica de EscribirConteo del VBA).

Llena "Exel Alfrimac" = lo que queda en la zona de picking por código+lote (stock - lo asignado hoy)
más las paletas que se bajan en el reabastecimiento; marca la diferencia con SAP en Obsev y agrega al
final los lotes que están en zona pero no figuran en el conteo del cliente.
"""
from __future__ import annotations

import io

import pandas as pd

from .asignacion import Contexto
from .carga_datos import norm, num, num_txt
from .reabastecimiento import Reabastecedor, ResultadoReab

COLS_CONTEO = ["material", "texto", "lote", "um", "sap", "alfrimac", "conteo", "diferencia", "obs"]
ENCABEZADOS = ["Material", "Texto breve material", "LOTE", "UM", "SAP", "Exel Alfrimac", "Conteo Fisico",
               "Diferencia", "Obsev"]


def _s(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def esperado_en_zona(ctx: Contexto, res: ResultadoReab) -> list[dict]:
    """Código+lote -> cajas esperadas en zona al cierre (orden de aparición)."""
    rb = Reabastecedor(ctx, None)
    acum: dict[tuple[str, str], dict] = {}

    def add(cod, lote, q, d):
        k = (cod, lote)
        if k in acum:
            acum[k]["cajas"] += q
        else:
            acum[k] = {"codigo": cod, "lote": lote, "cajas": q, "desc": d}

    for p in ctx.stock:
        if p.pick and rb.restante(p) > 0:
            add(p.cod, p.lote, rb.restante(p), p.desc)
    for m in res.movimientos:
        add(m["cod"], m["lote"], m["cajas"], "")
    return list(acum.values())


def calcular_conteo(ctx: Contexto, res: ResultadoReab, conteo: pd.DataFrame) -> pd.DataFrame:
    """Devuelve la tabla de conteo con 'alfrimac', 'obs' y 'diferencia' calculados."""
    esperado = esperado_en_zona(ctx, res)
    idx = {(e["codigo"], e["lote"]): e for e in esperado}
    en_lista: set[tuple[str, str]] = set()

    df = conteo.copy() if conteo is not None else pd.DataFrame(columns=COLS_CONTEO)
    for c in COLS_CONTEO:
        if c not in df.columns:
            df[c] = None
    df = df[COLS_CONTEO].astype(object)
    # quitar filas que agregó la macro antes (Obsev empieza con "Sistema:" y SAP vacío)
    borrar = [i for i, r in df.iterrows()
              if _s(r["obs"]).startswith("Sistema:") and (r["sap"] is None or pd.isna(r["sap"]))]
    df = df.drop(index=borrar).reset_index(drop=True)

    mat = ""
    for i, r in df.iterrows():
        if _s(r["material"]).strip().upper().startswith("TOTAL"):
            break
        if norm(r["material"]) != "":
            mat = norm(r["material"])
        lote = norm(r["lote"])
        if mat and lote:
            e = idx.get((mat, lote))
            q = e["cajas"] if e else 0.0
            if e:
                en_lista.add((mat, lote))
            df.at[i, "alfrimac"] = q
            obs = _s(r["obs"])
            if obs == "" or obs.startswith("Sistema:"):
                sap = num(r["sap"])
                df.at[i, "obs"] = f"Sistema: Alfrimac - SAP = {num_txt(q - sap)}" if q != sap else ""
            df.at[i, "diferencia"] = num(r["conteo"]) - num(r["sap"])

    # la fila "Total general" del Excel son fórmulas: se recalcula con las filas de arriba
    for i, r in df.iterrows():
        if _s(r["material"]).strip().upper().startswith("TOTAL"):
            arriba = df.iloc[:i]
            for c in ("sap", "alfrimac", "conteo", "diferencia"):
                df.at[i, c] = float(sum(num(v) for v in arriba[c]))
            break

    extras = []
    for e in esperado:
        k = (e["codigo"], e["lote"])
        if k not in en_lista:
            mi = ctx.maestro_de(e["codigo"])
            extras.append({"material": e["codigo"], "texto": mi.desc if mi else e["desc"], "lote": e["lote"],
                           "um": mi.uma if mi else "", "sap": None, "alfrimac": e["cajas"], "conteo": None,
                           "diferencia": None, "obs": "Sistema: lote en zona de picking que no figura en el conteo SAP"})
    if extras:
        df = pd.concat([df, pd.DataFrame(extras, columns=COLS_CONTEO)], ignore_index=True)
    return df


def exportar_conteo_excel(df: pd.DataFrame, titulo: str = "") -> bytes:
    """Excel con el mismo formato del cliente (título en A2, encabezados en la fila 4)."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CONTEO ZONA"
    ws["A2"] = titulo or "ZONA DE TRABAJO"
    ws["A2"].font = Font(bold=True, size=12)
    for j, h in enumerate(ENCABEZADOS, 1):
        c = ws.cell(row=4, column=j, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0D1117")
        c.alignment = Alignment(horizontal="center")
    for i, r in enumerate(df[COLS_CONTEO].itertuples(index=False, name=None), 5):
        for j, v in enumerate(r, 1):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                v = None
            ws.cell(row=i, column=j, value=v)
    for col, w in zip("ABCDEFGHI", (14, 44, 14, 6, 10, 14, 14, 12, 48)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

