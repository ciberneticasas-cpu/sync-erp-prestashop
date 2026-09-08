# Sincronización ERP → PrestaShop de pruebas, versión 2

Programa ejecutable en AlmaLinux 8, con la instalación **PrestaShop 8.1.7 / PHP 8.1** de
`192.168.0.229` (clon Proxmox 311), raíz `/var/www/html`, base **mercaboy_pruebas**, tienda **1**.
No usa Docker ni BigQuery. La sincronización utiliza objetos nativos. Las correcciones de compatibilidad del tema se documentan por separado en `RESULTADO.md`.

El flujo es **auditar → revisar un CSV → aplicar productos autorizados → verificar**.
Se aplicaron 99 productos autorizados en el clon 311 y se verificaron 150 respuestas de precio del escaparate. El clon 310 (`192.168.0.228`) permanece fuera del alcance. Véase `RESULTADO.md`.

## Componentes

| Archivo | Responsabilidad |
|---|---|
| `sync.py` | Planificador decimal, equivalencias, correspondencias ERP, CSV, autorización, validación y simulaciones. Python 3.6+, biblioteca estándar. |
| `src/main.rs` | Lector SQL Server/TDS; únicamente consultas SELECT hacia `192.168.0.231`. |
| `src/legacy.rs` | Funciones heredadas de interpretación de empaques, incluidos sus diez tests. |
| `bridge.php` | Adaptador CLI a los objetos nativos `Product`, `Combination`, `AttributeGroup`, `ProductAttribute`, `StockAvailable`. |
| `settings.json` | Rutas, almacenes y propuestas de mapeo, sin secretos. |

La lectura MySQL de auditoría usa una transacción `READ ONLY`. Las escrituras de catálogo
usan objetos de PrestaShop: el SQL ejecutado directamente por el adaptador de escritura se
limita a control de transacciones. El adaptador nunca debe copiarse al directorio público.

## Credenciales y destinos

Se conserva **sin modificar** `/opt/2prestashopsync/.env` y sus claves:

- `MARIADB_HOST`, `MARIADB_PORT`, `MARIADB_USER`, `MARIADB_PASSWORD`, `MARIADB_DATABASE`.
- `erp_host` o `MERCABOY_ERP_HOST`, `MERCABOY_ERP_DATABASE`, `MERCABOY_ERP_USER`,
  `MERCABOY_ERP_PASSWORD`, `MERCABOY_ERP_PORT`.

No se hereda el destino MySQL de producción. Si el `.env` describe explícitamente
`mercaboy_pruebas` en un host local permitido, se reutilizan su usuario y contraseña para
lectura. En caso contrario, se usan las credenciales nativas de
`/var/www/html/app/config/parameters.php`, verificando primero host y nombre de base.
Los objetos de PrestaShop siempre usan esa configuración nativa local.

También se verifican la interfaz local indicada en `settings.json:test_host`, los dominios de la tienda y el
contexto de tienda 1. No existe un interruptor `ALLOW_PRODUCTION_APPLY` ni una opción
para habilitar producción. `www.mercaboy.com` no se consulta ni se modifica.

El lector ERP conserva el modo TDS del conector anterior en esta LAN y solo contiene
consultas SELECT fijas; no permite introducir SQL arbitrario. No da de alta productos,
pedidos, reservas, devoluciones ni movimientos en SQL Server. Las credenciales existentes
pueden tener más permisos en el servidor: esta versión no cambia usuarios ni permisos.

Los almacenes predeterminados son `001`, `002`, `003`, como en el programa anterior.
Se incluyen en la instantánea y en la configuración del plan; revisar si corresponden al
inventario que se desea analizar. El stock calculado es informativo, no se publica.

## Ejecutar una auditoría

Desde esta carpeta:

```bash
cargo build --offline
python3 sync.py audit --output reports/mi_revision
```

La compilación ya se realizó en este servidor. `Cargo.lock` fija las versiones utilizadas.
En otra instalación, `cargo build --locked` necesita acceso al registro si faltan dependencias.

Un piloto:

```bash
python3 sync.py audit --product 4520 --product 7159 --output reports/mi_piloto
```

Sin filtros se analizan productos activos. Con `--product` se incluyen los identificadores
indicados aunque estén desactivados, para revisar borradores después de aplicarlos.
Cada ejecución exige una carpeta de salida nueva y produce **un solo CSV**:

- `revision.csv`: propuestas, bloqueos y equivalencias omitidas. Todas las autorizaciones nacen en `NO`.
- `plan.json`: cambios exactos, estado anterior y configuración para ejecutar/verificar.
- `snapshot.json`, `erp.json`: evidencia técnica sin contraseñas; incluye estructura ERP y listas de precios.

Los productos simples sin diferencias no agregan filas al CSV. Los archivos JSON evitan
crear CSV auxiliares para datos técnicos. La auditoría imprime el SHA256 del plan.

## Reglas comerciales

1. **Precio simple**: `precio ERP sin IVA × factor heredado de empaque`.
   Se mantienen el parser anterior, el nombre corto ERP cuando corresponde, las reglas
   de kilos y los casos especiales cubiertos por sus tests. Primero se usa `Producto.valor`;
   si es NULL, se usa `ListaPrecio.Lista=1`, igual que antes. Una lista 1 ambigua se bloquea.
   Se mantienen stock, promociones y configuración PUM; no se implementa una nueva sincronización PUM.
2. **Presentaciones**: cada presentación despachable usa una combinación. Su precio es
   `base sin IVA + impacto monetario`. El impacto es `precio presentación − base`, incluido
   un valor negativo para el blíster. `PrecioDesdePrincipal=1` aplica el factor al precio
   padre ERP; cuando es 0 se usa el precio comercial explícito de la presentación.
3. **Equivalencias**: igual factor e igual precio a seis decimales significa una sola opción.
   Caja/Paquete equivalentes se omiten. Igual precio con distinto factor se bloquea para
   revisión; no se crea automáticamente otra presentación. Factor 1 con precio distinto
   sí puede representar una oferta distinta. No se borran combinaciones existentes.
4. **Correspondencia ERP**: se normalizan ceros iniciales en claves numéricas. Se cruzan
   referencia y EAN; un EAN puede desambiguar referencias repetidas. Si ambos identifican
   productos distintos, se bloquea. Un mapeo explícito `erp_id` permite resolver un caso revisado.
5. **Referencias de combinación**: `reference_strategy=erp_tuple` propone claves técnicas
   basadas en claves ERP reales: `026074:BASE`, `026074:1414`. **No son SKU comerciales ni
   EAN asignados por el ERP/fabricante**. La correspondencia con ProductoId/PresentacionId
   queda en el plan y en el resultado de aplicación, y `order-preview` la utiliza.
   Se conservan referencias existentes distintas; las vacías/repetidas reciben una propuesta
   técnica. El CSV identifica su origen. Para exigir referencias comerciales confirmadas,
   establecer `reference_strategy` en `require_confirmed` y completar los mapeos.
6. Se reutilizan Caja y Sobre/Blíster existentes. No se renombran atributos globales, no se
   inventan EAN, no se reasignan imágenes de combinaciones existentes y se usa mínimo 1.
7. Ketoprofeno tiene una propuesta explícita de nombre comercial que menciona Caja de 30
   y Blíster de 10; se muestra en el CSV. Otros nombres que dicen «Fracción» requieren mapeo
   antes de convertirlos, para no vender una caja con un nombre de fracción.

Se conservan los impuestos y precios específicos configurados en PrestaShop. La conversión
del IVA ERP mantiene la interpretación heredada (19, 0.19 y 1.19). No es una auditoría fiscal
del ERP ni modifica grupos de impuestos. El motor nativo vuelve a comprobar los importes;
precios específicos fijos u otras reglas que impidan la diferencia esperada pueden detener
la aplicación de un producto antes de confirmar su transacción.

## Revisar y aplicar

**La configuración actual usa `presentation_mode=visible_preview`: las presentaciones quedan visibles con la compra deshabilitada.** Sin ese modo, las presentaciones se desactivan como borradores. Las combinaciones nuevas
tienen stock 0; el stock existente se conserva. El CSV muestra `activo_destino`, `disponible_para_pedido_destino` y `stock_a_escribir`. La actualización de precio simple conserva su estado activo.

1. Abrir `revision.csv` importando referencias como **texto**, para preservar ceros.
2. Cambiar únicamente `autorizar` de `NO` a `SI` en filas `PROPUESTO` elegidas.
3. Autorizar todas las filas propuestas de un producto o ninguna. No autorizar bloqueos.
4. Conservar nombres, precios, orden y número de filas. Los cambios comerciales se hacen
   en `settings.json` y requieren generar otra auditoría.
5. Calcular el SHA del CSV revisado y usar el SHA del plan impreso por `audit`:

```bash
sha256sum reports/mi_revision/revision.csv
python3 sync.py apply \
  --plan reports/mi_revision/plan.json \
  --csv reports/mi_revision/revision.csv \
  --plan-sha256 SHA_DEL_PLAN_IMPRESO_POR_AUDIT \
  --approved-csv-sha256 SHA_DEL_CSV_REVISADO
```

No ejecutar este ejemplo con el CSV actual en `NO`. La autorización no se infiere de
marcar una fila como propuesta. El programa exige ambos hashes y compara todas las
columnas con el plan, excepto `autorizar`.

El plan vence a las 24 horas como máximo. Antes de escribir se releen ERP y PrestaShop y
se rechazan cambios del catálogo, precio o factor respecto de la instantánea. Las variaciones de cantidad ERP se toleran en este lote de precios porque no publica existencias ERP. Hay un bloqueo
local para evitar dos aplicaciones simultáneas del conector. No bloquea ediciones concurrentes
del Back Office durante todo el lote: ejecutar la aplicación en una ventana sin edición de catálogo.

Se guarda `aplicacion.json` antes de empezar y después de cada producto. La transacción es
**por producto**, no por lote. Si un producto falla, los anteriores ya confirmados permanecen
aplicados. Se verifica precio padre, impactos, referencias, mínimo, predeterminada, borrador,
stock escrito y diferencias del precio visible mediante `Product::getPriceStatic()`.
El adaptador revierte la transacción del producto si falla la verificación. Los efectos
externos de hooks de terceros, si los hubiera, no forman parte del rollback MySQL.

Un plan intentado no se reutiliza. Ante interrupción se revisa `in_progress` en el diario y
se genera un plan nuevo: no se reintenta a ciegas un alta. La auditoría posterior de los IDs
desactivados reconoce las combinaciones existentes y omite las que ya coinciden.

```bash
python3 sync.py verify --journal reports/mi_revision/aplicacion.json
```

Esto genera `validacion.json`, sin otro CSV. Además de pruebas con dobles en memoria, la ruta de escritura se ejecutó y verificó en 97 productos del clon 311.

## Inventario compartido y exportación de pedidos

PrestaShop no convierte automáticamente Caja ↔ Blíster. Publicar simultáneamente una caja
y todos sus blísteres como existencias independientes duplica la disponibilidad.

Esta versión no publica stock ERP. En el modo `visible_preview`, activa la visibilidad de las presentaciones y deshabilita su compra. Incluye
dos herramientas de evaluación, sin escritura:

```bash
python3 sync.py stock-preview --allocation examples/stock.json
python3 sync.py order-preview \
  --journal reports/mi_revision/aplicacion.json \
  --lines examples/order-lines.json
```

`stock-preview` valida que `Σ(cantidad × factor) + reservas ≤ inventario ERP`.
El ejemplo reparte dos cajas equivalentes: una caja, siete blísteres y reserva de 0.3 cajas.
No calcula reservas reales ni comparte stock entre combinaciones en tiempo real.

`order-preview` convierte líneas JSON con `product_id`, `product_attribute_id`,
`product_reference` y `product_quantity` usando un diario aplicado y verificado. Tres sobres
de Eutarpan equivalen a 0.3 cajas ERP. Rechaza referencias o combinaciones sin correspondencia.
El archivo de ejemplo sirve para probar el formato, no acredita un pedido real. Para pedidos
históricos se necesita el mapeo vigente al crearlos; no se debe usar automáticamente el último
factor comercial para reinterpretar pedidos anteriores.

Se validaron 146 respuestas AJAX del selector de precios. Queda pendiente la revisión humana en navegador/Back Office, precio en carrito, pedido/factura, consumidor real de exportaciones, reservas,
cancelaciones y notas crédito. SQL Server seguirá en lectura: los movimientos se evaluarán
sin registrarlos mientras se mantenga esa restricción. No se puede declarar validado el ciclo
de venta completo con pruebas del precio del catálogo o una simulación JSON.

## Pruebas

```bash
cargo test --offline
python3 -m unittest discover -s tests -v
php tests/test_bridge.php
php -l bridge.php
```

Hay 10 pruebas heredadas Rust, 33 pruebas Python y 4 escenarios PHP con objetos simulados.
Se cubren impactos negativos, precio comercial explícito, IVA, equivalencias, referencias
ambiguas, hashes, autorización parcial, idempotencia, inventario compartido, conversión de
pedidos, preservación de imágenes, altas nativas y rollback de una validación fallida.

## Fundamento PrestaShop

Decisiones contrastadas con el código instalado 8.1.7 y la documentación oficial:

- [ObjectModel y contexto de tienda](https://devdocs.prestashop-project.org/8/development/components/database/objectmodel/).
- [Combinaciones y sus campos](https://devdocs.prestashop-project.org/8/webservice/resources/combinations/).
- [Creación de productos, atributos, combinaciones y existencias](https://devdocs.prestashop-project.org/8/webservice/tutorials/create-product-az/).
- [StockAvailable como fuente de existencias](https://devdocs.prestashop-project.org/8/faq/stock/).

El adaptador local usa los mismos objetos del catálogo, sin automatizar clics del Back Office
ni requerir una clave webservice. El navegador y los módulos instalados siguen siendo parte
de la validación funcional pendiente del piloto.

## Cambio de IP e informes finales

Ver `CAMBIO_IP.md`: `sudo python3 cambiar_ip.py NUEVA_IP --apply`. La IP debe estar asignada primero al sistema.

`validar_tienda.py` valida la respuesta HTTP que usa el selector, sin crear carritos ni pedidos. `exportar_resultado.py` combina propuestas, escrituras efectivas y enlaces en un CSV final. La ejecución del clon 311 está en `reports/clon311/resultado_precios.csv`; los CSV de autorización originales se conservan comprimidos como `.csv.gz`. No se debe pasar el CSV final a `apply`.

Por instrucción del usuario no se hacen dumps: se cuenta con el template Proxmox 309, el clon 310 sin cambios y sus respaldos periódicos. Los JSON locales guardan evidencia de las operaciones; no son un backup completo de la base.
