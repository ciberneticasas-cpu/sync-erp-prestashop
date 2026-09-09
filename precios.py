"""Plan de precios exclusivamente sobre productos y combinaciones existentes."""
import collections
import datetime
import match_erp
import vigencia
import sync
import pum


def build_plan(snapshot, erp, settings):
    if snapshot['target'] != sync.target(settings) or erp['host'] != '192.168.0.231':
        raise ValueError('Destino protegido')
    operations, rows, unchanged, pum_decisions = [], [], 0, {}
    prepared = match_erp.index(erp)
    presentations = collections.defaultdict(list)
    for record in erp['presentations']:
        presentations[record['erp_id']].append(record)
    for ps in snapshot['products']:
        e = None
        if str(ps['active']) != '1':
            continue
        try:
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
                if any(sync.norm(a['group_name']) == 'presentacion' for c in ps['combinations'] for a in c['attributes']):
                    raise ValueError('PENDIENTE_PRESENTACIONES: ERP_SIN_ALTERNATIVAS_CON_COMBINACIONES_WEB')
                if any(w in sync.norm(ps['name']) for w in ('fraccion', 'blister')) and not mapping.get('simple_factor'):
                    raise ValueError('FRACCION_SIN_PRESENTACION_ERP_CONFIRMADA')
                factor = mapping.get('simple_factor', erp['legacy_factors'].get('{}:{}'.format(ps['id'], e['erp_id'])))
                if factor is None or sync.dec(factor) <= 0:
                    raise ValueError('FALTA_FACTOR_HEREDADO_O_MAPEO_EXPLICITO')
                base = sync.money(sync.net_price(e['gross'], e['tax']) * sync.dec(factor))
                units[0].update(factor=str(factor), net_price=base, impact='0.000000', combination_id=0,
                                reference=ps['reference'], quantity=None, default=False)
                mode = 'simple'
            else:
                base = sync.money(sync.net_price(e['gross'], e['tax']))
                used = set()
                for u in units:
                    configured = mapping.get('presentations', {}).get(u['presentation_id'], {})
                    u['label'] = configured.get('label', 'Caja' if u['presentation_id'] == 'BASE' and sync.norm(e['unit']) in ('caja', 'cja', 'cj') else u['label'])
                    combo = sync.match_combination(ps, u, configured)
                    if not combo:
                        raise ValueError('PENDIENTE_PRESENTACIONES: ejecutar corregirPresentacionBlister')
                    if combo['id'] in used:
                        raise ValueError('COMBINACION_ASIGNADA_DOS_VECES')
                    used.add(combo['id'])
                    u.update(combination_id=combo['id'], reference=combo['reference'], label=combo['attributes'][0]['label'],
                             impact=sync.money(sync.dec(u['net_price']) - sync.dec(base)), quantity=None,
                             default=bool(combo.get('default_on')))
                if used != {c['id'] for c in ps['combinations']}:
                    raise ValueError('PENDIENTE_PRESENTACIONES: COMBINACIONES_SOLO_WEB_REVISAR_RETIRO')
                mode = 'presentations'
            current = {c['id']: c for c in ps['combinations']}
            pum_update = pum.plan(ps, e, units, base)
            pum_decisions[str(ps['id'])] = pum_update
            changed = sync.dec(ps['price']) != sync.dec(base) or any(
                u['combination_id'] and sync.dec(current[u['combination_id']]['price']) != sync.dec(u['impact']) for u in units)
            if not changed and not pum_update['changed']:
                unchanged += 1
                continue
            op = dict(id=ps['id'], before=ps, mode=mode, prices_only=True, base_price=base,
                      presentations=units, erp_product=e, erp_presentations=records,
                      stage_disabled=False, preview_only=False, new_name='', pum=pum_update)
            operations.append(op)
            rows.extend(sync.row_for(ps, e, u, estado='PROPUESTO', motivo='PRECIO_Y_PUM' if changed and pum_update['changed'] else 'SOLO_PRECIO' if changed else 'SOLO_PUM') for u in units)
        except (ValueError, ArithmeticError) as error:
            if isinstance(error, vigencia.Excluded):
                e = error.products[0] if len(error.products) == 1 else None
            rows.append(sync.row_for(ps, e, estado='BLOQUEADO', motivo=str(error)))
    return dict(version=3, target=sync.target(settings), created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                settings=settings, operations=operations, rows=rows, unchanged=unchanged, pum_decisions=pum_decisions)
