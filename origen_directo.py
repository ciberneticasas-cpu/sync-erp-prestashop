"""Direct production reads; all code runs on the test server, never on production."""
import copy
import sync

HOST = 'www.mercaboy.com'


def read(settings, ids=None):
    payload = dict(test_host=sync.test_host(settings), SERVIDOR_CONGELADO=sync.frozen_host(settings),
                   prestashop_root=settings['prestashop_root'], baseline_env_file=settings.get('baseline_env_file', ''), ids=ids or [])
    value = sync.invoke(['php', str(sync.ROOT/'origen_directo.php')], payload, timeout=540)
    if value.get('target') != HOST+'/mercaboy_2024/1' or not isinstance(value.get('products'), list):
        raise ValueError('ORIGEN_DIRECTO_INVALIDO')
    evidence = value.get('read_only_evidence', {})
    if not evidence.get('session_read_only') or evidence.get('source_writes_executed') != 0 or evidence.get('remote_php_executed') is not False:
        raise ValueError('ORIGEN_SIN_EVIDENCIA_SOLO_LECTURA')
    if len({p['id'] for p in value['products']}) != len(value['products']):
        raise ValueError('ORIGEN_PRODUCTOS_DUPLICADOS')
    prices(value)
    return value


def prices(catalog):
    value = copy.deepcopy(catalog.get('source_prices', {}))
    ids = {p['id'] for p in catalog['products']}
    value['prices'] = [r for r in value.get('prices', []) if r['id'] in ids]
    expected = {(p['id'], cid) for p in catalog['products'] for cid in [0]+[c['id'] for c in p['combinations']]}
    actual = {(r['id'], r['combination_id']) for r in value['prices']}
    if value.get('host') != HOST or expected != actual or len(actual) != len(value['prices']):
        raise ValueError('ORIGEN_PRECIOS_INCOMPLETOS')
    return value
