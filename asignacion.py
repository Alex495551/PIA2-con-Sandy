"""Asignación de paletas a las líneas de pedido (réplica de AsignarLinea y afines del VBA v5.2)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .carga_datos import (ORIG_ENT, SIN_FECHA, Maestro, Pal, norm, num, num_txt, ord_a_fecha,
                          texto_pedido)
from .config import Cfg

COLS_ASIG = ["id_linea", "pedido", "destino", "fecha_despacho", "codigo", "descripcion", "lote", "vence",
             "id_paleta", "ubicacion", "bloque", "columna", "nivel", "profundidad", "zona", "tipo_salida",
             "cajas", "uma", "orden_recorrido", "estado", "fecha_proceso", "origen"]


def add_obs(a: str, b: str) -> str:
    return b if not a else f"{a} | {b}"


@dataclass
class Linea:
    """Una línea de pedido (fila de PEDIDOS)."""
    pedido: str
    destino: str
    fecha: dt.date | None
    codigo: str
    lote: str
    cantidad: float
    usar_clie: bool = False
    # resultados
    estado: str = ""
    asignado: float = 0.0
    pendiente: float = 0.0
    observacion: str = ""
    id_linea: str = ""


class Contexto:
    """Stock en memoria + maestro + config (lo que el VBA guarda en variables de módulo)."""

    def __init__(self, stock: list[Pal], maestro: list[Maestro], cfg: Cfg):
        self.stock = stock
        self.maestro = maestro
        self.cfg = cfg
        self._m = {m.cod: m for m in maestro}  # el VBA toma la primera coincidencia
        for m in reversed(maestro):
            self._m[m.cod] = m
        self.por_cod: dict[str, list[Pal]] = {}
        self.por_id_loc: dict[tuple[str, str], Pal] = {}
        self.por_loc: dict[str, list[Pal]] = {}
        for p in stock:
            self.por_cod.setdefault(p.cod, []).append(p)
            self.por_id_loc.setdefault((p.id, p.loc), p)
            self.por_loc.setdefault(p.loc, []).append(p)
        self.asignaciones: list[dict] = []
        self._clie_usadas = 0

    # --- maestro ---
    def maestro_de(self, cod: str) -> Maestro | None:
        return self._m.get(cod)

    # --- stock ya asignado en el día ---
    def restar_asignaciones(self, asignaciones: list[dict]) -> None:
        for a in asignaciones:
            p = self.por_id_loc.get((str(a["id_paleta"]).strip(), str(a["ubicacion"]).strip().upper()))
            if p is not None:
                p.asig += num(a["cajas"])
        self.asignaciones = [dict(a) for a in asignaciones]

    # --- FEFO ---
    @staticmethod
    def _clave(p: Pal):
        return (p.vence, p.ingreso, p.disp - p.asig, p.loc)

    def candidatos(self, cod: str, lote: str, usar_clie: bool, solo_picking: bool, min_disp: float) -> list[Pal]:
        out = []
        for p in self.por_cod.get(cod, []):
            if (lote == "" or p.lote == lote) and p.pick == solo_picking:
                if p.usable or (p.es_clie and usar_clie):
                    if p.disp - p.asig >= min_disp:
                        out.append(p)
        out.sort(key=self._clave)  # estable: igual que el orden por inserción del VBA
        return out

    @staticmethod
    def es_picada(p: Pal, cpp: float) -> bool:
        """Paleta ya abierta: se le sacó algo hoy o tiene menos cajas que una paleta completa."""
        return p.asig > 0 or (cpp > 0 and p.disp < cpp)

    # --- registro ---
    def _registrar(self, linea_id: str, pedido: str, destino: str, fecha, p: Pal, cajas: float, tipo: str,
                   uma: str, ahora: dt.datetime) -> None:
        clie = p.es_clie and not p.usable
        self.asignaciones.append({
            "id_linea": linea_id, "pedido": pedido, "destino": destino, "fecha_despacho": fecha,
            "codigo": p.cod, "descripcion": p.desc, "lote": p.lote, "vence": ord_a_fecha(p.vence),
            "id_paleta": p.id, "ubicacion": p.loc, "bloque": p.bloque, "columna": p.col, "nivel": p.niv,
            "profundidad": p.prof, "zona": "Picking" if p.pick else "Reserva", "tipo_salida": tipo,
            "cajas": cajas, "uma": uma, "orden_recorrido": 0, "estado": "Pendiente",
            "fecha_proceso": ahora, "origen": f"{p.origen} (CLIE)" if clie else p.origen,
        })
        if clie:
            self._clie_usadas += 1
        p.asig += cajas

    # --- una línea ---
    def asignar_linea(self, ln: Linea, id_linea: str, ahora: dt.datetime | None = None) -> str:
        ahora = ahora or dt.datetime.now()
        self._clie_usadas = 0
        cod, lote, qty = ln.codigo, ln.lote, ln.cantidad
        mi = self.maestro_de(cod)
        if mi:
            cpp, desc, uma = mi.cpp, mi.desc, mi.uma
        else:
            cpp, desc, uma = 0.0, "", "CJ"
        hay_cod = hay_lote = False
        for p in self.por_cod.get(cod, []):
            hay_cod = True
            if desc == "":
                desc = p.desc
            if lote == "" or p.lote == lote:
                hay_lote = True
        obs = ""
        if cpp > 0:
            n_full = int(qty // cpp)
            resto = qty - n_full * cpp
        else:
            n_full, resto = 0, qty
            obs = add_obs(obs, "Sin cajas/paleta en MAESTRO: todo se trato como cajas sueltas")
        if not hay_cod:
            obs = add_obs(obs, "Codigo sin stock en el inventario")
        elif not hay_lote:
            obs = add_obs(obs, f"Lote {lote} no existe en el inventario")

        asignado = 0.0
        # 1) PALETAS COMPLETAS: reserva primero, luego picking; solo íntegras
        if n_full > 0:
            for pasada in (1, 2):
                if n_full <= 0:
                    break
                for p in self.candidatos(cod, lote, ln.usar_clie, pasada == 2, cpp):
                    if n_full <= 0:
                        break
                    self._registrar(id_linea, ln.pedido, ln.destino, ln.fecha, p, cpp, "Paleta completa", uma, ahora)
                    asignado += cpp
                    n_full -= 1
            if n_full > 0:
                obs = add_obs(obs, f"Faltan {n_full} paleta(s) completa(s) integras: quedan PENDIENTES")

        # 2) CAJAS SUELTAS (5 pasadas)
        need = resto
        sust = ""
        if need > 0:
            for pasada in range(1, 6):
                if need <= 0:
                    break
                if pasada == 1:
                    cand = self.candidatos(cod, lote, ln.usar_clie, True, 0.000001)
                elif pasada == 2:
                    cand = self.candidatos(cod, "", ln.usar_clie, True, 0.000001) if (lote != "" and self.cfg.sust_lote) else []
                elif pasada == 3:
                    cand = [p for p in self.candidatos(cod, lote, ln.usar_clie, False, 0.000001) if self.es_picada(p, cpp)]
                elif pasada == 4:
                    cand = ([p for p in self.candidatos(cod, "", ln.usar_clie, False, 0.000001) if self.es_picada(p, cpp)]
                            if (lote != "" and self.cfg.sust_lote) else [])
                else:
                    cand = self.candidatos(cod, lote, ln.usar_clie, False, 0.000001)
                for p in cand:
                    if need <= 0:
                        break
                    tomar = min(p.disp - p.asig, need)
                    if tomar > 0:
                        self._registrar(id_linea, ln.pedido, ln.destino, ln.fecha, p, tomar, "Cajas sueltas", uma, ahora)
                        asignado += tomar
                        need -= tomar
                        if lote != "" and p.lote != lote and p.lote not in sust:
                            sust += ("" if sust == "" else ", ") + p.lote
            if sust:
                obs = add_obs(obs, f"Cajas sueltas tomadas de picking con otro lote: {sust}")
            if need > 0:
                obs = add_obs(obs, f"Faltan {num_txt(need)} cajas sueltas: despacho PARCIAL")
        if self._clie_usadas > 0:
            obs = add_obs(obs, f"Usa {self._clie_usadas} paleta(s) CLIE: desbloquear (ver DESBLOQUEOS)")

        if asignado >= qty:
            estado = "Completo"
        elif asignado > 0:
            estado = "Parcial"
        else:
            estado = "Pendiente"
        ln.estado, ln.asignado, ln.pendiente = estado, asignado, qty - asignado
        ln.observacion, ln.id_linea = obs, id_linea
        return estado

    # --- orden de recorrido ---
    def clave_ruta(self, tipo: str, bloque: str, c, nv, pf) -> str:
        t = "1" if tipo == "Cajas sueltas" else "2"
        ord_b = 90
        for k, b in enumerate(self.cfg.pk_bloque, 1):
            if b == bloque:
                ord_b = k
                break
        return f"{t}{ord_b:02d}{(bloque + '    ')[:4]}{int(c):03d}{int(nv):02d}{int(pf)}"

    def actualizar_orden_recorrido(self) -> None:
        a = self.asignaciones
        claves = [self.clave_ruta(x["tipo_salida"], str(x["bloque"]), num(x["columna"]), num(x["nivel"]),
                                  num(x["profundidad"])) for x in a]
        peds = [texto_pedido(x["pedido"]) for x in a]
        grupos: dict[str, list[int]] = {}
        for i, p in enumerate(peds):
            grupos.setdefault(p, []).append(i)
        for idx in grupos.values():
            orden = sorted(idx, key=lambda i: (claves[i], i))
            for rk, i in enumerate(orden, 1):
                a[i]["orden_recorrido"] = rk


def procesar_pedidos(ctx: Contexto, lineas: list[Linea], contador: int,
                     ahora: dt.datetime | None = None) -> tuple[int, dict]:
    """Procesa las líneas (en orden). Devuelve (nuevo contador, resumen)."""
    res = {"lineas": 0, "Completo": 0, "Parcial": 0, "Pendiente": 0}
    for ln in lineas:
        if ln.codigo == "" or ln.cantidad <= 0:
            continue
        if ln.pedido == "":
            ln.pedido = "SIN-N"
        contador += 1
        est = ctx.asignar_linea(ln, f"L{contador:06d}", ahora)
        res["lineas"] += 1
        res[est] += 1
    ctx.actualizar_orden_recorrido()
    return contador, res


def hoja_picking(asignaciones: list[dict], pedido: str) -> dict:
    """Hoja de picking de un pedido, ordenada por recorrido, con marcas (E) y (CLIE)."""
    filas = [a for a in asignaciones if texto_pedido(a["pedido"]) == pedido]
    filas.sort(key=lambda a: num(a["orden_recorrido"]))
    if not filas:
        return {"pedido": pedido, "destino": "", "fecha": None, "filas": [], "total": 0, "notas": []}
    out, tot, hay_e, hay_c = [], 0.0, False, False
    for k, a in enumerate(filas, 1):
        org = str(a.get("origen") or "")
        zona = a["zona"]
        if ORIG_ENT in org:
            zona += " (E)"
            hay_e = True
        elif "CLIE" in org:
            zona += " (CLIE)"
            hay_c = True
        out.append({"N°": k, "Ubicación": a["ubicacion"], "Zona": zona, "ID paleta": a["id_paleta"],
                    "Código": a["codigo"], "Descripción": a["descripcion"], "Lote": a["lote"],
                    "Vence": a["vence"], "Tipo": a["tipo_salida"], "Cajas": num(a["cajas"]), "UMA": a["uma"]})
        tot += num(a["cajas"])
    notas = []
    if hay_e:
        notas.append("(E) = paleta de una entrada pendiente de confirmar en el Korber: confirmarla antes de despachar.")
    if hay_c:
        notas.append("(CLIE) = paleta retenida por el cliente: desbloquearla en el Korber antes de despachar (ver DESBLOQUEOS).")
    return {"pedido": pedido, "destino": filas[0]["destino"], "fecha": filas[0]["fecha_despacho"],
            "filas": out, "total": tot, "notas": notas}


def anular_pedido(asignaciones: list[dict], lineas: list[Linea], pedido: str) -> tuple[list[dict], int, int]:
    """Borra las asignaciones del pedido y limpia el resultado de sus líneas. -> (asignaciones, borradas, lineas)."""
    nuevas = [a for a in asignaciones if texto_pedido(a["pedido"]) != pedido]
    borradas = len(asignaciones) - len(nuevas)
    n = 0
    for ln in lineas:
        if texto_pedido(ln.pedido) == pedido:
            ln.estado, ln.asignado, ln.pendiente, ln.observacion, ln.id_linea = "", 0.0, 0.0, "", ""
            n += 1
    return nuevas, borradas, n


def desbloqueos(ctx: Contexto) -> tuple[list[dict], list[dict]]:
    """Paletas CLIE asignadas (detalle) y resumen por código+lote (EscribirDesbloqueos)."""
    det: dict[int, dict] = {}
    orden: list[int] = []
    for a in ctx.asignaciones:
        p = ctx.por_id_loc.get((str(a["id_paleta"]).strip(), str(a["ubicacion"]).strip().upper()))
        if p is None or not p.es_clie:
            continue
        a["origen"] = a.get("origen") or ""
        if "CLIE" not in str(a["origen"]):
            a["origen"] = (str(a["origen"]) + " (CLIE)").strip()
        k = id(p)
        if k not in det:
            det[k] = {"p": p, "cajas": 0.0, "peds": "", "dests": ""}
            orden.append(k)
        d = det[k]
        d["cajas"] += num(a["cajas"])
        ped, dst = texto_pedido(a["pedido"]), str(a["destino"]).strip()
        if ped not in d["peds"]:
            d["peds"] += ("" if not d["peds"] else ", ") + ped
        if dst not in d["dests"]:
            d["dests"] += ("" if not d["dests"] else ", ") + dst
    detalle, resumen, idx = [], [], {}
    for k in orden:
        d = det[k]
        p: Pal = d["p"]
        detalle.append({"Código": p.cod, "Descripción": p.desc, "Lote": p.lote, "ID paleta": p.id,
                        "Ubicación": p.loc, "Hold": p.hold, "Cajas en paleta": p.disp,
                        "Cajas asignadas": d["cajas"], "Pedido(s)": d["peds"], "Destino(s)": d["dests"],
                        "Acción": "Desbloquear en Korber"})
        key = (p.cod, p.lote)
        if key not in idx:
            idx[key] = len(resumen)
            resumen.append({"Código": p.cod, "Descripción": p.desc, "Lote a desbloquear": p.lote,
                            "N° paletas": 0, "Cajas asignadas": 0.0, "Pedido(s)": ""})
        r = resumen[idx[key]]
        r["N° paletas"] += 1
        r["Cajas asignadas"] += d["cajas"]
        if d["peds"] not in r["Pedido(s)"]:
            r["Pedido(s)"] += ("" if not r["Pedido(s)"] else ", ") + d["peds"]
    return detalle, resumen
