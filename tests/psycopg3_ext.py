#coding:utf-8
import datetime
import os
import uuid
from decimal import Decimal as Dc

import psycopg  # Failure to do so will skip these tests.

from peewee import *
from playhouse.psycopg3_ext import *

from .base import DatabaseTestCase
from .base import ModelTestCase
from .base import TestModel
from .base import db_loader
from .base import requires_models
from .base import skip_if
from .postgres_helpers import BaseBinaryJsonFieldTestCase
from .postgres_helpers import BaseJsonFieldTestCase


db = db_loader('postgres', db_class=Psycopg3Database)


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

class BJson(TestModel):
    data = BinaryJSONField()

class JData(TestModel):
    d1 = BinaryJSONField()
    d2 = BinaryJSONField(index=False)

class Normal(TestModel):
    data = TextField()

class Event(TestModel):
    name = CharField()
    duration = IntervalField()

class TZModel(TestModel):
    dt = DateTimeTZField()


class TestPsycopg3TZField(ModelTestCase):
    database = db
    requires = [TZModel]

    @skip_if(os.environ.get('CI'), 'running in ci mode, skipping')
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


class TestPsycopg3ArrayField(ModelTestCase):
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

    def test_hashable_objectslice(self):
        ArrayModel.create(tags=[], ints=[[0, 1], [2, 3]])
        ArrayModel.create(tags=[], ints=[[4, 5], [6, 7]])
        n = (ArrayModel
             .update({ArrayModel.ints[0][0]: ArrayModel.ints[0][0] + 1})
             .execute())
        self.assertEqual(n, 2)

        am1, am2 = ArrayModel.select().order_by(ArrayModel.id)
        self.assertEqual(am1.ints, [[1, 1], [2, 3]])
        self.assertEqual(am2.ints, [[5, 5], [6, 7]])

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
        assertAM(T.contained_by('alpha', 'beta', 'delta'), am2, am3)
        assertAM(T.contained_by('alpha', 'beta', 'gamma', 'delta'),
                 am, am2, am3)

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


class TestPsycopg3ArrayFieldConvertValues(ModelTestCase):
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


class TestPsycopg3ArrayUUIDField(ModelTestCase):
    database = db
    requires = [UUIDList]

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


class TestPsycopg3TSVectorField(ModelTestCase):
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
        super(TestPsycopg3TSVectorField, self).setUp()
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


class TestPsycopg3BinaryJsonField(BaseBinaryJsonFieldTestCase, ModelTestCase):
    M = BJson
    N = Normal
    database = db
    requires = [BJson, Normal]

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

    def test_json_contains_in_list(self):
        m1 = self.M.create(data=[{'k1': 'v1', 'k2': 'v2'}, {'a1': 'b1'}])
        m2 = self.M.create(data=[{'k3': 'v3'}, {'k4': 'v4'}])
        m3 = self.M.create(data=[{'k5': 'v5', 'k6': 'v6'}, {'k1': 'v1'}])

        query = (self.M
                 .select()
                 .where(self.M.data.contains([{'k1': 'v1'}]))
                 .order_by(self.M.id))
        self.assertEqual([m.id for m in query], [m1.id, m3.id])

    def test_integer_index_weirdness(self):
        self._create_test_data()

        def fails():
            with self.database.atomic():
                expr = BJson.data.contains_any(2, 8, 12)
                results = list(BJson.select().where(
                    BJson.data.contains_any(2, 8, 12)))

        # Complains of a missing cast/conversion for the data-type?
        self.assertRaises(ProgrammingError, fails)


class TestPsycopg3BinaryJsonFieldBulkUpdate(ModelTestCase):
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


class TestPsycopg3JsonFieldRegressions(ModelTestCase):
    database = db
    requires = [JData]

    def test_json_field_concat(self):
        jd = JData.create(
            d1={'k1': {'x1': 'y1'}, 'k2': 'v2', 'k3': 'v3'},
            d2={'k1': {'x2': 'y2'}, 'k2': 'v2-x', 'k4': 'v4'})

        query = JData.select(JData.d1.concat(JData.d2).alias('data'))
        obj = query.get()
        self.assertEqual(obj.data, {
            'k1': {'x2': 'y2'}, 'k2': 'v2-x', 'k3': 'v3', 'k4': 'v4'})


class TestPsycopg3IntervalField(ModelTestCase):
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


class KX(TestModel):
    key = CharField(unique=True)
    value = IntegerField()

class TestPsycopg3AutocommitIntegration(ModelTestCase):
    database = db
    requires = [KX]

    def setUp(self):
        super(TestPsycopg3AutocommitIntegration, self).setUp()
        with self.database.atomic():
            kx1 = KX.create(key='k1', value=1)

    def force_integrity_error(self):
        # Force an integrity error, then verify that the current
        # transaction has been aborted.
        self.assertRaises(IntegrityError, KX.create, key='k1', value=10)

    def test_autocommit_default(self):
        kx2 = KX.create(key='k2', value=2)  # Will be committed.
        self.assertTrue(kx2.id > 0)
        self.force_integrity_error()

        self.assertEqual(KX.select().count(), 2)
        self.assertEqual([(kx.key, kx.value)
                          for kx in KX.select().order_by(KX.key)],
                         [('k1', 1), ('k2', 2)])

    def test_autocommit_disabled(self):
        with self.database.manual_commit():
            self.database.begin()
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


class TestPsycopg3IsolationLevel(DatabaseTestCase):
    database = db_loader('postgres', db_class=Psycopg3Database,
                         isolation_level=3)  # SERIALIZABLE.

    def test_isolation_level(self):
        conn = self.database.connection()
        self.assertEqual(conn.isolation_level, 3)

        conn.isolation_level = 2
        self.assertEqual(conn.isolation_level, 2)

        self.database.close()
        conn = self.database.connection()
        self.assertEqual(conn.isolation_level, 3)
