#!/usr/bin/env python3
"""Validate native front-office refresh responses without cart/order mutations."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.parse
import urllib.request

from cambiar_ip import NoRedirect
import sync


class VisiblePrice(HTMLParser):
    def __init__(self):
        super().__init__()
        self.price = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'current-price-value' in attrs.get('class', '').split():
            self.price = Decimal(attrs['content'])


def validate(host, operation, expected, combination):
    payload = dict(id_product=operation['id'], id_product_attribute=expected['combination_id'], qty=1, ajax=1, action='refresh')
    for attribute in (combination or {}).get('attributes', []):
        payload['group[{}]'.format(attribute['id_attribute_group'])] = attribute['id_attribute']
    url = 'http://' + host + '/index.php?controller=product&id_product=' + str(operation['id'])
    request = urllib.request.Request(url, data=urllib.parse.urlencode(payload).encode(),
                                     headers={'X-Requested-With': 'XMLHttpRequest'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=50) as response:
        body = json.load(response)
    actual_id = int(body['id_product_attribute'] or 0)
    parser = VisiblePrice()
    parser.feed(body['product_prices'])
    if actual_id != int(expected['combination_id']):
        raise ValueError('El selector devuelve otra combinacion')
    if parser.price is None or abs(parser.price - sync.dec(expected['visible_price'])) > Decimal('.51'):
        raise ValueError('Precio HTTP diferente al motor nativo')
    parsed_url = urllib.parse.urlsplit(body['product_url'])
    if parsed_url.hostname != host:
        raise ValueError('La URL de producto apunta a otro servidor')
    return dict(product_id=operation['id'], combination_id=actual_id,
                visible_price=str(parser.price), url=body['product_url'], status='OK')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    settings = sync.read_json(sync.ROOT / 'settings.json')
    host = sync.test_host(settings)
    journal = sync.read_json(args.journal)
    if journal['target'] != sync.target(settings):
        raise ValueError('Diario de otro destino')
    products = sync.bridge(settings, ids=[r['operation']['id'] for r in journal['results']])['products']
    products = {p['id']: p for p in products}
    jobs = []
    for result in journal['results']:
        operation = result['operation']
        for expected in result['verification']['prices']:
            combination = next((c for c in products[operation['id']]['combinations'] if c['id'] == expected['combination_id']), None)
            jobs.append((operation, expected, combination))
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(validate, host, *job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                results.append(future.result())
            except Exception as error:
                errors.append(dict(product_id=job[0]['id'], combination_id=job[1]['combination_id'], error=str(error)))
            if (len(results) + len(errors)) % 20 == 0:
                print('Verificadas {} / {} respuestas de precios; errores {}'.format(len(results) + len(errors), len(jobs), len(errors)), flush=True)
    results.sort(key=lambda r: (r['product_id'], r['combination_id']))
    sync.write_json(Path(args.output), dict(target=sync.target(settings), results=results, errors=errors))
    print('Precios HTTP correctos: {}; errores: {}'.format(len(results), len(errors)))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
