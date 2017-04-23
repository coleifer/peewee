from peewee import *
from playhouse.postgres_ext import *

from .base import ModelTestCase
from .base import TestModel


db = PostgresqlExtDatabase('peewee_test')


class HStoreModel(TestModel):
    name = CharField()
    data = HStoreField()


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
        self.t1 = None
        self.t2 = None

    def create(self):
        self.t1 = HStoreModel.create(name='t1', data={'k1': 'v1', 'k2': 'v2'})
        self.t2 = HStoreModel.create(name='t2', data={'k2': 'v2', 'k3': 'v3'})

    def by_name(self, name):
        return HStoreModel.get(HStoreModel.name == name).data

    def test_hstore_storage(self):
        self.create()
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
        self.create()

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

    def test_hstore_filtering(self):
        self.create()

        def assertWhere(expr, names):
            query = HStoreModel.select().where(expr)
            self.assertEqual([x.name for x in query], names)

        D = HStoreModel.data
        assertWhere(D == {'k1': 'v1', 'k2': 'v2'}, ['t1'])

        assertWhere(D == {'k2': 'v2'}, [])

        assertWhere(D.contains('k3'), ['t2'])
        assertWhere(D.contains(['k2', 'k3']), ['t2'])
        assertWhere(D.contains(['k2']), ['t1', 't2'])

        # test dict
        assertWhere(D.contains({'k2': 'v2', 'k3': 'v3'}), ['t2'])
        assertWhere(D.contains({'k2': 'v2'}), ['t1', 't2'])
        assertWhere(D.contains({'k2': 'v3'}), [])

        # test contains any.
        assertWhere(D.contains_any('k3', 'kx'), ['t2'])
        assertWhere(D.contains_any('k2', 'x', 'k3'), ['t1', 't2'])
        assertWhere(D.contains_any('x', 'kx', 'y'), [])
