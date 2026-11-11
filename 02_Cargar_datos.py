import streamlit as st

import ui
from core import db
from core.carga_datos import (COLS_ENTRADAS, COLS_ENTRADAS_OBLIG, COLS_STOCK, COLS_STOCK_OBLIG, _mapa_columnas,
                              leer_tabla, norm, parse_abast, parse_conteo, validar_columnas)
from core.config import construir_cfg

ui.iniciar("Cargar datos", "Sube los archivos tal como llegan; se valida el formato antes de guardar.", "📥")

TIPOS = ["xlsx", "xlsm", "xls", "csv"]
t_stock, t_ent, t_abast, t_conteo = st.tabs(["STOCK (Korber)", "ENTRADAS por confirmar", "ABAST_CLIENTE", "CONTEO_ZONA"])


def estado_actual(tabla: str, tipo: str):
    n = len(db.leer(tabla))
    u = db.ultima_carga(tipo)
    st.caption(f"Actualmente guardado: **{ui.entero(n)}** filas" + (f" — {u['nombre']} ({u['fecha_carga'][:16]})" if u else ""))


def selector_hoja(archivo):
    """Si el libro tiene varias hojas, deja elegir (por defecto la primera)."""
    nombre = archivo.name.lower()
    if nombre.endswith((".xlsx", ".xlsm", ".xls")):
        import pandas as pd
        archivo.seek(0)
        hojas = pd.ExcelFile(archivo).sheet_names
        if len(hojas) > 1:
            return st.selectbox("Hoja a leer", hojas, key=f"hoja_{nombre}")
    return 0


# ------------------------------------------------------------------ STOCK
with t_stock:
    st.markdown("Exportación del Korber One (22 columnas). Las columnas se buscan **por nombre**: "
                "`CUST CODE, LOC CODE, TO CHAR INVT ORG RECD DATE, INVT LEV1 (código), INVT LEV2 (lote), "
                "INVT LEV3, INVT LEV4 (ID paleta), ON HAND QTY, DISPONIBLE, ON ORD QTY, RETENIDO, HOLD CODE, "
                "FECHA EXP, ITEM DES1`.")
    estado_actual("stock", "stock")
    f = st.file_uploader("Archivo de STOCK", type=TIPOS, key="up_stock")
    if f:
        df = leer_tabla(f, selector_hoja(f))
        faltan = validar_columnas(df, COLS_STOCK_OBLIG)
        opc = [c for c in COLS_STOCK if c not in _mapa_columnas(df.columns)]
        if faltan:
            st.error("Faltan columnas obligatorias: " + ", ".join(faltan))
        else:
            cfg = construir_cfg(db.get_config())
            m = _mapa_columnas(df.columns)
            cli = df.iloc[:, m["CUST CODE"]].map(norm) if "CUST CODE" in m else None
            n_cli = int((cli == cfg.cliente).sum()) if cli is not None else len(df)
            st.success(f"Formato correcto: {ui.entero(len(df))} filas, {ui.entero(n_cli)} del cliente {cfg.cliente}.")
            if opc:
                st.info("Columnas opcionales que no vienen en el archivo: " + ", ".join(opc))
            st.dataframe(df.head(50), width="stretch", height=260)
            if st.button("Guardar STOCK", type="primary", key="g_stock"):
                db.guardar("stock", df)
                db.registrar_carga("stock", f.name, len(df))
                st.success("STOCK guardado. Las asignaciones del día se descuentan de este inventario.")
                st.rerun()

# ------------------------------------------------------------------ ENTRADAS
with t_ent:
    st.markdown("Reporte **OP_ENTRADAS – PENDIENTE X CONF**: paletas que ya llegaron pero aún no figuran en el "
                "inventario. Se suman como paletas libres (si el ID ya está en STOCK se ignora; sin ubicación → "
                "`RECEPCION`).")
    estado_actual("entradas", "entradas")
    f = st.file_uploader("Archivo de ENTRADAS", type=TIPOS, key="up_ent")
    if f:
        df = leer_tabla(f, selector_hoja(f))
        faltan = validar_columnas(df, COLS_ENTRADAS_OBLIG)
        if faltan:
            st.error("Faltan columnas obligatorias: " + ", ".join(faltan))
        else:
            st.success(f"Formato correcto: {ui.entero(len(df))} filas.")
            opc = [c for c in COLS_ENTRADAS if c not in _mapa_columnas(df.columns)]
            if opc:
                st.info("Columnas opcionales que no vienen: " + ", ".join(opc))
            st.dataframe(df.head(50), width="stretch", height=260)
            if st.button("Guardar ENTRADAS", type="primary", key="g_ent"):
                db.guardar("entradas", df)
                db.registrar_carga("entradas", f.name, len(df))
                st.rerun()
    if len(db.leer("entradas")) and st.button("Vaciar ENTRADAS", key="v_ent"):
        db.vaciar("entradas")
        st.rerun()

# ------------------------------------------------------------------ ABAST_CLIENTE
with t_abast:
    st.markdown("Archivo del cliente con `CODIGO, TEXTO BREVE, LOTE, CANTIDAD, UBICACIÓN, FECHA`: "
                "**cada fila = 1 paleta** que el cliente quiere tener en piso.")
    estado_actual("abast_cliente", "abast")
    f = st.file_uploader("Archivo de ABAST_CLIENTE", type=TIPOS, key="up_abast")
    if f:
        raw = leer_tabla(f, selector_hoja(f), header=None)
        try:
            ab = parse_abast(raw)
        except ValueError as e:
            st.error(str(e))
        else:
            st.success(f"{len(ab)} solicitudes leídas.")
            st.dataframe(ui.para_mostrar(ab, ("fecha",)), width="stretch", height=260)
            if st.button("Guardar ABAST_CLIENTE", type="primary", key="g_ab"):
                for c in ("estado", "paleta", "destino"):
                    ab[c] = None
                db.guardar("abast_cliente", ab)
                db.registrar_carga("abast", f.name, len(ab))
                st.rerun()
    ab = db.leer("abast_cliente")
    if len(ab):
        with st.expander("Ver solicitudes guardadas (con el resultado del reabastecimiento)"):
            st.dataframe(ui.para_mostrar(ab, ("fecha",)), width="stretch", height=300)

# ------------------------------------------------------------------ CONTEO_ZONA
with t_conteo:
    st.markdown("Formato del cliente **«ZONA DE TRABAJO … CIERRE»**: `Material, Texto breve material, LOTE, UM, SAP, "
                "Exel Alfrimac, Conteo Fisico, Diferencia, Obsev` (el Material solo viene en la primera fila de "
                "cada grupo de lotes).")
    estado_actual("conteo_zona", "conteo")
    f = st.file_uploader("Archivo de CONTEO_ZONA", type=TIPOS, key="up_cnt")
    if f:
        raw = leer_tabla(f, selector_hoja(f), header=None)
        try:
            titulo, cz = parse_conteo(raw)
        except ValueError as e:
            st.error(str(e))
        else:
            st.success(f"«{titulo}»: {len(cz)} filas.")
            st.dataframe(cz, width="stretch", height=260)
            if st.button("Guardar CONTEO_ZONA", type="primary", key="g_cnt"):
                db.guardar("conteo_zona", cz)
                db.set_config({"conteo_titulo": titulo})
                db.registrar_carga("conteo", f.name, len(cz))
                st.rerun()
