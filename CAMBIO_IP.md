# Cambiar la IP de acceso a la tienda de pruebas

El script adapta PrestaShop y el sincronizador a una **IPv4 privada ya asignada al
servidor AlmaLinux**. Se ejecuta en el propio servidor; no cambia la conexión de red,
la puerta de enlace ni la sesión SSH. No consulta ni escribe en SQL Server.

Para la dirección actual:

```bash
cd /home/desa/sync-erp-prestashop
sudo python3 cambiar_ip.py 192.168.0.229 --apply
```

Para otro cambio, asignar primero la IP al sistema y sustituir el argumento:

```bash
sudo python3 cambiar_ip.py 192.168.0.230 --apply
```

Sin `--apply` muestra una vista previa. La dirección tiene que estar presente en una
interfaz local y pertenecer a una red privada IPv4. Se rechaza la IP ERP `192.168.0.231`.
Una IP incorrecta o aún no asignada se rechaza antes de modificar la tienda.

## Qué actualiza

- Dominio normal y SSL de la tienda 1 mediante `ShopUrl`.
- `PS_SHOP_DOMAIN` y `PS_SHOP_DOMAIN_SSL` mediante la API `Configuration`.
- Reglas `.htaccess` regeneradas por `Tools::generateHtaccess()`.
- Caché de plantillas Smarty que puede contener enlaces absolutos.
- `test_host` de `settings.json`, leído por Python y por el adaptador PHP.

El adaptador inicia también el contenedor Symfony de PrestaShop para que los hooks
de módulos como `ps_mbo` dispongan del contexto que requieren. No modifica esos módulos.

MySQL permanece en `localhost:3306`, base `mercaboy_pruebas`; `.env` y las claves se
conservan. Apache en esta instalación escucha sin fijar una IP, por lo que no necesita
reiniciarse ni editar sus archivos. El script no cambia certificados HTTPS, ajustes
personalizados de VirtualHost/Listen ni dominios públicos.

## Respaldo y comprobaciones

Antes de aplicar crea `reports/cambio_ip_FECHA_HORA/` con:

- `settings.json`: configuración anterior del conector, sin secretos.
- `htaccess.anterior`: reglas anteriores de la tienda.
- `estado.json`: dominios/configuración anteriores, estado de ejecución y resultado HTTP.

El cambio del dominio se hace en una transacción. Si falla antes del commit se revierte
la base y se restaura `.htaccess`. Si falla una comprobación posterior al commit, el diario
indica hasta dónde llegó: el cambio puede haber quedado aplicado. Corregir la causa y
repetir el mismo comando permite completar la configuración y su verificación.

Al terminar comprueba HTTP 200 y que el sincronizador pueda leer un producto en la nueva IP.
La comprobación HTTP no sigue redirecciones a otros servidores. No crea productos,
combinaciones, pedidos ni CSV de autorización comercial.

Los planes de productos anteriores conservan su IP y configuración originales. **Hay que
generar una auditoría nueva antes de aplicar productos**; no se alteran hashes ni autorizaciones
históricas para hacerlos pasar por válidos después de cambiar de servidor/dirección.

Para volver a una IP anterior, volver a asignarla a una interfaz del sistema y ejecutar
el script con esa dirección. Conservar el respaldo para diagnosticar cualquier configuración
personalizada de `.htaccess` que requiera revisión.
