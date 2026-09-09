# Origen configurable y resumen de atributos — 9 de septiembre de 2026

`SERVIDOR_CONGELADO` identifica el origen completo de MariaDB y de precios visibles.
Actualmente vale `192.168.0.227` en `settings.json`. Una variable de entorno del mismo
nombre tiene prioridad; `baseline_host` se admite para configuraciones anteriores.
La dirección se valida, se comprueba el servidor que responde y se rechaza usar el
origen como destino de escritura. Ambos programas y las reparaciones del tema usan
la misma protección. Los adaptadores continúan limitados al entorno de pruebas.

El libro compacta atributos exclusivos de PrestaShop sin impacto en precio o PUM.
Conserva una fila del producto con precio visible de su combinación predeterminada,
comparación histórica e inventario del producto. Caja/blíster y variantes con diferencias
conservan su detalle. No cambia los planes, el registro de escrituras ni los controles
internos por combinación.

## Verificación

- 78 pruebas Python del sincronizador y 38 del preparador correctas.
- Pruebas PHP de ambos escritores correctas: preservación, verificación y rollback.
- Pruebas sin base de datos con origen simulado `10.5.0.227`: protección de ambos
  escritores, prioridad del entorno, clave anterior y rechazo de valores inválidos.
- Lecturas SSH simuladas verifican que snapshot y motor usan el origen configurado;
  un servidor que responde con otra identidad o coincide con destino se rechaza.
- El informe registra el origen efectivo en `base_host` y `servidor_congelado` del resumen.

## Ejecución completa en pruebas

`reports/aplicacion_origen_configurable/stock_auditoria_20260909_121235_047437.xlsx`

Ejecutado con `--apply --evidence`: 57,328 segundos. Se actualizaron y verificaron
20 productos con cambios ERP desde la lectura anterior, sin errores de aplicación.
El CSV contiene 20 filas de cambios confirmados. Los datos vigentes del ERP también
modificaron categorías informativas; el libro refleja la nueva lectura.

- 5227 comprobaciones visibles y técnicas coinciden; 167 filas no tienen presentación
  existente comparable en el destino y conservan su señalización.
- 41 productos resumidos; 113 filas redundantes eliminadas. Libro de 14 pestañas,
  11118 filas de datos en total, incluidas las ausencias ERP/PS informativas.
- Repollo 85: una fila KL, factor 2, precio 8600 en ambos servidores y diferencia 0.
- Pepino 152: una fila KL, factor 0,5, precio inicial 2250, final 1950 y diferencia -300.
- La lectura posterior de las 5087 fichas confirma que nombres, referencias, atributos,
  estructura, existencias y estados no cambiaron. Solo se admitieron precio y PUM.
- Huella del origen intacta:
  `38d0c00f47ab5671a6f9e92a4092237eb52c21f9e28c446daa0554f8b67c7350`.
- XLSX abierto y contrastado por XML independiente, teniendo en cuenta celdas vacías;
  la compactación no modifica las filas originales de auditoría.
- Se mantienen cuatro bloqueos previos de correspondencia/revisión; salida 2 informa
  esos bloqueos, no errores de aplicación ni discrepancias de precios.

Evidencia: `resumen.json`, `aplicacion.json`, `validacion_compactacion.json`, lecturas
ERP y de ambos catálogos y precios visibles en ese directorio. Cron pausado.
Producción no utilizada; el cambio de origen no habilita por sí solo cPanel.
