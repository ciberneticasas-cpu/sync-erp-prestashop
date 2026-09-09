"""Precios del motor nativo: origen congelado, pronóstico y verificación del destino."""
import base64
from decimal import Decimal
import json
import subprocess
import base_congelada
import sync

FIELDS = ['precio_visible_base_227', 'precio_visible_229', 'diferencia_precio_visible',
          'precio_visible_antes_corrida', 'precio_visible_propuesto', 'diferencia_visible_corrida',
          'comparacion_precio_visible', 'verificacion_precio_visible']
NUMERIC = set(FIELDS[:6])


def read(settings, catalog, plan=None, baseline=False):
    host = base_congelada.HOST if baseline else sync.test_host(settings)
    if baseline and settings.get('baseline_host') != host:
        raise ValueError('Origen congelado de precios no configurado')
    operations = {o['id']: o for o in (plan or {}).get('operations', [])}
    products = []
    for p in catalog['products']:
        row = dict(id=p['id'], combinations=[c['id'] for c in p['combinations']])
        if p['id'] in operations:
            op = operations[p['id']]
            impacts = {str(u['combination_id']):u['impact'] for u in op['presentations'] if u['combination_id']}
            impacts.update({str(c['combination_id']):c['impact'] for c in op.get('combination_prices', [])})
            row['proposal'] = dict(base_price=op['base_price'], impacts=impacts)
        products.append(row)
    payload = dict(test_host=host, prestashop_root=settings['prestashop_root'], env_file=settings['env_file'], products=products)
    # Neither native writer nor apply/verify functions are sent to the frozen host.
    source = (sync.ROOT/'bridge.php').read_text().split('function verifyProduct(', 1)[0]
    source += (sync.ROOT/'precios_visibles.php').read_text().replace('<?php', '', 1)
    encoded = base64.b64encode(sync.canonical(payload)).decode('ascii')
    source += "\ntry { $request=json_decode(base64_decode('"+encoded+"'),true);"+'''
        $parameters=localParameters($request); $connection=connection($request,$parameters);
        echo json_encode(visiblePrices($request), JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
    } catch (Throwable $error) { fwrite(STDERR, "Fallo de lectura/calculo nativo de precios visibles\\n"); exit(1); }
'''
    command = ['php'] if not baseline else ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2','root@'+host,'php']
    result = subprocess.run(command, input=source.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=240)
    if result.returncode:
        raise RuntimeError('PRECIOS_VISIBLES_NO_DISPONIBLES: '+host)
    value = json.loads(result.stdout.decode())
    if value.get('host') != host or len(value.get('prices', [])) != sum(1+len(p['combinations']) for p in products):
        raise ValueError('LECTURA_PRECIOS_VISIBLES_INCOMPLETA: '+host)
    return value


def index(value):
    return {(p['id'],p['combination_id']):p for p in value['prices']}


def enrich(rows, initial, catalog, before, frozen, after=None):
    old = {p['id']:p for p in (initial or catalog)['products']}
    live = {p['id']:p for p in catalog['products']}
    previous, current = index(frozen), index(before)
    final = index(after) if after is not None else None
    for row in rows:
        pid, cid = row['id_producto'], row['id_combinacion']
        for field in FIELDS: row[field] = ''
        ps = old.get(pid)
        combo = next((c for c in live[pid]['combinations'] if c['id']==cid), None)
        old_cid = None
        if ps:
            if not cid or (row['presentacion_id']=='BASE' and not ps['combinations']): old_cid=0
            elif combo:
                try: old_combo=base_congelada.combination(ps,combo)
                except ValueError: old_combo=None
                if old_combo:old_cid=old_combo['id']
        base = previous.get((pid,old_cid))
        # A missing ERP alternative must not borrow the parent's visible price.
        exists = row.get('presentacion_en_prestashop') == 'SI'
        dest = current.get((pid,cid)) if exists else None
        if base and initial is not None:row['precio_visible_base_227']=sync.money(base['actual'])
        if dest:
            proposed=Decimal(str(dest['proposed']))
            row['precio_visible_antes_corrida']=sync.money(dest['actual'])
            row['precio_visible_propuesto']=sync.money(proposed)
            value=proposed
            row['verificacion_precio_visible']='PRONOSTICO_MOTOR_NATIVO'
            if final is not None:
                observed=final.get((pid,cid))
                if observed is None:raise ValueError('PRECIO_FINAL_NO_LEIDO: '+str(pid))
                value=Decimal(str(observed['actual']))
                row['precio_visible_verificado']=sync.money(value)
                row['diferencia_visible_corrida']=sync.money(value-Decimal(str(dest['actual'])))
                row['verificacion_precio_visible']='COINCIDE' if abs(value-proposed)<Decimal('0.01') else 'DIFIERE_REVISAR'
            row['precio_visible_229']=sync.money(value)
            if base and initial is not None:
                difference=value-Decimal(str(base['actual']))
                row['diferencia_precio_visible']=sync.money(difference)
                row['comparacion_precio_visible']='IGUAL' if abs(difference)<Decimal('0.01') else 'CAMBIO_VS_BASE'
            else:row['comparacion_precio_visible']='SIN_PRESENTACION_COMPARABLE_EN_BASE'
        else:row['comparacion_precio_visible']='SIN_PRESENTACION_EN_DESTINO'
    return rows
