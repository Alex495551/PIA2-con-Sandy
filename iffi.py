"""Archivo IFFI para el Korber (réplica de GenerarIFFIArchivos / CamposIFFI del VBA).

CSV separado por ';' con 61 campos, fin de línea CRLF, fechas MM/DD/YY, una línea por paleta
(si una paleta se repite en el pedido se suman las cajas).
"""
from __future__ import annotations

import datetime as dt
import re

from .asignacion import num
from .carga_datos import norm, num_txt, parse_fecha, texto_pedido
from .config import Cfg

N_CAMPOS = 61

# Posición (1..61) -> nombre del campo en la plantilla del Korber
CAMPOS_USADOS = {1: "*", 2: "B Consignee Code", 10: "J Soldto Name", 19: "S Order Date",
                 20: "T Order To Ship Date", 21: "U Order To Arrive Date", 22: "V Customer Order Number (destino)",
                 23: "W Order PO Number (pedido)", 24: "X Carrier Code", 27: "AA Warehouse Code",
                 29: "AC Inventory Level 1 (código)", 32: "AF Inventory Level 4 (ID paleta)",
                 33: "AG Order Quantity", 34: "AH Freight Term", 38: "AL Load Type", 61: "*"}


def _fecha(v, defecto: dt.date) -> dt.date:
    d = v if isinstance(v, dt.date) and not isinstance(v, dt.datetime) else parse_fecha(v)
    if isinstance(v, dt.datetime):
        d = v.date()
    return d or defecto


def fecha_us(v, hoy: dt.date | None = None) -> str:
    d = _fecha(v, hoy or dt.date.today())
    return f"{d.month:02d}/{d.day:02d}/{d.year % 100:02d}"


def fecha_punto(v, hoy: dt.date | None = None) -> str:
    d = _fecha(v, hoy or dt.date.today())
    return f"{d.day:02d}.{d.month:02d}.{d.year % 100:02d}"


def nombre_archivo(s: str) -> str:
    for ch in '\\/:*?"<>|':
        s = s.replace(ch, "-")
    s = s.strip()
    return s or "SIN DESTINO"


def campos_iffi(cfg: Cfg, fecha_pl, f_desp, dest: str, ped: str, cod: str, pid: str, qty: float,
                hoy: dt.date | None = None) -> list[str]:
    f = [""] * (N_CAMPOS + 1)  # índice 1..61
    f[1] = "*"
    f[2] = cfg.consignee
    f[10] = cfg.soldto
    f[19] = fecha_us(fecha_pl, hoy)
    f[20] = fecha_us(f_desp, hoy)
    f[21] = fecha_us(f_desp, hoy)
    f[22] = dest
    f[23] = ped
    f[24] = cfg.carrier
    f[27] = cfg.almacen
    f[29] = cod
    f[32] = pid
    f[33] = num_txt(qty)
    f[34] = cfg.freight
    f[38] = cfg.load
    f[61] = "*"
    return f[1:]


def generar_iffi(asignaciones: list[dict], cfg: Cfg, fecha_pl=None, pedido: str = "",
                 hoy: dt.date | None = None) -> list[dict]:
    """Un archivo por pedido (o solo el pedido indicado)."""
    hoy = hoy or dt.date.today()
    fecha_pl = _fecha(fecha_pl, hoy)
    peds: list[str] = []
    for a in asignaciones:
        p = texto_pedido(a["pedido"])
        if (pedido == "" or p == pedido) and p not in peds:
            peds.append(p)
    salida = []
    for p in peds:
        claves: dict[tuple[str, str], float] = {}
        dest, f_desp = "", None
        for a in asignaciones:
            if texto_pedido(a["pedido"]) != p:
                continue
            if dest == "":
                dest = str(a["destino"] or "").strip()
            if f_desp is None and parse_fecha(a["fecha_despacho"]) is not None:
                f_desp = _fecha(a["fecha_despacho"], hoy)
            k = (norm(a["codigo"]), str(a["id_paleta"]).strip())
            claves[k] = claves.get(k, 0.0) + num(a["cajas"])
        if not claves:
            continue
        if f_desp is None:
            f_desp = fecha_pl
        lineas = [campos_iffi(cfg, fecha_pl, f_desp, dest, p, c, i, q, hoy) for (c, i), q in claves.items()]
        texto = "".join(";".join(l) + "\r\n" for l in lineas)
        salida.append({
            "pedido": p, "destino": dest,
            "archivo": f"IFFI_{fecha_punto(fecha_pl, hoy)} - {nombre_archivo(dest)} - {p}.csv",
            "contenido": texto.encode("cp1252", errors="replace"),
            "lineas": lineas, "paletas": len(lineas), "cajas": sum(claves.values()),
        })
    return salida


def validar_iffi(contenido: bytes) -> list[str]:
    """Revisa un CSV IFFI: 61 campos por línea, CRLF y fechas MM/DD/YY. Devuelve la lista de problemas."""
    problemas = []
    texto = contenido.decode("cp1252")
    if "\n" in texto.replace("\r\n", ""):
        problemas.append("hay saltos de línea que no son CRLF")
    for i, l in enumerate(texto.split("\r\n")[:-1], 1):
        c = l.split(";")
        if len(c) != N_CAMPOS:
            problemas.append(f"línea {i}: {len(c)} campos (deben ser {N_CAMPOS})")
            continue
        for k in (19, 20, 21):
            if not re.fullmatch(r"\d\d/\d\d/\d\d", c[k - 1]):
                problemas.append(f"línea {i}: fecha inválida en campo {k}")
        if c[0] != "*" or c[-1] != "*":
            problemas.append(f"línea {i}: faltan los '*' de inicio/fin")
    return problemas
