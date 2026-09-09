#!/usr/bin/env python3
"""Audit by default; --apply updates all valid prices through native PrestaShop objects."""
import argparse
import collections
import csv
import datetime
from decimal import Decimal, ROUND_FLOOR
import json
import fcntl
import time
import vigencia
import aplicar_precios
from pathlib import Path
import subprocess
import sys
import match_erp
import sync
import base_congelada
import nombres
import libro_auditoria
import precios_visibles

LEGACY_FIELDS = 'referencia,nombre_prestashop,nombre_corto_erp,factor_conversion_precio,inventario_erp,inventario_para_prestashop,inventario_mariadb,pendiente,final_sync,precio_mariadb,precio_sin_impuesto_erp,ivaid,precio_erp,precio_para_prestashop,pum_fuente,pum_unidad,pum_ratio,pum_precio_unitario,otras_listas_precios_erp,erp_host,accion,unidad_erp,unidad_mariadb_inferida'.split(',')
EXTRA_FIELDS = 'id_producto,erp_id,criterio_match,observacion_match,nombre_erp,presentacion_id,presentacion,id_combinacion,referencia_combinacion,impacto_precio,nombre_destino,resultado,motivo,precio_final_sin_iva,precio_visible_verificado,url_revision,stock_se_actualiza,estado_erp,marcas_vigencia_erp,elegible_precio,motivo_exclusion,activo_prestashop,precio_base_anterior,precio_base_nuevo,impacto_anterior,presentacion_estado_erp,presentacion_venta_erp,presentacion_en_prestashop,situacion_presentacion,cantidad_presentaciones_erp,cantidad_presentaciones_web,maneja_presentaciones_erp,pum_ratio_final'.split(',')

PUM_FIELDS = 'pum_observacion,pum_discrepancia,pum_contenido_erp,pum_unidad_erp,pum_contenido_erp_convertido,pum_unidad_erp_normalizada,pum_contenido_nombre,pum_unidad_nombre,pum_unidad_anterior,pum_precio_unitario_anterior,pum_ratio_anterior,pum_unidad_propuesta,pum_precio_unitario_propuesto,pum_ratio_propuesto,pum_estado,pum_cambio_aplicado,pum_precio_visible_verificado,tipo_cambio'.split(',')
EXTRA_FIELDS += PUM_FIELDS + base_congelada.FIELDS + ['nombre_suguerido_prestashop', 'motivo_nombre_sugerido', 'pum_factor_presentacion_nombre', 'pum_contenido_nombre_convertido']


def pum_report(row, ps, combo, decision):
    old_price = sync.dec(ps.get('unit_price') or 0) + sync.dec((combo or {}).get('unit_price_impact') or 0)
    actual = sync.dec(row['precio_mariadb'] or 0)
    old_ratio = sync.money(actual / old_price) if old_price > 0 else '0.000000'
    row.update(pum_unidad_anterior=ps.get('unity', ''), pum_precio_unitario_anterior=sync.money(old_price),
               pum_ratio_anterior=old_ratio, pum_ratio=old_ratio, pum_ratio_final=old_ratio, pum_cambio_aplicado='NO')
    if not decision:
        return
    selected = next((c for c in decision['combinations'] if c['combination_id'] == row['id_combinacion']), decision)
    row.update(pum_observacion=decision['note'], pum_discrepancia=decision['discrepancy'], pum_contenido_erp=decision['erp_content'],
               pum_unidad_erp=decision['erp_unit'], pum_contenido_erp_convertido=decision['erp_ratio'],
               pum_unidad_erp_normalizada=decision['erp_unity'], pum_contenido_nombre=decision['name_ratio'],
               pum_unidad_nombre=decision['name_unity'], pum_factor_presentacion_nombre=decision.get('name_factor', '1'), pum_contenido_nombre_convertido=decision.get('name_base_ratio', decision['name_ratio']), pum_unidad_propuesta=decision['unity'],
               pum_precio_unitario_propuesto=selected['unit_price'], pum_ratio_propuesto=selected['ratio'],
               pum_estado=row['resultado'])
    if row['resultado'] in ('PROPUESTO', 'APLICADO', 'SIN_CAMBIOS'):
        row.update(pum_fuente=decision['source'], pum_unidad=decision['unity'],
                   pum_precio_unitario=selected['unit_price'], pum_ratio=selected['ratio'])
    changed = old_price != sync.dec(selected['unit_price']) or ps.get('unity', '') != decision['unity']
    price_changed = (sync.dec(row['precio_base_anterior']) != sync.dec(row['precio_base_nuevo']) or
                     sync.dec(row['impacto_anterior'] or 0) != sync.dec(row['impacto_precio'] or 0))
    row['tipo_cambio'] = 'PRECIO_Y_PUM' if changed and price_changed else 'SOLO_PUM' if changed else 'SOLO_PRECIO' if price_changed else 'SIN_CAMBIOS'
    if row['resultado'] in ('PROPUESTO', 'APLICADO') and changed:
        row['accion'] = 'ACTUALIZAR_PRECIO_Y_PUM' if price_changed else 'ACTUALIZAR_PUM'
    if row['resultado'] == 'APLICADO' and changed:
        row['pum_cambio_aplicado'] = 'SI'


def report_rows(snapshot, erp, plan, settings, journal=None):
    prepared = match_erp.index(erp)
    operations = {o['id']: o for o in plan['operations']}
    applied = {r['operation']['id']: r for r in (journal or {}).get('results', [])}
    failed = {r['product_id']: r['error'] for r in (journal or {}).get('errors', [])}
    blocked = collections.defaultdict(list)
    for r in plan['rows']:
        if r['estado'] == 'BLOQUEADO': blocked[int(r['id_producto'])].append(r['motivo'])
    price_lists = collections.defaultdict(list)
    for r in erp.get('price_lists', []): price_lists[r['erp_id']].append('Lista {}: {}'.format(r['list_id'], r['gross']))
    presentations = collections.defaultdict(list)
    for r in erp['presentations']: presentations[r['erp_id']].append(r)
    rows = []
    frozen = {p['id']: p for p in snapshot.get('baseline', {}).get('products', [])}
    for ps in snapshot['products']:
        initial = frozen.get(ps['id'], ps)
        ident = ps['id']; mapping = settings.get('mappings', {}).get(str(ident), {})
        operation = applied.get(ident, {}).get('operation', operations.get(ident))
        reason = '; '.join(sorted(set(blocked[ident])))
        e, criterion, warning, units = None, '', '', []
        try:
            e, criterion, warning = match_erp.resolve(initial, erp, mapping, prepared)
            warning = mapping.get('match_note', warning)
            if e['manages'] == 'S' and not presentations[e['erp_id']]:
                warning += '; ERP indica presentaciones sin definicion vendible: solo precio de la unidad existente'
            if operation:
                units = [dict(u) for u in operation['presentations']]
            else:
                units, aliases, issues = sync.presentations_for(e, presentations[e['erp_id']])
                if len(units) == 1:
                    factor = mapping.get('simple_factor', erp['legacy_factors'].get('{}:{}'.format(ident, e['erp_id'])))
                    if factor is not None:
                        units[0].update(factor=str(factor), net_price=sync.money(sync.net_price(e['gross'], e['tax']) * sync.dec(factor)))
                for u in units:
                    configured = mapping.get('presentations', {}).get(u['presentation_id'], {})
                    u['label'] = configured.get('label', 'Caja' if u['presentation_id'] == 'BASE' and sync.norm(e['unit']) in ('cja','cj','caja') else u['label'])
                    try: combo = sync.match_combination(ps, u, configured)
                    except ValueError: combo = None
                    u.update(combination_id=(combo or {}).get('id', 0), reference=(combo or {}).get('reference', ''), impact=sync.money(sync.dec(u['net_price'])-sync.net_price(e['gross'], e['tax'])))
        except ValueError as error:
            reason = reason or str(error)
            if isinstance(error, vigencia.Excluded):
                e = error.products[0] if len(error.products) == 1 else None
                if ps['combinations']:
                    units = [dict(presentation_id='EXISTENTE', label=' / '.join(a['label'] for a in c['attributes']), factor='', net_price='', combination_id=c['id'], reference=c['reference']) for c in ps['combinations']]
        if not units: units = [dict(presentation_id='BASE', label='', factor='', net_price='', combination_id=0)]
        represented = {u.get('combination_id') for u in units if u.get('combination_id')}
        for c in ps['combinations']:
            if c['id'] not in represented and all(sync.norm(a['group_name'])=='presentacion' for a in c['attributes']):
                units.append(dict(presentation_id='SOLO_WEB:'+str(c['id']), label=' / '.join(a['label'] for a in c['attributes']), factor='', net_price='', combination_id=c['id'], reference=c['reference'], impact=c['price']))
        decision = (operation or {}).get('pum', plan.get('pum_decisions', {}).get(str(ident)))
        if decision and not any(u.get('combination_id') for u in units):
            expected_impacts = {c['combination_id']: c['impact'] for c in (operation or {}).get('combination_prices', [])}
            for current_combo in ps['combinations']:
                c = dict(current_combo, price=expected_impacts.get(current_combo['id'], current_combo['price']))
                units.append(dict(presentation_id='EXISTENTE:'+str(c['id']), label=' / '.join(a['label'] for a in c['attributes']),
                                  factor=units[0]['factor'], net_price=sync.money(sync.dec((operation or {}).get('base_price', ps['price']))+sync.dec(c['price'])),
                                  combination_id=c['id'], reference=c['reference'], impact=c['price']))
        suggested, suggestion_reason = nombres.suggest(initial, e, settings, units)
        has_blister = any('blister' in sync.norm(u['label']) or sync.norm(u['label']) == 'sobre' for u in units) or any('blister' in sync.norm(r['label']) for r in presentations.get((e or {}).get('erp_id'), [])) or any('blister' in sync.norm(a['label']) for c in ps['combinations'] for a in c['attributes'])
        for u in units:
            row = {field: '' for field in LEGACY_FIELDS + EXTRA_FIELDS}
            combo = next((c for c in ps['combinations'] if c['id'] == u.get('combination_id')), None)
            actual_price = sync.money(sync.dec(ps['price']) + sync.dec((combo or {}).get('price', 0))) if combo or u['presentation_id']=='BASE' else ''
            stock = (combo or {}).get('quantity', ps.get('quantity', '') if u['presentation_id']=='BASE' else '')
            status = 'ERROR' if ident in failed else 'APLICADO' if ident in applied else 'BLOQUEADO' if reason else 'PROPUESTO' if operation else 'SIN_CAMBIOS'
            if reason.startswith('FUENTE_ERP_EXCLUIDA'): status = 'EXCLUIDO_ERP'
            elif reason.startswith('PENDIENTE_PRESENTACIONES'): status = 'PENDIENTE_PRESENTACIONES'
            if str(initial['active']) != '1': status = 'INACTIVO_PRESTASHOP'
            record = next((r for r in erp.get('all_presentations', erp['presentations']) if r['erp_id']==(e or {}).get('erp_id') and r['presentation_id']==u['presentation_id']), {})
            is_base = u['presentation_id']=='BASE'
            is_existing = bool(combo) or (is_base and not ps['combinations'])
            situation = 'SOLO_WEB_REVISAR_RETIRO' if u['presentation_id'].startswith('SOLO_WEB:') else 'EXISTENTE_FUENTE_EXCLUIDA' if status=='EXCLUIDO_ERP' else 'COINCIDE' if is_existing else 'FALTA_CREAR_EN_WEB'
            if not record and combo and e:
                for raw in erp.get('all_presentations', []):
                    if raw['erp_id'] != e['erp_id']: continue
                    configured = mapping.get('presentations', {}).get(raw['presentation_id'], {})
                    try: candidate = sync.match_combination(ps, raw, configured)
                    except ValueError: candidate = None
                    if candidate and candidate['id']==combo['id']:
                        record = raw; break
            row.update(maneja_presentaciones_erp=(e or {}).get('manages',''), pum_ratio_final=ps.get('unit_price_ratio',''), presentacion_estado_erp=record.get('state','A' if is_base and e else ''), presentacion_venta_erp=record.get('sale','1' if is_base and e else ''),
                presentacion_en_prestashop='SI' if is_existing else 'NO', situacion_presentacion=situation,
                cantidad_presentaciones_erp=1+len(presentations.get((e or {}).get('erp_id'), [])) if e else '', cantidad_presentaciones_web=len(ps['combinations']) or 1,
                estado_erp=(e or {}).get('state', ''), marcas_vigencia_erp=';'.join(vigencia.marks(e)) if e else '',
                elegible_precio='SI' if e and not vigencia.marks(e) else 'NO', motivo_exclusion=reason if status=='EXCLUIDO_ERP' else '',
                activo_prestashop=ps['active'], precio_base_anterior=ps['price'], precio_base_nuevo=(operation or {}).get('base_price',ps['price']), impacto_anterior=(combo or {}).get('price','0'),
                referencia=ps['reference'], nombre_prestashop=ps['name'], inventario_mariadb=stock,
                final_sync=stock, precio_mariadb=actual_price, precio_para_prestashop=u['net_price'],
                pum_fuente='ACTUAL_SIN_CAMBIOS', pum_unidad=ps.get('unity',''), pum_ratio=ps.get('unit_price_ratio',''),
                erp_host='192.168.0.231', accion='ACTUALIZAR_PRECIO_PRESENTACIONES' if operation and operation['mode']=='presentations' else 'ACTUALIZAR_PRECIO' if operation else status,
                id_producto=ident, criterio_match=criterion, observacion_match=warning, presentacion_id=u['presentation_id'], presentacion=u['label'],
                id_combinacion=u.get('combination_id',0), referencia_combinacion=u.get('reference',''), impacto_precio=u.get('impact',''),
                nombre_destino=(operation or {}).get('new_name',''), resultado=status, motivo=failed.get(ident,reason), stock_se_actualiza='NO')
            if 'unit_price' in ps:
                row['pum_fuente']='ACTUAL_UNIT_PRICE_SIN_CAMBIOS'
                row['pum_precio_unitario']=sync.money(sync.dec(ps['unit_price'])+sync.dec((combo or {}).get('unit_price_impact',0)))
            if e:
                row.update(nombre_corto_erp=e.get('short_name',''), nombre_erp=e['name'], erp_id=e['erp_id'], factor_conversion_precio=u['factor'],
                    inventario_erp=e['qty'], ivaid=e['tax'], precio_erp=e['gross'], unidad_erp=e['unit'], otras_listas_precios_erp=' | '.join(price_lists[e['erp_id']]))
                try:
                    row['precio_sin_impuesto_erp']=sync.money(sync.net_price(e['gross'],e['tax']))
                    if u['factor']: row['inventario_para_prestashop']=str(max(0,(sync.dec(e['qty'])/sync.dec(u['factor'])).to_integral_value(rounding=ROUND_FLOOR)))
                except ValueError: pass
            if status in ('SIN_CAMBIOS','EXCLUIDO_ERP','INACTIVO_PRESTASHOP','BLOQUEADO','PENDIENTE_PRESENTACIONES'):
                row['precio_final_sin_iva'] = actual_price
            if not reason:
                row['url_revision'] = 'http://{}/index.php?controller=product&id_product={}&id_product_attribute={}'.format(sync.test_host(settings),ident,u.get('combination_id',0))
            pum_report(row, ps, combo, decision)
            if ident in applied:
                verification = next(v for v in applied[ident]['verification']['prices'] if v['combination_id']==u['combination_id'])
                if 'unit_price_ratio' in verification: row['pum_ratio_final']=verification['unit_price_ratio']
                if 'unit_price' in verification: row['pum_precio_unitario']=verification['unit_price']
                row['pum_precio_visible_verificado']=verification.get('visible_unit_price', '')
                row.update(precio_final_sin_iva=u['net_price'], precio_visible_verificado=verification['visible_price'],
                    url_revision='http://{}/index.php?controller=product&id_product={}&id_product_attribute={}'.format(sync.test_host(settings),ident,u['combination_id']))
                if operation['mode']=='presentations' and u.get('quantity') is not None:
                    row['stock_se_actualiza']='CERO_COMBINACION_NUEVA';row['final_sync']=u['quantity']
            row.update(nombre_suguerido_prestashop=suggested, motivo_nombre_sugerido=suggestion_reason)
            row['_blister']=has_blister
            rows.append(row)
    rows.sort(key=lambda r:(r['_blister'], -sync.dec(r['factor_conversion_precio'] or 0) if not r['_blister'] else 0,
                            int(r['id_producto']), r['presentacion_id']!='BASE', str(r['presentacion_id'])))
    for row in rows: row.pop('_blister')
    if 'baseline' in snapshot:
        rows = base_congelada.report(rows, snapshot['baseline'], snapshot, price_changes(rows))
    return rows


def write_csv(path, rows, visible_reading=None):
    path=Path(path);tmp=path.with_suffix('.csv.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=LEGACY_FIELDS+EXTRA_FIELDS+precios_visibles.CSV_FIELDS);writer.writeheader()
        for row in rows:
            if visible_reading is not None:row=precios_visibles.format_verified(row, visible_reading)
            # Protect spreadsheet formulas in textual fields, preserving signed amounts.
            numeric={'factor_conversion_precio','inventario_erp','inventario_para_prestashop','inventario_mariadb','final_sync','precio_mariadb','precio_sin_impuesto_erp','ivaid','precio_erp','precio_para_prestashop','pum_ratio','pum_precio_unitario','impacto_precio','precio_final_sin_iva','precio_visible_verificado'}
            numeric.update(['precio_base_anterior', 'precio_base_nuevo', 'impacto_anterior', 'pum_ratio_final', 'pum_ratio_anterior', 'pum_ratio_propuesto', 'pum_precio_unitario_anterior', 'pum_precio_unitario_propuesto', 'pum_precio_visible_verificado', 'pum_contenido_erp', 'pum_contenido_erp_convertido', 'pum_contenido_nombre'])
            numeric.update(precios_visibles.NUMERIC)
            writer.writerow({k:("'"+str(v) if k not in numeric and str(v).lstrip().startswith(('=','+','-','@')) else v) for k,v in row.items()})
    tmp.replace(path)


def price_changes(rows):
    return [r for r in rows if r['resultado'] == 'APLICADO' and (r.get('cambio_aplicado_en_corrida') == 'SI' if r.get('base_host') else (
        sync.dec(r['precio_mariadb'] or 0) != sync.dec(r['precio_final_sin_iva'] or 0) or
        sync.dec(r['precio_base_anterior']) != sync.dec(r['precio_base_nuevo']) or
        sync.dec(r['impacto_anterior'] or 0) != sync.dec(r['impacto_precio'] or 0) or r.get('pum_cambio_aplicado') == 'SI'))]


def run(args, settings):
    started = time.monotonic()
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output = Path(args.output) if args.output else sync.ROOT/'reports'/('sincronizacion_'+stamp)
    output.mkdir(parents=True, exist_ok=False)
    initial = base_congelada.read(settings) if settings.get('baseline_host') else None
    catalog = sync.bridge(settings, ids=[])
    snapshot = dict(catalog)
    if args.product:
        snapshot['products'] = [p for p in catalog['products'] if p['id'] in args.product]
    if initial is not None:
        snapshot['baseline'] = initial
    erp = sync.erp_read(settings, (initial or snapshot)['products'])
    plan = sync.build_plan(snapshot, erp, settings)
    visible_before = precios_visibles.read(settings, snapshot, plan)
    selected_ids = {p['id'] for p in snapshot['products']}
    visible_initial = precios_visibles.read(settings, dict(products=[p for p in initial['products'] if p['id'] in selected_ids]), baseline=True) if initial is not None else visible_before
    workbook_path = output/('stock_auditoria_'+stamp+'.xlsx')
    fields = LEGACY_FIELDS + EXTRA_FIELDS + libro_auditoria.FIELDS
    audit_rows = precios_visibles.enrich(report_rows(snapshot, erp, plan, settings), initial, catalog, visible_before, visible_initial)
    sheets = libro_auditoria.classify(audit_rows, erp, catalog, settings, fields, initial_catalog=initial, stock_visibility=visible_before.get('stock_visibility'))
    libro_auditoria.validate_price_plan(plan, sheets)
    sheet_counts = libro_auditoria.write(workbook_path, sheets, fields)
    print('Libro: '+str(workbook_path), flush=True)
    # Large raw ERP evidence is optional for a job running 144 times/day.
    if args.evidence:
        for name,value in [('snapshot',snapshot),('catalog',catalog),('erp',erp),('plan',plan),('precios_visibles_antes',visible_before),('precios_visibles_base',visible_initial)]: sync.write_json(output/(name+'.json'),value)
    changes_path = output/('cambios_precios_'+stamp+'.csv')
    write_csv(changes_path, [])
    journal = aplicar_precios.apply(plan, settings, output) if args.apply else None
    rows = report_rows(snapshot, erp, plan, settings, journal)
    if args.apply:
        visible_after = precios_visibles.read(settings, snapshot)
        sync.write_json(output/'precios_visibles_despues.json', visible_after)
        audit_rows = precios_visibles.enrich([dict(r) for r in rows], initial, catalog, visible_before, visible_initial, visible_after)
        sheets = libro_auditoria.classify(audit_rows, erp, catalog, settings, fields, initial_catalog=initial, stock_visibility=visible_after.get('stock_visibility'))
        sheet_counts = libro_auditoria.write(workbook_path, sheets, fields)
    changes_path = output/('cambios_precios_'+stamp+'.csv')
    changes = price_changes(rows)
    write_csv(changes_path, changes, visible_before)
    counts = {state:len({r['id_producto'] for r in rows if r['resultado']==state}) for state in {r['resultado'] for r in rows}}
    visible_counts = dict(collections.Counter(r['verificacion_precio_visible'] for r in audit_rows))
    technical_counts = dict(collections.Counter(r['verificacion_precio_visible_tecnica'] for r in audit_rows))
    summary = dict(visible_prices=visible_counts, visible_prices_technical=technical_counts, currency=precios_visibles.currency(visible_before), target=sync.target(settings), baseline=(initial or {}).get('target'), baseline_hash=sync.digest(initial) if initial else None, apply=args.apply, products=len(snapshot['products']), states=counts,
                   workbook=str(workbook_path), sheets=sheet_counts, changes_csv=str(changes_path), changed_rows=len(changes),
                   duration_seconds=round(time.monotonic()-started,3),
                   all_resolved=not visible_counts.get('DIFIERE_REVISAR') and not technical_counts.get('DIFIERE_REVISAR') and not any(counts.get(k,0) for k in ['BLOQUEADO','ERROR','PROPUESTO','PENDIENTE_PRESENTACIONES']))
    sync.write_json(output/'resumen.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 2 if args.apply and not summary['all_resolved'] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Actualizar precios y PUM de productos existentes')
    parser.add_argument('--product',type=int,action='append')
    parser.add_argument('--output',help='Directorio nuevo para informes')
    parser.add_argument('--settings',default=str(sync.ROOT/'settings.json'))
    parser.add_argument('--evidence',action='store_true',help='Guardar además lectura ERP, catálogo y plan completos')
    args = parser.parse_args()
    settings = sync.read_json(args.settings)
    lock_path = sync.ROOT/'reports/catalogo.lock'; lock_path.parent.mkdir(exist_ok=True)
    with lock_path.open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('OMITIDO: otra sincronizacion o preparacion sigue en curso')
            return 0
        return run(args,settings)


if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as error:
        print('ERROR: '+str(error),file=sys.stderr);sys.exit(1)
