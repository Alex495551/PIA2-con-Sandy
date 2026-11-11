"""Lectura y normalización de los archivos de entrada (STOCK, ENTRADAS, PL, ABAST, CONTEO, MAESTRO).

Réplica de CargarStock / CargarEntradas / CargarMaestro / ImportarPLArchivo / LeerAbastCliente
del módulo ModPicking (VBA v5.2).
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .config import Cfg

SIN_FECHA = 1e12  # equivale al 99999 del VBA ("sin fecha": va al final del FEFO)
ORIG_ENT = "Entrada por confirmar"
_EPOCH_EXCEL = dt.date(1899, 12, 30)

MESES = {"JAN": 1, "ENE": 1, "FEB": 2, "MAR": 3, "APR": 4, "ABR": 4, "MAY": 5, "JUN": 6,
         "JUL": 7, "AUG": 8, "AGO": 8, "SEP": 9, "SET": 9, "OCT": 10, "NOV": 11, "DEC": 12, "DIC": 12}


# ----------------------------------------------------------------------------
# utilidades de valores (Norm / Num / fechas)
# ----------------------------------------------------------------------------
def _vacio(v: Any) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def norm(v: Any) -> str:
    """Código/lote en mayúsculas y sin espacios; números enteros sin '.0'."""
    if _vacio(v):
        return ""
    if isinstance(v, bool):
        return str(v).upper()
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else str(v).upper()
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            return norm(v.item())
        except Exception:  # pragma: no cover
            pass
    return str(v).strip().upper()


def num(v: Any) -> float:
    """Número o 0 si no es numérico (igual que Num() del VBA)."""
    if _vacio(v):
        return 0.0
    if isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        return float(s.replace(",", "")) if re.fullmatch(r"[-+]?[\d,]*\.?\d+(e[-+]?\d+)?", s, re.I) else 0.0
    except ValueError:
        return 0.0


def es_numerico(v: Any) -> bool:
    if _vacio(v) or isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    s = str(v).strip()
    return bool(s) and bool(re.fullmatch(r"[-+]?[\d,]*\.?\d+(e[-+]?\d+)?", s, re.I))


def texto_pedido(v: Any) -> str:
    if _vacio(v):
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(int(v)) if float(v) == int(v) else str(v)
    return str(v).strip()


def _ord(d: dt.date) -> float:
    return float(d.toordinal())


def fecha_texto(v: Any) -> float:
    """Acepta fecha real, serie Excel, '03-SEP-27', '03/09/27' (y ISO). Devuelve 0 si no puede."""
    try:
        if _vacio(v):
            return 0.0
        if isinstance(v, (dt.datetime, pd.Timestamp)):
            return _ord(v.date())
        if isinstance(v, dt.date):
            return _ord(v)
        if es_numerico(v):
            x = num(v)
            if 20000 < x < 80000:
                return _ord(_EPOCH_EXCEL + dt.timedelta(days=int(x)))
            return 0.0
        s = str(v).strip().upper()
        if len(s) >= 9 and s[2] == "-" and s[6] == "-":
            dd, mm, yy = int(s[:2]), MESES.get(s[3:6], 0), int(s[7:])
            if yy < 100:
                yy += 2000
            return _ord(dt.date(yy, mm, dd)) if mm else 0.0
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", s):
            return _ord(dt.date(int(s[:4]), int(s[5:7]), int(s[8:10])))
        if "/" in s:
            p = s.split("/")
            if len(p) == 3:
                dd, mm, yy = int(p[0]), int(p[1]), int(p[2][:4])
                if yy < 100:
                    yy += 2000
                return _ord(dt.date(yy, mm, dd))
    except (ValueError, OverflowError):
        return 0.0
    return 0.0


def fecha_lev3(v: Any) -> float:
    """INVT LEV3 viene como ddmmaa (ej. 030927)."""
    try:
        s = norm(v)
        if len(s) == 5:
            s = "0" + s
        if len(s) == 6 and s.isdigit():
            return _ord(dt.date(2000 + int(s[4:]), int(s[2:4]), int(s[:2])))
    except ValueError:
        return 0.0
    return 0.0


def a_fecha(v: Any, lev3: Any = "") -> float:
    r = fecha_texto(v)
    if r == 0:
        r = fecha_lev3(lev3)
    return r if r else SIN_FECHA


def ord_a_fecha(x: float) -> dt.date | None:
    return None if x >= SIN_FECHA else dt.date.fromordinal(int(x))


def fecha_a_ord(v: Any) -> float:
    r = fecha_texto(v)
    return r if r else SIN_FECHA


def parse_fecha(v: Any) -> dt.date | None:
    """Fecha de pantalla/BD -> date (o None)."""
    return ord_a_fecha(fecha_a_ord(v))


def fmt_fecha(v: Any) -> str:
    d = v if isinstance(v, dt.date) and not isinstance(v, dt.datetime) else parse_fecha(v)
    if isinstance(v, (dt.datetime, pd.Timestamp)):
        d = v.date()
    return d.strftime("%d/%m/%Y") if d else ""


def num_txt(x: float) -> str:
    """Número como lo escribe el VBA al concatenar (sin '.0')."""
    return str(int(x)) if float(x) == int(x) else repr(float(x))


# ----------------------------------------------------------------------------
# modelos
# ----------------------------------------------------------------------------
@dataclass(eq=False)
class Pal:
    """Una paleta del stock (arreglos sXxx del VBA)."""
    id: str = ""
    loc: str = ""
    cod: str = ""
    desc: str = ""
    lote: str = ""
    hold: str = ""
    bloque: str = ""
    col: int = 0
    niv: int = 0
    prof: int = 0
    pick: bool = False
    usable: bool = False
    es_clie: bool = False
    disp: float = 0.0       # sDisp: disponible (con RETENIDO si CLIE, con ON ORD si se pide)
    asig: float = 0.0       # sAsig: asignado en el día
    korber: float = 0.0     # sKorber: DISPONIBLE del Korber
    origen: str = "Inventario"
    on_hand: float = 0.0
    on_ord: float = 0.0
    vence: float = SIN_FECHA
    ingreso: float = SIN_FECHA

    @property
    def libre(self) -> float:
        return self.disp - self.asig


@dataclass
class Maestro:
    cod: str
    desc: str = ""
    cpp: float = 0.0
    uma: str = "CJ"
    bloque: str = ""
    cols: str = ""
    nub: float = 0.0


def cargar_maestro(df: pd.DataFrame) -> list[Maestro]:
    """df con columnas: codigo, descripcion, cajas_paleta, uma, fuente, bloque, n_ubic, columnas."""
    out: list[Maestro] = []
    for r in df.to_dict("records"):
        if norm(r.get("codigo")) == "":
            continue
        cols = r.get("columnas")
        cols = "" if _vacio(cols) else str(cols).strip()
        if cols.startswith("#"):
            cols = ""
        uma = norm(r.get("uma")) or "CJ"
        out.append(Maestro(
            cod=norm(r.get("codigo")), desc="" if _vacio(r.get("descripcion")) else str(r.get("descripcion")),
            cpp=num(r.get("cajas_paleta")), uma=uma, bloque=norm(r.get("bloque")), cols=cols,
            nub=num(r.get("n_ubic"))))
    return out


# ----------------------------------------------------------------------------
# lectura de archivos
# ----------------------------------------------------------------------------
def leer_tabla(archivo, hoja: int | str = 0, header: int | None = 0) -> pd.DataFrame:
    """Lee xlsx/xlsm/xls/csv. header=None devuelve la grilla cruda."""
    nombre = getattr(archivo, "name", str(archivo)).lower()
    if hasattr(archivo, "seek"):
        archivo.seek(0)
    if nombre.endswith((".csv", ".txt")):
        for enc in ("utf-8-sig", "cp1252"):
            try:
                if hasattr(archivo, "seek"):
                    archivo.seek(0)
                return pd.read_csv(archivo, sep=None, engine="python", dtype=object, header=header, encoding=enc)
            except UnicodeDecodeError:
                continue
    return pd.read_excel(archivo, sheet_name=hoja, dtype=object, header=header)


def _mapa_columnas(columnas) -> dict[str, int]:
    """Nombre normalizado -> posición (si se repite, gana la última, como en el VBA)."""
    m: dict[str, int] = {}
    for i, c in enumerate(columnas):
        m[str(c).strip().upper()] = i
    return m


COLS_STOCK_OBLIG = ["LOC CODE", "INVT LEV1", "INVT LEV4", "DISPONIBLE", "HOLD CODE"]
COLS_STOCK = ["CUST CODE", "LOC CODE", "TO CHAR INVT ORG RECD DATE", "INVT LEV1", "INVT LEV2", "INVT LEV3",
              "INVT LEV4", "ON HAND QTY", "DISPONIBLE", "ON ORD QTY", "RETENIDO", "HOLD CODE", "FECHA EXP",
              "ITEM DES1"]
COLS_ENTRADAS_OBLIG = ["RCPT LEV1", "RCPT LEV4", "RCPT RECD QTY"]
COLS_ENTRADAS = ["CUST CODE", "RCPT LEV1", "RCPT LEV2", "RCPT LEV3", "RCPT LEV4", "RCPT RECD QTY", "LOC CODE",
                 "TO CHAR RCPT DATE", "ITEM DES1"]


def validar_columnas(df: pd.DataFrame, obligatorias: list[str]) -> list[str]:
    m = _mapa_columnas(df.columns)
    return [c for c in obligatorias if c not in m]


def excluida(loc: str, cfg: Cfg) -> bool:
    if loc == "":
        return True
    if cfg.excluir == "":
        return False
    for t in cfg.excluir.split(";"):
        t = t.strip()
        if t and loc.startswith(t):
            return True
    return False


def es_picking(bloque: str, nivel: int, cfg: Cfg) -> bool:
    for b, n in zip(cfg.pk_bloque, cfg.pk_nivel):
        if b == bloque and (n == "*" or n == str(nivel)):
            return True
    return False


def uso_hold(h: str, cfg: Cfg) -> str:
    for c, u in zip(cfg.hold_cod, cfg.hold_uso):
        if c == h:
            return u
    return "NO"


def _int(x: float) -> int:
    return int(round(x))


def cargar_stock(df: pd.DataFrame, cfg: Cfg, entradas: pd.DataFrame | None = None) -> list[Pal]:
    """STOCK del Korber (+ entradas por confirmar si la config lo pide) -> lista de paletas."""
    faltan = validar_columnas(df, COLS_STOCK_OBLIG)
    if faltan:
        raise ValueError("No encuentro estas columnas del Korber en STOCK: " + ", ".join(faltan)
                         + ". Revisa que el archivo tenga los encabezados en la primera fila.")
    m = _mapa_columnas(df.columns)
    g = lambda row, k: row[m[k]] if k in m else None  # noqa: E731
    pals: list[Pal] = []
    for row in df.itertuples(index=False, name=None):
        cod = norm(g(row, "INVT LEV1"))
        ok = cod != ""
        if ok and "CUST CODE" in m and cfg.cliente != "":
            ok = norm(g(row, "CUST CODE")) == cfg.cliente
        loc = "" if _vacio(g(row, "LOC CODE")) else str(g(row, "LOC CODE")).strip().upper()
        if ok:
            ok = not excluida(loc, cfg)
        if not ok:
            continue
        p = Pal()
        p.id = "" if _vacio(g(row, "INVT LEV4")) else str(g(row, "INVT LEV4")).strip()
        p.loc = loc
        p.cod = cod
        if "ITEM DES1" in m and not _vacio(g(row, "ITEM DES1")):
            p.desc = str(g(row, "ITEM DES1")).strip()
        if "INVT LEV2" in m:
            p.lote = norm(g(row, "INVT LEV2"))
        p.hold = "" if _vacio(g(row, "HOLD CODE")) else str(g(row, "HOLD CODE")).strip().upper()
        partes = loc.split("_")
        if len(partes) >= 4:
            p.bloque = partes[0]
            p.col = _int(num(partes[1]))
            p.niv = _int(num(partes[2]))
            p.prof = _int(num(partes[3]))
            p.pick = es_picking(p.bloque, p.niv, cfg)
        else:  # ubicaciones especiales (ej. _RANDEN = andén): reserva
            p.bloque, p.col, p.niv, p.prof, p.pick = loc, 0, 0, 0, False
        if "FECHA EXP" in m:
            p.vence = a_fecha(g(row, "FECHA EXP"), g(row, "INVT LEV3") if "INVT LEV3" in m else "")
        elif "INVT LEV3" in m:
            p.vence = a_fecha("", g(row, "INVT LEV3"))
        else:
            p.vence = SIN_FECHA
        p.ingreso = a_fecha(g(row, "TO CHAR INVT ORG RECD DATE"), "") if "TO CHAR INVT ORG RECD DATE" in m else SIN_FECHA
        uso = uso_hold(p.hold, cfg)
        p.usable = uso == "SI"
        p.es_clie = uso[:3] == "SOL"
        p.korber = num(g(row, "DISPONIBLE"))
        if p.es_clie and "RETENIDO" in m:
            p.disp = num(g(row, "RETENIDO")) + num(g(row, "DISPONIBLE"))
        else:
            p.disp = num(g(row, "DISPONIBLE"))
        if cfg.sumar_ord and "ON ORD QTY" in m:
            p.disp += num(g(row, "ON ORD QTY"))
        p.on_hand = num(g(row, "ON HAND QTY")) if "ON HAND QTY" in m else p.disp
        p.on_ord = num(g(row, "ON ORD QTY")) if "ON ORD QTY" in m else 0.0
        pals.append(p)
    if cfg.usar_ent and entradas is not None and len(entradas):
        pals.extend(_cargar_entradas(entradas, cfg, pals))
    return pals


def _cargar_entradas(df: pd.DataFrame, cfg: Cfg, inv: list[Pal]) -> list[Pal]:
    m = _mapa_columnas(df.columns)
    if any(k not in m for k in COLS_ENTRADAS_OBLIG):
        return []
    g = lambda row, k: row[m[k]] if k in m else None  # noqa: E731
    ids_inv = {p.id for p in inv}  # el VBA solo compara contra el inventario, no entre entradas
    out: list[Pal] = []
    for row in df.itertuples(index=False, name=None):
        pid = "" if _vacio(g(row, "RCPT LEV4")) else str(g(row, "RCPT LEV4")).strip()
        cod = norm(g(row, "RCPT LEV1"))
        qty = num(g(row, "RCPT RECD QTY"))
        if not (pid and cod and qty > 0):
            continue
        if "CUST CODE" in m and cfg.cliente != "" and norm(g(row, "CUST CODE")) != cfg.cliente:
            continue
        if pid in ids_inv:
            continue
        loc = ""
        if "LOC CODE" in m and not _vacio(g(row, "LOC CODE")):
            loc = str(g(row, "LOC CODE")).strip().upper()
        partes = loc.split("_")
        sin_ubic = loc == "" or loc == "*" or len(partes) < 4
        if not sin_ubic:
            sin_ubic = excluida(loc, cfg)
        if sin_ubic:
            if not cfg.ent_sin_ubic:
                continue
            if loc in ("", "*"):
                loc = "RECEPCION"
        p = Pal(id=pid, loc=loc, cod=cod)
        if "ITEM DES1" in m and not _vacio(g(row, "ITEM DES1")):
            p.desc = str(g(row, "ITEM DES1")).strip()
        if "RCPT LEV2" in m:
            p.lote = norm(g(row, "RCPT LEV2"))
        p.hold = "*"
        if sin_ubic:
            p.bloque, p.col, p.niv, p.prof, p.pick = "REC", 0, 0, 0, False
        else:
            partes = loc.split("_")
            p.bloque = partes[0]
            p.col, p.niv, p.prof = _int(num(partes[1])), _int(num(partes[2])), _int(num(partes[3]))
            p.pick = es_picking(p.bloque, p.niv, cfg)
        p.vence = a_fecha("", g(row, "RCPT LEV3")) if "RCPT LEV3" in m else SIN_FECHA
        p.ingreso = a_fecha(g(row, "TO CHAR RCPT DATE"), "") if "TO CHAR RCPT DATE" in m else SIN_FECHA
        p.usable, p.es_clie = True, False
        p.disp = p.korber = p.on_hand = qty
        p.on_ord = 0.0
        p.origen = ORIG_ENT
        out.append(p)
    return out


# ----------------------------------------------------------------------------
# PEDIDOS: importación de archivos PL "CONTROL DE DESPACHO - PICKING"
# ----------------------------------------------------------------------------
def importar_pl(archivo, nombre: str | None = None, ahora: dt.datetime | None = None) -> list[dict]:
    """Devuelve las líneas de pedido del PL (mismo criterio que ImportarPLArchivo)."""
    import openpyxl

    if hasattr(archivo, "seek"):
        archivo.seek(0)
    nombre = nombre or getattr(archivo, "name", "")
    wb = openpyxl.load_workbook(archivo, data_only=True, read_only=False)
    ws = wb.worksheets[0]
    cel = lambda r, c: ws.cell(row=r, column=c).value  # noqa: E731
    hdr = 0
    for r in range(1, 31):
        if str(cel(r, 7) or "").strip().upper() == "CANTIDAD":
            hdr = r
            break
    if hdr == 0:
        hdr = 8
    cliente = str(cel(4, 3) or "").strip()
    if cliente == "":
        p = nombre.upper().find("HACIA ")
        if p >= 0:
            cliente = nombre[p + 6:p + 46].strip()
        if " " in cliente:
            cliente = cliente.split(" ")[0]
    fecha = ws["G4"].value
    pedido = texto_pedido(ws["G6"].value)
    if pedido in ("", "0"):
        pedido = f"{cliente}-{(ahora or dt.datetime.now()).strftime('%H%M%S')}"
    f = parse_fecha(fecha) if fecha is not None else None
    out: list[dict] = []
    r = hdr + 1
    while r < hdr + 400:
        cod = str(cel(r, 2) if cel(r, 2) is not None else "").strip()
        if cod == "":
            if str(cel(r + 1, 2) if cel(r + 1, 2) is not None else "").strip() == "":
                break
        elif es_numerico(cod) and num(cel(r, 7)) > 0:
            lote = cel(r, 5)
            out.append({"pedido": pedido, "destino": cliente, "fecha": f, "codigo": cod,
                        "lote": "" if lote is None else str(lote).strip(),
                        "cantidad": num(cel(r, 7)), "usar_clie": "N"})
        r += 1
    return out


# ----------------------------------------------------------------------------
# ABAST_CLIENTE y CONTEO_ZONA
# ----------------------------------------------------------------------------
def parse_abast(raw: pd.DataFrame) -> pd.DataFrame:
    """Archivo del cliente (grilla cruda) -> filas: fila, codigo, texto, lote, cantidad, ubicacion, fecha."""
    hdr, cc, cd, cl, cq, cf, cu = -1, -1, -1, -1, -1, -1, -1
    for r in range(min(10, len(raw))):
        for c in range(min(12, raw.shape[1])):
            h = str(raw.iat[r, c]).strip().upper() if not _vacio(raw.iat[r, c]) else ""
            if h in ("CODIGO", "CÓDIGO", "MATERIAL"):
                cc, hdr = c, r
            elif h in ("TEXTO BREVE", "DESCRIPCION"):
                cd = c
            elif h == "LOTE":
                cl = c
            elif h == "CANTIDAD":
                cq = c
            elif h.startswith("FECHA"):
                cf = c
            elif h in ("UBICACIÓN", "UBICACION"):
                cu = c
        if hdr >= 0:
            break
    if hdr < 0 or cl < 0:
        raise ValueError("ABAST_CLIENTE: no encuentro los encabezados CODIGO y LOTE en las primeras filas.")
    filas = []
    for r in range(hdr + 1, len(raw)):
        v = raw.iat[r, cc]
        if norm(v) != "" and es_numerico(v):
            d = raw.iat[r, cd] if cd >= 0 else ""
            filas.append({
                "fila": r + 1,
                "codigo": norm(v),
                "texto": "" if _vacio(d) else str(d).replace("\xa0", " ").strip(),
                "lote": norm(raw.iat[r, cl]),
                "cantidad": num(raw.iat[r, cq]) if cq >= 0 else 0.0,
                "ubicacion": "" if cu < 0 or _vacio(raw.iat[r, cu]) else str(raw.iat[r, cu]).strip(),
                "fecha": parse_fecha(raw.iat[r, cf]) if cf >= 0 and not _vacio(raw.iat[r, cf]) else None,
            })
    return pd.DataFrame(filas, columns=["fila", "codigo", "texto", "lote", "cantidad", "ubicacion", "fecha"])


def parse_conteo(raw: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """Formato del cliente 'ZONA DE TRABAJO ... CIERRE' -> (título, filas)."""
    hdr = -1
    cols: dict[str, int] = {}
    nombres = {"MATERIAL": "material", "CODIGO": "material", "CÓDIGO": "material",
               "TEXTO BREVE MATERIAL": "texto", "TEXTO BREVE": "texto", "LOTE": "lote", "UM": "um",
               "SAP": "sap", "EXEL ALFRIMAC": "alfrimac", "EXCEL ALFRIMAC": "alfrimac",
               "CONTEO FISICO": "conteo", "CONTEO FÍSICO": "conteo", "DIFERENCIA": "diferencia",
               "OBSEV": "obs", "OBSERV": "obs", "OBSERVACION": "obs", "OBSERVACIÓN": "obs"}
    for r in range(min(15, len(raw))):
        for c in range(min(15, raw.shape[1])):
            h = str(raw.iat[r, c]).strip().upper() if not _vacio(raw.iat[r, c]) else ""
            if h in nombres:
                cols[nombres[h]] = c
                if nombres[h] == "material":
                    hdr = r
        if hdr >= 0:
            break
    if hdr < 0 or "lote" not in cols:
        raise ValueError("CONTEO_ZONA: no encuentro los encabezados Material y LOTE en las primeras filas.")
    titulo = ""
    for r in range(hdr):
        for c in range(min(4, raw.shape[1])):
            if not _vacio(raw.iat[r, c]):
                titulo = str(raw.iat[r, c]).strip()
    filas = []
    for r in range(hdr + 1, len(raw)):
        fila = {k: (raw.iat[r, c] if c < raw.shape[1] else None) for k, c in cols.items()}
        a0 = raw.iat[r, 0]
        if all(_vacio(v) for v in fila.values()):
            continue
        for k in ("material", "texto", "lote", "um", "obs"):
            fila.setdefault(k, None)
        fila["material"] = "" if _vacio(fila["material"]) else (
            str(a0).strip() if str(a0).strip().upper().startswith("TOTAL") else norm(fila["material"]))
        fila["lote"] = norm(fila.get("lote"))
        fila["texto"] = "" if _vacio(fila.get("texto")) else str(fila["texto"]).replace("\xa0", " ").strip()
        fila["um"] = "" if _vacio(fila.get("um")) else str(fila["um"]).strip()
        fila["obs"] = "" if _vacio(fila.get("obs")) else str(fila["obs"])
        for k in ("sap", "alfrimac", "conteo", "diferencia"):
            fila[k] = None if _vacio(fila.get(k)) else num(fila[k])
        filas.append(fila)
    cols_out = ["material", "texto", "lote", "um", "sap", "alfrimac", "conteo", "diferencia", "obs"]
    df = pd.DataFrame(filas)
    for c in cols_out:
        if c not in df.columns:
            df[c] = None
    return titulo, df[cols_out]
