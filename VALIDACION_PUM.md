# Regla ERP/nombre del PUM — 8 de septiembre de 2026

Aplicada en `192.168.0.229/mercaboy_pruebas/1`, consultando el ERP `.231` solo por
lectura. Producción no se ha utilizado. La configuración del cron se trasladó a
`/home/desa/mercaboy-precios-pruebas.cron.pausado`; permanece fuera de `/etc/cron.d`.

## Resultados

- 33 pruebas Python del sincronizador y sus pruebas PHP nativas con dobles: correctas.
- 37 pruebas Python y pruebas PHP del preparador: correctas, ejecutadas desde su
  directorio y sin el bloqueo ocupado por una sincronización.
- Piloto en ocho fichas y aplicación general: ninguna escritura fallida.
- Aplicación general: 2115 productos en 128,504 segundos. Se aplicaron después los
  últimos casos de lectura de concentraciones, sobres y cantidades adicionales.
- Auditoría final: 5087 fichas, 4487 elegibles sin cambios pendientes; 211 inactivas,
  385 excluidas por fuente ERP y los cuatro bloqueos de correspondencia preexistentes
  (4193, 5133, 7150, 7746). Duración: 7,669 segundos.
- Comparación completa de las 5087 fichas antes/después: no cambiaron campos ajenos
  a precio, unidad/PUM, ratio nativo e impactos de precio/PUM. Incluye existencias,
  nombres, publicación, referencias, atributos y número de combinaciones.

La auditoría final identificó 1832 coincidencias ERP/nombre, 366 discrepancias que
usan el nombre, 1957 contenidos tomados solo del nombre, 15 del ERP sin contenido
interpretable en el nombre y 317 valores por defecto. Diez nombres requieren revisión
por contener cantidades ambiguas; quedan señalados en `pum_observacion`.

No se declara el catálogo entero resuelto: los cuatro bloqueos conservan su estado.
La repetición no vuelve a proponer cambios de PUM ya aplicados.

## Navegador real

Chrome contra el clon, con accesos externos bloqueados y cambio real de presentación:

| Producto | Presentación | Precio visible | PUM visible |
|---|---|---:|---:|
| Ciruela 2830 | 500 gr | 12000 | 24 Gramo |
| Furosemida 4480 | Caja | 20340 | 203 Unidad |
| Furosemida 4480 | Blíster | 2034 | 203 Unidad |
| Eutarpan 7159 | Caja | 48000 | 480 Unidad |
| Eutarpan 7159 | Blíster | 4800 | 480 Unidad |
| Bedoyecta 7174 | Caja | 72000 | 72000 Unidad |
| Bedoyecta 7174 | UNIDAD | 24000 | 24000 Unidad |

No apareció «Undefined». Furosemida tiene descuento visible y el escaparate redondea
su PUM de 203,4 a 203. Bedoyecta no tiene contenido PUM en el ERP ni cantidad en el
nombre de PrestaShop: la regla solicitada usa una unidad vendida en cada presentación.

## Evidencia local

Los informes no se suben a Git:

- `reports/pum_regla_piloto/`: primera aplicación y observación web `web.json`.
- `reports/pum_regla_aplicacion/`: auditoría, cambios y recibos de aplicación general.
- `reports/pum_regla_verificacion/`: últimos ajustes de lectura del nombre.
- `reports/pum_regla_final/`: auditoría sin propuestas e `integridad.json`.

Para repetir en el clon: `python3 -m unittest discover -s tests -q`,
`php tests/test_bridge.php` y `python3 sincronizar.py --evidence`.
La interpretación exacta y las columnas están documentadas en `USO.md`.
