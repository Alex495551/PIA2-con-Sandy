import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from core import exportar, servicio
from core.reabastecimiento import COLS_POS, COLS_REAB

ui.iniciar("Reabastecimiento y posiciones de picking",
           "Solo se bajan paletas que piden los pedidos o el cliente; nunca más que las posiciones libres del código.", "🔁")

d = ui.dia()
if d.ctx is None:
    ui.sin_datos(d.error or "No hay STOCK cargado.")
    st.stop()

reab = pd.DataFrame(d.reab.filas, columns=COLS_REAB)
pos = pd.DataFrame(d.reab.posiciones, columns=COLS_POS)
bajar = reab[reab["estado"].astype(str).str.startswith("BAJAR")] if len(reab) else reab
ui.fila_tarjetas([
    ("Paletas a bajar", ui.entero(len(bajar)), ui.AZUL),
    ("Solicitudes sin stock del lote", ui.entero((reab["estado"] == "SIN STOCK DEL LOTE").sum()) if len(reab) else 0, ui.AMBAR),
    ("No se baja (sin cupo)", ui.entero(reab["estado"].astype(str).str.startswith("NO SE BAJA").sum()) if len(reab) else 0, ui.ROJO),
    ("Posiciones libres/saldo bajo", ui.entero(pos["estado"].isin(["VACIA", "SALDO BAJO"]).sum()) if len(pos) else 0, ui.INK),
])
st.write("")
t1, t2, t3 = st.tabs(["Reabastecimiento", "Posiciones de picking", "Mapa zona G"])

NOMBRES_REAB = {"n": "N°", "motivo": "Motivo", "codigo": "Código", "descripcion": "Descripción",
                "lote_solicitado": "Lote solicitado", "id_paleta": "ID paleta a bajar", "ubic_origen": "Ubicación origen",
                "lote": "Lote", "vence": "Vence", "cajas": "Cajas", "pos_destino": "Posición destino",
                "columnas": "Columnas asignadas", "estado": "Estado", "observacion": "Observación",
                "pedidos": "Pedido(s) que la picaron", "fecha_solicitud": "Fecha solicitud"}

with t1:
    if reab.empty:
        st.info("Nadie pidió reabastecimiento: no se baja nada. (Sin pedidos que piquen reserva y sin solicitudes del cliente.)")
    else:
        ests = st.multiselect("Estado", sorted(reab["estado"].dropna().unique()), key="f_reab_est")
        v = reab[reab["estado"].isin(ests)] if ests else reab
        v = ui.para_mostrar(v, ("vence", "fecha_solicitud")).rename(columns=NOMBRES_REAB)
        st.dataframe(v, width="stretch", hide_index=True, height=480)
        ui.boton_descarga("⬇️ Excel", exportar.excel_de_tablas({"REABASTECIMIENTO": v}), "Reabastecimiento.xlsx", ui.MIME_XLSX)

with t2:
    if pos.empty:
        st.info("El MAESTRO no tiene códigos con bloque de picking.")
    else:
        e = st.multiselect("Estado de la posición", sorted(pos["estado"].unique()), key="f_pos_est")
        cod = st.text_input("Código contiene", key="f_pos_cod")
        v = pos[pos["estado"].isin(e)] if e else pos
        if cod.strip():
            v = v[v["codigo"].astype(str).str.contains(cod.strip())]
        v = v.sort_values(["prioridad", "codigo", "posicion"], kind="stable")
        st.dataframe(v, width="stretch", hide_index=True, height=480)
        ui.boton_descarga("⬇️ Excel", exportar.excel_de_tablas({"POSICIONES_PICKING": v}), "Posiciones_picking.xlsx", ui.MIME_XLSX)

with t3:
    mapa = servicio.mapa_zona(d)
    codigos = ["(todos)"] + sorted({c for c in mapa["codigo"] if c})
    resaltar = st.selectbox("Resaltar código", codigos)
    estados = list(ui.COLOR_ESTADO_POS)
    chips = "".join(f'<span class="pk-chip" style="background:{ui.COLOR_ESTADO_POS[e]};'
                    f'{"color:#374151;" if e in ("VACIA", "SIN ASIGNAR") else ""}">{e.capitalize()}</span>' for e in estados)
    st.markdown(chips, unsafe_allow_html=True)
    n_cols = int(mapa["columna"].max())
    for lado, cols in (("Lado impar", range(1, n_cols + 1, 2)), ("Lado par", range(2, n_cols + 1, 2))):
        sub = mapa[mapa["columna"].isin(list(cols))]
        xs = [int(c) for c in cols]
        z, textos, colores = [], [], []
        for pr in sorted(sub["prof"].unique()):
            fila_z, fila_t = [], []
            for c in xs:
                r = sub[(sub["columna"] == c) & (sub["prof"] == pr)].iloc[0]
                fila_z.append(estados.index(r["estado"]))
                gris = resaltar != "(todos)" and r["codigo"] != resaltar
                fila_t.append(f"<b>{r['posicion']}</b><br>{r['estado']}<br>Código: {r['codigo'] or '—'}<br>"
                              f"Lote: {r['lote'] or '—'}<br>Cajas: {ui.entero(r['cajas'])}")
                if gris:
                    fila_z[-1] = -1
            z.append(fila_z)
            textos.append(fila_t)
        # escala discreta: -1 -> gris claro (atenuado); 0..k-1 -> colores de estado
        colorscale = []
        todos = ["#eef0f3"] + [ui.COLOR_ESTADO_POS[e] for e in estados]
        for i, c in enumerate(todos):
            colorscale += [[i / len(todos), c], [(i + 1) / len(todos), c]]
        zz = [[v + 1 for v in fila] for fila in z]
        fig = go.Figure(go.Heatmap(z=zz, x=[f"{c:02d}" for c in xs], y=[f"Prof. {p}" for p in sorted(sub["prof"].unique())],
                                   text=textos, hovertemplate="%{text}<extra></extra>", colorscale=colorscale,
                                   zmin=-0.5, zmax=len(todos) - 0.5, showscale=False, xgap=2, ygap=3))
        fig.update_layout(title=lado, height=210, margin=dict(l=10, r=10, t=40, b=10),
                          xaxis=dict(side="bottom", tickangle=-90, type="category", tickfont=dict(size=9)),
                          yaxis=dict(autorange="reversed"), plot_bgcolor="white")
        st.plotly_chart(fig, width="stretch", key=f"mapa_{lado}")
    st.caption("Zona G, nivel 1. «Sin asignar» = posición que ningún código del MAESTRO tiene asignada; "
               "«Ocupada sin asignar» = tiene stock pero no pertenece a ningún código del MAESTRO.")

