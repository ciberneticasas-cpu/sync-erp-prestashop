import copy
import csv
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import unittest
import sync


def product(combinations=None):
    return dict(id=7159, name='Eutarpan 100 Tabletas', reference='26074', ean13='7707019328622',
                price='48000.000000', active='1', ecotax='0', product_type='standard',
                combinations=combinations or [])


def erp_product():
    return dict(erp_id='026074', reference='026074', ean='7707019328622', ean2='', ean3='',
                name='EUTARPAN 10MG 10TAB CJAX100TAB', unit='CJA', gross='48000', tax='0', qty='2', manages='S')


def presentation(factor='0.1', gross='0', from_main='1', ident='1414', label='BLISTER'):
    return dict(erp_id='026074', presentation_id=ident, label=label, factor=factor, gross=gross, from_main=from_main)


def combo(ident, label, ref):
    return dict(id=ident, reference=ref, price='0', attributes=[dict(group_name='Presentación', label=label)])


def sample():
    ps = product([combo(142, 'Caja', '026074'), combo(143, 'Sobre', '026074:1414')])
    e = dict(host='192.168.0.231', products=[erp_product()], presentations=[presentation()], legacy_factors={'7159:026074': '1'})
    return dict(target='192.168.0.186/mercaboy_pruebas/1', products=[ps]), e, dict(mappings={}, test_host='192.168.0.186')


class PriceRules(unittest.TestCase):
    def test_eutarpan_negative_impact(self):
        snapshot, erp, settings = sample()
        plan = sync.build_plan(snapshot, erp, settings)
        item = plan['operations'][0]['presentations'][1]
        self.assertEqual(item['impact'], '-43200.000000')
        self.assertEqual(item['net_price'], '4800.000000')
        self.assertEqual(item['combination_id'], 143)
        self.assertTrue(plan['operations'][0]['stage_disabled'])

    def test_ketoprofeno_exact_one_third(self):
        e = erp_product(); e['gross'] = '37350'
        units, _, _ = sync.presentations_for(e, [presentation(str(Decimal(1) / 3))])
        self.assertEqual(units[1]['net_price'], '12450.000000')

    def test_box_package_equivalent_omitted(self):
        units, aliases, issues = sync.presentations_for(erp_product(), [presentation('1', label='Paquete')])
        self.assertEqual(len(units), 1)
        self.assertEqual(aliases[0]['equivalent_to'], 'BASE')
        self.assertFalse(issues)

    def test_same_price_different_amount_is_not_silently_removed(self):
        units, aliases, issues = sync.presentations_for(erp_product(), [presentation('0.1', '48000', '0')])
        self.assertEqual(len(units), 2)
        self.assertFalse(aliases)
        self.assertTrue(issues)

    def test_factor_one_different_commercial_price_is_kept(self):
        units, aliases, issues = sync.presentations_for(erp_product(), [presentation('1', '45000', '0')])
        self.assertEqual(len(units), 2)
        self.assertEqual(units[1]['net_price'], '45000.000000')

    def test_explicit_price_takes_precedence_when_flag_false(self):
        units, _, _ = sync.presentations_for(erp_product(), [presentation('0.1', '5100', '0')])
        self.assertEqual(units[1]['net_price'], '5100.000000')

    def test_tax_formats_match_legacy(self):
        for tax in ['19', '0.19', '1.19']:
            self.assertEqual(sync.net_price('11900', tax), Decimal('10000'))

    def test_invalid_inputs_fail_closed(self):
        for value in ['', 'NaN', 'Infinity', '-1', '0']:
            with self.assertRaises(ValueError):
                sync.net_price(value, '0')

    def test_simple_legacy_factor_is_retained(self):
        s, e, settings = sample(); s['products'][0]['combinations'] = []
        e['products'][0]['manages'] = 'N'; e['presentations'] = []; e['legacy_factors']['7159:026074'] = '0.5'
        plan = sync.build_plan(s, e, settings)
        self.assertEqual(plan['operations'][0]['base_price'], '24000.000000')
        self.assertFalse(plan['operations'][0]['stage_disabled'])
        self.assertIsNone(plan['operations'][0]['presentations'][0]['quantity'])

    def test_noop_simple_has_no_proposal(self):
        s, e, settings = sample(); s['products'][0]['combinations'] = []
        e['products'][0]['manages'] = 'N'; e['presentations'] = []
        plan = sync.build_plan(s, e, settings)
        self.assertFalse(plan['operations'])
        self.assertEqual(plan['unchanged'], 1)


class Matching(unittest.TestCase):
    def test_real_duplicate_reference_disambiguated_by_ean(self):
        erp = dict(products=[erp_product(), dict(erp_product(), erp_id='031891', ean='7707019313505')])
        self.assertEqual(sync.resolve(product(), erp, {})['erp_id'], '026074')

    def test_ambiguous_reference_without_ean_is_blocked(self):
        erp = dict(products=[erp_product(), dict(erp_product(), erp_id='031891', ean='7707019313505')])
        ps = product(); ps['ean13'] = ''
        with self.assertRaisesRegex(ValueError, 'AMBIGUO'):
            sync.resolve(ps, erp, {})

    def test_reference_ean_conflict_blocked(self):
        other = dict(erp_product(), erp_id='031891', reference='31891', ean='999')
        ps = product(); ps['ean13'] = '999'
        with self.assertRaisesRegex(ValueError, 'CONFLICTO'):
            sync.resolve(ps, dict(products=[erp_product(), other]), {})

    def test_duplicate_combination_references_blocked(self):
        s, e, settings = sample(); s['products'][0]['combinations'][1]['reference'] = '026074'
        plan = sync.build_plan(s, e, settings)
        self.assertFalse(plan['operations'])
        self.assertIn('REFERENCIAS_DE_COMBINACION_NO_UNICAS', plan['rows'][0]['motivo'])

    def test_unknown_existing_combination_is_not_deleted(self):
        s, e, settings = sample(); s['products'][0]['combinations'].append(combo(144, 'Especial', '999'))
        plan = sync.build_plan(s, e, settings)
        self.assertFalse(plan['operations'])
        self.assertIn('SIN_MAPEAR', plan['rows'][0]['motivo'])

    def test_missing_new_reference_blocked(self):
        s, e, settings = sample(); s['products'][0]['combinations'] = []
        plan = sync.build_plan(s, e, settings)
        self.assertFalse(plan['operations'])
        self.assertIn('FALTA_REFERENCIA', plan['rows'][0]['motivo'])

    def test_tuple_strategy_proposes_real_erp_pair_without_ean(self):
        s, e, settings = sample(); settings['reference_strategy'] = 'erp_tuple'
        s['products'][0]['combinations'][1]['reference'] = '026074'
        plan = sync.build_plan(s, e, settings)
        self.assertEqual(plan['operations'][0]['presentations'][1]['reference'], '026074:1414')
        self.assertIn('CLAVE_TECNICA', plan['rows'][1]['origen_referencia'])

    def test_applied_presentations_are_noop_on_next_audit(self):
        s, e, settings = sample(); ps = s['products'][0]; ps['active'] = '0'
        for combo in ps['combinations']:
            combo['minimal_quantity'] = '1'; combo['default_on'] = '1' if combo['id'] == 142 else None
            combo['price'] = '0' if combo['id'] == 142 else '-43200'
        plan = sync.build_plan(s, e, settings)
        self.assertFalse(plan['operations'])
        self.assertEqual(plan['unchanged'], 1)

    def test_visible_preview_disables_purchase_in_csv(self):
        s, e, settings = sample(); settings['presentation_mode'] = 'visible_preview'
        plan = sync.build_plan(s, e, settings)
        self.assertTrue(plan['operations'][0]['preview_only'])
        self.assertFalse(plan['operations'][0]['stage_disabled'])
        self.assertEqual(plan['rows'][0]['activo_destino'], '1')
        self.assertEqual(plan['rows'][0]['disponible_para_pedido_destino'], '0')

    def test_production_target_blocked(self):
        s, e, settings = sample(); s['target'] = 'www.mercaboy.com'
        with self.assertRaises(ValueError):
            sync.build_plan(s, e, settings)


class Approval(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'revision.csv'
        self.plan = sync.build_plan(*sample())

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows):
        with self.path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=sync.FIELDS)
            writer.writeheader(); writer.writerows(rows)
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_full_product_approval(self):
        rows = [dict(r, autorizar='SI') for r in self.plan['rows']]
        selected = sync.approved_operations(self.plan, self.path, self.write(rows))
        self.assertEqual(len(selected), 1)

    def test_partial_presentation_approval_rejected(self):
        rows = copy.deepcopy(self.plan['rows']); rows[0]['autorizar'] = 'SI'
        with self.assertRaisesRegex(ValueError, 'todas'):
            sync.approved_operations(self.plan, self.path, self.write(rows))

    def test_modified_price_rejected_even_with_matching_file_hash(self):
        rows = [dict(r, autorizar='SI') for r in self.plan['rows']]; rows[0]['precio_padre_propuesto'] = '1'
        with self.assertRaisesRegex(ValueError, 'Solo puede'):
            sync.approved_operations(self.plan, self.path, self.write(rows))

    def test_unapproved_csv_does_not_apply(self):
        with self.assertRaisesRegex(ValueError, 'No hay'):
            sync.approved_operations(self.plan, self.path, self.write(self.plan['rows']))

    def test_hash_mismatch_rejected(self):
        self.write(self.plan['rows'])
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            sync.approved_operations(self.plan, self.path, '0' * 64)


class StockAndOrders(unittest.TestCase):
    def test_shared_stock_cannot_be_copied_twice(self):
        with self.assertRaisesRegex(ValueError, 'Sobreventa'):
            sync.validate_allocation('1', '0', [dict(quantity=1, factor=1), dict(quantity=10, factor='.1')])

    def test_partition_subtracts_reservations(self):
        result = sync.validate_allocation('2', '.3', [dict(quantity=1, factor=1), dict(quantity=7, factor='.1')])
        self.assertEqual(Decimal(result['remaining_base']), 0)

    def test_order_uses_combination_and_erp_factor(self):
        plan = sync.build_plan(*sample())
        line = dict(product_id=7159, product_attribute_id=143, product_reference='026074:1414', product_quantity=3)
        self.assertEqual(sync.convert_order([line], plan['operations'])[0]['quantity_erp_base'], '0.3')

    def test_parent_only_order_rejected(self):
        plan = sync.build_plan(*sample())
        line = dict(product_id=7159, product_attribute_id=0, product_reference='026074', product_quantity=3)
        with self.assertRaises(ValueError):
            sync.convert_order([line], plan['operations'])


if __name__ == '__main__':
    unittest.main()
