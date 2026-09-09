# Categorías excluyentes de auditoría — 9 de septiembre de 2026

El libro ahora clasifica cada ficha en una única pestaña. Las presentaciones tienen
prioridad sobre el factor; simples estándar y no estándar se reparten el resto de los
activos en ambos sistemas. Se conservan los factores estándar anteriores:
6, 4, 2.5, 2, 1.5, 1, 0.5. Nulo significa estado vacío o NULL, no ausencia de match.

Evidencia: `reports/libro_categorias_excluyentes_final/`, con Excel, snapshots, ERP,
plan, resumen y validación independiente. Generación en 14,277 segundos; 3126202 bytes.

| Pestaña | Productos | Filas |
|---|---:|---:|
| Activos ambos - presentaciones | 68 | 136 |
| Activos ambos - simples | 4416 | 4529 |
| Activos - factor no estándar | 8 | 8 |
| ERP inactivo - PS activo | 382 | 382 |
| ERP activo - PS inactivo | 149 | 275 |
| PS activo sin ERP | 0 | 0 |
| PS inactivo sin ERP | 59 | 59 |
| ERP activo sin PS | 4975 | 4975 |
| ERP inactivo sin PS | 860 | 860 |
| ERP nulo | 0 | 0 |
| PS nulo | 0 | 0 |
| Otros y por revisar | 5 | 5 |

Las fichas PS suman 5087 productos / 5394 filas, sin duplicarse entre pestañas. Las
5835 filas ERP sin PS se separan por estado. Las ocho filas no estándar incluyen
seis factores numéricos fuera de la lista y dos vacíos que requieren revisión.

## Condiciones de escritura verificadas

- Solo las tres primeras categorías pueden tener `elegible_precio=SI`. Las demás
  siempre tienen `NO`, incluidos los ERP activos sin PS.
- Pertenecer a las tres primeras es condición necesaria, no suficiente: siguen los
  bloqueos de fuente ERP, correspondencia, precio, factor, PUM y presentaciones.
- Antes de aplicar, se contrasta cada operación con la clasificación y elegibilidad.
  Una operación ajena a esas categorías aborta antes de llamar al escritor.
- Se exige PS activo tanto en el origen inicial como en el destino actual; el escritor
  nativo también comprueba el estado actual antes de actualizar precio o PUM.
- La relectura ERP previa al lote conserva la protección ante cambios de fuente.
- Continúa `.227` como origen inicial, con hash
  `38d0c00f47ab5671a6f9e92a4092237eb52c21f9e28c446daa0554f8b67c7350`.

## Pruebas

- 61 pruebas Python del sincronizador y 38 del preparador correctas.
- Pruebas PHP del escritor correctas, incluidos bloqueo de estado inactivo/nulo,
  ausencia de escrituras en ese caso, preservación de nombres/stock y rollback.
- Sintaxis PHP correcta.
- Lectura completa independiente con openpyxl: doce pestañas en orden, todos los PS
  presentes, exclusividad por ficha, factores estándar correctos, todas las filas
  informativas no elegibles, 219278 celdas numéricas y ninguna fórmula.

La generación fue sin `--apply`: cero escrituras de precio. Permanecen cuatro productos
bloqueados previamente, que este cambio del informe no resuelve. El cron sigue pausado.
No se utilizó producción. La generación sigue usando solo la biblioteca estándar.
