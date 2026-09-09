"""Precios del motor nativo: origen congelado, pronóstico y verificación del destino."""
import base64
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_DOWN, ROUND_HALF_EVEN, ROUND_CEILING, ROUND_FLOOR
import json
import subprocess
import base_congelada
import sync

FIELDS = ['precio_visible_base_227', 'precio_visible_229', 'diferencia_precio_visible',
          'precio_visible_antes_corrida', 'precio_visible_propuesto', 'diferencia_visible_corrida',
          'comparacion_precio_visible', 'verificacion_precio_visible']
NUMERIC = set(FIELDS[:6])

TECHNICAL_FIELDS = [f+'_tecnico' for f in FIELDS[:6]] + ['precio_visible_verificado_tecnico', 'pum_precio_visible_verificado_tecnico']
CSV_FIELDS = ['precio_visible_verificado_tecnico', 'pum_precio_visible_verificado_tecnico', 'moneda_precios_visibles', 'decimales_precios_visibles']
FIELDS += TECHNICAL_FIELDS + ['comparacion_precio_visible_tecnica', 'verificacion_precio_visible_tecnica', 'moneda_precios_visibles', 'decimales_precios_visibles']
NUMERIC.update(TECHNICAL_FIELDS + ['decimales_precios_visibles'])


def currency(reading):
    # Defaults only support old saved evidence/test fixtures. Live reads require metadata.
    value = reading.get('currency', {'iso_code':'COP', 'precision':0, 'round_mode':2})
    if not value.get('iso_code') or not 0 <= value['precision'] <= 6 or value['round_mode'] not in range(6):
        raise ValueError('CONFIGURACION_REDONDEO_INVALIDA')
    return value


def rounded(value, reading):
    c = currency(reading)
    number = sync.dec(value)
    unit = Decimal(1).scaleb(-c['precision'])
    mode = c['round_mode']
    rounding = {0:ROUND_CEILING, 1:ROUND_FLOOR, 2:ROUND_HALF_UP, 3:ROUND_HALF_DOWN, 4:ROUND_HALF_EVEN, 5:ROUND_HALF_EVEN}[mode]
    result = number.quantize(unit, rounding=rounding)
    if mode == 5:
        scaled = abs(number/unit)
        lower = scaled.to_integral_value(rounding=ROUND_FLOOR)
        if scaled-lower == Decimal('0.5'):
            odd = lower if int(lower) % 2 else lower+1
            result = ((-odd if number < 0 else odd)*unit).quantize(unit)
    if result == 0:result=abs(result)
    return format(result, 'f')


def assign(row, field, value, reading):
    row[field+'_tecnico'] = sync.money(value)
    row[field] = rounded(value, reading)


def format_verified(row, reading):
    result = dict(row)
    for field in ('precio_visible_verificado', 'pum_precio_visible_verificado'):
        if result.get(field) not in ('', None):
            assign(result, field, result.get(field+'_tecnico') or result[field], reading)
    c = currency(reading)
    result.update(moneda_precios_visibles=c['iso_code'], decimales_precios_visibles=c['precision'])
    return result



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
    payload = dict(test_host=host, prestashop_root=settings['prestashop_root'], env_file=settings['env_file'], products=products, stock_visibility=not baseline)
    # Neither native writer nor apply/verify functions are sent to the frozen host.
    source = (sync.ROOT/'bridge.php').read_text().split('function verifyProduct(', 1)[0]
    if not baseline:
        source += (sync.ROOT/'stock_informe.php').read_text().replace('<?php', '', 1)
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
    if 'currency' not in value:raise ValueError('FALTA_MONEDA_PRECIOS_VISIBLES')
    currency(value)
    if value.get('host') != host or len(value.get('prices', [])) != sum(1+len(p['combinations']) for p in products):
        raise ValueError('LECTURA_PRECIOS_VISIBLES_INCOMPLETA: '+host)
    if not baseline and set(value.get('stock_visibility', {})) != {str(p['id']) for p in products}:
        raise ValueError('LECTURA_VISIBILIDAD_STOCK_INCOMPLETA')
    return value


def index(value):
    return {(p['id'],p['combination_id']):p for p in value['prices']}


def enrich(rows, initial, catalog, before, frozen, after=None):
    for reading in ([frozen] if initial is not None else []) + ([after] if after is not None else []):
        if currency(reading)['iso_code'] != currency(before)['iso_code']:
            raise ValueError('MONEDAS_NO_COMPARABLES')
    old = {p['id']:p for p in (initial or catalog)['products']}
    live = {p['id']:p for p in catalog['products']}
    previous, current = index(frozen), index(before)
    final = index(after) if after is not None else None
    for row in rows:
        pid, cid = row['id_producto'], row['id_combinacion']
        for field in FIELDS: row[field] = ''
        row.update(format_verified(row, before))
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
        if base and initial is not None:assign(row, 'precio_visible_base_227', base['actual'], frozen)
        if dest:
            proposed=Decimal(str(dest['proposed']))
            assign(row, 'precio_visible_antes_corrida', dest['actual'], before)
            assign(row, 'precio_visible_propuesto', proposed, before)
            value=proposed
            row['verificacion_precio_visible']='PRONOSTICO_MOTOR_NATIVO'
            row['verificacion_precio_visible_tecnica']='PRONOSTICO_MOTOR_NATIVO'
            if final is not None:
                observed=final.get((pid,cid))
                if observed is None:raise ValueError('PRECIO_FINAL_NO_LEIDO: '+str(pid))
                value=Decimal(str(observed['actual']))
                assign(row, 'precio_visible_verificado', value, after)
                row['diferencia_visible_corrida']=format(Decimal(row['precio_visible_verificado'])-Decimal(row['precio_visible_antes_corrida']), 'f')
                row['diferencia_visible_corrida_tecnico']=sync.money(value-Decimal(str(dest['actual'])))
                row['verificacion_precio_visible']='COINCIDE' if Decimal(row['precio_visible_verificado'])==Decimal(row['precio_visible_propuesto']) else 'DIFIERE_REVISAR'
                row['verificacion_precio_visible_tecnica']='COINCIDE' if abs(value-proposed)<Decimal('0.01') else 'DIFIERE_REVISAR'
            assign(row, 'precio_visible_229', value, after if after is not None else before)
            if base and initial is not None:
                difference=value-Decimal(str(base['actual']))
                row['diferencia_precio_visible']=format(Decimal(row['precio_visible_229'])-Decimal(row['precio_visible_base_227']), 'f')
                row['diferencia_precio_visible_tecnico']=sync.money(difference)
                row['comparacion_precio_visible']='IGUAL' if Decimal(row['diferencia_precio_visible'])==0 else 'CAMBIO_VS_BASE'
                row['comparacion_precio_visible_tecnica']='IGUAL' if abs(difference)<Decimal('0.01') else 'CAMBIO_VS_BASE'
            else:row['comparacion_precio_visible']='SIN_PRESENTACION_COMPARABLE_EN_BASE'
        else:row['comparacion_precio_visible']='SIN_PRESENTACION_EN_DESTINO'
    return rows
