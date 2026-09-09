# Precios visibles y comparación entre clones — 9 de septiembre de 2026

Se ejecutó `sincronizar.py --apply --evidence` en `.229`, usando `.227` como origen
congelado y `.231` como ERP. Evidencia en `reports/precios_visibles_aplicados_final/`.

El Excel comienza por referencia, nombre PS, nombre corto ERP, factor, presentación,
precio visible .227, precio visible .229 y diferencia .229 menos .227. Cada pestaña
ordena las fichas por su mayor diferencia absoluta, de mayor a menor, conservando
signo, filas contiguas y presentación BASE primero. Sin comparación, la ficha va al final.

## Qué precio se compara

`precio_mariadb` y `precio_para_prestashop` son importes sin impuestos. Los campos
visibles se calculan con `Product::getPriceStatic`, incluyendo impuestos, descuentos
y reglas específicas para visitante sin sesión, cantidad 1, moneda y país predeterminados.

El pronóstico cambia solamente los precios de la caché en memoria del lector nativo
8.1.7 y reutiliza el cálculo de impuestos/descuentos; no hace UPDATE ni crea productos.
El lector ejecuta las consultas del motor dentro de una transacción READ ONLY. A `.227`
se envían solo las funciones de lectura y bootstrap, sin el escritor ni funciones apply.
Después del lote se inicia otra lectura del motor en `.229` y se compara con lo previsto.

Las combinaciones se emparejan por atributos entre clones. Si falta la presentación
original, se dejan vacíos precio inicial y diferencia. La BASE creada sobre un producto
antes simple usa el precio base original. Esto permite mostrar diferencias históricas
sin confundirlas con escrituras nuevas de la corrida.

## Resultado real

- Ejecución completa: 52,836 segundos, Excel de 3400108 bytes, doce pestañas y 11229 filas.
- 5227 filas con precio visible verificable: todas coinciden con el pronóstico.
- 167 filas sin presentación existente comparable en el destino; no se inventa un precio.
- Frente a `.227`: 63 filas bajaron, 78 subieron y 5019 permanecen iguales. Las restantes
  verificadas no tienen presentación comparable en el origen congelado.
- Cero cambios nuevos de precio/PUM: los productos elegibles ya estaban sincronizados.
  El diario de aplicación registra SIN_CAMBIOS y el CSV de cambios no tiene filas.
- Continúan los cuatro productos bloqueados previamente; el comando devuelve 2 por esas
  incidencias preexistentes, no por discrepancias de los precios visibles.
- Se comprobó por lectura completa que tanto el origen congelado como el catálogo de
  destino siguen iguales a sus snapshots previos en esta corrida sin cambios.

## Comprobación de páginas

Se consultó el HTML público de seis URLs, incluyendo variantes de Furosemida y las fichas
Ciruela y Floratil. El `current-price-value` coincide con el motor en las variantes existentes:

| Producto/presentación | .227 | .229 | Diferencia comparable |
|---|---:|---:|---:|
| Furosemida, base/caja | 21600 | 20340 | -1260 |
| Furosemida, blister | No existe | 2034 | Sin comparación |
| Ciruela, ficha simple | — | 12000 | — |
| Floratil 10 cápsulas, ficha simple | — | 76950 | — |

En `.227`, solicitar el ID de blister de `.229` devuelve la ficha simple y su precio
21600. Se verificó que `.227` no tiene combinaciones para Furosemida: ese importe no
se asigna al blister en el Excel. Una URL que responde no prueba que exista la variante.

Una simulación adicional sin escrituras, con precio base 30000 e impacto de blister
-27000, produjo 27000 y 2700 respectivamente: el motor conservó el descuento del 10%.

## Validaciones

- 65 pruebas Python del sincronizador y 38 del preparador correctas.
- Pruebas PHP del escritor y sintaxis del nuevo lector correctas.
- Lectura completa del XLSX con openpyxl: columnas en orden, precios numéricos, fórmulas
  de diferencia comprobadas numéricamente, fichas sin duplicar entre pestañas, grupos
  contiguos y orden por diferencia absoluta comprobado.
- Pruebas de atributos con IDs diferentes entre clones, alternativas nuevas sin precio
  inventado, diferencia histórica distinta del cambio de corrida y detección de discrepancias.

El cron permanece pausado. Producción no se utilizó.
