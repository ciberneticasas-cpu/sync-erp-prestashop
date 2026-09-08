#!/usr/bin/env python3
"""Real Chrome click regression, using WebDriver HTTP and Python's standard library."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import urllib.error


class Browser:
    def __init__(self, root):
        self.root = Path(root)
        self.log = (self.root / 'driver.log').open('w')
        self.driver = subprocess.Popen([str(self.root / 'chromedriver-linux64/chromedriver'), '--port=9515', '--allowed-ips=127.0.0.1'], stdout=self.log, stderr=self.log)
        self.session = None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(50):
            try:
                self.call('GET', '/status'); break
            except OSError:
                time.sleep(.1)
        capabilities = {'browserName': 'chrome', 'pageLoadStrategy': 'eager',
                        'goog:loggingPrefs': {'browser': 'ALL', 'performance': 'ALL'},
                        'goog:chromeOptions': {'binary': str(self.root / 'chrome-headless-shell-linux64/chrome-headless-shell'),
                                              'args': ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--no-proxy-server',
                                                       '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 192.168.0.229', '--window-size=1440,1000']}}
        self.session = self.call('POST', '/session', {'capabilities': {'alwaysMatch': capabilities}})['sessionId']
        self.call('POST', self.path('/goog/cdp/execute'), {'cmd': 'Network.enable', 'params': {}})
        self.call('POST', self.path('/goog/cdp/execute'), {'cmd': 'Network.setBlockedURLs', 'params': {'urls': ['*mercaboy.com*', 'https://*']}})

    def path(self, path):
        return '/session/' + self.session + path

    def call(self, method, path, data=None):
        request = urllib.request.Request('http://127.0.0.1:9515' + path,
                                         data=None if data is None else json.dumps(data).encode(), method=method,
                                         headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=60) as response:
                result = json.load(response)['value']
        except urllib.error.HTTPError as error:
            raise RuntimeError(error.read().decode()[:2000])
        if isinstance(result, dict) and result.get('error'):
            raise RuntimeError(result['error'])
        return result

    def js(self, script):
        return self.call('POST', self.path('/execute/sync'), {'script': script, 'args': []})

    def inspect(self):
        return self.js('''return {
          price: document.querySelector('#main .product-container .current-price-value')?.textContent.trim(),
          amount: document.querySelector('#main .product-container .current-price-value')?.getAttribute('content'),
          matchingVariants: document.querySelectorAll(prestashop.selectors.product.variants).length,
          formProducts: $(prestashop.selectors.product.actions).find('form:first').serializeArray().filter(x=>x.name==='id_product').map(x=>x.value),
          checked: Array.from(document.querySelectorAll('#main .product-container input[data-product-attribute]:checked')).map(x=>x.value)
        };''')

    def click(self, value):
        elements = self.call('POST', self.path('/elements'), {'using': 'css selector', 'value': '#main .product-container input[data-product-attribute="13"][value="' + str(value) + '"]'})
        if not elements:
            raise RuntimeError('No existe la opcion de presentacion')
        element = elements[0]['element-6066-11e4-a52e-4f735466cecf']
        self.call('POST', self.path('/element/' + element + '/click'), {})
        time.sleep(2)

    def close(self):
        try:
            if self.session: self.call('DELETE', self.path(''))
        finally:
            self.driver.terminate(); self.driver.wait(timeout=10); self.log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--browser-root', default='/tmp/prestashop-browser')
    parser.add_argument('--expect-fixed', action='store_true')
    args = parser.parse_args()
    browser = Browser(args.browser_root)
    results = []
    try:
        for product, attribute, expected in [(7159, 51, '4800'), (4520, 58, '11205')]:
            browser.call('POST', browser.path('/url'), {'url': 'http://192.168.0.229/index.php?controller=product&id_product=' + str(product)})
            time.sleep(2)
            close = browser.call('POST', browser.path('/elements'), {'using': 'css selector', 'value': '#wk_hyper_location_modal.in button.close'})
            if close:
                browser.call('POST', browser.path('/element/' + close[0]['element-6066-11e4-a52e-4f735466cecf'] + '/click'), {})
                time.sleep(.5)
            before = browser.inspect()
            browser.click(attribute)
            after = browser.inspect()
            browser.click(50)
            restored = browser.inspect()
            entry = dict(product=product, before=before, after=after, restored=restored)
            results.append(entry)
            print(json.dumps(entry, ensure_ascii=False), flush=True)
            if args.expect_fixed and (after['amount'] != expected or before['amount'] != restored['amount']):
                raise RuntimeError('El clic no actualizo/restauro el precio esperado')
        image = browser.call('GET', browser.path('/screenshot'))
        Path(args.output).with_suffix('.png').write_bytes(base64.b64decode(image))
    finally:
        Path(args.output).write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n')
        browser.close()


if __name__ == '__main__':
    main()
