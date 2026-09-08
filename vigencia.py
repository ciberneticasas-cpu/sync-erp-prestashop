"""Señales explícitas del ERP: excluir fuentes, sin desactivar fichas de tienda."""
import re
import unicodedata


def marks(product):
    result = []
    state = str(product.get('state', '')).strip().upper()
    if state != 'A':
        result.append('ESTADO_' + (state or 'DESCONOCIDO'))
    name = unicodedata.normalize('NFKD', product.get('name', '')).upper()
    if re.search(r'\bNO\s+USAR\b', name):
        result.append('NO_USAR')
    for field in ('ean', 'ean2', 'ean3'):
        if re.match(r'^(?:DESCO(?:DIFICAD[OA])?|DESC|ANULAR)(?:\b|[_-])', str(product.get(field, '')).strip(), re.I):
            result.append(field.upper() + '_DESCODIFICADO_O_ANULADO')
    return result


class Excluded(ValueError):
    def __init__(self, products):
        self.products = products
        super().__init__('FUENTE_ERP_EXCLUIDA: ' + '; '.join(p['erp_id'] + ':' + ','.join(marks(p)) for p in products))
