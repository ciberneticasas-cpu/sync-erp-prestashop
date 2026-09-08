"""Deterministic legacy identifier priority, retaining collision evidence."""
import collections


def keys(value):
    value = str(value or '').strip()
    result = [value] if value else []
    if len(value) > 1 and all('0' <= c <= '9' for c in value):
        normalized = value.lstrip('0')
        if normalized and normalized != value:
            result.append(normalized)
    return result


def index(erp):
    maps = {name: collections.defaultdict(set) for name in ('reference', 'ean', 'erp_id')}
    products = {p['erp_id']: p for p in erp['products']}
    for p in products.values():
        for name, fields in [('reference', ['reference']), ('ean', ['ean', 'ean2', 'ean3']), ('erp_id', ['erp_id'])]:
            for field in fields:
                for key in keys(p.get(field)):
                    maps[name][key].add(p['erp_id'])
    return products, maps


def resolve(ps, erp, mapping, prepared=None):
    products, maps = prepared or index(erp)
    explicit = mapping.get('erp_id')
    if explicit:
        if explicit not in products:
            raise ValueError('MAPEO_ERP_INEXISTENTE')
        return products[explicit], 'MAPEO_EXPLICITO', ''
    collisions = []
    for field, names in [('reference', ['reference', 'ean', 'erp_id']), ('ean13', ['ean'])]:
        for name in names:
            for key in keys(ps.get(field)):
                ids = maps[name].get(key, set())
                if len(ids) > 1:
                    collisions.append(field + ':' + name + ':' + key)
                if len(ids) == 1:
                    selected = next(iter(ids))
                    barcode_ids = set()
                    for barcode in keys(ps.get('ean13')):
                        barcode_ids.update(maps['ean'].get(barcode, set()))
                    warning = 'EAN_DIFIERE_SE_APLICA_PRIORIDAD_REFERENCIA_HEREDADA' if barcode_ids and selected not in barcode_ids else ''
                    return products[selected], field + '->' + name, warning
    raise ValueError('MATCH_ERP_AMBIGUO: ' + ', '.join(collisions) if collisions else 'SIN_MATCH_ERP')
