import unittest
from unittest import mock
import urllib.error
import cambiar_ip
import sync


class IpConfiguration(unittest.TestCase):
    def test_lan_addresses(self):
        for host in ('192.168.0.229', '192.168.0.230', '10.0.2.3', '172.16.2.3'):
            self.assertEqual(sync.target({'test_host': host}), host + '/mercaboy_pruebas/1')

    def test_erp_public_loopback_and_invalid_addresses_rejected(self):
        for host in ('192.168.0.231', '8.8.8.8', '127.0.0.1', 'www.mercaboy.com', '::1', '', '192.168.0.999'):
            with self.assertRaises(ValueError):
                sync.test_host({'test_host': host})

    def test_old_plan_target_does_not_match_new_ip(self):
        self.assertNotEqual(sync.target({'test_host': '192.168.0.186'}), sync.target({'test_host': '192.168.0.229'}))

    def test_http_does_not_follow_redirect_outside_new_host(self):
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError('http://192.168.0.229/', 302, '', {'Location': 'https://www.mercaboy.com/'}, None)
        with mock.patch('cambiar_ip.urllib.request.build_opener', return_value=opener):
            with self.assertRaisesRegex(RuntimeError, 'fuera'):
                cambiar_ip.check_http('192.168.0.229')
        self.assertEqual(opener.open.call_count, 1)


if __name__ == '__main__':
    unittest.main()
