"""Contenido físico y PUM: ERP contrastado con el nombre de PrestaShop.

Importes nativos sin IVA; el escaparate aplica impuestos y descuentos.
Los miligramos de una dosis no se consideran contenido del envase.
"""
import re
from decimal import Decimal
import sync

NUMBER = r'\d+(?:[.,]\d+)*'
COUNT = r'(?:tabletas?|tabs?|capsulas?|caps?|ampollas?|amps?|sobres?|sbs|unidades|unidad|unds?|uds?|uni|u|panuelos|repuestos?|pares|par)'
MEASURE = r'(?:kilogramos?|kilos?|kgs?|kl|gramos?|grs?|gm|g|mililitros?|ml|litros?|lts?|l)'


def normalized(amount, unit):
    try:
        quantity = sync.dec(str(amount).replace(',', '.'))
    except (ValueError, ArithmeticError):
        return None
    if quantity <= 0:
        return None
    unit = sync.norm(unit or '').rstrip('.')
    if re.fullmatch(r'kilogramos?|kilos?|kgs?|kl', unit):
        return quantity * 1000, 'Gramo'
    if re.fullmatch(r'gramos?|grs?|gm|g', unit):
        return quantity, 'Gramo'
    if re.fullmatch(r'litros?|lts?|l', unit):
        return quantity * 1000, 'Mililitro'
    if re.fullmatch(r'mililitros?|ml', unit):
        return quantity, 'Mililitro'
    if re.fullmatch(COUNT, unit):
        return quantity * (2 if unit in ('par', 'pares') else 1), 'Unidad'
    return None


def name_amount(value):
    # Spanish thousands separator: 3.000 gr is 3000 gr, not three grams.
    if re.fullmatch(r'[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?', value):
        value = value.replace('.', '')
    return sync.dec(value.replace(',', '.'))


def from_name(name):
    name = sync.norm(name).replace('×', 'x')
    box = re.search(r'(?:\bcaja|\bcja)\s*(?:de\s*)?x?\s*(' + NUMBER + r')\s*(' + COUNT + r'|a)\b', name)
    if box:
        content = normalized(name_amount(box[1]), 'amp' if box[2] == 'a' else box[2])
        inner = re.search(r'\bcon\s*(' + NUMBER + r')\s*(?:unidades|unidad|unds?)\s*c\s*/\s*u\b', name[box.end():])
        return (content[0] * name_amount(inner[1]), 'Unidad') if inner else content
    counts = list(re.finditer(r'(?<![\d.,])(' + NUMBER + r')\s*(' + COUNT + r')\b', name))
    medical = [m for m in counts if re.fullmatch(r'tabletas?|tabs?|capsulas?|caps?|ampollas?|amps?', m[2])]
    if medical:
        values = {normalized(name_amount(m[1]), m[2]) for m in medical}
        return values.pop() if len(values) == 1 else None
    measures = list(re.finditer(r'(?<![\d.,])(' + NUMBER + r')\s*(' + MEASURE + r')\b', name))
    measures = [m for m in measures if not re.search(r'/\s*$', name[:m.start()])
                and not ('jeringa' in name and m[2] == 'g')]
    if measures:
        values = []
        for m in measures:
            value = normalized(name_amount(m[1]), m[2])
            # A count plus a weight usually describes total pack weight (bread,
            # biscuits). Multiply only when the name explicitly says per item,
            # refills, or an unambiguous 'pack 6 x 200 ml' expression.
            before = re.search(r'(?<![a-wyz0-9])(' + NUMBER + r')\s*(' + COUNT + r')?\s*x\s*$', name[:m.start()])
            after = re.match(r'\s*x\s*(' + NUMBER + r')\s*(' + COUNT + r')?\b', name[m.end():])
            per_item = bool(re.search(r'\bc\s*/\s*u\b|\bcada\s+(?:uno|una|unidad)\b', name))
            refills = before and before[2] in ('repuesto', 'repuestos')
            explicit_pack = before and not before[2] and re.search(r'\b(?:pack|paquete)\s*$', name[:before.start()])
            multiplier = (before or after) if per_item else before if refills or explicit_pack else None
            if multiplier:
                value = (value[0] * name_amount(multiplier[1]), value[1])
            values.append(value)
        total = next((value for m, value in zip(measures, values) if re.search(r'\btotal\s*x?\s*$', name[:m.start()])), None)
        if total:
            return total
        if re.search(r'\bpague\b', name):
            received = next((value for m, value in zip(measures, values) if re.search(r'\bllev[ae]\s*x?\s*$', name[:m.start()])), None)
            if received:
                return received
        if len({v[1] for v in values}) == 1:
            if all(re.search(r'\+|\bmas\b|\bgratis\b', name[a.end():b.start()]) for a, b in zip(measures, measures[1:])):
                return sum(v[0] for v in values), values[0][1]
            # E.g. 25gr x12 unidades x300gr explicitly lists both sizes.
            if len(values) == 2 and any(max(v[0] for v in values) == min(v[0] for v in values) * name_amount(c[1]) for c in counts):
                return max(v[0] for v in values), values[0][1]
        values = set(values)
        return values.pop() if len(values) == 1 else None
    values = [normalized(name_amount(m[1]), m[2]) for m in counts]
    if values and all(re.search(r'\+|\bmas\b|\bgratis\b', name[a.end():b.start()]) for a, b in zip(counts, counts[1:])):
        return sum(v[0] for v in values), 'Unidad'
    values = set(values)
    return values.pop() if len(values) == 1 else None


def resolve(ps, erp, base_factor, name_factor='1'):
    source = normalized(erp.get('content', ''), erp.get('content_unit', ''))
    if source:
        source = source[0] * sync.dec(base_factor), source[1]
    named = from_name(ps['name'])
    raw_named = named
    if named:
        if sync.dec(name_factor) <= 0:
            raise ValueError('FACTOR_CONTENIDO_NOMBRE_INVALIDO')
        named = named[0] / sync.dec(name_factor), named[1]
    ambiguous = not named and bool(re.search(NUMBER + r'\s*(?:' + MEASURE + '|' + COUNT + r')\b', sync.norm(ps['name'])))
    same = source and named and source[1] == named[1] and abs(source[0] - named[0]) <= Decimal('0.00001')
    if source and named:
        selected, origin = (source, 'ERP_VALIDADO_CON_NOMBRE') if same else (named, 'NOMBRE_DIFIERE_ERP')
    elif source:
        selected, origin = source, 'ERP_SIN_CONTENIDO_EN_NOMBRE'
    elif named:
        selected, origin = named, 'NOMBRE_SIN_PUM_ERP'
    else:
        selected, origin = (Decimal(1), 'Unidad'), 'UNIDAD_POR_DEFECTO'
    return dict(note='NOMBRE_CON_CONTENIDOS_AMBIGUOS_REVISAR' if ambiguous else '', ratio=sync.money(selected[0]), unity=selected[1], source=origin,
                discrepancy='SI' if source and named and not same else 'NO',
                erp_content=str(erp.get('content') or ''), erp_unit=erp.get('content_unit') or '',
                erp_ratio=sync.money(source[0]) if source else '', erp_unity=source[1] if source else '',
                name_factor=str(name_factor), name_ratio=sync.money(raw_named[0]) if raw_named else '', name_base_ratio=sync.money(named[0]) if named else '', name_unity=named[1] if named else '')


def plan(ps, erp, units, base, name_factor='1'):
    base_unit = next(u for u in units if u['presentation_id'] == 'BASE')
    decision = resolve(ps, erp, base_unit['factor'], name_factor)
    ratio = sync.dec(decision['ratio'])
    decision['unit_price'] = sync.money(sync.dec(base) / ratio)
    combinations = []
    by_id = {u['combination_id']: u for u in units if u.get('combination_id')}
    for combo in ps['combinations']:
        unit = by_id.get(combo['id'])
        content = ratio
        if unit and decision['source'] != 'UNIDAD_POR_DEFECTO':
            content *= sync.dec(unit['factor']) / sync.dec(base_unit['factor'])
            nearest = content.to_integral_value()
            if nearest > 0 and abs(content - nearest) < Decimal('0.00001'):
                content = nearest
        price = sync.dec(unit['net_price']) if unit else sync.dec(base) + sync.dec(combo['price'])
        unit_price = sync.money(price / content)
        combinations.append(dict(combination_id=combo['id'], ratio=sync.money(content), unit_price=unit_price,
                                 impact=sync.money(sync.dec(unit_price) - sync.dec(decision['unit_price']))))
    decision['combinations'] = combinations
    decision['changed'] = changed(ps, decision)
    return decision


def changed(ps, decision):
    current = {c['id']: c for c in ps['combinations']}
    return ps.get('unity', '') != decision['unity'] or sync.dec(ps.get('unit_price') or 0) != sync.dec(decision['unit_price']) or any(
        sync.dec(current[c['combination_id']].get('unit_price_impact') or 0) != sync.dec(c['impact']) for c in decision['combinations'])


def initial_name_factor(ps, erp, units):
    """El nombre explícito de una fracción describe esa alternativa, no la caja."""
    if 'fraccion' not in sync.norm(ps['name']) or not from_name(ps['name']):
        return '1'
    alternatives = [u for u in units if u['presentation_id'] != 'BASE']
    if len(alternatives) != 1:
        raise ValueError('NOMBRE_FRACCION_CON_VARIAS_ALTERNATIVAS_REQUIERE_REVISION')
    factor = sync.dec(alternatives[0]['factor'])
    inverse = 1 / factor
    nearest = inverse.to_integral_value()
    return str(1 / nearest) if nearest > 0 and abs(inverse-nearest) < Decimal('.00001') else str(factor)
