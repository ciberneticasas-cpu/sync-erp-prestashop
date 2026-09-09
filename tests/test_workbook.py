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
        return dict(id_producto=pid,erp_id=erp,estado_erp=state,activo_prestashop=active,factor_conversion_precio='1')

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
        self.assertEqual([len(sheets[n]) for n in book.SHEETS],[1,1,0,1,1,0,0,1,1,1,0,1])
        self.assertEqual([r['erp_id'] for r in sheets[book.ERP_ACTIVE_ABSENT_PS_SHEET]],['000999'])
        self.assertEqual([r['erp_id'] for r in sheets[book.ERP_INACTIVE_ABSENT_PS_SHEET]],['000998'])
        self.assertEqual(sum(len(v) for k,v in sheets.items() if k not in (book.ERP_ACTIVE_ABSENT_PS_SHEET,book.ERP_INACTIVE_ABSENT_PS_SHEET)),len(rows))

    def test_missing_erp_presentation_is_grouped_as_multiple(self):
        s,e,c=test_prices.Prices().ready();s['products'][0]['combinations']=[]
        sheets=book.classify([self.row(7159,'026074')],e,s,c,[])
        self.assertEqual(len(sheets[book.MULTIPLE_SHEET]),1)

    def test_nonpresentation_variants_do_not_count_as_multiple_presentations(self):
        s,e,c=test_prices.Prices().ready();e['presentations']=[]
        for co in s['products'][0]['combinations']:co['attributes'][0]['group_name']='Talla'
        sheets=book.classify([self.row(7159,'026074')],e,s,c,[])
        self.assertEqual(len(sheets[book.SIMPLE_SHEET]),1)

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
            self.assertEqual(summary['sheets'][book.ERP_ACTIVE_ABSENT_PS_SHEET]['rows'],0)

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
                text=z.read('xl/worksheets/sheet1.xml').decode()
                self.assertIn('APLICADO',text);self.assertNotIn('PROPUESTO',text)
            with next(folder.glob('cambios_precios*.csv')).open(encoding='utf-8-sig') as f:
                self.assertEqual(len(list(csv.DictReader(f))),2)

    def test_factor_review_numeric_equivalence_and_invalid_values(self):
        for value in ['6', '4.000000', '2.5', '2,5', '2', '1.5000', '1.00000000', '0.5']:
            self.assertEqual(book.factor_review_reason(value), '', value)
        for value in ['0.33333333', '0.1', '3', '6.000001', '0', '-1']:
            self.assertIn('fuera', book.factor_review_reason(value), value)
        for value in ['', None, 'NaN', 'Infinity', 'texto']:
            self.assertIn('inválido', book.factor_review_reason(value), value)

    def test_presentations_take_priority_and_never_duplicate_by_factor(self):
        s,e,c=test_prices.Prices().ready()
        rows=[dict(self.row(7159,'026074'),factor_conversion_precio=f) for f in ['1','0.1','0.33333333']]
        sheets=book.classify(rows,e,s,c,[])
        self.assertEqual(next(iter(sheets)),book.MULTIPLE_SHEET)
        self.assertFalse(sheets[book.FACTOR_SHEET])
        self.assertEqual(len(sheets[book.MULTIPLE_SHEET]),3)
        self.assertEqual(sheets[book.MULTIPLE_SHEET][1]['clasificacion_informe'],book.MULTIPLE_SHEET)
        for state,active in [('I','1'),('A','0'),('I','0')]:
            excluded=[dict(self.row(7159,'026074',state,active),factor_conversion_precio='0.1')]
            self.assertFalse(book.classify(excluded,e,s,c,[])[book.FACTOR_SHEET])

    def test_missing_erp_separates_ps_states_and_keeps_family(self):
        s,e,c=test_prices.Prices().ready();e['products']=[];e['presentations']=[]
        s['products'].append(dict(product(),id=9,reference='999',ean13='999'))
        rows=[self.row(7159,'','','1'),self.row(7159,'','','1'),self.row(9,'','','0')]
        sheets=book.classify(rows,e,s,c,[])
        self.assertEqual(len(sheets[book.PS_ACTIVE_ABSENT_ERP_SHEET]),2)
        self.assertEqual(len(sheets[book.PS_INACTIVE_ABSENT_ERP_SHEET]),1)
        self.assertFalse(sheets[book.REVIEW_SHEET])
        self.assertFalse(sheets[book.FACTOR_SHEET])

    def test_unresolved_candidates_are_not_missing_even_when_inactive(self):
        s,e,c=test_prices.Prices().ready();old=e['products'][0];old['state']='I'
        e['products'].append(dict(old,erp_id='other',reference='other'))
        rows=[self.row(7159,'','','1')]
        sheets=book.classify(rows,e,s,c,[])
        self.assertEqual(len(sheets[book.REVIEW_SHEET]),1)
        self.assertFalse(sheets[book.PS_ACTIVE_ABSENT_ERP_SHEET])
        s['products'][0].update(reference='missing',ean13='missing')
        c['mappings']={'7159':{'erp_id':old['erp_id']}}
        self.assertFalse(book.classify(rows,e,s,c,[])[book.PS_ACTIVE_ABSENT_ERP_SHEET])
        c['mappings']['7159']['erp_id']='nonexistent'
        self.assertEqual(len(book.classify(rows,e,s,c,[])[book.PS_ACTIVE_ABSENT_ERP_SHEET]),1)

    def test_missing_erp_uses_frozen_identity_and_does_not_guess_without_it(self):
        s,e,c=test_prices.Prices().ready()
        initial=copy.deepcopy(s)
        s['products'][0].update(reference='missing',ean13='missing')
        rows=[self.row(7159,'','','1')]
        self.assertFalse(book.classify(rows,e,s,c,[],initial_catalog=initial)[book.PS_ACTIVE_ABSENT_ERP_SHEET])
        self.assertFalse(book.classify(rows,e,s,c,[],initial_catalog={'products':[]})[book.PS_ACTIVE_ABSENT_ERP_SHEET])
        s,e,c=test_prices.Prices().ready()
        initial['products'][0].update(reference='missing',ean13='missing')
        sheets=book.classify(rows,e,s,c,[],initial_catalog=initial)
        self.assertEqual(len(sheets[book.PS_ACTIVE_ABSENT_ERP_SHEET]),1)

    def test_simple_factors_partition_whole_families(self):
        s,e,c=test_prices.Prices().ready();s['products'][0]['combinations']=[];e['presentations']=[]
        for factor,expected in [('6.',book.SIMPLE_SHEET),('2.5',book.SIMPLE_SHEET),('0.33333333',book.FACTOR_SHEET),('',book.FACTOR_SHEET)]:
            rows=[dict(self.row(7159,'026074'),factor_conversion_precio=factor)]
            sheets=book.classify(rows,e,s,c,[])
            self.assertEqual(len(sheets[expected]),1)
            self.assertEqual(sum(len(v) for v in sheets.values()),1)
        rows=[self.row(7159,'026074'),dict(self.row(7159,'026074'),factor_conversion_precio='0.1')]
        sheets=book.classify(rows,e,s,c,[])
        self.assertEqual(len(sheets[book.FACTOR_SHEET]),2)
        self.assertFalse(sheets[book.SIMPLE_SHEET])

    def test_null_states_unknown_and_both_inactive_are_exclusive(self):
        for erp_state,ps_state,expected in [(None,'1',book.ERP_NULL_SHEET),('',None,book.ERP_NULL_SHEET),('A',None,book.PS_NULL_SHEET),('I','',book.PS_NULL_SHEET),('I','0',book.REVIEW_SHEET),('X','1',book.REVIEW_SHEET)]:
            s,e,c=test_prices.Prices().ready();e['products'][0]['state']=erp_state
            rows=[self.row(7159,'026074',erp_state,ps_state)]
            sheets=book.classify(rows,e,s,c,[])
            self.assertEqual(len(sheets[expected]),1,(erp_state,ps_state))
            self.assertEqual(sum(map(len,sheets.values())),1)
            self.assertEqual(sheets[expected][0]['elegible_precio'],'NO')
        s,e,c=test_prices.Prices().ready();s['products']=[]
        for state,expected in [(None,book.ERP_NULL_SHEET),('',book.ERP_NULL_SHEET),('A',book.ERP_ACTIVE_ABSENT_PS_SHEET),('I',book.ERP_INACTIVE_ABSENT_PS_SHEET),('X',book.REVIEW_SHEET)]:
            e['products'][0]['state']=state
            sheets=book.classify([],e,s,c,[])
            self.assertEqual(len(sheets[expected]),1)
            self.assertEqual(sheets[expected][0]['elegible_precio'],'NO')

    def test_operations_only_allowed_in_first_three_categories(self):
        for name in book.SHEETS:
            plan={'operations':[{'id':7159}]}
            sheets={name:[dict(self.row(7159,'026074'),elegible_precio='SI')]}
            if name in book.PRICE_SHEETS:
                book.validate_price_plan(plan,sheets)
            else:
                with self.assertRaisesRegex(ValueError,'CATEGORIAS_ELEGIBLES'):
                    book.validate_price_plan(plan,sheets)
        for sheets in [{}, {book.SIMPLE_SHEET:[dict(self.row(7159,'026074'),elegible_precio='NO')]}]:
            with self.assertRaises(ValueError):book.validate_price_plan(plan,sheets)

    def test_informative_operation_cannot_reach_apply(self):
        s,e,c=test_prices.Prices().ready();s['products'][0]['active']='0'
        with tempfile.TemporaryDirectory() as d:
            args=Namespace(output=d+'/audit',product=None,evidence=False,apply=True)
            with patch('sync.bridge',return_value=s),patch('sync.erp_read',return_value=e),patch('sync.build_plan',return_value={'operations':[], 'rows':[]}) as build,patch('aplicar_precios.apply') as apply:
                original=book.validate_price_plan
                def inject(plan,sheets):
                    original({'operations':[{'id':7159}]},sheets)
                with patch('libro_auditoria.validate_price_plan',side_effect=inject):
                    with self.assertRaisesRegex(ValueError,'CATEGORIAS_ELEGIBLES'):sincronizar.run(args,c)
                apply.assert_not_called()
