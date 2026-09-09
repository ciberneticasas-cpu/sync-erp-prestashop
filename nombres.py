"""Recomendaciones para revisar en CSV; no modifica nombres de ninguna base."""
import sync


def suggest(ps, erp, settings, units):
    configured = settings.get('mappings', {}).get(str(ps['id']), {}).get('product_name', '')
    if configured and configured != ps['name']:
        return configured, 'NOMBRE_COMERCIAL_REVISADO_EN_MAPEO'
    if erp and len(units) > 1 and 'fraccion' in sync.norm(ps['name']):
        labels = ['Caja' if u['presentation_id'] == 'BASE' and sync.norm(erp['unit']) in ('cja', 'cj', 'caja') else u['label'] for u in units]
        return erp['name'] + ' - ' + ' / '.join(labels), 'EL_NOMBRE_SOLO_DESCRIBE_LA_FRACCION'
    return '', ''
