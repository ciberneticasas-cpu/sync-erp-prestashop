#!/usr/bin/env python3
"""Audit by default; --apply updates all valid prices through native PrestaShop objects."""
import argparse
import collections
import csv
import datetime
from decimal import Decimal, ROUND_FLOOR
import json
from pathlib import Path
import subprocess
import sys
import match_erp
import sync

LEGACY_FIELDS = 'referencia,nombre_prestashop,nombre_corto_erp,factor_conversion_precio,inventario_erp,inventario_para_prestashop,inventario_mariadb,pendiente,final_sync,precio_mariadb,precio_sin_impuesto_erp,ivaid,precio_erp,precio_para_prestashop,pum_fuente,pum_unidad,pum_ratio,pum_precio_unitario,otras_listas_precios_erp,erp_host,accion,unidad_erp,unidad_mariadb_inferida'.split(',')
EXTRA_FIELDS = 'id_producto,erp_id,criterio_match,observacion_match,nombre_erp,presentacion_id,presentacion,id_combinacion,referencia_combinacion,impacto_precio,nombre_destino,resultado,motivo,precio_final_sin_iva,precio_visible_verificado,url_revision,stock_se_actualiza'.split(',')


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
    for ps in snapshot['products']:
        ident = ps['id']; mapping = settings.get('mappings', {}).get(str(ident), {})
        operation = applied.get(ident, {}).get('operation', operations.get(ident))
        reason = '; '.join(sorted(set(blocked[ident])))
        e, criterion, warning, units = None, '', '', []
        try:
            e, criterion, warning = match_erp.resolve(ps, erp, mapping, prepared)
            warning = mapping.get('match_note', warning)
            if e['manages'] == 'S' and not presentations[e['erp_id']]:
                warning += '; ERP indica presentaciones sin definicion vendible: solo precio de la unidad existente'
            if operation:
                units = operation['presentations']
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
        if not units: units = [dict(presentation_id='BASE', label='', factor='', net_price='', combination_id=0)]
        has_blister = any('blister' in sync.norm(u['label']) or sync.norm(u['label']) == 'sobre' for u in units) or any('blister' in sync.norm(r['label']) for r in presentations.get((e or {}).get('erp_id'), [])) or any('blister' in sync.norm(a['label']) for c in ps['combinations'] for a in c['attributes'])
        for u in units:
            row = {field: '' for field in LEGACY_FIELDS + EXTRA_FIELDS}
            combo = next((c for c in ps['combinations'] if c['id'] == u.get('combination_id')), None)
            actual_price = sync.money(sync.dec(ps['price']) + sync.dec((combo or {}).get('price', 0))) if combo or u['presentation_id']=='BASE' else ''
            stock = (combo or {}).get('quantity', ps.get('quantity', '') if u['presentation_id']=='BASE' else '')
            status = 'ERROR' if ident in failed else 'APLICADO' if ident in applied else 'BLOQUEADO' if reason else 'PROPUESTO' if operation else 'SIN_CAMBIOS'
            row.update(referencia=ps['reference'], nombre_prestashop=ps['name'], inventario_mariadb=stock,
                final_sync=stock, precio_mariadb=actual_price, precio_para_prestashop=u['net_price'],
                pum_fuente='ACTUAL_SIN_CAMBIOS', pum_unidad=ps.get('unity',''), pum_ratio=ps.get('unit_price_ratio',''),
                erp_host='192.168.0.231', accion='ACTUALIZAR_PRECIO_PRESENTACIONES' if operation and operation['mode']=='presentations' else 'ACTUALIZAR_PRECIO' if operation else status,
                id_producto=ident, criterio_match=criterion, observacion_match=warning, presentacion_id=u['presentation_id'], presentacion=u['label'],
                id_combinacion=u.get('combination_id',0), referencia_combinacion=u.get('reference',''), impacto_precio=u.get('impact',''),
                nombre_destino=(operation or {}).get('new_name',''), resultado=status, motivo=failed.get(ident,reason), stock_se_actualiza='NO')
            if actual_price and sync.dec(ps.get('unit_price_ratio') or 0)>0:
                row['pum_precio_unitario']=sync.money(sync.dec(actual_price)/sync.dec(ps['unit_price_ratio']))
            if e:
                row.update(nombre_corto_erp=e.get('short_name',''), nombre_erp=e['name'], erp_id=e['erp_id'], factor_conversion_precio=u['factor'],
                    inventario_erp=e['qty'], ivaid=e['tax'], precio_erp=e['gross'], unidad_erp=e['unit'], otras_listas_precios_erp=' | '.join(price_lists[e['erp_id']]))
                try:
                    row['precio_sin_impuesto_erp']=sync.money(sync.net_price(e['gross'],e['tax']))
                    if u['factor']: row['inventario_para_prestashop']=str(max(0,(sync.dec(e['qty'])/sync.dec(u['factor'])).to_integral_value(rounding=ROUND_FLOOR)))
                except ValueError: pass
            if status == 'SIN_CAMBIOS':
                row['precio_final_sin_iva'] = actual_price
            if not reason:
                row['url_revision'] = 'http://{}/index.php?controller=product&id_product={}&id_product_attribute={}'.format(sync.test_host(settings),ident,u.get('combination_id',0))
            if ident in applied:
                verification = next(v for v in applied[ident]['verification']['prices'] if v['combination_id']==u['combination_id'])
                row.update(precio_final_sin_iva=u['net_price'], precio_visible_verificado=verification['visible_price'],
                    url_revision='http://{}/index.php?controller=product&id_product={}&id_product_attribute={}'.format(sync.test_host(settings),ident,u['combination_id']))
                if operation['mode']=='presentations' and u.get('quantity') is not None:
                    row['stock_se_actualiza']='CERO_COMBINACION_NUEVA';row['final_sync']=u['quantity']
            row['_blister']=has_blister
            rows.append(row)
    rows.sort(key=lambda r:(r['_blister'], -sync.dec(r['factor_conversion_precio'] or 0) if not r['_blister'] else 0,
                            int(r['id_producto']), r['presentacion_id']!='BASE', str(r['presentacion_id'])))
    for row in rows: row.pop('_blister')
    return rows


def write_csv(path, rows):
    path=Path(path);tmp=path.with_suffix('.csv.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=LEGACY_FIELDS+EXTRA_FIELDS);writer.writeheader()
        for row in rows:
            # Protect spreadsheet formulas in textual fields, preserving signed amounts.
            numeric={'factor_conversion_precio','inventario_erp','inventario_para_prestashop','inventario_mariadb','final_sync','precio_mariadb','precio_sin_impuesto_erp','ivaid','precio_erp','precio_para_prestashop','pum_ratio','pum_precio_unitario','impacto_precio','precio_final_sin_iva','precio_visible_verificado'}
            writer.writerow({k:("'"+str(v) if k not in numeric and str(v).lstrip().startswith(('=','+','-','@')) else v) for k,v in row.items()})
    tmp.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Aplicar todos los productos resolubles; sin esta opcion solo audita')
    parser.add_argument('--product',type=int,action='append')
    parser.add_argument('--output',help='Directorio nuevo para CSV y evidencia JSON')
    args=parser.parse_args()
    settings=sync.read_json(sync.ROOT/'settings.json')
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    output=Path(args.output) if args.output else sync.ROOT/'reports'/('sincronizacion_'+stamp)
    output.mkdir(parents=True,exist_ok=False)
    snapshot=sync.bridge(settings,ids=args.product or [])
    if not args.product: snapshot['products']=[p for p in snapshot['products'] if str(p['active'])=='1']
    erp=sync.erp_read(settings,snapshot['products']);plan=sync.build_plan(snapshot,erp,settings)
    for name,value in [('snapshot',snapshot),('erp',erp),('plan',plan)]:sync.write_json(output/(name+'.json'),value)
    csv_path=output/('stock_auditoria_'+stamp+'.csv')
    write_csv(csv_path,report_rows(snapshot,erp,plan,settings))
    print('CSV: '+str(csv_path),flush=True)
    journal=None
    if args.apply:
        subprocess.check_call([sys.executable,str(sync.ROOT/'corregir_blister.py'),'--apply'])
        if plan['operations']:
            sync.apply(argparse.Namespace(plan=str(output/'plan.json'),plan_sha256=sync.digest(plan),direct_apply=True),settings)
            journal=sync.read_json(output/'aplicacion.json')
    rows=report_rows(snapshot,erp,plan,settings,journal)
    browser_errors = []
    if args.apply:
        verification_path = output/'verificacion_presentaciones.json'
        verification_status = subprocess.call([sys.executable,str(sync.ROOT/'verificar_presentaciones.py'),'--output',str(verification_path)])
        if verification_path.exists():
            verified = sync.read_json(verification_path)
            browser_errors = verified['errors']
            by_combination = {(r['product_id'],r['combination_id']):r for r in verified['results']}
            for row in rows:
                front = by_combination.get((int(row['id_producto']),int(row['id_combinacion'] or 0)))
                if front:
                    row['precio_visible_verificado'] = front['visible_price']; row['url_revision'] = front['url']
        if verification_status and not browser_errors: browser_errors = [{'error':'No se pudo completar la verificacion de presentaciones'}]
    write_csv(csv_path,rows)
    counts={state:len({r['id_producto'] for r in rows if r['resultado']==state}) for state in {r['resultado'] for r in rows}}
    summary=dict(target=sync.target(settings),apply=args.apply,products=len(snapshot['products']),states=counts,csv=str(csv_path),all_resolved=not browser_errors and not any(counts.get(k,0) for k in ['BLOQUEADO','ERROR','PROPUESTO']),browser_errors=browser_errors)
    sync.write_json(output/'resumen.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
    if args.apply and not summary['all_resolved']: return 2
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as error:
        print('ERROR: '+str(error),file=sys.stderr);sys.exit(1)
