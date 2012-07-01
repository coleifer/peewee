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

class Testing2(BaseModel):
    name = CharField()
    path = LTreeField()

    class Meta:
        ordering = ('name',)


class PostgresExtHStoreTestCase(unittest.TestCase):
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

        t = Testing.create(name='t3', data={})
        self.assertEqual(Testing.get(name='t3').data, {})

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
        sq = Testing.select().where(data__contains=['k2', 'k3'])
        self.assertEqual([x.name for x in sq], ['t2'])

        sq = Testing.select().where(data__contains=['k2'])
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


class PostgresExtLTreeTestCase(unittest.TestCase):
    def setUp(self):
        Testing2.drop_table(True)
        Testing2.create_table()
        self.t1 = None
        self.t2 = None

    def create(self):
        self.t1 = Testing2.create(name='t1', path='alpha.beta.delta')
        self.t2 = Testing2.create(name='t2', path='alpha.beta.gamma.epsilon')

    def test_storage(self):
        self.create()
        self.assertEqual(Testing2.get(name='t1').path, 'alpha.beta.delta')
        self.assertEqual(Testing2.get(name='t2').path, 'alpha.beta.gamma.epsilon')

        self.t1.path = 'alpha.beta.delta.gamma'
        self.t1.save()
        self.assertEqual(Testing2.get(name='t1').path, 'alpha.beta.delta.gamma')

        t = Testing2.create(name='t3', path='')
        self.assertEqual(Testing2.get(name='t3').path, '')

    def test_selecting(self):
        self.create()

        sq = Testing2.select(['name', lsubtree('path', 1, 2, 'stree')])
        self.assertEqual([(x.name, x.stree) for x in sq], [
            ('t1', 'beta'), ('t2', 'beta'),
        ])

        sq = Testing2.select(['name', lsubpath('path', 0, 2, 'stree')])
        self.assertEqual([(x.name, x.stree) for x in sq], [
            ('t1', 'alpha.beta'), ('t2', 'alpha.beta'),
        ])

        sq = Testing2.select(['name', lsubpath('path', -1, 1, 'stree')])
        self.assertEqual([(x.name, x.stree) for x in sq], [
            ('t1', 'delta'), ('t2', 'epsilon'),
        ])

        sq = Testing2.select(['name', lsubpath('path', 1, 'stree')])
        self.assertEqual([(x.name, x.stree) for x in sq], [
            ('t1', 'beta.delta'), ('t2', 'beta.gamma.epsilon'),
        ])

        sq = Testing2.select(['name', nlevel('path', 'lvl')])
        self.assertEqual([(x.name, x.lvl) for x in sq], [
            ('t1', 3), ('t2', 4),
        ])

        sq = Testing2.select(['name', lindex('path', 'beta', 'idx')])
        self.assertEqual([(x.name, x.idx) for x in sq], [
            ('t1', 1), ('t2', 1),
        ])

        sq = Testing2.select(['name', lindex('path', 'delta', 'idx')])
        self.assertEqual([(x.name, x.idx) for x in sq], [
            ('t1', 2), ('t2', -1),
        ])

    def test_filtering(self):
        t1 = Testing2.create(name='t1', path='a.b.c')
        t2 = Testing2.create(name='t2', path='a.b.d.e')
        t3 = Testing2.create(name='t3', path='a.b.d.f')
        t4 = Testing2.create(name='t4', path='a.b.e')

        def assertExpected(sq, res):
            self.assertEqual([x.name for x in sq], res)

        bq = Testing2.select()

        sq = bq.where(path__lchildren='a.b.d')
        assertExpected(sq, ['t2', 't3'])

        sq = bq.where(path__lchildren='a.b.c')
        assertExpected(sq, ['t1'])

        sq = bq.where(path__lmatch='a.b.*{1}')
        assertExpected(sq, ['t1', 't4'])

        sq = bq.where(path__lmatch='*.b.*{2}')
        assertExpected(sq, ['t2', 't3'])

        sq = bq.where(path__lmatch='*.B@.!d|e')
        assertExpected(sq, ['t1'])

        sq = bq.where(path__lmatch_text='B@ & D@')
        assertExpected(sq, ['t2', 't3'])

        sq = bq.where(path__lmatch_text='a & d & !e')
        assertExpected(sq, ['t3'])

        sq = Testing2.select().where(path__contains='*.d.*')
        assertExpected(sq, ['t2', 't3'])

        sq = Testing2.select().where(path__startswith='a.b.d')
        assertExpected(sq, ['t2', 't3'])

        sq = Testing2.select().where(path__startswith='b.d')
        assertExpected(sq, [])
