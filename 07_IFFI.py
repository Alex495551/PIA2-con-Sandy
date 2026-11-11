import datetime as dt
import io
import zipfile

import pandas as pd
import streamlit as st

import ui
from core import servicio
from core.carga_datos import texto_pedido
from core.iffi import CAMPOS_USADOS, N_CAMPOS, validar_iffi

ui.iniciar("IFFI para el Korber", "CSV separado por «;», 61 campos, fin de línea CRLF, fechas MM/DD/AA. "
           "Una línea por paleta; un archivo por pedido.", "📤")

asig = servicio.leer_asignaciones()
pedidos = list(dict.fromkeys(texto_pedido(a["pedido"]) for a in asig))
if not pedidos:
    st.info("Todavía no hay asignaciones. Procesa pedidos primero.")
    st.stop()

c1, c2 = st.columns(2)
sel = c1.selectbox("N° de pedido", ["(todos: un archivo por pedido)"] + pedidos)
fecha = c2.date_input("Fecha del packing list", dt.date.today(), format="DD/MM/YYYY",
                      help="Por defecto hoy. Va en el campo S (Order Date).")
ped = "" if sel.startswith("(") else sel
archivos = servicio.iffi(ped, fecha)
st.caption("Nombre: `IFFI_dd.mm.aa - DESTINO - PEDIDO.csv`")

if len(archivos) > 1:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for a in archivos:
            z.writestr(a["archivo"], a["contenido"])
    ui.boton_descarga(f"⬇️ Descargar los {len(archivos)} archivos (.zip)", buf.getvalue(), "IFFI.zip", "application/zip",
                      type="primary")

for a in archivos:
    with st.container(border=True):
        h1, h2 = st.columns([4, 1])
        h1.markdown(f"**{a['archivo']}**  \n{a['paletas']} paletas · {ui.entero(a['cajas'])} cajas")
        with h2:
            ui.boton_descarga("⬇️ Descargar CSV", a["contenido"], a["archivo"], "text/csv", key=f"dl_{a['archivo']}",
                              width="stretch")
        prob = validar_iffi(a["contenido"])
        if prob:
            st.error("Problemas de formato: " + "; ".join(prob))
        else:
            st.caption(f"✔ Formato verificado: {N_CAMPOS} campos por línea, CRLF, fechas MM/DD/AA.")
        with st.expander("Ver líneas (solo campos con valor)"):
            usados = sorted(CAMPOS_USADOS)
            df = pd.DataFrame([[l[k - 1] for k in usados] for l in a["lineas"]],
                              columns=[f"{k}. {CAMPOS_USADOS[k]}" for k in usados])
            st.dataframe(df, width="stretch", hide_index=True)
