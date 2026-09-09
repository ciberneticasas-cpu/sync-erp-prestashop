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

SHEETS = ['Activos ambos - simples', 'Activos ambos - presentaciones', 'ERP inactivo - PS activo',
          'ERP activo - PS inactivo', 'ERP sin PrestaShop', 'Otros y por revisar']
FIELDS = ['referencia_erp', 'codigo_barras_erp', 'codigo_barras_erp_2', 'codigo_barras_erp_3', 'clasificacion_informe', 'motivo_clasificacion']
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PACKAGE = 'http://schemas.openxmlformats.org/package/2006/relationships'
NUMERIC = set('factor_conversion_precio,inventario_erp,inventario_para_prestashop,inventario_mariadb,final_sync,precio_mariadb,precio_sin_impuesto_erp,ivaid,precio_erp,precio_para_prestashop,pum_ratio,pum_precio_unitario,impacto_precio,precio_final_sin_iva,precio_visible_verificado,precio_base_anterior,precio_base_nuevo,impacto_anterior,pum_ratio_final,pum_ratio_anterior,pum_ratio_propuesto,pum_precio_unitario_anterior,pum_precio_unitario_propuesto,pum_precio_visible_verificado,pum_contenido_erp,pum_contenido_erp_convertido,pum_contenido_nombre,pum_contenido_nombre_convertido,pum_factor_presentacion_nombre,cantidad_presentaciones_erp,cantidad_presentaciones_web,cantidad_presentaciones_iniciales,inventario_producto_inicial,pum_precio_producto_inicial,pum_ratio_producto_inicial,inventario_destino_antes,precio_destino_antes,precio_base_destino_antes,impacto_destino_antes,pum_precio_unitario_destino_antes,pum_ratio_destino_antes'.split(','))


def present_erp_ids(erp, catalog, settings):
    """Una correspondencia ambigua cuenta como posible presencia, no como ausencia."""
    _, index = match_erp.index(erp, eligible_only=False)
    found = set()
    for ps in catalog['products']:
        explicit = settings.get('mappings', {}).get(str(ps['id']), {}).get('erp_id')
        if explicit:
            found.add(explicit)
        for field, names in [('reference', ('reference', 'erp_id', 'ean')), ('ean13', ('ean',))]:
            for key in match_erp.keys(ps.get(field)):
                for name in names:
                    found.update(index[name].get(key, set()))
    return found


def classify(rows, erp, catalog, settings, fields):
    products = {p['erp_id']: p for p in erp['products']}
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
        state = str(first['estado_erp']).strip().upper()
        active = str(first['activo_prestashop'])
        combinations = web.get(pid, {}).get('combinations', [])
        multiple = len(combinations) > 1 and any(sync.norm(a['group_name']) == 'presentacion' for c in combinations for a in c['attributes'])
        if e:
            try:
                units, _, _ = sync.presentations_for(e, records[e['erp_id']])
                multiple = multiple or len(units) > 1
            except (ValueError, ArithmeticError):
                # Invalid economics must not hide that alternative ERP records exist.
                multiple = multiple or bool(records[e['erp_id']])
        if state == 'A' and active == '1':
            name = SHEETS[1] if multiple else SHEETS[0]
        elif state == 'I' and active == '1':
            name = SHEETS[2]
        elif state == 'A' and active == '0':
            name = SHEETS[3]
        else:
            name = SHEETS[5]
        for row in family:
            enrich(row, e)
            row.update(clasificacion_informe=name, motivo_clasificacion='Estado ERP='+state+'; activo PrestaShop='+active)
            sheets[name].append(row)
    # The presence check uses the COMPLETE destination catalog, even with --product.
    present = present_erp_ids(erp, catalog, settings)
    for e in erp['products']:
        if e['erp_id'] in present:
            continue
        row = {field: '' for field in fields}
        row.update(referencia=e.get('reference', ''), erp_id=e['erp_id'], nombre_erp=e['name'],
                   nombre_corto_erp=e.get('short_name', ''), estado_erp=e.get('state', ''),
                   inventario_erp=e.get('qty', ''), precio_erp=e.get('gross', ''), ivaid=e.get('tax', ''),
                   unidad_erp=e.get('unit', ''), erp_host=erp['host'], maneja_presentaciones_erp=e.get('manages', ''),
                   marcas_vigencia_erp=';'.join(vigencia.marks(e)), elegible_precio='NO' if vigencia.marks(e) else 'SI',
                   resultado='SIN_PRODUCTO_PRESTASHOP', accion='SOLO_AUDITORIA', stock_se_actualiza='NO',
                   clasificacion_informe=SHEETS[4], motivo_clasificacion='Sin correspondencia por referencia, EAN o mapeo en el catalogo completo del destino')
        try:
            row['precio_sin_impuesto_erp'] = sync.money(sync.net_price(e['gross'], e['tax']))
        except (ValueError, ArithmeticError):
            pass
        enrich(row, e)
        sheets[SHEETS[4]].append(row)
    return sheets


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
                leading = ['erp_id', 'nombre_erp', 'referencia_erp', 'nombre_corto_erp', 'estado_erp', 'inventario_erp', 'precio_erp', 'precio_sin_impuesto_erp', 'unidad_erp', 'codigo_barras_erp', 'marcas_vigencia_erp', 'elegible_precio', 'motivo_clasificacion'] if name == SHEETS[4] else []
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
