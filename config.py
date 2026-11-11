"""Configuración del sistema (equivale a la hoja CONFIG del Excel)."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

# Valores iniciales tomados de CONFIG del Picking_Nestle_v6.xlsm
CONFIG_DEFECTO: dict = {
    "cliente": "NESTLE",
    "umbral": 0.05,                  # C5: saldo bajo (fracción de una paleta)
    "excluir": "CAMARA",             # C6: ubicaciones que empiezan con (separar con ;)
    "sumar_on_ord": False,           # C9: sumar ON ORD al disponible
    "zonas_picking": [{"bloque": "G", "nivel": "1"}],  # orden = orden de recorrido
    "hold": [
        {"codigo": "*", "significado": "Libre", "uso": "SI"},
        {"codigo": "CLIE", "significado": "Petición cliente", "uso": "SOLO CON AUTORIZACION"},
        {"codigo": "CADU", "significado": "Caducado", "uso": "NO"},
        {"codigo": "CUAR", "significado": "Cuarentena (reencaje)", "uso": "NO"},
        {"codigo": "DAOP", "significado": "Daño operativo", "uso": "NO"},
        {"codigo": "DAOR", "significado": "Daño de origen", "uso": "NO"},
        {"codigo": "INV", "significado": "Diferencia de inventario", "uso": "NO"},
        {"codigo": "INVE", "significado": "Diferencia de inventario", "uso": "NO"},
        {"codigo": "OTRO", "significado": "Otros (pérdida)", "uso": "NO"},
        {"codigo": "PICK", "significado": "Bloqueo por picking", "uso": "NO"},
    ],
    "usar_entradas": True,           # K4
    "entradas_sin_ubic": True,       # K5
    "iffi_consignee": "NESTLE",      # K6
    "iffi_soldto": "NESTLE",         # K7
    "iffi_almacen": "CLL1",          # K8
    "iffi_carrier": "NA",            # K9
    "iffi_freight": "NA",            # K10
    "iffi_load": "PLT",              # K11
    "nivel_picking": 1,              # K14
    "profundidades": 2,              # K15
    "sust_lote": True,               # K16: otros lotes de picking en cajas sueltas
    "reab_ord": True,                # K17: reabastecer descontando ON ORD
    "contador_lineas": 0,            # C7: contador de ID de línea
    "g_columnas": 140,               # solo para el mapa visual de la zona G
}


@dataclass
class Cfg:
    """Configuración ya interpretada (lo que en el VBA son las variables cXxx)."""
    cliente: str = "NESTLE"
    umbral: float = 0.05
    excluir: str = "CAMARA"
    sumar_ord: bool = False
    pk_bloque: list = field(default_factory=lambda: ["G"])
    pk_nivel: list = field(default_factory=lambda: ["1"])
    hold_cod: list = field(default_factory=list)
    hold_uso: list = field(default_factory=list)
    usar_ent: bool = True
    ent_sin_ubic: bool = True
    consignee: str = "NESTLE"
    soldto: str = "NESTLE"
    almacen: str = "CLL1"
    carrier: str = "NA"
    freight: str = "NA"
    load: str = "PLT"
    nivel_pick: int = 1
    profund: int = 2
    sust_lote: bool = True
    reab_ord: bool = True


def _txt(v, defecto: str) -> str:
    s = "" if v is None else str(v).strip()
    return s if s else defecto


def construir_cfg(d: dict | None) -> Cfg:
    """Convierte el diccionario de configuración en un objeto Cfg (igual que CargarConfig del VBA)."""
    base = copy.deepcopy(CONFIG_DEFECTO)
    if d:
        base.update(d)
    c = Cfg()
    c.cliente = str(base["cliente"] or "").strip().upper()
    c.umbral = float(base["umbral"] or 0)
    if c.umbral <= 0:
        c.umbral = 0.3  # igual que el VBA
    c.excluir = str(base["excluir"] or "").strip().upper()
    c.sumar_ord = bool(base["sumar_on_ord"])
    c.pk_bloque, c.pk_nivel = [], []
    for z in base["zonas_picking"]:
        b = str(z.get("bloque", "")).strip().upper()
        if b:
            c.pk_bloque.append(b)
            n = str(z.get("nivel", "")).strip().upper()
            c.pk_nivel.append(n if n else "*")
    for h in base["hold"]:
        cod = str(h.get("codigo", "")).strip().upper()
        if cod:
            c.hold_cod.append(cod)
            c.hold_uso.append(str(h.get("uso", "")).strip().upper())
    c.usar_ent = bool(base["usar_entradas"])
    c.ent_sin_ubic = bool(base["entradas_sin_ubic"])
    c.consignee = _txt(base["iffi_consignee"], "NESTLE")
    c.soldto = _txt(base["iffi_soldto"], "NESTLE")
    c.almacen = _txt(base["iffi_almacen"], "CLL1")
    c.carrier = _txt(base["iffi_carrier"], "NA")
    c.freight = _txt(base["iffi_freight"], "NA")
    c.load = _txt(base["iffi_load"], "PLT")
    c.nivel_pick = int(base["nivel_picking"] or 0) or 1
    c.profund = int(base["profundidades"] or 0) or 2
    c.sust_lote = bool(base["sust_lote"])
    c.reab_ord = bool(base["reab_ord"])
    return c
