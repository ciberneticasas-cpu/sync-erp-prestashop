from fixtures import *
import precios_visibles as visible
import libro_auditoria as book
import sincronizar
import zipfile
import xml.etree.ElementTree as ET


class VisiblePrices(unittest.TestCase):
    def sample_row(self, cid, presentation='BASE'):
        return dict(id_producto=7159,id_combinacion=cid,presentacion_id=presentation,presentacion_en_prestashop='SI')

    def test_baseline_pairing_by_attributes_and_run_difference_are_separate(self):
        live,e,c=sample();old=copy.deepcopy(live)
        old['products'][0]['combinations'][1]['id']=999
        before={'prices':[dict(id=7159,combination_id=143,actual=9000,proposed=7200)]}
        frozen={'prices':[dict(id=7159,combination_id=999,actual=90000,proposed=90000)]}
        after={'prices':[dict(id=7159,combination_id=143,actual=7200,proposed=7200)]}
        row=visible.enrich([self.sample_row(143,'1414')],old,live,before,frozen,after)[0]
        self.assertEqual(row['precio_visible_base_227'],'90000.000000')
        self.assertEqual(row['precio_visible_229'],'7200.000000')
        self.assertEqual(row['diferencia_precio_visible'],'-82800.000000')
        self.assertEqual(row['diferencia_visible_corrida'],'-1800.000000')
        self.assertEqual(row['verificacion_precio_visible'],'COINCIDE')
        after['prices'][0]['actual']=8000
        row=visible.enrich([self.sample_row(143,'1414')],old,live,before,frozen,after)[0]
        self.assertEqual(row['verificacion_precio_visible'],'DIFIERE_REVISAR')
        self.assertEqual(row['precio_visible_229'],'8000.000000')

    def test_new_alternative_has_no_invented_baseline_price(self):
        live,e,c=sample();old=copy.deepcopy(live);old['products'][0]['combinations']=[]
        before={'prices':[dict(id=7159,combination_id=cid,actual=100,proposed=90) for cid in (142,143)]}
        frozen={'prices':[dict(id=7159,combination_id=0,actual=1000,proposed=1000)]}
        rows=visible.enrich([self.sample_row(142),self.sample_row(143,'1414')],old,live,before,frozen)
        self.assertEqual(rows[0]['precio_visible_base_227'],'1000.000000')
        self.assertEqual(rows[1]['precio_visible_base_227'],'')
        self.assertEqual(rows[1]['diferencia_precio_visible'],'')
        self.assertEqual(rows[1]['verificacion_precio_visible'],'PRONOSTICO_MOTOR_NATIVO')
        missing=dict(self.sample_row(0,'new'),presentacion_en_prestashop='NO')
        self.assertEqual(visible.enrich([missing],old,live,before,frozen)[0]['precio_visible_229'],'')

    def test_sort_largest_change_keeps_base_before_alternatives_and_unknowns_last(self):
        def row(pid,presentation,difference):return dict(id_producto=pid,presentacion_id=presentation,diferencia_precio_visible=difference)
        rows=[row(1,'alt','-1000'),row(2,'BASE','500'),row(1,'BASE','0'),row(3,'BASE',''),row(4,'BASE','0')]
        ordered=book.order_families(rows)
        self.assertEqual([(r['id_producto'],r['presentacion_id']) for r in ordered],[(1,'BASE'),(1,'alt'),(2,'BASE'),(4,'BASE'),(3,'BASE')])

    def test_workbook_visual_prefix_and_numeric_visible_prices(self):
        fields=sincronizar.LEGACY_FIELDS+sincronizar.EXTRA_FIELDS+book.FIELDS
        row=dict(referencia='0001',nombre_prestashop='Producto',nombre_corto_erp='ERP',factor_conversion_precio='0.1',presentacion='Blister',precio_visible_base_227='100',precio_visible_229='10',diferencia_precio_visible='-90')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a.xlsx';book.write(path,{book.MULTIPLE_SHEET:[row]},fields)
            with zipfile.ZipFile(str(path)) as archive:
                tree=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'));ns={'s':book.NS}
                header=[c.find('s:is/s:t',ns).text for c in tree.findall('s:sheetData/s:row',ns)[0]]
                self.assertEqual(header[:8],book.LEADING_FIELDS)
                cells={c.attrib['r']:c for c in tree.findall('.//s:c',ns)}
                self.assertEqual(cells['E2'].find('s:is/s:t',ns).text,'Blister')
                self.assertEqual(cells['H2'].find('s:v',ns).text,'-90')
