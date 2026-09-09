# Subdivisión por ocultamiento de stock — 9 de septiembre de 2026

Las categorías de activos en ambos sistemas con presentaciones y simples estándar
se dividen según el ocultamiento efectivo del módulo `stockthresholdhide` en `.229`.
Las reglas de elegibilidad de precios se conservan en ambas subdivisiones. Los no
estándar siguen en una pestaña y reciben las mismas columnas informativas de stock.

| Subdivisión | Productos | Filas |
|---|---:|---:|
| Presentaciones - sin ocultar | 63 | 126 |
| Presentaciones - stock bajo | 5 | 10 |
| Simples - sin ocultar | 3757 | 3870 |
| Simples - stock bajo | 659 | 659 |

Se conservan los totales anteriores: 68 fichas con presentaciones y 4416 simples.
El libro completo tiene catorce pestañas, 5087 fichas PS sin duplicados y conserva
las presentaciones juntas, BASE primero, y el orden por diferencia de precios.

## Fuente y significado

El módulo debe estar activo y habilitado. Se consultan sus reglas por categoría,
expansión de subcategorías y mínimo más exigente. La cantidad se obtiene con la
misma función nativa y consulta alternativa utilizadas por el módulo. Las reglas
se expanden una sola vez y las asociaciones se leen juntas, evitando repetir las
consultas de categorías para cada producto.

Se agregan las columnas de inventario evaluado, mínimo visible, oculto por stock,
página bloqueada por stock, reglas aplicadas, motivo y servidor de origen. Usan el
destino actual para explicar su visibilidad, conservando `.227` como fuente de los
campos iniciales anteriores. Sin regla aplicable o con módulo desactivado no se
clasifica una ficha como oculta aunque tenga stock cero. «Sin ocultar» se refiere
exclusivamente al módulo de stock, no garantiza acceso frente a otras restricciones.

La Nan Etapa 2 de 1400 g (2403) queda en Simples - stock bajo: cantidad 0, mínimo 5,
regla Bebés (187), página bloqueada. La de 400 g (2402), con 6 unidades, queda en
Simples - sin ocultar. Furosemida (4480) no tiene regla aplicable: mínimo 0 y no oculta.

## Evidencia y verificación

- `reports/auditoria_stock_bajo_final/stock_auditoria_20260909_064458_821007.xlsx`.
- Ejecución sin `--apply`, 39,122 segundos, 3517259 bytes; cero escrituras de precio,
  inventario, estado, nombres o configuración del módulo.
- 66 pruebas Python del sincronizador y 38 del preparador correctas.
- Pruebas PHP del lector de stock: subcategorías, reglas concurrentes, igualdad al
  umbral, umbrales de 1 y 5, fallback de cantidad, módulo desactivado, modos all y
  selected, diferencia entre ocultar listados y bloquear URL.
- Pruebas del escritor y sintaxis PHP correctas.
- XLSX leído por completo: columnas iniciales preservadas, exclusividad, grupos
  contiguos, BASE primero, cantidades y clasificación coherentes con la evidencia.
- Muestra de 30 fichas contrastada con los métodos originales `shouldHideProduct`
  y `getRuleMinQtyForProduct`: todos los resultados y mínimos coinciden.

Se conserva el hash de la base congelada registrado anteriormente. El cron continúa
pausado y producción no se utilizó. Las cuatro incidencias previamente bloqueadas
siguen reportadas; esta subdivisión no cambia sus resultados de sincronización.
