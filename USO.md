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
  precio base, el impacto o el precio de presentación. Solo cabecera si no hubo cambios.
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

El PUM usa `unit_price` más `unit_price_impact` nativos, sin dividir otra vez por el
contenido de la caja. Se conserva ese precio unitario y su unidad; esta versión no
recalcula el PUM comercial desde el ERP. `pum_ratio` es el valor previo almacenado y
`pum_ratio_final` registra el derivado por PrestaShop al guardar un precio. PrestaShop 8
recalcula ese campo de compatibilidad automáticamente; no es una cantidad que publique
el sincronizador. Un PUM comercial incorrecto de origen requiere una revisión separada.

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
la adaptación de rutas/permisos y las políticas de baja, stock y PUM comercial pendientes
son parte de la preparación para producción.
