# Auditoría Excel con pestañas — 8 de septiembre de 2026

`sincronizar.py` genera `stock_auditoria_FECHA.xlsx` en lugar del CSV completo.
Se mantiene `cambios_precios_FECHA.csv` para las escrituras de cada ejecución.
El origen inicial sigue siendo `.227`, el ERP `.231` y el destino de pruebas `.229`.

## Libro generado

Evidencia local: `reports/libro_auditoria_final/`, con el Excel, resumen, snapshots,
ERP, plan y `validacion_libro.json`. La generación completa tardó 13,858 segundos.
Tamaño del archivo: 3114908 bytes, aproximadamente 3,1 MB.

| Pestaña | Productos | Filas |
|---|---:|---:|
| Activos ambos - simples | 4424 | 4537 |
| Activos ambos - presentaciones | 68 | 136 |
| ERP inactivo - PS activo | 382 | 382 |
| ERP activo - PS inactivo | 149 | 275 |
| ERP sin PrestaShop | 5835 | 5835 |
| Otros y por revisar | 64 | 64 |

Las pestañas de fichas existentes suman 5087 productos y 5394 filas. Las filas
adicionales corresponden a presentaciones o variantes, no a productos nuevos.
La pestaña de ausentes incluye registros activos e inactivos del ERP. Se comparan
referencias, EAN y mapeos contra el catálogo completo, incluso con `--product`.
Las correspondencias ambiguas no se presentan como ausencias confirmadas.

La clasificación activo/inactivo utiliza A/I del ERP y el estado inicial de la tienda;
las marcas de exclusión comercial permanecen en sus columnas. «Otros y por revisar»
conserva ambos inactivos y estados/correspondencias sin resolver.

## Validación

- 51 pruebas Python del sincronizador: correctas, incluidas particiones, códigos,
  ERP inactivo, coincidencias ambiguas, alcance completo con `--product`, variantes
  que no son presentaciones y actualización del libro después de aplicar.
- 38 pruebas Python del preparador: correctas.
- Archivo leído por completo con openpyxl 3.0.10, instalado exclusivamente en un
  directorio temporal para validación: seis hojas, cantidades de filas correctas,
  precios numéricos, identificadores como texto y ninguna fórmula inesperada.
- Pruebas de estructura XLSX: paquete ZIP/XML válido, filtros y paneles inmovilizados.
- La generación normal utiliza únicamente la biblioteca estándar de Python; no requiere
  openpyxl ni otras dependencias adicionales.

Esta ejecución fue una auditoría sin escrituras. No modifica nombres, stock ni catálogo.
El cron continúa pausado y producción no se utilizó.

## Ampliación: factores y PrestaShop sin ERP

Se generó `reports/libro_factores_ausencias_final/stock_auditoria_20260908_224039_380412.xlsx`
con nueve pestañas. La lectura completa y generación tardó 14,435 segundos; archivo
3158895 bytes. La base congelada conserva el hash
`38d0c00f47ab5671a6f9e92a4092237eb52c21f9e28c446daa0554f8b67c7350`.

| Pestaña | Productos | Filas |
|---|---:|---:|
| Activos - factor no estándar | 74 | 74 |
| Activos ambos - simples | 4424 | 4537 |
| Activos ambos - presentaciones | 68 | 136 |
| ERP inactivo - PS activo | 382 | 382 |
| ERP activo - PS inactivo | 149 | 275 |
| ERP sin PrestaShop | 5835 | 5835 |
| PS activo sin ERP | 0 | 0 |
| PS inactivo sin ERP | 59 | 59 |
| Otros y por revisar | 5 | 5 |

La primera pestaña es una vista adicional: 72 filas con factor numérico fuera de
6, 4, 2.5, 2, 1.5, 1, 0.5 y dos con factor vacío que requieren revisión. No se suma
esa vista a las pestañas de clasificación. Las ausencias en ERP se contrastaron
contra todos los identificadores ERP y las referencias/EAN de la base congelada.

Validación de esta ampliación:

- 56 pruebas del sincronizador y 38 del preparador correctas. La primera ejecución
  de las pruebas del preparador coincidió con la auditoría y respetó el bloqueo
  compartido; se repitió correctamente al terminar esta.
- Lectura completa con openpyxl: nueve pestañas, cantidades correctas, 221668 celdas
  numéricas, ninguna fórmula. La primera hoja coincide exactamente con el filtro
  de las filas activas en ambos sistemas, evaluado por presentación.
- Pruebas de equivalencia decimal, factores inválidos, separación activo/inactivo,
  correspondencias ambiguas/inactivas, mapeos e identificadores congelados.
- Auditoría sin `--apply`, cero cambios de precio aplicados. Continúan cuatro
  productos bloqueados previamente en el plan; este ajuste del informe no declara
  resueltas esas incidencias. Cron pausado y producción sin utilizar.

Detalles en `reports/libro_factores_ausencias_final/validacion_libro.json` y
`resumen.json`. El archivo XLSX sigue sin requerir dependencias adicionales en ejecución.
