"""Página de Inicio — indicadores del día y pasos de trabajo (la carga app.py con st.navigation)."""
import streamlit as st

import ui
from core import db, servicio

ui.iniciar("Sistema de picking Nestlé", "Asignación de paletas, hoja de picking, reabastecimiento, entradas por "
           "confirmar e IFFI para el Korber", "📦")

st.subheader("Indicadores del día")
ind = servicio.indicadores()
ui.fila_tarjetas([
    ("Líneas procesadas", ui.entero(ind["lineas"]), ui.INK),
    ("Completas", ui.entero(ind["Completo"]), ui.VERDE),
    ("Parciales", ui.entero(ind["Parcial"]), ui.AMBAR),
    ("Pendientes", ui.entero(ind["Pendiente"]), ui.ROJO),
])
st.write("")
ui.fila_tarjetas([
    ("Cajas asignadas", ui.entero(ind["cajas"]), ui.INK),
    ("Paletas CLIE a desbloquear", ui.entero(ind["clie"]), ui.AMBAR if ind["clie"] else ui.INK),
    ("Paletas a bajar a piso", ui.entero(ind["bajar"]), ui.AZUL),
    ("Líneas sin procesar", ui.entero(ind["sin_procesar"]), ui.AMBAR if ind["sin_procesar"] else ui.INK),
])

st.write("")
c1, c2 = st.columns([3, 2])
with c1:
    st.subheader("Cómo se usa cada día")
    pasos = [
        "<b>1. Cargar datos</b> — sube el inventario del Korber (STOCK), las entradas por confirmar (ENTRADAS), "
        "el abastecimiento del cliente y el conteo de la zona.",
        "<b>2. Pedidos</b> — escríbelos en la tabla o importa los archivos PL; pulsa <i>Procesar pedidos</i>: el stock se "
        "descuenta solo y se generan las asignaciones.",
        "<b>3. Hoja de picking</b> — elige el pedido y descarga la hoja ordenada por recorrido (Excel o PDF).",
        "<b>4. IFFI</b> — genera el CSV para subir al Korber (un archivo por pedido).",
        "<b>5. Desbloqueos</b> — lotes y paletas CLIE que debes desbloquear en el Korber.",
        "<b>6. Reabastecimiento</b> — paletas a bajar a piso y su posición; el conteo de zona se llena solo.",
        "<b>7. Cerrar día</b> (en <i>Pedidos</i>) — todo pasa al historial; luego carga el inventario nuevo.",
    ]
    for p in pasos:
        st.markdown(f'<div class="pk-paso">{p}</div>', unsafe_allow_html=True)
with c2:
    st.subheader("Datos cargados")
    for tipo, tabla, etiqueta in (("stock", "stock", "STOCK (Korber)"), ("entradas", "entradas", "ENTRADAS"),
                                  ("abast", "abast_cliente", "ABAST_CLIENTE"), ("conteo", "conteo_zona", "CONTEO_ZONA"),
                                  ("maestro", "maestro", "MAESTRO")):
        n = len(db.leer(tabla))
        u = db.ultima_carga(tipo)
        extra = f" · {u['nombre']} ({u['fecha_carga'][:16]})" if u else ""
        st.markdown(f"{'✅' if n else '⬜'} **{etiqueta}**: {ui.entero(n)} filas{extra}")
    st.markdown(f"🗂️ **Historial**: {ui.entero(len(db.leer('historial')))} asignaciones guardadas")



