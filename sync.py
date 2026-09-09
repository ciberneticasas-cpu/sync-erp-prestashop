#!/usr/bin/env python3
"""Review-first ERP -> native PrestaShop adapter. Python 3.6+, no pip packages."""
import argparse
import collections
import csv
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_FLOOR
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import unicodedata
import match_erp

API_VERSION = 3
ROOT = Path(__file__).resolve().parent
def test_host(settings):
    value = settings.get('test_host', '')
    address = ipaddress.IPv4Address(value)
    networks = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')
    if not any(address in ipaddress.IPv4Network(n) for n in networks) or value == '192.168.0.231':
        raise ValueError('Se requiere una IP LAN de pruebas distinta del ERP')
    return str(address)


def frozen_host(settings):
    """Explicit environment override, shared settings, then legacy configuration."""
    if 'SERVIDOR_CONGELADO' not in os.environ and not any(k in settings for k in ('SERVIDOR_CONGELADO', 'baseline_host')):
        return None
    value = os.environ.get('SERVIDOR_CONGELADO', settings.get('SERVIDOR_CONGELADO', settings.get('baseline_host')))
    if not isinstance(value, str):
        raise ValueError('SERVIDOR_CONGELADO debe ser una IPv4 LAN en texto')
    # Same LAN restriction as the test adapters. Empty/malformed values fail closed.
    return test_host({'test_host': value})


def target(settings):
    return test_host(settings) + '/mercaboy_pruebas/1'

FIELDS = ['autorizar', 'operacion', 'estado', 'motivo', 'id_producto', 'nombre_prestashop',
          'referencia_prestashop', 'erp_id', 'nombre_erp', 'presentacion_id', 'presentacion',
          'factor_erp', 'precio_erp_con_iva', 'iva_erp', 'precio_padre_actual',
          'precio_padre_propuesto', 'precio_presentacion_actual_sin_iva', 'precio_presentacion_sin_iva', 'impacto_actual', 'impacto_propuesto',
          'id_combinacion', 'referencia_combinacion', 'origen_referencia', 'fuente_precio_erp', 'inventario_erp_base',
          'stock_teorico_no_publicable', 'stock_actual', 'stock_a_escribir', 'predeterminada_destino', 'activo_destino', 'disponible_para_pedido_destino', 'nombre_destino']


def dec(value):
    try:
        d = Decimal(str(value).strip().replace(',', '.'))
    except InvalidOperation:
        raise ValueError('PRECIO_O_FACTOR_ERP_VACIO_INVALIDO')
    if not d.is_finite():
        raise ValueError('Importe/factor no finito')
    return d


def money(value):
    return str(dec(value).quantize(Decimal('.000001'), rounding=ROUND_HALF_UP))


def net_price(gross, tax):
    price, iva = dec(gross), dec(tax)
    if price <= 0 or iva < 0 or iva > 100:
        raise ValueError('Precio o IVA fuera de rango; requiere revision')
    # Same interpretation as legacy price_without_tax().
    divisor = 1 + iva / 100 if iva >= 2 else iva if iva > 1 else 1 + iva if iva > 0 else 1
    return price / divisor


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value or '').strip().lower())
                   if not unicodedata.combining(c))


def key(value):
    value = str(value or '').strip()
    return str(int(value)) if value.isdigit() else value


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def read_json(path):
    with open(str(path), encoding='utf-8') as stream:
        return json.load(stream)


def write_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(str(tmp), 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    tmp.replace(path)


def invoke(command, payload, timeout=180):
    result = subprocess.run(command, input=canonical(payload), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=str(ROOT), timeout=timeout)
    if result.returncode:
        # Our adapters redact credentials. Never include stdin or environment.
        raise RuntimeError(result.stderr.decode('utf-8', 'replace')[-1500:].strip())
    try:
        return json.loads(result.stdout.decode('utf-8'))
    except ValueError:
        raise RuntimeError('El adaptador no devolvio JSON valido; salida omitida')


def bridge(settings, command='snapshot', **kwargs):
    payload = dict(prestashop_root=settings['prestashop_root'], env_file=settings['env_file'], test_host=test_host(settings), SERVIDOR_CONGELADO=frozen_host(settings))
    payload.update(kwargs)
    return invoke(['php', str(ROOT / 'bridge.php'), command], payload)


def erp_read(settings, products):
    executable = ROOT / 'target/release/mercaboy_erp_reader'
    if not executable.exists():
        raise RuntimeError('Compile primero: cargo build --offline --release')
    result = invoke([str(executable)], dict(env_file=settings['env_file'],
                                        warehouses=settings['warehouses'], products=products), timeout=300)
    if result.get('schema_version') != API_VERSION:
        raise RuntimeError('Lector ERP incompatible; ejecute cargo build --offline --release')
    return result


def make_index(erp):
    refs, eans = collections.defaultdict(set), collections.defaultdict(set)
    products = {e['erp_id']: e for e in erp['products']}
    for e in erp['products']:
        for name in ('erp_id', 'reference', 'ean', 'ean2', 'ean3'):
            if key(e[name]): refs[key(e[name])].add(e['erp_id'])
        for name in ('ean', 'ean2', 'ean3'):
            if e[name]: eans[e[name]].add(e['erp_id'])
    return products, refs, eans


def resolve(ps, erp, mapping, index=None):
    products, refs, eans = index or make_index(erp)
    if mapping.get('erp_id'):
        ids = {mapping['erp_id']} & set(products)
    else:
        by_ref = refs.get(key(ps['reference']), set())
        by_ean = eans.get(str(ps['ean13'] or '').strip(), set())
        if by_ref and by_ean:
            ids = by_ref & by_ean
            if not ids:
                raise ValueError('REFERENCIA_Y_EAN_EN_CONFLICTO')
        else:
            ids = by_ref or by_ean
    if len(ids) != 1:
        raise ValueError('SIN_MATCH_ERP' if not ids else 'MATCH_ERP_AMBIGUO: ' + ','.join(sorted(ids)))
    return products[next(iter(ids))]


def presentations_for(erp_product, records):
    """Deduplicate economically AND physically identical units; flag same-price conflicts."""
    base = net_price(erp_product['gross'], erp_product['tax'])
    values = [dict(presentation_id='BASE', label=erp_product['unit'] or 'Base', factor='1', net_price=money(base))]
    aliases, issues = [], []
    for record in records:
        factor = dec(record['factor'])
        if factor <= 0:
            raise ValueError('FACTOR_ERP_INVALIDO: ' + record['presentation_id'])
        if record['from_main'].lower() not in ('0', '1', 'true', 'false'):
            raise ValueError('PrecioDesdePrincipal desconocido')
        price = base * factor if record['from_main'].lower() in ('1', 'true') else net_price(record['gross'], erp_product['tax'])
        price = dec(money(price))
        same = [v for v in values if dec(v['factor']) == factor and dec(v['net_price']) == price]
        if same:
            aliases.append(dict(record, equivalent_to=same[0]['presentation_id']))
            continue
        if any(dec(v['net_price']) == price for v in values):
            issues.append('MISMO_PRECIO_DISTINTO_FACTOR: ' + record['presentation_id'])
        values.append(dict(presentation_id=record['presentation_id'], label=record['label'],
                           factor=str(factor), net_price=money(price)))
    return values, aliases, issues


def match_combination(ps, item, configured):
    ident = configured.get('combination_id')
    aliases = {'sobre', 'blister'}
    matches = []
    for combo in ps['combinations']:
        attrs = combo['attributes']
        if len(attrs) != 1 or norm(attrs[0]['group_name']) != 'presentacion':
            raise ValueError('COMBINACIONES_AJENAS_A_PRESENTACION')
        label = norm(attrs[0]['label'])
        requested = norm(item['label'])
        if (ident and combo['id'] == int(ident)) or (not ident and
                (label == requested or {label, requested}.issubset(aliases))):
            matches.append(combo)
    if len(matches) > 1 or (ident and not matches):
        raise ValueError('MAPEO_COMBINACION_AMBIGUO_O_INEXISTENTE')
    return matches[0] if matches else None


def row_for(ps, e=None, item=None, **extra):
    row = {f: '' for f in FIELDS}
    row.update(autorizar='NO', operacion=str(ps['id']), id_producto=str(ps['id']),
               nombre_prestashop=ps['name'], referencia_prestashop=ps['reference'] or '',
               precio_padre_actual=ps['price'])
    if e:
        row.update(erp_id=e['erp_id'], nombre_erp=e['name'], precio_erp_con_iva=e['gross'],
                   iva_erp=e['tax'], inventario_erp_base=e['qty'], fuente_precio_erp=e.get('price_source', ''))
    if item:
        row.update(presentacion_id=item['presentation_id'], presentacion=item['label'],
                   factor_erp=item['factor'], precio_presentacion_sin_iva=item['net_price'])
        current = next((c for c in ps['combinations'] if c['id'] == item.get('combination_id') and c['id']), None)
        if current:
            row.update(impacto_actual=str(current['price']),
                       precio_presentacion_actual_sin_iva=money(dec(ps['price']) + dec(current['price'])),
                       stock_actual=str(current.get('quantity', '')))
        elif item['presentation_id'] == 'BASE' and not ps['combinations']:
            row.update(impacto_actual='0.000000', precio_presentacion_actual_sin_iva=ps['price'], stock_actual=str(ps.get('quantity', '')))
        if 'default' in item:
            row['predeterminada_destino'] = 'SI' if item['default'] else 'NO'
        if e:
            theoretical = max(0, (dec(e['qty']) / dec(item['factor'])).to_integral_value(rounding=ROUND_FLOOR))
            row['stock_teorico_no_publicable'] = str(theoretical)
    row.update(extra)
    return {k: str(v) for k, v in row.items()}


def build_plan(snapshot, erp, settings):
    from precios import build_plan as prices_plan
    return prices_plan(snapshot, erp, settings)


def audit(args, settings):
    snapshot = bridge(settings, ids=args.product or [])
    if not args.product:
        snapshot['products'] = [p for p in snapshot['products'] if str(p['active']) == '1']
    erp = erp_read(settings, snapshot['products'])
    plan = build_plan(snapshot, erp, settings)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'snapshot.json', snapshot)
    write_json(output / 'erp.json', erp)
    write_json(output / 'plan.json', plan)
    with open(str(output / 'revision.csv'), 'w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for row in plan['rows']:
            writer.writerow(csv_safe(row))
    counts = collections.Counter(row['estado'] for row in plan['rows'])
    print(json.dumps(dict(output=str(output), products=len(snapshot['products']),
                          proposed_products=len(plan['operations']), rows=counts,
                          unchanged=plan['unchanged'], plan_sha256=digest(plan)), ensure_ascii=False, indent=2))


def csv_safe(row):
    # Spreadsheet formula protection for ERP/product text. Negative money stays numeric.
    text_fields = {'nombre_prestashop', 'referencia_prestashop', 'nombre_erp', 'presentacion',
                   'referencia_combinacion', 'nombre_destino', 'erp_id', 'motivo'}
    return {k: "'" + v if k in text_fields and v.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else v
            for k, v in row.items()}


def approved_operations(plan, path, expected_sha):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha:
        raise ValueError('SHA256 del CSV no coincide')
    with open(str(path), encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError('Columnas CSV alteradas')
        rows = list(reader)
    if len(rows) != len(plan['rows']):
        raise ValueError('Filas CSV alteradas')
    decisions = collections.defaultdict(list)
    for actual, original in zip(rows, plan['rows']):
        expected = csv_safe(original)
        decision = actual.get('autorizar', '')
        if decision not in ('SI', 'NO'):
            raise ValueError('autorizar admite solamente SI o NO')
        if any(actual[k] != expected[k] for k in FIELDS if k != 'autorizar'):
            raise ValueError('Solo puede editarse autorizar; regenere para cambiar importes o mapeos')
        if actual['estado'] != 'PROPUESTO' and decision == 'SI':
            raise ValueError('No puede autorizar una fila bloqueada/omitida')
        if actual['estado'] == 'PROPUESTO':
            decisions[actual['operacion']].append(decision)
    selected = []
    for op in plan['operations']:
        values = decisions[str(op['id'])]
        if 'SI' in values and 'NO' in values:
            raise ValueError('Autorice todas las presentaciones del producto o ninguna')
        if values and all(v == 'SI' for v in values):
            selected.append(op)
    if not selected:
        raise ValueError('No hay productos autorizados')
    return selected


def apply(args, settings, adapter=None):
    adapter = adapter or bridge
    plan = read_json(args.plan)
    if plan['target'] != target(settings) or plan['settings'] != settings or digest(plan) != args.plan_sha256:
        raise ValueError('Plan/configuracion/destino distintos de los revisados')
    created = datetime.datetime.strptime(plan['created_at'][:19], '%Y-%m-%dT%H:%M:%S')
    age = (datetime.datetime.utcnow() - created).total_seconds()
    if age < 0 or age > min(24, int(settings['max_plan_age_hours'])) * 3600:
        raise ValueError('Plan vencido: regenere la auditoria')
    selected = plan['operations'] if getattr(args, 'direct_apply', False) else approved_operations(plan, args.csv, args.approved_csv_sha256)
    lock_path = ROOT / 'reports/apply.lock'
    lock_path.parent.mkdir(exist_ok=True)
    with open(str(lock_path), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        journal = Path(args.plan).parent / 'aplicacion.json'
        if journal.exists():
            raise ValueError('Este plan ya se intento aplicar. Revise aplicacion.json y genere un nuevo plan')
        live = adapter(settings, ids=[o['id'] for o in selected])
        current = {p['id']: p for p in live['products']}
        live_erp = erp_read(settings, live['products'])
        for op in selected:
            if current.get(op['id']) != op['before']:
                raise ValueError('PrestaShop cambio: regenere el plan antes de aplicar')
            e = [p for p in live_erp['products'] if p['erp_id'] == op['erp_product']['erp_id']]
            presentations = [p for p in live_erp['presentations'] if p['erp_id'] == op['erp_product']['erp_id']]
            # Price-only synchronization does not publish live ERP stock. New combinations
            # receive a fixed zero for review, so stock movement cannot stale a price plan.
            def economics(product):
                return {k: v for k, v in product.items() if k != 'qty'}
            if len(e) != 1 or economics(e[0]) != economics(op['erp_product']) or presentations != op['erp_presentations']:
                fields = [] if len(e) != 1 else [k for k in economics(e[0]) if e[0].get(k) != op['erp_product'].get(k)]
                raise ValueError('ERP cambio para producto {} ({}): regenere la auditoria'.format(op['id'], ', '.join(fields) or 'presentaciones/correspondencia'))
        state = dict(target=target(settings), plan_sha256=digest(plan), csv_sha256=getattr(args, 'approved_csv_sha256', None), authorization='--apply' if getattr(args, 'direct_apply', False) else 'CSV', results=[], errors=[], status='INICIADO')
        write_json(journal, state)
        for op in selected:
            state['in_progress'] = op['id']
            write_json(journal, state)
            try:
                result = adapter(settings, 'apply', operation=op, authorization='CLI_APPLY_TEST_ONLY' if getattr(args, 'direct_apply', False) else 'CSV_REVIEWED_TEST_ONLY')
                state['results'].append(result)
                state['in_progress'] = None
                write_json(journal, state)
            except Exception as error:
                state['errors'].append(dict(product_id=op['id'], error=str(error)))
                state['status'] = 'ERROR_REVISAR_ULTIMO_PRODUCTO'
                write_json(journal, state)
                if not getattr(args, 'direct_apply', False): raise
                continue
        state['status'] = 'APLICADO_CON_ERRORES' if state['errors'] else 'APLICADO_Y_VERIFICADO'
        write_json(journal, state)
        print('Aplicados y verificados {} productos; errores {}. {}'.format(len(state['results']), len(state['errors']), journal))


def verify(args, settings):
    journal = read_json(args.journal)
    if journal.get('target') != target(settings):
        raise ValueError('Destino protegido')
    results = [bridge(settings, 'verify', operation=result['operation']) for result in journal['results']]
    write_json(Path(args.journal).parent / 'validacion.json', results)
    print(json.dumps(results, ensure_ascii=False, indent=2))


def convert_order(lines, operations):
    """Read-only ERP export proposal. Never exports by parent reference alone."""
    index = {}
    for op in operations:
        for unit in op['presentations']:
            pair = (int(op['id']), int(unit['combination_id']))
            if pair in index:
                raise ValueError('Mapeo pedido duplicado')
            index[pair] = (op, unit)
    output = []
    for line in lines:
        pair = (int(line['product_id']), int(line['product_attribute_id']))
        if pair not in index:
            raise ValueError('Linea de pedido sin mapeo por producto/combinacion')
        op, unit = index[pair]
        if line['product_reference'] != unit['reference']:
            raise ValueError('Referencia del pedido no coincide con la combinacion')
        qty = dec(line['product_quantity'])
        if qty <= 0 or qty != qty.to_integral_value():
            raise ValueError('Cantidad de pedido invalida')
        output.append(dict(erp_id=op['erp_product']['erp_id'], presentation_id=unit['presentation_id'],
                           combination_id=pair[1], quantity_presentations=str(qty),
                           quantity_erp_base=str(qty * dec(unit['factor']))))
    return output


def validate_allocation(available, reserved, units):
    """Partition a shared ERP stock pool; never duplicate it across presentations."""
    available, reserved = dec(available), dec(reserved)
    if available < 0 or reserved < 0:
        raise ValueError('Inventario/reservas negativos')
    consumed = Decimal(0)
    for unit in units:
        qty, factor = dec(unit['quantity']), dec(unit['factor'])
        if qty < 0 or qty != qty.to_integral_value() or factor <= 0:
            raise ValueError('Asignacion/factor invalidos')
        consumed += qty * factor
    if consumed + reserved > available:
        raise ValueError('Sobreventa: asignaciones + reservas superan inventario ERP')
    return dict(consumed_base=str(consumed), remaining_base=str(available - reserved - consumed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', default=str(ROOT / 'settings.json'))
    sub = parser.add_subparsers(dest='command')
    a = sub.add_parser('audit', help='Solo lectura; genera un unico CSV de revision')
    a.add_argument('--product', type=int, action='append')
    a.add_argument('--output', default=str(ROOT / 'reports' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')))
    a = sub.add_parser('apply', help='Aplica exclusivamente productos autorizados en CSV')
    a.add_argument('--plan', required=True)
    a.add_argument('--csv', required=True)
    a.add_argument('--plan-sha256', required=True)
    a.add_argument('--approved-csv-sha256', required=True)
    a = sub.add_parser('verify', help='Valida objetos y motor de precios de una aplicacion')
    a.add_argument('--journal', required=True)
    a = sub.add_parser('order-preview', help='Convierte lineas de pedido JSON; no escribe en ERP')
    a.add_argument('--journal', required=True)
    a.add_argument('--lines', required=True)
    a = sub.add_parser('stock-preview', help='Evalua reparto de stock compartido; no lo publica')
    a.add_argument('--allocation', required=True)
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    settings = read_json(args.settings)
    if args.command == 'audit': audit(args, settings)
    elif args.command == 'apply': apply(args, settings)
    elif args.command == 'verify': verify(args, settings)
    elif args.command == 'order-preview':
        journal = read_json(args.journal)
        if journal['target'] != target(settings) or journal['status'] != 'APLICADO_Y_VERIFICADO':
            raise ValueError('Se requiere una aplicacion verificada en pruebas')
        print(json.dumps(convert_order(read_json(args.lines), [r['operation'] for r in journal['results']]), indent=2))
    elif args.command == 'stock-preview':
        allocation = read_json(args.allocation)
        print(json.dumps(validate_allocation(allocation['available_base'], allocation['reserved_base'], allocation['units']), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired, InvalidOperation, KeyError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
