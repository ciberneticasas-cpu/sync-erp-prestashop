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
                name='EUTARPAN 10MG 10TAB CJAX100TAB', unit='CJA', gross='48000', tax='0', qty='2', manages='S', state='A')


def presentation(factor='0.1', gross='0', from_main='1', ident='1414', label='BLISTER'):
    return dict(erp_id='026074', presentation_id=ident, label=label, factor=factor, gross=gross, from_main=from_main)


def combo(ident, label, ref):
    return dict(id=ident, reference=ref, price='0', attributes=[dict(group_name='Presentación', label=label)])


def sample():
    ps = product([combo(142, 'Caja', '026074'), combo(143, 'Sobre', '026074:1414')])
    e = dict(host='192.168.0.231', products=[erp_product()], presentations=[presentation()], legacy_factors={'7159:026074': '1'})
    return dict(target='192.168.0.186/mercaboy_pruebas/1', products=[ps]), e, dict(mappings={}, test_host='192.168.0.186')
