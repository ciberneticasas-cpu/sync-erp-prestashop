from fixtures import *
import xml.etree.ElementTree as ET
import zipfile
from unittest.mock import patch
from argparse import Namespace
import libro_auditoria as book
import sincronizar
import test_prices


class Workbook(unittest.TestCase):
    def row(self, pid, erp, state='A', active='1'):
        return dict(id_producto=pid,erp_id=erp,estado_erp=state,activo_prestashop=active)

    def test_partitions_and_absent_include_both_erp_states(self):
        e=dict(host='192.168.0.231',products=[],presentations=[])
        catalog=dict(products=[]); rows=[]
        for pid,state,active in [(1,'A','1'),(2,'A','1'),(3,'I','1'),(4,'A','0'),(5,'I','0'),(6,'','1')]:
            ep=dict(erp_product(),erp_id=str(pid),reference=str(pid),ean=str(pid),state=state,manages='N')
            e['products'].append(ep);ps=dict(product(),id=pid,reference=str(pid),ean13=str(pid))
            if pid==2:ps['combinations']=[combo(10,'Caja','a'),combo(11,'Blister','b')]
            catalog['products'].append(ps);rows.append(self.row(pid,str(pid),state,active))
        for ident,state in [('000999','A'),('000998','I')]:
            e['products'].append(dict(erp_product(),erp_id=ident,reference=ident,ean=ident,state=state))
        sheets=book.classify(rows,e,catalog,{},sincronizar.LEGACY_FIELDS+sincronizar.EXTRA_FIELDS+book.FIELDS)
        self.assertEqual([len(sheets[n]) for n in book.SHEETS],[1,1,1,1,2,2])
        self.assertEqual({r['erp_id'] for r in sheets[book.SHEETS[4]]},{'000999','000998'})
        self.assertEqual(sum(len(v) for k,v in sheets.items() if k!=book.SHEETS[4]),len(rows))

    def test_missing_erp_presentation_is_grouped_as_multiple(self):
        s,e,c=test_prices.Prices().ready();s['products'][0]['combinations']=[]
        sheets=book.classify([self.row(7159,'026074')],e,s,c,[])
        self.assertEqual(len(sheets[book.SHEETS[1]]),1)

    def test_nonpresentation_variants_do_not_count_as_multiple_presentations(self):
        s,e,c=test_prices.Prices().ready();e['presentations']=[]
        for co in s['products'][0]['combinations']:co['attributes'][0]['group_name']='Talla'
        sheets=book.classify([self.row(7159,'026074')],e,s,c,[])
        self.assertEqual(len(sheets[book.SHEETS[0]]),1)

    def test_inactive_and_ambiguous_identity_candidates_are_not_claimed_absent(self):
        s,e,c=test_prices.Prices().ready();old=e['products'][0];old['state']='I'
        e['products'].append(dict(old,erp_id='other',reference='other',state='A'))
        self.assertEqual(book.present_erp_ids(e,s,c),{'026074','other'})
        e['products'].append(dict(old,erp_id='mapped',reference='mapped',ean='unmatched'))
        c['mappings']={'7159':{'erp_id':'mapped'}}
        self.assertIn('mapped',book.present_erp_ids(e,s,c))

    def test_xlsx_has_sheets_filters_freeze_and_safe_typed_cells(self):
        fields=['referencia','nombre_prestashop','precio_mariadb','impacto_anterior']
        data=dict(referencia='000283',nombre_prestashop='=1+2 & <texto>',precio_mariadb='12000.25',impacto_anterior='-43200')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'audit.xlsx';book.write(path,dict((name,[data] if i==0 else []) for i,name in enumerate(book.SHEETS)),fields)
            with zipfile.ZipFile(str(path)) as z:
                self.assertIsNone(z.testzip())
                for n in z.namelist():
                    if n.endswith('.xml') or n.endswith('.rels'):ET.fromstring(z.read(n))
                ns={'s':book.NS}
                wb=ET.fromstring(z.read('xl/workbook.xml'))
                self.assertEqual([s.attrib['name'] for s in wb.findall('s:sheets/s:sheet',ns)],book.SHEETS)
                sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
                cells={c.attrib['r']:c for c in sheet.findall('.//s:c',ns)}
                self.assertEqual(cells['A2'].find('s:is/s:t',ns).text,'000283')
                self.assertEqual(cells['B2'].attrib['t'],'inlineStr')
                self.assertEqual(cells['B2'].find('s:is/s:t',ns).text,'=1+2 & <texto>')
                self.assertFalse(sheet.findall('.//s:f',ns))
                self.assertEqual(cells['D2'].find('s:v',ns).text,'-43200')
                self.assertEqual(sheet.find('s:autoFilter',ns).attrib['ref'],'A1:D2')
                self.assertEqual(sheet.find('.//s:pane',ns).attrib['state'],'frozen')
            self.assertFalse(path.with_suffix('.xlsx.tmp').exists())

    def test_product_filter_uses_full_catalog_for_absence_and_replaces_audit_csv(self):
        s,e,c=test_prices.Prices().ready()
        s['products'].append(dict(product(),id=9,reference='000009',ean13='999',combinations=[]))
        e['products'].append(dict(erp_product(),erp_id='000009',reference='000009',ean='999',manages='N'))
        with tempfile.TemporaryDirectory() as d:
            args=Namespace(output=d+'/audit',product=[7159],evidence=False,apply=False)
            with patch('sync.bridge',return_value=s) as bridge,patch('sync.erp_read',return_value=e),patch('aplicar_precios.apply') as apply:
                sincronizar.run(args,c)
                bridge.assert_called_once_with(c,ids=[]);apply.assert_not_called()
            folder=Path(d)/'audit'
            self.assertEqual(len(list(folder.glob('stock_auditoria*.xlsx'))),1)
            self.assertFalse(list(folder.glob('stock_auditoria*.csv')))
            summary=sync.read_json(folder/'resumen.json')
            self.assertEqual(summary['sheets'][book.SHEETS[4]]['rows'],0)

    def test_apply_rewrites_workbook_with_final_status_and_keeps_change_log(self):
        s,e,c=test_prices.Prices().ready();e['products'][0]['gross']='50000'
        def applied(plan,settings,output):
            op=plan['operations'][0]
            return dict(results=[dict(operation=op,verification=dict(prices=[dict(combination_id=u['combination_id'],visible_price=u['net_price'],unit_price='500') for u in op['presentations']]))])
        with tempfile.TemporaryDirectory() as d:
            args=Namespace(output=d+'/audit',product=None,evidence=False,apply=True)
            with patch('sync.bridge',return_value=s),patch('sync.erp_read',return_value=e),patch('aplicar_precios.apply',side_effect=applied):
                self.assertEqual(sincronizar.run(args,c),0)
            folder=Path(d)/'audit'
            with zipfile.ZipFile(str(next(folder.glob('stock_auditoria*.xlsx')))) as z:
                text=z.read('xl/worksheets/sheet2.xml').decode()
                self.assertIn('APLICADO',text);self.assertNotIn('PROPUESTO',text)
            with next(folder.glob('cambios_precios*.csv')).open(encoding='utf-8-sig') as f:
                self.assertEqual(len(list(csv.DictReader(f))),2)
