from fixtures import *
import pum
import sincronizar
import test_prices


class Pum(unittest.TestCase):
    def test_physical_names_and_dosage(self):
        examples = {
            'Ciruela Importada X500 gr': ('500', 'Gramo'),
            'Yogurt 1 LT': ('1000', 'Mililitro'),
            'Producto 0,5 kg': ('500', 'Gramo'),
            'Ambientador X3 repuestos X21ml': ('63', 'Mililitro'),
            'Pack 6 x 200 ml': ('1200', 'Mililitro'),
            'Yogur 150g x 5 unidades c/u': ('750', 'Gramo'),
            'Pan Hamburguesa X4 Und X210gr': ('210', 'Gramo'),
            'Ponds B3 X100gr': ('100', 'Gramo'),
            'Arroz Roa 10 X1000gr': ('1000', 'Gramo'),
            'Arroz X3.000gr': ('3000', 'Gramo'),
            'Envase 0.125 litros': ('125', 'Mililitro'),
            'Yogurt X5 Und X150gr Total X750gr': ('750', 'Gramo'),
            'Papas X25gr X12 Und X300gr': ('300', 'Gramo'),
            'Talco 150gr + 85gr': ('235', 'Gramo'),
            'Crema pague 100gr lleve 150gr': ('150', 'Gramo'),
            'Avena X6Und X210gr c/u': ('1260', 'Gramo'),
            'Acetaminofen 160mg/5ml 90ml': ('90', 'Mililitro'),
            'Jeringa 21G x 1 1/2 50ml': ('50', 'Mililitro'),
            'Esponja X6 Unidades Gratis X2 Unidades': ('8', 'Unidad'),
            'Gasa Caja de 12 Sobres con 2 Unidades C/U': ('24', 'Unidad'),
            'Furosemida 40mg - Caja 100 tabletas / Blíster 10 tabletas': ('100', 'Unidad'),
            'EUTARPAN 10MG 10TAB CJAX100TAB': ('100', 'Unidad'),
            'BEDOYECTA 2ML 1AMP CJAX3AMP': ('3', 'Unidad'),
            'Diclofenaco X75Mg X5 Ampollas': ('5', 'Unidad'),
            'Lactulax 1 Sobre X15Ml': ('15', 'Mililitro'),
            'Guante talla 6.5 1Par': ('2', 'Unidad'),
        }
        for name, (quantity, unity) in examples.items():
            with self.subTest(name=name): self.assertEqual(pum.from_name(name), (Decimal(quantity), unity))
        for name in ['Bedoyecta ampolla', 'Fluimucil Efervescente 600mg', 'Bloqueador SPF50', 'Micropore 1x5', 'Surtido 200ml y 300ml']:
            with self.subTest(name=name): self.assertIsNone(pum.from_name(name))

    def test_precedence_normalization_and_fallback(self):
        ps = dict(name='Ciruela X500 gr')
        result = pum.resolve(ps, dict(content='1', content_unit='KG'), '.5')
        self.assertEqual(result['source'], 'ERP_VALIDADO_CON_NOMBRE')
        self.assertEqual(result['ratio'], '500.000000')
        result = pum.resolve(ps, dict(content='750', content_unit='GR'), '1')
        self.assertEqual(result['source'], 'NOMBRE_DIFIERE_ERP'); self.assertEqual(result['discrepancy'], 'SI')
        self.assertEqual(result['ratio'], '500.000000')
        result = pum.resolve(ps, dict(content='500', content_unit='ML'), '1')
        self.assertEqual(result['discrepancy'], 'SI'); self.assertEqual(result['unity'], 'Gramo')
        result = pum.resolve(dict(name='Sin contenido'), dict(content='100', content_unit='ml'), '1')
        self.assertEqual(result['source'], 'ERP_SIN_CONTENIDO_EN_NOMBRE')
        result = pum.resolve(dict(name='Sin contenido'), dict(content='0', content_unit='G'), '1')
        self.assertEqual((result['unity'], result['ratio']), ('Unidad', '1.000000'))
        result = pum.resolve(ps, {}, '1')
        self.assertEqual(result['source'], 'NOMBRE_SIN_PUM_ERP')

    def test_ciruela_price_changes_keep_content(self):
        s,e,c = sample(); ps=s['products'][0]; ps.update(name='Ciruela X500 gr', combinations=[], unity='Gramo', unit_price='24', price='12000')
        e['products'][0].update(gross='26000',manages='N'); e['presentations']=[]; e['legacy_factors']['7159:026074']='.5'
        op=sync.build_plan(s,e,c)['operations'][0]
        self.assertEqual(op['pum']['unit_price'], '26.000000'); self.assertEqual(op['pum']['ratio'], '500.000000')

    def test_pum_only_change_logged_and_idempotent(self):
        s,e,c=test_prices.Prices().ready(); ps=s['products'][0]; ps['unit_price']='55000'
        plan=sync.build_plan(s,e,c); op=plan['operations'][0]
        self.assertEqual(plan['rows'][0]['motivo'], 'SOLO_PUM')
        self.assertEqual(op['pum']['unit_price'], '480.000000')
        self.assertEqual([u['ratio'] for u in op['pum']['combinations']], ['100.000000','10.000000'])
        journal=dict(results=[dict(operation=op,verification=dict(prices=[dict(combination_id=u['combination_id'], visible_price=u['net_price'], unit_price='480',unit_price_ratio=ratio) for u,ratio in zip(op['presentations'],[100,10])]))])
        rows=sincronizar.report_rows(s,e,plan,c,journal)
        self.assertEqual(len(sincronizar.price_changes(rows)),2)
        self.assertTrue(all(r['tipo_cambio']=='SOLO_PUM' for r in rows))
        ps.update(unit_price=op['pum']['unit_price'],unity=op['pum']['unity'])
        for combo, value in zip(ps['combinations'], op['pum']['combinations']): combo['unit_price_impact']=value['impact']
        self.assertFalse(sync.build_plan(s,e,c)['operations'])
        audit=sincronizar.report_rows(s,e,sync.build_plan(s,e,c),c)
        self.assertTrue(all(r['pum_fuente']=='NOMBRE_SIN_PUM_ERP' for r in audit))

    def test_independent_fraction_price_and_fallback_per_sale_unit(self):
        s,e,c=test_prices.Prices().ready(); e['presentations'][0].update(from_main='0',gross='5000')
        op=sync.build_plan(s,e,c)['operations'][0]
        self.assertEqual(op['pum']['combinations'][1]['unit_price'],'500.000000')
        self.assertEqual(op['pum']['combinations'][1]['impact'],'20.000000')
        s['products'][0]['name']='Sin contenido'
        op=sync.build_plan(s,e,c)['operations'][0]
        self.assertEqual([u['ratio'] for u in op['pum']['combinations']],['1.000000','1.000000'])
        self.assertEqual(op['pum']['combinations'][1]['unit_price'],'5000.000000')

    def test_thirds_are_whole_units(self):
        s,e,c=test_prices.Prices().ready(); s['products'][0]['name']='Caja X3 ampollas';e['presentations'][0]['factor']='0.33333333'
        op=sync.build_plan(s,e,c)['operations'][0]
        self.assertEqual(op['pum']['combinations'][1]['ratio'],'1.000000')

    def test_blocked_and_excluded_never_propose_pum(self):
        for blocked in ('structure','inactive'):
            s,e,c=test_prices.Prices().ready();s['products'][0]['unit_price']='999'
            if blocked=='structure':s['products'][0]['combinations'].pop()
            else:e['products'][0]['state']='I'
            plan=sync.build_plan(s,e,c)
            self.assertFalse(plan['operations']);self.assertFalse(plan['pum_decisions'])
            self.assertTrue(all(r['pum_precio_unitario_propuesto']=='' for r in sincronizar.report_rows(s,e,plan,c)))

    def test_nonpresentation_combinations_are_reported(self):
        s,e,c=test_prices.Prices().ready();e['products'][0]['manages']='N';e['presentations']=[]
        for combo in s['products'][0]['combinations']:combo['attributes'][0]['group_name']='Talla'
        plan=sync.build_plan(s,e,c);op=plan['operations'][0]
        self.assertEqual(op['pum']['combinations'][1]['unit_price'],'48.000000')
        self.assertEqual({r['id_combinacion'] for r in sincronizar.report_rows(s,e,plan,c)},{0,142,143})
        self.assertEqual(len(op['presentations']), 1, 'El informe no debe modificar el plan que se aplica')
