"""Sistema de picking Nestlé — punto de entrada.

Ejecutar:  streamlit run app.py
Las páginas viven en /pages (una por pantalla) y solo llaman a /core.
"""
import streamlit as st

st.set_page_config(page_title="Picking Nestlé", page_icon="📦", layout="wide")

PAGINAS = [
    st.Page("inicio.py", title="Inicio", icon="🏠", default=True),
    st.Page("pages/02_Cargar_datos.py", title="Cargar datos", icon="📥", url_path="cargar-datos"),
    st.Page("pages/03_Pedidos.py", title="Pedidos", icon="🧾", url_path="pedidos"),
    st.Page("pages/04_Hoja_de_picking.py", title="Hoja de picking", icon="🗒️", url_path="hoja-de-picking"),
    st.Page("pages/05_Asignaciones.py", title="Asignaciones", icon="📋", url_path="asignaciones"),
    st.Page("pages/06_Desbloqueos.py", title="Desbloqueos", icon="🔓", url_path="desbloqueos"),
    st.Page("pages/07_IFFI.py", title="IFFI", icon="📤", url_path="iffi"),
    st.Page("pages/08_Reabastecimiento.py", title="Reabastecimiento", icon="🔁", url_path="reabastecimiento"),
    st.Page("pages/09_Conteo_de_zona.py", title="Conteo de zona", icon="🧮", url_path="conteo-de-zona"),
    st.Page("pages/10_Maestro_y_Configuracion.py", title="Maestro y Configuración", icon="⚙️", url_path="maestro-y-configuracion"),
    st.Page("pages/11_Historial_y_tablero.py", title="Historial y tablero", icon="📊", url_path="historial"),
]
st.navigation(PAGINAS).run()
