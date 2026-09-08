# Presentaciones por blister: Ketoprofeno y Eutarpan

Fecha de revisión: 2026-09-07  
Ámbito: tienda de pruebas `192.168.0.186` y base `mercaboy_pruebas`.  
Acción realizada: **solo lectura**. Este documento no cambia productos, código ni base de datos.

## Conclusión

La solución adecuada en PrestaShop es una **combinación** por presentación
despachable, no una característica del producto ni un producto duplicado.

- Cada presentación vendible (Caja y Blister/Sobre) debe tener su propio
  `id_product_attribute`, referencia ERP, precio e inventario.
- PrestaShop estándar no convierte inventario entre una caja y sus blísteres.
  Por tanto, si el ERP almacena cajas pero la web vende blísteres, la
  conversión de cantidades y la reserva/descarga deben estar en la integración
  ERP, no solamente en MySQL.
- No se recomienda hacer estas altas con SQL directo. Deben crearse desde el
  Back Office, la API webservice o una integración que use los objetos/API de
  PrestaShop; luego se valida la sincronización ERP.

La documentación de PrestaShop establece que las variaciones de un producto
se modelan con atributos y combinaciones, y que cada combinación puede tener
su propia referencia, EAN, cantidad y efecto de precio. [Combinaciones de
PrestaShop 1.7](https://docs.prestashop-project.org/1.7-documentation/spanish/guia-usuario/vender/gestionar-catalogo/gestionar-productos)

## Datos de ERP observados en las capturas

| Producto | Referencia ERP | Contenido interno | Tabletas por blíster | Mínimo de venta |
|---|---:|---:|---:|---:|
| Ketoprofeno Genfar 100 mg | `100001749` | 30 tabletas | 10 | 10 |
| Eutarpan 10 mg | `026074` | 100 tabletas | 10 | 10 |

Interpretación propuesta:

| Producto | Presentación Caja | Presentación Blister/Sobre | Factor ERP |
|---|---:|---:|---:|
| Ketoprofeno | 30 tabletas = 3 blísteres | 10 tabletas | 3 blísteres por caja |
| Eutarpan | 100 tabletas = 10 blísteres | 10 tabletas | 10 blísteres por caja; fracción ERP `0,1` |

> Para Eutarpan queda confirmada la fracción ERP `0,1`: un Sobre/Blister de
> 10 tabletas equivale a la décima parte de una Caja de 100. El precio de
> blíster se calcula como `precio_caja × 0,1`, salvo que el ERP suministre una
> regla comercial distinta.

## Estado actual comprobado

### Producto 4520 — Ketoprofeno

- Producto: `4520`.
- Nombre actual: **Ketoprofeno Genfar Fracción 10 Tabletas 100mg**.
- Referencia actual: `977`; EAN-13: `7702605101801`.
- Precio base sin impuesto: `$37.350`.
- Atributo/combinación predeterminada: `0`: actualmente **no tiene
  combinaciones**.
- Tiene un precio específico global de 10 % de descuento (`id_specific_price`
  `53711`). En el front se observa $37.350 tachado y precio efectivo $33.615.

Para que se pueda escoger y despachar blíster, se debe convertir a “Producto
con combinaciones” y crear el grupo **Presentación** con, como mínimo:

| Combinación | Contenido | Precio base propuesto | Impacto sobre el precio padre $37.350 |
|---|---:|---:|---:|
| Caja | 30 tabletas | $37.350 | $0 |
| Blister / Sobre | 10 tabletas | $12.450 | **-$24.900** |

Con el descuento específico actual de 10 %, los precios visibles esperados
serían $33.615 y $11.205 respectivamente. Si el ERP define otro precio para
blíster, se conserva Caja como base y se calcula el impacto como
`precio_blister_sin_impuesto - 37.350`.

La referencia de la combinación de blíster debe ser **propia y estable**
(por ejemplo, una referencia ERP que el ERP entregue para la fracción; no se
debe inventar ni reutilizar el EAN de la caja). Esa referencia será la llave de
sincronización recomendada.

### Producto 7159 — Eutarpan

El borrador ya existe y confirma el modelo técnico correcto, pero su precio es
incorrecto.

| `id_product_attribute` | Presentación | Impacto actual | Precio resultante actual |
|---:|---|---:|---:|
| 142 | Caja | $0 | $48.000 |
| 143 | Sobre | **+$43.200** | **$91.200** |

El producto padre tiene precio base $48.000 y el ERP define que 10 tabletas
son una fracción **`0,1`** de la caja de 100. Por tanto **Sobre** debe costar
`$48.000 × 0,1 = $4.800`; el impacto correcto de la combinación es
**-$43.200**, no `+$43.200`.

PrestaShop no almacena un factor de fraccionamiento en
`ps_product_attribute.price`: ese campo guarda un **impacto monetario
absoluto**. El factor `0,1` debe ser un dato del ERP/conector (o de una tabla
de mapeo propia) para convertir precio y stock; en PrestaShop se refleja con
el impacto `-43200.000000` para este precio padre.

La combinación 142 (Caja) es la predeterminada. Ambas combinaciones están en
el grupo `Presentación`, atributos `Caja` y `Sobre`, por lo que no hay que
crear nuevamente ese grupo. Se debe completar para cada una la referencia ERP
distinta, la política de stock y el precio validado por ERP.

## Cambios funcionales necesarios

1. Confirmar con farmacia/ERP el nombre comercial para la unidad fraccionada:
   **Blister** es más preciso que “Sobre” cuando se venden 10 tabletas; se
   puede conservar “Sobre” solo si así lo exige el ERP o el cliente.
2. Confirmar referencia/código ERP, EAN si existe, precio de venta, costo e
   impuesto para cada presentación. No usar el EAN de una caja como EAN de un
   blíster salvo que el fabricante lo asigne explícitamente.
3. En Back Office, crear o reutilizar `Presentación: Caja` y
   `Presentación: Blister` y crear una combinación por cada unidad vendible.
4. Definir Caja como combinación predeterminada si la URL/nombre del producto
   representa la caja; si el negocio quiere priorizar el fraccionado, usar
   Blister como predeterminada y ajustar nombre, texto y SEO para que no sea
   engañoso.
5. Asignar el precio mediante **impacto de combinación**, no mediante un
   descuento específico, cuando la diferencia es permanente por presentación.
   Los precios específicos se reservan para descuentos temporales o por
   cliente/grupo; PrestaShop permite ligarlos a una combinación concreta.
6. Configurar la cantidad mínima de cada combinación en `1` para que el
   cliente compre un blíster por vez. El dato ERP “venta mínima de pastas: 10”
   ya coincide con un blíster de 10 tabletas; no significa mínimo 10 blísteres.
7. Sincronizar existencia por combinación y probar: selector, precio,
   disponibilidad, carrito, pedido, nota de crédito y exportación al ERP.

## ¿Solo MySQL? No

Los datos nativos de catálogo se persisten en MySQL, pero la solución completa
no es exclusivamente una modificación de MySQL:

| Capa | Necesidad |
|---|---|
| Back Office/API de PrestaShop | Crear y editar combinaciones de forma soportada; invalidar cachés y mantener multi-tienda. |
| MySQL | Guarda atributos, combinaciones, impactos de precio, referencias y existencias. |
| Integración ERP | Debe reconocer la referencia de combinación y convertir unidades Caja ↔ Blister cuando el ERP no guarda stock por blíster. |
| Código/módulos | Puede requerir ajuste si el conector exporta solo `id_product`/referencia padre y omite `id_product_attribute`. |
| Front-end | No requiere cambio para el selector estándar; solo texto/tema si se desea llamar “Blister” en lugar de “Sobre”. |

La documentación técnica de PrestaShop indica que el stock real de productos y
combinaciones reside en `StockAvailable`; los campos `quantity` duplicados de
producto/combinación son de compatibilidad y no deben ser la fuente de
sincronización. [FAQ oficial de stock](https://devdocs.prestashop-project.org/9/faq/stock/)

También se puede crear combinaciones y actualizar su stock mediante el
webservice de PrestaShop, evitando SQL directo. Al crear una combinación, se
crea su entidad de stock correspondiente. [Guía oficial de webservice para
combinaciones](https://devdocs.prestashop-project.org/8/webservice/tutorials/create-product-az/)

## Tablas MySQL involucradas

Prefijo observado: `ps_`. En multi-tienda debe filtrarse y completarse
correctamente `id_shop=1`.

| Finalidad | Tablas principales |
|---|---|
| Grupo y valores de atributo | `ps_attribute_group`, `ps_attribute_group_lang`, `ps_attribute_group_shop`, `ps_attribute`, `ps_attribute_lang`, `ps_attribute_shop` |
| Combinación | `ps_product_attribute`, `ps_product_attribute_shop`, `ps_product_attribute_combination`, opcionalmente `ps_product_attribute_image` |
| Producto padre/por tienda | `ps_product`, `ps_product_shop`; actualizar el atributo predeterminado solo mediante PrestaShop |
| Inventario | `ps_stock_available` con `id_product_attribute` de cada combinación |
| Precio/promoción | Impacto permanente en `ps_product_attribute.price`; descuentos por combinación en `ps_specific_price` si fueran necesarios |
| Proveedor/costo por presentación | `ps_product_supplier` si se sincroniza costo o referencia de proveedor por combinación |
| Pedido ya creado | `ps_cart_product`, `ps_order_detail` y tablas de movimientos: PrestaShop las llena automáticamente; no se tocan para crear el catálogo |

Evitar `INSERT`/`UPDATE` manual: faltas en tablas `*_shop`, combinación de
atributos, caché del producto, búsqueda/indexación o stock pueden dejar el
front y el ERP en estados distintos.

## Integración ERP: requisito decisivo

PrestaShop mantiene existencias separadas: una Caja no descuenta
automáticamente blísteres y un Blister no descuenta automáticamente una Caja.
Para Ketoprofeno, si el ERP solo dispone de `cajas`, el conector debe aplicar
un factor de 3; para Eutarpan, uno de 10. Debe decidirse una de estas
estrategias antes de activar ventas:

1. **ERP maneja cada presentación como SKU propio**: opción preferida. El
   conector mapea `referencia_combinación → SKU ERP` y copia precio/stock sin
   conversión.
2. **ERP solo maneja cajas**: el conector calcula el stock publicable de
   blísteres y al recibir un pedido de blíster descuenta/reserva la fracción
   correcta. Debe prevenir ventas simultáneas que vendan más blísteres que los
   contenidos en las cajas disponibles.
3. **Inventario web por blíster y ERP por caja**: requiere un registro de
   conversión/auditoría externo; no debe intentar “compartir” la misma fila de
   `ps_stock_available` entre combinaciones.

En la instalación revisada solo se identificaron como activos
`productsexportpro` y `mercaboyexportclientes`; no se encontró evidencia de un
módulo nativo de entrada/sincronización ERP para estas combinaciones. Se debe
revisar el proceso externo que consume o envía datos antes de publicar.

## Plan de prueba antes de producción

1. Clonar la BD/archivos actuales y ejecutar los cambios únicamente en
   `mercaboy_pruebas`.
2. Crear Ketoprofeno con Caja y Blister; corregir Eutarpan Sobre a su precio
   ERP confirmado.
3. Ejecutar una sincronización de prueba y comprobar que recibe
   `id_product_attribute` y la referencia de combinación, no solo el padre.
4. Simular compra de una caja y de un blíster; validar precio, factura, stock,
   línea de pedido y SKU recibido por ERP.
5. Validar cancelación/reembolso y sincronización inversa de stock.
6. Solo entonces repetir mediante Back Office/API en producción.
