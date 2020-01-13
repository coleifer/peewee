#coding:utf-8
import datetime
import functools
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
from .base_models import Tweet
from .base_models import User
from .postgres_helpers import BaseBinaryJsonFieldTestCase
from .postgres_helpers import BaseJsonFieldTestCase


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

    def test_index_expression(self):
        data = (
            (['a', 'b', 'c'], []),
            (['b', 'c', 'd', 'e'], []))
        am_ids = []
        for tags, ints in data:
            am = ArrayModel.create(tags=tags, ints=ints)
            am_ids.append(am.id)

        last_tag = fn.array_upper(ArrayModel.tags, 1)
        query = ArrayModel.select(ArrayModel.tags[last_tag]).tuples()
        self.assertEqual(sorted([t for t, in query]), ['c', 'e'])

        q = ArrayModel.select().where(ArrayModel.tags[last_tag] < 'd')
        self.assertEqual([a.id for a in q], [am_ids[0]])

        q = ArrayModel.select().where(ArrayModel.tags[last_tag] > 'd')
        self.assertEqual([a.id for a in q], [am_ids[1]])

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
    N = Normal
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
class TestBinaryJsonField(BaseBinaryJsonFieldTestCase, ModelTestCase):
    M = BJson
    N = Normal
    database = db
    requires = [BJson, Normal]

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

    def test_integer_index_weirdness(self):
        self._create_test_data()

        def fails():
            with self.database.atomic():
                expr = BJson.data.contains_any(2, 8, 12)
                results = list(BJson.select().where(
                    BJson.data.contains_any(2, 8, 12)))

        # Complains of a missing cast/conversion for the data-type?
        self.assertRaises(ProgrammingError, fails)


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


@skip_unless(pg93(), 'lateral join requires pg >= 9.3')
class TestPostgresLateralJoin(ModelTestCase):
    database = db
    test_data = (
        ('a', (('a1', 1),
               ('a2', 2),
               ('a10', 10))),
        ('b', (('b3', 3),
               ('b4', 4),
               ('b7', 7))),
        ('c', ()))
    ts = functools.partial(datetime.datetime, 2019, 1)

    def create_data(self):
        with self.database.atomic():
            for username, tweets in self.test_data:
                user = User.create(username=username)
                for c, d in tweets:
                    Tweet.create(user=user, content=c, timestamp=self.ts(d))

    @requires_models(User, Tweet)
    def test_lateral_top_n(self):
        self.create_data()

        subq = (Tweet
                .select(Tweet.content, Tweet.timestamp)
                .where(Tweet.user == User.id)
                .order_by(Tweet.timestamp.desc())
                .limit(2))
        query = (User
                 .select(User, subq.c.content)
                 .join(subq, JOIN.LEFT_LATERAL)
                 .order_by(subq.c.timestamp.desc(nulls='last')))
        results = [(u.username, u.content) for u in query]
        self.assertEqual(results, [
            ('a', 'a10'),
            ('b', 'b7'),
            ('b', 'b4'),
            ('a', 'a2'),
            ('c', None)])

        query = (Tweet
                 .select(User.username, subq.c.content)
                 .from_(User)
                 .join(subq, JOIN.LEFT_LATERAL)
                 .order_by(User.username, subq.c.timestamp))

        results = [(t.username, t.content) for t in query]
        self.assertEqual(results, [
            ('a', 'a2'),
            ('a', 'a10'),
            ('b', 'b4'),
            ('b', 'b7'),
            ('c', None)])
