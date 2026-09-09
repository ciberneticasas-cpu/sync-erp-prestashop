"""Plan de precios exclusivamente sobre productos y combinaciones existentes."""
import collections
import datetime
import match_erp
import vigencia
import sync
import pum
import base_congelada
import copy


def build_plan(snapshot, erp, settings):
    if snapshot['target'] != sync.target(settings) or erp['host'] != '192.168.0.231':
        raise ValueError('Destino protegido')
    if settings.get('baseline_host') and 'baseline' not in snapshot:
        raise ValueError('FALTA_LECTURA_BASE_CONGELADA: ejecutar sincronizar.py')
    operations, rows, unchanged, pum_decisions = [], [], 0, {}
    prepared = match_erp.index(erp)
    presentations = collections.defaultdict(list)
    for record in erp['presentations']:
        presentations[record['erp_id']].append(record)
    frozen = {p['id']: p for p in snapshot.get('baseline', {}).get('products', [])}
    for dest in snapshot['products']:
        ps = frozen.get(dest['id'], dest)
        e = None
        if str(ps['active']) != '1':
            continue
        try:
            if str(dest.get('active')) != '1':
                raise ValueError('DESTINO_PRESTASHOP_NO_ACTIVO')
            if 'baseline' in snapshot and dest['id'] not in frozen:
                raise ValueError('PRODUCTO_SIN_BASE_CONGELADA')
            mapping = settings.get('mappings', {}).get(str(ps['id']), {})
            if ps['product_type'] in ('pack', 'virtual'):
                raise ValueError('TIPO_PRODUCTO_NO_COMPATIBLE')
            e, criterion, warning = match_erp.resolve(ps, erp, mapping, prepared)
            if warning:
                raise ValueError('MATCH_DISCREPANTE_REQUIERE_REVISION: ' + warning)
            if sync.dec(ps['ecotax']) != 0:
                raise ValueError('ECOTASA_REQUIERE_REVISION')
            records = presentations[e['erp_id']]
            units, aliases, issues = sync.presentations_for(e, records)
            if issues:
                raise ValueError('; '.join(issues))
            if len(units) == 1:
                if any(sync.norm(a['group_name']) == 'presentacion' for c in dest['combinations'] for a in c['attributes']):
                    raise ValueError('PENDIENTE_PRESENTACIONES: ERP_SIN_ALTERNATIVAS_CON_COMBINACIONES_WEB')
                if any(w in sync.norm(ps['name']) for w in ('fraccion', 'blister')) and not mapping.get('simple_factor'):
                    raise ValueError('FRACCION_SIN_PRESENTACION_ERP_CONFIRMADA')
                factor = mapping.get('simple_factor', erp['legacy_factors'].get('{}:{}'.format(ps['id'], e['erp_id'])))
                if factor is None or sync.dec(factor) <= 0:
                    raise ValueError('FALTA_FACTOR_HEREDADO_O_MAPEO_EXPLICITO')
                base = sync.money(sync.net_price(e['gross'], e['tax']) * sync.dec(factor))
                units[0].update(factor=str(factor), net_price=base, impact='0.000000', combination_id=0,
                                reference=dest['reference'], quantity=None, default=False)
                mode = 'simple'
            else:
                base = sync.money(sync.net_price(e['gross'], e['tax']))
                used = set()
                for u in units:
                    configured = mapping.get('presentations', {}).get(u['presentation_id'], {})
                    u['label'] = configured.get('label', 'Caja' if u['presentation_id'] == 'BASE' and sync.norm(e['unit']) in ('caja', 'cja', 'cj') else u['label'])
                    combo = sync.match_combination(dest, u, configured)
                    if not combo:
                        raise ValueError('PENDIENTE_PRESENTACIONES: ejecutar corregirPresentacionBlister')
                    if combo['id'] in used:
                        raise ValueError('COMBINACION_ASIGNADA_DOS_VECES')
                    used.add(combo['id'])
                    u.update(combination_id=combo['id'], reference=combo['reference'], label=combo['attributes'][0]['label'],
                             impact=sync.money(sync.dec(u['net_price']) - sync.dec(base)), quantity=None,
                             default=bool(combo.get('default_on')))
                if used != {c['id'] for c in dest['combinations']}:
                    raise ValueError('PENDIENTE_PRESENTACIONES: COMBINACIONES_SOLO_WEB_REVISAR_RETIRO')
                mode = 'presentations'
            current = {c['id']: c for c in dest['combinations']}
            content_source = copy.deepcopy(ps)
            content_source['combinations'] = copy.deepcopy(dest['combinations'])
            if 'baseline' in snapshot and mode == 'simple':
                for combo in content_source['combinations']:
                    old = base_congelada.combination(ps, combo)
                    if not old:
                        raise ValueError('COMBINACION_SIN_BASE_CONGELADA_PARA_IMPACTO')
                    combo['price'] = old['price']
            name_factor = pum.initial_name_factor(ps, e, units) if 'baseline' in snapshot and mode == 'presentations' else '1'
            pum_update = pum.plan(content_source, e, units, base, name_factor=name_factor)
            pum_update['changed'] = pum.changed(dest, pum_update)
            pum_decisions[str(ps['id'])] = pum_update
            changed = sync.dec(dest['price']) != sync.dec(base) or any(
                u['combination_id'] and sync.dec(current[u['combination_id']]['price']) != sync.dec(u['impact']) for u in units)
            if mode == 'simple':
                changed = changed or any(sync.dec(current[c['id']]['price']) != sync.dec(c['price']) for c in content_source['combinations'])
            if not changed and not pum_update['changed']:
                unchanged += 1
                continue
            op = dict(id=ps['id'], before=dest, initial=ps, mode=mode, prices_only=True, base_price=base,
                      presentations=units, erp_product=e, erp_presentations=records,
                      stage_disabled=False, preview_only=False, new_name='', pum=pum_update)
            if mode == 'simple' and 'baseline' in snapshot:
                op['combination_prices'] = [dict(combination_id=c['id'], impact=c['price']) for c in content_source['combinations']]
            operations.append(op)
            rows.extend(sync.row_for(ps, e, u, estado='PROPUESTO', motivo='PRECIO_Y_PUM' if changed and pum_update['changed'] else 'SOLO_PRECIO' if changed else 'SOLO_PUM') for u in units)
        except (ValueError, ArithmeticError) as error:
            if isinstance(error, vigencia.Excluded):
                e = error.products[0] if len(error.products) == 1 else None
            rows.append(sync.row_for(ps, e, estado='BLOQUEADO', motivo=str(error)))
    return dict(version=3, target=sync.target(settings), created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                settings=settings, operations=operations, rows=rows, unchanged=unchanged, pum_decisions=pum_decisions)
