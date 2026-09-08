# Uso de la nueva versión

Ejecutar desde `/home/desa/sync-erp-prestashop`:

```bash
python3 sincronizar.py
```

Solo consulta el ERP y PrestaShop y genera **un CSV por ejecución**, con nombre
`reports/sincronizacion_FECHA/stock_auditoria_FECHA.csv`. No cambia precios, existencias
ni plantillas. Los JSON de la misma carpeta conservan evidencia y resultados técnicos.

Para aplicar todos los productos válidos:

```bash
python3 sincronizar.py --apply
```

No hay que editar autorizaciones en el CSV ni proporcionar hashes. `--apply` genera un
plan nuevo con datos actuales, vuelve a comprobarlos antes de escribir, aplica mediante
objetos nativos y actualiza el mismo CSV con los resultados. También ejecuta la reparación
del tema y verifica todas las presentaciones visibles. Un fallo individual queda registrado
y se intenta el resto. Código de salida 2 significa productos bloqueados, errores de
aplicación o de verificación; no significa que las escrituras exitosas se hayan revertido.

Filtro opcional para un producto: `--product 4480` (repetible). Carpeta opcional:
`--output reports/mi_ejecucion` (debe ser nueva). El alcance por defecto son todos los
productos activos, igual que el programa anterior.

## Reparar solamente el navegador

```bash
python3 corregir_blister.py
python3 corregir_blister.py --apply
```

El primer comando comprueba y previsualiza. El segundo restaura las clases esperadas
por PrestaShop, separa formularios y controles de las tarjetas de recomendados, instala
la plantilla del módulo de ubicación en el tema y limpia la caché de Smarty. Activa la
visualización de combinaciones sin stock para esta revisión. Conserva copias de los
archivos modificados y se puede repetir: una plantilla ya corregida no se duplica.

Este script repara la interfaz. Las combinaciones y sus precios se preparan mediante
`sincronizar.py --apply`. Ambos comandos están protegidos para el clon 311. Tras reparar,
recargar las páginas abiertas para sustituir el HTML anterior.

Verificación adicional de todas las presentaciones, sin escribir catálogo:

```bash
python3 verificar_presentaciones.py --output reports/verificacion_presentaciones.json
```

## CSV y MATCH

Se conservan las primeras 23 columnas y su orden de
`/opt/2prestashopsync/stock_auditoria_20260907_175348.csv`. Después se añaden identificadores,
criterio de MATCH, observaciones, presentación, resultado, precio final y enlace.
Los productos con Blíster (también «BLISTER DE 10TAB» y Sobre) se colocan al final,
agrupando todas sus filas: primero Caja, después las fracciones.

- `precio_mariadb`: importe anterior sin IVA; en una combinación incluye su impacto.
- `precio_para_prestashop`: importe propuesto sin IVA para esa presentación.
- `precio_final_sin_iva` y `precio_visible_verificado`: resultado; el visible incluye
  impuestos y descuentos existentes. La comprobación de todas las presentaciones completa
  el precio visible incluso para las que ya estaban sincronizadas.
- `inventario_para_prestashop`: conversión teórica, **no stock que se publique**.
- `final_sync`: stock conservado; cero para combinaciones nuevas de revisión.
- `pendiente` y `unidad_mariadb_inferida`: vacíos porque esta versión no calcula reservas
  ni infiere unidades para escribirlas. Las columnas PUM describen la configuración actual,
  que se conserva. No se atribuyen cálculos del programa antiguo a esta versión.
- `resultado`: `PROPUESTO`, `APLICADO`, `SIN_CAMBIOS`, `BLOQUEADO` o `ERROR`.

El MATCH reproduce la prioridad anterior: referencia PrestaShop contra referencia ERP,
barras/barras2/barras3 y ProductoId; después EAN PrestaShop contra códigos de barras.
Primero se prueba la clave exacta y después su variante numérica sin ceros iniciales;
se excluyen claves ambiguas. Las discrepancias de referencia/EAN revisadas quedan en
`settings.json` y `reports/match_revisado_20260908.json`. Nuevas discrepancias se bloquean
para evitar cruces de productos distintos.

Los nombres «Fracción» que tienen varias presentaciones explícitas usan el nombre completo
ERP y la lista de presentaciones. No se deducen blísteres inexistentes solo por el nombre.
Presentaciones con igual factor y precio se omiten. Las variantes de tamaño o grosor se
conservan y solo se actualiza el precio base cuando procede.

## Destinos y alcance

Solo `192.168.0.229`, clon 311, `mercaboy_pruebas`, tienda 1. Se conserva `.env`.
SQL Server `192.168.0.231` se consulta con SELECT; producción, template 309 y clon 310 no
se modifican. No se hacen dumps. No se usa BigQuery ni Docker.

Las presentaciones quedan visibles **con compra deshabilitada**; las nuevas combinaciones
reciben stock cero. No se publica stock ERP ni se duplican existencias entre Caja y Blíster.
El núcleo de PrestaShop y los archivos originales de `wkcustomhyperlocal` no se editan.
La personalización del módulo reside en el tema, según el mecanismo documentado:
https://devdocs.prestashop-project.org/8/themes/reference/overriding-modules/
