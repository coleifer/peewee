#coding:utf-8
import datetime
import uuid
from decimal import Decimal as Dc
from types import MethodType

from peewee import *
from playhouse.postgres_ext import *

from .base import BaseTestCase
from .base import DatabaseTestCase
from .base import ModelTestCase
from .base import TestModel
from .base import db_loader
from .base import requires_models
from .base import skip_unless
from .base_models import Register


db = db_loader('postgres', db_class=PostgresqlExtDatabase)


class HStoreModel(TestModel):
    name = CharField()
    data = HStoreField()
D = HStoreModel.data


class ArrayModel(TestModel):
    tags = ArrayField(CharField)
    ints = ArrayField(IntegerField, dimensions=2)


class UUIDList(TestModel):
    key = CharField()
    id_list = ArrayField(BinaryUUIDField, convert_values=True, index=False)
    id_list_native = ArrayField(UUIDField, index=False)


class ArrayTSModel(TestModel):
    key = CharField(max_length=100, primary_key=True)
    timestamps = ArrayField(TimestampField, convert_values=True)


class DecimalArray(TestModel):
    values = ArrayField(DecimalField, field_kwargs={'decimal_places': 1})


class FTSModel(TestModel):
    title = CharField()
    data = TextField()
    fts_data = TSVectorField()


try:
    class JsonModel(TestModel):
        data = JSONField()

    class JsonModelNull(TestModel):
        data = JSONField(null=True)
except:
    JsonModel = JsonModelNull = None

try:
    class BJson(TestModel):
        data = BinaryJSONField()
except:
    BJson = None


class Normal(TestModel):
    data = TextField()


class Event(TestModel):
    name = CharField()
    duration = IntervalField()


class TZModel(TestModel):
    dt = DateTimeTZField()


class TestTZField(ModelTestCase):
    database = db
    requires = [TZModel]

    def test_tz_field(self):
        self.database.set_time_zone('us/eastern')

        # Our naive datetime is treated as if it were in US/Eastern.
        dt = datetime.datetime(2019, 1, 1, 12)
        tz = TZModel.create(dt=dt)
        self.assertTrue(tz.dt.tzinfo is None)

        # When we retrieve the row, psycopg2 will attach the appropriate tzinfo
        # data. The value is returned as an "aware" datetime in US/Eastern.
        tz_db = TZModel[tz.id]
        self.assertTrue(tz_db.dt.tzinfo is not None)
        self.assertEqual(tz_db.dt.timetuple()[:4], (2019, 1, 1, 12))
        self.assertEqual(tz_db.dt.utctimetuple()[:4], (2019, 1, 1, 17))

        class _UTC(datetime.tzinfo):
            def utcoffset(self, dt): return datetime.timedelta(0)
            def tzname(self, dt): return "UTC"
            def dst(self, dt): return datetime.timedelta(0)
        UTC = _UTC()

        # We can explicitly insert a row with a different timezone, however.
        # When we read the row back, it is returned in US/Eastern.
        dt2 = datetime.datetime(2019, 1, 1, 12, tzinfo=UTC)
        tz2 = TZModel.create(dt=dt2)
        tz2_db = TZModel[tz2.id]
        self.assertEqual(tz2_db.dt.timetuple()[:4], (2019, 1, 1, 7))
        self.assertEqual(tz2_db.dt.utctimetuple()[:4], (2019, 1, 1, 12))

        # Querying using naive datetime, treated as localtime (US/Eastern).
        tzq1 = TZModel.get(TZModel.dt == dt)
        self.assertEqual(tzq1.id, tz.id)

        # Querying using aware datetime, tzinfo is respected.
        tzq2 = TZModel.get(TZModel.dt == dt2)
        self.assertEqual(tzq2.id, tz2.id)

        # Change the connection timezone?
        self.database.set_time_zone('us/central')
        tz_db = TZModel[tz.id]
        self.assertEqual(tz_db.dt.timetuple()[:4], (2019, 1, 1, 11))
        self.assertEqual(tz_db.dt.utctimetuple()[:4], (2019, 1, 1, 17))

        tz2_db = TZModel[tz2.id]
        self.assertEqual(tz2_db.dt.timetuple()[:4], (2019, 1, 1, 6))
        self.assertEqual(tz2_db.dt.utctimetuple()[:4], (2019, 1, 1, 12))


class TestHStoreField(ModelTestCase):
    database = db_loader('postgres', db_class=PostgresqlExtDatabase,
                         register_hstore=True)
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
        query = self.query(D.keys().alias('keys'))
        self.assertEqual([(x.name, sorted(x.keys)) for x in query], [
            ('t1', ['k1', 'k2']), ('t2', ['k2', 'k3'])])

        query = self.query(D.values().alias('vals'))
        self.assertEqual([(x.name, sorted(x.vals)) for x in query], [
            ('t1', ['v1', 'v2']), ('t2', ['v2', 'v3'])])

        query = self.query(D.items().alias('mtx'))
        self.assertEqual([(x.name, sorted(x.mtx)) for x in query], [
            ('t1', [['k1', 'v1'], ['k2', 'v2']]),
            ('t2', [['k2', 'v2'], ['k3', 'v3']])])

        query = self.query(D.slice('k2', 'k3').alias('kz'))
        self.assertEqual([(x.name, x.kz) for x in query], [
            ('t1', {'k2': 'v2'}),
            ('t2', {'k2': 'v2', 'k3': 'v3'})])

        query = self.query(D.slice('k4').alias('kz'))
        self.assertEqual([(x.name, x.kz) for x in query], [
            ('t1', {}), ('t2', {})])

        query = self.query(D.exists('k3').alias('ke'))
        self.assertEqual([(x.name, x.ke) for x in query], [
            ('t1', False), ('t2', True)])

        query = self.query(D.defined('k3').alias('ke'))
        self.assertEqual([(x.name, x.ke) for x in query], [
            ('t1', False), ('t2', True)])

        query = self.query(D['k1'].alias('k1'))
        self.assertEqual([(x.name, x.k1) for x in query], [
            ('t1', 'v1'), ('t2', None)])

        query = self.query().where(D['k1'] == 'v1')
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
        self.assertWhere(D.exists('k2') == True, ['t1', 't2'])
        self.assertWhere(D.exists('k3') == True, ['t2'])
        self.assertWhere(D.defined('k2') == True, ['t1', 't2'])
        self.assertWhere(D.defined('k3') == True, ['t2'])

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

    def test_array_equality(self):
        am1 = ArrayModel.create(tags=['t1'], ints=[[1, 2]])
        am2 = ArrayModel.create(tags=['t2'], ints=[[3, 4]])

        obj = ArrayModel.get(ArrayModel.tags == ['t1'])
        self.assertEqual(obj.id, am1.id)
        self.assertEqual(obj.tags, ['t1'])

        obj = ArrayModel.get(ArrayModel.ints == [[3, 4]])
        self.assertEqual(obj.id, am2.id)

        obj = ArrayModel.get(ArrayModel.tags != ['t1'])
        self.assertEqual(obj.id, am2.id)

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

    @requires_models(DecimalArray)
    def test_field_kwargs(self):
        vl1, vl2 = [Dc('3.1'), Dc('1.3')], [Dc('3.14'), Dc('1')]
        da1, da2 = [DecimalArray.create(values=vl) for vl in (vl1, vl2)]

        da1_db = DecimalArray.get(DecimalArray.id == da1.id)
        da2_db = DecimalArray.get(DecimalArray.id == da2.id)
        self.assertEqual(da1_db.values, [Dc('3.1'), Dc('1.3')])
        self.assertEqual(da2_db.values, [Dc('3.1'), Dc('1.0')])


class TestArrayFieldConvertValues(ModelTestCase):
    database = db
    requires = [ArrayTSModel]

    def dt(self, day, hour=0, minute=0, second=0):
        return datetime.datetime(2018, 1, day, hour, minute, second)

    def test_value_conversion(self):

        data = {
            'k1': [self.dt(1), self.dt(2), self.dt(3)],
            'k2': [],
            'k3': [self.dt(4, 5, 6, 7), self.dt(10, 11, 12, 13)],
        }
        for key in sorted(data):
            ArrayTSModel.create(key=key, timestamps=data[key])

        for key in sorted(data):
            am = ArrayTSModel.get(ArrayTSModel.key == key)
            self.assertEqual(am.timestamps, data[key])

        # Perform lookup using timestamp values.
        ts = ArrayTSModel.get(ArrayTSModel.timestamps.contains(self.dt(3)))
        self.assertEqual(ts.key, 'k1')

        ts = ArrayTSModel.get(
            ArrayTSModel.timestamps.contains(self.dt(4, 5, 6, 7)))
        self.assertEqual(ts.key, 'k3')

        self.assertRaises(ArrayTSModel.DoesNotExist, ArrayTSModel.get,
                          ArrayTSModel.timestamps.contains(self.dt(4, 5, 6)))

    def test_get_with_array_values(self):
        a1 = ArrayTSModel.create(key='k1', timestamps=[self.dt(1)])
        a2 = ArrayTSModel.create(key='k2', timestamps=[self.dt(2), self.dt(3)])

        query = (ArrayTSModel
                 .select()
                 .where(ArrayTSModel.timestamps == [self.dt(1)]))
        a1_db = query.get()
        self.assertEqual(a1_db.id, a1.id)

        query = (ArrayTSModel
                 .select()
                 .where(ArrayTSModel.timestamps == [self.dt(2), self.dt(3)]))
        a2_db = query.get()
        self.assertEqual(a2_db.id, a2.id)

        a1_db = ArrayTSModel.get(timestamps=[self.dt(1)])
        self.assertEqual(a1_db.id, a1.id)

        a2_db = ArrayTSModel.get(timestamps=[self.dt(2), self.dt(3)])
        self.assertEqual(a2_db.id, a2.id)


class TestArrayUUIDField(ModelTestCase):
    database = db
    requires = [UUIDList]

    def setUp(self):
        super(TestArrayUUIDField, self).setUp()
        import psycopg2.extras
        psycopg2.extras.register_uuid()

    def test_array_of_uuids(self):
        u1, u2, u3, u4 = [uuid.uuid4() for _ in range(4)]
        a = UUIDList.create(key='a', id_list=[u1, u2, u3],
                            id_list_native=[u1, u2, u3])
        b = UUIDList.create(key='b', id_list=[u2, u3, u4],
                            id_list_native=[u2, u3, u4])
        a_db = UUIDList.get(UUIDList.key == 'a')
        b_db = UUIDList.get(UUIDList.key == 'b')

        self.assertEqual(a.id_list, [u1, u2, u3])
        self.assertEqual(b.id_list, [u2, u3, u4])

        self.assertEqual(a.id_list_native, [u1, u2, u3])
        self.assertEqual(b.id_list_native, [u2, u3, u4])


class TestTSVectorField(ModelTestCase):
    database = db
    requires = [FTSModel]

    messages = [
        'A faith is a necessity to a man. Woe to him who believes in nothing.',
        'All who call on God in true faith, earnestly from the heart, will '
        'certainly be heard, and will receive what they have asked and desired.',
        'Be faithful in small things because it is in them that your strength lies.',
        'Faith consists in believing when it is beyond the power of reason to believe.',
        'Faith has to do with things that are not seen and hope with things that are not at hand.',
    ]

    def setUp(self):
        super(TestTSVectorField, self).setUp()
        for idx, message in enumerate(self.messages):
            FTSModel.create(title=str(idx), data=message,
                            fts_data=fn.to_tsvector(message))

    def assertMessages(self, expr, expected):
        query = FTSModel.select().where(expr).order_by(FTSModel.id)
        titles = [row.title for row in query]
        self.assertEqual(list(map(int, titles)), expected)

    def test_sql(self):
        query = FTSModel.select().where(Match(FTSModel.data, 'foo bar'))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."title", "t1"."data", "t1"."fts_data" '
            'FROM "fts_model" AS "t1" '
            'WHERE (to_tsvector("t1"."data") @@ to_tsquery(?))'), ['foo bar'])

    def test_match_function(self):
        D = FTSModel.data
        self.assertMessages(Match(D, 'heart'), [1])
        self.assertMessages(Match(D, 'god'), [1])
        self.assertMessages(Match(D, 'faith'), [0, 1, 2, 3, 4])
        self.assertMessages(Match(D, 'thing'), [2, 4])
        self.assertMessages(Match(D, 'faith & things'), [2, 4])
        self.assertMessages(Match(D, 'god | things'), [1, 2, 4])
        self.assertMessages(Match(D, 'god & things'), [])

    def test_tsvector_field(self):
        M = FTSModel.fts_data.match
        self.assertMessages(M('heart'), [1])
        self.assertMessages(M('god'), [1])
        self.assertMessages(M('faith'), [0, 1, 2, 3, 4])
        self.assertMessages(M('thing'), [2, 4])
        self.assertMessages(M('faith & things'), [2, 4])
        self.assertMessages(M('god | things'), [1, 2, 4])
        self.assertMessages(M('god & things'), [])

        # Using the plain parser we cannot express "OR", but individual term
        # match works like we expect and multi-term is AND-ed together.
        self.assertMessages(M('god | things', plain=True), [])
        self.assertMessages(M('god', plain=True), [1])
        self.assertMessages(M('thing', plain=True), [2, 4])
        self.assertMessages(M('faith things', plain=True), [2, 4])


class BaseJsonFieldTestCase(object):
    M = None  # Subclasses must define this.

    def test_json_field(self):
        data = {'k1': ['a1', 'a2'], 'k2': {'k3': 'v3'}}
        j = self.M.create(data=data)
        j_db = self.M.get(j._pk_expr())
        self.assertEqual(j_db.data, data)

    def test_joining_on_json_key(self):
        values = [
            {'foo': 'bar', 'baze': {'nugget': 'alpha'}},
            {'foo': 'bar', 'baze': {'nugget': 'beta'}},
            {'herp': 'derp', 'baze': {'nugget': 'epsilon'}},
            {'herp': 'derp', 'bar': {'nuggie': 'alpha'}},
        ]
        for data in values:
            self.M.create(data=data)

        for value in ['alpha', 'beta', 'gamma', 'delta']:
            Normal.create(data=value)

        query = (self.M
                 .select()
                 .join(Normal, on=(
                     Normal.data == self.M.data['baze']['nugget']))
                 .order_by(self.M.id))
        results = [jm.data for jm in query]
        self.assertEqual(results, [
            {'foo': 'bar', 'baze': {'nugget': 'alpha'}},
            {'foo': 'bar', 'baze': {'nugget': 'beta'}},
        ])

    def test_json_lookup_methods(self):
        data = {
            'gp1': {
                'p1': {'c1': 'foo'},
                'p2': {'c2': 'bar'}},
            'gp2': {}}
        j = self.M.create(data=data)

        def assertLookup(lookup, expected):
            query = (self.M
                     .select(lookup)
                     .where(j._pk_expr())
                     .dicts())
            self.assertEqual(query.get(), expected)

        expr = self.M.data['gp1']['p1']
        assertLookup(expr.alias('p1'), {'p1': '{"c1": "foo"}'})
        assertLookup(expr.as_json().alias('p2'), {'p2': {'c1': 'foo'}})

        expr = self.M.data['gp1']['p1']['c1']
        assertLookup(expr.alias('c1'), {'c1': 'foo'})
        assertLookup(expr.as_json().alias('c2'), {'c2': 'foo'})

        j.data = [
            {'i1': ['foo', 'bar', 'baz']},
            ['nugget', 'mickey']]
        j.save()

        expr = self.M.data[0]['i1']
        assertLookup(expr.alias('i1'), {'i1': '["foo", "bar", "baz"]'})
        assertLookup(expr.as_json().alias('i2'), {'i2': ['foo', 'bar', 'baz']})

        expr = self.M.data[1][1]
        assertLookup(expr.alias('l1'), {'l1': 'mickey'})
        assertLookup(expr.as_json().alias('l2'), {'l2': 'mickey'})

    def test_json_cast(self):
        self.M.create(data={'foo': {'bar': 3}})
        self.M.create(data={'foo': {'bar': 5}})
        query = (self.M
                 .select(Cast(self.M.data['foo']['bar'], 'float') * 1.5)
                 .order_by(self.M.id)
                 .tuples())
        self.assertEqual(query[:], [(4.5,), (7.5,)])

    def test_json_path(self):
        data = {
            'foo': {
                'baz': {
                    'bar': ['i1', 'i2', 'i3'],
                    'baze': ['j1', 'j2'],
                }}}
        j = self.M.create(data=data)

        def assertPath(path, expected):
            query = (self.M
                     .select(path)
                     .where(j._pk_expr())
                     .dicts())
            self.assertEqual(query.get(), expected)

        expr = self.M.data.path('foo', 'baz', 'bar')
        assertPath(expr.alias('p1'), {'p1': '["i1", "i2", "i3"]'})
        assertPath(expr.as_json().alias('p2'), {'p2': ['i1', 'i2', 'i3']})

        expr = self.M.data.path('foo', 'baz', 'baze', 1)
        assertPath(expr.alias('p1'), {'p1': 'j2'})
        assertPath(expr.as_json().alias('p2'), {'p2': 'j2'})

    def test_json_field_sql(self):
        j = (self.M
             .select()
             .where(self.M.data == {'foo': 'bar'}))
        table = self.M._meta.table_name
        self.assertSQL(j, (
            'SELECT "t1"."id", "t1"."data" '
            'FROM "%s" AS "t1" WHERE ("t1"."data" = CAST(? AS %s))')
            % (table, self.M.data._json_datatype))

        j = (self.M
             .select()
             .where(self.M.data['foo'] == 'bar'))
        self.assertSQL(j, (
            'SELECT "t1"."id", "t1"."data" '
            'FROM "%s" AS "t1" WHERE ("t1"."data"->>? = ?)') % table)

    def assertItems(self, where, *items):
        query = (self.M
                 .select()
                 .where(where)
                 .order_by(self.M.id))
        self.assertEqual(
            [item.id for item in query],
            [item.id for item in items])

    def test_lookup(self):
        t1 = self.M.create(data={'k1': 'v1', 'k2': {'k3': 'v3'}})
        t2 = self.M.create(data={'k1': 'x1', 'k2': {'k3': 'x3'}})
        t3 = self.M.create(data={'k1': 'v1', 'j2': {'j3': 'v3'}})
        self.assertItems((self.M.data['k2']['k3'] == 'v3'), t1)
        self.assertItems((self.M.data['k1'] == 'v1'), t1, t3)

        # Valid key, no matching value.
        self.assertItems((self.M.data['k2'] == 'v1'))

        # Non-existent key.
        self.assertItems((self.M.data['not-here'] == 'v1'))

        # Non-existent nested key.
        self.assertItems((self.M.data['not-here']['xxx'] == 'v1'))

        self.assertItems((self.M.data['k2']['xxx'] == 'v1'))

    def test_json_bulk_update_top_level_list(self):
        m1 = self.M.create(data=['a', 'b', 'c'])
        m2 = self.M.create(data=['d', 'e', 'f'])

        m1.data = ['g', 'h', 'i']
        m2.data = ['j', 'k', 'l']
        self.M.bulk_update([m1, m2], fields=[self.M.data])
        m1_db = self.M.get(self.M.id == m1.id)
        m2_db = self.M.get(self.M.id == m2.id)
        self.assertEqual(m1_db.data, ['g', 'h', 'i'])
        self.assertEqual(m2_db.data, ['j', 'k', 'l'])


def pg93():
    with db:
        return db.connection().server_version >= 90300

def pg10():
    with db:
        return db.connection().server_version >= 100000

def pg12():
    with db:
        return db.connection().server_version >= 120000

JSON_SUPPORT = (JsonModel is not None) and pg93()


@skip_unless(JSON_SUPPORT, 'json support unavailable')
class TestJsonField(BaseJsonFieldTestCase, ModelTestCase):
    M = JsonModel
    database = db
    requires = [JsonModel, Normal, JsonModelNull]

    def test_json_null(self):
        tjn = JsonModelNull.create(data=None)
        tj = JsonModelNull.create(data={'k1': 'v1'})

        results = JsonModelNull.select().order_by(JsonModelNull.id)
        self.assertEqual(
            [tj_db.data for tj_db in results],
            [None, {'k1': 'v1'}])

        query = JsonModelNull.select().where(
            JsonModelNull.data.is_null(True))
        self.assertEqual(query.get(), tjn)


@skip_unless(JSON_SUPPORT, 'json support unavailable')
class TestBinaryJsonField(BaseJsonFieldTestCase, ModelTestCase):
    M = BJson
    database = db
    requires = [BJson, Normal]

    def _create_test_data(self):
        data = [
            {'k1': 'v1', 'k2': 'v2', 'k3': {'k4': ['i1', 'i2'], 'k5': {}}},
            ['a1', 'a2', {'a3': 'a4'}],
            {'a1': 'x1', 'a2': 'x2', 'k4': ['i1', 'i2']},
            list(range(10)),
            list(range(5, 15)),
            ['k4', 'k1']]

        self._bjson_objects = []
        for json_value in data:
            self._bjson_objects.append(BJson.create(data=json_value))

    def assertObjects(self, expr, *indexes):
        query = (BJson
                 .select()
                 .where(expr)
                 .order_by(BJson.id))
        self.assertEqual(
            [bjson.data for bjson in query],
            [self._bjson_objects[index].data for index in indexes])

    def test_contained_by(self):
        self._create_test_data()

        item1 = ['a1', 'a2', {'a3': 'a4'}, 'a5']
        self.assertObjects(BJson.data.contained_by(item1), 1)

        item2 = {'a1': 'x1', 'a2': 'x2', 'k4': ['i0', 'i1', 'i2'], 'x': 'y'}
        self.assertObjects(BJson.data.contained_by(item2), 2)

    def test_equality(self):
        data = {'k1': ['a1', 'a2'], 'k2': {'k3': 'v3'}}
        j = BJson.create(data=data)
        j_db = BJson.get(BJson.data == data)
        self.assertEqual(j.id, j_db.id)

    def test_subscript_contains(self):
        self._create_test_data()
        D = BJson.data

        # 'k3' is mapped to another dictioary {'k4': [...]}. Therefore,
        # 'k3' is said to contain 'k4', but *not* ['k4'] or ['k4', 'k5'].
        self.assertObjects(D['k3'].contains('k4'), 0)
        self.assertObjects(D['k3'].contains(['k4']))
        self.assertObjects(D['k3'].contains(['k4', 'k5']))

        # We can check for the keys this way, though.
        self.assertObjects(D['k3'].contains_all('k4', 'k5'), 0)
        self.assertObjects(D['k3'].contains_any('k4', 'kx'), 0)

        # However, in test object index=2, 'k4' can be said to contain
        # both 'i1' and ['i1'].
        self.assertObjects(D['k4'].contains('i1'), 2)
        self.assertObjects(D['k4'].contains(['i1']), 2)

        # Interestingly, we can also specify the list of contained values
        # out-of-order.
        self.assertObjects(D['k4'].contains(['i2', 'i1']), 2)

        # We can test whether an object contains another JSON object fragment.
        self.assertObjects(D['k3'].contains({'k4': ['i1']}), 0)
        self.assertObjects(D['k3'].contains({'k4': ['i1', 'i2']}), 0)

        # Check multiple levels of nesting / containment.
        self.assertObjects(D['k3']['k4'].contains('i2'), 0)
        self.assertObjects(D['k3']['k4'].contains_all('i1', 'i2'), 0)
        self.assertObjects(D['k3']['k4'].contains_all('i0', 'i2'))
        self.assertObjects(D['k4'].contains_all('i1', 'i2'), 2)

        # Check array indexes.
        self.assertObjects(D[2].contains('a3'), 1)
        self.assertObjects(D[0].contains('a1'), 1)
        self.assertObjects(D[0].contains('k1'))

    def test_contains(self):
        self._create_test_data()
        D = BJson.data

        # Test for keys. 'k4' is both an object key and an array element.
        self.assertObjects(D.contains('k4'), 2, 5)
        self.assertObjects(D.contains('a1'), 1, 2)
        self.assertObjects(D.contains('k3'), 0)

        # We can test for multiple top-level keys/indexes.
        self.assertObjects(D.contains_all('a1', 'a2'), 1, 2)

        # If we test for both with .contains(), though, it is treated as
        # an object match.
        self.assertObjects(D.contains(['a1', 'a2']), 1)

        # Check numbers.
        self.assertObjects(D.contains([2, 5, 6, 7, 8]), 3)
        self.assertObjects(D.contains([5, 6, 7, 8, 9]), 3, 4)

        # We can check for partial objects.
        self.assertObjects(D.contains({'a1': 'x1'}), 2)
        self.assertObjects(D.contains({'k3': {'k4': []}}), 0)
        self.assertObjects(D.contains([{'a3': 'a4'}]), 1)

        # Check for simple keys.
        self.assertObjects(D.contains('a1'), 1, 2)
        self.assertObjects(D.contains('k3'), 0)

        # Contains any.
        self.assertObjects(D.contains_any('a1', 'k1'), 0, 1, 2, 5)
        self.assertObjects(D.contains_any('k4', 'xx', 'yy', '2'), 2, 5)
        self.assertObjects(D.contains_any('i1', 'i2', 'a3'))

        # Contains all.
        self.assertObjects(D.contains_all('k1', 'k2', 'k3'), 0)
        self.assertObjects(D.contains_all('k1', 'k2', 'k3', 'k4'))

        # Has key.
        self.assertObjects(D.has_key('a1'), 1, 2)
        self.assertObjects(D.has_key('k1'), 0, 5)
        self.assertObjects(D.has_key('k4'), 2, 5)
        self.assertObjects(D.has_key('a3'))

        self.assertObjects(D['k3'].has_key('k4'), 0)
        self.assertObjects(D['k4'].has_key('i2'), 2)

    @skip_unless(pg10(), 'jsonb remove support requires pg >= 10')
    def test_remove_data(self):
        BJson.delete().execute()  # Clear out db.
        BJson.create(data={
            'k1': 'v1',
            'k2': 'v2',
            'k3': {'x1': 'z1', 'x2': 'z2'},
            'k4': [0, 1, 2]})

        def assertData(exp_list, expected_data):
            query = BJson.select(BJson.data.remove(*exp_list)).tuples()
            data = query[:][0][0]
            self.assertEqual(data, expected_data)

        D = BJson.data
        assertData(['k3'], {'k1': 'v1', 'k2': 'v2', 'k4': [0, 1, 2]})
        assertData(['k1', 'k3'], {'k2': 'v2', 'k4': [0, 1, 2]})
        assertData(['k1', 'kx', 'ky', 'k3'], {'k2': 'v2', 'k4': [0, 1, 2]})
        assertData(['k4', 'k3'], {'k1': 'v1', 'k2': 'v2'})

    def test_concat_data(self):
        BJson.delete().execute()
        BJson.create(data={'k1': {'x1': 'y1'}, 'k2': 'v2', 'k3': [0, 1]})

        def assertData(exp, expected_data):
            query = BJson.select(BJson.data.concat(exp)).tuples()
            data = query[:][0][0]
            self.assertEqual(data, expected_data)

        D = BJson.data
        assertData({'k2': 'v2-x', 'k1': {'x2': 'y2'}, 'k4': 'v4'}, {
            'k1': {'x2': 'y2'},  # NB: not merged/patched!!
            'k2': 'v2-x',
            'k3': [0, 1],
            'k4': 'v4'})
        assertData({'k1': 'v1-x', 'k3': [2, 3, 4], 'k4': {'x4': 'y4'}}, {
            'k1': 'v1-x',
            'k2': 'v2',
            'k3': [2, 3, 4],
            'k4': {'x4': 'y4'}})

        # We can update sub-keys.
        query = BJson.select(BJson.data['k1'].concat({'x2': 'y2', 'x3': 'y3'}))
        self.assertEqual(query.tuples()[0][0],
                         {'x1': 'y1', 'x2': 'y2', 'x3': 'y3'})

        # Concat can be used to extend JSON arrays.
        query = BJson.select(BJson.data['k3'].concat([2, 3]))
        self.assertEqual(query.tuples()[0][0], [0, 1, 2, 3])

    def test_update_data_inplace(self):
        BJson.delete().execute()
        b = BJson.create(data={'k1': {'x1': 'y1'}, 'k2': 'v2'})

        BJson.update(data=BJson.data.concat({
            'k1': {'x2': 'y2'},
            'k3': 'v3'})).execute()
        b2 = BJson.get(BJson.id == b.id)
        self.assertEqual(b2.data, {'k1': {'x2': 'y2'}, 'k2': 'v2', 'k3': 'v3'})

    def test_integer_index_weirdness(self):
        self._create_test_data()

        def fails():
            with self.database.atomic():
                expr = BJson.data.contains_any(2, 8, 12)
                results = list(BJson.select().where(
                    BJson.data.contains_any(2, 8, 12)))

        # Complains of a missing cast/conversion for the data-type?
        self.assertRaises(ProgrammingError, fails)

    def test_selecting(self):
        self._create_test_data()
        query = (BJson
                 .select(BJson.data['k3']['k4'].as_json().alias('k3k4'))
                 .order_by(BJson.id))
        k3k4_data = [obj.k3k4 for obj in query]
        self.assertEqual(k3k4_data, [
            ['i1', 'i2'],
            None,
            None,
            None,
            None,
            None])

        query = (BJson
                 .select(
                     BJson.data[0].as_json(),
                     BJson.data[2].as_json())
                 .order_by(BJson.id)
                 .tuples())
        self.assertEqual(list(query), [
            (None, None),
            ('a1', {'a3': 'a4'}),
            (None, None),
            (0, 2),
            (5, 7),
            ('k4', None)])

    def test_conflict_update(self):
        b1 = BJson.create(data={'k1': 'v1'})
        iq = (BJson
              .insert(id=b1.id, data={'k1': 'v1-x'})
              .on_conflict('update', conflict_target=[BJson.id],
                           update={BJson.data: {'k1': 'v1-z'}}))
        b1_id_db = iq.execute()
        self.assertEqual(b1.id, b1_id_db)

        b1_db = BJson.get(BJson.id == b1.id)
        self.assertEqual(BJson.data, {'k1': 'v1-z'})

        iq = (BJson
              .insert(id=b1.id, data={'k1': 'v1-y'})
              .on_conflict('update', conflict_target=[BJson.id],
                           update={'data': {'k1': 'v1-w'}}))
        b1_id_db = iq.execute()
        self.assertEqual(b1.id, b1_id_db)

        b1_db = BJson.get(BJson.id == b1.id)
        self.assertEqual(BJson.data, {'k1': 'v1-w'})

        self.assertEqual(BJson.select().count(), 1)


@skip_unless(JSON_SUPPORT, 'json support unavailable')
class TestBinaryJsonFieldBulkUpdate(ModelTestCase):
    database = db
    requires = [BJson]

    def test_binary_json_field_bulk_update(self):
        b1 = BJson.create(data={'k1': 'v1'})
        b2 = BJson.create(data={'k2': 'v2'})
        b1.data['k1'] = 'v1-x'
        b2.data['k2'] = 'v2-y'
        BJson.bulk_update([b1, b2], fields=[BJson.data])

        b1_db = BJson.get(BJson.id == b1.id)
        b2_db = BJson.get(BJson.id == b2.id)
        self.assertEqual(b1_db.data, {'k1': 'v1-x'})
        self.assertEqual(b2_db.data, {'k2': 'v2-y'})


class TestIntervalField(ModelTestCase):
    database = db
    requires = [Event]

    def test_interval_field(self):
        e1 = Event.create(name='hour', duration=datetime.timedelta(hours=1))
        e2 = Event.create(name='mix', duration=datetime.timedelta(
            days=1,
            hours=2,
            minutes=3,
            seconds=4))

        events = [(e.name, e.duration)
                  for e in Event.select().order_by(Event.duration)]
        self.assertEqual(events, [
            ('hour', datetime.timedelta(hours=1)),
            ('mix', datetime.timedelta(days=1, hours=2, minutes=3, seconds=4))
        ])


class TestIndexedField(BaseTestCase):
    def test_indexed_field_ddl(self):
        class FakeIndexedField(IndexedFieldMixin, CharField):
            default_index_type = 'GiST'

        class IndexedModel(TestModel):
            array_index = ArrayField(CharField)
            array_noindex= ArrayField(IntegerField, index=False)
            fake_index = FakeIndexedField()
            fake_index_with_type = FakeIndexedField(index_type='MAGIC')
            fake_noindex = FakeIndexedField(index=False)

            class Meta:
                database = db

        create_sql, _ = IndexedModel._schema._create_table(False).query()
        self.assertEqual(create_sql, (
            'CREATE TABLE "indexed_model" ('
            '"id" SERIAL NOT NULL PRIMARY KEY, '
            '"array_index" VARCHAR(255)[] NOT NULL, '
            '"array_noindex" INTEGER[] NOT NULL, '
            '"fake_index" VARCHAR(255) NOT NULL, '
            '"fake_index_with_type" VARCHAR(255) NOT NULL, '
            '"fake_noindex" VARCHAR(255) NOT NULL)'))

        indexes = [idx.query()[0]
                   for idx in IndexedModel._schema._create_indexes(False)]
        self.assertEqual(indexes, [
            ('CREATE INDEX "indexed_model_array_index" ON "indexed_model" '
             'USING GIN ("array_index")'),
            ('CREATE INDEX "indexed_model_fake_index" ON "indexed_model" '
             'USING GiST ("fake_index")'),
            ('CREATE INDEX "indexed_model_fake_index_with_type" '
             'ON "indexed_model" '
             'USING MAGIC ("fake_index_with_type")')])


class IDAlways(TestModel):
    id = IdentityField(generate_always=True)
    data = CharField()


class IDByDefault(TestModel):
    id = IdentityField()
    data = CharField()


@skip_unless(pg10(), 'identity field requires pg >= 10')
class TestIdentityField(ModelTestCase):
    database = db
    requires = [IDAlways, IDByDefault]

    def test_identity_field_always(self):
        iq = IDAlways.insert_many([(d,) for d in ('d1', 'd2', 'd3')])
        curs = iq.execute()
        self.assertEqual(list(curs), [(1,), (2,), (3,)])

        # Cannot specify id when generate always is true.
        with self.assertRaises(ProgrammingError):
            with self.database.atomic():
                IDAlways.create(id=10, data='d10')

        query = IDAlways.select().order_by(IDAlways.id)
        self.assertEqual(list(query.tuples()), [
            (1, 'd1'), (2, 'd2'), (3, 'd3')])

    def test_identity_field_by_default(self):
        iq = IDByDefault.insert_many([(d,) for d in ('d1', 'd2', 'd3')])
        curs = iq.execute()
        self.assertEqual(list(curs), [(1,), (2,), (3,)])

        # Cannot specify id when generate always is true.
        IDByDefault.create(id=10, data='d10')

        query = IDByDefault.select().order_by(IDByDefault.id)
        self.assertEqual(list(query.tuples()), [
            (1, 'd1'), (2, 'd2'), (3, 'd3'), (10, 'd10')])

    def test_schema(self):
        sql, params = IDAlways._schema._create_table(False).query()
        self.assertEqual(sql, (
            'CREATE TABLE "id_always" ("id" INT GENERATED ALWAYS AS IDENTITY '
            'NOT NULL PRIMARY KEY, "data" VARCHAR(255) NOT NULL)'))

        sql, params = IDByDefault._schema._create_table(False).query()
        self.assertEqual(sql, (
            'CREATE TABLE "id_by_default" ("id" INT GENERATED BY DEFAULT AS '
            'IDENTITY NOT NULL PRIMARY KEY, "data" VARCHAR(255) NOT NULL)'))


class TestServerSide(ModelTestCase):
    database = db
    requires = [Register]

    def setUp(self):
        super(TestServerSide, self).setUp()
        with db.atomic():
            for i in range(100):
                Register.create(value=i)

    def test_server_side_cursor(self):
        query = Register.select().order_by(Register.value)
        with self.assertQueryCount(1):
            data = [row.value for row in ServerSide(query)]
            self.assertEqual(data, list(range(100)))

        ss_query = ServerSide(query.limit(10), array_size=3)
        self.assertEqual([row.value for row in ss_query], list(range(10)))

        ss_query = ServerSide(query.where(SQL('1 = 0')))
        self.assertEqual(list(ss_query), [])


class KX(TestModel):
    key = CharField(unique=True)
    value = IntegerField()

class TestAutocommitIntegration(ModelTestCase):
    database = db
    requires = [KX]

    def setUp(self):
        super(TestAutocommitIntegration, self).setUp()
        with self.database.atomic():
            kx1 = KX.create(key='k1', value=1)

    def force_integrity_error(self):
        # Force an integrity error, then verify that the current
        # transaction has been aborted.
        self.assertRaises(IntegrityError, KX.create, key='k1', value=10)
        self.assertRaises(InternalError, KX.get, key='k1')

    def test_autocommit_default(self):
        kx2 = KX.create(key='k2', value=2)  # Will be committed.
        self.assertTrue(kx2.id > 0)
        self.force_integrity_error()
        self.database.rollback()

        self.assertEqual(KX.select().count(), 2)
        self.assertEqual([(kx.key, kx.value)
                          for kx in KX.select().order_by(KX.key)],
                         [('k1', 1), ('k2', 2)])

    def test_autocommit_disabled(self):
        with self.database.manual_commit():
            kx2 = KX.create(key='k2', value=2)  # Not committed.
            self.assertTrue(kx2.id > 0)  # Yes, we have a primary key.
            self.force_integrity_error()
            self.database.rollback()

        self.assertEqual(KX.select().count(), 1)
        kx1_db = KX.get(KX.key == 'k1')
        self.assertEqual(kx1_db.value, 1)

    def test_atomic_block(self):
        with self.database.atomic() as txn:
            kx2 = KX.create(key='k2', value=2)
            self.assertTrue(kx2.id > 0)
            self.force_integrity_error()
            txn.rollback(False)

        self.assertEqual(KX.select().count(), 1)
        kx1_db = KX.get(KX.key == 'k1')
        self.assertEqual(kx1_db.value, 1)

    def test_atomic_block_exception(self):
        with self.assertRaises(IntegrityError):
            with self.database.atomic():
                KX.create(key='k2', value=2)
                KX.create(key='k1', value=10)

        self.assertEqual(KX.select().count(), 1)


class TestPostgresIsolationLevel(DatabaseTestCase):
    database = db_loader('postgres', isolation_level=3)  # SERIALIZABLE.

    def test_isolation_level(self):
        conn = self.database.connection()
        self.assertEqual(conn.isolation_level, 3)

        conn.set_isolation_level(2)
        self.assertEqual(conn.isolation_level, 2)

        self.database.close()
        conn = self.database.connection()
        self.assertEqual(conn.isolation_level, 3)


@skip_unless(pg12(), 'cte materialization requires pg >= 12')
class TestPostgresCTEMaterialization(ModelTestCase):
    database = db
    requires = [Register]

    def test_postgres_cte_materialization(self):
        Register.insert_many([(i,) for i in (1, 2, 3)]).execute()

        for materialized in (None, False, True):
            cte = Register.select().cte('t', materialized=materialized)
            query = (cte
                     .select_from(cte.c.value)
                     .where(cte.c.value != 2)
                     .order_by(cte.c.value))
            self.assertEqual([r.value for r in query], [1, 3])
