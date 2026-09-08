import copy
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import match_erp
import sincronizar
import sync
from test_sync import sample, erp_product, product

class LegacyMatch(unittest.TestCase):
    def test_reference_priority_and_collision_evidence(self):
        e1=dict(erp_product(),reference='444');e2=dict(e1,erp_id='123',reference='26074',ean='999')
        p=product();p['ean13']=e1['ean']
        found,criterion,warning=match_erp.resolve(p,{'products':[e1,e2]}, {})
        self.assertEqual(found['erp_id'],'123')
        self.assertEqual(criterion,'reference->reference')
        self.assertTrue(warning)
    def test_ambiguous_reference_falls_back_to_unique_barcode(self):
        a=erp_product();b=dict(a,erp_id='123',ean='999')
        found,criterion,_=match_erp.resolve(product(),{'products':[a,b]}, {})
        self.assertEqual(found['erp_id'],a['erp_id'])
        self.assertEqual(criterion,'reference->erp_id')
    def test_no_arbitrary_choice_on_duplicates(self):
        a=erp_product();b=dict(a,erp_id='123');p=product();p['reference']='';
        with self.assertRaisesRegex(ValueError,'AMBIGUO'):match_erp.resolve(p,{'products':[a,b]}, {})
    def test_exact_numeric_key_precedes_normalized_key(self):
        a=erp_product();b=dict(a,erp_id='123',reference='26074',ean='999')
        p=product();p['reference']='026074'
        self.assertEqual(match_erp.resolve(p,{'products':[a,b]}, {})[0]['erp_id'],a['erp_id'])

class Workflow(unittest.TestCase):
    def test_fraction_gets_erp_name_and_real_combinations(self):
        s,e,c=sample();s['products'][0].update(name='Eutarpan Fracción 10 tabletas',combinations=[])
        c.update(automatic_presentation_names=True,reference_strategy='erp_tuple',presentation_mode='visible_preview')
        p=sync.build_plan(s,e,c);self.assertEqual(len(p['operations']),1)
        self.assertIn(e['products'][0]['name'],p['operations'][0]['new_name'])
        self.assertEqual(p['operations'][0]['presentations'][1]['net_price'],'4800.000000')
    def test_unrelated_variants_preserved_as_base_price_only(self):
        s,e,c=sample();e['presentations']=[];e['products'][0]['manages']='N'
        s['products'][0]['price']='100'
        for combo in s['products'][0]['combinations']:combo['attributes'][0]['group_name']='Grosor'
        c['preserve_nonpresentation_combinations']=True
        op=sync.build_plan(s,e,c)['operations'][0]
        self.assertEqual(op['mode'],'simple');self.assertIsNone(op['presentations'][0]['quantity'])
    def test_known_conflict_does_not_write_unreviewed_product(self):
        s,e,c=sample();e['products'][0]['reference']='444';e['products'].append(dict(e['products'][0],erp_id='123',reference='26074',ean='999'))
        c.update(match_strategy='legacy_priority',review_match_conflicts=True)
        p=sync.build_plan(s,e,c);self.assertFalse(p['operations']);self.assertIn('MATCH_DISCREPANTE',p['rows'][0]['motivo'])
    def test_blister_family_is_last_and_csv_prefix_exact(self):
        s,e,c=sample();c['reference_strategy']='erp_tuple';c['max_plan_age_hours']=24
        simple=dict(s['products'][0],id=9000,reference='123',ean13='999',combinations=[],price='100')
        s['products'].append(simple);e['products'].append(dict(erp_product(),erp_id='123',reference='123',ean='999',manages='N',gross='100'))
        e['legacy_factors']['9000:123']='1'
        rows=sincronizar.report_rows(s,e,sync.build_plan(s,e,c),c)
        self.assertEqual([r['id_producto'] for r in rows],[9000,7159,7159])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.csv';sincronizar.write_csv(p,rows)
            with p.open(encoding='utf-8-sig') as f:header=next(csv.reader(f))
            self.assertEqual(header[:23],sincronizar.LEGACY_FIELDS)
    def test_dry_run_never_calls_mutations(self):
        s,e,c=sample();c.update(reference_strategy='erp_tuple')
        with tempfile.TemporaryDirectory() as d:
            with patch('sys.argv',['sincronizar.py','--output',d+'/audit']),patch('sync.read_json',return_value=c),patch('sync.bridge',return_value=s) as bridge,patch('sync.erp_read',return_value=e),patch('sync.apply') as apply,patch('subprocess.check_call') as repair:
                self.assertEqual(sincronizar.main(),0);apply.assert_not_called();repair.assert_not_called()
                self.assertEqual(bridge.call_count,1)

if __name__=='__main__':unittest.main()

class DirectApplication(unittest.TestCase):
    def test_apply_attempts_every_operation_and_records_failure(self):
        import argparse
        s,e,c=sample();c['reference_strategy']='erp_tuple';c['max_plan_age_hours']=24
        base=sync.build_plan(s,e,c)
        first=base['operations'][0]
        base['operations']=[]
        for ident in [7159,7160,7161]:
            op=copy.deepcopy(first);op['id']=ident;op['before']['id']=ident;base['operations'].append(op)
        live={'products':[o['before'] for o in base['operations']]}
        def native(settings,command='snapshot',**kw):
            if command=='snapshot':return live
            self.assertEqual(kw['authorization'],'CLI_APPLY_TEST_ONLY')
            if kw['operation']['id']==7160:raise RuntimeError('fallo simulado')
            return {'operation':kw['operation'],'verification':{'prices':[]}}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'plan.json';sync.write_json(path,base)
            with patch('sync.ROOT',root),patch('sync.bridge',side_effect=native) as bridge,patch('sync.erp_read',return_value=e):
                sync.apply(argparse.Namespace(plan=str(path),plan_sha256=sync.digest(base),direct_apply=True),c)
            journal=sync.read_json(root/'aplicacion.json')
            self.assertEqual([r['operation']['id'] for r in journal['results']],[7159,7161])
            self.assertEqual(journal['errors'][0]['product_id'],7160)
            self.assertEqual(journal['status'],'APLICADO_CON_ERRORES')
