import pandas as pd
import streamlit as st

import ui
from core import db
from core.carga_datos import norm, num
from core.config import CONFIG_DEFECTO

ui.iniciar("Maestro y Configuración", "Cajas por paleta, posiciones de picking por código y reglas generales del sistema.", "⚙️")

t_m, t_c = st.tabs(["Maestro de productos", "Configuración"])

# ------------------------------------------------------------------ MAESTRO
with t_m:
    m = db.leer("maestro")
    st.caption(f"{len(m)} productos. «Columnas G asignadas» es texto libre con los números de columna, por ejemplo `77 y 79`; "
               "las posiciones de picking del código = N° ubic. × profundidades.")
    m["cajas_paleta"] = m["cajas_paleta"].map(lambda v: num(v) if v not in (None, "") else None)
    m["n_ubic"] = m["n_ubic"].map(lambda v: num(v) if v not in (None, "") else None)
    ed = st.data_editor(
        m, num_rows="dynamic", width="stretch", height=520, hide_index=True, key="ed_maestro",
        column_config={"codigo": st.column_config.TextColumn("Código", required=True),
                       "descripcion": st.column_config.TextColumn("Descripción", width="large"),
                       "cajas_paleta": st.column_config.NumberColumn("Cajas por paleta", min_value=0, format="%d"),
                       "uma": st.column_config.SelectboxColumn("UMA", options=["CJ", "UND"]),
                       "fuente": st.column_config.TextColumn("Fuente del dato"),
                       "bloque": st.column_config.TextColumn("Bloque picking"),
                       "n_ubic": st.column_config.NumberColumn("N° ubic. picking", min_value=0, format="%d"),
                       "columnas": st.column_config.TextColumn("Columnas G asignadas")})
    if st.button("💾 Guardar maestro", type="primary"):
        ed = ed[ed["codigo"].map(lambda c: norm(c) != "")].copy()
        ed["codigo"] = ed["codigo"].map(norm)
        ed["uma"] = ed["uma"].map(lambda v: norm(v) or "CJ")
        dup = ed["codigo"][ed["codigo"].duplicated()].unique()
        if len(dup):
            st.error("Códigos repetidos: " + ", ".join(dup))
        else:
            db.guardar("maestro", ed)
            st.success("Maestro guardado.")
            st.rerun()

# ------------------------------------------------------------------ CONFIG
with t_c:
    cfg = db.get_config()
    with st.form("form_cfg"):
        a, b, c = st.columns(3)
        cliente = a.text_input("Cliente (CUST CODE)", cfg["cliente"])
        umbral = b.number_input("Umbral de saldo bajo (% de una paleta en picking)", 0.0, 100.0, float(cfg["umbral"]) * 100,
                                step=1.0, help="Una paleta en piso con menos de este % cuenta como posición libre.")
        excluir = c.text_input("Excluir ubicaciones que empiezan con (separar con ;)", cfg["excluir"])
        a, b, c = st.columns(3)
        sumar = a.checkbox("Sumar ON ORD QTY al disponible", cfg["sumar_on_ord"])
        usar_ent = b.checkbox("Usar entradas pendientes por confirmar", cfg["usar_entradas"])
        ent_sin = c.checkbox("Incluir entradas que aún no tienen ubicación", cfg["entradas_sin_ubic"])
        a, b, c, d_ = st.columns(4)
        nivel = a.number_input("Nivel de las posiciones de picking", 1, 20, int(cfg["nivel_picking"]))
        prof = b.number_input("Profundidades por columna", 1, 6, int(cfg["profundidades"]))
        sust = c.checkbox("Cajas sueltas: usar otros lotes de picking antes que reserva", cfg["sust_lote"])
        reab_ord = d_.checkbox("Reabastecer descontando ON ORD del Korber", cfg["reab_ord"])
        st.markdown("**IFFI**")
        i1, i2, i3, i4, i5, i6 = st.columns(6)
        consignee = i1.text_input("Consignee (B)", cfg["iffi_consignee"])
        soldto = i2.text_input("Soldto (J)", cfg["iffi_soldto"])
        almacen = i3.text_input("Warehouse (AA)", cfg["iffi_almacen"])
        carrier = i4.text_input("Carrier (X)", cfg["iffi_carrier"])
        freight = i5.text_input("Freight (AH)", cfg["iffi_freight"])
        load = i6.text_input("Load type (AL)", cfg["iffi_load"])
        g_cols = st.number_input("Columnas de la zona G (solo para el mapa visual)", 10, 400, int(cfg["g_columnas"]))
        z1, z2 = st.columns(2)
        with z1:
            st.markdown("**Zonas de picking** (el orden es el orden del recorrido; nivel `*` = todos)")
            zonas = st.data_editor(pd.DataFrame(cfg["zonas_picking"]), num_rows="dynamic", hide_index=True, key="ed_zonas",
                                   width="stretch")
        with z2:
            st.markdown("**HOLD** (uso: SI / NO / SOLO CON AUTORIZACION)")
            hold = st.data_editor(pd.DataFrame(cfg["hold"]), num_rows="dynamic", hide_index=True, key="ed_hold",
                                  width="stretch",
                                  column_config={"uso": st.column_config.SelectboxColumn(
                                      "Uso", options=["SI", "NO", "SOLO CON AUTORIZACION"])})
        enviado = st.form_submit_button("💾 Guardar configuración", type="primary")
    if enviado:
        zonas = zonas.dropna(subset=["bloque"]).fillna("")
        hold = hold.dropna(subset=["codigo"]).fillna("")
        db.set_config({
            "cliente": cliente.strip().upper(), "umbral": umbral / 100.0, "excluir": excluir.strip(),
            "sumar_on_ord": sumar, "usar_entradas": usar_ent, "entradas_sin_ubic": ent_sin,
            "nivel_picking": int(nivel), "profundidades": int(prof), "sust_lote": sust, "reab_ord": reab_ord,
            "iffi_consignee": consignee, "iffi_soldto": soldto, "iffi_almacen": almacen, "iffi_carrier": carrier,
            "iffi_freight": freight, "iffi_load": load, "g_columnas": int(g_cols),
            "zonas_picking": zonas.to_dict("records"), "hold": hold.to_dict("records")})
        st.success("Configuración guardada.")
        st.rerun()
