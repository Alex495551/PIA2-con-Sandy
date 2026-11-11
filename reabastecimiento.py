"""Reabastecimiento y posiciones de picking (réplica de EscribirReabastecimiento / EscribirPosiciones, VBA v5.2).

Solo se bajan paletas que lo piden los pedidos (paletas de reserva picadas hoy) o el cliente (ABAST_CLIENTE).
Si nadie lo pide, no se baja nada. Por código nunca se bajan más paletas que posiciones libres
(N ubic. picking x profundidades).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from .asignacion import Contexto, add_obs
from .carga_datos import ORIG_ENT, SIN_FECHA, Pal, es_numerico, fecha_a_ord, norm, num, num_txt, ord_a_fecha, texto_pedido

COLS_REAB = ["n", "motivo", "codigo", "descripcion", "lote_solicitado", "id_paleta", "ubic_origen", "lote",
             "vence", "cajas", "pos_destino", "columnas", "estado", "observacion", "pedidos", "fecha_solicitud"]
COLS_POS = ["codigo", "descripcion", "bloque", "columnas", "n_ubic", "pos_requeridas", "posicion", "estado",
            "paleta_en_pos", "lote_en_pos", "cajas_en_pos", "paleta_que_baja", "lote_que_baja",
            "cajas_que_bajan", "prioridad", "observacion"]
MAX_FILAS = 1990

PRIORIDAD_POS = {"SE LLENA CON REABASTECIMIENTO": 1, "SALDO BAJO": 2, "OCUPADA POR OTRO CODIGO": 2,
                 "BLOQUEADA": 3, "VACIA": 4, "SIN COLUMNAS ASIGNADAS": 5}


def parse_columnas(t: str) -> list[int]:
    """'73 y 75', '2 Y 4' o '129' -> [73, 75]."""
    return [int(x) for x in re.findall(r"\d+", t or "")][:20]


@dataclass
class Solicitud:
    fila: int
    cod: str
    desc: str
    lote: str
    cant: float
    fecha: float  # ordinal (SIN_FECHA si no hay)
    ok: bool = False
    estado: str = ""
    id: str = ""
    dest: str = ""


@dataclass
class ResultadoReab:
    filas: list[dict] = field(default_factory=list)
    abast: dict[int, tuple[str, str, str]] = field(default_factory=dict)  # fila -> (estado, paleta, destino)
    movimientos: list[dict] = field(default_factory=list)  # cod, lote, cajas, dest, id
    posiciones: list[dict] = field(default_factory=list)


def leer_solicitudes(abast: pd.DataFrame | None) -> list[Solicitud]:
    out: list[Solicitud] = []
    if abast is None or len(abast) == 0:
        return out
    for r in abast.to_dict("records"):
        if norm(r.get("codigo")) == "" or not es_numerico(r.get("codigo")):
            continue
        f = r.get("fecha")
        out.append(Solicitud(fila=int(num(r.get("fila"))) or len(out) + 2, cod=norm(r["codigo"]),
                             desc=str(r.get("texto") or "").strip(), lote=norm(r.get("lote")),
                             cant=num(r.get("cantidad")), fecha=fecha_a_ord(f) if f not in (None, "") else SIN_FECHA))
    return out


class Reabastecedor:
    def __init__(self, ctx: Contexto, abast: pd.DataFrame | None):
        self.ctx = ctx
        self.cfg = ctx.cfg
        self.solicitudes = leer_solicitudes(abast)
        self.pos_usada: set[str] = set()
        self.mv: list[dict] = []
        self._cap: dict[str, list[int]] = {}  # cod -> [libres, maximo]

    # ---- cálculos de saldo ----
    def restante(self, p: Pal) -> float:
        sale = p.asig
        if self.cfg.reab_ord and p.on_ord > sale:
            sale = p.on_ord
        return p.on_hand - sale

    def saldo_bajo(self, p: Pal | None) -> bool:
        if p is None:
            return False
        q = self.restante(p)
        if q <= 0:
            return False
        mi = self.ctx.maestro_de(p.cod)
        if mi is None or mi.cpp <= 0 or self.cfg.umbral <= 0:
            return False
        return q < self.cfg.umbral * mi.cpp

    def saldo_en(self, loc: str) -> float:
        return sum(self.restante(p) for p in self.ctx.por_loc.get(loc, []) if self.restante(p) > 0)

    def pos_ocupada(self, loc: str) -> bool:
        if loc in self.pos_usada:
            return True
        for p in self.ctx.por_loc.get(loc, []):
            if self.restante(p) > 0 and not self.saldo_bajo(p):
                return True
        return False

    def posicion_libre(self, cod: str) -> str:
        mi = self.ctx.maestro_de(cod)
        if mi is None or mi.bloque == "":
            return ""
        for c in parse_columnas(mi.cols):
            for pr in range(1, self.cfg.profund + 1):
                loc = f"{mi.bloque}_{c:02d}_{self.cfg.nivel_pick}_{pr}"
                if not self.pos_ocupada(loc):
                    self.pos_usada.add(loc)
                    return loc
        return ""

    def capacidad(self, cod: str) -> list[int]:
        """[posiciones libres, posiciones máximas] del código (se calcula una vez y se va descontando)."""
        if cod in self._cap:
            return self._cap[cod]
        mi = self.ctx.maestro_de(cod)
        mx = 0
        if mi is not None and mi.bloque != "":
            if mi.nub > 0:
                mx = int(round(mi.nub * self.cfg.profund))
            else:
                mx = len(parse_columnas(mi.cols)) * self.cfg.profund
        ocup, vistos = 0, set()
        for p in self.ctx.por_cod.get(cod, []):
            if p.pick and self.restante(p) > 0 and not self.saldo_bajo(p) and p.loc not in vistos:
                ocup += 1
                vistos.add(p.loc)
        self._cap[cod] = [max(mx - ocup, 0), mx]
        return self._cap[cod]

    # ---- filas ----
    @staticmethod
    def _vacia() -> list:
        return [None] * 16

    def _fila_sin_bajar(self, a: list, n: int, motivo: str, cod: str, desc: str, lote: str, max_pos: int, extra: str):
        a[0], a[1], a[2], a[3], a[4] = n, motivo, cod, desc, lote
        mi = self.ctx.maestro_de(cod)
        if mi:
            a[11] = mi.cols
        if max_pos <= 0:
            a[12] = "NO SE BAJA - SKU SIN POSICIONES"
            a[13] = "El codigo no tiene N ubic. picking / columnas en MAESTRO"
        else:
            a[12] = "NO SE BAJA - POSICIONES COMPLETAS"
            a[13] = f"El codigo ya tiene sus {max_pos} posiciones (N ubic. x 2) llenas o reservadas por solicitudes anteriores"
        if extra:
            a[13] = add_obs(a[13], extra)

    def _fila_movimiento(self, a: list, n: int, motivo: str, p: Pal, lote_sol: str, peds: str):
        a[0], a[1], a[2], a[3], a[4] = n, motivo, p.cod, p.desc, lote_sol
        a[5], a[6], a[7] = p.id, p.loc, p.lote
        a[8] = ord_a_fecha(p.vence)
        a[9] = p.disp - p.asig
        mi = self.ctx.maestro_de(p.cod)
        if mi:
            a[11] = mi.cols
        dest = self.posicion_libre(p.cod)
        if dest:
            a[10] = dest
            a[12] = "BAJAR"
            s = self.saldo_en(dest)
            if s > 0:
                a[13] = (f"La posicion tiene un saldo de {num_txt(s)} cajas (menos del "
                         f"{int(self.cfg.umbral * 100 + 0.5)}% de paleta): juntar o bajar cuando se termine")
        else:
            a[12] = "BAJAR - POSICION POR DEFINIR"
            a[13] = ("Hay cupo segun N ubic. x 2, pero las columnas del MAESTRO no tienen una posicion libre: "
                     "revisar columnas asignadas")
        if p.origen == ORIG_ENT:
            a[13] = add_obs(a[13] or "", "Es entrada por confirmar")
        if p.es_clie and not p.usable:
            a[13] = add_obs(a[13] or "", "HOLD CLIE")
        a[14] = peds
        self.mv.append({"cod": p.cod, "lote": p.lote, "cajas": p.disp - p.asig, "dest": dest, "id": p.id})

    # ---- proceso principal ----
    def calcular(self) -> ResultadoReab:
        ctx, cfg = self.ctx, self.cfg
        stock = ctx.stock
        rqs = self.solicitudes
        orden = sorted(range(len(rqs)), key=lambda k: (rqs[k].fecha, rqs[k].fila))
        usado: set[int] = set()
        filas: list[list] = []

        # paletas de reserva picadas hoy por los pedidos (cajas sueltas)
        pic_hoy: dict[int, str] = {}
        for a in ctx.asignaciones:
            if a["tipo_salida"] == "Cajas sueltas" and a["zona"] == "Reserva":
                p = ctx.por_id_loc.get((str(a["id_paleta"]).strip(), str(a["ubicacion"]).strip().upper()))
                if p is not None:
                    ped = texto_pedido(a["pedido"])
                    cur = pic_hoy.get(id(p), "")
                    if ped not in cur:
                        cur += ("" if cur == "" else ", ") + ped
                    pic_hoy[id(p)] = cur

        # 1) paletas picadas en pedidos (dentro del límite de posiciones)
        for p in stock:
            if id(p) in pic_hoy and p.disp - p.asig > 0 and len(filas) < MAX_FILAS:
                cap = self.capacidad(p.cod)
                motivo = "Paleta picada en pedido"
                rq = None
                for k in orden:
                    r = rqs[k]
                    if not r.ok and r.cod == p.cod and r.lote == p.lote:
                        r.ok = True
                        rq = r
                        motivo = f"Paleta picada en pedido + solicitud del cliente (fila {r.fila})"
                        break
                a = self._vacia()
                n = len(filas) + 1
                if cap[0] > 0:
                    usado.add(id(p))
                    cap[0] -= 1
                    self._fila_movimiento(a, n, motivo, p, p.lote, pic_hoy[id(p)])
                    if rq:
                        rq.estado, rq.id, rq.dest = a[12], p.id, a[10] or ""
                else:
                    self._fila_sin_bajar(a, n, motivo, p.cod, p.desc, p.lote, cap[1],
                                         "Paleta picada queda en reserva: no hay posicion libre del codigo")
                    a[5], a[6], a[7], a[9], a[14] = p.id, p.loc, p.lote, p.disp - p.asig, pic_hoy[id(p)]
                    if rq:
                        rq.estado = a[12]
                filas.append(a)

        # 2) solicitudes del cliente por fecha, hasta llenar las posiciones del código
        for k in orden:
            r = rqs[k]
            if r.ok or len(filas) >= MAX_FILAS:
                continue
            cap = self.capacidad(r.cod)
            n = len(filas) + 1
            a = self._vacia()
            if cap[0] <= 0:
                self._fila_sin_bajar(a, n, f"Solicitud del cliente (fila {r.fila})", r.cod, r.desc, r.lote, cap[1], "")
                if r.fecha < SIN_FECHA:
                    a[15] = ord_a_fecha(r.fecha)
                r.estado = a[12]
            else:
                mi = ctx.maestro_de(r.cod)
                cpp = mi.cpp if mi else 0.0
                best = None
                for j in (1, 2):
                    for p in ctx.por_cod.get(r.cod, []):
                        if id(p) not in usado and not p.pick and p.usable and p.lote == r.lote and p.disp - p.asig > 0:
                            if j == 2 or ctx.es_picada(p, cpp):
                                if best is None or ctx._clave(p) < ctx._clave(best):
                                    best = p
                    if best is not None:
                        break
                if best is not None:
                    usado.add(id(best))
                    r.ok = True
                    cap[0] -= 1
                    motivo = f"Solicitud del cliente (fila {r.fila})"
                    if ctx.es_picada(best, cpp):
                        motivo += " - saldo de paleta picada"
                    self._fila_movimiento(a, n, motivo, best, r.lote, "")
                    r.estado, r.id, r.dest = a[12], best.id, a[10] or ""
                else:
                    otros = self._otros_lotes_reserva(r.cod, r.lote)
                    a[0], a[1] = n, f"Solicitud del cliente (fila {r.fila})"
                    a[2], a[3], a[4] = r.cod, r.desc, r.lote
                    a[12] = "SIN STOCK DEL LOTE"
                    a[13] = "Se continua con la siguiente fecha."
                    if otros:
                        a[13] += " Otros lotes en reserva: " + otros
                    r.estado = "SIN STOCK DEL LOTE"
                if r.fecha < SIN_FECHA:
                    a[15] = ord_a_fecha(r.fecha)
            filas.append(a)

        res = ResultadoReab()
        res.filas = [dict(zip(COLS_REAB, a)) for a in filas]
        for r in rqs:
            res.abast[r.fila] = (r.estado or "NO SE BAJA", r.id, r.dest)
        res.movimientos = list(self.mv)
        res.posiciones = self.posiciones()
        return res

    def _otros_lotes_reserva(self, cod: str, lote: str) -> str:
        s = ""
        for p in self.ctx.por_cod.get(cod, []):
            if not p.pick and p.usable and p.lote != lote and p.disp - p.asig > 0 and p.lote not in s:
                s += ("" if s == "" else ", ") + p.lote
        return s

    # ---- POSICIONES_PICKING ----
    def posiciones(self) -> list[dict]:
        ctx, cfg = self.ctx, self.cfg
        out: list[list] = []
        for m in ctx.maestro:
            if m.bloque == "" or len(out) >= 3900:
                continue
            cols = parse_columnas(m.cols)
            req = m.nub * cfg.profund if m.nub > 0 else len(cols) * cfg.profund
            obs = ""
            if m.nub > 0 and cols and len(cols) != m.nub:
                obs = f"MAESTRO indica {num_txt(m.nub)} ubic. pero hay {len(cols)} columna(s) asignada(s)"
            if not cols:
                a = [None] * 16
                a[0], a[1], a[2], a[3], a[4], a[5] = m.cod, m.desc, m.bloque, m.cols, m.nub, req
                a[7] = "SIN COLUMNAS ASIGNADAS"
                a[14] = PRIORIDAD_POS["SIN COLUMNAS ASIGNADAS"]
                a[15] = "Completa 'Columnas G asignadas' en MAESTRO"
                out.append(a)
                continue
            for c in cols:
                for pr in range(1, cfg.profund + 1):
                    loc = f"{m.bloque}_{c:02d}_{cfg.nivel_pick}_{pr}"
                    a = [None] * 16
                    a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[15] = m.cod, m.desc, m.bloque, m.cols, m.nub, req, loc, obs
                    cajas, en_pos, otro, bloq = 0.0, None, "", ""
                    for p in ctx.por_loc.get(loc, []):
                        if p.cod == m.cod:
                            if self.restante(p) > 0:
                                cajas += self.restante(p)
                                if en_pos is None:
                                    en_pos = p
                                if not p.usable and not p.es_clie:
                                    bloq = p.hold
                        elif self.restante(p) > 0:
                            if p.cod not in otro:
                                otro += ("" if otro == "" else ", ") + p.cod
                    if otro:
                        est = "OCUPADA POR OTRO CODIGO"
                        a[15] = add_obs(obs, f"En la posicion hay: {otro} (reubicar)")
                    elif bloq:
                        est = "BLOQUEADA"
                        a[15] = add_obs(obs, f"Paleta del SKU con HOLD {bloq}")
                    elif cajas > 0 and self.saldo_bajo(en_pos):
                        est = "SALDO BAJO"
                        a[15] = add_obs(obs, f"Queda menos del {int(cfg.umbral * 100 + 0.5)}% de una paleta: "
                                             "cuenta como posicion libre para reabastecer")
                    elif cajas > 0:
                        est = "LLENA"
                    else:
                        est = "VACIA"
                    if en_pos is not None:
                        a[8], a[9], a[10] = en_pos.id, en_pos.lote, cajas
                    for t in self.mv:
                        if t["dest"] == loc:
                            a[11], a[12], a[13] = t["id"], t["lote"], t["cajas"]
                            est = "SE LLENA CON REABASTECIMIENTO"
                            break
                    if est == "VACIA":
                        a[15] = add_obs(a[15] or "", "Sin solicitud: no se baja paleta")
                    a[7] = est
                    a[14] = PRIORIDAD_POS.get(est, 6)
                    out.append(a)
        return [dict(zip(COLS_POS, a)) for a in out]


def calcular_reabastecimiento(ctx: Contexto, abast: pd.DataFrame | None) -> ResultadoReab:
    return Reabastecedor(ctx, abast).calcular()


def estado_posiciones_zona(ctx: Contexto, res: ResultadoReab, bloque: str = "G", n_cols: int = 140) -> pd.DataFrame:
    """Estado de TODAS las posiciones de la zona (para el mapa visual). Las posiciones de picking sin código
    asignado en MAESTRO se muestran como 'SIN ASIGNAR' (vacías) u 'OCUPADA SIN ASIGNAR' (tienen stock)."""
    cfg = ctx.cfg
    rb = Reabastecedor(ctx, None)
    asignadas = {r["posicion"]: r for r in res.posiciones if r["posicion"]}
    filas = []
    for c in range(1, n_cols + 1):
        for pr in range(1, cfg.profund + 1):
            loc = f"{bloque}_{c:02d}_{cfg.nivel_pick}_{pr}"
            r = asignadas.get(loc)
            if r:
                est, cod, det = r["estado"], r["codigo"], r["observacion"] or ""
                cajas = r["cajas_en_pos"] or 0
                lote = r["lote_en_pos"] or ""
            else:
                ocup = [p for p in ctx.por_loc.get(loc, []) if rb.restante(p) > 0]
                cajas = sum(rb.restante(p) for p in ocup)
                est = "OCUPADA SIN ASIGNAR" if ocup else "SIN ASIGNAR"
                cod = ocup[0].cod if ocup else ""
                lote = ocup[0].lote if ocup else ""
                det = ""
            filas.append({"posicion": loc, "columna": c, "prof": pr, "estado": est, "codigo": cod,
                          "lote": lote, "cajas": cajas, "detalle": det})
    return pd.DataFrame(filas)
