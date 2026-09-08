#!/usr/bin/env python3
"""Adapta PrestaShop y el sincronizador a una IP LAN ya asignada al servidor."""
import argparse
import datetime
import fcntl
import json
from pathlib import Path
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

import sync


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_http(host):
    """Never follow a redirect to production, and bypass proxy environment variables."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    url = 'http://' + host + '/'
    for _ in range(5):
        try:
            response = opener.open(url, timeout=30)
        except urllib.error.HTTPError as error:
            if error.code not in (301, 302, 303, 307, 308):
                raise RuntimeError('La tienda devuelve HTTP {}'.format(error.code))
            destination = urllib.parse.urljoin(url, error.headers.get('Location', ''))
            parsed = urllib.parse.urlsplit(destination)
            if parsed.hostname != host or parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
                raise RuntimeError('Redireccion fuera de la nueva IP; se detuvo la comprobacion')
            url = destination
            continue
        with response:
            body = response.read(2 * 1024 * 1024)
            if response.status != 200 or b'<html' not in body.lower():
                raise RuntimeError('La respuesta HTTP no parece una pagina de la tienda')
            return dict(url=url, status=response.status, bytes=len(body))
    raise RuntimeError('Demasiadas redirecciones al verificar la tienda')


def migration(settings, host, **kwargs):
    payload = dict(prestashop_root=settings['prestashop_root'], test_host=host)
    payload.update(kwargs)
    return sync.invoke(['php', str(sync.ROOT / 'cambiar_ip.php')], payload)


def run(args):
    settings_path = sync.ROOT / 'settings.json'
    settings = sync.read_json(settings_path)
    host = sync.test_host(dict(settings, test_host=args.ip))
    # Share the catalog apply lock so the endpoint cannot move mid-synchronization.
    reports = sync.ROOT / 'reports'
    reports.mkdir(exist_ok=True)
    with (reports / 'apply.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        preview = migration(settings, host)
        print('Dominio actual: {} | IP propuesta: {}'.format(preview['old_ip'], host))
        print('Destino: mercaboy_pruebas / tienda 1. La interfaz de red ya debe tener esa IP.')
        if not args.apply:
            print('Vista previa: ShopUrl, dominios, .htaccess, cache Smarty y settings.json.')
            print('Para aplicar: sudo python3 cambiar_ip.py {} --apply'.format(host))
            return
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        backup = reports / ('cambio_ip_' + stamp)
        backup.mkdir(mode=0o700)
        shutil.copy2(str(settings_path), str(backup / 'settings.json'))
        shutil.copy2('/var/www/html/.htaccess', str(backup / 'htaccess.anterior'))
        state = dict(status='INICIADO', previous=preview, new_ip=host)
        sync.write_json(backup / 'estado.json', state)
        try:
            result = migration(settings, host, apply=True, expected_before=preview['before'])
            state.update(status='DOMINIO_APLICADO', native=result)
            sync.write_json(backup / 'estado.json', state)
            settings['test_host'] = host
            sync.write_json(settings_path, settings)
            state['status'] = 'CONFIGURACION_APLICADA'
            sync.write_json(backup / 'estado.json', state)
            state['http'] = check_http(host)
            snapshot = sync.bridge(settings, ids=[7159])
            if snapshot['target'] != sync.target(settings):
                raise RuntimeError('El sincronizador no reconoce el nuevo destino')
            state['status'] = 'APLICADO_Y_VERIFICADO'
            sync.write_json(backup / 'estado.json', state)
            print('Tienda disponible: {}'.format(state['http']['url']))
            print('HTTP 200 y lectura del sincronizador comprobados.')
            if result.get('cache_warning'):
                print(result['cache_warning'])
            print('Respaldo y registro: {}'.format(backup))
            print('Los planes CSV anteriores conservan su IP original: genere una nueva auditoria antes de aplicar productos.')
        except Exception:
            state['verification'] = 'ERROR; revisar estado y repetir comando tras corregir la causa'
            sync.write_json(backup / 'estado.json', state)
            print('Consulte el registro: {}'.format(backup / 'estado.json'), file=sys.stderr)
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ip', help='Nueva IPv4 privada ya asignada al servidor, por ejemplo 192.168.0.229')
    parser.add_argument('--apply', action='store_true', help='Aplica el cambio; sin esta opcion solo muestra la propuesta')
    try:
        run(parser.parse_args())
    except (ValueError, RuntimeError, OSError, KeyError, urllib.error.URLError) as exc:
        print('ERROR: {}'.format(exc), file=sys.stderr)
        sys.exit(1)
