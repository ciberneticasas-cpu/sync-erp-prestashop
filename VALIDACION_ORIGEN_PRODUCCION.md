# Validación de origen productivo y destino de pruebas — 2026-09-09

La sincronización consulta directamente `www.mercaboy.com/mercaboy_2024/1` y escribe
únicamente en `192.168.0.229/mercaboy_pruebas/1`. La conexión usa el archivo `.env`
externo de `/opt/prestashopsyncConsultaMariaDB`, cuyo `cargo run` se ejecutó correctamente.
No se importó una copia de la base ni se ejecutó PHP o SSH en producción.

## Lectura y cálculo

El adaptador configura y comprueba `SET SESSION TRANSACTION READ ONLY`, mantiene
los datos iniciales y sus precios en una misma transacción con vista consistente,
y admite solamente las consultas de lectura previstas. Las pruebas de rechazo de
SQL de escritura se realizan sin conexión, antes de poder enviar SQL al servidor.
El dominio productivo está permitido como origen y rechazado como destino.

La cuenta existente conserva permisos amplios: la protección de este programa se
aplica en la sesión, la transacción y el adaptador; no procede de una cuenta limitada
a SELECT. El transporte directo no usa TLS, igual que el programa de consulta existente.
No se cambiaron cuentas, permisos ni configuración del servidor productivo.
Producción es un origen vivo; la vista consistente corresponde a cada corrida.

Los precios se calculan con las clases locales del motor PrestaShop 8.1.7 y los datos
leídos directamente del origen. No se ejecutan módulos del origen: si un hook activo
interviene en el cálculo, la lectura se detiene para revisión. La comparación entre
consultas originales y optimizadas coincidió en los 39 precios de 20 productos revisados.
La página pública del Pepino mostró $2.250, coincidente con el cálculo del origen.

La lectura completa de prueba obtuvo 5.092 fichas y 5.207 precios en 18,12 segundos.
La corrida aplicada registró 164 SELECT, un EXPLAIN SELECT, una consulta SHOW GRANTS
y el inicio de la transacción de lectura, además de su configuración de sesión y rollback.

## Aplicación y libro

Evidencias locales, excluidas de Git:
`reports/aplicacion_origen_produccion/`.

- Libro: `stock_auditoria_20260909_181410_374847.xlsx`.
- Duración de la corrida: 72,833 segundos; 5.087 productos del destino evaluados.
- Cambio aplicado y verificado: referencia 23654, producto 7301, Doña Gallina Cubo
  × 8 unidades, de $3.800 a $3.850; también se actualizó su PUM.
- Cero errores del escritor; 5.227 verificaciones de precio visible y técnico coincidentes.
- 167 filas sin precio verificable corresponden a casos sin presentación existente
  equivalente; no se inventa un precio para esos casos.
- 37 fichas bloqueadas: 32 inactivas en el destino, una sin ficha en el origen y cuatro
  correspondencias ERP que requieren revisión. No se activaron ni crearon productos.
  El resultado global conserva `all_resolved=false` y salida 2 por estos bloqueos.
- Excel de 14 pestañas y 11.122 filas de datos. Las columnas visibles identifican
  `precio_visible_origen` y `precio_visible_destino`.
- Se conserva la compactación de 113 filas redundantes de atributos sin impacto
  de precio en 41 productos. El detalle original de auditoría no se modifica.
- Repollo: una fila KL, $8.600 en origen y destino, diferencia $0.
- Pepino: una fila KL, $2.250 en origen y $1.950 en destino, diferencia −$300.
- Relectura del destino: nombres, referencias, existencias, estados y estructura de
  atributos conservados en las 5.087 fichas; solo se excluyeron precio y PUM al comparar.

`validacion_origen_produccion.json` contiene la comprobación independiente del XML
 del Excel, elegibilidad del plan, estructura del catálogo y evidencia de lectura.
El cron sigue pausado.

## Pruebas

83 pruebas Python del sincronizador y 38 del preparador aprobadas. También pasan las
pruebas PHP del escritor, del origen protegido y del preparador. La validación sobre
el lote aplicado comprueba precios y preservación de los campos ajenos al cambio.
