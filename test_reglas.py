"""Tests unitarios de las reglas de negocio con inventarios mínimos armados a mano."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from core.asignacion import Contexto, Linea, procesar_pedidos
from core.carga_datos import Maestro, cargar_stock, parse_fecha
from core.config import construir_cfg
from core.iffi import N_CAMPOS, generar_iffi, validar_iffi
from core.reabastecimiento import calcular_reabastecimiento

COD = "1001"
COLS = ["CUST CODE", "LOC CODE", "TO CHAR INVT ORG RECD DATE", "INVT LEV1", "INVT LEV2", "INVT LEV3", "INVT LEV4",
        "ON HAND QTY", "DISPONIBLE", "ON ORD QTY", "RETENIDO", "HOLD CODE", "FECHA EXP", "ITEM DES1"]


def pal(id, loc, lote="L1", disp=100, hold="*", vence="01-JAN-28", ingreso="01-JAN-26", on_hand=None,
        on_ord=0, ret=0, cod=COD):
    return ["NESTLE", loc, ingreso, cod, lote, "010128", id, disp if on_hand is None else on_hand, disp, on_ord,
            ret, hold, vence, "PRODUCTO " + cod]


def armar(filas, cfg_extra=None, maestro=None, abast=None, asignaciones=None):
    cfg = construir_cfg(cfg_extra or {})
    df = pd.DataFrame(filas, columns=COLS)
    stock = cargar_stock(df, cfg)
    m = maestro or [Maestro(cod=COD, desc="PRODUCTO", cpp=100, bloque="G", cols="1 y 3", nub=2)]
    ctx = Contexto(stock, m, cfg)
    if asignaciones:
        ctx.restar_asignaciones(asignaciones)
    return ctx


def pedir(ctx, cantidad, lote="", clie=False, cod=COD, pedido="P1"):
    ln = Linea(pedido=pedido, destino="LIMA", fecha=dt.date(2026, 11, 10), codigo=cod, lote=lote,
               cantidad=cantidad, usar_clie=clie)
    procesar_pedidos(ctx, [ln], 0)
    return ln


def salidas(ctx):
    return [(a["id_paleta"], a["tipo_salida"], a["cajas"]) for a in ctx.asignaciones]


# ---------------------------------------------------------------- paletas completas
def test_paleta_completa_sale_de_reserva_antes_que_de_picking():
    ctx = armar([pal("PK", "G_01_1_1"), pal("RS", "A_01_1_1")])
    ln = pedir(ctx, 100)
    assert salidas(ctx) == [("RS", "Paleta completa", 100)]
    assert ln.estado == "Completo"


def test_paleta_completa_solo_paletas_integras_y_queda_pendiente():
    ctx = armar([pal("RS", "A_01_1_1", disp=90)])
    ln = pedir(ctx, 100)
    assert salidas(ctx) == []  # una paleta con 90 no sirve como paleta completa
    assert ln.estado == "Pendiente"
    assert "Faltan 1 paleta(s) completa(s)" in ln.observacion


def test_paletas_completas_mas_cajas_sueltas_en_picking_primero():
    ctx = armar([pal("R1", "A_01_1_1"), pal("R2", "A_02_1_1"), pal("PK", "G_01_1_1", disp=80)])
    ln = pedir(ctx, 250)  # 2 paletas + 50 cajas sueltas
    assert salidas(ctx) == [("R1", "Paleta completa", 100), ("R2", "Paleta completa", 100), ("PK", "Cajas sueltas", 50)]
    assert ln.estado == "Completo"


def test_paletas_completas_respetan_fefo_y_lote_exacto():
    ctx = armar([pal("TARDE", "A_01_1_1", lote="L1", vence="01-JAN-29"), pal("TEMPRANO", "A_02_1_1", lote="L1", vence="01-JAN-27"),
                 pal("OTROLOTE", "A_03_1_1", lote="L2", vence="01-JAN-26")])
    pedir(ctx, 100, lote="L1")
    assert salidas(ctx) == [("TEMPRANO", "Paleta completa", 100)]


# ---------------------------------------------------------------- cajas sueltas
def test_cajas_sueltas_con_lote_usa_solo_ese_lote_en_picking():
    ctx = armar([pal("A", "G_01_1_1", lote="L1", disp=40), pal("B", "G_01_1_2", lote="L2", disp=40, vence="01-JAN-27")])
    ln = pedir(ctx, 30, lote="L1")
    assert salidas(ctx) == [("A", "Cajas sueltas", 30)]
    assert ln.estado == "Completo" and ln.observacion == ""


def test_cajas_sueltas_sin_lote_van_por_fefo():
    ctx = armar([pal("TARDE", "G_01_1_1", lote="L1", disp=40, vence="01-JAN-29"),
                 pal("TEMPRANO", "G_01_1_2", lote="L2", disp=40, vence="01-JAN-27")])
    pedir(ctx, 30)
    assert salidas(ctx) == [("TEMPRANO", "Cajas sueltas", 30)]


def test_cajas_sueltas_otro_lote_de_picking_si_la_opcion_esta_activa():
    filas = [pal("A", "G_01_1_1", lote="L1", disp=10), pal("B", "G_01_1_2", lote="L2", disp=40),
             pal("R", "A_01_1_1", lote="L1", disp=100)]
    ctx = armar(filas)
    ln = pedir(ctx, 30, lote="L1")
    assert salidas(ctx) == [("A", "Cajas sueltas", 10), ("B", "Cajas sueltas", 20)]
    assert "otro lote: L2" in ln.observacion
    # con la opción en N no se sustituye el lote: lo que falta sale de la reserva (paleta íntegra del mismo lote)
    ctx = armar(filas, {"sust_lote": False})
    pedir(ctx, 30, lote="L1")
    assert salidas(ctx) == [("A", "Cajas sueltas", 10), ("R", "Cajas sueltas", 20)]


def test_cajas_sueltas_de_reserva_primero_paleta_ya_picada_del_lote():
    ctx = armar([pal("ENTERA", "A_01_1_1", lote="L1", disp=100, vence="01-JAN-27"),
                 pal("PICADA", "A_02_1_1", lote="L1", disp=60, vence="01-JAN-29")])
    pedir(ctx, 30, lote="L1")
    assert salidas(ctx) == [("PICADA", "Cajas sueltas", 30)]  # abre primero la que ya estaba picada, aunque vence después


def test_paleta_picada_hoy_cuenta_como_picada():
    ctx = armar([pal("P1", "A_01_1_1", lote="L1", disp=100, vence="01-JAN-29"),
                 pal("P2", "A_02_1_1", lote="L1", disp=100, vence="01-JAN-27")])
    pedir(ctx, 10, lote="L1", pedido="UNO")   # sin picada previa: FEFO abre P2
    pedir(ctx, 10, lote="L1", pedido="DOS")   # ahora P2 ya está picada: sigue con P2
    assert [s[0] for s in salidas(ctx)] == ["P2", "P2"]


def test_cajas_sueltas_parcial_cuando_no_alcanza():
    ctx = armar([pal("A", "G_01_1_1", disp=20)])
    ln = pedir(ctx, 50)
    assert ln.estado == "Parcial" and ln.asignado == 20 and ln.pendiente == 30
    assert "Faltan 30 cajas sueltas: despacho PARCIAL" in ln.observacion


def test_pedido_sin_stock_queda_pendiente():
    ctx = armar([pal("A", "G_01_1_1", disp=20)], {"sust_lote": False})
    ln = pedir(ctx, 50, lote="NOEXISTE")
    assert ln.estado == "Pendiente" and "no existe en el inventario" in ln.observacion
    # con sustitución de lote activa (opción S) toma otro lote de picking y avisa
    ctx = armar([pal("A", "G_01_1_1", disp=20)])
    ln = pedir(ctx, 50, lote="NOEXISTE")
    assert ln.estado == "Parcial" and "otro lote: L1" in ln.observacion


# ---------------------------------------------------------------- CLIE
def test_clie_solo_se_usa_si_la_linea_lo_autoriza():
    filas = [pal("C", "A_01_1_1", hold="CLIE", disp=0, ret=100, on_hand=100)]
    ctx = armar(filas)
    assert pedir(ctx, 100).estado == "Pendiente"
    ctx = armar(filas)
    ln = pedir(ctx, 100, clie=True)
    assert ln.estado == "Completo"
    assert ctx.asignaciones[0]["origen"].endswith("(CLIE)")
    assert "Usa 1 paleta(s) CLIE" in ln.observacion


def test_hold_no_usable_nunca_se_asigna():
    ctx = armar([pal("X", "A_01_1_1", hold="CADU")])
    assert pedir(ctx, 100, clie=True).estado == "Pendiente"


# ---------------------------------------------------------------- reabastecimiento
def _abast(*filas):
    return pd.DataFrame([{"fila": i + 3, "codigo": COD, "texto": "", "lote": l, "cantidad": 0, "ubicacion": "RACK",
                          "fecha": f} for i, (l, f) in enumerate(filas)])


def test_si_nadie_lo_pide_no_se_baja_nada():
    ctx = armar([pal("R", "A_01_1_1")])
    assert calcular_reabastecimiento(ctx, None).filas == []


def test_tope_de_posiciones_por_codigo():
    # N ubic = 1 -> 2 posiciones; una ya ocupada en G nivel 1 => solo cabe 1 paleta más
    m = [Maestro(cod=COD, desc="P", cpp=100, bloque="G", cols="1", nub=1)]
    filas = [pal("ENPISO", "G_01_1_1", lote="L9")] + [pal(f"R{i}", f"A_0{i}_1_1", lote="L1") for i in range(1, 4)]
    ctx = armar(filas, maestro=m)
    res = calcular_reabastecimiento(ctx, _abast(("L1", dt.date(2026, 11, 1)), ("L1", dt.date(2026, 11, 2)),
                                                ("L1", dt.date(2026, 11, 3))))
    estados = [f["estado"] for f in res.filas]
    assert estados == ["BAJAR", "NO SE BAJA - POSICIONES COMPLETAS", "NO SE BAJA - POSICIONES COMPLETAS"]
    assert res.filas[0]["pos_destino"] == "G_01_1_2"


def test_sku_sin_posiciones_en_maestro():
    m = [Maestro(cod=COD, desc="P", cpp=100)]
    ctx = armar([pal("R", "A_01_1_1")], maestro=m)
    res = calcular_reabastecimiento(ctx, _abast(("L1", dt.date(2026, 11, 1))))
    assert res.filas[0]["estado"] == "NO SE BAJA - SKU SIN POSICIONES"


def test_prioridad_por_fecha_aunque_este_despues_en_la_tabla():
    m = [Maestro(cod=COD, desc="P", cpp=100, bloque="G", cols="1", nub=1)]
    filas = [pal("ENPISO", "G_01_1_1", lote="X"), pal("RA", "A_01_1_1", lote="LA"), pal("RB", "A_02_1_1", lote="LB")]
    ctx = armar(filas, maestro=m)
    # fila de la tabla: LA (fecha 5) viene primero, LB (fecha 2) después -> LB debe ganar la única posición
    res = calcular_reabastecimiento(ctx, _abast(("LA", dt.date(2026, 11, 5)), ("LB", dt.date(2026, 11, 2))))
    por_lote = {f["lote_solicitado"]: f["estado"] for f in res.filas}
    assert por_lote["LB"] == "BAJAR" and por_lote["LA"].startswith("NO SE BAJA")
    assert res.filas[0]["lote_solicitado"] == "LB"


def test_igual_fecha_manda_el_orden_de_la_tabla():
    m = [Maestro(cod=COD, desc="P", cpp=100, bloque="G", cols="1", nub=1)]
    filas = [pal("ENPISO", "G_01_1_1", lote="X"), pal("RA", "A_01_1_1", lote="LA"), pal("RB", "A_02_1_1", lote="LB")]
    ctx = armar(filas, maestro=m)
    f = dt.date(2026, 11, 2)
    res = calcular_reabastecimiento(ctx, _abast(("LA", f), ("LB", f)))
    assert {x["lote_solicitado"]: x["estado"] for x in res.filas}["LA"] == "BAJAR"


def test_sin_stock_del_lote_sigue_con_la_siguiente_fecha():
    m = [Maestro(cod=COD, desc="P", cpp=100, bloque="G", cols="1", nub=1)]
    ctx = armar([pal("RB", "A_02_1_1", lote="LB")], maestro=m)
    res = calcular_reabastecimiento(ctx, _abast(("LA", dt.date(2026, 11, 1)), ("LB", dt.date(2026, 11, 2))))
    assert [f["estado"] for f in res.filas] == ["SIN STOCK DEL LOTE", "BAJAR"]


def test_paleta_picada_en_pedido_se_baja_y_cuenta_para_la_solicitud_del_cliente():
    m = [Maestro(cod=COD, desc="P", cpp=100, bloque="G", cols="1", nub=1)]
    ctx = armar([pal("RS", "A_01_1_1", lote="L1")], maestro=m)
    pedir(ctx, 30, lote="L1")  # abre la paleta de reserva (sin picking)
    res = calcular_reabastecimiento(ctx, _abast(("L1", dt.date(2026, 11, 1))))
    assert len(res.filas) == 1
    assert res.filas[0]["motivo"].startswith("Paleta picada en pedido + solicitud del cliente")
    assert res.filas[0]["estado"] == "BAJAR" and res.filas[0]["cajas"] == 70


def test_saldo_bajo_menos_del_5_por_ciento_cuenta_como_posicion_libre():
    m = [Maestro(cod=COD, desc="P", cpp=100, bloque="G", cols="1", nub=1)]
    for saldo, esperado in ((4, "BAJAR"), (6, "NO SE BAJA - POSICIONES COMPLETAS")):
        filas = [pal("P1", "G_01_1_1", lote="X", disp=saldo), pal("P2", "G_01_1_2", lote="X", disp=100),
                 pal("RS", "A_01_1_1", lote="L1")]
        ctx = armar(filas, maestro=m)
        res = calcular_reabastecimiento(ctx, _abast(("L1", dt.date(2026, 11, 1))))
        assert res.filas[0]["estado"] == esperado, saldo
        if esperado == "BAJAR":
            assert res.filas[0]["pos_destino"] == "G_01_1_1"
            assert "saldo de 4 cajas" in res.filas[0]["observacion"]


# ---------------------------------------------------------------- ON ORD
def test_on_ord_se_toma_el_maximo_con_lo_asignado_no_la_suma():
    m = [Maestro(cod=COD, desc="P", cpp=100, bloque="G", cols="1", nub=1)]
    filas = [pal("P1", "G_01_1_1", disp=100, on_hand=100, on_ord=50)]
    ctx = armar(filas, maestro=m)
    from core.reabastecimiento import Reabastecedor
    rb = Reabastecedor(ctx, None)
    p = ctx.stock[0]
    p.asig = 30
    assert rb.restante(p) == 50        # max(50, 30) = 50 -> 100 - 50 (no 100 - 80)
    p.asig = 70
    assert rb.restante(p) == 30        # max(50, 70) = 70
    ctx2 = armar(filas, {"reab_ord": False}, maestro=m)
    ctx2.stock[0].asig = 30
    assert Reabastecedor(ctx2, None).restante(ctx2.stock[0]) == 70


def test_sumar_on_ord_al_disponible_es_configurable():
    fila = pal("R", "A_01_1_1", disp=60, on_ord=40, on_hand=100)
    assert armar([fila]).stock[0].disp == 60
    assert armar([fila], {"sumar_on_ord": True}).stock[0].disp == 100


# ---------------------------------------------------------------- entradas por confirmar
def test_entrada_por_confirmar_se_suma_como_paleta_libre_y_se_ignora_si_ya_esta_en_stock():
    cfg = construir_cfg({})
    inv = pd.DataFrame([pal("EXISTE", "A_01_1_1")], columns=COLS)
    ent = pd.DataFrame([
        {"CUST CODE": "NESTLE", "RCPT LEV1": COD, "RCPT LEV2": "L5", "RCPT LEV3": "010128", "RCPT LEV4": "NUEVA",
         "RCPT RECD QTY": 100, "LOC CODE": "", "TO CHAR RCPT DATE": "09/11/26", "ITEM DES1": "X"},
        {"CUST CODE": "NESTLE", "RCPT LEV1": COD, "RCPT LEV2": "L5", "RCPT LEV3": "010128", "RCPT LEV4": "EXISTE",
         "RCPT RECD QTY": 100, "LOC CODE": "", "TO CHAR RCPT DATE": "09/11/26", "ITEM DES1": "X"}])
    pals = cargar_stock(inv, cfg, ent)
    assert [p.id for p in pals] == ["EXISTE", "NUEVA"]
    assert pals[1].loc == "RECEPCION" and pals[1].origen == "Entrada por confirmar" and not pals[1].pick


# ---------------------------------------------------------------- IFFI
def test_iffi_61_campos_crlf_fechas_y_paletas_repetidas_se_suman():
    cfg = construir_cfg({})
    asig = [{"pedido": 8031700995, "destino": "CHINCHA", "fecha_despacho": dt.date(2026, 10, 27), "codigo": COD,
             "id_paleta": "H2N1", "cajas": 40},
            {"pedido": 8031700995, "destino": "CHINCHA", "fecha_despacho": dt.date(2026, 10, 27), "codigo": COD,
             "id_paleta": "H2N1", "cajas": 60},
            {"pedido": 8031700995, "destino": "CHINCHA", "fecha_despacho": dt.date(2026, 10, 27), "codigo": COD,
             "id_paleta": "H2N2", "cajas": 100}]
    [arch] = generar_iffi(asig, cfg, dt.date(2026, 10, 26))
    assert arch["archivo"] == "IFFI_26.10.26 - CHINCHA - 8031700995.csv"
    texto = arch["contenido"].decode("cp1252")
    assert texto.endswith("\r\n") and texto.count("\r\n") == 2 and "\n" not in texto.replace("\r\n", "")
    l1 = texto.split("\r\n")[0].split(";")
    assert len(l1) == N_CAMPOS == 61
    assert (l1[0], l1[1], l1[9], l1[18], l1[19], l1[20], l1[21], l1[22], l1[23], l1[26], l1[28], l1[31], l1[32],
            l1[33], l1[37], l1[60]) == ("*", "NESTLE", "NESTLE", "10/26/26", "10/27/26", "10/27/26", "CHINCHA",
                                         "8031700995", "NA", "CLL1", COD, "H2N1", "100", "NA", "PLT", "*")
    assert validar_iffi(arch["contenido"]) == []


def test_iffi_un_archivo_por_pedido():
    cfg = construir_cfg({})
    base = {"destino": "X", "fecha_despacho": None, "codigo": COD, "id_paleta": "A", "cajas": 1}
    out = generar_iffi([dict(base, pedido=1), dict(base, pedido=2)], cfg, dt.date(2026, 1, 2))
    assert [o["pedido"] for o in out] == ["1", "2"]
    assert generar_iffi([dict(base, pedido=1), dict(base, pedido=2)], cfg, dt.date(2026, 1, 2), "2")[0]["pedido"] == "2"


def test_fechas_del_korber():
    assert parse_fecha("03-SEP-27") == dt.date(2027, 9, 3)
    assert parse_fecha("03/09/27") == dt.date(2027, 9, 3)
    assert parse_fecha(dt.datetime(2027, 9, 3)) == dt.date(2027, 9, 3)
