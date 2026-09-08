# Ensayo de separación — 8 de septiembre de 2026

Destino aplicado: **192.168.0.229**, base local `mercaboy_pruebas`. Se consultaron `.227`
y `.228` como referencias; no se modificó su catálogo ni producción. El ERP `.231` solo
recibió SELECT.

| Comprobación | Resultado |
|---|---|
| Catálogo completo | 5.087 fichas: 4.876 activas y 211 inactivas |
| Primera aplicación del programa de precios | 110 productos: 109 simples y 1 con presentaciones; 0 errores, 15,105 s |
| Programa de presentaciones | 68 productos preparados: Furosemida, 66 fichas y Benzirin; 0 errores |
| Verificación AJAX | 136 respuestas de 68 fichas, sin errores de combinación, precio o bloque de disponibilidad |
| Chrome, cambio y regreso repetidos | Furosemida, Ketoprofeno y Eutarpan; precio correcto y sin Undefined |
| Repetición de precios | 0 cambios, aproximadamente 6,7 s |
| Pruebas aisladas | 25 Python de precios, 37 Python de presentaciones; contratos PHP en ambos repositorios |

En la última lectura: 4.487 fichas activas resueltas, 385 excluidas por vigencia ERP y
4 bloqueadas para revisión de correspondencia. Las 211 inactivas de PrestaShop se
incluyen en CSV pero no se actualizan. La salida 2 identifica pendientes comerciales,
no errores de las escrituras exitosas. No quedan altas de presentaciones válidas pendientes.

Durante la sesión `005097`, Alpina 1100 ml, cambió de I a A en el ERP; los excluidos
pasaron de 386 a 385. Esto confirma que el estado se lee nuevamente en cada ejecución.

## Precios visibles verificados en Chrome

| Ficha | Caja | Fracción |
|---|---:|---:|
| 4480 Furosemida | 20.340 | 2.034 |
| 4520 Ketoprofeno | 33.615 | 11.205 |
| 7159 Eutarpan | 48.000 | 4.800 |

Los valores de Furosemida y Ketoprofeno incluyen el descuento existente. Los importes ERP
son distintos del precio visible cuando hay promociones.

## Floratil

La ficha `4916`, 10 cápsulas, usa el ERP `001226`, activo, con `ManejPrese=N` y sin
presentaciones de venta definidas. La ficha `7166`, 20 sobres, usa `019148`, actualmente
inactivo. Sus antiguas filas de caja 120.000 y fracción 6.000 no justifican crear
alternativas en la ficha de cápsulas ni usar una fuente inactiva para crear nuevas
combinaciones. El CSV anterior no incorporaba esta exclusión.

## Correspondencias que requieren decisión comercial

| Ficha | Motivo |
|---|---|
| 4193 Galletas Moments 280 g | La alternativa activa corresponde a 168 g |
| 5133 Brujesin Sport 80 ml | Referencia antigua excluida y candidato activo; falta confirmar sustitución |
| 7150 Dosalin 30 mg | El candidato por prioridad de código dice SUMI HUELLERO; no se cruza automáticamente |
| 7746 Glade Vainilla | La alternativa activa dice Surtido; no certifica el aroma Vainilla |

No se cambiaron las fichas excluidas. En los productos tratados exclusivamente por el
programa de precios se verificaron nombres, publicación, unidades, referencias,
combinaciones y existencias. PrestaShop recalculó en 104 el `unit_price_ratio` derivado
al guardar; es un efecto nativo de `Product::update`, no publicación de inventario.
El CSV usa ahora `unit_price`/`unit_price_impact` para describir el PUM real y distingue
el ratio previo del final. No se recalcula el PUM comercial desde el ERP.

## Evidencia local

- `reports/separacion_precios_aplicacion/`: primer CSV completo, cambios y recibos.
- `reports/entrega_verificada/`: repetición final, CSV completo y cambios vacío.
- `reports/separacion_invariantes.json`: preservación de datos y excluidos.
- En el nuevo proyecto: `reports/aplicacion_catalogo/` y `reports/browser_separacion.json`.

Los informes completos permanecen locales, fuera de Git. El cron instalado en `.229`
ejecuta solo precios cada diez minutos, con bloqueo compartido y límite de 540 segundos.

**No se certifica aún producción.** Falta el ensayo en la nueva máquina prevista por el
usuario y resolver, si se requieren, el retiro automático de combinaciones, el PUM
comercial y la venta con inventario compartido. Las presentaciones preparadas están en
modo visible de pruebas con compra deshabilitada y stock cero en las nuevas combinaciones.

El cron ejecutó automáticamente el lote de las 17:00: 2 productos, 4 filas de cambios,
0 errores de aplicación y 8,147 s. El ERP había cambiado después de la prueba sin
cambios. El control de frescura rechaza por producto precios que cambian entre lecturas.
