"""Libro XLSX de auditoría, sin dependencias externas (Python 3.6+)."""
import collections
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from xml.sax.saxutils import escape, quoteattr
import zipfile
import match_erp
import sync
import vigencia
import precios_visibles

FACTOR_SHEET = 'Activos - factor no estándar'
SIMPLE_SHEET = 'Simples - sin ocultar'
SIMPLE_LOW_STOCK_SHEET = 'Simples - stock bajo'
MULTIPLE_SHEET = 'Presentaciones - sin ocultar'
MULTIPLE_LOW_STOCK_SHEET = 'Presentaciones - stock bajo'
ERP_INACTIVE_SHEET = 'ERP inactivo - PS activo'
PS_INACTIVE_SHEET = 'ERP activo - PS inactivo'
ERP_ACTIVE_ABSENT_PS_SHEET = 'ERP activo sin PS'
ERP_INACTIVE_ABSENT_PS_SHEET = 'ERP inactivo sin PS'
ERP_NULL_SHEET = 'ERP nulo'
PS_NULL_SHEET = 'PS nulo'
PS_ACTIVE_ABSENT_ERP_SHEET = 'PS activo sin ERP'
PS_INACTIVE_ABSENT_ERP_SHEET = 'PS inactivo sin ERP'
REVIEW_SHEET = 'Otros y por revisar'
SHEETS = [MULTIPLE_SHEET, MULTIPLE_LOW_STOCK_SHEET, SIMPLE_SHEET, SIMPLE_LOW_STOCK_SHEET, FACTOR_SHEET, ERP_INACTIVE_SHEET,
          PS_INACTIVE_SHEET, PS_ACTIVE_ABSENT_ERP_SHEET, PS_INACTIVE_ABSENT_ERP_SHEET,
          ERP_ACTIVE_ABSENT_PS_SHEET, ERP_INACTIVE_ABSENT_PS_SHEET,
          ERP_NULL_SHEET, PS_NULL_SHEET, REVIEW_SHEET]
PRICE_SHEETS = frozenset(SHEETS[:5])
STANDARD_FACTORS = frozenset(Decimal(v) for v in ('6', '4', '2.5', '2', '1.5', '1', '0.5'))
FIELDS = ['referencia_erp', 'codigo_barras_erp', 'codigo_barras_erp_2', 'codigo_barras_erp_3', 'clasificacion_informe', 'motivo_clasificacion']
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PACKAGE = 'http://schemas.openxmlformats.org/package/2006/relationships'
NUMERIC = set('factor_conversion_precio,inventario_erp,inventario_para_prestashop,inventario_mariadb,final_sync,precio_mariadb,precio_sin_impuesto_erp,ivaid,precio_erp,precio_para_prestashop,pum_ratio,pum_precio_unitario,impacto_precio,precio_final_sin_iva,precio_visible_verificado,precio_base_anterior,precio_base_nuevo,impacto_anterior,pum_ratio_final,pum_ratio_anterior,pum_ratio_propuesto,pum_precio_unitario_anterior,pum_precio_unitario_propuesto,pum_precio_visible_verificado,pum_contenido_erp,pum_contenido_erp_convertido,pum_contenido_nombre,pum_contenido_nombre_convertido,pum_factor_presentacion_nombre,cantidad_presentaciones_erp,cantidad_presentaciones_web,cantidad_presentaciones_iniciales,inventario_producto_inicial,pum_precio_producto_inicial,pum_ratio_producto_inicial,inventario_destino_antes,precio_destino_antes,precio_base_destino_antes,impacto_destino_antes,pum_precio_unitario_destino_antes,pum_ratio_destino_antes'.split(','))

FIELDS += precios_visibles.FIELDS + ['inventario_evaluado_ocultamiento', 'minimo_inventario_visible', 'oculto_por_stock', 'pagina_bloqueada_por_stock', 'reglas_stock_aplicadas', 'motivo_visibilidad_stock', 'origen_visibilidad_stock']
NUMERIC.update(['inventario_evaluado_ocultamiento', 'minimo_inventario_visible'])
NUMERIC.update(precios_visibles.NUMERIC)
LEADING_FIELDS = ['referencia', 'nombre_prestashop', 'nombre_corto_erp', 'factor_conversion_precio', 'presentacion', 'precio_visible_base_227', 'precio_visible_229', 'diferencia_precio_visible']


def erp_candidates(ps, settings, prepared):
    """Busca también ERP inactivos/excluidos; ambiguo no significa inexistente."""
    products, index = prepared
    found = set()
    explicit = settings.get('mappings', {}).get(str(ps['id']), {}).get('erp_id')
    if explicit in products:
        found.add(explicit)
    for field, names in [('reference', ('reference', 'erp_id', 'ean')), ('ean13', ('ean',))]:
        for key in match_erp.keys(ps.get(field)):
            for name in names:
                found.update(index[name].get(key, set()))
    return found


def present_erp_ids(erp, catalog, settings, prepared=None):
    prepared = prepared or match_erp.index(erp, eligible_only=False)
    found = set()
    for ps in catalog['products']:
        found.update(erp_candidates(ps, settings, prepared))
    return found


def factor_review_reason(value):
    try:
        factor = Decimal(str(value).strip().replace(',', '.'))
        if factor.is_finite():
            return '' if factor in STANDARD_FACTORS else 'Factor fuera de los valores estándar: '+str(value)
    except InvalidOperation:
        pass
    return 'Factor vacío o inválido: revisar'


def classify(rows, erp, catalog, settings, fields, initial_catalog=None, stock_visibility=None):
    prepared = match_erp.index(erp, eligible_only=False)
    products = prepared[0]
    initial = {p['id']: p for p in (initial_catalog if initial_catalog is not None else catalog)['products']}
    web = {p['id']: p for p in catalog['products']}
    records = collections.defaultdict(list)
    for p in erp['presentations']:
        records[p['erp_id']].append(p)
    grouped = collections.OrderedDict()
    for row in rows:
        grouped.setdefault(row['id_producto'], []).append(dict(row))
    sheets = collections.OrderedDict((name, []) for name in SHEETS)
    for pid, family in grouped.items():
        first = family[0]
        e = products.get(first['erp_id'])
        state = str(first.get('estado_erp') or '').strip().upper()
        active = str(first.get('activo_prestashop') if first.get('activo_prestashop') is not None else '').strip()
        combinations = web.get(pid, {}).get('combinations', [])
        multiple = len(combinations) > 1 and any(sync.norm(a['group_name']) == 'presentacion' for c in combinations for a in c['attributes'])
        if e:
            try:
                units, _, _ = sync.presentations_for(e, records[e['erp_id']])
                multiple = multiple or len(units) > 1
            except (ValueError, ArithmeticError):
                # Invalid economics must not hide that alternative ERP records exist.
                multiple = multiple or bool(records[e['erp_id']])
        identity = initial.get(pid)
        absent = e is None and identity is not None and not erp_candidates(identity, settings, prepared)
        if absent and active == '1':
            name = PS_ACTIVE_ABSENT_ERP_SHEET
        elif absent and active == '0':
            name = PS_INACTIVE_ABSENT_ERP_SHEET
        elif e is not None and state == 'A' and active == '1':
            name = MULTIPLE_SHEET if multiple else FACTOR_SHEET if any(factor_review_reason(r.get('factor_conversion_precio')) for r in family) else SIMPLE_SHEET
        elif state == 'I' and active == '1':
            name = ERP_INACTIVE_SHEET
        elif state == 'A' and active == '0':
            name = PS_INACTIVE_SHEET
        elif e is not None and not state:
            name = ERP_NULL_SHEET
        elif not active:
            name = PS_NULL_SHEET
        else:
            name = REVIEW_SHEET
        stock = (stock_visibility or {}).get(str(pid))
        if stock_visibility is not None and stock is None:
            raise ValueError('FALTA_VISIBILIDAD_STOCK: '+str(pid))
        if stock and stock['hidden']:
            name = {MULTIPLE_SHEET: MULTIPLE_LOW_STOCK_SHEET, SIMPLE_SHEET: SIMPLE_LOW_STOCK_SHEET}.get(name, name)
        for row in family:
            enrich(row, e)
            if stock:
                row.update(inventario_evaluado_ocultamiento=stock['quantity'], minimo_inventario_visible=stock['minimum'],
                    oculto_por_stock='SI' if stock['hidden'] else 'NO', pagina_bloqueada_por_stock='SI' if stock['page_blocked'] else 'NO',
                    reglas_stock_aplicadas=stock['rules'], motivo_visibilidad_stock=stock['reason'], origen_visibilidad_stock=sync.test_host(settings))
            row.update(clasificacion_informe=name, motivo_clasificacion='Estado ERP='+state+'; activo PrestaShop='+active)
            if absent:
                row['motivo_clasificacion'] = 'Sin correspondencia por referencia, EAN o mapeo en el ERP completo; activo PrestaShop='+active
            if name == FACTOR_SHEET:
                row['motivo_clasificacion'] += '; '+(factor_review_reason(row.get('factor_conversion_precio')) or 'Otra fila de esta ficha tiene factor no estándar')
            if name in (ERP_NULL_SHEET, PS_NULL_SHEET):
                row['motivo_clasificacion'] += '; Estado vacío o NULL'+('; sin ficha inicial PS' if identity is None else '')
            row['elegible_precio'] = 'SI' if (name in PRICE_SHEETS and e is not None and not vigencia.marks(e)
                and str(web.get(pid, {}).get('active')) == '1'
                and row.get('resultado') in ('SIN_CAMBIOS', 'PROPUESTO', 'APLICADO')) else 'NO'
            sheets[name].append(row)
    # The presence check uses the COMPLETE destination catalog, even with --product.
    present = present_erp_ids(erp, catalog, settings, prepared)
    for e in erp['products']:
        if e['erp_id'] in present:
            continue
        state = str(e.get('state') or '').strip().upper()
        name = ERP_ACTIVE_ABSENT_PS_SHEET if state == 'A' else ERP_INACTIVE_ABSENT_PS_SHEET if state == 'I' else ERP_NULL_SHEET if not state else REVIEW_SHEET
        row = {field: '' for field in fields}
        row.update(referencia=e.get('reference', ''), erp_id=e['erp_id'], nombre_erp=e['name'],
                   nombre_corto_erp=e.get('short_name', ''), estado_erp=e.get('state', ''),
                   inventario_erp=e.get('qty', ''), precio_erp=e.get('gross', ''), ivaid=e.get('tax', ''),
                   unidad_erp=e.get('unit', ''), erp_host=erp['host'], maneja_presentaciones_erp=e.get('manages', ''),
                   marcas_vigencia_erp=';'.join(vigencia.marks(e)), elegible_precio='NO',
                   resultado='SIN_PRODUCTO_PRESTASHOP', accion='SOLO_AUDITORIA', stock_se_actualiza='NO',
                   clasificacion_informe=name, motivo_clasificacion='Sin correspondencia por referencia, EAN o mapeo en el catalogo completo del destino')
        try:
            row['precio_sin_impuesto_erp'] = sync.money(sync.net_price(e['gross'], e['tax']))
        except (ValueError, ArithmeticError):
            pass
        enrich(row, e)
        sheets[name].append(row)
    return collections.OrderedDict((name, order_families(values)) for name, values in sheets.items())


def order_families(rows):
    groups = collections.OrderedDict()
    for row in rows:
        key = ('PS', str(row['id_producto'])) if row.get('id_producto') else ('ERP', str(row.get('erp_id', '')))
        groups.setdefault(key, []).append(row)
    def priority(item):
        key, family = item
        differences = []
        for row in family:
            value = row.get('diferencia_precio_visible')
            if value is not None and value != '':
                try:
                    number = Decimal(str(value))
                    if number.is_finite(): differences.append(abs(number))
                except InvalidOperation: pass
        return (not bool(differences), -max(differences) if differences else Decimal(0), key)
    result = []
    for key, family in sorted(groups.items(), key=priority):
        result.extend(sorted(family, key=lambda r: (r.get('presentacion_id') != 'BASE', str(r.get('presentacion_id', '')), str(r.get('id_combinacion', '')))))
    return result


def validate_price_plan(plan, sheets):
    """Impide enviar al escritor una ficha informativa o no elegible."""
    categories = collections.defaultdict(set)
    eligible = collections.defaultdict(list)
    for name, rows in sheets.items():
        for row in rows:
            if row.get('id_producto'):
                categories[row['id_producto']].add(name)
                eligible[row['id_producto']].append(row.get('elegible_precio') == 'SI')
    for op in plan['operations']:
        names = categories.get(op['id'], set())
        if len(names) != 1 or not names.issubset(PRICE_SHEETS) or not all(eligible[op['id']]):
            raise ValueError('PLAN_PRECIO_FUERA_DE_CATEGORIAS_ELEGIBLES: '+str(op['id']))


def enrich(row, erp):
    erp = erp or {}
    row.update(referencia_erp=erp.get('reference', ''), codigo_barras_erp=erp.get('ean', ''),
               codigo_barras_erp_2=erp.get('ean2', ''), codigo_barras_erp_3=erp.get('ean3', ''))


def column(number):
    result = ''
    while number:
        number, remainder = divmod(number-1, 26)
        result = chr(65+remainder) + result
    return result


def clean(value):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value))[:32767]


def cell(address, value, field='', header=False):
    if value is None or value == '':
        return ''
    if field in NUMERIC and not header:
        try:
            number = Decimal(str(value))
            if number.is_finite():
                return '<c r="{}" s="2"><v>{}</v></c>'.format(address, number)
        except InvalidOperation:
            pass
    # Explicit inline text preserves leading zeroes and never executes formulas.
    return '<c r="{}" t="inlineStr" s="{}"><is><t xml:space="preserve">{}</t></is></c>'.format(address, 1 if header else 0, escape(clean(value)))


STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.######"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF203864"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def write(path, sheets, fields):
    path = Path(path)
    temporary = path.with_suffix('.xlsx.tmp')
    xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    def relationships(items):
        return xml+'<Relationships xmlns="'+PACKAGE+'">'+''.join('<Relationship Id="{}" Type="{}" Target={}/>'.format(i, t, quoteattr(target)) for i,t,target in items)+'</Relationships>'
    try:
        with zipfile.ZipFile(str(temporary), 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('_rels/.rels', relationships([('rId1', REL+'/officeDocument', 'xl/workbook.xml')]))
            archive.writestr('xl/workbook.xml', xml+'<workbook xmlns="'+NS+'" xmlns:r="'+REL+'"><sheets>'+''.join('<sheet name={} sheetId="{}" r:id="rId{}"/>'.format(quoteattr(name),i,i) for i,name in enumerate(sheets,1))+'</sheets></workbook>')
            archive.writestr('xl/_rels/workbook.xml.rels', relationships([('rId'+str(i), REL+'/worksheet', 'worksheets/sheet'+str(i)+'.xml') for i in range(1,len(sheets)+1)]+[('rIdStyles', REL+'/styles', 'styles.xml')]))
            archive.writestr('xl/styles.xml', STYLES)
            types = [('xl/workbook.xml', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'), ('xl/styles.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml')]
            for index, (name, rows) in enumerate(sheets.items(),1):
                leading = LEADING_FIELDS
                ordered_fields = [f for f in leading if f in fields] + [f for f in fields if f not in leading]
                end = column(len(ordered_fields))+str(len(rows)+1)
                columns = ''.join('<col min="{0}" max="{0}" width="{1}" customWidth="1"/>'.format(i, 52 if 'nombre' in f or f in ('motivo','motivo_clasificacion') else 22 if f in NUMERIC else 26) for i,f in enumerate(ordered_fields,1))
                start = xml+'<worksheet xmlns="'+NS+'"><dimension ref="A1:'+end+'"/><sheetViews><sheetView workbookViewId="0" zoomScale="85"><pane xSplit="2" ySplit="1" topLeftCell="C2" activePane="bottomRight" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/><cols>'+columns+'</cols><sheetData>'
                filename = 'xl/worksheets/sheet'+str(index)+'.xml'
                # Streaming ZIP writing bounds memory even for the complete ERP catalog.
                with archive.open(filename, 'w') as stream:
                    stream.write(start.encode('utf-8'))
                    stream.write(('<row r="1" ht="46" customHeight="1">'+''.join(cell(column(i)+'1',f,header=True) for i,f in enumerate(ordered_fields,1))+'</row>').encode('utf-8'))
                    for number, row in enumerate(rows,2):
                        stream.write(('<row r="'+str(number)+'">'+''.join(cell(column(i)+str(number),row.get(f,''),f) for i,f in enumerate(ordered_fields,1))+'</row>').encode('utf-8'))
                    stream.write(('</sheetData><autoFilter ref="A1:'+end+'"/></worksheet>').encode('utf-8'))
                types.append((filename,'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'))
            archive.writestr('[Content_Types].xml', xml+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'+''.join('<Override PartName="/'+part+'" ContentType="'+content+'"/>' for part,content in types)+'</Types>')
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {name: dict(rows=len(rows), products=len({r.get('id_producto') or r.get('erp_id') for r in rows})) for name,rows in sheets.items()}
