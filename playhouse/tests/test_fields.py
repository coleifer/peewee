import calendar
import datetime
import decimal
import sys
import time
import uuid

from peewee import MySQLDatabase
from peewee import Param
from peewee import Proxy
from peewee import SqliteDatabase
from peewee import binary_construct
from peewee import sqlite3
from playhouse.tests.base import binary_construct
from playhouse.tests.base import binary_types
from playhouse.tests.base import database_class
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import skip_test_if
from playhouse.tests.base import skip_test_unless
from playhouse.tests.base import skip_if
from playhouse.tests.base import skip_unless
from playhouse.tests.base import test_db
from playhouse.tests.models import *


class TestFieldTypes(ModelTestCase):
    requires = [NullModel, BlobModel]

    _dt = datetime.datetime
    _d = datetime.date
    _t = datetime.time

    field_data = {
        'char_field': ('c1', 'c2', 'c3'),
        'date_field': (
            _d(2010, 1, 1),
            _d(2010, 1, 2),
            _d(2010, 1, 3)),
        'datetime_field': (
            _dt(2010, 1, 1, 0, 0),
            _dt(2010, 1, 2, 0, 0),
            _dt(2010, 1, 3, 0, 0)),
        'decimal_field1': ('1.0', '2.0', '3.0'),
        'fixed_char_field': ('fc1', 'fc2', 'fc3'),
        'float_field': (1.0, 2.0, 3.0),
        'int_field': (1, 2, 3),
        'text_field': ('t1', 't2', 't3'),
        'time_field': (
            _t(1, 0),
            _t(2, 0),
            _t(3, 0)),
        'ts_field': (
            _dt(2010, 1, 1, 0, 0),
            _dt(2010, 1, 2, 0, 0),
            _dt(2010, 1, 3, 0, 0)),
        'ts_field2': (
            _dt(2010, 1, 1, 13, 37, 1, 123456),
            _dt(2010, 1, 2, 13, 37, 1, 123456),
            _dt(2010, 1, 3, 13, 37, 1, 123456)),
    }
    value_table = list(zip(*[(k,) + v for k, v in field_data.items()]))

    def setUp(self):
        super(TestFieldTypes, self).setUp()
        header, values = self.value_table[0], self.value_table[1:]
        for row in values:
            nm = NullModel()
            for i, col in enumerate(row):
                setattr(nm, header[i], col)
            nm.save()

    def assertNM(self, q, exp):
        query = NullModel.select().where(q).order_by(NullModel.id)
        self.assertEqual([nm.char_field for nm in query], exp)

    def test_null_query(self):
        NullModel.delete().execute()
        nm1 = NullModel.create(char_field='nm1')
        nm2 = NullModel.create(char_field='nm2', int_field=1)
        nm3 = NullModel.create(char_field='nm3', int_field=2, float_field=3.0)

        q = ~(NullModel.int_field >> None)
        self.assertNM(q, ['nm2', 'nm3'])

    def test_field_types(self):
        for field, values in self.field_data.items():
            field_obj = getattr(NullModel, field)
            self.assertNM(field_obj < values[2], ['c1', 'c2'])
            self.assertNM(field_obj <= values[1], ['c1', 'c2'])
            self.assertNM(field_obj > values[0], ['c2', 'c3'])
            self.assertNM(field_obj >= values[1], ['c2', 'c3'])
            self.assertNM(field_obj == values[1], ['c2'])
            self.assertNM(field_obj != values[1], ['c1', 'c3'])
            self.assertNM(field_obj << [values[0], values[2]], ['c1', 'c3'])
            self.assertNM(field_obj << [values[1]], ['c2'])

    def test_charfield(self):
        NM = NullModel
        nm = NM.create(char_field=4)
        nm_db = NM.get(NM.id==nm.id)
        self.assertEqual(nm_db.char_field, '4')

        nm_alpha = NM.create(char_field='Alpha')
        nm_bravo = NM.create(char_field='Bravo')

        if isinstance(test_db, SqliteDatabase):
            # Sqlite's sql-dialect uses "*" as case-sensitive lookup wildcard,
            # and pysqlcipher is simply a wrapper around sqlite's engine.
            like_wildcard = '*'
        else:
            like_wildcard = '%'
        like_str = '%sA%s' % (like_wildcard, like_wildcard)
        ilike_str = '%A%'

        case_sens = NM.select(NM.char_field).where(NM.char_field % like_str)
        self.assertEqual([x[0] for x in case_sens.tuples()], ['Alpha'])

        case_insens = NM.select(NM.char_field).where(NM.char_field ** ilike_str)
        self.assertEqual([x[0] for x in case_insens.tuples()], ['Alpha', 'Bravo'])

    def test_fixed_charfield(self):
        NM = NullModel
        nm = NM.create(fixed_char_field=4)
        nm_db = NM.get(NM.id == nm.id)
        self.assertEqual(nm_db.fixed_char_field, '4')

        fc_vals = [obj.fixed_char_field for obj in NM.select().order_by(NM.id)]
        self.assertEqual(fc_vals, ['fc1', 'fc2', 'fc3', '4'])

    def test_intfield(self):
        nm = NullModel.create(int_field='4')
        nm_db = NullModel.get(NullModel.id==nm.id)
        self.assertEqual(nm_db.int_field, 4)

    def test_floatfield(self):
        nm = NullModel.create(float_field='4.2')
        nm_db = NullModel.get(NullModel.id==nm.id)
        self.assertEqual(nm_db.float_field, 4.2)

    def test_decimalfield(self):
        D = decimal.Decimal
        nm = NullModel()
        nm.decimal_field1 = D("3.14159265358979323")
        nm.decimal_field2 = D("100.33")
        nm.save()

        nm_from_db = NullModel.get(NullModel.id==nm.id)
        # sqlite doesn't enforce these constraints properly
        #self.assertEqual(nm_from_db.decimal_field1, decimal.Decimal("3.14159"))
        self.assertEqual(nm_from_db.decimal_field2, D("100.33"))

        class TestDecimalModel(TestModel):
            df1 = DecimalField(decimal_places=2, auto_round=True)
            df2 = DecimalField(decimal_places=2, auto_round=True, rounding=decimal.ROUND_UP)

        f1 = TestDecimalModel.df1.db_value
        f2 = TestDecimalModel.df2.db_value

        self.assertEqual(f1(D('1.2345')), D('1.23'))
        self.assertEqual(f2(D('1.2345')), D('1.24'))

    def test_boolfield(self):
        NullModel.delete().execute()

        nmt = NullModel.create(boolean_field=True, char_field='t')
        nmf = NullModel.create(boolean_field=False, char_field='f')
        nmn = NullModel.create(boolean_field=None, char_field='n')

        self.assertNM(NullModel.boolean_field == True, ['t'])
        self.assertNM(NullModel.boolean_field == False, ['f'])
        self.assertNM(NullModel.boolean_field >> None, ['n'])

    def _time_to_delta(self, t):
        micro = t.microsecond / 1000000.
        return datetime.timedelta(
            seconds=(3600 * t.hour) + (60 * t.minute) + t.second + micro)

    def test_date_and_time_fields(self):
        dt1 = datetime.datetime(2011, 1, 2, 11, 12, 13, 54321)
        dt2 = datetime.datetime(2011, 1, 2, 11, 12, 13)
        d1 = datetime.date(2011, 1, 3)
        t1 = datetime.time(11, 12, 13, 54321)
        t2 = datetime.time(11, 12, 13)
        if isinstance(test_db, MySQLDatabase):
            dt1 = dt1.replace(microsecond=0)
            dt2 = dt2.replace(microsecond=0)
            t1 = t1.replace(microsecond=0)

        nm1 = NullModel.create(datetime_field=dt1, date_field=d1, time_field=t1)
        nm2 = NullModel.create(datetime_field=dt2, time_field=t2)

        nmf1 = NullModel.get(NullModel.id==nm1.id)
        self.assertEqual(nmf1.date_field, d1)
        self.assertEqual(nmf1.datetime_field, dt1)
        self.assertEqual(nmf1.time_field, t1)

        nmf2 = NullModel.get(NullModel.id==nm2.id)
        self.assertEqual(nmf2.datetime_field, dt2)
        self.assertEqual(nmf2.time_field, t2)

    def test_time_field_python_value(self):
        tf = NullModel.time_field
        def T(*a):
            return datetime.time(*a)
        tests = (
            ('01:23:45', T(1, 23, 45)),
            ('01:23', T(1, 23, 0)),
            (T(13, 14, 0), T(13, 14, 0)),
            (datetime.datetime(2015, 1, 1, 0, 59, 0), T(0, 59)),
            ('', ''),
            (None, None),
            (T(0, 0), T(0, 0)),
            (datetime.timedelta(seconds=(4 * 60 * 60) + (20 * 60)), T(4, 20)),
            (datetime.timedelta(seconds=0), T(0, 0)),
        )
        for val, expected in tests:
            self.assertEqual(tf.python_value(val), expected)

    def test_date_as_string(self):
        nm1 = NullModel.create(date_field='2014-01-02')
        nm1_db = NullModel.get(NullModel.id == nm1.id)
        self.assertEqual(nm1_db.date_field, datetime.date(2014, 1, 2))

    def test_various_formats(self):
        class FormatModel(Model):
            dtf = DateTimeField()
            df = DateField()
            tf = TimeField()

        dtf = FormatModel._meta.fields['dtf']
        df = FormatModel._meta.fields['df']
        tf = FormatModel._meta.fields['tf']

        d = datetime.datetime
        self.assertEqual(dtf.python_value('2012-01-01 11:11:11.123456'), d(
            2012, 1, 1, 11, 11, 11, 123456
        ))
        self.assertEqual(dtf.python_value('2012-01-01 11:11:11'), d(
            2012, 1, 1, 11, 11, 11
        ))
        self.assertEqual(dtf.python_value('2012-01-01'), d(
            2012, 1, 1,
        ))
        self.assertEqual(dtf.python_value('2012 01 01'), '2012 01 01')

        d = datetime.date
        self.assertEqual(df.python_value('2012-01-01 11:11:11.123456'), d(
            2012, 1, 1,
        ))
        self.assertEqual(df.python_value('2012-01-01 11:11:11'), d(
            2012, 1, 1,
        ))
        self.assertEqual(df.python_value('2012-01-01'), d(
            2012, 1, 1,
        ))
        self.assertEqual(df.python_value('2012 01 01'), '2012 01 01')

        t = datetime.time
        self.assertEqual(tf.python_value('2012-01-01 11:11:11.123456'), t(
            11, 11, 11, 123456
        ))
        self.assertEqual(tf.python_value('2012-01-01 11:11:11'), t(
            11, 11, 11
        ))
        self.assertEqual(tf.python_value('11:11:11.123456'), t(
            11, 11, 11, 123456
        ))
        self.assertEqual(tf.python_value('11:11:11'), t(
            11, 11, 11
        ))
        self.assertEqual(tf.python_value('11:11'), t(
            11, 11,
        ))
        self.assertEqual(tf.python_value('11:11 AM'), '11:11 AM')

        class CustomFormatsModel(Model):
            dtf = DateTimeField(formats=['%b %d, %Y %I:%M:%S %p'])
            df = DateField(formats=['%b %d, %Y'])
            tf = TimeField(formats=['%I:%M %p'])

        dtf = CustomFormatsModel._meta.fields['dtf']
        df = CustomFormatsModel._meta.fields['df']
        tf = CustomFormatsModel._meta.fields['tf']

        d = datetime.datetime
        self.assertEqual(dtf.python_value('2012-01-01 11:11:11.123456'), '2012-01-01 11:11:11.123456')
        self.assertEqual(dtf.python_value('Jan 1, 2012 11:11:11 PM'), d(
            2012, 1, 1, 23, 11, 11,
        ))

        d = datetime.date
        self.assertEqual(df.python_value('2012-01-01'), '2012-01-01')
        self.assertEqual(df.python_value('Jan 1, 2012'), d(
            2012, 1, 1,
        ))

        t = datetime.time
        self.assertEqual(tf.python_value('11:11:11'), '11:11:11')
        self.assertEqual(tf.python_value('11:11 PM'), t(
            23, 11
        ))

    @skip_test_if(lambda: isinstance(test_db, MySQLDatabase))
    def test_blob_and_binary_field(self):
        byte_count = 256
        data = ''.join(chr(i) for i in range(256))
        blob = BlobModel.create(data=data)

        # pull from db and check binary data
        res = BlobModel.get(BlobModel.id == blob.id)
        self.assertTrue(isinstance(res.data, binary_types))

        self.assertEqual(len(res.data), byte_count)
        db_data = res.data
        binary_data = binary_construct(data)

        if db_data != binary_data and sys.version_info[:3] >= (3, 3, 3):
            db_data = db_data.tobytes()

        self.assertEqual(db_data, binary_data)

        # try querying the blob field
        binary_data = res.data

        # use the string representation
        res = BlobModel.get(BlobModel.data == data)
        self.assertEqual(res.id, blob.id)

        # use the binary representation
        res = BlobModel.get(BlobModel.data == binary_data)
        self.assertEqual(res.id, blob.id)

    def test_between(self):
        field = NullModel.int_field
        self.assertNM(field.between(1, 2), ['c1', 'c2'])
        self.assertNM(field.between(2, 3), ['c2', 'c3'])
        self.assertNM(field.between(5, 300), [])

    def test_in_(self):
        self.assertNM(NullModel.int_field.in_([1, 3]), ['c1', 'c3'])
        self.assertNM(NullModel.int_field.in_([2, 5]), ['c2'])

    def test_contains(self):
        self.assertNM(NullModel.char_field.contains('c2'), ['c2'])
        self.assertNM(NullModel.char_field.contains('c'), ['c1', 'c2', 'c3'])
        self.assertNM(NullModel.char_field.contains('1'), ['c1'])

    def test_startswith(self):
        NullModel.create(char_field='ch1')
        self.assertNM(NullModel.char_field.startswith('c'), ['c1', 'c2', 'c3', 'ch1'])
        self.assertNM(NullModel.char_field.startswith('ch'), ['ch1'])
        self.assertNM(NullModel.char_field.startswith('a'), [])

    def test_endswith(self):
        NullModel.create(char_field='ch1')
        self.assertNM(NullModel.char_field.endswith('1'), ['c1', 'ch1'])
        self.assertNM(NullModel.char_field.endswith('4'), [])

    def test_regexp(self):
        values = [
            'abcdefg',
            'abcd',
            'defg',
            'gij',
            'xx',
        ]
        for value in values:
            NullModel.create(char_field=value)

        def assertValues(regexp, *expected):
            query = NullModel.select().where(
                NullModel.char_field.regexp(regexp)).order_by(NullModel.id)
            values = [nm.char_field for nm in query]
            self.assertEqual(values, list(expected))

        assertValues('^ab', 'abcdefg', 'abcd')
        assertValues('d', 'abcdefg', 'abcd', 'defg')
        assertValues('efg$', 'abcdefg', 'defg')
        assertValues('a.+d', 'abcdefg', 'abcd')

    @skip_test_if(lambda: database_class is MySQLDatabase)
    def test_concat(self):
        NullModel.create(char_field='foo')
        NullModel.create(char_field='bar')

        values = (NullModel
                  .select(
                      NullModel.char_field.concat('-nuggets').alias('nugs'))
                  .order_by(NullModel.id)
                  .dicts())
        self.assertEqual(list(values), [
            {'nugs': 'c1-nuggets'},
            {'nugs': 'c2-nuggets'},
            {'nugs': 'c3-nuggets'},
            {'nugs': 'foo-nuggets'},
            {'nugs': 'bar-nuggets'}])

    def test_field_aliasing(self):
        username = User.username
        user_fk = Blog.user
        blog_pk = Blog.pk

        for i in range(2):
            username = username.clone()
            user_fk = user_fk.clone()
            blog_pk = blog_pk.clone()

            self.assertEqual(username.name, 'username')
            self.assertEqual(username.model_class, User)

            self.assertEqual(user_fk.name, 'user')
            self.assertEqual(user_fk.model_class, Blog)
            self.assertEqual(user_fk.rel_model, User)

            self.assertEqual(blog_pk.name, 'pk')
            self.assertEqual(blog_pk.model_class, Blog)
            self.assertTrue(blog_pk.primary_key)


class TestTimestampField(ModelTestCase):
    requires = [TimestampModel]

    def test_timestamp_field(self):
        dt = datetime.datetime(2016, 1, 2, 11, 12, 13, 654321)
        d_dt = datetime.datetime(2016, 1, 3)
        d = d_dt.date()

        t1 = TimestampModel.create(local_us=dt, utc_ms=dt, local=dt)
        t2 = TimestampModel.create(local_us=d, utc_ms=d, local=d)

        t1_db = TimestampModel.get(TimestampModel.local_us == dt)
        self.assertEqual(t1_db.id, t1.id)
        self.assertEqual(t1_db.local_us, dt)
        self.assertEqual(t1_db.utc_ms, dt.replace(microsecond=654000))
        self.assertEqual(t1_db.local,
                         dt.replace(microsecond=0).replace(second=14))

        t2_db = TimestampModel.get(TimestampModel.utc_ms == d)
        self.assertEqual(t2_db.id, t2.id)
        self.assertEqual(t2_db.local_us, d_dt)
        self.assertEqual(t2_db.utc_ms, d_dt)
        self.assertEqual(t2_db.local, d_dt)

        dt += datetime.timedelta(days=1, seconds=3600)
        dt_us = dt.microsecond / 1000000.
        ts = time.mktime(dt.timetuple()) + dt_us
        utc_ts = calendar.timegm(dt.utctimetuple()) + dt_us
        t3 = TimestampModel.create(local_us=ts, utc_ms=utc_ts, local=ts)

        t3_db = TimestampModel.get(TimestampModel.local == ts)
        self.assertEqual(t3_db.id, t3.id)

        expected = datetime.datetime(2016, 1, 3, 12, 12, 13)
        self.assertEqual(t3_db.local_us, expected.replace(microsecond=654321))
        self.assertEqual(t3_db.utc_ms, expected.replace(microsecond=654000))
        self.assertEqual(t3_db.local, expected.replace(second=14))


class TestBinaryTypeFromDatabase(PeeweeTestCase):
    @skip_test_if(lambda: sys.version_info[0] == 3)
    def test_binary_type_info(self):
        db_proxy = Proxy()
        class A(Model):
            blob_field = BlobField()
            class Meta:
                database = db_proxy

        self.assertTrue(A.blob_field._constructor is binary_construct)

        db = SqliteDatabase(':memory:')
        db_proxy.initialize(db)
        self.assertTrue(A.blob_field._constructor is sqlite3.Binary)

class TestDateTimeExtract(ModelTestCase):
    requires = [NullModel]

    test_datetimes = [
        datetime.datetime(2001, 1, 2, 3, 4, 5),
        datetime.datetime(2002, 2, 3, 4, 5, 6),
        # overlap on year and hour with previous
        datetime.datetime(2002, 3, 4, 4, 6, 7),
    ]
    datetime_parts = ['year', 'month', 'day', 'hour', 'minute', 'second']
    date_parts = datetime_parts[:3]
    time_parts = datetime_parts[3:]

    def setUp(self):
        super(TestDateTimeExtract, self).setUp()

        self.nms = []
        for dt in self.test_datetimes:
            self.nms.append(NullModel.create(
                datetime_field=dt,
                date_field=dt.date(),
                time_field=dt.time()))

    def assertDates(self, sq, expected):
        sq = sq.tuples().order_by(NullModel.id)
        self.assertEqual(list(sq), [(e,) for e in expected])

    def assertPKs(self, sq, idxs):
        sq = sq.tuples().order_by(NullModel.id)
        self.assertEqual(list(sq), [(self.nms[i].id,) for i in idxs])

    def test_extract_datetime(self):
        self.test_extract_date(NullModel.datetime_field)
        self.test_extract_time(NullModel.datetime_field)

    def test_extract_date(self, f=None):
        if f is None:
            f = NullModel.date_field

        self.assertDates(NullModel.select(f.year), [2001, 2002, 2002])
        self.assertDates(NullModel.select(f.month), [1, 2, 3])
        self.assertDates(NullModel.select(f.day), [2, 3, 4])

    def test_extract_time(self, f=None):
        if f is None:
            f = NullModel.time_field

        self.assertDates(NullModel.select(f.hour), [3, 4, 4])
        self.assertDates(NullModel.select(f.minute), [4, 5, 6])
        self.assertDates(NullModel.select(f.second), [5, 6, 7])

    def test_extract_datetime_where(self):
        f = NullModel.datetime_field
        self.test_extract_date_where(f)
        self.test_extract_time_where(f)

        sq = NullModel.select(NullModel.id)
        self.assertPKs(sq.where((f.year == 2002) & (f.month == 2)), [1])
        self.assertPKs(sq.where((f.year == 2002) & (f.hour == 4)), [1, 2])
        self.assertPKs(sq.where((f.year == 2002) & (f.minute == 5)), [1])

    def test_extract_date_where(self, f=None):
        if f is None:
            f = NullModel.date_field

        sq = NullModel.select(NullModel.id)
        self.assertPKs(sq.where(f.year == 2001), [0])
        self.assertPKs(sq.where(f.year == 2002), [1, 2])
        self.assertPKs(sq.where(f.year == 2003), [])

        self.assertPKs(sq.where(f.month == 1), [0])
        self.assertPKs(sq.where(f.month > 1), [1, 2])
        self.assertPKs(sq.where(f.month == 4), [])

        self.assertPKs(sq.where(f.day == 2), [0])
        self.assertPKs(sq.where(f.day > 2), [1, 2])
        self.assertPKs(sq.where(f.day == 5), [])

    def test_extract_time_where(self, f=None):
        if f is None:
            f = NullModel.time_field

        sq = NullModel.select(NullModel.id)
        self.assertPKs(sq.where(f.hour == 3), [0])
        self.assertPKs(sq.where(f.hour == 4), [1, 2])
        self.assertPKs(sq.where(f.hour == 5), [])

        self.assertPKs(sq.where(f.minute == 4), [0])
        self.assertPKs(sq.where(f.minute > 4), [1, 2])
        self.assertPKs(sq.where(f.minute == 7), [])

        self.assertPKs(sq.where(f.second == 5), [0])
        self.assertPKs(sq.where(f.second > 5), [1, 2])
        self.assertPKs(sq.where(f.second == 8), [])


class TestUniqueColumnConstraint(ModelTestCase):
    requires = [UniqueModel, MultiIndexModel]

    def test_unique(self):
        uniq1 = UniqueModel.create(name='a')
        uniq2 = UniqueModel.create(name='b')
        self.assertRaises(Exception, UniqueModel.create, name='a')
        test_db.rollback()

    def test_multi_index(self):
        mi1 = MultiIndexModel.create(f1='a', f2='a', f3='a')
        mi2 = MultiIndexModel.create(f1='b', f2='b', f3='b')
        self.assertRaises(Exception, MultiIndexModel.create, f1='a', f2='a', f3='b')
        test_db.rollback()
        self.assertRaises(Exception, MultiIndexModel.create, f1='b', f2='b', f3='a')
        test_db.rollback()

        mi3 = MultiIndexModel.create(f1='a', f2='b', f3='b')

class TestNonIntegerPrimaryKey(ModelTestCase):
    requires = [NonIntModel, NonIntRelModel]

    def test_non_int_pk(self):
        ni1 = NonIntModel.create(pk='a1', data='ni1')
        self.assertEqual(ni1.pk, 'a1')

        ni2 = NonIntModel(pk='a2', data='ni2')
        ni2.save(force_insert=True)
        self.assertEqual(ni2.pk, 'a2')

        ni2.save()
        self.assertEqual(ni2.pk, 'a2')

        self.assertEqual(NonIntModel.select().count(), 2)

        ni1_db = NonIntModel.get(NonIntModel.pk=='a1')
        self.assertEqual(ni1_db.data, ni1.data)

        self.assertEqual([(x.pk, x.data) for x in NonIntModel.select().order_by(NonIntModel.pk)], [
            ('a1', 'ni1'), ('a2', 'ni2'),
        ])

    def test_non_int_fk(self):
        ni1 = NonIntModel.create(pk='a1', data='ni1')
        ni2 = NonIntModel.create(pk='a2', data='ni2')

        rni11 = NonIntRelModel(non_int_model=ni1)
        rni12 = NonIntRelModel(non_int_model=ni1)
        rni11.save()
        rni12.save()

        self.assertEqual([r.id for r in ni1.nr.order_by(NonIntRelModel.id)], [rni11.id, rni12.id])
        self.assertEqual([r.id for r in ni2.nr.order_by(NonIntRelModel.id)], [])

        rni21 = NonIntRelModel.create(non_int_model=ni2)
        self.assertEqual([r.id for r in ni2.nr.order_by(NonIntRelModel.id)], [rni21.id])

        sq = NonIntRelModel.select().join(NonIntModel).where(NonIntModel.data == 'ni2')
        self.assertEqual([r.id for r in sq], [rni21.id])


class TestPrimaryKeyIsForeignKey(ModelTestCase):
    requires = [Job, JobExecutionRecord, JERRelated]

    def test_primary_foreign_key(self):
        # we have one job, unexecuted, and therefore no executed jobs
        job = Job.create(name='Job One')
        executed_jobs = Job.select().join(JobExecutionRecord)
        self.assertEqual([], list(executed_jobs))

        # after execution, we must have one executed job
        exec_record = JobExecutionRecord.create(job=job, status='success')
        executed_jobs = Job.select().join(JobExecutionRecord)
        self.assertEqual([job], list(executed_jobs))

        # we must not be able to create another execution record for the job
        self.assertRaises(Exception, JobExecutionRecord.create, job=job, status='success')
        test_db.rollback()

    def test_pk_fk_relations(self):
        j1 = Job.create(name='j1')
        j2 = Job.create(name='j2')
        jer1 = JobExecutionRecord.create(job=j1, status='1')
        jer2 = JobExecutionRecord.create(job=j2, status='2')
        jerr1 = JERRelated.create(jer=jer1)
        jerr2 = JERRelated.create(jer=jer2)

        jerr_j1 = [x for x in jer1.jerrelated_set]
        self.assertEqual(jerr_j1, [jerr1])

        jerr_j2 = [x for x in jer2.jerrelated_set]
        self.assertEqual(jerr_j2, [jerr2])

        jerr1_db = JERRelated.get(JERRelated.jer == j1)
        self.assertEqual(jerr1_db, jerr1)


class TestFieldDatabaseColumn(ModelTestCase):
    requires = [DBUser, DBBlog]

    def test_select(self):
        sq = DBUser.select().where(DBUser.username == 'u1')
        self.assertSelect(sq, '"dbuser"."db_user_id", "dbuser"."db_username"', [])
        self.assertWhere(sq, '("dbuser"."db_username" = ?)', ['u1'])

        sq = DBUser.select(DBUser.user_id).join(DBBlog).where(DBBlog.title == 'b1')
        self.assertSelect(sq, '"dbuser"."db_user_id"', [])
        self.assertJoins(sq, ['INNER JOIN "dbblog" AS dbblog ON ("dbuser"."db_user_id" = "dbblog"."db_user")'])
        self.assertWhere(sq, '("dbblog"."db_title" = ?)', ['b1'])

    def test_db_column(self):
        u1 = DBUser.create(username='u1')
        u2 = DBUser.create(username='u2')
        u2_db = DBUser.get(DBUser.user_id==u2._get_pk_value())
        self.assertEqual(u2_db.username, 'u2')

        b1 = DBBlog.create(user=u1, title='b1')
        b2 = DBBlog.create(user=u2, title='b2')
        b2_db = DBBlog.get(DBBlog.blog_id==b2._get_pk_value())
        self.assertEqual(b2_db.user.user_id, u2.user_id)
        self.assertEqual(b2_db.title, 'b2')

        self.assertEqual([b.title for b in u2.dbblog_set], ['b2'])

class _SqliteDateTestHelper(PeeweeTestCase):
    datetimes = [
        datetime.datetime(2000, 1, 2, 3, 4, 5),
        datetime.datetime(2000, 2, 3, 4, 5, 6),
    ]

    def create_date_model(self, date_fn):
        dp_db = SqliteDatabase(':memory:')
        class SqDp(Model):
            datetime_field = DateTimeField()
            date_field = DateField()
            time_field = TimeField()
            null_datetime_field = DateTimeField(null=True)

            class Meta:
                database = dp_db

            @classmethod
            def date_query(cls, field, part):
                return (SqDp
                        .select(date_fn(field, part))
                        .tuples()
                        .order_by(SqDp.id))

        SqDp.create_table()

        for d in self.datetimes:
            SqDp.create(datetime_field=d, date_field=d.date(),
                        time_field=d.time())

        return SqDp

class TestSQLiteDatePart(_SqliteDateTestHelper):
    def test_sqlite_date_part(self):
        date_fn = lambda field, part: fn.date_part(part, field)
        SqDp = self.create_date_model(date_fn)

        for part in ('year', 'month', 'day', 'hour', 'minute', 'second'):
            for i, dp in enumerate(SqDp.date_query(SqDp.datetime_field, part)):
                self.assertEqual(dp[0], getattr(self.datetimes[i], part))

        for part in ('year', 'month', 'day'):
            for i, dp in enumerate(SqDp.date_query(SqDp.date_field, part)):
                self.assertEqual(dp[0], getattr(self.datetimes[i], part))

        for part in ('hour', 'minute', 'second'):
            for i, dp in enumerate(SqDp.date_query(SqDp.time_field, part)):
                self.assertEqual(dp[0], getattr(self.datetimes[i], part))

        # ensure that the where clause works
        query = SqDp.select().where(fn.date_part('year', SqDp.datetime_field) == 2000)
        self.assertEqual(query.count(), 2)

        query = SqDp.select().where(fn.date_part('month', SqDp.datetime_field) == 1)
        self.assertEqual(query.count(), 1)
        query = SqDp.select().where(fn.date_part('month', SqDp.datetime_field) == 3)
        self.assertEqual(query.count(), 0)

        null_sqdp = SqDp.create(
            datetime_field=datetime.datetime.now(),
            date_field=datetime.date.today(),
            time_field=datetime.time(0, 0),
            null_datetime_field=datetime.datetime(2014, 1, 1))
        query = SqDp.select().where(
            fn.date_part('year', SqDp.null_datetime_field) == 2014)
        self.assertEqual(query.count(), 1)
        self.assertEqual(list(query), [null_sqdp])


class TestSQLiteDateTrunc(_SqliteDateTestHelper):
    def test_sqlite_date_trunc(self):
        date_fn = lambda field, part: fn.date_trunc(part, field)
        SqDp = self.create_date_model(date_fn)

        def assertQuery(field, part, expected):
            values = SqDp.date_query(field, part)
            self.assertEqual([r[0] for r in values], expected)

        assertQuery(SqDp.datetime_field, 'year', ['2000', '2000'])
        assertQuery(SqDp.datetime_field, 'month', ['2000-01', '2000-02'])
        assertQuery(SqDp.datetime_field, 'day', ['2000-01-02', '2000-02-03'])
        assertQuery(SqDp.datetime_field, 'hour', [
            '2000-01-02 03', '2000-02-03 04'])
        assertQuery(SqDp.datetime_field, 'minute', [
            '2000-01-02 03:04', '2000-02-03 04:05'])
        assertQuery(SqDp.datetime_field, 'second', [
            '2000-01-02 03:04:05', '2000-02-03 04:05:06'])

        null_sqdp = SqDp.create(
            datetime_field=datetime.datetime.now(),
            date_field=datetime.date.today(),
            time_field=datetime.time(0, 0),
            null_datetime_field=datetime.datetime(2014, 1, 1))
        assertQuery(SqDp.null_datetime_field, 'year', [None, None, '2014'])


class TestCheckConstraints(ModelTestCase):
    requires = [CheckModel]

    def test_check_constraint(self):
        CheckModel.create(value=1)
        if isinstance(test_db, MySQLDatabase):
            # MySQL silently ignores all check constraints.
            CheckModel.create(value=0)
        else:
            with test_db.transaction() as txn:
                self.assertRaises(IntegrityError, CheckModel.create, value=0)
                txn.rollback()


@skip_if(lambda: isinstance(test_db, MySQLDatabase))
class TestServerDefaults(ModelTestCase):
    requires = [ServerDefaultModel]

    def test_server_default(self):
        sd = ServerDefaultModel.create(name='baz')
        sd_db = ServerDefaultModel.get(ServerDefaultModel.id == sd.id)

        self.assertEqual(sd_db.name, 'baz')
        self.assertIsNotNone(sd_db.timestamp)

        sd2 = ServerDefaultModel.create(
            timestamp=datetime.datetime(2015, 1, 2, 3, 4))
        sd2_db = ServerDefaultModel.get(ServerDefaultModel.id == sd2.id)

        self.assertEqual(sd2_db.name, 'foo')
        self.assertEqual(sd2_db.timestamp, datetime.datetime(2015, 1, 2, 3, 4))


class TestUUIDField(ModelTestCase):
    requires = [
        TestingID,
        UUIDData,
        UUIDRelatedModel,
    ]

    def test_uuid(self):
        uuid_str = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
        uuid_obj = uuid.UUID(uuid_str)

        t1 = TestingID.create(uniq=uuid_obj)
        t1_db = TestingID.get(TestingID.uniq == uuid_str)
        self.assertEqual(t1, t1_db)

        t2 = TestingID.get(TestingID.uniq == uuid_obj)
        self.assertEqual(t1, t2)

    def test_uuid_casting(self):
        uuid_obj = uuid.UUID('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11')
        uuid_str = uuid_obj.hex
        uuid_str_short = uuid_str.replace("-", "")

        t1 = TestingID.create(uniq=uuid_obj)
        t1_db = TestingID.get(TestingID.uniq == uuid_str)
        self.assertEqual(t1_db.uniq, uuid_obj)
        t1_db = TestingID.get(TestingID.uniq == uuid_str_short)
        self.assertEqual(t1_db.uniq, uuid_obj)

        t1 = TestingID.create(uniq=uuid_str)
        t1_db = TestingID.get(TestingID.uniq == uuid_str)
        self.assertEqual(t1_db.uniq, uuid_obj)
        t1_db = TestingID.get(TestingID.uniq == uuid_str_short)
        self.assertEqual(t1_db.uniq, uuid_obj)

        t1 = TestingID.create(uniq=uuid_str_short)
        t1_db = TestingID.get(TestingID.uniq == uuid_str)
        self.assertEqual(t1_db.uniq, uuid_obj)
        t1_db = TestingID.get(TestingID.uniq == uuid_str_short)
        self.assertEqual(t1_db.uniq, uuid_obj)

    def test_uuid_foreign_keys(self):
        data_a = UUIDData.create(id=uuid.uuid4(), data='a')
        data_b = UUIDData.create(id=uuid.uuid4(), data='b')

        rel_a1 = UUIDRelatedModel.create(data=data_a, value=1)
        rel_a2 = UUIDRelatedModel.create(data=data_a, value=2)
        rel_none = UUIDRelatedModel.create(data=None, value=3)

        db_a = UUIDData.get(UUIDData.id == data_a.id)
        self.assertEqual(db_a.id, data_a.id)
        self.assertEqual(db_a.data, 'a')

        values = [rm.value
                  for rm in db_a.related_models.order_by(UUIDRelatedModel.id)]
        self.assertEqual(values, [1, 2])

        rnone = UUIDRelatedModel.get(UUIDRelatedModel.data >> None)
        self.assertEqual(rnone.value, 3)

        ra = (UUIDRelatedModel
              .select()
              .where(UUIDRelatedModel.data == data_a)
              .order_by(UUIDRelatedModel.value.desc()))
        self.assertEqual([r.value for r in ra], [2, 1])

    def test_prefetch_regression(self):
        a = UUIDData.create(id=uuid.uuid4(), data='a')
        b = UUIDData.create(id=uuid.uuid4(), data='b')
        for i in range(5):
            for u in [a, b]:
                UUIDRelatedModel.create(data=u, value=i)

        with self.assertQueryCount(2):
            query = prefetch(
                UUIDData.select().order_by(UUIDData.data),
                UUIDRelatedModel.select().where(UUIDRelatedModel.value < 3))

            accum = []
            for item in query:
                accum.append((item.data, [
                    rel.value for rel in item.related_models_prefetch]))

            self.assertEqual(accum, [
                ('a', [0, 1, 2]),
                ('b', [0, 1, 2]),
            ])


@skip_unless(lambda: isinstance(test_db, SqliteDatabase))
class TestForeignKeyConversion(ModelTestCase):
    requires = [UIntModel, UIntRelModel]

    def test_fk_conversion(self):
        u1 = UIntModel.create(data=1337)
        u2 = UIntModel.create(data=(1 << 31) + 1000)

        u1_db = UIntModel.get(UIntModel.data == 1337)
        self.assertEqual(u1_db.id, u1.id)
        u2_db = UIntModel.get(UIntModel.data == (1 << 31) + 1000)
        self.assertEqual(u2_db.id, u2.id)

        ur1 = UIntRelModel.create(uint_model=u1)
        ur2 = UIntRelModel.create(uint_model=u2)

        self.assertEqual(ur1.uint_model_id, 1337)
        self.assertEqual(ur2.uint_model_id, (1 << 31) + 1000)

        ur1_db = UIntRelModel.get(UIntRelModel.id == ur1.id)
        ur2_db = UIntRelModel.get(UIntRelModel.id == ur2.id)

        self.assertEqual(ur1_db.uint_model.id, u1.id)
        self.assertEqual(ur2_db.uint_model.id, u2.id)
