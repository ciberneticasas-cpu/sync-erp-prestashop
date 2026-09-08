#!/usr/bin/env python3
"""Export one review CSV with original proposal, actual changes and storefront links."""
import argparse
import csv
from pathlib import Path
import sync


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--journal', required=True)
    parser.add_argument('--http', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    plan, journal, http = (sync.read_json(path) for path in (args.plan, args.journal, args.http))
    settings = sync.read_json(sync.ROOT / 'settings.json')
    if any(source['target'] != sync.target(settings) for source in (plan, journal, http)):
        raise ValueError('Los informes corresponden a otro destino')
    results = {r['operation']['id']: r for r in journal['results']}
    current = {p['id']: p for p in sync.bridge(settings, ids=list(results))['products']}
    checked = {(r['product_id'], r['combination_id']): r for r in http['results']}
    for ident, result in results.items():
        op, product = result['operation'], current[ident]
        if sync.dec(product['price']) != sync.dec(op['base_price']):
            raise ValueError('Precio padre cambio despues de aplicar')
        if op.get('preview_only') and (str(product['active']) != '1' or str(product['available_for_order']) != '0'):
            raise ValueError('Estado de vista previa incorrecto')
        combos = {c['id']: c for c in product['combinations']}
        for unit in op['presentations']:
            if unit['combination_id']:
                combo = combos[unit['combination_id']]
                if sync.dec(combo['price']) != sync.dec(unit['impact']) or combo['reference'] != unit['reference']:
                    raise ValueError('Combinacion cambio despues de aplicar')
                if int(combo['minimal_quantity']) != 1 or (unit['default'] and int(product['cache_default_attribute']) != combo['id']):
                    raise ValueError('Minimo/predeterminada incorrectos')
    extra = ['resultado_aplicacion', 'id_combinacion_final', 'precio_padre_final_sin_iva',
             'impacto_final', 'precio_presentacion_final_sin_iva', 'precio_visible_verificado', 'url_revision']
    output = Path(args.output)
    with output.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=sync.FIELDS + extra)
        writer.writeheader()
        for original in plan['rows']:
            row = dict(original)
            row.update({field: '' for field in extra})
            ident = int(row['id_producto'])
            row['resultado_aplicacion'] = 'SIN_CAMBIOS_' + row['estado']
            if row['estado'] == 'PROPUESTO' and ident in results:
                op = results[ident]['operation']
                unit = next(u for u in op['presentations'] if u['presentation_id'] == row['presentacion_id'])
                front = checked.get((ident, unit['combination_id']))
                row.update(autorizar='SI', resultado_aplicacion='APLICADO_HTTP_OK' if front else 'APLICADO_HTTP_PENDIENTE',
                           id_combinacion_final=str(unit['combination_id']), precio_padre_final_sin_iva=op['base_price'],
                           impacto_final=unit['impact'], precio_presentacion_final_sin_iva=unit['net_price'],
                           precio_visible_verificado=front['visible_price'] if front else '', url_revision=front['url'] if front else '')
            writer.writerow(sync.csv_safe(row))
    print('CSV consolidado: {}'.format(output))


if __name__ == '__main__':
    main()
