"""Deterministic legacy identifier priority, retaining collision evidence."""
import collections
import vigencia


def keys(value):
    value = str(value or '').strip()
    result = [value] if value else []
    if len(value) > 1 and all('0' <= c <= '9' for c in value):
        normalized = value.lstrip('0')
        if normalized and normalized != value:
            result.append(normalized)
    return result


def index(erp, eligible_only=True):
    maps = {name: collections.defaultdict(set) for name in ('reference', 'ean', 'erp_id', 'excluded_ref', 'excluded_ean')}
    products = {p['erp_id']: p for p in erp['products']}
    for p in products.values():
        if eligible_only and vigencia.marks(p):
            for field in ('reference', 'erp_id', 'ean', 'ean2', 'ean3'):
                for key in keys(p.get(field)):
                    maps['excluded_ref'][key].add(p['erp_id'])
                    if field.startswith('ean'): maps['excluded_ean'][key].add(p['erp_id'])
            continue
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
        if vigencia.marks(products[explicit]):
            raise vigencia.Excluded([products[explicit]])
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
                    old_reference = set()
                    for ref_key in keys(ps.get('reference')):
                        old_reference.update(maps['excluded_ref'].get(ref_key, set()))
                    excluded = [products[i] for i in sorted(old_reference)]
                    if excluded:
                        warning = 'REFERENCIA_ANTIGUA_EXCLUIDA_REVISAR_SUSTITUCION: ' + ','.join(p['erp_id'] for p in excluded)
                    return products[selected], field + '->' + name, warning
    excluded = excluded_candidates(ps, erp, (products, maps))
    if excluded:
        raise vigencia.Excluded(excluded)
    raise ValueError('MATCH_ERP_AMBIGUO: ' + ', '.join(collisions) if collisions else 'SIN_MATCH_ERP')


def excluded_candidates(ps, erp, prepared=None):
    products, maps = prepared or index(erp)
    ids = set()
    for field, name in [('reference', 'excluded_ref'), ('ean13', 'excluded_ean')]:
        for key in keys(ps.get(field)):
            ids.update(maps[name].get(key, set()))
    return [products[i] for i in sorted(ids)]
