import datetime as dt

import pandas as pd
import streamlit as st

import ui
from core import db, servicio
from core.carga_datos import importar_pl, norm, num, parse_fecha, texto_pedido

ui.iniciar("Pedidos", "Escribe los pedidos o importa los PL «Control de despacho – picking»; luego procesa.", "🧾")

COLS = db.COLUMNAS["pedidos"]
ped = db.leer("pedidos")
maestro = {m.cod: m for m in servicio.maestro_lista()}


def a_tabla(df: pd.DataFrame) -> pd.DataFrame:
    t = df.copy()
    t["fecha"] = t["fecha"].map(lambda v: parse_fecha(v) if v not in (None, "") else None)
    t["cantidad"] = t["cantidad"].map(lambda v: num(v) if v not in (None, "") else None)
    t["usar_clie"] = t["usar_clie"].map(lambda v: "S" if str(v or "").strip().upper().startswith("S") else "N")
    t.insert(4, "descripcion", t["codigo"].map(lambda c: maestro[norm(c)].desc if norm(c) in maestro else ("Revisar código" if norm(c) else "")))
    t.insert(8, "uma", t["codigo"].map(lambda c: maestro[norm(c)].uma if norm(c) in maestro else ("CJ" if norm(c) else "")))
    return t


cargados = a_tabla(ped)
pendientes = int(((cargados["codigo"].map(norm) != "") & (cargados["estado"].map(lambda v: not v))).sum()) if len(cargados) else 0

# ------------------------------------------------------------------ importar PL
with st.expander("Importar archivos PL (Control de despacho – picking)"):
    pls = st.file_uploader("Selecciona uno o varios PL", type=["xlsx", "xlsm", "xls"], accept_multiple_files=True,
                           key="up_pl")
    if pls and st.button("Importar a la tabla de pedidos"):
        nuevas = []
        for f in pls:
            try:
                nuevas += importar_pl(f, f.name)
            except Exception as e:  # noqa: BLE001
                st.error(f"{f.name}: {e}")
        if nuevas:
            add = pd.DataFrame(nuevas)
            for c in COLS:
                if c not in add.columns:
                    add[c] = None
            db.guardar("pedidos", pd.concat([ped, add[COLS]], ignore_index=True))
            st.success(f"{len(nuevas)} líneas importadas. Revísalas y pulsa «Procesar pedidos».")
            st.rerun()

# ------------------------------------------------------------------ tabla editable
st.markdown(f"**{len(cargados)}** líneas · **{pendientes}** sin procesar. "
            "Las líneas ya procesadas (con Estado) no se vuelven a procesar; para repetirlas, anula el pedido.")
editado = st.data_editor(
    cargados, num_rows="dynamic", width="stretch", height=380, key="ed_pedidos", hide_index=True,
    column_config={
        "pedido": st.column_config.TextColumn("N° Pedido"),
        "destino": st.column_config.TextColumn("Destino / Cliente"),
        "fecha": st.column_config.DateColumn("Fecha despacho", format="DD/MM/YYYY"),
        "codigo": st.column_config.TextColumn("Código"),
        "descripcion": st.column_config.TextColumn("Descripción (auto)", disabled=True),
        "lote": st.column_config.TextColumn("Lote (opcional)"),
        "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0, step=1, format="%d"),
        "uma": st.column_config.TextColumn("UMA (auto)", disabled=True),
        "usar_clie": st.column_config.SelectboxColumn("Usar CLIE", options=["N", "S"]),
        "estado": st.column_config.TextColumn("Estado", disabled=True),
        "asignado": st.column_config.NumberColumn("Asignado", disabled=True, format="%d"),
        "pendiente": st.column_config.NumberColumn("Pendiente", disabled=True, format="%d"),
        "observacion": st.column_config.TextColumn("Observación", disabled=True, width="large"),
        "id_linea": st.column_config.TextColumn("ID línea", disabled=True),
    })


def tabla_a_bd(t: pd.DataFrame) -> pd.DataFrame:
    t = t.copy().drop(columns=["descripcion", "uma"], errors="ignore")
    t = t[t["codigo"].map(lambda c: norm(c) != "") | t["pedido"].map(lambda c: str(c or "").strip() != "")]
    t["codigo"] = t["codigo"].map(norm)
    t["pedido"] = t["pedido"].map(texto_pedido)
    t["lote"] = t["lote"].map(lambda v: norm(v) if v not in (None, "") else "")
    t["usar_clie"] = t["usar_clie"].map(lambda v: "S" if str(v or "").strip().upper().startswith("S") else "N")
    return t[COLS]


c1, c2, c3 = st.columns([1, 1, 3])
if c1.button("💾 Guardar cambios", width="stretch"):
    db.guardar("pedidos", tabla_a_bd(editado))
    st.success("Pedidos guardados.")
    st.rerun()
if c2.button("▶️ Procesar pedidos", type="primary", width="stretch"):
    db.guardar("pedidos", tabla_a_bd(editado))
    res = servicio.procesar()
    if "error" in res:
        st.error(res["error"])
    else:
        st.success(f"Pedidos procesados: {res['lineas']} líneas — completas {res['Completo']}, "
                   f"parciales {res['Parcial']}, pendientes {res['Pendiente']}.")
        st.rerun()

# ------------------------------------------------------------------ anular / cerrar día
st.divider()
a, b = st.columns(2)
with a:
    st.subheader("Anular pedido")
    st.caption("Borra sus asignaciones y el stock vuelve; sus líneas quedan listas para reprocesar.")
    con_asig = sorted({texto_pedido(x["pedido"]) for x in servicio.leer_asignaciones()})
    elegido = st.selectbox("Pedido", ["—"] + con_asig, key="anular_sel")
    conf = st.checkbox("Confirmo que quiero anular este pedido", key="anular_conf")
    if st.button("Anular pedido", disabled=(elegido == "—" or not conf)):
        r = servicio.anular(elegido)
        st.success(f"Pedido {elegido} anulado: {r['borradas']} asignaciones borradas, {r['lineas']} líneas listas para reprocesar.")
        st.rerun()
with b:
    st.subheader("Cerrar día")
    st.caption("Pasa las asignaciones y pedidos de hoy al historial (con la fecha de cierre) y limpia el día. "
               "Después carga el inventario nuevo del Korber.")
    fecha_cierre = st.date_input("Fecha de cierre", dt.date.today(), format="DD/MM/YYYY")
    conf2 = st.checkbox("Confirmo el cierre del día", key="cierre_conf")
    if st.button("Cerrar día", disabled=not conf2):
        r = servicio.cerrar_dia(fecha_cierre)
        st.success(f"Día cerrado: {r['asignaciones']} asignaciones y {r['pedidos']} pedidos pasaron al historial.")
        st.rerun()
