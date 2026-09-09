# Redondeo monetario de precios visibles — 9 de septiembre de 2026

Se usa la precisión y el modo de redondeo configurados en PrestaShop: COP, cero
decimales, HALF_UP. Las lecturas reales incluyen esos metadatos y se valida su presencia.
La aritmética del informe usa Decimal. No se cambian la precisión de los precios
internos, los factores, los datos originales del ERP ni la configuración de moneda.

## Alcance

- Precios visibles de origen, destino, antes de la corrida, propuestos y verificados.
- PUM visible verificado, también en el CSV de cambios.
- Diferencias históricas y de corrida, restando los importes ya redondeados.
- Comparación visible, verificación del pronóstico y orden por diferencia/factor.
- Comprobación nativa de que las presentaciones tienen precios distintos: se comparan
  después del redondeo de moneda, impidiendo aceptar diferencias invisibles al cliente.

Se conservan columnas `_tecnico` con los valores de seis decimales del motor y las
restas técnicas. Las verificaciones `_tecnica` mantienen la tolerancia anterior de
0.01 y siguen impidiendo declarar resuelto un resultado técnicamente discrepante.
El diario nativo mantiene los valores técnicos originales. No se usa el redondeo
visual para decidir qué precios internos necesitan escribirse.

## Ejemplo confirmado

Pestañina, referencia PS 11099, ID 5294, mapeada a ERP 030721:

| Campo | Resultado |
|---|---:|
| precio_visible_base_227 | 30400 |
| precio_visible_229 | 32900 |
| precio_visible_229_tecnico | 32900.000001 |
| diferencia_precio_visible | 2500 |
| diferencia_precio_visible_tecnico | 2500.000001 |
| precio_final_sin_iva | 27647.058824 |

El residuo procede de guardar el precio sin IVA con seis decimales y volver a aplicar
el 19%. Se conserva el precio neto; se redondea únicamente la representación monetaria.

## Ejecución y evidencia

`reports/auditoria_redondeo_moneda_final/stock_auditoria_20260909_081255_400701.xlsx`.
Ejecución completa con `--apply --evidence`: 68,103 segundos, 3775390 bytes.

- 5227 filas verificables coinciden con el pronóstico visible y técnico.
- Había 28 productos con precios ERP nuevos respecto a la auditoría anterior. Se
  actualizaron y verificaron sin errores: 59 filas en el CSV de cambios.
- Se contrastaron los ERP de las 28 operaciones con la lectura anterior: todas tienen
  cambio real en el precio bruto de la fuente, independiente del redondeo del informe.
- Se comprobó que las 5087 fichas conservan nombres, referencias, existencias, estado,
  atributos y estructura. La base `.227` conserva su hash anterior.
- El libro mantiene catorce pestañas y agrupación BASE primero. Frente al origen:
  4992 filas comparables iguales, 76 menores y 92 mayores.
- Persisten cuatro productos bloqueados anteriormente. El código de salida 2 informa
  esas incidencias; el diario del lote es APLICADO_Y_VERIFICADO, sin errores de escritura.

## Validación

69 pruebas Python del sincronizador y 38 del preparador correctas. Pruebas PHP del
escritor, reglas de stock y sintaxis correctas. Se verificaron residuos de una millonésima,
redondeos en límites, moneda con dos decimales, modos de redondeo, monedas incompatibles,
PUM y CSV, y rollback cuando dos presentaciones resultan visualmente iguales.

Lectura independiente completa del XLSX: 26305 celdas visibles contrastadas con su
valor técnico, diferencias coherentes, orden por diferencia y por factor en ceros,
grupos contiguos y presentación básica primero. El CSV real también conserva los valores
técnicos y redondea sus importes visibles/PUM en las 59 filas.

Detalles en `validacion_redondeo.json`, `validacion_preservacion.json`, `resumen.json`,
`aplicacion.json` y las lecturas nativas del directorio de evidencia. Cron pausado;
producción no se utilizó.
