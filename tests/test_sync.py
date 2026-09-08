from fixtures import *

class PriceRules(unittest.TestCase):
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
