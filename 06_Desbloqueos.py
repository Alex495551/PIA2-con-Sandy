import pandas as pd
import streamlit as st

import ui
from core import exportar, servicio

ui.iniciar("Desbloqueos", "Paletas y lotes con HOLD CLIE asignados («Usar CLIE = S») que hay que desbloquear en el Korber antes de despachar.", "🔓")

det, res = servicio.lista_desbloqueos()
if not det:
    st.success("No hay paletas CLIE asignadas: no hay nada que desbloquear.")
    st.stop()

ui.fila_tarjetas([("Paletas a desbloquear", ui.entero(len(det)), ui.AMBAR),
                  ("Lotes a desbloquear", ui.entero(len(res)), ui.INK),
                  ("Cajas asignadas", ui.entero(sum(r["Cajas asignadas"] for r in res)), ui.INK)])
st.write("")
st.subheader("Resumen por lote")
d_res = pd.DataFrame(res)
st.dataframe(d_res, width="stretch", hide_index=True)
st.subheader("Detalle por paleta")
d_det = pd.DataFrame(det)
st.dataframe(d_det, width="stretch", hide_index=True)
ui.boton_descarga("⬇️ Descargar Excel", exportar.excel_de_tablas({"DESBLOQUEOS": d_det, "RESUMEN POR LOTE": d_res}),
                  "Desbloqueos.xlsx", ui.MIME_XLSX)
