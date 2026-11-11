import pandas as pd
import streamlit as st

import ui
from core import db, servicio
from core.conteo import COLS_CONTEO, ENCABEZADOS, exportar_conteo_excel

ui.iniciar("Conteo de zona", "«Exel Alfrimac» = lo que queda en la zona de picking por código+lote, más las paletas que se bajan. "
           "Las diferencias contra SAP se marcan en Obsev.", "🧮")

d = ui.dia(con_conteo=True)
if d.ctx is None:
    ui.sin_datos(d.error or "No hay STOCK cargado.")
    st.stop()
if d.conteo is None:
    st.info("Falta cargar el conteo del cliente («ZONA DE TRABAJO … CIERRE») en la página «Cargar datos».")
    st.stop()

cz: pd.DataFrame = d.conteo.copy()
titulo = db.get_config().get("conteo_titulo") or "ZONA DE TRABAJO"
st.subheader(titulo)
datos = cz[~cz["material"].astype(str).str.upper().str.startswith("TOTAL")]
con_dif = datos[datos["obs"].astype(str).str.startswith("Sistema:")]
extra = datos[datos["sap"].isna()]
ui.fila_tarjetas([("Filas del cliente", ui.entero(len(datos) - len(extra)), ui.INK),
                  ("Con diferencia vs SAP", ui.entero(len(con_dif) - len(extra)), ui.AMBAR),
                  ("Lotes en zona fuera del conteo", ui.entero(len(extra)), ui.ROJO),
                  ("Cajas Alfrimac", ui.entero(datos["alfrimac"].astype(float).sum()), ui.AZUL)])
st.write("")
solo = st.checkbox("Mostrar solo filas con observación")
vista = cz[cz["obs"].astype(str).str.len() > 0] if solo else cz
nombres = dict(zip(COLS_CONTEO, ENCABEZADOS))
editado = st.data_editor(
    vista.rename(columns=nombres), hide_index=False, width="stretch", height=520, key="ed_conteo",
    disabled=[n for c, n in nombres.items() if c != "conteo"],
    column_config={"Conteo Fisico": st.column_config.NumberColumn("Conteo Fisico", format="%d")})

c1, c2, _ = st.columns([1.3, 1.3, 3])
if c1.button("💾 Guardar conteo físico", type="primary", width="stretch"):
    guardado = db.leer("conteo_zona")
    nuevo = cz.copy()
    for i, v in editado["Conteo Fisico"].items():
        nuevo.at[i, "conteo"] = None if pd.isna(v) else float(v)
    db.guardar("conteo_zona", nuevo)
    servicio.refrescar()
    st.success("Conteo físico guardado.")
    st.rerun()
with c2:
    ui.boton_descarga("⬇️ Descargar en formato del cliente", exportar_conteo_excel(cz, titulo),
                      f"{titulo}.xlsx".replace("/", "-"), ui.MIME_XLSX, width="stretch")
