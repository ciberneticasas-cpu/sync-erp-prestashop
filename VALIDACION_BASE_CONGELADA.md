# Base inicial .227 y nombres conservados — 8 de septiembre de 2026

El sincronizador lee el snapshot completo inicial por SSH desde `.227`, consulta el
ERP de solo lectura y compara las propuestas con el destino `.229`. La configuración
actual activa este modo mediante `baseline_host`. No se instaló ningún archivo remoto
ni se cambiaron permisos MariaDB. Si SSH falla, no se sustituye el origen por el destino.

## Comprobaciones

- 44 pruebas Python del sincronizador, incluidas las de base congelada: correctas.
- Pruebas PHP: preservación de nombres y stock, verificación/rollback de precios y PUM,
  y recuperación del impacto inicial de una variante no relacionada con presentaciones.
- 38 pruebas Python y pruebas PHP del preparador: correctas; los planes antiguos que
  incluyen renombrados se rechazan. Crear combinaciones conserva el nombre del producto.
- Dos ejecuciones completas con `--apply`: 5087 fichas; 4487 sin cambios, 211 inactivas,
  385 excluidas ERP y los mismos cuatro bloqueos de correspondencia. Cero escrituras.
- Última ejecución: 10,737 segundos, incluidos SSH, ERP e informes.
- Comparación de snapshots completos: origen .227 y destino .229 intactos durante este
  ajuste. No se cambiaron nombres, existencias, productos ni combinaciones.

El SELECT bruto de `product` en .227 devuelve 5089 registros; la lectura completa que
exige fila de tienda e idioma devuelve las mismas 5087 fichas presentes en .229.
Los nombres de 23 fichas ya diferían entre clones por pruebas anteriores: se muestran
por separado y no se restauraron ni modificaron durante este cambio.

## Informe

Evidencia local: `reports/base_227_final/`, con snapshot inicial y destino, ERP, plan,
CSV completo, CSV de cambios vacío, resumen e `integridad.json`. No se sube a Git.
Huella de la base utilizada:
`38d0c00f47ab5671a6f9e92a4092237eb52c21f9e28c446daa0554f8b67c7350`.

Hay 134 filas de combinaciones creadas después del clon inicial: sus valores históricos
no se inventan y se identifican con `COMBINACION_NUEVA_SIN_BASE`. El precio y el PUM
originales del padre se conservan en sus columnas específicas. El informe incluye
92 sugerencias de nombre, sin aplicarlas.

Ejemplo de Eutarpan: la combinación 143 conserva como precio inicial 91200 (48000 de
base más impacto 43200 de .227), frente a 4800 actuales en .229. Esto es una diferencia
histórica, no una nueva escritura: `cambio_aplicado_en_corrida=NO` y el archivo de
cambios permanece vacío al repetir.

El cron sigue pausado en `/home/desa/mercaboy-precios-pruebas.cron.pausado`.
Producción no se utilizó.
