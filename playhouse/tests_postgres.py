import unittest

from postgres_ext import *


test_db = PostgresqlExtDatabase('peewee_test', user='postgres')


class BaseModel(Model):
    class Meta:
        database = test_db

class Testing(BaseModel):
    name = CharField()
    data = HStoreField()

    class Meta:
        ordering = ('name',)


class PostgresExtTestCase(unittest.TestCase):
    def setUp(self):
        Testing.drop_table(True)
        Testing.create_table()
        self.t1 = None
        self.t2 = None

    def create(self):
        self.t1 = Testing.create(name='t1', data={'k1': 'v1', 'k2': 'v2'})
        self.t2 = Testing.create(name='t2', data={'k2': 'v2', 'k3': 'v3'})

    def test_storage(self):
        self.create()
        self.assertEqual(Testing.get(name='t1').data, {'k1': 'v1', 'k2': 'v2'})
        self.assertEqual(Testing.get(name='t2').data, {'k2': 'v2', 'k3': 'v3'})

        self.t1.data = {'k4': 'v4'}
        self.t1.save()
        self.assertEqual(Testing.get(name='t1').data, {'k4': 'v4'})

    def test_selecting(self):
        self.create()

        sq = Testing.select(['name', hkeys('data', 'keys')])
        self.assertEqual([(x.name, sorted(x.keys)) for x in sq], [
            ('t1', ['k1', 'k2']), ('t2', ['k2', 'k3'])
        ])

        sq = Testing.select(['name', hvalues('data', 'vals')])
        self.assertEqual([(x.name, sorted(x.vals)) for x in sq], [
            ('t1', ['v1', 'v2']), ('t2', ['v2', 'v3'])
        ])

        sq = Testing.select(['name', hmatrix('data', 'mtx')])
        self.assertEqual([(x.name, sorted(x.mtx)) for x in sq], [
            ('t1', [['k1', 'v1'], ['k2', 'v2']]),
            ('t2', [['k2', 'v2'], ['k3', 'v3']]),
        ])

        sq = Testing.select(['name', hslice('data', 'kz', ['k2', 'k3'])])
        self.assertEqual([(x.name, x.kz) for x in sq], [
            ('t1', {'k2': 'v2'}),
            ('t2', {'k2': 'v2', 'k3': 'v3'}),
        ])

        sq = Testing.select(['name', hslice('data', 'kz', ['k4'])])
        self.assertEqual([(x.name, x.kz) for x in sq], [
            ('t1', {}),
            ('t2', {}),
        ])

        sq = Testing.select(['name', hexist('data', 'ke', 'k3')])
        self.assertEqual([(x.name, x.ke) for x in sq], [
            ('t1', False),
            ('t2', True),
        ])

        sq = Testing.select(['name', hdefined('data', 'ke', 'k3')])
        self.assertEqual([(x.name, x.ke) for x in sq], [
            ('t1', False),
            ('t2', True),
        ])

    def test_filtering(self):
        self.create()

        sq = Testing.select().where(data={'k1': 'v1', 'k2': 'v2'})
        self.assertEqual([x.name for x in sq], ['t1'])

        sq = Testing.select().where(data={'k2': 'v2'})
        self.assertEqual([x.name for x in sq], [])

        # test single key
        sq = Testing.select().where(data__contains='k3')
        self.assertEqual([x.name for x in sq], ['t2'])

        # test list of keys
        sq = Testing.select().where(data__contains=[['k2', 'k3']])
        self.assertEqual([x.name for x in sq], ['t2'])

        sq = Testing.select().where(data__contains=[['k2']])
        self.assertEqual([x.name for x in sq], ['t1', 't2'])

        # test dict
        sq = Testing.select().where(data__contains={'k2': 'v2', 'k3': 'v3'})
        self.assertEqual([x.name for x in sq], ['t2'])

        sq = Testing.select().where(data__contains={'k2': 'v2'})
        self.assertEqual([x.name for x in sq], ['t1', 't2'])

        sq = Testing.select().where(data__contains={'k2': 'v3'})
        self.assertEqual([x.name for x in sq], [])

    def test_filter_functions(self):
        self.create()

        sq = Testing.select().where(hexist('data', ['k2']))
        self.assertEqual([x.name for x in sq], ['t1', 't2'])

        sq = Testing.select().where(hexist('data', ['k3']))
        self.assertEqual([x.name for x in sq], ['t2'])

        sq = Testing.select().where(hdefined('data', ['k2']))
        self.assertEqual([x.name for x in sq], ['t1', 't2'])

        sq = Testing.select().where(hdefined('data', ['k3']))
        self.assertEqual([x.name for x in sq], ['t2'])

    def test_update_functions(self):
        self.create()

        rc = Testing.update(data=hupdate('data', {'k4': 'v4'})).where(name='t1').execute()
        self.assertEqual(rc, 1)
        self.assertEqual(Testing.get(name='t1').data, {'k1': 'v1', 'k2': 'v2', 'k4': 'v4'})

        rc = Testing.update(data=hupdate('data', {'k5': 'v5', 'k6': 'v6'})).where(name='t2').execute()
        self.assertEqual(rc, 1)
        self.assertEqual(Testing.get(name='t2').data, {'k2': 'v2', 'k3': 'v3', 'k5': 'v5', 'k6': 'v6'})

        rc = Testing.update(data=hupdate('data', {'k2': 'vxxx'})).execute()
        self.assertEqual(rc, 2)
        self.assertEqual([x.data for x in Testing.select()], [
            {'k1': 'v1', 'k2': 'vxxx', 'k4': 'v4'},
            {'k2': 'vxxx', 'k3': 'v3', 'k5': 'v5', 'k6': 'v6'}
        ])

        rc = Testing.update(data=hdelete('data', 'k4')).where(name='t1').execute()
        self.assertEqual(rc, 1)
        self.assertEqual(Testing.get(name='t1').data, {'k1': 'v1', 'k2': 'vxxx'})

        rc = Testing.update(data=hdelete('data', 'k5')).execute()
        self.assertEqual(rc, 2)
        self.assertEqual([x.data for x in Testing.select()], [
            {'k1': 'v1', 'k2': 'vxxx'},
            {'k2': 'vxxx', 'k3': 'v3', 'k6': 'v6'}
        ])

        rc = Testing.update(data=hdelete('data', ['k1', 'k2'])).execute()
        self.assertEqual(rc, 2)
        self.assertEqual([x.data for x in Testing.select()], [
            {},
            {'k3': 'v3', 'k6': 'v6'}
        ])
