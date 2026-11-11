# Sistema de picking Nestlé (app web en Streamlit)

Reemplaza al Excel con macros `Picking_Nestle_v6.xlsm` y replica su lógica (módulo VBA `ModPicking`, versión 5.2).
Todo se guarda en una base SQLite (`data/picking.db`), así que el trabajo del día y el historial no se pierden al cerrar la app.

## Cómo iniciarla

1. Doble clic en **`iniciar_app.bat`** (instala lo que falte y abre la app en el navegador), o desde una consola:

   ```bash
   streamlit run app.py
   ```

2. Requisitos: Python 3.11 o superior. Las dependencias están en `requirements.txt`
   (`py -m pip install -r requirements.txt`).

## Primera vez: traer los datos del Excel

La base ya viene cargada con los datos del `Picking_Nestle_v6.xlsm` (maestro, configuración, historial, stock, abastecimiento
del cliente y conteo). Para repetir la migración (reemplaza el contenido de esas tablas):

```bash
py scripts/importar_desde_excel.py "..\Picking_Nestle_v6 (2).xlsm"
```

Opciones: `--db ruta\otra.db` y `--sin-historial`.

## Trabajo de cada día

| Paso | Página | Qué hace |
|---|---|---|
| 1 | **Cargar datos** | Sube STOCK (Korber), ENTRADAS por confirmar, ABAST_CLIENTE y CONTEO_ZONA. Valida las columnas **por nombre** antes de guardar. |
| 2 | **Pedidos** | Tabla editable o importación de PL «Control de despacho – picking». *Procesar pedidos*, *Anular pedido* y *Cerrar día*. |
| 3 | **Hoja de picking** | Por pedido, ordenada por recorrido (cajas sueltas primero, luego paletas), con marcas (E) y (CLIE). Excel y PDF. |
| 4 | **Asignaciones** | Una fila por paleta. El *Estado* se edita: Pendiente / En picking / Listo / Despachado. |
| 5 | **Desbloqueos** | Paletas y lotes CLIE que hay que desbloquear en el Korber. |
| 6 | **IFFI** | CSV `;` de 61 campos, CRLF, fechas MM/DD/AA. Un archivo por pedido: `IFFI_dd.mm.aa - DESTINO - PEDIDO.csv`. |
| 7 | **Reabastecimiento** | Paletas a bajar a piso, posiciones de picking y mapa visual de la zona G (140 columnas × 2 profundidades, lado impar y par). |
| 8 | **Conteo de zona** | Llena «Exel Alfrimac», marca diferencias con SAP y descarga en el formato del cliente. |
| 9 | **Maestro y Configuración** | Cajas por paleta, posiciones por código, umbral, HOLD, zonas, IFFI… |
| 10 | **Historial y tablero** | Cajas por día, por destino, top SKU y avance de pedidos. |

## Estructura

```
app.py                  Punto de entrada (menú lateral)
inicio.py               Página de inicio (indicadores)
ui.py                   Estilo y utilidades de interfaz
pages/                  Una página por pantalla; solo llaman a /core
core/
  config.py             Configuración (equivale a CONFIG)
  carga_datos.py        Lectura de STOCK, ENTRADAS, PL, ABAST_CLIENTE, CONTEO_ZONA, MAESTRO
  asignacion.py         Asignación por línea, FEFO, recorrido, hoja de picking, anular, desbloqueos
  reabastecimiento.py   Reabastecimiento, tope de posiciones, posiciones de picking
  conteo.py             Conteo de la zona
  iffi.py               Archivo IFFI
  exportar.py           Excel / PDF
  db.py, servicio.py    SQLite y orquestación
scripts/importar_desde_excel.py
tests/                  pytest
data/picking.db         Base de datos
```

## Reglas principales (iguales al VBA)

- Ubicación = `Bloque_Columna_Nivel_Profundidad` (ej. `G_77_1_2`). Picking = bloque G nivel 1; todo lo demás es reserva
  (`_RANDEN` también).
- Paletas completas (`cantidad ÷ cajas por paleta`): de **reserva primero**, luego picking; solo paletas íntegras; lote exacto;
  FEFO (vencimiento → ingreso → menor disponible → ubicación). Si faltan, queda *Pendiente*.
- Cajas sueltas: picking del lote → otros lotes de picking (si la opción está en S) → reserva ya picada del lote →
  reserva ya picada de otro lote → reserva del lote por FEFO. Si no alcanza: *Parcial*.
- HOLD: solo los marcados «SI»; CLIE solo si la línea dice «Usar CLIE = S» (usa RETENIDO + DISPONIBLE).
- Reabastecimiento: solo baja lo que piden los pedidos (paletas de reserva picadas hoy) o el cliente (por fecha, y a igual
  fecha por orden de la tabla). Nunca más paletas que posiciones libres (N° ubic. × 2). Una paleta con menos del 5 % cuenta
  como posición libre (SALDO BAJO). «Queda» = ON HAND − mayor(ON ORD, asignado hoy).

## Pruebas

```bash
py -m pytest tests -q
```

- `tests/test_reglas.py`: reglas una por una (paleta completa, cajas sueltas con y sin lote, picadas, CLIE, tope de
  posiciones, prioridad por fecha, saldo bajo, ON ORD, entradas, IFFI de 61 campos).
- `tests/test_equivalencia_vba.py`: compara la app contra la **macro real** ejecutada en Excel sobre los mismos datos y pedidos
  (52 líneas, 2 configuraciones). Los archivos de `tests/golden/` son la salida de la macro.
- `tests/test_servicio.py`: anular, cerrar día, estados, importación de PL.

## Diferencias conocidas respecto al Excel

1. **Fila «Total general» del conteo**: en el Excel son valores pegados que la macro no recalcula (queda en 0 en
   «Exel Alfrimac»); la app sí la recalcula.
2. **Mapa de la zona G**: posiciones que ningún código del MAESTRO tiene asignadas se muestran como «Sin asignar» /
   «Ocupada sin asignar» (la hoja POSICIONES_PICKING del Excel solo lista las posiciones de los códigos del MAESTRO).
3. **Anular pedido** conserva sus líneas en la tabla de pedidos, igual que el Excel, para poder reprocesarlas.
4. El Excel exigía que la hoja ENTRADAS tuviera datos en la columna A (COMP CODE) para detectar la última fila; la app no.
