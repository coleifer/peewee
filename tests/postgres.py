#coding:utf-8
from peewee import *
from playhouse.postgres_ext import *

from .base import ModelTestCase
from .base import TestModel


db = PostgresqlExtDatabase('peewee_test')


class HStoreModel(TestModel):
    name = CharField()
    data = HStoreField()
D = HStoreModel.data


class ArrayModel(TestModel):
    tags = ArrayField(CharField)
    ints = ArrayField(IntegerField, dimensions=2)


class TZModel(TestModel):
    dt = DateTimeTZField()


class TestTZField(ModelTestCase):
    database = db
    requires = [TZModel]

    def test_tz_field(self):
        self.database.execute_sql('set time zone "us/central";')

        dt = datetime.datetime.now()
        tz = TZModel.create(dt=dt)
        self.assertTrue(tz.dt.tzinfo is None)

        tz = TZModel.get(TZModel.id == tz.id)



class TestHStoreField(ModelTestCase):
    database = db
    requires = [HStoreModel]

    def setUp(self):
        super(TestHStoreField, self).setUp()
        self.t1 = HStoreModel.create(name='t1', data={'k1': 'v1', 'k2': 'v2'})
        self.t2 = HStoreModel.create(name='t2', data={'k2': 'v2', 'k3': 'v3'})

    def by_name(self, name):
        return HStoreModel.get(HStoreModel.name == name).data

    def test_hstore_storage(self):
        self.assertEqual(self.by_name('t1'), {'k1': 'v1', 'k2': 'v2'})
        self.assertEqual(self.by_name('t2'), {'k2': 'v2', 'k3': 'v3'})

        self.t1.data = {'k4': 'v4'}
        self.t1.save()
        self.assertEqual(self.by_name('t1'), {'k4': 'v4'})

        HStoreModel.create(name='t3', data={})
        self.assertEqual(self.by_name('t3'), {})

    def query(self, *cols):
        return (HStoreModel
                .select(HStoreModel.name, *cols)
                .order_by(HStoreModel.id))

    def test_hstore_selecting(self):
        query = self.query(HStoreModel.data.keys().alias('keys'))
        self.assertEqual([(x.name, sorted(x.keys)) for x in query], [
            ('t1', ['k1', 'k2']), ('t2', ['k2', 'k3'])])

        query = self.query(HStoreModel.data.values().alias('vals'))
        self.assertEqual([(x.name, sorted(x.vals)) for x in query], [
            ('t1', ['v1', 'v2']), ('t2', ['v2', 'v3'])])

        query = self.query(HStoreModel.data.items().alias('mtx'))
        self.assertEqual([(x.name, sorted(x.mtx)) for x in query], [
            ('t1', [['k1', 'v1'], ['k2', 'v2']]),
            ('t2', [['k2', 'v2'], ['k3', 'v3']])])

        query = self.query(HStoreModel.data.slice('k2', 'k3').alias('kz'))
        self.assertEqual([(x.name, x.kz) for x in query], [
            ('t1', {'k2': 'v2'}),
            ('t2', {'k2': 'v2', 'k3': 'v3'})])

        query = self.query(HStoreModel.data.slice('k4').alias('kz'))
        self.assertEqual([(x.name, x.kz) for x in query], [
            ('t1', {}), ('t2', {})])

        query = self.query(HStoreModel.data.exists('k3').alias('ke'))
        self.assertEqual([(x.name, x.ke) for x in query], [
            ('t1', False), ('t2', True)])

        query = self.query(HStoreModel.data.defined('k3').alias('ke'))
        self.assertEqual([(x.name, x.ke) for x in query], [
            ('t1', False), ('t2', True)])

        query = self.query(HStoreModel.data['k1'].alias('k1'))
        self.assertEqual([(x.name, x.k1) for x in query], [
            ('t1', 'v1'), ('t2', None)])

        query = self.query().where(HStoreModel.data['k1'] == 'v1')
        self.assertEqual([x.name for x in query], ['t1'])

    def assertWhere(self, expr, names):
        query = HStoreModel.select().where(expr)
        self.assertEqual([x.name for x in query], names)

    def test_hstore_filtering(self):
        self.assertWhere(D == {'k1': 'v1', 'k2': 'v2'}, ['t1'])
        self.assertWhere(D == {'k2': 'v2'}, [])

        self.assertWhere(D.contains('k3'), ['t2'])
        self.assertWhere(D.contains(['k2', 'k3']), ['t2'])
        self.assertWhere(D.contains(['k2']), ['t1', 't2'])

        # test dict
        self.assertWhere(D.contains({'k2': 'v2', 'k3': 'v3'}), ['t2'])
        self.assertWhere(D.contains({'k2': 'v2'}), ['t1', 't2'])
        self.assertWhere(D.contains({'k2': 'v3'}), [])

        # test contains any.
        self.assertWhere(D.contains_any('k3', 'kx'), ['t2'])
        self.assertWhere(D.contains_any('k2', 'x', 'k3'), ['t1', 't2'])
        self.assertWhere(D.contains_any('x', 'kx', 'y'), [])

    def test_hstore_filter_functions(self):
        self.assertWhere(HStoreModel.data.exists('k2') == True, ['t1', 't2'])
        self.assertWhere(HStoreModel.data.exists('k3') == True, ['t2'])
        self.assertWhere(HStoreModel.data.defined('k2') == True, ['t1', 't2'])
        self.assertWhere(HStoreModel.data.defined('k3') == True, ['t2'])

    def test_hstore_update(self):
        rc = (HStoreModel
              .update(data=D.update(k4='v4'))
              .where(HStoreModel.name == 't1')
              .execute())
        self.assertTrue(rc > 0)

        self.assertEqual(self.by_name('t1'),
                         {'k1': 'v1', 'k2': 'v2', 'k4': 'v4'})

        rc = (HStoreModel
              .update(data=D.update(k5='v5', k6='v6'))
              .where(HStoreModel.name == 't2')
              .execute())
        self.assertTrue(rc > 0)

        self.assertEqual(self.by_name('t2'),
                         {'k2': 'v2', 'k3': 'v3', 'k5': 'v5', 'k6': 'v6'})

        HStoreModel.update(data=D.update(k2='vxxx')).execute()
        self.assertEqual([x.data for x in self.query(D)], [
            {'k1': 'v1', 'k2': 'vxxx', 'k4': 'v4'},
            {'k2': 'vxxx', 'k3': 'v3', 'k5': 'v5', 'k6': 'v6'}])

        (HStoreModel
         .update(data=D.delete('k4'))
         .where(HStoreModel.name == 't1')
         .execute())

        self.assertEqual(self.by_name('t1'), {'k1': 'v1', 'k2': 'vxxx'})

        HStoreModel.update(data=D.delete('k5')).execute()
        self.assertEqual([x.data for x in self.query(D)], [
            {'k1': 'v1', 'k2': 'vxxx'},
            {'k2': 'vxxx', 'k3': 'v3', 'k6': 'v6'}
        ])

        HStoreModel.update(data=D.delete('k1', 'k2')).execute()
        self.assertEqual([x.data for x in self.query(D)], [
            {},
            {'k3': 'v3', 'k6': 'v6'}])


class TestArrayField(ModelTestCase):
    database = db
    requires = [ArrayModel]

    def create_sample(self):
        return ArrayModel.create(
            tags=['alpha', 'beta', 'gamma', 'delta'],
            ints=[[1, 2], [3, 4], [5, 6]])

    def test_array_get_set(self):
        am = self.create_sample()
        am_db = ArrayModel.get(ArrayModel.id == am.id)
        self.assertEqual(am_db.tags, ['alpha', 'beta', 'gamma', 'delta'])
        self.assertEqual(am_db.ints, [[1, 2], [3, 4], [5, 6]])

    def test_array_db_value(self):
        am = ArrayModel.create(tags=('foo', 'bar'), ints=[])
        am_db = ArrayModel.get(ArrayModel.id == am.id)
        self.assertEqual(am_db.tags, ['foo', 'bar'])

    def test_array_search(self):
        def assertAM(where, *instances):
            query = (ArrayModel
                     .select()
                     .where(where)
                     .order_by(ArrayModel.id))
            self.assertEqual([x.id for x in query], [x.id for x in instances])

        am = self.create_sample()
        am2 = ArrayModel.create(tags=['alpha', 'beta'], ints=[[1, 1]])
        am3 = ArrayModel.create(tags=['delta'], ints=[[3, 4]])
        am4 = ArrayModel.create(tags=['中文'], ints=[[3, 4]])
        am5 = ArrayModel.create(tags=['中文', '汉语'], ints=[[3, 4]])

        AM = ArrayModel
        T = AM.tags

        assertAM((Value('beta') == fn.ANY(T)), am, am2)
        assertAM((Value('delta') == fn.Any(T)), am, am3)
        assertAM(Value('omega') == fn.Any(T))

        # Check the contains operator.
        assertAM(SQL("tags::text[] @> ARRAY['beta']"), am, am2)

        # Use the nicer API.
        assertAM(T.contains('beta'), am, am2)
        assertAM(T.contains('omega', 'delta'))
        assertAM(T.contains('汉语'), am5)
        assertAM(T.contains('alpha', 'delta'), am)

        # Check for any.
        assertAM(T.contains_any('beta'), am, am2)
        assertAM(T.contains_any('中文'), am4, am5)
        assertAM(T.contains_any('omega', 'delta'), am, am3)
        assertAM(T.contains_any('alpha', 'delta'), am, am2, am3)

    def test_array_index_slice(self):
        self.create_sample()
        AM = ArrayModel
        I, T = AM.ints, AM.tags

        row = AM.select(T[1].alias('arrtags')).dicts().get()
        self.assertEqual(row['arrtags'], 'beta')

        row = AM.select(T[2:4].alias('foo')).dicts().get()
        self.assertEqual(row['foo'], ['gamma', 'delta'])

        row = AM.select(I[1][1].alias('ints')).dicts().get()
        self.assertEqual(row['ints'], 4)

        row = AM.select(I[1:2][0].alias('ints')).dicts().get()
        self.assertEqual(row['ints'], [[3], [5]])
