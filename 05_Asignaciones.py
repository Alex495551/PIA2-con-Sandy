import pandas as pd
import streamlit as st

import ui
from core import db, exportar, servicio
from core.carga_datos import texto_pedido

ui.iniciar("Asignaciones", "Una fila por paleta asignada. El Estado se edita a mano: Pendiente → En picking → Listo → Despachado.", "📋")

df = db.leer("asignaciones")
if df.empty:
    st.info("Todavía no hay asignaciones del día.")
    st.stop()

df = df.reset_index(drop=True)
df["pedido"] = df["pedido"].map(texto_pedido)
f1, f2, f3 = st.columns(3)
fp = f1.multiselect("Pedido", sorted(df["pedido"].unique()))
fc = f2.multiselect("Código", sorted(df["codigo"].astype(str).unique()))
fe = f3.multiselect("Estado", servicio.ESTADOS_ASIG)
vista = df.copy()
if fp:
    vista = vista[vista["pedido"].isin(fp)]
if fc:
    vista = vista[vista["codigo"].astype(str).isin(fc)]
if fe:
    vista = vista[vista["estado"].isin(fe)]

ui.fila_tarjetas([("Filas", ui.entero(len(vista)), ui.INK), ("Cajas", ui.entero(vista["cajas"].astype(float).sum()), ui.INK),
                  ("Pedidos", ui.entero(vista["pedido"].nunique()), ui.INK),
                  ("Despachadas", ui.entero((vista["estado"] == "Despachado").sum()), ui.VERDE)])
st.write("")

mostrar = ui.para_mostrar(vista, ("fecha_despacho", "vence"))
mostrar["fecha_proceso"] = mostrar["fecha_proceso"].map(lambda v: str(v)[:16] if v else "")
bloqueadas = [c for c in mostrar.columns if c != "estado"]
editado = st.data_editor(
    mostrar, hide_index=False, width="stretch", height=480, key="ed_asig", disabled=bloqueadas,
    column_config={"estado": st.column_config.SelectboxColumn("Estado", options=servicio.ESTADOS_ASIG, required=True),
                   "cajas": st.column_config.NumberColumn("Cajas", format="%d")})
c1, c2, _ = st.columns([1, 1, 3])
if c1.button("💾 Guardar estados", type="primary", width="stretch"):
    cambios = {int(i): v for i, v in editado["estado"].items()}
    n = servicio.actualizar_estados_asignaciones(cambios)
    st.success(f"{n} estados actualizados.")
    st.rerun()
with c2:
    ui.boton_descarga("⬇️ Excel", exportar.excel_de_tablas({"ASIGNACIONES": mostrar}), "Asignaciones.xlsx", ui.MIME_XLSX,
                      width="stretch")
