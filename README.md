# sync-erp-prestashop

Sincroniza **precios y PUM** de productos activos y combinaciones existentes. Consulta
el ERP en cada ejecución, excluye fuentes inactivas/descodificadas y genera un CSV
completo y otro con los cambios realmente aplicados. No crea combinaciones ni repara
plantillas. El destino de esta versión está protegido para pruebas; producción no se ha tocado.

```bash
cargo build --offline --release
python3 sincronizar.py            # Consultar y generar CSV
python3 sincronizar.py --apply    # Actualizar precios y PUM válidos
python3 instalar_cron.py --apply  # Cada 10 minutos, en este clon
```

La preparación de Caja/Blíster y la reparación de Undefined están en el repositorio
[corregirPresentacionBlister](https://github.com/ciberneticasas-cpu/corregirPresentacionBlister).
Instalar ambos directorios uno junto al otro. El sincronizador funciona por sí solo;
el preparador reutiliza su lector ERP y reglas de precio.

Ver [uso, CSV y cambios de presentaciones](USO.md) y [validación de la separación](VALIDACION.md).
La documentación de versiones anteriores conserva valor histórico; la entrada vigente es
`sincronizar.py`. No utilizar planes guardados de versiones anteriores.
