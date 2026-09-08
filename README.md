# Sincronización ERP → PrestaShop de pruebas

> Revisión de vigencia ERP: se detectaron fuentes en estado I y marcas «no usar»/DESCO.
> El control de vigencia aún no está incorporado al sincronizador. Los resultados de
> precios no certifican vigencia comercial. Ver [análisis y regla propuesta](analisis-vigencia-erp.md).


La entrada principal es `sincronizar.py`: **auditoría por defecto y escritura solo con `--apply`**.
El CSV conserva las 23 columnas originales del programa anterior y coloca los productos
con Blíster al final. Usa los objetos nativos de PrestaShop en el clon 311 (192.168.0.229).

```bash
python3 sincronizar.py
python3 sincronizar.py --apply
```

Para reparar solamente el navegador:

```bash
python3 corregir_blister.py --apply
```

Ver [instrucciones completas y significado del CSV](USO.md).
El flujo anterior de `sync.py audit/apply` se conserva para compatibilidad y trazabilidad;
no es necesario utilizarlo para la ejecución habitual.

## Resultado del 8 de septiembre

- 4.876 productos activos auditados.
- 90 productos actualizados en esta ejecución, sin errores de aplicación.
- Auditoría posterior: 4.875 sin cambios pendientes y 1 bloqueado por una discrepancia ERP.
- 92 fichas con presentaciones: 184 respuestas de combinación/precio/bloque de compra correctas.
- Chrome: cuatro fichas representativas, incluidos Blíster nuevos, sin aviso Undefined.

[CSV principal de revisión](reports/mejoras_aplicacion_20260908/stock_auditoria_20260908_003052.csv).
[Diario de aplicación](reports/mejoras_aplicacion_20260908/aplicacion.json).
[Verificación de presentaciones](reports/mejoras_aplicacion_20260908/verificacion_presentaciones.json).

Pendiente: producto 7746, Glade Vainilla x3 repuestos de 21 ml. Su referencia ERP dice
«no usar» y su EAN corresponde a Surtido. Se requiere la correspondencia comercial correcta;
no se aplicó un precio de otro producto para eliminar artificialmente el bloqueo.

El detalle histórico está en [RESULTADO.md](RESULTADO.md). El lector ERP mantiene SELECT
sobre 192.168.0.231; el clon 310 y producción quedan fuera del alcance. No se hacen dumps.
