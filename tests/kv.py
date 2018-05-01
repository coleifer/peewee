from peewee import IntegerField
from playhouse.kv import KeyValue

from .base import DatabaseTestCase
from .base import IS_POSTGRESQL
from .base import db
from .base import skip_if


class TestKeyValue(DatabaseTestCase):
    def setUp(self):
        super(TestKeyValue, self).setUp()
        self._kvs = []

    def tearDown(self):
        if self._kvs:
            self.database.drop_tables([kv.model for kv in self._kvs])
        super(TestKeyValue, self).tearDown()

    def create_kv(self, **kwargs):
        kv = KeyValue(database=self.database, **kwargs)
        self._kvs.append(kv)
        return kv

    def test_basic_apis(self):
        KV = self.create_kv()
        KV['k1'] = 'v1'
        KV['k2'] = [0, 1, 2]

        self.assertEqual(KV['k1'], 'v1')
        self.assertEqual(KV['k2'], [0, 1, 2])
        self.assertRaises(KeyError, lambda: KV['k3'])

        self.assertTrue((KV.key < 'k2') in KV)
        self.assertFalse((KV.key > 'k2') in KV)

        del KV['k1']
        KV['k3'] = 'v3'

        self.assertFalse('k1' in KV)
        self.assertTrue('k3' in KV)
        self.assertEqual(sorted(KV.keys()), ['k2', 'k3'])
        self.assertEqual(len(KV), 2)

        data = dict(KV)
        self.assertEqual(data, {
            'k2': [0, 1, 2],
            'k3': 'v3'})

        self.assertEqual(dict(KV), dict(KV.items()))

        self.assertEqual(KV.pop('k2'), [0, 1, 2])
        self.assertRaises(KeyError, lambda: KV['k2'])
        self.assertRaises(KeyError, KV.pop, 'k2')

        self.assertEqual(KV.get('k3'), 'v3')
        self.assertTrue(KV.get('kx') is None)
        self.assertEqual(KV.get('kx', 'vx'), 'vx')

        KV.clear()
        self.assertEqual(len(KV), 0)

    @skip_if(IS_POSTGRESQL, 'requires replace support')
    def test_update(self):
        KV = self.create_kv()
        KV.update(k1='v1', k2='v2', k3='v3')
        self.assertEqual(len(KV), 3)

        KV.update(k1='v1-x', k3='v3-x', k4='v4')
        self.assertEqual(len(KV), 4)

        self.assertEqual(dict(KV), {
            'k1': 'v1-x',
            'k2': 'v2',
            'k3': 'v3-x',
            'k4': 'v4'})

        KV['k1'] = 'v1-y'
        self.assertEqual(len(KV), 4)

        self.assertEqual(dict(KV), {
            'k1': 'v1-y',
            'k2': 'v2',
            'k3': 'v3-x',
            'k4': 'v4'})

    def test_expressions(self):
        KV = self.create_kv(value_field=IntegerField(), ordered=True)
        with self.database.atomic():
            for i in range(1, 11):
                KV['k%d' % i] = i

        self.assertEqual(KV[KV.key < 'k2'], [1, 10])
        self.assertEqual(KV[KV.value > 7], [10, 8, 9])
        self.assertEqual(KV[(KV.key > 'k2') & (KV.key < 'k6')], [3, 4, 5])
        self.assertEqual(KV[KV.key == 'kx'], [])

        del KV[KV.key > 'k3']
        self.assertEqual(dict(KV), {
            'k1': 1,
            'k2': 2,
            'k3': 3,
            'k10': 10})

        KV[KV.value > 2] = 99
        self.assertEqual(dict(KV), {
            'k1': 1,
            'k2': 2,
            'k3': 99,
            'k10': 99})

    def test_integer_keys(self):
        KV = self.create_kv(key_field=IntegerField(primary_key=True),
                            ordered=True)
        KV[1] = 'v1'
        KV[2] = 'v2'
        KV[10] = 'v10'
        self.assertEqual(list(KV), [(1, 'v1'), (2, 'v2'), (10, 'v10')])
        self.assertEqual(list(KV.keys()), [1, 2, 10])
        self.assertEqual(list(KV.values()), ['v1', 'v2', 'v10'])

        del KV[2]
        KV[1] = 'v1-x'
        KV[3] = 'v3'
        self.assertEqual(dict(KV), {
            1: 'v1-x',
            3: 'v3',
            10: 'v10'})
