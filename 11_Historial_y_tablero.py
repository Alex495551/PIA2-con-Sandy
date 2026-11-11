import pandas as pd
import plotly.express as px
import streamlit as st

import ui
from core import db
from core.carga_datos import parse_fecha

ui.iniciar("Historial y tablero", "Lo despachado en días anteriores (cada «Cerrar día» suma al historial) y el avance del día.", "📊")

h = db.leer("historial")
act = db.leer("asignaciones")
if h.empty and act.empty:
    st.info("Aún no hay historial ni asignaciones.")
    st.stop()

base = pd.concat([h.assign(origen_dato="Historial"), act.assign(fecha_cierre=None, origen_dato="Hoy (sin cerrar)")],
                 ignore_index=True)
base["cajas"] = base["cajas"].astype(float)
base["dia"] = base.apply(lambda r: parse_fecha(r["fecha_cierre"]) or parse_fecha(r["fecha_despacho"]), axis=1)
base["dia"] = pd.to_datetime(base["dia"])
base["pedido"] = base["pedido"].astype(str)
base["codigo"] = base["codigo"].astype(str)

d0, d1 = base["dia"].min().date(), base["dia"].max().date()
c1, c2, c3 = st.columns([2, 2, 3])
rango = c1.date_input("Rango de fechas", (d0, d1), min_value=d0, max_value=d1, format="DD/MM/YYYY")
incluir_hoy = c2.checkbox("Incluir lo de hoy (sin cerrar)", True)
if isinstance(rango, tuple) and len(rango) == 2:
    base = base[(base["dia"] >= pd.Timestamp(rango[0])) & (base["dia"] <= pd.Timestamp(rango[1]))]
if not incluir_hoy:
    base = base[base["origen_dato"] == "Historial"]
if base.empty:
    st.info("No hay datos en ese rango.")
    st.stop()

ui.fila_tarjetas([("Cajas", ui.entero(base["cajas"].sum()), ui.INK), ("Pedidos", ui.entero(base["pedido"].nunique()), ui.INK),
                  ("Destinos", ui.entero(base["destino"].nunique()), ui.INK), ("SKU", ui.entero(base["codigo"].nunique()), ui.INK),
                  ("Días", ui.entero(base["dia"].nunique()), ui.INK)])
st.write("")
LAYOUT = dict(margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="white", font=dict(family="Inter, Segoe UI"))

a, b = st.columns(2)
por_dia = base.groupby("dia", as_index=False)["cajas"].sum()
fig = px.bar(por_dia, x="dia", y="cajas", title="Cajas por día", color_discrete_sequence=[ui.AZUL])
fig.update_layout(**LAYOUT, xaxis_title=None, yaxis_title="cajas")
a.plotly_chart(fig, width="stretch")

por_dest = base.groupby("destino", as_index=False)["cajas"].sum().sort_values("cajas", ascending=False).head(15)
fig = px.bar(por_dest.sort_values("cajas"), x="cajas", y="destino", orientation="h", title="Cajas por destino (top 15)",
             color_discrete_sequence=[ui.VERDE])
fig.update_layout(**LAYOUT, xaxis_title="cajas", yaxis_title=None)
b.plotly_chart(fig, width="stretch")

a, b = st.columns(2)
top = base.groupby(["codigo", "descripcion"], as_index=False)["cajas"].sum().sort_values("cajas", ascending=False).head(15)
top["SKU"] = top["codigo"] + " · " + top["descripcion"].astype(str).str.slice(0, 28)
fig = px.bar(top.sort_values("cajas"), x="cajas", y="SKU", orientation="h", title="Top 15 SKU por cajas",
             color_discrete_sequence=[ui.INK])
fig.update_layout(**LAYOUT, xaxis_title="cajas", yaxis_title=None)
a.plotly_chart(fig, width="stretch")

# avance de pedidos de hoy
lineas = db.leer("pedidos")
with b:
    st.markdown("**Avance de los pedidos de hoy**")
    if lineas.empty:
        st.caption("No hay pedidos cargados hoy.")
    else:
        est = lineas["estado"].fillna("Sin procesar").replace("", "Sin procesar").value_counts().reset_index()
        est.columns = ["Estado de la línea", "Líneas"]
        fig = px.pie(est, names="Estado de la línea", values="Líneas", hole=0.55,
                     color="Estado de la línea",
                     color_discrete_map={"Completo": ui.VERDE, "Parcial": ui.AMBAR, "Pendiente": ui.ROJO,
                                         "Sin procesar": ui.GRIS})
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=260)
        st.plotly_chart(fig, width="stretch")
    if not act.empty:
        av = act["estado"].value_counts().reindex(["Pendiente", "En picking", "Listo", "Despachado"]).fillna(0).astype(int)
        st.caption("Paletas por estado de picking: " + " · ".join(f"{k}: {v}" for k, v in av.items()))

with st.expander("Detalle por pedido"):
    det = base.groupby(["pedido", "destino"], as_index=False).agg(cajas=("cajas", "sum"), paletas=("id_paleta", "nunique"),
                                                                    fecha=("dia", "max"))
    det["fecha"] = det["fecha"].dt.strftime("%d/%m/%Y")
    st.dataframe(det.sort_values("fecha", ascending=False), width="stretch", hide_index=True)
