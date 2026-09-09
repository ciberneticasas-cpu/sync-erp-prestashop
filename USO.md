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

## Punto de partida congelado en desarrollo

La configuración actual contiene `baseline_host: 192.168.0.227`. En cada corrida se
consulta por SSH `root@192.168.0.227` el snapshot completo de MariaDB: productos,
nombres, referencias, códigos, precios, PUM, estado, existencias, combinaciones,
atributos y precios específicos. Se reutilizan exactamente las consultas del lector
local. El puerto MariaDB respondió, pero las credenciales locales no permitieron acceso
remoto; se utiliza SSH sin cambiar permisos de la base ni instalar archivos remotos.
Si falla esta lectura, la ejecución se detiene antes de escribir. No usa el destino ni
un CSV anterior como sustituto. Se exige clave SSH disponible para el usuario del cron.

La copia `.229` sigue siendo el destino. Su lectura actual sirve para localizar las
combinaciones, detectar qué importes requieren una escritura y comprobar que el producto
no cambió entre la auditoría y la aplicación. La elegibilidad, la correspondencia ERP y
los datos iniciales de cálculo parten de `.227`. El motor del destino verifica los
precios publicados. El nombre, el estado activo y las existencias no se escriben.

Los campos anteriores (`nombre_prestashop`, `referencia`, `inventario_mariadb`,
`precio_mariadb`, `precio_base_anterior`, `impacto_anterior`, `activo_prestashop` y los
`pum_*_anterior`) corresponden a `.227`. Las columnas `*_destino_antes` conservan la
lectura real previa a esta corrida en `.229`. `nombre_destino_actual` identifica el
nombre que permanece publicado. `final_sync` refleja la existencia del destino, que
el sincronizador no modifica. `base_host` y `base_huella` identifican la lectura inicial.

Las combinaciones se corresponden por grupo y valor de atributo dentro del mismo
producto; no se presupone que IDs reutilizados entre clones sean equivalentes. Si una
combinación fue creada después de la copia, `base_estado=COMBINACION_NUEVA_SIN_BASE` y
sus importes/existencias anteriores quedan vacíos. Los datos originales del padre
siguen disponibles en `precio_base_anterior`, `inventario_producto_inicial`,
`pum_precio_producto_inicial`, `pum_ratio_producto_inicial` y `pum_unidad_anterior`.
No se asigna a una combinación nueva un precio histórico que nunca tuvo.

`diferencia_respecto_base` compara el resultado con el punto de partida y puede seguir
en SI durante muchas corridas. `cambio_aplicado_en_corrida` y el archivo de cambios
registran únicamente escrituras reales de esa ejecución; una diferencia histórica no
provoca escrituras ni registros repetidos. Un producto del destino ausente en la base
inicial queda bloqueado para revisión.

Este modo corresponde al entorno de desarrollo. Al preparar el uso normal se debe
revisar expresamente la configuración del origen. El cron permanece pausado desde
la solicitud del usuario; este ajuste no lo reinstala.

Cada ejecución genera `reports/sincronizacion_FECHA/`:

- `stock_auditoria_FECHA.xlsx`: libro Excel con las pestañas de auditoría detalladas abajo.
- `cambios_precios_FECHA.csv`: únicamente filas de escrituras exitosas que cambiaron el
  precio base, el impacto, el precio de presentación o el PUM. Solo cabecera si no hubo cambios.
- `resumen.json`: estados, duración y rutas de informes.
- `aplicacion.json` y `recibos.jsonl`: resultados de aplicación y recibos por producto.

`--evidence` añade lectura ERP, snapshot y plan completos. `--output RUTA` exige una
carpeta nueva. `--settings ARCHIVO` permite elegir la configuración de otro clon local.
El CSV completo de auditoría se sustituye por el Excel. El CSV de cambios se conserva.
Las pestañas de fichas existentes conservan las columnas anteriores; la de ERP sin
PrestaShop coloca primero la identificación, nombre, estado, stock y precio del ERP.
No se publican existencias ERP.

Las pestañas son excluyentes y se muestran en este orden:

1. **Activos ambos - presentaciones:** activos en ERP y PS, con más de una presentación
   ERP real o varias combinaciones del grupo Presentación en PS, cualquiera que sea su
   factor. Incluye presentaciones pendientes de preparar, con su advertencia.
2. **Activos ambos - simples:** activos en ambos, sin otras presentaciones y con factores
   estándar: **6, 4, 2.5, 2, 1.5, 1, 0.5**. Puede haber variantes de talla u otros atributos.
   La comparación es numérica: `6.` equivale a `6`, `1.000000` a `1` y `2,5` a `2.5`.
3. **Activos - factor no estándar:** los demás activos en ambos, que no entraron en las
   dos anteriores. Incluye factores vacíos o inválidos, señalados en `motivo_clasificacion`.
4. **ERP inactivo - PS activo:** ERP `I`, PS `1`.
5. **ERP activo - PS inactivo:** ERP `A`, PS `0`.
6. **PS activo sin ERP:** PS activo sin correspondencia en el ERP completo.
7. **PS inactivo sin ERP:** PS inactivo sin correspondencia en el ERP completo.
8. **ERP activo sin PS:** ERP activo sin correspondencia en el catálogo completo de PS.
9. **ERP inactivo sin PS:** ERP inactivo sin correspondencia en el catálogo completo de PS.
10. **ERP nulo:** registro ERP existente con estado vacío o NULL. Incluye los que no
    tienen correspondencia PS. No significa que el producto no exista en ERP.
11. **PS nulo:** estado inicial PS vacío o NULL; incluye fichas sin origen congelado.
    Si también hay estado ERP nulo, prevalece la pestaña anterior.
12. **Otros y por revisar:** lo no clasificado antes, incluidos ambos inactivos, estados
    distintos de A/I o 1/0 y correspondencias ambiguas.

La prioridad es por ficha completa: todas sus filas permanecen juntas. Si una ficha sin
otras presentaciones tiene alguna fila con factor no estándar, toda la ficha entra en
la tercera pestaña. No se repiten productos entre pestañas; ya no existe una vista
adicional duplicada para factores. Se conservan sugerencias y todos los datos de auditoría.

Solo las tres primeras pestañas pueden dar lugar a actualizaciones. Estar en ellas no
obliga a actualizar: siguen vigentes las comprobaciones de precio, factor, PUM,
correspondencia, presentaciones y marcas ERP como «no usar». `elegible_precio=SI` exige
además estado actual activo en PS y resultado SIN_CAMBIOS, PROPUESTO o APLICADO; las
pestañas informativas siempre indican `NO`. Las escrituras efectivas quedan en el CSV
de cambios, no se deducen únicamente de esa columna.

Antes de enviar el lote al escritor se verifica que cada operación pertenezca a una
única categoría de las tres permitidas y sea elegible. Se vuelve a comprobar la fuente
ERP antes del lote y el escritor comprueba que el producto PS esté activo antes de
modificarlo. Un destino inactivo o nulo bloquea la escritura aunque `.227` esté activo.
La clasificación y los valores iniciales siguen usando `.227`; `activo_destino_antes`
permite ver el estado actual. Los nombres, las existencias y el estado activo no se escriben.

Para detectar ERP sin PrestaShop se consultan todos los productos del destino, también
cuando se usa `--product`: esa lista siempre tiene alcance global. Las pestañas de fichas
PrestaShop corresponden a los productos seleccionados para la corrida. Para detectar PS
sin ERP se usan sus identificadores iniciales de `.227` cuando está configurada la base
congelada; si falta esa ficha inicial, no se afirma su ausencia en ERP. Se busca también
entre ERP inactivos y excluidos. Una coincidencia ambigua de referencia/EAN cuenta como
posible presencia y queda para revisión, no como ausencia confirmada. Las ausencias son
resultados de comparación de identificadores; este informe no crea productos ni combinaciones.

El libro incluye autofiltros, encabezado y dos columnas inmovilizados, precios y cantidades
numéricos, y referencias/códigos como texto para conservar ceros iniciales. El texto no
se convierte en fórmulas. La generación usa la biblioteca estándar, sin paquetes pip.
`resumen.json` registra la ruta en `workbook` y las cantidades de filas y productos por
pestaña en `sheets`. El libro se genera antes de aplicar y se actualiza con los resultados
al finalizar una ejecución con `--apply`.

`precio_mariadb` es el precio inicial congelado sin impuestos (o el precio actual previo si no se configura base congelada); `precio_para_prestashop` el propuesto;
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
`pum_unidad_nombre` permiten revisarla. La discrepancia persiste en el libro completo
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

Cuando el nombre inicial dice explícitamente «Fracción» y hay una única alternativa
ERP, ese contenido corresponde a la fracción: se divide por su factor ERP para obtener
el contenido de la caja. Por ejemplo, 10 tabletas / 0,1 = 100 tabletas. Se conserva el
nombre original; `pum_factor_presentacion_nombre` y `pum_contenido_nombre_convertido`
explican la conversión. Varias alternativas posibles requieren revisión.

Ninguno de los dos programas cambia nombres de productos ni escribe nombres en el ERP.
Las recomendaciones quedan en `nombre_suguerido_prestashop` y
`motivo_nombre_sugerido`. Los mapeos `product_name` son sugerencias, no instrucciones
de renombrado. El preparador rechaza planes antiguos con `new_name` no vacío.

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

Estados de la auditoría: `SIN_CAMBIOS`, `PROPUESTO`, `APLICADO`, `EXCLUIDO_ERP`,
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
| Se inactiva una presentación, deja de ser vendible o ManejPrese pasa a N | Conserva en el informe las combinaciones web y marca discrepancia; no actualiza parcialmente la ficha | Señala retiro pendiente; no elimina automáticamente |
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
`reports/cron.log` conserva la salida del programador. Los libros e informes de cambios
se conservan sin borrado automático. Archivar informes antiguos forma parte del
mantenimiento del servidor; su tamaño depende del catálogo y de las filas ERP ausentes.

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
