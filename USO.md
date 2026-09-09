# Operación

Requisitos en pruebas: Python 3.6+, PHP CLI compatible con la tienda, acceso local a
PrestaShop 8.1.7 y lector Rust compilado con `cargo build --offline --release`.
La compilación offline requiere dependencias ya descargadas; en una máquina nueva usar
`cargo build --release` si no existe la caché. No hacen falta paquetes pip.

Desde el directorio del proyecto:

```bash
python3 sincronizar.py
python3 sincronizar.py --apply
python3 sincronizar.py --apply --product 4480
```

Cada ejecución genera `reports/sincronizacion_FECHA/`:

- `stock_auditoria_FECHA.csv`: todas las fichas de PrestaShop, incluidas las inactivas.
- `cambios_precios_FECHA.csv`: únicamente filas de escrituras exitosas que cambiaron el
  precio base, el impacto, el precio de presentación o el PUM. Solo cabecera si no hubo cambios.
- `resumen.json`: estados, duración y rutas de informes.
- `aplicacion.json` y `recibos.jsonl`: resultados de aplicación y recibos por producto.

`--evidence` añade lectura ERP, snapshot y plan completos. `--output RUTA` exige una
carpeta nueva. `--settings ARCHIVO` permite elegir la configuración de otro clon local.
Las primeras 23 columnas del CSV se conservan; todas las filas de productos con Blíster
quedan al final. No se publican existencias ERP.

`precio_mariadb` es el precio anterior sin impuestos; `precio_para_prestashop` el propuesto;
`precio_final_sin_iva` el resultado. El precio visible verificado por el motor incluye
promociones y descuentos, por lo que no siempre coincide con el importe ERP.
En combinaciones inexistentes, el precio propuesto no es un precio publicado.
`presentacion_en_prestashop` y `situacion_presentacion` distinguen ambas situaciones.

El PUM se recalcula en cada ejecución, incluso cuando el precio de venta no cambia:

1. Lee `HeadProd.PUMContenidoInterno` y `HeadProd.PUMUnidadMedida` del ERP.
2. Normaliza kilos/gramos y litros/mililitros y convierte el contenido ERP a la unidad
   vendida en PrestaShop usando el factor comercial del producto simple.
3. Contrasta contenido **y unidad** con el nombre de PrestaShop. Si coinciden, usa ERP;
   si difieren, usa el nombre y marca `pum_discrepancia=SI`.
4. Si solo se puede interpretar una fuente, la utiliza. Si ninguna contiene una cantidad
   y unidad interpretables, utiliza `Unidad`, ratio 1 por presentación vendida.

`pum_fuente` explica la elección; las columnas `pum_contenido_erp`,
`pum_unidad_erp`, `pum_contenido_erp_convertido`, `pum_contenido_nombre` y
`pum_unidad_nombre` permiten revisarla. La discrepancia persiste en el CSV completo
incluso después de sincronizar. Los productos excluidos o bloqueados conservan su PUM.

Se interpretan gramos, kilos, mililitros, litros y cantidades explícitas de tabletas,
cápsulas, ampollas, sobres y unidades. Los miligramos de dosis y denominadores de
concentraciones como `160mg/5ml` no se consideran contenido del envase. `3.000 gr`
se interpreta como 3000 gramos. Un peso acompañado de un número de unidades se toma
como peso total; solo se multiplica con indicación por unidad (`c/u`, `cada unidad`),
repuestos o una expresión explícita como `pack 6 x 200ml`. Se reconocen totales,
contenidos adicionales de la misma unidad y ofertas «pague/lleve». No se deducen
cantidades del nombre ERP ni de un PUM anterior. Los nombres que contienen varias
cantidades sin una interpretación única llevan `pum_observacion=NOMBRE_CON_CONTENIDOS_AMBIGUOS_REVISAR`;
en ese caso se usa el PUM ERP válido y, si no existe, el valor por defecto.

`pum_ratio` es el contenido seleccionado de la presentación; `pum_precio_unitario`
es precio sin IVA dividido por ese contenido. Para alternativas con contenido conocido,
el contenido base se multiplica por el factor de la presentación. Si se usó el valor
por defecto, cada presentación se considera una unidad vendida. Por ejemplo, un
nombre sin cantidad como «Bedoyecta ampolla», sin PUM ERP, utiliza ratio 1 tanto para
Caja como para UNIDAD; no se inventa cuántas ampollas contiene la caja.

Se guardan `unity`, `unit_price` y `unit_price_impact` mediante objetos nativos.
PrestaShop calcula su campo de compatibilidad `unit_price_ratio`; no se escribe
manualmente. `pum_ratio_final` refleja el cociente efectivo por combinación, con las
pequeñas diferencias de redondeo de seis decimales. El precio visible por unidad incluye
los impuestos y descuentos de la tienda y se registra en `pum_precio_visible_verificado`
cuando hubo aplicación verificada. Así, una caja de 100 tabletas a 48000 y un blíster
de 10 a 4800 muestran 480 por Unidad en ambas presentaciones, antes de descuentos.

Las columnas `pum_*_anterior` y `pum_*_propuesto` separan lo existente de la propuesta;
`pum_estado` indica si se aplicó. `cambios_precios_*.csv` también incluye cambios
exclusivamente del PUM, identificados por `tipo_cambio=SOLO_PUM`; las demás categorías
son `SOLO_PRECIO` y `PRECIO_Y_PUM`. Solo se registran escrituras confirmadas.

## Vigencia y correspondencias

Se exige `Producto.estado=A` y ausencia de marcas explícitas «no usar», DESCO/DESC,
DESCODIFICADO o ANULAR en los campos correspondientes. «DESCONGEL» no se excluye por su
nombre. Los mapeos manuales también respetan esta regla.

La búsqueda usa primero candidatos elegibles. Si una referencia antigua excluida lleva
a otro registro por EAN, se exige revisar la sustitución: un mismo EAN puede estar mal
asignado o representar otra cantidad/aroma. No se escoge automáticamente otro producto.
Excluir una fuente ERP **no desactiva ni borra** su ficha de PrestaShop.

Estados del CSV: `SIN_CAMBIOS`, `PROPUESTO`, `APLICADO`, `EXCLUIDO_ERP`,
`INACTIVO_PRESTASHOP`, `PENDIENTE_PRESENTACIONES`, `BLOQUEADO`, `ERROR`.
`EXCLUIDO_ERP` incluye estado y motivo; no significa necesariamente baja definitiva del
fabricante. Cada ejecución vuelve a consultar la vigencia y puede admitir una fuente
reactivada.

## Altas y bajas de presentaciones

La lectura conserva tanto las definiciones ERP como su estado/permiso de venta. Solo
se usan para calcular precios las presentaciones activas, vendibles y con manejo
habilitado en la cabecera ERP. La unidad base sigue existiendo; unidades físicamente y
económicamente equivalentes se consolidan.

| Cambio | Proceso de precios | Preparador |
|---|---|---|
| Cambia precio o factor de una presentación existente | Actualiza base e impactos | No hace falta ejecutarlo |
| Aparece una alternativa nueva | `PENDIENTE_PRESENTACIONES`; conserva precios de la ficha | Repetir `corregir.py --apply`; crea lo que falta |
| Se inactiva una presentación, deja de ser vendible o ManejPrese pasa a N | Conserva en CSV las combinaciones web y marca discrepancia; no actualiza parcialmente la ficha | Señala retiro pendiente; no elimina automáticamente |
| Se inactiva el producto ERP completo | `EXCLUIDO_ERP`, conserva toda la ficha y su precio | No crea nuevas combinaciones usando esa fuente |
| Se reactiva el producto ERP | Revalida MATCH y estructura en la siguiente ejecución | Se usa si faltan combinaciones |

La reparación del tema es general; las combinaciones pertenecen a cada ficha. **El segundo
programa no puede considerarse de una única ejecución para siempre.** Debe repetirse ante
altas y revisarse ante bajas. El cron de precios no ejecuta el preparador.

Una combinación de PrestaShop no tiene un campo `active` equivalente al del producto.
Su eliminación nativa también elimina asociaciones con stock, precios específicos y
carritos. Por eso esta versión no automatiza bajas de combinaciones. Conserva y señala
las discrepancias, sin declarar sincronizado lo que aún difiere. Si se necesita que una
baja ERP desaparezca inmediatamente de la web, falta definir y probar la política de
retiro y de stock antes del despliegue productivo.

## Cada diez minutos

```bash
python3 instalar_cron.py           # Ver la línea y comprobar destino
python3 instalar_cron.py --apply   # Instalar en /etc/cron.d/mercaboy-precios-pruebas
```

El bloqueo compartido `reports/catalogo.lock` evita solapamientos con otra sincronización
o preparación. El cron limita cada ejecución a 540 segundos. Una escritura se valida
con el motor nativo antes del COMMIT; un error individual queda registrado y el resto
continúa. Si se interrumpe el proceso, revisar `recibos.jsonl` y `aplicacion.json` antes
de repetir: una transacción confirmada justo antes del corte podría requerir comparar
el catálogo. Una auditoría nueva siempre consulta los precios actuales.

Salida 0: ejecución resuelta o salto por bloqueo; 2: quedan bloqueos, errores o estructura
pendiente, aunque otros productos se hayan actualizado correctamente; 1: fallo general.
`reports/cron.log` conserva la salida del programador. Los CSV se conservan sin borrado
automático; un CSV completo ronda 2,8 MB (unos 400 MB/día con 144 ejecuciones). Archivar
informes antiguos forma parte del mantenimiento del servidor.

## Nueva máquina y producción

Clonar ambos repositorios como directorios hermanos. Preparar el clon y su IP mediante
el procedimiento de pruebas existente, revisar `settings.json`, compilar, auditar,
ejecutar el preparador, sincronizar precios y repetir ambas auditorías. No copiar planes
viejos: los identificadores de combinaciones pueden diferir entre clones.

Se exige base local `mercaboy_pruebas`, raíz `/var/www/html`, una sola tienda y dominio
igual a la IP LAN configurada; el ERP permitido es 192.168.0.231, de solo lectura.
**Esta versión no está habilitada para cPanel/mercaboy.com.** El ensayo en un clon nuevo,
la adaptación de rutas/permisos y las políticas de baja y stock pendientes y la revisión de nombres ambiguos
son parte de la preparación para producción.
