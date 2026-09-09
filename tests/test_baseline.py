from fixtures import *
from unittest.mock import patch
import subprocess
import base_congelada
import sincronizar
import pum
import test_prices


class Baseline(unittest.TestCase):
    def ready(self):
        live, erp, settings = test_prices.Prices().ready()
        initial = copy.deepcopy(live)
        initial['target']='192.168.0.227/mercaboy_pruebas/1'
        live['baseline']=initial
        return live, erp, settings

    def test_previous_values_are_frozen_and_not_logged_as_new_changes(self):
        live,e,c=self.ready();old=live['baseline']['products'][0]
        old.update(price='55000',unit_price='55000',quantity='17',name='Nombre inicial 100 Tabletas')
        old['combinations'][1].update(price='43200',quantity='9')
        plan=sync.build_plan(live,e,c);self.assertFalse(plan['operations'])
        rows=sincronizar.report_rows(live,e,plan,c)
        row=next(r for r in rows if r['id_combinacion']==143)
        self.assertEqual(row['precio_mariadb'],'98200.000000')
        self.assertEqual(row['precio_destino_antes'],'4800.000000')
        self.assertEqual(row['inventario_mariadb'],'9')
        self.assertEqual(row['nombre_prestashop'],'Nombre inicial 100 Tabletas')
        self.assertEqual(row['pum_precio_unitario_anterior'],'55000.000000')
        self.assertEqual(row['diferencia_respecto_base'],'SI')
        self.assertFalse(sincronizar.price_changes(rows))

    def test_wrong_live_price_is_corrected_and_freshness_uses_live(self):
        live,e,c=self.ready();live['products'][0]['price']='99999'
        plan=sync.build_plan(live,e,c);op=plan['operations'][0]
        self.assertEqual(op['base_price'],'48000.000000')
        self.assertEqual(op['before']['price'],'99999')
        self.assertEqual(op['initial']['price'],'48000.000000')
        self.assertEqual(op['new_name'],'')

    def test_initial_and_current_active_are_required_without_writing_them(self):
        live,e,c=self.ready();live['baseline']['products'][0]['active']='0';live['products'][0]['price']='99999'
        plan=sync.build_plan(live,e,c);self.assertFalse(plan['operations'])
        self.assertTrue(all(r['resultado']=='INACTIVO_PRESTASHOP' for r in sincronizar.report_rows(live,e,plan,c)))
        live,e,c=self.ready();live['products'][0].update(active='0',price='99999')
        plan=sync.build_plan(live,e,c);self.assertFalse(plan['operations'])
        self.assertIn('DESTINO_PRESTASHOP_NO_ACTIVO',plan['rows'][0]['motivo'])

    def test_new_combination_has_no_invented_previous_price(self):
        live,e,c=self.ready();live['baseline']['products'][0]['combinations']=[]
        plan=sync.build_plan(live,e,c);rows=sincronizar.report_rows(live,e,plan,c)
        self.assertTrue(all(r['base_estado']=='COMBINACION_NUEVA_SIN_BASE' and r['precio_mariadb']=='' and r['inventario_mariadb']=='' for r in rows))
        self.assertTrue(all(r['precio_base_anterior']=='48000.000000' for r in rows))

    def test_initial_name_is_used_without_renaming_and_fraction_content_is_converted(self):
        live,e,c=self.ready();live['baseline']['products'][0]['name']='Eutarpan Fracción 10 Tabletas'
        plan=sync.build_plan(live,e,c);self.assertFalse(plan['operations'])
        d=plan['pum_decisions']['7159'];self.assertEqual(d['ratio'],'100.000000');self.assertEqual(d['name_ratio'],'10.000000')
        rows=sincronizar.report_rows(live,e,plan,c)
        self.assertTrue(all(r['nombre_suguerido_prestashop'] and r['nombre_destino']=='' for r in rows))

    def test_nonpresentation_impacts_use_initial_data(self):
        live,e,c=self.ready();e['presentations']=[];e['products'][0]['manages']='N'
        for snapshot in (live,live['baseline']):
            for combo in snapshot['products'][0]['combinations']:
                combo['attributes'][0]['group_name']='Talla';combo['price']='0'
        live['products'][0]['combinations'][1]['price']='999'
        op=sync.build_plan(live,e,c)['operations'][0]
        self.assertEqual(op['combination_prices'][1]['impact'],'0')
        self.assertEqual(op['pum']['combinations'][1]['unit_price'],'480.000000')

    def test_missing_initial_product_blocks_instead_of_using_target(self):
        live,e,c=self.ready();live['baseline']['products']=[]
        plan=sync.build_plan(live,e,c);self.assertFalse(plan['operations']);self.assertIn('SIN_BASE',plan['rows'][0]['motivo'])

    def test_ssh_failure_never_falls_back_to_target(self):
        settings=dict(test_host='192.168.0.229',baseline_host=base_congelada.HOST,prestashop_root='/var/www/html',env_file='/opt/2prestashopsync/.env')
        with patch('base_congelada.subprocess.run',side_effect=subprocess.TimeoutExpired('ssh',120)):
            with self.assertRaisesRegex(RuntimeError,'NO_DISPONIBLE'):base_congelada.read(settings)
        with self.assertRaisesRegex(ValueError,'nunca destino'):base_congelada.read(dict(settings,test_host=base_congelada.HOST))

    def test_same_combination_id_with_different_attributes_is_not_a_match(self):
        live,e,c=self.ready();current=live['products'][0]['combinations'][0]
        old=live['baseline']['products'][0];old['combinations'][0]['attributes'][0]['label']='Otra presentación'
        self.assertIsNone(base_congelada.combination(old,current))

    def test_changes_csv_records_real_write_even_if_result_equals_initial_value(self):
        live,e,c=self.ready();live['products'][0]['price']='99999'
        plan=sync.build_plan(live,e,c);op=plan['operations'][0]
        journal=dict(results=[dict(operation=op,verification=dict(prices=[dict(combination_id=u['combination_id'],visible_price=u['net_price'],unit_price='480') for u in op['presentations']]))])
        rows=sincronizar.report_rows(live,e,plan,c,journal)
        self.assertEqual(len(sincronizar.price_changes(rows)),2)
        self.assertTrue(all(r['diferencia_respecto_base']=='NO' and r['cambio_aplicado_en_corrida']=='SI' for r in rows))

    def test_configured_baseline_requires_initial_snapshot(self):
        live,e,c=test_prices.Prices().ready();c['baseline_host']=base_congelada.HOST
        with self.assertRaisesRegex(ValueError,'FALTA_LECTURA_BASE'):sync.build_plan(live,e,c)
