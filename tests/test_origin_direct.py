from fixtures import *
from unittest.mock import patch
import origen_directo
import base_congelada
import precios_visibles

class DirectOrigin(unittest.TestCase):
    def sample(self):
        return dict(target='www.mercaboy.com/mercaboy_2024/1',products=[dict(id=85,combinations=[dict(id=70)])],
                    source_prices=dict(host='www.mercaboy.com',prices=[dict(id=85,combination_id=i,actual=8600,proposed=8600) for i in (0,70)],currency=dict(iso_code='COP',precision=0,round_mode=2)),
                    read_only_evidence=dict(session_read_only=True,source_writes_executed=0,remote_php_executed=False))
    def settings(self):
        return dict(test_host='192.168.0.229',SERVIDOR_CONGELADO='www.mercaboy.com',prestashop_root='/var/www/html',baseline_env_file='/protected/source.env')
    def test_production_is_allowed_only_as_origin(self):
        self.assertEqual(sync.frozen_host(self.settings()),'www.mercaboy.com')
        with self.assertRaises(ValueError):sync.test_host(dict(test_host='www.mercaboy.com'))
    def test_direct_reader_reuses_prices_from_same_transaction_without_ssh(self):
        with patch('sync.invoke',return_value=self.sample()) as invoke:
            result=base_congelada.read(self.settings(),[85])
            self.assertEqual(invoke.call_args[0][0],['php',str(sync.ROOT/'origen_directo.php')])
            self.assertEqual(invoke.call_args[0][1]['ids'],[85])
        with patch('precios_visibles.subprocess.run') as external:
            value=precios_visibles.read(self.settings(),result,baseline=True)
            external.assert_not_called()
            self.assertEqual(value['prices'],result['source_prices']['prices'])
    def test_incomplete_duplicate_or_unverified_reads_are_rejected(self):
        for case in ('host','prices','duplicate','read_only','writes','php'):
            with self.subTest(case=case):
                value=self.sample()
                if case=='host':value['target']='192.168.0.229/mercaboy_pruebas/1'
                if case=='prices':value['source_prices']['prices'].pop()
                if case=='duplicate':value['source_prices']['prices'].append(value['source_prices']['prices'][0])
                if case=='read_only':value['read_only_evidence']['session_read_only']=False
                if case=='writes':value['read_only_evidence']['source_writes_executed']=1
                if case=='php':value['read_only_evidence']['remote_php_executed']=True
                with patch('sync.invoke',return_value=value),self.assertRaises(ValueError):origen_directo.read(self.settings())
    def test_missing_prices_do_not_fall_back_to_destination(self):
        with self.assertRaisesRegex(ValueError,'INCOMPLETOS'):
            origen_directo.prices(dict(products=[dict(id=85,combinations=[])]))
