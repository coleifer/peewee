"""
Field type tests: validation, conversion, storage, and retrieval for all
field types, plus foreign key behavior, composite keys, and field-level
constraints.

Test case ordering (current):
  1. Numeric and basic value types
  2. Date/time fields
  3. Foreign key basics and deferred FK resolution
  4. Composite PK, field functions, IP, bit fields
  5. Blob, BigAuto, UUID, timestamp, custom fields
  6. String fields and misc field types
  7. Virtual field behavior
  8. Foreign key advanced: non-PK targets, multiple FKs, composite PK with FK
  9. Search operators (regexp, contains)
  10. Value conversion and type coercion
  11. Regressions and edge cases
"""
import calendar
import datetime
import json
import sqlite3
import time
import uuid
from decimal import Decimal as D
from decimal import ROUND_UP

from peewee import NodeList
from peewee import VirtualField
from peewee import *

from playhouse.hybrid import *

from .base import BaseTestCase
from .base import IS_CRDB
from .base import IS_MYSQL
from .base import IS_POSTGRESQL
from .base import IS_SQLITE
from .base import ModelTestCase
from .base import TestModel
from .base import db
from .base import get_in_memory_db
from .base import requires_models
from .base import requires_mysql
from .base import requires_pglike
from .base import requires_sqlite
from .base import skip_if
from .base_models import Note
from .base_models import Person
from .base_models import Relationship
from .base_models import Tweet
from .base_models import User


# ===========================================================================
# Numeric and basic value types
# ===========================================================================

class IntModel(TestModel):
    value = IntegerField()
    value_null = IntegerField(null=True)


class TestCoerce(ModelTestCase):
    requires = [IntModel]

    def test_coerce(self):
        i = IntModel.create(value='1337', value_null=3.14159)
        i_db = IntModel.get(IntModel.id == i.id)
        self.assertEqual(i_db.value, 1337)
        self.assertEqual(i_db.value_null, 3)


class DefaultValues(TestModel):
    data = IntegerField(default=17)
    data_callable = IntegerField(default=lambda: 1337)


class TestDefaultValues(ModelTestCase):
    requires = [DefaultValues]

    def test_default_values(self):
        d = DefaultValues()
        self.assertEqual(d.data, 17)
        self.assertEqual(d.data_callable, 1337)
        d.save()

        d_db = DefaultValues.get(DefaultValues.id == d.id)
        self.assertEqual(d_db.data, 17)
        self.assertEqual(d_db.data_callable, 1337)

    def test_defaults_create(self):
        d = DefaultValues.create()
        self.assertEqual(d.data, 17)
        self.assertEqual(d.data_callable, 1337)

        d_db = DefaultValues.get(DefaultValues.id == d.id)
        self.assertEqual(d_db.data, 17)
        self.assertEqual(d_db.data_callable, 1337)


class TestNullConstraint(ModelTestCase):
    requires = [IntModel]

    def test_null(self):
        i = IntModel.create(value=1)
        i_db = IntModel.get(IntModel.value == 1)
        self.assertIsNone(i_db.value_null)

    def test_empty_value(self):
        with self.database.atomic():
            with self.assertRaisesCtx(IntegrityError):
                IntModel.create(value=None)


class TestIntegerField(ModelTestCase):
    requires = [IntModel]

    def test_integer_field(self):
        i1 = IntModel.create(value=1)
        i2 = IntModel.create(value=2, value_null=20)

        vals = [(i.value, i.value_null)
                for i in IntModel.select().order_by(IntModel.value)]
        self.assertEqual(vals, [
            (1, None),
            (2, 20)])


class FloatModel(TestModel):
    value = FloatField()
    value_null = FloatField(null=True)


class TestFloatField(ModelTestCase):
    requires = [FloatModel]

    def test_float_field(self):
        f1 = FloatModel.create(value=1.23)
        f2 = FloatModel.create(value=3.14, value_null=0.12)

        query = FloatModel.select().order_by(FloatModel.id)
        self.assertEqual([(f.value, f.value_null) for f in query],
                         [(1.23, None), (3.14, 0.12)])


class DecimalModel(TestModel):
    value = DecimalField(decimal_places=2, auto_round=True)
    value_up = DecimalField(decimal_places=2, auto_round=True,
                            rounding=ROUND_UP, null=True)


class TestDecimalField(ModelTestCase):
    requires = [DecimalModel]

    def test_decimal_field(self):
        d1 = DecimalModel.create(value=D('3'))
        d2 = DecimalModel.create(value=D('100.33'))

        self.assertEqual(sorted(d.value for d in DecimalModel.select()),
                         [D('3'), D('100.33')])

    def test_decimal_rounding(self):
        d = DecimalModel.create(value=D('1.2345'), value_up=D('1.2345'))
        d_db = DecimalModel.get(DecimalModel.id == d.id)
        self.assertEqual(d_db.value, D('1.23'))
        self.assertEqual(d_db.value_up, D('1.24'))


class BoolModel(TestModel):
    key = TextField()
    value = BooleanField(null=True)


class TestBooleanField(ModelTestCase):
    requires = [BoolModel]

    def test_boolean_field(self):
        BoolModel.create(key='t', value=True)
        BoolModel.create(key='f', value=False)
        BoolModel.create(key='n', value=None)

        vals = sorted((b.key, b.value) for b in BoolModel.select())
        self.assertEqual(vals, [
            ('f', False),
            ('n', None),
            ('t', True)])

    def test_boolean_compare(self):
        b1 = BoolModel.create(key='b1', value=True)
        b2 = BoolModel.create(key='b2', value=False)

        expr2key = (
            ((BoolModel.value == True), 'b1'),
            ((BoolModel.value == False), 'b2'),
            ((BoolModel.value != True), 'b2'),
            ((BoolModel.value != False), 'b1'))
        for expr, key in expr2key:
            q = BoolModel.select().where(expr)
            self.assertEqual([b.key for b in q], [key])




# ===========================================================================
# String fields
# ===========================================================================

class SM(TestModel):
    text_field = TextField()
    char_field = CharField()


class TestStringFields(ModelTestCase):
    requires = [SM]

    def test_string_fields(self):
        bdata = b'b1'
        udata = b'u1'.decode('utf8')

        sb = SM.create(text_field=bdata, char_field=bdata)
        su = SM.create(text_field=udata, char_field=udata)

        sb_db = SM.get(SM.id == sb.id)
        self.assertEqual(sb_db.text_field, 'b1')
        self.assertEqual(sb_db.char_field, 'b1')

        su_db = SM.get(SM.id == su.id)
        self.assertEqual(su_db.text_field, 'u1')
        self.assertEqual(su_db.char_field, 'u1')

        bvals = (b'b1', u'b1')
        uvals = (b'u1', u'u1')

        for field in (SM.text_field, SM.char_field):
            for bval in bvals:
                sb_db = SM.get(field == bval)
                self.assertEqual(sb.id, sb_db.id)

            for uval in uvals:
                sb_db = SM.get(field == uval)
                self.assertEqual(su.id, su_db.id)


class FC(TestModel):
    code = FixedCharField(max_length=5)
    name = CharField()


class TestFixedCharFieldIntegration(ModelTestCase):
    database = get_in_memory_db()
    requires = [FC]

    def test_fixed_char_truncates(self):
        FC.create(code='ABCDEF', name='short')

        fc = FC.get(FC.code == 'ABCDE')
        self.assertEqual(fc.code, 'ABCDE')


class LK(TestModel):
    key = TextField()

class TestLikeEscape(ModelTestCase):
    requires = [LK]

    def assertNames(self, expr, expected):
        query = LK.select().where(expr).order_by(LK.id)
        self.assertEqual([lk.key for lk in query], expected)

    def test_like_escape(self):
        names = ('foo', 'foo%', 'foo%bar', 'foo_bar', 'fooxba', 'fooba')
        LK.insert_many([(n,) for n in names]).execute()

        cases = (
            (LK.key.contains('bar'), ['foo%bar', 'foo_bar']),
            (LK.key.contains('%'), ['foo%', 'foo%bar']),
            (LK.key.contains('_'), ['foo_bar']),
            (LK.key.contains('o%b'), ['foo%bar']),
            (LK.key.startswith('foo%'), ['foo%', 'foo%bar']),
            (LK.key.startswith('foo_'), ['foo_bar']),
            (LK.key.startswith('bar'), []),
            (LK.key.endswith('ba'), ['fooxba', 'fooba']),
            (LK.key.endswith('_bar'), ['foo_bar']),
            (LK.key.endswith('fo'), []),
        )
        for expr, expected in cases:
            self.assertNames(expr, expected)

    def test_like_escape_backslash(self):
        names = ('foo_bar\\baz', 'bar\\', 'fbar\\baz', 'foo_bar')
        LK.insert_many([(n,) for n in names]).execute()

        cases = (
            (LK.key.contains('\\'), ['foo_bar\\baz', 'bar\\', 'fbar\\baz']),
            (LK.key.contains('_bar\\'), ['foo_bar\\baz']),
            (LK.key.contains('bar\\'), ['foo_bar\\baz', 'bar\\', 'fbar\\baz']),
        )
        for expr, expected in cases:
            self.assertNames(expr, expected)

# ===========================================================================
# Date and time fields
# ===========================================================================

class DateModel(TestModel):
    date = DateField(null=True)
    time = TimeField(null=True)
    date_time = DateTimeField(null=True)


class CustomDateTimeModel(TestModel):
    date_time = DateTimeField(formats=[
        '%m/%d/%Y %I:%M %p',
        '%Y-%m-%d %H:%M:%S'])


class TestDateFields(ModelTestCase):
    requires = [DateModel]

    @requires_models(CustomDateTimeModel)
    def test_date_time_custom_format(self):
        cdtm = CustomDateTimeModel.create(date_time='01/02/2003 01:37 PM')
        cdtm_db = CustomDateTimeModel[cdtm.id]
        self.assertEqual(cdtm_db.date_time,
                         datetime.datetime(2003, 1, 2, 13, 37, 0))

    def test_date_fields(self):
        dt1 = datetime.datetime(2011, 1, 2, 11, 12, 13, 54321)
        dt2 = datetime.datetime(2011, 1, 2, 11, 12, 13)
        d1 = datetime.date(2011, 1, 3)
        t1 = datetime.time(11, 12, 13, 54321)
        t2 = datetime.time(11, 12, 13)

        if isinstance(self.database, MySQLDatabase):
            dt1 = dt1.replace(microsecond=0)
            t1 = t1.replace(microsecond=0)

        dm1 = DateModel.create(date_time=dt1, date=d1, time=t1)
        dm2 = DateModel.create(date_time=dt2, time=t2)

        dm1_db = DateModel.get(DateModel.id == dm1.id)
        self.assertEqual(dm1_db.date, d1)
        self.assertEqual(dm1_db.date_time, dt1)
        self.assertEqual(dm1_db.time, t1)

        dm2_db = DateModel.get(DateModel.id == dm2.id)
        self.assertEqual(dm2_db.date, None)
        self.assertEqual(dm2_db.date_time, dt2)
        self.assertEqual(dm2_db.time, t2)

    def test_extract_parts(self):
        dm = DateModel.create(
            date_time=datetime.datetime(2011, 1, 2, 11, 12, 13, 54321),
            date=datetime.date(2012, 2, 3),
            time=datetime.time(3, 13, 37))
        query = (DateModel
                 .select(DateModel.date_time.year, DateModel.date_time.month,
                         DateModel.date_time.day, DateModel.date_time.hour,
                         DateModel.date_time.minute,
                         DateModel.date_time.second, DateModel.date.year,
                         DateModel.date.month, DateModel.date.day,
                         DateModel.time.hour, DateModel.time.minute,
                         DateModel.time.second)
                 .tuples())

        row, = query
        if IS_SQLITE or IS_MYSQL:
            self.assertEqual(row,
                             (2011, 1, 2, 11, 12, 13, 2012, 2, 3, 3, 13, 37))
        else:
            self.assertTrue(row in [
                (2011., 1., 2., 11., 12., 13.054321, 2012., 2., 3., 3., 13.,
                 37.),
                (D('2011'), D('1'), D('2'), D('11'), D('12'), D('13.054321'),
                 D('2012'), D('2'), D('3'), D('3'), D('13'), D('37'))])

    def test_truncate_date(self):
        dm = DateModel.create(
            date_time=datetime.datetime(2001, 2, 3, 4, 5, 6, 7),
            date=datetime.date(2002, 3, 4))

        accum = []
        for p in ('year', 'month', 'day', 'hour', 'minute', 'second'):
            accum.append(DateModel.date_time.truncate(p))
        for p in ('year', 'month', 'day'):
            accum.append(DateModel.date.truncate(p))

        query = DateModel.select(*accum).tuples()
        data = list(query[0])

        # Postgres includes timezone info, so strip that for comparison.
        if IS_POSTGRESQL or IS_CRDB:
            data = [dt.replace(tzinfo=None) for dt in data]

        self.assertEqual(data, [
            datetime.datetime(2001, 1, 1, 0, 0, 0),
            datetime.datetime(2001, 2, 1, 0, 0, 0),
            datetime.datetime(2001, 2, 3, 0, 0, 0),
            datetime.datetime(2001, 2, 3, 4, 0, 0),
            datetime.datetime(2001, 2, 3, 4, 5, 0),
            datetime.datetime(2001, 2, 3, 4, 5, 6),
            datetime.datetime(2002, 1, 1, 0, 0, 0),
            datetime.datetime(2002, 3, 1, 0, 0, 0),
            datetime.datetime(2002, 3, 4, 0, 0, 0)])

    def test_to_timestamp(self):
        dt = datetime.datetime(2019, 1, 2, 3, 4, 5)
        ts = calendar.timegm(dt.utctimetuple())

        dt2 = datetime.datetime(2019, 1, 3)
        ts2 = calendar.timegm(dt2.utctimetuple())

        DateModel.create(date_time=dt, date=dt2.date())

        query = DateModel.select(
            DateModel.id,
            DateModel.date_time.to_timestamp().alias('dt_ts'),
            DateModel.date.to_timestamp().alias('dt2_ts'))
        obj = query.get()

        self.assertEqual(obj.dt_ts, ts)
        self.assertEqual(obj.dt2_ts, ts2)

        ts3 = ts + 86400
        query = (DateModel.select()
                 .where((DateModel.date_time.to_timestamp() + 86400) < ts3))
        self.assertRaises(DateModel.DoesNotExist, query.get)

        query = (DateModel.select()
                 .where((DateModel.date.to_timestamp() + 86400) > ts3))
        self.assertEqual(query.get().id, obj.id)

    def test_distinct_date_part(self):
        years = (1980, 1990, 2000, 2010)
        for i, year in enumerate(years):
            for j in range(i + 1):
                DateModel.create(date=datetime.date(year, i + 1, 1))

        query = (DateModel
                 .select(DateModel.date.year.distinct())
                 .order_by(DateModel.date.year))
        self.assertEqual([year for year, in query.tuples()],
                         [1980, 1990, 2000, 2010])



# U2/T2: local User/Tweet variants for testing on_delete='CASCADE'.
# Not to be confused with base_models.User/Tweet which lack on_delete.
class TSModel(TestModel):
    ts_s = TimestampField()
    ts_us = TimestampField(resolution=10 ** 6)
    ts_ms = TimestampField(resolution=3)  # Milliseconds.
    ts_u = TimestampField(null=True, utc=True)


class TSR(TestModel):
    ts_0 = TimestampField(resolution=0)
    ts_1 = TimestampField(resolution=1)
    ts_10 = TimestampField(resolution=10)
    ts_2 = TimestampField(resolution=2)


class TestTimestampField(ModelTestCase):
    requires = [TSModel]

    @requires_models(TSR)
    def test_timestamp_field_resolutions(self):
        dt = datetime.datetime(2018, 3, 1, 3, 3, 7).replace(microsecond=123456)
        ts = TSR.create(ts_0=dt, ts_1=dt, ts_10=dt, ts_2=dt)
        ts_db = TSR[ts.id]

        # Zero and one are both treated as "seconds" resolution.
        self.assertEqual(ts_db.ts_0, dt.replace(microsecond=0))
        self.assertEqual(ts_db.ts_1, dt.replace(microsecond=0))
        self.assertEqual(ts_db.ts_10, dt.replace(microsecond=100000))
        self.assertEqual(ts_db.ts_2, dt.replace(microsecond=120000))

    def test_timestamp_field(self):
        dt = datetime.datetime(2018, 3, 1, 3, 3, 7)
        dt = dt.replace(microsecond=31337)  # us=031_337, ms=031.
        ts = TSModel.create(ts_s=dt, ts_us=dt, ts_ms=dt, ts_u=dt)
        ts_db = TSModel.get(TSModel.id == ts.id)
        self.assertEqual(ts_db.ts_s, dt.replace(microsecond=0))
        self.assertEqual(ts_db.ts_ms, dt.replace(microsecond=31000))
        self.assertEqual(ts_db.ts_us, dt)
        self.assertEqual(ts_db.ts_u, dt.replace(microsecond=0))

        self.assertEqual(TSModel.get(TSModel.ts_s == dt).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_ms == dt).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_us == dt).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_u == dt).id, ts.id)

    def test_timestamp_field_math(self):
        dt = datetime.datetime(2019, 1, 2, 3, 4, 5, 31337)
        ts = TSModel.create(ts_s=dt, ts_us=dt, ts_ms=dt)

        # Although these fields use different scales for storing the
        # timestamps, adding "1" has the effect of adding a single second -
        # the value will be multiplied by the correct scale via the converter.
        TSModel.update(
            ts_s=TSModel.ts_s + 1,
            ts_us=TSModel.ts_us + 1,
            ts_ms=TSModel.ts_ms + 1).execute()

        ts_db = TSModel.get(TSModel.id == ts.id)
        dt2 = dt + datetime.timedelta(seconds=1)
        self.assertEqual(ts_db.ts_s, dt2.replace(microsecond=0))
        self.assertEqual(ts_db.ts_us, dt2)
        self.assertEqual(ts_db.ts_ms, dt2.replace(microsecond=31000))

    def test_timestamp_field_value_as_ts(self):
        dt = datetime.datetime(2018, 3, 1, 3, 3, 7, 31337)
        unix_ts = time.mktime(dt.timetuple()) + 0.031337
        ts = TSModel.create(ts_s=unix_ts, ts_us=unix_ts, ts_ms=unix_ts,
                            ts_u=unix_ts)

        # Fetch from the DB and validate the values were stored correctly.
        ts_db = TSModel[ts.id]
        self.assertEqual(ts_db.ts_s, dt.replace(microsecond=0))
        self.assertEqual(ts_db.ts_ms, dt.replace(microsecond=31000))
        self.assertEqual(ts_db.ts_us, dt)

        utc_dt = TimestampField().local_to_utc(dt)
        self.assertEqual(ts_db.ts_u, utc_dt)

        # Verify we can query using a timestamp.
        self.assertEqual(TSModel.get(TSModel.ts_s == unix_ts).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_ms == unix_ts).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_us == unix_ts).id, ts.id)
        self.assertEqual(TSModel.get(TSModel.ts_u == unix_ts).id, ts.id)

    def test_timestamp_utc_vs_localtime(self):
        local_field = TimestampField()
        utc_field = TimestampField(utc=True)

        dt = datetime.datetime(2019, 1, 1, 12)
        unix_ts = int(local_field.get_timestamp(dt))
        utc_ts = int(utc_field.get_timestamp(dt))

        # Local timestamp is unmodified. Verify that when utc=True, the
        # timestamp is converted from local time to UTC.
        self.assertEqual(local_field.db_value(dt), unix_ts)
        self.assertEqual(utc_field.db_value(dt), utc_ts)

        self.assertEqual(local_field.python_value(unix_ts), dt)
        self.assertEqual(utc_field.python_value(utc_ts), dt)

        # Convert back-and-forth several times.
        dbv, pyv = local_field.db_value, local_field.python_value
        self.assertEqual(pyv(dbv(pyv(dbv(dt)))), dt)

        dbv, pyv = utc_field.db_value, utc_field.python_value
        self.assertEqual(pyv(dbv(pyv(dbv(dt)))), dt)

    def test_timestamp_field_parts(self):
        dt = datetime.datetime(2019, 1, 2, 3, 4, 5)
        dt_utc = TimestampField().local_to_utc(dt)
        ts = TSModel.create(ts_s=dt, ts_us=dt, ts_ms=dt, ts_u=dt_utc)

        fields = (TSModel.ts_s, TSModel.ts_us, TSModel.ts_ms, TSModel.ts_u)
        attrs = ('year', 'month', 'day', 'hour', 'minute', 'second')
        selection = []
        for field in fields:
            for attr in attrs:
                selection.append(getattr(field, attr))

        row = TSModel.select(*selection).tuples()[0]

        # First ensure that all 3 fields are returning the same data.
        ts_s, ts_us, ts_ms, ts_u = row[:6], row[6:12], row[12:18], row[18:]
        self.assertEqual(ts_s, ts_us)
        self.assertEqual(ts_s, ts_ms)
        self.assertEqual(ts_s, ts_u)

        # Now validate that the data is correct. We will receive the data back
        # as a UTC unix timestamp, however!
        y, m, d, H, M, S = ts_s
        self.assertEqual(y, 2019)
        self.assertEqual(m, 1)
        self.assertEqual(d, dt_utc.day)
        self.assertEqual(H, dt_utc.hour)
        self.assertEqual(M, 4)
        self.assertEqual(S, 5)

    def test_timestamp_field_from_ts(self):
        dt = datetime.datetime(2019, 1, 2, 3, 4, 5)
        dt_utc = TimestampField().local_to_utc(dt)

        ts = TSModel.create(ts_s=dt, ts_us=dt, ts_ms=dt, ts_u=dt_utc)
        query = TSModel.select(
            TSModel.ts_s.from_timestamp().alias('dt_s'),
            TSModel.ts_us.from_timestamp().alias('dt_us'),
            TSModel.ts_ms.from_timestamp().alias('dt_ms'),
            TSModel.ts_u.from_timestamp().alias('dt_u'))

        # Get row and unpack into variables corresponding to the fields.
        row = query.tuples()[0]
        dt_s, dt_us, dt_ms, dt_u = row

        # Ensure the timestamp values for all 4 fields are the same.
        self.assertEqual(dt_s, dt_us)
        self.assertEqual(dt_s, dt_ms)
        self.assertEqual(dt_s, dt_u)
        if IS_SQLITE:
            expected = dt_utc.strftime('%Y-%m-%d %H:%M:%S')
            self.assertEqual(dt_s, expected)
        elif IS_POSTGRESQL or IS_CRDB:
            # Postgres returns an aware UTC datetime. Strip this to compare
            # against our naive UTC datetime.
            self.assertEqual(dt_s.replace(tzinfo=None), dt_utc)

    def test_invalid_resolution(self):
        self.assertRaises(ValueError, TimestampField, resolution=7)
        self.assertRaises(ValueError, TimestampField, resolution=20)
        self.assertRaises(ValueError, TimestampField, resolution=10**7)


class TS(TestModel):
    key = CharField(primary_key=True)
    timestamp = TimestampField(utc=True)


class TestZeroTimestamp(ModelTestCase):
    requires = [TS]

    def test_zero_timestamp(self):
        t0 = TS.create(key='t0', timestamp=0)
        t1 = TS.create(key='t1', timestamp=1)

        t0_db = TS.get(TS.key == 't0')
        self.assertEqual(t0_db.timestamp, datetime.datetime(1970, 1, 1))

        t1_db = TS.get(TS.key == 't1')
        self.assertEqual(t1_db.timestamp,
                         datetime.datetime(1970, 1, 1, 0, 0, 1))


class Schedule(TestModel):
    interval = IntegerField()

class Task(TestModel):
    schedule = ForeignKeyField(Schedule)
    name = TextField()
    last_run = DateTimeField()


class TestDateTimeMath(ModelTestCase):
    offset_to_names = (
        (-10, ()),
        (5, ('s1',)),
        (10, ('s1', 's10')),
        (11, ('s1', 's10')),
        (60, ('s1', 's10', 's60')),
        (61, ('s1', 's10', 's60')))
    requires = [Schedule, Task]

    def setUp(self):
        super(TestDateTimeMath, self).setUp()
        with self.database.atomic():
            s1 = Schedule.create(interval=1)
            s10 = Schedule.create(interval=10)
            s60 = Schedule.create(interval=60)

            self.dt = datetime.datetime(2019, 1, 1, 12)
            for s, n in ((s1, 's1'), (s10, 's10'), (s60, 's60')):
                Task.create(schedule=s, name=n, last_run=self.dt)

    def _do_test_date_time_math(self, next_occurrence_expression):
        for offset, names in self.offset_to_names:
            dt = Value(self.dt + datetime.timedelta(seconds=offset))
            query = (Task
                     .select(Task, Schedule)
                     .join(Schedule)
                     .where(dt >= next_occurrence_expression)
                     .order_by(Schedule.interval))
            tnames = [task.name for task in query]
            self.assertEqual(list(names), tnames)

    @requires_pglike
    def test_date_time_math_pg(self):
        second = SQL("INTERVAL '1 second'")
        next_occurrence = Task.last_run + (Schedule.interval * second)
        self._do_test_date_time_math(next_occurrence)

    @requires_sqlite
    def test_date_time_math_sqlite(self):
        # Convert to a timestamp, add the scheduled seconds, then convert back
        # to a datetime string for comparison with the last occurrence.
        next_ts = Task.last_run.to_timestamp() + Schedule.interval
        next_occurrence = fn.datetime(next_ts, 'unixepoch')
        self._do_test_date_time_math(next_occurrence)

    @requires_mysql
    def test_date_time_math_mysql(self):
        nl = NodeList((SQL('INTERVAL'), Schedule.interval, SQL('SECOND')))
        next_occurrence = fn.date_add(Task.last_run, nl)
        self._do_test_date_time_math(next_occurrence)



# ===========================================================================
# Blob, BigAutoField, and field value handling
# ===========================================================================

class BlobModel(TestModel):
    data = BlobField()


class TestBlobField(ModelTestCase):
    requires = [BlobModel]

    def test_blob_field(self):
        b = BlobModel.create(data=b'\xff\x01')
        b_db = BlobModel.get(BlobModel.data == b'\xff\x01')
        self.assertEqual(b.id, b_db.id)

        data = b_db.data
        if isinstance(data, memoryview):
            data = data.tobytes()
        elif not isinstance(data, bytes):
            data = bytes(data)
        self.assertEqual(data, b'\xff\x01')

    def test_blob_on_proxy(self):
        db = Proxy()
        class NewBlobModel(Model):
            data = BlobField()
            class Meta:
                database = db

        db_obj = SqliteDatabase(':memory:')
        db.initialize(db_obj)
        self.assertTrue(NewBlobModel.data._constructor is sqlite3.Binary)

    def test_blob_db_hook(self):
        sentinel = object()

        class FakeDatabase(Database):
            def get_binary_type(self):
                return sentinel

        class B(Model):
            b1 = BlobField()
            b2 = BlobField()

        B._meta.set_database(FakeDatabase(None))
        self.assertTrue(B.b1._constructor is sentinel)
        self.assertTrue(B.b2._constructor is sentinel)

        alt_db = SqliteDatabase(':memory:')
        with alt_db.bind_ctx([B]):
            # The constructor has been changed.
            self.assertTrue(B.b1._constructor is sqlite3.Binary)
            self.assertTrue(B.b2._constructor is sqlite3.Binary)

        # The constructor has been restored.
        self.assertTrue(B.b1._constructor is sentinel)
        self.assertTrue(B.b2._constructor is sentinel)


class TestBlobFieldContextRegression(BaseTestCase):
    def test_blob_field_context_regression(self):
        class A(Model):
            f = BlobField()

        orig = A.f._constructor
        db = get_in_memory_db()
        with db.bind_ctx([A]):
            self.assertTrue(A.f._constructor is db.get_binary_type())

        self.assertTrue(A.f._constructor is orig)


class BigModel(TestModel):
    pk = BigAutoField()
    data = TextField()


class TestBigAutoField(ModelTestCase):
    requires = [BigModel]

    def test_big_auto_field(self):
        b1 = BigModel.create(data='b1')
        b2 = BigModel.create(data='b2')

        b1_db = BigModel.get(BigModel.pk == b1.pk)
        b2_db = BigModel.get(BigModel.pk == b2.pk)

        self.assertTrue(b1_db.pk < b2_db.pk)
        self.assertTrue(b1_db.data, 'b1')
        self.assertTrue(b2_db.data, 'b2')


class Item(TestModel):
    price = IntegerField()
    multiplier = FloatField(default=1.)


class Bare(TestModel):
    key = BareField()
    value = BareField(adapt=int, null=True)


class TestFieldValueHandling(ModelTestCase):
    requires = [Item]

    @skip_if(IS_CRDB, 'crdb requires cast to multiply int and float')
    def test_int_float_multi(self):
        i = Item.create(price=10, multiplier=0.75)

        query = (Item
                 .select(Item, (Item.price * Item.multiplier).alias('total'))
                 .where(Item.id == i.id))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."price", "t1"."multiplier", '
            '("t1"."price" * "t1"."multiplier") AS "total" '
            'FROM "item" AS "t1" '
            'WHERE ("t1"."id" = ?)'), [i.id])

        i_db = query.get()
        self.assertEqual(i_db.price, 10)
        self.assertEqual(i_db.multiplier, .75)
        self.assertEqual(i_db.total, 7.5)

        # By default, Peewee will use the Price field (integer) converter to
        # coerce the value of it's right-hand operand (converting to 0).
        query = (Item
                 .select(Item, (Item.price * 0.75).alias('total'))
                 .where(Item.id == i.id))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."price", "t1"."multiplier", '
            '("t1"."price" * ?) AS "total" '
            'FROM "item" AS "t1" '
            'WHERE ("t1"."id" = ?)'), [0, i.id])

        # We can explicitly pass "False" and the value will not be converted.
        exp = Item.price * Value(0.75, False)
        query = (Item
                 .select(Item, exp.alias('total'))
                 .where(Item.id == i.id))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."price", "t1"."multiplier", '
            '("t1"."price" * ?) AS "total" '
            'FROM "item" AS "t1" '
            'WHERE ("t1"."id" = ?)'), [0.75, i.id])

        i_db = query.get()
        self.assertEqual(i_db.price, 10)
        self.assertEqual(i_db.multiplier, .75)
        self.assertEqual(i_db.total, 7.5)

    def test_explicit_cast(self):
        prices = ((10, 1.1), (5, .5))
        for price, multiplier in prices:
            Item.create(price=price, multiplier=multiplier)

        text = 'CHAR' if IS_MYSQL else 'TEXT'

        query = (Item
                 .select(Item.price.cast(text).alias('price_text'),
                         Item.multiplier.cast(text).alias('multiplier_text'))
                 .order_by(Item.id)
                 .dicts())
        self.assertEqual(list(query), [
            {'price_text': '10', 'multiplier_text': '1.1'},
            {'price_text': '5', 'multiplier_text': '0.5'},
        ])

        item = (Item
                .select(Item.price.cast(text).alias('price'),
                        Item.multiplier.cast(text).alias('multiplier'))
                .where(Item.price == 10)
                .get())
        self.assertEqual(item.price, '10')
        self.assertEqual(item.multiplier, '1.1')

    @requires_sqlite
    @requires_models(Bare)
    def test_bare_model_adapt(self):
        b1 = Bare.create(key='k1', value=1)
        b2 = Bare.create(key='k2', value='2')
        b3 = Bare.create(key='k3', value=None)

        b1_db = Bare.get(Bare.id == b1.id)
        self.assertEqual(b1_db.key, 'k1')
        self.assertEqual(b1_db.value, 1)

        b2_db = Bare.get(Bare.id == b2.id)
        self.assertEqual(b2_db.key, 'k2')
        self.assertEqual(b2_db.value, 2)

        b3_db = Bare.get(Bare.id == b3.id)
        self.assertEqual(b3_db.key, 'k3')
        self.assertTrue(b3_db.value is None)




# ===========================================================================
# UUID, IP, and bit fields
# ===========================================================================

class UUIDModel(TestModel):
    data = UUIDField(null=True)
    bdata = BinaryUUIDField(null=True)


class TestUUIDField(ModelTestCase):
    requires = [UUIDModel]

    def test_uuid_field(self):
        uu = uuid.uuid4()
        u = UUIDModel.create(data=uu)

        u_db = UUIDModel.get(UUIDModel.id == u.id)
        self.assertEqual(u_db.data, uu)
        self.assertTrue(u_db.bdata is None)

        u_db2 = UUIDModel.get(UUIDModel.data == uu)
        self.assertEqual(u_db2.id, u.id)

        # Verify we can use hex string.
        uu = uuid.uuid4()
        u = UUIDModel.create(data=uu.hex)
        u_db = UUIDModel.get(UUIDModel.data == uu.hex)
        self.assertEqual(u.id, u_db.id)
        self.assertEqual(u_db.data, uu)

        # Verify we can use raw binary representation.
        uu = uuid.uuid4()
        u = UUIDModel.create(data=uu.bytes)
        u_db = UUIDModel.get(UUIDModel.data == uu.bytes)
        self.assertEqual(u.id, u_db.id)
        self.assertEqual(u_db.data, uu)

    def test_binary_uuid_field(self):
        uu = uuid.uuid4()
        u = UUIDModel.create(bdata=uu)

        u_db = UUIDModel.get(UUIDModel.id == u.id)
        self.assertEqual(u_db.bdata, uu)
        self.assertTrue(u_db.data is None)

        u_db2 = UUIDModel.get(UUIDModel.bdata == uu)
        self.assertEqual(u_db2.id, u.id)

        # Verify we can use hex string.
        uu = uuid.uuid4()
        u = UUIDModel.create(bdata=uu.hex)
        u_db = UUIDModel.get(UUIDModel.bdata == uu.hex)
        self.assertEqual(u.id, u_db.id)
        self.assertEqual(u_db.bdata, uu)

        # Verify we can use raw binary representation.
        uu = uuid.uuid4()
        u = UUIDModel.create(bdata=uu.bytes)
        u_db = UUIDModel.get(UUIDModel.bdata == uu.bytes)
        self.assertEqual(u.id, u_db.id)
        self.assertEqual(u_db.bdata, uu)


class UU1(TestModel):
    id = UUIDField(default=uuid.uuid4, primary_key=True)
    name = TextField()

class UU2(TestModel):
    id = UUIDField(default=uuid.uuid4, primary_key=True)
    u1 = ForeignKeyField(UU1)
    name = TextField()


class TestForeignKeyUUIDField(ModelTestCase):
    requires = [UU1, UU2]

    def test_bulk_insert(self):
        # Create three UU1 instances.
        UU1.insert_many([{UU1.name: name} for name in 'abc'],
                       fields=[UU1.id, UU1.name]).execute()
        ua, ub, uc = UU1.select().order_by(UU1.name)

        # Create several UU2 instances.
        data = (
            ('a1', ua),
            ('b1', ub),
            ('b2', ub),
            ('c1', uc))
        iq = UU2.insert_many([{UU2.name: name, UU2.u1: u} for name, u in data],
                             fields=[UU2.id, UU2.name, UU2.u1])
        iq.execute()

        query = UU2.select().order_by(UU2.name)
        for (name, u1), u2 in zip(data, query):
            self.assertEqual(u2.name, name)
            self.assertEqual(u2.u1.id, u1.id)


class IPModel(TestModel):
    ip = IPField()
    ip_null = IPField(null=True)


class TestIPField(ModelTestCase):
    requires = [IPModel]

    def test_ip_field(self):
        ips = ('0.0.0.0', '255.255.255.255', '192.168.1.1')
        for ip in ips:
            i = IPModel.create(ip=ip)
            i_db = IPModel.get(ip=ip)
            self.assertEqual(i_db.ip, ip)
            self.assertEqual(i_db.ip_null, None)


class Bits(TestModel):
    F_STICKY = 1
    F_FAVORITE = 2
    F_MINIMIZED = 4

    flags = BitField()
    is_sticky = flags.flag(F_STICKY)
    is_favorite = flags.flag(F_FAVORITE)
    is_minimized = flags.flag(F_MINIMIZED)

    status = BitField(default=0)
    st_active = status.flag()
    st_draft = status.flag()

    data = BigBitField()


class TestBitFields(ModelTestCase):
    requires = [Bits]

    def test_bit_field_update(self):
        def assertFlags(expected):
            query = Bits.select().order_by(Bits.id)
            self.assertEqual([b.flags for b in query], expected)

        # Bits - flags (1=sticky, 2=favorite, 4=minimized)
        for i in range(1, 5):
            Bits.create(flags=i)

        q = Bits.select((~Bits.flags & 2).alias('bn')).order_by(Bits.id)
        self.assertEqual([b.bn for b in q], [2, 0, 0, 2])

        q = Bits.select().where((Bits.flags & 2) != 0).order_by(Bits.id)
        self.assertEqual([b.flags for b in q], [2, 3])

        Bits.update(flags=Bits.flags & ~2).execute()
        assertFlags([1, 0, 1, 4])

        Bits.update(flags=Bits.flags | 2).execute()
        assertFlags([3, 2, 3, 6])

        Bits.update(flags=Bits.is_favorite.clear()).execute()
        assertFlags([1, 0, 1, 4])

        Bits.update(flags=Bits.is_favorite.set()).execute()
        assertFlags([3, 2, 3, 6])

        # Clear multiple bits in one operation.
        Bits.update(flags=Bits.flags & ~(1 | 4)).execute()
        assertFlags([2, 2, 2, 2])

    def test_bit_field_auto_flag(self):
        class Bits2(TestModel):
            flags = BitField()

            f1 = flags.flag()  # Automatically gets 1.
            f2 = flags.flag()  # 2
            f4 = flags.flag()  # 4
            f16 = flags.flag(16)
            f32 = flags.flag()  # 32

        b = Bits2()
        self.assertEqual(b.flags, 0)

        b.f1 = True
        self.assertEqual(b.flags, 1)
        b.f4 = True
        self.assertEqual(b.flags, 5)

        b.f32 = True
        self.assertEqual(b.flags, 37)

    def test_bit_field_instance_flags(self):
        b = Bits()
        self.assertEqual(b.flags, 0)
        self.assertFalse(b.is_sticky)
        self.assertFalse(b.is_favorite)
        self.assertFalse(b.is_minimized)

        b.is_sticky = True
        b.is_minimized = True
        self.assertEqual(b.flags, 5)  # 1 | 4

        self.assertTrue(b.is_sticky)
        self.assertFalse(b.is_favorite)
        self.assertTrue(b.is_minimized)

        b.flags = 3
        self.assertTrue(b.is_sticky)
        self.assertTrue(b.is_favorite)
        self.assertFalse(b.is_minimized)

    def test_bit_field(self):
        b1 = Bits.create(flags=1)
        b2 = Bits.create(flags=2)
        b3 = Bits.create(flags=3)

        query = Bits.select().where(Bits.is_sticky).order_by(Bits.id)
        self.assertEqual([x.id for x in query], [b1.id, b3.id])

        query = Bits.select().where(Bits.is_favorite).order_by(Bits.id)
        self.assertEqual([x.id for x in query], [b2.id, b3.id])

        query = Bits.select().where(~Bits.is_favorite).order_by(Bits.id)
        self.assertEqual([x.id for x in query], [b1.id])

        # "&" operator does bitwise and for BitField.
        query = Bits.select().where((Bits.flags & 1) == 1).order_by(Bits.id)
        self.assertEqual([x.id for x in query], [b1.id, b3.id])

        # Test combining multiple bit expressions.
        query = Bits.select().where(Bits.is_sticky & Bits.is_favorite)
        self.assertEqual([x.id for x in query], [b3.id])

        query = Bits.select().where(Bits.is_sticky & ~Bits.is_favorite)
        self.assertEqual([x.id for x in query], [b1.id])

    def test_bit_field_name(self):
        def assertBits(bf, expected):
            self.assertEqual(
                (bf.is_sticky, bf.is_favorite, bf.st_active, bf.st_draft),
                expected)

        bf = Bits.create(flags=1)
        assertBits(bf, (True, False, False, False))

        bf.is_sticky = False
        bf.is_favorite = True
        bf.st_active = True
        bf.save()
        assertBits(bf, (False, True, True, False))

        bf = Bits.get(Bits.id == bf.id)
        assertBits(bf, (False, True, True, False))

        self.assertEqual(bf.flags, 2)
        self.assertEqual(bf.status, 1)

        self.assertEqual(Bits.select().where(Bits.is_favorite).count(), 1)
        self.assertEqual(Bits.select().where(Bits.st_draft).count(), 0)

    def test_bigbit_field_instance_data(self):
        b = Bits()
        values_to_set = (1, 11, 63, 31, 55, 48, 100, 99)
        for value in values_to_set:
            b.data.set_bit(value)

        for i in range(128):
            self.assertEqual(b.data.is_set(i), i in values_to_set)

        for i in range(128):
            b.data.clear_bit(i)

        buf = bytes(b.data._buffer)
        self.assertEqual(len(buf), 16)

        self.assertEqual(bytes(buf), b'\x00' * 16)

    def test_bigbit_zero_idx(self):
        b = Bits()
        b.data.set_bit(0)
        self.assertTrue(b.data.is_set(0))
        b.data.clear_bit(0)
        self.assertFalse(b.data.is_set(0))

        # Out-of-bounds returns False and does not extend data.
        self.assertFalse(b.data.is_set(1000))
        self.assertTrue(len(b.data), 1)

    def test_bigbit_item_methods(self):
        b = Bits()
        idxs = [0, 1, 4, 7, 8, 15, 16, 31, 32, 63]
        for i in idxs:
            b.data[i] = True
        for i in range(64):
            self.assertEqual(b.data[i], i in idxs)

        data = list(b.data)
        self.assertEqual(data, [1 if i in idxs else 0 for i in range(64)])

        for i in range(64):
            del b.data[i]
        self.assertEqual(len(b.data), 8)
        self.assertEqual(b.data._buffer, b'\x00' * 8)

    def test_bigbit_set_clear(self):
        b = Bits()
        b.data = b'\x01'
        for i in range(8):
            self.assertEqual(b.data[i], i == 0)

        b.data.clear()
        self.assertEqual(len(b.data), 0)

    def test_bigbit_field(self):
        b = Bits.create()
        b.data.set_bit(1)
        b.data.set_bit(3)
        b.data.set_bit(5)
        b.save()

        b_db = Bits.get(Bits.id == b.id)
        for x in range(7):
            if x % 2 == 1:
                self.assertTrue(b_db.data.is_set(x))
            else:
                self.assertFalse(b_db.data.is_set(x))

    def test_bigbit_field_bitwise(self):
        b1 = Bits(data=b'\x11')
        b2 = Bits(data=b'\x12')
        b3 = Bits(data=b'\x99')
        self.assertEqual(b1.data & b2.data, b'\x10')
        self.assertEqual(b1.data | b2.data, b'\x13')
        self.assertEqual(b1.data ^ b2.data, b'\x03')
        self.assertEqual(b1.data & b3.data, b'\x11')
        self.assertEqual(b1.data | b3.data, b'\x99')
        self.assertEqual(b1.data ^ b3.data, b'\x88')

        b1.data &= b2.data
        self.assertEqual(b1.data._buffer, b'\x10')

        b1.data |= b2.data
        self.assertEqual(b1.data._buffer, b'\x12')

        b1.data ^= b3.data
        self.assertEqual(b1.data._buffer, b'\x8b')

        b1.data = b'\x11'
        self.assertEqual(b1.data & b'\xff\xff', b'\x11\x00')
        self.assertEqual(b1.data | b'\xff\xff', b'\xff\xff')
        self.assertEqual(b1.data ^ b'\xff\xff', b'\xee\xff')

        b1.data = b'\x11\x11'
        self.assertEqual(b1.data & b'\xff', b'\x11\x00')
        self.assertEqual(b1.data | b'\xff', b'\xff\x11')
        self.assertEqual(b1.data ^ b'\xff', b'\xee\x11')

    def test_bigbit_field_bulk_create(self):
        b1, b2, b3 = Bits(), Bits(), Bits()
        b1.data.set_bit(1)
        b2.data.set_bit(2)
        b3.data.set_bit(3)
        Bits.bulk_create([b1, b2, b3])
        self.assertEqual(len(Bits), 3)
        for b in Bits.select():
            self.assertEqual(sum(1 if b.data.is_set(i) else 0
                                 for i in (1, 2, 3)), 1)

    def test_bigbit_field_bulk_update(self):
        b1, b2, b3 = Bits.create(), Bits.create(), Bits.create()

        b1.data.set_bit(11)
        b2.data.set_bit(12)
        b3.data.set_bit(13)
        Bits.bulk_update([b1, b2, b3], fields=[Bits.data])

        mapping = {b1.id: 11, b2.id: 12, b3.id: 13}
        for b in Bits.select():
            bit = mapping[b.id]
            self.assertTrue(b.data.is_set(bit))




# ===========================================================================
# Special fields (custom, virtual, field functions, misc types)
# ===========================================================================

class ListField(TextField):
    def db_value(self, value):
        return ','.join(value) if value else ''

    def python_value(self, value):
        return value.split(',') if value else []


class Todo(TestModel):
    content = TextField()
    tags = ListField()


class TestCustomField(ModelTestCase):
    requires = [Todo]

    def test_custom_field(self):
        t1 = Todo.create(content='t1', tags=['t1-a', 't1-b'])
        t2 = Todo.create(content='t2', tags=[])

        t1_db = Todo.get(Todo.id == t1.id)
        self.assertEqual(t1_db.tags, ['t1-a', 't1-b'])

        t2_db = Todo.get(Todo.id == t2.id)
        self.assertEqual(t2_db.tags, [])

        t1_db = Todo.get(Todo.tags == AsIs(['t1-a', 't1-b']))
        self.assertEqual(t1_db.id, t1.id)

        t2_db = Todo.get(Todo.tags == AsIs([]))
        self.assertEqual(t2_db.id, t2.id)


class UpperField(TextField):
    def db_value(self, value):
        return fn.UPPER(value)


class UpperModel(TestModel):
    name = UpperField()


class TestSQLFunctionDBValue(ModelTestCase):
    database = get_in_memory_db()
    requires = [UpperModel]

    def test_sql_function_db_value(self):
        # Verify that the db function is applied as part of an INSERT.
        um = UpperModel.create(name='huey')
        um_db = UpperModel.get(UpperModel.id == um.id)
        self.assertEqual(um_db.name, 'HUEY')

        # Verify that the db function is applied as part of an UPDATE.
        um_db.name = 'zaizee'
        um_db.save()

        # Ensure that the name was updated correctly.
        um_db2 = UpperModel.get(UpperModel.id == um.id)
        self.assertEqual(um_db2.name, 'ZAIZEE')

        # Verify that the db function is applied in a WHERE expression.
        um_db3 = UpperModel.get(UpperModel.name == 'zaiZee')
        self.assertEqual(um_db3.id, um.id)

        # If we nest the field in a function, the conversion is not applied.
        expr = fn.SUBSTR(UpperModel.name, 1, 1) == 'z'
        self.assertRaises(UpperModel.DoesNotExist, UpperModel.get, expr)

class VF(TestModel):
    name = TextField()
    computed = VirtualField(field_class=IntegerField)


class TestVirtualFieldBehavior(BaseTestCase):
    def test_virtual_field_not_in_columns(self):
        """VirtualField should not appear in the model's SELECT columns."""
        fields = VF._meta.sorted_fields
        field_names = [f.name for f in fields]
        self.assertIn('name', field_names)
        # VirtualField should not be in sorted_fields (it's a MetaField).
        self.assertNotIn('computed', field_names)

        query = VF.select()
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name" FROM "vf" AS "t1"'))

    def test_virtual_field_db_value(self):
        vf = VF.computed
        self.assertEqual(vf.db_value('42'), 42)
        self.assertEqual(vf.python_value('42'), 42)


class TestTextField(TextField):
    def first_char(self):
        return fn.SUBSTR(self, 1, 1)


class PhoneBook(TestModel):
    name = TestTextField()


class TestFieldFunction(ModelTestCase):
    requires = [PhoneBook]

    def setUp(self):
        super(TestFieldFunction, self).setUp()
        names = ('huey', 'mickey', 'zaizee', 'beanie', 'scout', 'hallee')
        for name in names:
            PhoneBook.create(name=name)

    def _test_field_function(self, PB):
        query = (PB
                 .select()
                 .where(PB.name.first_char() == 'h')
                 .order_by(PB.name))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name" '
            'FROM "phone_book" AS "t1" '
            'WHERE (SUBSTR("t1"."name", ?, ?) = ?) '
            'ORDER BY "t1"."name"'), [1, 1, 'h'])

        self.assertEqual([pb.name for pb in query], ['hallee', 'huey'])

    def test_field_function(self):
        self._test_field_function(PhoneBook)

    def test_field_function_alias(self):
        self._test_field_function(PhoneBook.alias())


class DblSI(TestModel):
    df = DoubleField()
    si = SmallIntegerField()


class TestDoubleSmallInt(ModelTestCase):
    database = get_in_memory_db()
    requires = [DblSI]

    def test_double_round_trip(self):
        DblSI.create(df=3.141592653589793, si=0)
        obj = DblSI.get()
        self.assertAlmostEqual(obj.df, 3.141592653589793, places=10)

    def test_small_int_round_trip(self):
        DblSI.create(df=0, si=32000)
        DblSI.create(df=0, si=-100)
        results = (DblSI
                   .select(DblSI.si)
                   .order_by(DblSI.si)
                   .tuples())
        self.assertEqual(list(results), [(-100,), (32000,)])

    def test_coercion(self):
        DblSI.create(df=float('inf'), si='42')
        obj = DblSI.get()
        self.assertEqual(obj.df, float('inf'))
        self.assertEqual(obj.si, 42)

        obj = DblSI.create(df=float('-inf'), si='1.23')
        obj = DblSI.get(DblSI.id == obj.id)
        self.assertEqual(obj.df, float('-inf'))
        self.assertEqual(obj.si, 1)


class InvalidTypes(TestModel):
    tfield = TextField()
    ifield = IntegerField()
    ffield = FloatField()


class TestSqliteInvalidDataTypes(ModelTestCase):
    database = get_in_memory_db()
    requires = [InvalidTypes]

    def test_invalid_data_types(self):
        it = InvalidTypes.create(tfield=100, ifield='five', ffield='pi')
        it_db1 = InvalidTypes.get(InvalidTypes.tfield == 100)
        it_db2 = InvalidTypes.get(InvalidTypes.ifield == 'five')
        it_db3 = InvalidTypes.get(InvalidTypes.ffield == 'pi')
        self.assertTrue(it.id == it_db1.id == it_db2.id == it_db3.id)

        self.assertEqual(it_db1.tfield, '100')
        self.assertEqual(it_db1.ifield, 'five')
        self.assertEqual(it_db1.ffield, 'pi')



# ===========================================================================
# Foreign key basics, deferred FK, lazy loading, constraints
# ===========================================================================

class U2(TestModel):
    username = TextField()


class T2(TestModel):
    user = ForeignKeyField(U2, backref='tweets', on_delete='CASCADE')
    content = TextField()


class TestForeignKeyField(ModelTestCase):
    requires = [User, Tweet]

    def test_set_fk(self):
        huey = User.create(username='huey')
        zaizee = User.create(username='zaizee')

        # Test resolution of attributes after creation does not trigger SELECT.
        with self.assertQueryCount(1):
            tweet = Tweet.create(content='meow', user=huey)
            self.assertEqual(tweet.user.username, 'huey')

        # Test we can set to an integer, in which case a query will occur.
        with self.assertQueryCount(2):
            tweet = Tweet.create(content='purr', user=zaizee.id)
            self.assertEqual(tweet.user.username, 'zaizee')

        # Test we can set the ID accessor directly.
        with self.assertQueryCount(2):
            tweet = Tweet.create(content='hiss', user_id=huey.id)
            self.assertEqual(tweet.user.username, 'huey')

    def test_follow_attributes(self):
        huey = User.create(username='huey')
        Tweet.create(content='meow', user=huey)
        Tweet.create(content='hiss', user=huey)

        with self.assertQueryCount(1):
            query = (Tweet
                     .select(Tweet.content, Tweet.user.username)
                     .join(User)
                     .order_by(Tweet.content))
            self.assertEqual([(tweet.content, tweet.user.username)
                              for tweet in query],
                             [('hiss', 'huey'), ('meow', 'huey')])

        self.assertRaises(AttributeError, lambda: Tweet.user.foo)

    def test_disable_backref(self):
        class Person(TestModel):
            pass
        class Pet(TestModel):
            owner = ForeignKeyField(Person, backref='!')

        self.assertEqual(Pet.owner.backref, '!')

        # No attribute/accessor is added to the related model.
        self.assertRaises(AttributeError, lambda: Person.pet_set)

        # We still preserve the metadata about the relationship.
        self.assertTrue(Pet.owner in Person._meta.backrefs)

    @requires_models(U2, T2)
    def test_on_delete_behavior(self):
        if IS_SQLITE:
            self.database.foreign_keys = 1

        with self.database.atomic():
            for username in ('u1', 'u2', 'u3'):
                user = U2.create(username=username)
                for i in range(3):
                    T2.create(user=user, content='%s-%s' % (username, i))

        self.assertEqual(T2.select().count(), 9)
        U2.delete().where(U2.username == 'u2').execute()
        self.assertEqual(T2.select().count(), 6)

        query = (U2
                 .select(U2.username, fn.COUNT(T2.id).alias('ct'))
                 .join(T2, JOIN.LEFT_OUTER)
                 .group_by(U2.username)
                 .order_by(U2.username))
        self.assertEqual([(u.username, u.ct) for u in query], [
            ('u1', 3),
            ('u3', 3)])


class M1(TestModel):
    name = CharField(primary_key=True)
    m2 = DeferredForeignKey('M2', deferrable='INITIALLY DEFERRED',
                            on_delete='CASCADE')

class M2(TestModel):
    name = CharField(primary_key=True)
    m1 = ForeignKeyField(M1, deferrable='INITIALLY DEFERRED',
                         on_delete='CASCADE')


@skip_if(IS_MYSQL)
@skip_if(IS_CRDB, 'crdb does not support deferred foreign-key constraints')
class TestDeferredForeignKey(ModelTestCase):
    requires = [M1, M2]

    def test_deferred_foreign_key(self):
        with self.database.atomic():
            m1 = M1.create(name='m1', m2='m2')
            m2 = M2.create(name='m2', m1='m1')

        m1_db = M1.get(M1.name == 'm1')
        self.assertEqual(m1_db.m2.name, 'm2')

        m2_db = M2.get(M2.name == 'm2')
        self.assertEqual(m2_db.m1.name, 'm1')


class Composite(TestModel):
    first = CharField()
    last = CharField()
    data = TextField()

    class Meta:
        primary_key = CompositeKey('first', 'last')


class TestDeferredForeignKeyResolution(ModelTestCase):
    def test_unresolved_deferred_fk(self):
        class Photo(Model):
            album = DeferredForeignKey('Album', column_name='id_album')
            class Meta:
                database = get_in_memory_db()
        self.assertSQL(Photo.select(), (
            'SELECT "t1"."id", "t1"."id_album" FROM "photo" AS "t1"'), [])

    def test_deferred_foreign_key_resolution(self):
        class Base(Model):
            class Meta:
                database = get_in_memory_db()

        class Photo(Base):
            album = DeferredForeignKey('Album', column_name='id_album',
                                       null=False, backref='pictures')
            alt_album = DeferredForeignKey('Album', column_name='id_Alt_album',
                                           field='alt_id', backref='alt_pix',
                                           null=True)

        class Album(Base):
            name = TextField()
            alt_id = IntegerField(column_name='_Alt_id')

        self.assertTrue(Photo.album.rel_model is Album)
        self.assertTrue(Photo.album.rel_field is Album.id)
        self.assertEqual(Photo.album.column_name, 'id_album')
        self.assertFalse(Photo.album.null)

        self.assertTrue(Photo.alt_album.rel_model is Album)
        self.assertTrue(Photo.alt_album.rel_field is Album.alt_id)
        self.assertEqual(Photo.alt_album.column_name, 'id_Alt_album')
        self.assertTrue(Photo.alt_album.null)

        self.assertSQL(Photo._schema._create_table(), (
            'CREATE TABLE IF NOT EXISTS "photo" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"id_album" INTEGER NOT NULL, '
            '"id_Alt_album" INTEGER)'), [])

        self.assertSQL(Photo._schema._create_foreign_key(Photo.album), (
            'ALTER TABLE "photo" ADD CONSTRAINT "fk_photo_id_album_refs_album"'
            ' FOREIGN KEY ("id_album") REFERENCES "album" ("id")'))
        self.assertSQL(Photo._schema._create_foreign_key(Photo.alt_album), (
            'ALTER TABLE "photo" ADD CONSTRAINT '
            '"fk_photo_id_Alt_album_refs_album"'
            ' FOREIGN KEY ("id_Alt_album") REFERENCES "album" ("_Alt_id")'))

        self.assertSQL(Photo.select(), (
            'SELECT "t1"."id", "t1"."id_album", "t1"."id_Alt_album" '
            'FROM "photo" AS "t1"'), [])

        a = Album(id=3, alt_id=4)
        self.assertSQL(a.pictures, (
            'SELECT "t1"."id", "t1"."id_album", "t1"."id_Alt_album" '
            'FROM "photo" AS "t1" WHERE ("t1"."id_album" = ?)'), [3])
        self.assertSQL(a.alt_pix, (
            'SELECT "t1"."id", "t1"."id_album", "t1"."id_Alt_album" '
            'FROM "photo" AS "t1" WHERE ("t1"."id_Alt_album" = ?)'), [4])

class TestDeferredForeignKeyIntegration(ModelTestCase):
    database = get_in_memory_db()

    def test_deferred_fk_simple(self):
        class Base(TestModel):
            class Meta:
                database = self.database
        class DFFk(Base):
            fk = DeferredForeignKey('DFPk')

        # Deferred key not bound yet.
        self.assertTrue(isinstance(DFFk.fk, DeferredForeignKey))

        class DFPk(Base): pass

        # Deferred key is bound correctly.
        self.assertTrue(isinstance(DFFk.fk, ForeignKeyField))
        self.assertEqual(DFFk.fk.rel_model, DFPk)
        self.assertEqual(DFFk._meta.refs, {DFFk.fk: DFPk})
        self.assertEqual(DFFk._meta.backrefs, {})
        self.assertEqual(DFPk._meta.refs, {})
        self.assertEqual(DFPk._meta.backrefs, {DFFk.fk: DFFk})
        self.assertSQL(DFFk._schema._create_table(False), (
            'CREATE TABLE "df_fk" ("id" INTEGER NOT NULL PRIMARY KEY, '
            '"fk_id" INTEGER NOT NULL)'), [])

    def test_deferred_fk_as_pk(self):
        class Base(TestModel):
            class Meta:
                database = self.database
        class DFFk(Base):
            fk = DeferredForeignKey('DFPk', primary_key=True)

        # Deferred key not bound yet.
        self.assertTrue(isinstance(DFFk.fk, DeferredForeignKey))
        self.assertTrue(DFFk._meta.primary_key is DFFk.fk)

        class DFPk(Base): pass

        # Resolved and primary-key set correctly.
        self.assertTrue(isinstance(DFFk.fk, ForeignKeyField))
        self.assertTrue(DFFk._meta.primary_key is DFFk.fk)

        self.assertEqual(DFFk.fk.rel_model, DFPk)
        self.assertEqual(DFFk._meta.refs, {DFFk.fk: DFPk})
        self.assertEqual(DFFk._meta.backrefs, {})
        self.assertEqual(DFPk._meta.refs, {})
        self.assertEqual(DFPk._meta.backrefs, {DFFk.fk: DFFk})
        self.assertSQL(DFFk._schema._create_table(False), (
            'CREATE TABLE "df_fk" ("fk_id" INTEGER NOT NULL PRIMARY KEY)'), [])

class NQ(TestModel):
    name = TextField()

class NQItem(TestModel):
    nq = ForeignKeyField(NQ, backref='items')
    nq_null = ForeignKeyField(NQ, backref='null_items', null=True)
    nq_lazy = ForeignKeyField(NQ, lazy_load=False, backref='lazy_items')
    nq_lazy_null = ForeignKeyField(NQ, lazy_load=False,
                                   backref='lazy_null_items', null=True)


class TestForeignKeyLazyLoad(ModelTestCase):
    requires = [NQ, NQItem]

    def setUp(self):
        super(TestForeignKeyLazyLoad, self).setUp()
        with self.database.atomic():
            a1, a2, a3, a4 = [NQ.create(name='a%s' % i) for i in range(1, 5)]
            ai = NQItem.create(nq=a1, nq_null=a2, nq_lazy=a3, nq_lazy_null=a4)

            b = NQ.create(name='b')
            bi = NQItem.create(nq=b, nq_lazy=b)

    def test_doesnotexist_lazy_load(self):
        n = NQ.create(name='n1')
        i = NQItem.create(nq=n, nq_null=n, nq_lazy=n, nq_lazy_null=n)

        i_db = NQItem.select(NQItem.id).where(NQItem.nq == n).get()
        with self.assertQueryCount(0):
            # Only raise DoesNotExist for non-nullable *and* lazy-load=True.
            # Otherwise we just return None.
            self.assertRaises(NQ.DoesNotExist, lambda: i_db.nq)
            self.assertTrue(i_db.nq_null is None)
            self.assertTrue(i_db.nq_lazy is None)
            self.assertTrue(i_db.nq_lazy_null is None)

    def test_foreign_key_lazy_load(self):
        a1, a2, a3, a4 = (NQ.select()
                          .where(NQ.name.startswith('a'))
                          .order_by(NQ.name))
        b = NQ.get(NQ.name == 'b')
        ai = NQItem.get(NQItem.nq_id == a1.id)
        bi = NQItem.get(NQItem.nq_id == b.id)

        # Accessing the lazy foreign-key fields will not result in any queries
        # being executed.
        with self.assertQueryCount(0):
            self.assertEqual(ai.nq_lazy, a3.id)
            self.assertEqual(ai.nq_lazy_null, a4.id)
            self.assertEqual(bi.nq_lazy, b.id)
            self.assertTrue(bi.nq_lazy_null is None)
            self.assertTrue(bi.nq_null is None)

        # Accessing the regular foreign-key fields uses a query to get the
        # related model instance.
        with self.assertQueryCount(2):
            self.assertEqual(ai.nq.id, a1.id)
            self.assertEqual(ai.nq_null.id, a2.id)

        with self.assertQueryCount(1):
            self.assertEqual(bi.nq.id, b.id)

    def test_fk_lazy_load_related_instance(self):
        nq = NQ(name='b1')
        nqi = NQItem(nq=nq, nq_null=nq, nq_lazy=nq, nq_lazy_null=nq)
        nq.save()
        nqi.save()

        with self.assertQueryCount(1):
            nqi_db = NQItem.get(NQItem.id == nqi.id)
            self.assertEqual(nqi_db.nq_lazy, nq.id)
            self.assertEqual(nqi_db.nq_lazy_null, nq.id)

    def test_fk_lazy_select_related(self):
        NA, NB, NC, ND = [NQ.alias(a) for a in ('na', 'nb', 'nc', 'nd')]
        LO = JOIN.LEFT_OUTER
        query = (NQItem.select(NQItem, NA, NB, NC, ND)
                 .join_from(NQItem, NA, LO, on=NQItem.nq)
                 .join_from(NQItem, NB, LO, on=NQItem.nq_null)
                 .join_from(NQItem, NC, LO, on=NQItem.nq_lazy)
                 .join_from(NQItem, ND, LO, on=NQItem.nq_lazy_null)
                 .order_by(NQItem.id))

        # If we explicitly / eagerly select lazy foreign-key models, they
        # behave just like regular foreign keys.
        with self.assertQueryCount(1):
            ai, bi = [ni for ni in query]
            self.assertEqual(ai.nq.name, 'a1')
            self.assertEqual(ai.nq_null.name, 'a2')
            self.assertEqual(ai.nq_lazy.name, 'a3')
            self.assertEqual(ai.nq_lazy_null.name, 'a4')

            self.assertEqual(bi.nq.name, 'b')
            self.assertEqual(bi.nq_lazy.name, 'b')
            self.assertTrue(bi.nq_null is None)
            self.assertTrue(bi.nq_lazy_null is None)

class Package(TestModel):
    barcode = CharField(unique=True)


class PackageItem(TestModel):
    title = CharField()
    package = ForeignKeyField(Package, Package.barcode, backref='items')


class TestForeignKeyToNonPrimaryKey(ModelTestCase):
    requires = [Package, PackageItem]

    def setUp(self):
        super(TestForeignKeyToNonPrimaryKey, self).setUp()

        for barcode in ['101', '102']:
            Package.create(barcode=barcode)
            for i in range(2):
                PackageItem.create(
                    package=barcode,
                    title='%s-%s' % (barcode, i))

    def test_fk_resolution(self):
        pi = PackageItem.get(PackageItem.title == '101-0')
        self.assertEqual(pi.__data__['package'], '101')
        self.assertEqual(pi.package, Package.get(Package.barcode == '101'))

    def test_select_generation(self):
        p = Package.get(Package.barcode == '101')
        self.assertEqual(
            [item.title for item in p.items.order_by(PackageItem.title)],
            ['101-0', '101-1'])


class Manufacturer(TestModel):
    name = CharField()


class Component(TestModel):
    name = CharField()
    manufacturer = ForeignKeyField(Manufacturer, null=True)


class Computer(TestModel):
    hard_drive = ForeignKeyField(Component, backref='c1')
    memory = ForeignKeyField(Component, backref='c2')
    processor = ForeignKeyField(Component, backref='c3')


class TestMultipleForeignKey(ModelTestCase):
    requires = [Manufacturer, Component, Computer]
    test_values = [
        ['3TB', '16GB', 'i7'],
        ['128GB', '1GB', 'ARM'],
    ]

    def setUp(self):
        super(TestMultipleForeignKey, self).setUp()
        intel = Manufacturer.create(name='Intel')
        amd = Manufacturer.create(name='AMD')
        kingston = Manufacturer.create(name='Kingston')
        for hard_drive, memory, processor in self.test_values:
            c = Computer.create(
                hard_drive=Component.create(name=hard_drive),
                memory=Component.create(name=memory, manufacturer=kingston),
                processor=Component.create(name=processor, manufacturer=intel))

        # The 2nd computer has an AMD processor.
        c.processor.manufacturer = amd
        c.processor.save()

    def test_multi_join(self):
        HDD = Component.alias('hdd')
        HDDMf = Manufacturer.alias('hddm')
        Memory = Component.alias('mem')
        MemoryMf = Manufacturer.alias('memm')
        Processor = Component.alias('proc')
        ProcessorMf = Manufacturer.alias('procm')
        query = (Computer
                 .select(
                     Computer,
                     HDD,
                     Memory,
                     Processor,
                     HDDMf,
                     MemoryMf,
                     ProcessorMf)
                 .join(HDD, on=(
                     Computer.hard_drive_id == HDD.id).alias('hard_drive'))
                 .join(
                     HDDMf,
                     JOIN.LEFT_OUTER,
                     on=(HDD.manufacturer_id == HDDMf.id))
                 .switch(Computer)
                 .join(Memory, on=(
                     Computer.memory_id == Memory.id).alias('memory'))
                 .join(
                     MemoryMf,
                     JOIN.LEFT_OUTER,
                     on=(Memory.manufacturer_id == MemoryMf.id))
                 .switch(Computer)
                 .join(Processor, on=(
                     Computer.processor_id == Processor.id).alias('processor'))
                 .join(
                     ProcessorMf,
                     JOIN.LEFT_OUTER,
                     on=(Processor.manufacturer_id == ProcessorMf.id))
                 .order_by(Computer.id))

        with self.assertQueryCount(1):
            vals = []
            manufacturers = []
            for computer in query:
                components = [
                    computer.hard_drive,
                    computer.memory,
                    computer.processor]
                vals.append([component.name for component in components])
                for component in components:
                    if component.manufacturer:
                        manufacturers.append(component.manufacturer.name)
                    else:
                        manufacturers.append(None)

            self.assertEqual(vals, self.test_values)
            self.assertEqual(manufacturers, [
                None, 'Kingston', 'Intel',
                None, 'Kingston', 'AMD',
            ])


class TestMultipleForeignKeysJoining(ModelTestCase):
    requires = [Person, Relationship]

    def test_multiple_fks(self):
        a = Person.create(first='a', last='l')
        b = Person.create(first='b', last='l')
        c = Person.create(first='c', last='l')

        self.assertEqual(list(a.relations), [])
        self.assertEqual(list(a.related_to), [])

        r_ab = Relationship.create(from_person=a, to_person=b)
        self.assertEqual(list(a.relations), [r_ab])
        self.assertEqual(list(a.related_to), [])
        self.assertEqual(list(b.relations), [])
        self.assertEqual(list(b.related_to), [r_ab])

        r_bc = Relationship.create(from_person=b, to_person=c)

        following = Person.select().join(
            Relationship, on=Relationship.to_person
        ).where(Relationship.from_person == a)
        self.assertEqual(list(following), [b])

        followers = Person.select().join(
            Relationship, on=Relationship.from_person
        ).where(Relationship.to_person == a.id)
        self.assertEqual(list(followers), [])

        following = Person.select().join(
            Relationship, on=Relationship.to_person
        ).where(Relationship.from_person == b.id)
        self.assertEqual(list(following), [c])

        followers = Person.select().join(
            Relationship, on=Relationship.from_person
        ).where(Relationship.to_person == b.id)
        self.assertEqual(list(followers), [a])

        following = Person.select().join(
            Relationship, on=Relationship.to_person
        ).where(Relationship.from_person == c.id)
        self.assertEqual(list(following), [])

        followers = Person.select().join(
            Relationship, on=Relationship.from_person
        ).where(Relationship.to_person == c.id)
        self.assertEqual(list(followers), [b])


class TestForeignKeyConstraints(ModelTestCase):
    requires = [Person, Note]

    def setUp(self):
        super(TestForeignKeyConstraints, self).setUp()
        self.set_foreign_key_pragma(True)

    def tearDown(self):
        self.set_foreign_key_pragma(False)
        super(TestForeignKeyConstraints, self).tearDown()

    def set_foreign_key_pragma(self, is_enabled):
        if IS_SQLITE:
            self.database.foreign_keys = 'on' if is_enabled else 'off'

    def test_constraint_exists(self):
        max_id = Person.select(fn.MAX(Person.id)).scalar() or 0
        with self.assertRaisesCtx(IntegrityError):
            with self.database.atomic():
                Note.create(author=max_id + 1, content='test')

    @requires_sqlite
    def test_disable_constraint(self):
        self.set_foreign_key_pragma(False)
        Note.create(author=0, content='test')


class FK_A(TestModel):
    key = CharField(max_length=16, unique=True)

class FK_B(TestModel):
    fk_a = ForeignKeyField(FK_A, field='key')


class TestFKtoNonPKField(ModelTestCase):
    requires = [FK_A, FK_B]

    def test_fk_to_non_pk_field(self):
        a1 = FK_A.create(key='a1')
        a2 = FK_A.create(key='a2')
        b1 = FK_B.create(fk_a=a1)
        b2 = FK_B.create(fk_a=a2)

        args = (b1.fk_a, b1.fk_a_id, a1, a1.key)
        for arg in args:
            query = FK_B.select().where(FK_B.fk_a == arg)
            self.assertSQL(query, (
                'SELECT "t1"."id", "t1"."fk_a_id" FROM "fk_b" AS "t1" '
                'WHERE ("t1"."fk_a_id" = ?)'), ['a1'])
            b1_db = query.get()
            self.assertEqual(b1_db.id, b1.id)

    def test_fk_to_non_pk_insert_update(self):
        a1 = FK_A.create(key='a1')
        b1 = FK_B.create(fk_a=a1)
        self.assertEqual(FK_B.select().where(FK_B.fk_a == a1).count(), 1)

        exprs = (
            {FK_B.fk_a: a1},
            {'fk_a': a1},
            {FK_B.fk_a: a1.key},
            {'fk_a': a1.key})
        for n, expr in enumerate(exprs, 2):
            self.assertTrue(FK_B.insert(expr).execute())
            self.assertEqual(FK_B.select().where(FK_B.fk_a == a1).count(), n)

        a2 = FK_A.create(key='a2')
        exprs = (
            {FK_B.fk_a: a2},
            {'fk_a': a2},
            {FK_B.fk_a: a2.key},
            {'fk_a': a2.key})

        b_list = list(FK_B.select().where(FK_B.fk_a == a1))
        for i, (b, expr) in enumerate(zip(b_list[1:], exprs), 1):
            self.assertTrue(FK_B.update(expr).where(FK_B.id == b.id).execute())
            self.assertEqual(FK_B.select().where(FK_B.fk_a == a2).count(), i)


class FKN_A(TestModel): pass
class FKN_B(TestModel):
    a = ForeignKeyField(FKN_A, null=True)

class TestSetFKNull(ModelTestCase):
    requires = [FKN_A, FKN_B]

    def test_set_fk_null(self):
        a1 = FKN_A.create()
        a2 = FKN_A()
        b1 = FKN_B(a=a1)
        b2 = FKN_B(a=a2)

        self.assertTrue(b1.a is a1)
        self.assertTrue(b2.a is a2)
        b1.a = b2.a = None
        self.assertTrue(b1.a is None)
        self.assertTrue(b2.a is None)

class FKF_A(TestModel):
    key = CharField(max_length=16, unique=True)

class FKF_B(TestModel):
    fk_a_1 = ForeignKeyField(FKF_A, field='key')
    fk_a_2 = IntegerField()


class TestQueryWithModelInstanceParam(ModelTestCase):
    requires = [FKF_A, FKF_B]

    def test_query_with_model_instance_param(self):
        a1 = FKF_A.create(key='k1')
        a2 = FKF_A.create(key='k2')
        b1 = FKF_B.create(fk_a_1=a1, fk_a_2=a1)
        b2 = FKF_B.create(fk_a_1=a2, fk_a_2=a2)

        # Ensure that UPDATE works as expected as well.
        b1.save()

        # See also keys.TestFKtoNonPKField test, which replicates much of this.
        args = (b1.fk_a_1, b1.fk_a_1_id, a1, a1.key)
        for arg in args:
            query = FKF_B.select().where(FKF_B.fk_a_1 == arg)
            self.assertSQL(query, (
                'SELECT "t1"."id", "t1"."fk_a_1_id", "t1"."fk_a_2" '
                'FROM "fkf_b" AS "t1" '
                'WHERE ("t1"."fk_a_1_id" = ?)'), ['k1'])
            b1_db = query.get()
            self.assertEqual(b1_db.id, b1.id)

        # When we are handed a model instance and a conversion (an IntegerField
        # in this case), when the attempted conversion fails we fall back to
        # using the given model's primary-key.
        args = (b1.fk_a_2, a1, a1.id)
        for arg in args:
            query = FKF_B.select().where(FKF_B.fk_a_2 == arg)
            self.assertSQL(query, (
                'SELECT "t1"."id", "t1"."fk_a_1_id", "t1"."fk_a_2" '
                'FROM "fkf_b" AS "t1" '
                'WHERE ("t1"."fk_a_2" = ?)'), [a1.id])
            b1_db = query.get()
            self.assertEqual(b1_db.id, b1.id)


# ===========================================================================
# Composite primary key
# ===========================================================================

class TestCompositePrimaryKeyField(ModelTestCase):
    requires = [Composite]

    def test_composite_primary_key(self):
        pass


class CompositeKeyModel(TestModel):
    f1 = CharField()
    f2 = IntegerField()
    f3 = FloatField()

    class Meta:
        primary_key = CompositeKey('f1', 'f2')


class Post(TestModel):
    title = CharField()

class Tag(TestModel):
    tag = CharField()

class TagPostThrough(TestModel):
    tag = ForeignKeyField(Tag, backref='posts')
    post = ForeignKeyField(Post, backref='tags')

    class Meta:
        primary_key = CompositeKey('tag', 'post')

class TagPostThroughAlt(TestModel):
    tag = ForeignKeyField(Tag, backref='posts_alt')
    post = ForeignKeyField(Post, backref='tags_alt')

class DIParent(TestModel):
    title = CharField()

class DIChild(TestModel):
    parent = ForeignKeyField(DIParent, backref='children')
    data = CharField()

    class Meta:
        primary_key = CompositeKey('data', 'parent')


class TestCompositePrimaryKey(ModelTestCase):
    requires = [Tag, Post, TagPostThrough, CompositeKeyModel]

    def setUp(self):
        super(TestCompositePrimaryKey, self).setUp()
        tags = [Tag.create(tag='t%d' % i) for i in range(1, 4)]
        posts = [Post.create(title='p%d' % i) for i in range(1, 4)]
        p12 = Post.create(title='p12')
        for t, p in zip(tags, posts):
            TagPostThrough.create(tag=t, post=p)
        TagPostThrough.create(tag=tags[0], post=p12)
        TagPostThrough.create(tag=tags[1], post=p12)

    def test_create_table_query(self):
        query, params = TagPostThrough._schema._create_table().query()
        sql = ('CREATE TABLE IF NOT EXISTS "tag_post_through" ('
               '"tag_id" INTEGER NOT NULL, '
               '"post_id" INTEGER NOT NULL, '
               'PRIMARY KEY ("tag_id", "post_id"), '
               'FOREIGN KEY ("tag_id") REFERENCES "tag" ("id"), '
               'FOREIGN KEY ("post_id") REFERENCES "post" ("id"))')
        if IS_MYSQL:
            sql = sql.replace('"', '`')
        self.assertEqual(query, sql)

    def test_get_set_id(self):
        tpt = (TagPostThrough
               .select()
               .join(Tag)
               .switch(TagPostThrough)
               .join(Post)
               .order_by(Tag.tag, Post.title)).get()
        # Sanity check.
        self.assertEqual(tpt.tag.tag, 't1')
        self.assertEqual(tpt.post.title, 'p1')

        tag = Tag.select().where(Tag.tag == 't1').get()
        post = Post.select().where(Post.title == 'p1').get()
        self.assertEqual(tpt._pk, (tag.id, post.id))

        # set_id is a no-op.
        with self.assertRaisesCtx(TypeError):
            tpt._pk = None

        self.assertEqual(tpt._pk, (tag.id, post.id))
        t3 = Tag.get(Tag.tag == 't3')
        p3 = Post.get(Post.title == 'p3')
        tpt._pk = (t3, p3)
        self.assertEqual(tpt.tag.tag, 't3')
        self.assertEqual(tpt.post.title, 'p3')

    def test_querying(self):
        posts = (Post.select()
                 .join(TagPostThrough)
                 .join(Tag)
                 .where(Tag.tag == 't1')
                 .order_by(Post.title))
        self.assertEqual([p.title for p in posts], ['p1', 'p12'])

        tags = (Tag.select()
                .join(TagPostThrough)
                .join(Post)
                .where(Post.title == 'p12')
                .order_by(Tag.tag))
        self.assertEqual([t.tag for t in tags], ['t1', 't2'])

    def test_composite_key_model(self):
        CKM = CompositeKeyModel
        values = [
            ('a', 1, 1.0),
            ('a', 2, 2.0),
            ('b', 1, 1.0),
            ('b', 2, 2.0)]
        c1, c2, c3, c4 = [
            CKM.create(f1=f1, f2=f2, f3=f3) for f1, f2, f3 in values]

        # Update a single row, giving it a new value for `f3`.
        CKM.update(f3=3.0).where((CKM.f1 == 'a') & (CKM.f2 == 2)).execute()

        c = CKM.get((CKM.f1 == 'a') & (CKM.f2 == 2))
        self.assertEqual(c.f3, 3.0)

        # Update the `f3` value and call `save()`, triggering an update.
        c3.f3 = 4.0
        c3.save()

        c = CKM.get((CKM.f1 == 'b') & (CKM.f2 == 1))
        self.assertEqual(c.f3, 4.0)

        # Only 1 row updated.
        query = CKM.select().where(CKM.f3 == 4.0)
        self.assertEqual(query.count(), 1)

        # Unfortunately this does not work since the original value of the
        # PK is lost (and hence cannot be used to update).
        c4.f1 = 'c'
        c4.save()
        self.assertRaises(
            CKM.DoesNotExist,
            lambda: CKM.get((CKM.f1 == 'c') & (CKM.f2 == 2)))

    def test_count_composite_key(self):
        CKM = CompositeKeyModel
        values = [
            ('a', 1, 1.0),
            ('a', 2, 2.0),
            ('b', 1, 1.0),
            ('b', 2, 1.0)]
        for f1, f2, f3 in values:
            CKM.create(f1=f1, f2=f2, f3=f3)

        self.assertEqual(CKM.select().count(), 4)
        self.assertTrue(CKM.select().where(
            (CKM.f1 == 'a') &
            (CKM.f2 == 1)).exists())
        self.assertFalse(CKM.select().where(
            (CKM.f1 == 'a') &
            (CKM.f2 == 3)).exists())

    @requires_models(DIParent, DIChild)
    def test_delete_instance(self):
        p1, p2 = [DIParent.create(title='p%s' % i) for i in range(2)]
        c1 = DIChild.create(data='m1', parent=p1)
        c2 = DIChild.create(data='m2', parent=p1)
        c3 = DIChild.create(data='m3', parent=p2)
        c4 = DIChild.create(data='m4', parent=p2)

        res = c1.delete_instance()
        self.assertEqual(res, 1)
        self.assertEqual(
            [x.data for x in DIChild.select().order_by(DIChild.data)],
            ['m2', 'm3', 'm4'])

        p2.delete_instance(recursive=True)
        self.assertEqual(
            [x.data for x in DIChild.select().order_by(DIChild.data)],
            ['m2'])

    def test_composite_key_inheritance(self):
        class Person(TestModel):
            first = TextField()
            last = TextField()

            class Meta:
                primary_key = CompositeKey('first', 'last')

        self.assertTrue(isinstance(Person._meta.primary_key, CompositeKey))
        self.assertEqual(Person._meta.primary_key.field_names,
                         ('first', 'last'))

        class Employee(Person):
            title = TextField()

        self.assertTrue(isinstance(Employee._meta.primary_key, CompositeKey))
        self.assertEqual(Employee._meta.primary_key.field_names,
                         ('first', 'last'))
        sql = ('CREATE TABLE IF NOT EXISTS "employee" ('
               '"first" TEXT NOT NULL, "last" TEXT NOT NULL, '
               '"title" TEXT NOT NULL, PRIMARY KEY ("first", "last"))')
        if IS_MYSQL:
            sql = sql.replace('"', '`')
        self.assertEqual(Employee._schema._create_table().query(), (sql, []))


class Product(TestModel):
    id = CharField()
    color = CharField()
    class Meta:
        primary_key = CompositeKey('id', 'color')

class Sku(TestModel):
    upc = CharField(primary_key=True)
    product_id = CharField()
    color = CharField()
    class Meta:
        constraints = [SQL('FOREIGN KEY (product_id, color) REFERENCES '
                           'product(id, color)')]

    @hybrid_property
    def product(self):
        if not hasattr(self, '_product'):
            self._product = Product.get((Product.id == self.product_id) &
                                        (Product.color == self.color))
        return self._product

    @product.setter
    def product(self, obj):
        self._product = obj
        self.product_id = obj.id
        self.color = obj.color

    @product.expression
    def product(cls):
        return (Product.id == cls.product_id) & (Product.color == cls.color)


class TestFKCompositePK(ModelTestCase):
    requires = [Product, Sku]

    def test_fk_composite_pk_regression(self):
        Product.insert_many([
            (1, 'red'),
            (1, 'blue'),
            (2, 'red'),
            (2, 'green'),
            (3, 'white')]).execute()
        Sku.insert_many([
            ('1-red', 1, 'red'),
            ('1-blue', 1, 'blue'),
            ('2-red', 2, 'red'),
            ('2-green', 2, 'green'),
            ('3-white', 3, 'white')]).execute()

        query = (Product
                 .select(Product, Sku)
                 .join(Sku, on=Sku.product)
                 .where(Product.color == 'red')
                 .order_by(Product.id, Product.color))
        with self.assertQueryCount(1):
            rows = [(p.id, p.color, p.sku.upc) for p in query]
            self.assertEqual(rows, [
                ('1', 'red', '1-red'),
                ('2', 'red', '2-red')])

        query = (Sku
                 .select(Sku, Product)
                 .join(Product, on=Sku.product)
                 .where(Product.color != 'red')
                 .order_by(Sku.upc))
        with self.assertQueryCount(1):
            rows = [(s.upc, s.product_id, s.color,
                     s.product.id, s.product.color) for s in query]
            self.assertEqual(rows, [
                ('1-blue', '1', 'blue', '1', 'blue'),
                ('2-green', '2', 'green', '2', 'green'),
                ('3-white', '3', 'white', '3', 'white')])

class CPK(TestModel):
    name = TextField()

class CPKFK(TestModel):
    key = CharField()
    cpk = ForeignKeyField(CPK)
    class Meta:
        primary_key = CompositeKey('key', 'cpk')


class TestCompositePKwithFK(ModelTestCase):
    requires = [CPK, CPKFK]

    def test_composite_pk_with_fk(self):
        c1 = CPK.create(name='c1')
        c2 = CPK.create(name='c2')
        CPKFK.create(key='k1', cpk=c1)
        CPKFK.create(key='k2', cpk=c1)
        CPKFK.create(key='k3', cpk=c2)

        query = (CPKFK
                 .select(CPKFK.key, CPK)
                 .join(CPK)
                 .order_by(CPKFK.key, CPK.name))
        with self.assertQueryCount(1):
            self.assertEqual([(r.key, r.cpk.name) for r in query],
                             [('k1', 'c1'), ('k2', 'c1'), ('k3', 'c2')])


# ===========================================================================
# Value conversion, type coercion, and search operators
# ===========================================================================

class TestValueConversion(ModelTestCase):
    """
    Test the conversion of field values using a field's db_value() function.

    It is possible that a field's `db_value()` function may returns a Node
    subclass (e.g. a SQL function). These tests verify and document how such
    conversions are applied in various parts of the query.
    """
    database = get_in_memory_db()
    requires = [UpperModel]

    def test_value_conversion(self):
        # Ensure value is converted on INSERT.
        insert = UpperModel.insert({UpperModel.name: 'huey'})
        self.assertSQL(insert, (
            'INSERT INTO "upper_model" ("name") VALUES (UPPER(?))'), ['huey'])
        uid = insert.execute()

        obj = UpperModel.get(UpperModel.id == uid)
        self.assertEqual(obj.name, 'HUEY')

        # Ensure value is converted on UPDATE.
        update = (UpperModel
                  .update({UpperModel.name: 'zaizee'})
                  .where(UpperModel.id == uid))
        self.assertSQL(update, (
            'UPDATE "upper_model" SET "name" = UPPER(?) '
            'WHERE ("upper_model"."id" = ?)'),
            ['zaizee', uid])
        update.execute()

        # Ensure it works with SELECT (or more generally, WHERE expressions).
        select = UpperModel.select().where(UpperModel.name == 'zaizee')
        self.assertSQL(select, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE ("t1"."name" = UPPER(?))'), ['zaizee'])
        obj = select.get()
        self.assertEqual(obj.name, 'ZAIZEE')

        # Ensure it works with DELETE.
        delete = UpperModel.delete().where(UpperModel.name == 'zaizee')
        self.assertSQL(delete, (
            'DELETE FROM "upper_model" '
            'WHERE ("upper_model"."name" = UPPER(?))'), ['zaizee'])
        self.assertEqual(delete.execute(), 1)

    def test_value_conversion_mixed(self):
        um = UpperModel.create(name='huey')

        # If we apply a function to the field, the conversion is not applied.
        sq = UpperModel.select().where(fn.SUBSTR(UpperModel.name, 1, 1) == 'h')
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE (SUBSTR("t1"."name", ?, ?) = ?)'), [1, 1, 'h'])
        self.assertRaises(UpperModel.DoesNotExist, sq.get)

        # If we encapsulate the object as a value, the conversion is applied.
        sq = UpperModel.select().where(UpperModel.name == Value('huey'))
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE ("t1"."name" = UPPER(?))'), ['huey'])
        self.assertEqual(sq.get().id, um.id)

        # Unless we explicitly pass converter=False.
        sq = UpperModel.select().where(UpperModel.name == Value('huey', False))
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE ("t1"."name" = ?)'), ['huey'])
        self.assertRaises(UpperModel.DoesNotExist, sq.get)

        # If we specify explicit SQL on the rhs, the conversion is not applied.
        sq = UpperModel.select().where(UpperModel.name == SQL('?', ['huey']))
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE ("t1"."name" = ?)'), ['huey'])
        self.assertRaises(UpperModel.DoesNotExist, sq.get)

        # Function arguments are not coerced.
        sq = UpperModel.select().where(UpperModel.name == fn.LOWER('huey'))
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE ("t1"."name" = LOWER(?))'), ['huey'])
        self.assertRaises(UpperModel.DoesNotExist, sq.get)

    def test_value_conversion_query(self):
        um = UpperModel.create(name='huey')
        UM = UpperModel.alias()
        subq = UM.select(UM.name).where(UM.name == 'huey')

        # Select from WHERE ... IN <subquery>.
        query = UpperModel.select().where(UpperModel.name.in_(subq))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE ("t1"."name" IN ('
            'SELECT "t2"."name" FROM "upper_model" AS "t2" '
            'WHERE ("t2"."name" = UPPER(?))))'), ['huey'])
        self.assertEqual(query.get().id, um.id)

        # Join on sub-query.
        query = (UpperModel
                 .select()
                 .join(subq, on=(UpperModel.name == subq.c.name)))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'INNER JOIN (SELECT "t2"."name" FROM "upper_model" AS "t2" '
            'WHERE ("t2"."name" = UPPER(?))) AS "t3" '
            'ON ("t1"."name" = "t3"."name")'), ['huey'])
        row = query.tuples().get()
        self.assertEqual(row, (um.id, 'HUEY'))

    def test_having_clause(self):
        query = (UpperModel
                 .select(UpperModel.name, fn.COUNT(UpperModel.id).alias('ct'))
                 .group_by(UpperModel.name)
                 .having(UpperModel.name == 'huey'))
        self.assertSQL(query, (
            'SELECT "t1"."name", COUNT("t1"."id") AS "ct" '
            'FROM "upper_model" AS "t1" '
            'GROUP BY "t1"."name" '
            'HAVING ("t1"."name" = UPPER(?))'), ['huey'])


class TC(TestModel):
    ifield = IntegerField()
    ffield = FloatField()
    cfield = TextField()
    tfield = TextField()


class TestTypeCoercion(ModelTestCase):
    requires = [TC]

    def test_type_coercion(self):
        t = TC.create(ifield='10', ffield='20.5', cfield=30, tfield=40)
        t_db = TC.get(TC.id == t.id)

        self.assertEqual(t_db.ifield, 10)
        self.assertEqual(t_db.ffield, 20.5)
        self.assertEqual(t_db.cfield, '30')
        self.assertEqual(t_db.tfield, '40')


class JsonField(TextField):
    def db_value(self, value):
        return json.dumps(value) if value is not None else None
    def python_value(self, value):
        return json.loads(value) if value is not None else None


class JM(TestModel):
    key = TextField()
    data = JsonField()


class TestListValueConversion(ModelTestCase):
    requires = [JM]

    def test_list_value_conversion(self):
        jm = JM.create(key='k1', data=['i0', 'i1'])
        jm.key = 'k1-x'
        jm.save()

        jm_db = JM.get(JM.key == 'k1-x')
        self.assertEqual(jm_db.data, ['i0', 'i1'])

        JM.update(data=['i1', 'i2']).execute()
        jm_db = JM.get(JM.key == 'k1-x')
        self.assertEqual(jm_db.data, ['i1', 'i2'])

        jm2 = JM.create(key='k2', data=['i3', 'i4'])

        jm_db.data = ['i1', 'i2', 'i3']
        jm2.data = ['i4', 'i5']

        JM.bulk_update([jm_db, jm2], fields=[JM.key, JM.data])

        jm = JM.get(JM.key == 'k1-x')
        self.assertEqual(jm.data, ['i1', 'i2', 'i3'])
        jm2 = JM.get(JM.key == 'k2')
        self.assertEqual(jm2.data, ['i4', 'i5'])


class BaseNamesTest(ModelTestCase):
    requires = [User]

    def assertNames(self, exp, x):
        query = User.select().where(exp).order_by(User.username)
        self.assertEqual([u.username for u in query], x)


class TestRegexp(BaseNamesTest):
    @skip_if(IS_SQLITE)
    def test_regexp_iregexp(self):
        users = [User.create(username=name) for name in ('n1', 'n2', 'n3')]

        self.assertNames(User.username.regexp('n[1,3]'), ['n1', 'n3'])
        self.assertNames(User.username.regexp('N[1,3]'), [])
        self.assertNames(User.username.iregexp('n[1,3]'), ['n1', 'n3'])
        self.assertNames(User.username.iregexp('N[1,3]'), ['n1', 'n3'])


class TestContains(BaseNamesTest):
    def test_contains_startswith_endswith(self):
        users = [User.create(username=n) for n in ('huey', 'mickey', 'zaizee')]

        self.assertNames(User.username.contains('ey'), ['huey', 'mickey'])
        self.assertNames(User.username.contains('EY'), ['huey', 'mickey'])

        self.assertNames(User.username.startswith('m'), ['mickey'])
        self.assertNames(User.username.startswith('M'), ['mickey'])

        self.assertNames(User.username.endswith('ey'), ['huey', 'mickey'])
        self.assertNames(User.username.endswith('EY'), ['huey', 'mickey'])




# ===========================================================================
# Regressions and edge cases
# ===========================================================================

class ModelTypeField(CharField):
    def db_value(self, value):
        if value is not None:
            return value._meta.name
    def python_value(self, value):
        if value is not None:
            return {'user': User, 'tweet': Tweet}[value]


class MTF(TestModel):
    name = TextField()
    mtype = ModelTypeField()


class TestFieldValueRegression(ModelTestCase):
    requires = [MTF]

    def test_field_value_regression(self):
        u = MTF.create(name='user', mtype=User)
        u_db = MTF.get()

        self.assertEqual(u_db.name, 'user')
        self.assertTrue(u_db.mtype is User)


class CharPK(TestModel):
    id = CharField(primary_key=True)
    name = CharField(unique=True)

    def __str__(self):
        return self.name


class CharFK(TestModel):
    id = IntegerField(primary_key=True)
    cpk = ForeignKeyField(CharPK, field=CharPK.name)


class TestModelConversionRegression(ModelTestCase):
    requires = [CharPK, CharFK]

    def test_model_conversion_regression(self):
        cpks = [CharPK.create(id=str(i), name='u%s' % i) for i in range(3)]

        query = CharPK.select().where(CharPK.id << cpks)
        self.assertEqual(sorted([c.id for c in query]), ['0', '1', '2'])

        query = CharPK.select().where(CharPK.id.in_(list(CharPK.select())))
        self.assertEqual(sorted([c.id for c in query]), ['0', '1', '2'])

    def test_model_conversion_fk_retained(self):
        cpks = [CharPK.create(id=str(i), name='u%s' % i) for i in range(3)]
        cfks = [CharFK.create(id=i + 1, cpk='u%s' % i) for i in range(3)]

        c0, c1, c2 = cpks
        query = CharFK.select().where(CharFK.cpk << [c0, c2])
        self.assertEqual(sorted([f.id for f in query]), [1, 3])


