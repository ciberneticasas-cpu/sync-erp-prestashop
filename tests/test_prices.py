from fixtures import *
import match_erp
import vigencia
import sincronizar

class Prices(unittest.TestCase):
    def ready(self):
        s,e,c=sample()
        for combo in s['products'][0]['combinations']:
            combo.update(minimal_quantity='3',default_on='1' if combo['id']==142 else None)
            combo['price']='0' if combo['id']==142 else '-43200'
        return s,e,c
    def test_existing_presentations_only_prices_and_noop(self):
        s,e,c=self.ready();self.assertEqual(sync.build_plan(s,e,c)['operations'],[])
        e['products'][0]['gross']='50000';op=sync.build_plan(s,e,c)['operations'][0]
        self.assertTrue(op['prices_only']);self.assertFalse(op['preview_only']);self.assertFalse(op['stage_disabled']);self.assertEqual(op['new_name'],'')
        self.assertEqual(op['presentations'][1]['impact'],'-45000.000000');self.assertEqual(op['presentations'][1]['net_price'],'5000.000000')
        self.assertTrue(all(u['quantity'] is None for u in op['presentations']))
    def test_missing_combination_never_created(self):
        s,e,c=self.ready();s['products'][0]['combinations'].pop()
        p=sync.build_plan(s,e,c);self.assertFalse(p['operations']);self.assertIn('PENDIENTE_PRESENTACIONES',p['rows'][0]['motivo'])
    def test_inactive_erp_excluded_even_manual_mapping(self):
        s,e,c=self.ready();e['products'][0]['state']='I';c['mappings']={'7159':{'erp_id':'026074'}}
        p=sync.build_plan(s,e,c);self.assertFalse(p['operations']);rows=sincronizar.report_rows(s,e,p,c)
        self.assertEqual(len(rows),2);self.assertTrue(all(r['resultado']=='EXCLUIDO_ERP' and r['estado_erp']=='I' for r in rows))
    def test_mark_boundaries_and_unknown_state(self):
        self.assertFalse(vigencia.marks(dict(erp_product(),name='DESCONGEL')))
        for changes in [dict(state=''),dict(name='Producto (no usar)'),dict(ean2='DESCO-32'),dict(ean='ANULAR')]:
            self.assertTrue(vigencia.marks(dict(erp_product(),**changes)))
    def test_active_replacement_requires_review(self):
        s,e,c=self.ready();old=e['products'][0];old.update(state='I',ean='DESCO-1')
        e['products'].append(dict(old,state='A',erp_id='999',reference='999',ean=s['products'][0]['ean13']))
        selected,_,warning=match_erp.resolve(s['products'][0],e,{})
        self.assertEqual(selected['erp_id'],'999');self.assertIn('REVISAR_SUSTITUCION',warning);self.assertFalse(sync.build_plan(s,e,c)['operations'])
    def test_inactive_prestashop_in_report_untouched(self):
        s,e,c=self.ready();s['products'][0]['active']='0';e['products'][0]['gross']='99999'
        p=sync.build_plan(s,e,c);self.assertFalse(p['operations'])
        self.assertTrue(all(r['resultado']=='INACTIVO_PRESTASHOP' for r in sincronizar.report_rows(s,e,p,c)))
    def test_changes_log_excludes_noops_failures_and_audits(self):
        row=dict(resultado='APLICADO',precio_mariadb='10',precio_final_sin_iva='20',precio_base_anterior='100',precio_base_nuevo='200',impacto_anterior='-90',impacto_precio='-180')
        self.assertEqual(sincronizar.price_changes([row,dict(row,resultado='ERROR'),dict(row,resultado='PROPUESTO')]),[row])
        self.assertEqual(sincronizar.price_changes([dict(row,precio_mariadb='20',precio_base_anterior='200',impacto_anterior='-180')]),[])
    def test_simple_with_nonpresentation_combinations_keeps_impacts(self):
        s,e,c=self.ready();e['presentations']=[];e['products'][0]['manages']='N';e['products'][0]['gross']='50000'
        for combo in s['products'][0]['combinations']:combo['attributes'][0]['group_name']='Talla'
        op=sync.build_plan(s,e,c)['operations'][0];self.assertEqual(op['mode'],'simple');self.assertEqual(op['base_price'],'50000.000000')
    def test_removing_all_erp_alternatives_keeps_both_web_rows(self):
        s,e,c=self.ready();e['presentations']=[];e['products'][0]['manages']='N'
        p=sync.build_plan(s,e,c);self.assertFalse(p['operations']);rows=sincronizar.report_rows(s,e,p,c)
        self.assertEqual(len(rows),2);self.assertEqual({r['id_combinacion'] for r in rows},{142,143})
        self.assertTrue(all(r['resultado']=='PENDIENTE_PRESENTACIONES' for r in rows))
        self.assertEqual(rows[1]['situacion_presentacion'],'SOLO_WEB_REVISAR_RETIRO')
    def test_extra_web_combination_never_disappears_from_csv(self):
        s,e,c=self.ready();s['products'][0]['combinations'].append(combo(144,'Fraccion retirada','old'))
        p=sync.build_plan(s,e,c);self.assertFalse(p['operations']);rows=sincronizar.report_rows(s,e,p,c)
        self.assertEqual({r['id_combinacion'] for r in rows},{142,143,144})

    def test_inactive_barcode_duplicate_does_not_poison_matching_active_reference(self):
        s,e,c=self.ready()
        e['products'].append(dict(e['products'][0],state='I',erp_id='999',reference='999'))
        selected,criterion,warning=match_erp.resolve(s['products'][0],e,{})
        self.assertEqual(selected['erp_id'],'026074');self.assertEqual(warning,'')
        self.assertEqual(sync.build_plan(s,e,c)['operations'],[])

    def test_erp_change_is_recorded_without_starting_writer(self):
        from unittest.mock import patch
        import aplicar_precios
        s,e,c=self.ready();e['products'][0]['gross']='50000'
        plan=sync.build_plan(s,e,c);live=copy.deepcopy(e);live['products'][0]['gross']='51000'
        with tempfile.TemporaryDirectory() as d:
            with patch('sync.erp_read',return_value=live),patch('subprocess.Popen') as worker:
                journal=aplicar_precios.apply(plan,c,Path(d));worker.assert_not_called()
            self.assertEqual(journal['results'],[])
            self.assertEqual(journal['errors'][0]['product_id'],7159)
            self.assertIn('ERP_CAMBIO',journal['errors'][0]['error'])
