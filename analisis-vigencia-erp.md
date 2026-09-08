# Vigencia de productos ERP y correspondencia con PrestaShop

Revisión del 8 de septiembre de 2026. Consultas SELECT a SQL Server 192.168.0.231.
No se cambiaron precios, estados, correspondencias ni configuración de sincronización.

## Hallazgos del catálogo

Se consultaron 10.969 registros Producto unidos a HeadProd:

| Señal | Resultado observado | Uso propuesto |
|---|---|---|
| `Producto.estado` | A: 9.689; I: 1.280 | Exigir A para utilizar un registro como fuente vigente de precio. I identifica inactividad operativa; no prueba una baja definitiva del fabricante. |
| Nombre con «no usar» | 24 registros; 7 todavía en A | Excluir el registro como fuente automática, aunque figure activo. |
| Códigos de barras marcados `DESCO-…`, `DESCODIFICADO`, `DESC-…`, `ANULAR` | 68 registros; 16 en A | No utilizarlos como EAN ni como fuente automática hasta resolver la marca. |
| Stock positivo con estado I | 73 registros | El stock no anula la marca de inactividad. |
| `HeadProd.sustituto` | Vacío en los 10.969 registros | No existe aquí un enlace explícito para automatizar sustituciones. |
| `HeadProd.ECommerce` | N en 10.747; vacío en 222 | No sirve hoy como lista positiva de productos publicables: excluiría todo el catálogo. |
| `TipoProducto` | 01 = PRODUCTO ESTANDAR; 02 = PRODUCTO CON SABORES | 02 no significa descontinuado. |
| Nombres `OBS…` | 150 registros, todos en A | Su significado no quedó confirmado. `EsObsequio` está vacío en estos casos; no clasificarlos automáticamente como obsoletos ni como obsequios. |

Las marcas deben buscarse en su campo y con patrones delimitados. Por ejemplo, **DESCONGEL**
es el nombre de un medicamento y no debe excluirse por contener «DESCO». Tampoco
«BLOQUEADOR» o «ELIMINADOR DE PIOJOS» significan registros bloqueados/eliminados.
No se encontró un campo específico `descontinuado` en Producto/HeadProd ni descripciones
extendidas o restricciones CHECK que documenten una equivalencia adicional de estados.
No se deben confundir `HeadProd.Tipo` o el estado de Talla con `Producto.estado`.

## Caso Glade, producto PrestaShop 7746

PrestaShop conserva referencia `8761`, EAN `7591005001657` y nombre
«Glade Ambientador Vainilla X3 Repuestos X21ml».

| Evidencia | ERP 008761, referencia antigua | ERP 030947, EAN coincidente |
|---|---|---|
| Estado | I | A |
| Nombre | AMBIENTADOR GLADE REPUESTOS 21ML ACEITE 3U (no usar) | AMBIENTADOR GLADE REPUESTO 21ML ACEITE SURTIDO 3U |
| Barras | DESCO-71 | 7591005001657 |
| Variante | Talla 163 = HAWAIAN BREEZE | Sin talla asignada |
| Tipo | 02, producto con sabores | 01, producto estándar |
| Última venta registrada | 2026-05-20 | 2026-09-06 |
| Stock, suma de todos los almacenes | 0 | 44 |

La variante antigua VAINILLA era `004683`, talla 84, también en I, con `DESCO-70`.
Esto demuestra que la referencia 8761 de la ficha no identifica correctamente Vainilla.
El registro 030947 es el único candidato activo encontrado por el EAN exacto de la ficha;
su nombre es Surtido. La coincidencia permite proponerlo como fuente de precio del paquete
3 × 21 ml, pero no demuestra que represente exclusivamente el aroma Vainilla ni autoriza
renombrar la ficha. No hay enlace `sustituto` entre los registros. Es una inferencia de MATCH,
no una sustitución comercial explícitamente registrada en el ERP.

## Regla general propuesta

1. Mantener como universo los productos ya existentes en PrestaShop.
2. **Evaluar elegibilidad ERP antes de resolver el MATCH**, no después de elegir el primer código:
   exigir `Producto.estado = 'A'` y ausencia de marcas explícitas «no usar» o códigos descodificados/anulados.
3. Resolver referencia/EAN/ProductoId solo entre candidatos elegibles. Una referencia antigua
   excluida no debe impedir buscar una coincidencia por EAN real. Si hay un único candidato
   activo, comprobar contenido, cantidad de unidades y variante antes de darlo por resuelto.
4. Los mapeos manuales también deben respetar la elegibilidad; un mapeo no rehabilita un registro
   inactivo. Si apuntaba a uno excluido, proponer revisión de su EAN y conservar trazabilidad.
5. Con más de un candidato, cambios de tamaño/aroma o ninguna fuente elegible, conservar el
   precio y mostrar el motivo en el CSV. No elegir por tener stock, por precio más reciente
   ni simplemente por mayor código ERP.
6. Excluir un registro como **fuente de precio** no equivale a borrar o desactivar automáticamente
   el producto existente en PrestaShop. Esa sería otra regla comercial.

Para el CSV propondría añadir `estado_erp`, `marcas_vigencia_erp`, `elegible_precio`,
`criterio_match` y `motivo_exclusion`, aprovechando las columnas de diagnóstico existentes.

## Impacto y limitación de la versión actual

El lector que alimenta actualmente la sincronización no incluye `Producto.estado` ni las
marcas de vigencia. Esta es una omisión detectada en la revisión; verificar que un precio
coincide con el motor nativo no verifica que su registro ERP sea vigente.

Al contrastar las correspondencias actuales de las 4.876 fichas auditadas con la lectura
actual del ERP, **393** apuntan a registros con marcas: **392 en estado I** y un registro A
con código DESCO. Es una evaluación de fuentes, no 393 nuevas escrituras ni 393 precios
necesariamente incorrectos. De los productos intervenidos en los lotes anteriores, **36**
apuntan hoy a registros con estas señales; no se dispone de su estado histórico en el
momento de cada aplicación. No se ha revertido ni modificado ninguno en esta revisión.

La nueva regla queda **propuesta, todavía no incorporada al sincronizador**. La ausencia
actual de un precio pendiente no sustituye este control de vigencia.

## Evidencia

- [Lectura completa](reports/estados_erp_20260908/lectura.json): estados, marcas, fechas, variantes, tipos y metadatos.
- [Resumen](reports/estados_erp_20260908/resumen.json).
- [Correspondencias actuales con marcas](reports/estados_erp_20260908/matches_actuales_con_marcas.json).
- Lector independiente: `src/bin/auditar_estados.rs`, con consultas SELECT fijas; no admite SQL libre.

El análisis no genera otro CSV: se mantiene el CSV principal de revisión sin cambios.
