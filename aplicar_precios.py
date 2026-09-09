"""Un solo proceso PrestaShop por lote, con recibos persistidos por producto."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import sync


def apply(plan, settings, output):
    operations = plan['operations']
    state = dict(target=sync.target(settings), results=[], errors=[], status='INICIADO')
    journal = output / 'aplicacion.json'
    sync.write_json(journal, state)
    if not operations:
        state['status'] = 'SIN_CAMBIOS'
        sync.write_json(journal, state)
        return state
    # Recheck ERP economics once; stock is not published by this program.
    erp = sync.erp_read(settings, [o['before'] for o in operations])
    products = {p['erp_id']: p for p in erp['products']}
    presentations = {}
    for p in erp['presentations']:
        presentations.setdefault(p['erp_id'], []).append(p)
    economics = lambda p: {k: v for k, v in p.items() if k != 'qty'}
    fresh = []
    for o in operations:
        ident = o['erp_product']['erp_id']
        if economics(products.get(ident, {})) != economics(o['erp_product']) or presentations.get(ident, []) != o['erp_presentations']:
            state['errors'].append(dict(product_id=o['id'], error='ERP_CAMBIO_REINTENTAR_PROXIMA_EJECUCION'))
        else:
            fresh.append(o)
    operations = fresh
    if not operations:
        state['status'] = 'APLICADO_CON_ERRORES'
        sync.write_json(journal, state)
        return state
    initial_errors = len(state['errors'])
    payload = dict(prestashop_root=settings['prestashop_root'], env_file=settings['env_file'],
                   test_host=sync.test_host(settings), SERVIDOR_CONGELADO=sync.frozen_host(settings), authorization='CLI_APPLY_TEST_ONLY', operations=operations)
    # Temporary input avoids pipe deadlock on large plans. No credentials in payload.
    with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as errors, (output / 'recibos.jsonl').open('w') as receipts:
        source.write(sync.canonical(payload)); source.seek(0)
        process = subprocess.Popen(['php', str(sync.ROOT / 'bridge.php'), 'apply-prices'], stdin=source, stdout=subprocess.PIPE, stderr=errors)
        selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
        pending = b''
        try:
            while True:
                if not selector.select(180):
                    raise RuntimeError('PrestaShop sin respuesta durante 180 segundos; revisar recibos')
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk: break
                pending += chunk
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    event = json.loads(line)
                    receipts.write(json.dumps(event, ensure_ascii=False) + '\n'); receipts.flush(); os.fsync(receipts.fileno())
                    if 'result' in event: state['results'].append(event['result'])
                    else: state['errors'].append(event['error'])
                    if (len(state['results']) + len(state['errors'])) % 100 == 0:
                        print('Procesados {} precios; errores {}'.format(len(state['results']), len(state['errors'])), flush=True)
            code = process.wait(timeout=10)
            if code or pending or len(state['results']) + len(state['errors']) - initial_errors != len(operations):
                raise RuntimeError('Lote interrumpido; revisar recibos.jsonl antes de repetir')
            state['status'] = 'APLICADO_CON_ERRORES' if state['errors'] else 'APLICADO_Y_VERIFICADO'
        except Exception:
            state['status'] = 'INTERRUMPIDO_REVISAR_RECIBOS'
            raise
        finally:
            selector.close()
            if process.poll() is None: process.kill(); process.wait()
            sync.write_json(journal, state)
    return state
