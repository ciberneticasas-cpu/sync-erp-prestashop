> **Actualización 2026-09-08:** el informe vigente y los comandos simplificados están en
> [README.md](README.md) y [USO.md](USO.md). Los totales siguientes describen el lote anterior.
> El nuevo lote aplicó 90 productos más (algunos ya intervenidos previamente), sin errores;
> no sumar los lotes como productos únicos. Se verificaron 92 fichas y 184 combinaciones.

# Resultado aplicado — clon Proxmox 311

Servidor **192.168.0.229**, PrestaShop **8.1.7**, base **mercaboy_pruebas**, tienda 1.
El usuario confirmó que la VM 310 es 192.168.0.228 y autorizó aplicar los precios en esta VM 311.

## Revisión

**[Abrir el único CSV final](reports/clon311/resultado_precios.csv.gz)**.

Contiene la propuesta original, precios e impactos anteriores, importes finales, ID de
combinación definitivo, resultado de aplicación y URL de cada presentación. Las filas
`APLICADO_HTTP_OK` están escritas y verificadas. `SIN_CAMBIOS_BLOQUEADO` identifica datos
que no se modificaron porque la correspondencia ERP o su presentación no era inequívoca.

| Resultado | Cantidad |
|---|---:|
| Productos activos analizados | 4.876 |
| Productos actualizados | 99 |
| Actualizaciones de precio simple | 48 |
| Productos con presentaciones creadas/corregidas | 51 |
| Precios del escaparate verificados por HTTP/AJAX | 150 |
| Errores en las 150 comprobaciones HTTP | 0 |
| Productos bloqueados pendientes | 150 |
| Productos inicialmente sin cambios de precio | 4.627 |

Las presentaciones quedan **visibles y con la compra deshabilitada** para revisión.
Se usa stock 0 para nuevas combinaciones y se conserva el stock existente. No se publica
el inventario ERP simultáneamente en Caja y Blíster. Los productos simples conservan su
estado comercial y su configuración de stock/PUM.

## Ejemplos

| Producto | Caja | Blíster/Sobre |
|---|---:|---:|
| Ketoprofeno 4520, con descuento existente del 10 % | $33.615 | $11.205 |
| Eutarpan 7159 | $48.000 | $4.800 |

- [Ketoprofeno Caja](http://192.168.0.229/droguera/4520-182-ketoprofeno-genfar-fraccion-10-tabletas-100mg-7702605101801.html#/50-presentacion-caja).
- [Ketoprofeno Blíster](http://192.168.0.229/droguera/4520-183-ketoprofeno-genfar-fraccion-10-tabletas-100mg-7702605101801.html#/58-presentacion-blister).
- [Eutarpan Caja](http://192.168.0.229/droguera/7159-142-eutarpan-x10mg-100-tabletas-7707019328622.html#/50-presentacion-caja).
- [Eutarpan Sobre](http://192.168.0.229/droguera/7159-143-eutarpan-x10mg-100-tabletas-7707019328622.html#/51-presentacion-sobre).

Ketoprofeno usa combinaciones 182 y 183; Eutarpan conserva 142 y 143. El impacto de
Sobre en Eutarpan pasó de +43.200 a **−43.200**. En Ketoprofeno el factor ERP es
0.33333333: el precio neto del blíster se conserva a seis decimales (12449.999876) y
la tienda lo redondea conforme a su moneda/descuento. El nombre comercial identifica
Caja de 30 tabletas y Blíster de 10; se conservó la URL histórica.

## Ejecución y evidencia

Se usaron `Product`, `Combination`, `AttributeGroup`, `ProductAttribute` y
`StockAvailable` con el contenedor Symfony instalado. La sincronización no modifica el núcleo ni el tema; las reparaciones posteriores de compatibilidad del tema se detallan abajo.
La comprobación posterior a establecer la combinación predeterminada necesitó desactivar
la caché de ObjectModel dentro del proceso CLI para leer los datos recién escritos.

El primer lote confirmó 18 productos y revirtió el producto 1751 al fallar esa comprobación.
Tras corregir el adaptador, un plan nuevo aplicó los 79 restantes. No se repitieron las
18 escrituras iniciales. El lote inicial contenía 97 productos distintos. Se añadieron las dos Furosemidas tras resolver sus nombres comerciales; el diario consolidado contiene ahora 99.

- [Diario consolidado](reports/clon311/aplicacion_completa.json).
- [Validación HTTP del selector](reports/clon311/validacion_http.json).
- [Estado final leído de PrestaShop](reports/clon311/estado_final.json).

Los CSV de autorización se preservan como `.csv.gz`, con sus bytes originales para
contrastar los hashes de los diarios. El CSV final es un informe de resultados y no debe
pasarse otra vez al comando `apply`.

Pasaron 33 pruebas Python, 10 pruebas heredadas Rust y 4 escenarios PHP con objetos
simulados; además se verificaron los precios reales del motor nativo al escribir cada
producto y las 146 respuestas del endpoint de actualización del selector.
La prueba HTTP de precios no ejecuta JavaScript. El usuario confirmó posteriormente que el precio cambia correctamente al seleccionar la presentación, después de reparar el tema. No se crearon carritos ni pedidos. El ciclo de reservas, facturas,
cancelaciones y notas crédito continúa pendiente de validación funcional ERP.

## Alcance protegido

No se accedió al clon 310 ni se modificó el template 309. No se conectó a
www.mercaboy.com. SQL Server 192.168.0.231 se utilizó únicamente con SELECT.
No se hicieron dumps por indicación del usuario; se cuenta con su protección Proxmox.
El archivo `/opt/2prestashopsync/.env` se conserva sin cambios.

El [script de cambio de IP](CAMBIO_IP.md) ya adaptó la tienda a 192.168.0.229 y permite
repetir la operación con otra IP privada previamente asignada al sistema.

## Reparaciones del escaparate en el clon 311

El tema personalizado usaba `product-variant` en singular, que no coincide con los
selectores nativos, y las tarjetas de recomendados compartían las clases del formulario
principal. `reparar_selector_tema.php` restauró los selectores en la ficha y separó las
clases de las tarjetas. Se conservaron las plantillas originales en
`reports/clon311/selector_tema_original`. El usuario confirmó visualmente el cambio de precio.

El aviso `Undefined` procedía de `wkcustomhyperlocal`: sin una dirección válida, su
plantilla AJAX devolvía solamente la cantidad y el botón, omitiendo el contenedor
`product-add-to-cart` esperado por el JavaScript nativo. Se instaló una personalización
bajo `themes/classic/modules/wkcustomhyperlocal/views/templates/hook/product-add-to-cart.tpl`.
Hereda la estructura del tema y conserva el bloque de cantidad y el botón deshabilitado
del módulo. No se editaron el núcleo ni los archivos originales del módulo.

Fuente reproducible: `theme_overrides/wkcustomhyperlocal/views/templates/hook/product-add-to-cart.tpl`.
Instalador limitado por UUID al clon 311: `php reparar_aviso_undefined.php --apply`
(sin `--apply` solo previsualiza). También limpia la caché de Smarty.
La comprobación específica del aviso se registra en `reports/clon311/aviso_undefined_http.json`
y `reports/clon311/aviso_undefined_navegador.json`; no se repitió la validación de precios.

Se utiliza el mecanismo documentado de personalización de módulos desde el tema:
https://devdocs.prestashop-project.org/8/themes/reference/overriding-modules/

## Furosemida: presentaciones incorporadas

Los productos 4479 y 4480 estaban bloqueados por nombres «Fracción» asociados al precio
de caja. La revisión de los nombres ERP y las presentaciones explícitas BLISTER, factor
0.1, permitió añadir mapeos comerciales en `settings.json`:

| Producto | ERP | Caja | Blíster | Precio visible Caja / Blíster |
|---|---|---|---|---|
| 4479 Furosemida MK 40 mg | 000333 / 990 | 300 tabletas | 30 tabletas | $90.900 / $9.090 |
| 4480 Furosemida Genfar 40 mg | 021228 / 995 | 100 tabletas | 10 tabletas | $21.600 / $2.160 |

Los precios visibles incluyen la promoción existente del 10 %. Se conservaron las URL
históricas y la correspondencia EAN. Ambas opciones quedan visibles con compra deshabilitada,
igual que las demás presentaciones en revisión. No se publicó stock ERP.

Evidencia: `reports/clon311_furosemida/aplicacion.json`, `validacion_http.json` (4 respuestas
correctas) y `selector_html.json` (Caja y Blíster presentes en las dos páginas).
El CSV único `reports/clon311/resultado_precios.csv` sustituye sus cuatro filas bloqueadas
por resultados aplicados. Los planes originales y autorizaciones comprimidas se conservan;
`plan_resultado_actualizado.json` sirve solamente para exportar el informe consolidado.
