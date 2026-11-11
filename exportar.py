"""Exportaciones: Excel genérico, hoja de picking en Excel/PDF."""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd

from .carga_datos import fmt_fecha


def _limpio(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (dt.datetime, pd.Timestamp)):
        return v.to_pydatetime() if isinstance(v, pd.Timestamp) else v
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            return v.item()
        except Exception:
            return str(v)
    return v


def excel_de_tablas(hojas: dict[str, pd.DataFrame]) -> bytes:
    """Un libro con una hoja por DataFrame, con encabezado resaltado."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, df in hojas.items():
        ws = wb.create_sheet(nombre[:31])
        ws.append(list(df.columns))
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="0D1117")
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for fila in df.itertuples(index=False, name=None):
            ws.append([_limpio(v) for v in fila])
        for j, col in enumerate(df.columns, 1):
            ancho = max([len(str(col))] + [len(str(v)) for v in df[col].head(200) if v is not None]) + 2
            ws.column_dimensions[get_column_letter(j)].width = min(max(ancho, 8), 48)
        ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _tabla_hoja(h: dict) -> list[list]:
    cab = ["N°", "Ubicación", "Zona", "ID paleta", "Código", "Descripción", "Lote", "Vence", "Tipo", "Cajas", "UMA"]
    filas = [cab]
    for f in h["filas"]:
        filas.append([f["N°"], f["Ubicación"], f["Zona"], f["ID paleta"], f["Código"], f["Descripción"], f["Lote"],
                      fmt_fecha(f["Vence"]), f["Tipo"], int(f["Cajas"]) if float(f["Cajas"]).is_integer() else f["Cajas"],
                      f["UMA"]])
    filas.append(["", "", "", "", "", "", "", "", "TOTAL", int(h["total"]) if float(h["total"]).is_integer() else h["total"], ""])
    return filas


def hoja_picking_excel(h: dict) -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "HOJA PICKING"
    ws["A1"] = "HOJA DE PICKING — CONTROL DE DESPACHO"
    ws["A1"].font = Font(bold=True, size=14)
    ws["B3"], ws["C3"] = "N° Pedido:", h["pedido"]
    ws["B4"], ws["C4"] = "Destino:", h["destino"]
    ws["B5"], ws["C5"] = "Fecha:", fmt_fecha(h["fecha"])
    ws["G3"] = "Ordenada por recorrido: primero cajas sueltas (picking), luego paletas completas."
    ws["G4"] = "Placa: ____________   Chofer: ________________"
    ws["G5"] = "Hora inicio: ______   Hora fin: ______   Firma: ______________"
    for c in ("B3", "B4", "B5"):
        ws[c].font = Font(bold=True)
    tabla = _tabla_hoja(h)
    for i, fila in enumerate(tabla, 8):
        for j, v in enumerate(fila, 1):
            ws.cell(row=i, column=j, value=v)
    for c in ws[8]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0D1117")
        c.alignment = Alignment(horizontal="center")
    for c in ws[8 + len(tabla) - 1]:
        c.font = Font(bold=True)
    for k, nota in enumerate(h["notas"]):
        ws.cell(row=8 + len(tabla) + 1 + k, column=2, value=nota)
    for col, w in zip("ABCDEFGHIJK", (5, 14, 14, 12, 11, 40, 14, 12, 16, 8, 6)):
        ws.column_dimensions[col].width = w
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToHeight = 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def hoja_picking_pdf(h: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24,
                            title=f"Hoja de picking {h['pedido']}")
    st = getSampleStyleSheet()
    el = [Paragraph("<b>HOJA DE PICKING — CONTROL DE DESPACHO</b>", st["Title"]),
          Paragraph(f"<b>N° Pedido:</b> {h['pedido']} &nbsp;&nbsp; <b>Destino:</b> {h['destino']} &nbsp;&nbsp; "
                    f"<b>Fecha:</b> {fmt_fecha(h['fecha'])}", st["Normal"]),
          Paragraph("Placa: ____________ &nbsp; Chofer: ________________ &nbsp; Hora inicio: ______ &nbsp; "
                    "Hora fin: ______ &nbsp; Firma: ______________", st["Normal"]),
          Paragraph("Ordenada por recorrido: primero cajas sueltas (picking), luego paletas completas.", st["Italic"]),
          Spacer(1, 8)]
    datos = _tabla_hoja(h)
    chico = st["BodyText"].clone("chico", fontSize=7, leading=8)
    for r in datos[1:-1]:
        r[5] = Paragraph(str(r[5]), chico)
    t = Table(datos, repeatRows=1, colWidths=[22, 62, 58, 56, 52, 190, 62, 52, 72, 36, 28])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d1117")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9aa3af")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f3f4f6")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (9, 1), (9, -1), "RIGHT")]))
    el.append(t)
    for n in h["notas"]:
        el += [Spacer(1, 6), Paragraph(n, chico)]
    doc.build(el)
    return buf.getvalue()
