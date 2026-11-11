"""Orquesta base de datos + reglas de negocio. Es lo único que llaman las páginas de /pages."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from . import db
from .asignacion import (COLS_ASIG, Contexto, Linea, anular_pedido, desbloqueos, hoja_picking,
                         procesar_pedidos)
from .carga_datos import (Maestro, cargar_maestro, cargar_stock, norm, num, parse_fecha, texto_pedido)
from .config import Cfg, construir_cfg
from .conteo import calcular_conteo
from .iffi import generar_iffi
from .reabastecimiento import ResultadoReab, calcular_reabastecimiento, estado_posiciones_zona

ESTADOS_ASIG = ["Pendiente", "En picking", "Listo", "Despachado"]


# ----------------------------------------------------------------------------
# lectura de tablas -> estructuras de la lógica
# ----------------------------------------------------------------------------
def _fecha(v):
    return parse_fecha(v) if v not in (None, "") else None


def leer_asignaciones() -> list[dict]:
    df = db.leer("asignaciones")
    out = []
    for r in df.to_dict("records"):
        r["fecha_despacho"] = _fecha(r["fecha_despacho"])
        r["vence"] = _fecha(r["vence"])
        out.append(r)
    return out


def guardar_asignaciones(asig: list[dict]) -> None:
    df = pd.DataFrame(asig, columns=db.COLUMNAS["asignaciones"]) if asig else pd.DataFrame(columns=db.COLUMNAS["asignaciones"])
    db.guardar("asignaciones", df)


def leer_lineas() -> list[Linea]:
    df = db.leer("pedidos")
    out = []
    for i, r in enumerate(df.to_dict("records")):
        ln = Linea(pedido=texto_pedido(r["pedido"]), destino=str(r["destino"] or "").strip(),
                   fecha=_fecha(r["fecha"]), codigo=norm(r["codigo"]), lote=norm(r["lote"]),
                   cantidad=num(r["cantidad"]), usar_clie=str(r["usar_clie"] or "").strip()[:1].upper() == "S")
        ln.estado = str(r["estado"] or "")
        ln.asignado, ln.pendiente = num(r["asignado"]), num(r["pendiente"])
        ln.observacion, ln.id_linea = str(r["observacion"] or ""), str(r["id_linea"] or "")
        ln._fila = i + 2  # número de fila "como en Excel" (para SIN-N#)
        out.append(ln)
    return out


def guardar_lineas(lineas: list[Linea]) -> None:
    filas = [{"pedido": l.pedido, "destino": l.destino, "fecha": l.fecha, "codigo": l.codigo, "lote": l.lote,
              "cantidad": l.cantidad, "usar_clie": "S" if l.usar_clie else "N", "estado": l.estado or None,
              "asignado": l.asignado if l.estado else None, "pendiente": l.pendiente if l.estado else None,
              "observacion": l.observacion or None, "id_linea": l.id_linea or None} for l in lineas]
    db.guardar("pedidos", pd.DataFrame(filas, columns=db.COLUMNAS["pedidos"]))


def maestro_lista() -> list[Maestro]:
    return cargar_maestro(db.leer("maestro"))


def cfg_actual() -> Cfg:
    return construir_cfg(db.get_config())


@dataclass
class Dia:
    """Estado completo del día, calculado desde la BD."""
    cfg: Cfg
    ctx: Contexto | None
    reab: ResultadoReab | None
    conteo: pd.DataFrame | None
    error: str = ""


def construir_contexto(con_asignaciones: bool = True) -> tuple[Cfg, Contexto | None, str]:
    cfg = cfg_actual()
    stock_df = db.leer("stock")
    if stock_df.empty:
        return cfg, None, "No hay STOCK cargado. Sube el inventario del Korber en 'Cargar datos'."
    ent = db.leer("entradas")
    try:
        pals = cargar_stock(stock_df, cfg, ent if len(ent) else None)
    except ValueError as e:
        return cfg, None, str(e)
    ctx = Contexto(pals, maestro_lista(), cfg)
    if con_asignaciones:
        ctx.restar_asignaciones(leer_asignaciones())
    return cfg, ctx, ""


def calcular_dia(con_conteo: bool = True) -> Dia:
    """Reabastecimiento, posiciones y conteo con el estado actual (sin escribir nada)."""
    cfg, ctx, err = construir_contexto()
    if ctx is None:
        return Dia(cfg, None, None, None, err)
    reab = calcular_reabastecimiento(ctx, db.leer("abast_cliente"))
    conteo = None
    if con_conteo:
        cz = db.leer("conteo_zona")
        if len(cz):
            conteo = calcular_conteo(ctx, reab, cz)
    return Dia(cfg, ctx, reab, conteo)


def refrescar() -> Dia:
    """Recalcula y guarda el estado de ABAST_CLIENTE y CONTEO_ZONA (como hacía la macro al procesar)."""
    dia = calcular_dia()
    if dia.ctx is None:
        return dia
    ab = db.leer("abast_cliente")
    if len(ab):
        est = ab["fila"].map(lambda f: dia.reab.abast.get(int(num(f)), ("", "", "")))
        ab["estado"] = est.map(lambda t: t[0])
        ab["paleta"] = est.map(lambda t: t[1] or None)
        ab["destino"] = est.map(lambda t: t[2] or None)
        db.guardar("abast_cliente", ab)
    if dia.conteo is not None:
        db.guardar("conteo_zona", dia.conteo)
    return dia


# ----------------------------------------------------------------------------
# acciones
# ----------------------------------------------------------------------------
def procesar() -> dict:
    cfg, ctx, err = construir_contexto()
    if ctx is None:
        return {"error": err}
    lineas = leer_lineas()
    pendientes = []
    for l in lineas:
        if l.codigo and l.estado == "" and l.cantidad > 0:
            if l.pedido == "":
                l.pedido = f"SIN-N{l._fila}"
            pendientes.append(l)
    conf = db.get_config()
    contador, resumen = procesar_pedidos(ctx, pendientes, int(conf.get("contador_lineas", 0)))
    db.set_config({"contador_lineas": contador})
    guardar_asignaciones(ctx.asignaciones)
    guardar_lineas(lineas)
    refrescar()
    return resumen


def anular(pedido: str) -> dict:
    pedido = pedido.strip()
    asig = leer_asignaciones()
    lineas = leer_lineas()
    nuevas, borradas, n = anular_pedido(asig, lineas, pedido)
    guardar_asignaciones(nuevas)
    guardar_lineas(lineas)
    refrescar()
    return {"borradas": borradas, "lineas": n}


def cerrar_dia(fecha: dt.date | None = None) -> dict:
    fecha = fecha or dt.date.today()
    asig = db.leer("asignaciones")
    if len(asig):
        asig["fecha_cierre"] = fecha.isoformat()
        db.guardar("historial", asig, agregar=True)
    ped = db.leer("pedidos")
    ped = ped[ped["codigo"].map(lambda x: norm(x) != "")]
    if len(ped):
        ped["fecha_cierre"] = fecha.isoformat()
        db.guardar("hist_pedidos", ped, agregar=True)
    n = (len(asig), len(ped))
    guardar_asignaciones([])
    guardar_lineas([])
    return {"asignaciones": n[0], "pedidos": n[1]}


def hoja(pedido: str) -> dict:
    return hoja_picking(leer_asignaciones(), pedido.strip())


def iffi(pedido: str = "", fecha_pl: dt.date | None = None) -> list[dict]:
    return generar_iffi(leer_asignaciones(), cfg_actual(), fecha_pl, pedido.strip())


def lista_desbloqueos():
    cfg, ctx, err = construir_contexto()
    if ctx is None:
        return [], []
    return desbloqueos(ctx)


def mapa_zona(dia: Dia) -> pd.DataFrame:
    n = int(db.get_config().get("g_columnas", 140))
    bloque = dia.cfg.pk_bloque[0] if dia.cfg.pk_bloque else "G"
    return estado_posiciones_zona(dia.ctx, dia.reab, bloque, n)


def actualizar_estados_asignaciones(cambios: dict[int, str]) -> int:
    """Guarda el Estado editable (Pendiente / En picking / Listo / Despachado) por posición de fila."""
    actual = db.leer("asignaciones")
    n = 0
    for pos, est in cambios.items():
        if 0 <= pos < len(actual) and est in ESTADOS_ASIG and actual.at[pos, "estado"] != est:
            actual.at[pos, "estado"] = est
            n += 1
    if n:
        db.guardar("asignaciones", actual)
    return n

def indicadores() -> dict:
    lineas = leer_lineas()
    asig = db.leer("asignaciones")
    ind = {"lineas": sum(1 for l in lineas if l.estado), "Completo": 0, "Parcial": 0, "Pendiente": 0,
           "cajas": float(sum(num(c) for c in asig["cajas"])) if len(asig) else 0.0,
           "clie": 0, "bajar": 0, "sin_procesar": sum(1 for l in lineas if l.codigo and not l.estado)}
    for l in lineas:
        if l.estado in ("Completo", "Parcial", "Pendiente"):
            ind[l.estado] += 1
    dia = calcular_dia(con_conteo=False)
    if dia.ctx is not None:
        ind["clie"] = len(desbloqueos(dia.ctx)[0])
        ind["bajar"] = sum(1 for r in dia.reab.filas if str(r["estado"]).startswith("BAJAR"))
    return ind

