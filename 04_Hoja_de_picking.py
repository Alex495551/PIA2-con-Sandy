import pandas as pd
import streamlit as st

import ui
from core import exportar, servicio
from core.asignacion import hoja_picking
from core.carga_datos import fmt_fecha, texto_pedido

ui.iniciar("Hoja de picking", "Por pedido, ordenada por recorrido: primero cajas sueltas, luego paletas completas.", "🗒️")

asig = servicio.leer_asignaciones()
pedidos = list(dict.fromkeys(texto_pedido(a["pedido"]) for a in asig))
if not pedidos:
    st.info("Todavía no hay asignaciones. Procesa pedidos en la página «Pedidos».")
    st.stop()

elegido = st.selectbox("N° de pedido", pedidos)
h = hoja_picking(asig, elegido)

ui.fila_tarjetas([("Pedido", h["pedido"], ui.INK), ("Destino", h["destino"], ui.INK), ("Fecha", fmt_fecha(h["fecha"]), ui.INK),
                  ("Total de cajas", ui.entero(h["total"]), ui.AZUL)])

df = pd.DataFrame(h["filas"])
df["Vence"] = df["Vence"].map(fmt_fecha)
df["Cajas"] = df["Cajas"].map(ui.entero)


def pintar(fila):
    z = str(fila["Zona"])
    if "(CLIE)" in z:
        return ["background-color: #fff4d6"] * len(fila)
    if "(E)" in z:
        return ["background-color: #e1efff"] * len(fila)
    return [""] * len(fila)


st.dataframe(df.style.apply(pintar, axis=1), width="stretch", hide_index=True, height=min(600, 40 + 35 * len(df)))
st.caption("Placa: ____________   Chofer: ________________   Hora inicio: ______   Hora fin: ______   Firma: ______________")
for n in h["notas"]:
    st.info(n)

d1, d2, _ = st.columns([1, 1, 3])
with d1:
    ui.boton_descarga("⬇️ Descargar Excel", exportar.hoja_picking_excel(h), f"Hoja_picking_{h['pedido']}.xlsx", ui.MIME_XLSX,
                      width="stretch")
with d2:
    ui.boton_descarga("🖨️ Descargar PDF", exportar.hoja_picking_pdf(h), f"Hoja_picking_{h['pedido']}.pdf",
                      "application/pdf", width="stretch")

