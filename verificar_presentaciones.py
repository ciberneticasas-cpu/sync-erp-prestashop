#!/usr/bin/env python3
"""Read-only check of every native presentation and its storefront refresh response."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
import json
import urllib.parse
import urllib.request
from cambiar_ip import NoRedirect
import sync
from validar_tienda import VisiblePrice

class Structure(HTMLParser):
    def __init__(self):
        super().__init__();self.wrapper=0;self.options=set();self.availability=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'product-add-to-cart' in a.get('class','').split():self.wrapper+=1
        if a.get('id')=='product-availability':self.availability+=1
        if tag in ('input','option') and 'value' in a:self.options.add(a['value'])


def check(host, product, combination, native):
    payload={'id_product':product['id'],'id_product_attribute':combination['id'],'qty':1,'ajax':1,'action':'refresh'}
    for attr in combination['attributes']:payload['group[{}]'.format(attr['id_attribute_group'])]=attr['id_attribute']
    url='http://{}/index.php?controller=product&id_product={}'.format(host,product['id'])
    request=urllib.request.Request(url,data=urllib.parse.urlencode(payload).encode(),headers={'X-Requested-With':'XMLHttpRequest'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(request,timeout=50) as r:body=json.load(r)
    assert int(body['id_product_attribute'])==combination['id'],'La respuesta corresponde a otra combinacion'
    price=VisiblePrice();price.feed(body['product_prices'])
    assert price.price is not None and abs(price.price-sync.dec(native['visible_price']))<sync.dec('.51'),'Precio diferente del motor nativo'
    block=Structure();block.feed(body['product_add_to_cart'])
    assert block.wrapper==1 and block.availability==1,'Bloque de compra incompleto: riesgo de Undefined'
    variants=Structure();variants.feed(body['product_variants'])
    assert all(str(a['id_attribute']) in variants.options for a in combination['attributes']),'Falta opcion en selector'
    assert urllib.parse.urlsplit(body['product_url']).hostname==host,'Enlace fuera del clon'
    return {'product_id':product['id'],'combination_id':combination['id'],'visible_price':str(price.price),'url':body['product_url'],'status':'OK'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    settings=sync.read_json(sync.ROOT/'settings.json');host=sync.test_host(settings)
    products=[p for p in sync.bridge(settings)['products'] if str(p['active'])=='1' and len(p['combinations'])>1 and all(sync.norm(a['group_name'])=='presentacion' for c in p['combinations'] for a in c['attributes'])]
    prices={}
    for start in range(0,len(products),20):
        for p in sync.bridge(settings,'prices',ids=[p['id'] for p in products[start:start+20]]):prices[p['id']]={c['combination_id']:c for c in p['prices']}
    results=[];errors=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(check,host,p,c,prices[p['id']][c['id']]):(p['id'],c['id']) for p in products for c in p['combinations']}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as error:errors.append({'product_id':futures[future][0],'combination_id':futures[future][1],'error':str(error)})
            if (len(results)+len(errors))%30==0:print('Verificadas {} / {}; errores {}'.format(len(results)+len(errors),len(futures),len(errors)),flush=True)
    sync.write_json(Path(args.output),{'target':sync.target(settings),'products':len(products),'results':sorted(results,key=lambda r:(r['product_id'],r['combination_id'])),'errors':errors})
    print('Productos: {}; respuestas correctas: {}; errores: {}'.format(len(products),len(results),len(errors)))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
