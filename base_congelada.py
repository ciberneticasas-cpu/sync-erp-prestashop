"""Datos iniciales completos del servidor congelado configurable, leídos por SSH."""
import base64
import json
import subprocess
import sync

HOST = '192.168.0.227'  # Compatibility constant for old evidence/tests; reads use settings.


def read(settings, ids=None):
    host = sync.frozen_host(settings)
    if not host or sync.test_host(settings) == host:
        raise ValueError('BASE_CONGELADA: el servidor congelado debe ser origen, nunca destino')
    if host == 'www.mercaboy.com':
        import origen_directo
        return origen_directo.read(settings, ids)
    # Solo las funciones de lectura compartidas; no se envía el escritor al servidor congelado.
    reader = (sync.ROOT / 'bridge.php').read_text().split('function boot(', 1)[0]
    payload = dict(test_host=host, SERVIDOR_CONGELADO=host, prestashop_root=settings['prestashop_root'], env_file=settings['env_file'], ids=ids or [])
    encoded = base64.b64encode(sync.canonical(payload)).decode('ascii')
    code = reader + "\ntry { $request=json_decode(base64_decode('" + encoded + "'),true);" + '''
        $parameters=localParameters($request); $db=connection($request,$parameters);
        echo json_encode(snapshot($db,$parameters,$request['ids']), JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
    } catch (Throwable $error) { fwrite(STDERR,"Fallo de lectura de base congelada\\n"); exit(1); }
'''
    try:
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '-o', 'ServerAliveInterval=10',
                                 '-o', 'ServerAliveCountMax=2', 'root@'+host, 'php'], input=code.encode(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if result.returncode:
            raise RuntimeError('BASE_CONGELADA_NO_DISPONIBLE: SSH/lectura '+host)
        value = json.loads(result.stdout.decode('utf-8'))
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise RuntimeError('BASE_CONGELADA_NO_DISPONIBLE: no se sustituye por datos del destino') from error
    if value.get('target') != host+'/mercaboy_pruebas/1' or not isinstance(value.get('products'), list):
        raise ValueError('BASE_CONGELADA_INVALIDA: origen o formato inesperado')
    if len({p['id'] for p in value['products']}) != len(value['products']):
        raise ValueError('BASE_CONGELADA_INVALIDA: productos duplicados')
    return value


def combination(initial, current):
    if not current:
        return None
    attrs = lambda c: sorted((sync.norm(a['group_name']), sync.norm(a['label'])) for a in c['attributes'])
    candidates = [c for c in initial['combinations'] if attrs(c) == attrs(current)]
    if len(candidates) > 1:
        raise ValueError('BASE_CONGELADA_COMBINACION_AMBIGUA')
    return candidates[0] if candidates else None

FIELDS = 'inventario_producto_inicial,pum_precio_producto_inicial,pum_ratio_producto_inicial,base_host,base_huella,base_estado,id_combinacion_anterior,cantidad_presentaciones_iniciales,nombre_destino_actual,referencia_destino_actual,referencia_combinacion_destino,activo_destino_antes,inventario_destino_antes,precio_destino_antes,precio_base_destino_antes,impacto_destino_antes,pum_unidad_destino_antes,pum_precio_unitario_destino_antes,pum_ratio_destino_antes,cambio_aplicado_en_corrida,diferencia_respecto_base'.split(',')


def report(rows, initial, destination, changes):
    old = {p['id']: p for p in initial['products']}
    live = {p['id']: p for p in destination['products']}
    fingerprint = sync.digest(initial)
    changed = {(r['id_producto'], r['id_combinacion']) for r in changes}
    for row in rows:
        pid, cid = row['id_producto'], row['id_combinacion']
        previous = old.get(pid)
        current_combo = next((c for c in live[pid]['combinations'] if c['id'] == cid), None)
        row.update(base_host=initial['target'].split('/', 1)[0], base_huella=fingerprint, nombre_destino_actual=live[pid]['name'],
                   referencia_destino_actual=live[pid]['reference'], referencia_combinacion_destino=row['referencia_combinacion'],
                   activo_destino_antes=live[pid]['active'], inventario_destino_antes=row['inventario_mariadb'],
                   precio_destino_antes=row['precio_mariadb'], precio_base_destino_antes=row['precio_base_anterior'],
                   impacto_destino_antes=row['impacto_anterior'], pum_unidad_destino_antes=row['pum_unidad_anterior'],
                   pum_precio_unitario_destino_antes=row['pum_precio_unitario_anterior'], pum_ratio_destino_antes=row['pum_ratio_anterior'],
                   cambio_aplicado_en_corrida='SI' if (pid, cid) in changed else 'NO')
        for field in 'nombre_prestashop,referencia,activo_prestashop,inventario_mariadb,precio_mariadb,precio_base_anterior,impacto_anterior,pum_unidad_anterior,pum_precio_unitario_anterior,pum_ratio_anterior,referencia_combinacion'.split(','):
            row[field] = ''
        row['diferencia_respecto_base'] = 'NO_COMPARABLE'
        if not previous:
            row['base_estado'] = 'PRODUCTO_SIN_BASE'
            continue
        row.update(nombre_prestashop=previous['name'], referencia=previous['reference'], activo_prestashop=previous['active'],
                   precio_base_anterior=previous['price'], pum_unidad_anterior=previous.get('unity', ''),
                   cantidad_presentaciones_iniciales=len(previous['combinations']), inventario_producto_inicial=previous.get('quantity', ''), pum_precio_producto_inicial=previous.get('unit_price', ''), pum_ratio_producto_inicial=previous.get('unit_price_ratio', ''))
        try:
            previous_combo = combination(previous, current_combo)
        except ValueError:
            row['base_estado'] = 'COMBINACION_AMBIGUA_EN_BASE'
            continue
        if cid and not previous_combo:
            row['base_estado'] = 'COMBINACION_NUEVA_SIN_BASE'
            continue
        row['base_estado'] = 'COINCIDE'
        row['id_combinacion_anterior'] = previous_combo['id'] if previous_combo else 0
        old_price = sync.dec(previous['price']) + sync.dec((previous_combo or {}).get('price', 0))
        unit_price = sync.dec(previous.get('unit_price') or 0) + sync.dec((previous_combo or {}).get('unit_price_impact') or 0)
        row.update(inventario_mariadb=(previous_combo or previous).get('quantity', ''), precio_mariadb=sync.money(old_price),
                   impacto_anterior=(previous_combo or {}).get('price', '0'), referencia_combinacion=(previous_combo or {}).get('reference', ''),
                   pum_precio_unitario_anterior=sync.money(unit_price), pum_ratio_anterior=sync.money(old_price / unit_price) if unit_price > 0 else '0.000000')
        final_price = row['precio_para_prestashop'] if row['resultado'] == 'PROPUESTO' else row['precio_final_sin_iva']
        if final_price != '':
            row['diferencia_respecto_base'] = 'SI' if (old_price != sync.dec(final_price) or previous.get('unity', '') != row['pum_unidad'] or unit_price != sync.dec(row['pum_precio_unitario'] or 0)) else 'NO'
    return rows
