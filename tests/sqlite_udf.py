import datetime
import json
import random

try:
    import vtfunc
except ImportError:
    vtfunc = None

from peewee import *
from peewee import sqlite3
from playhouse.sqlite_ext import SqliteExtDatabase
from playhouse.sqlite_udf import register_all

from .base import ModelTestCase
from .base import TestModel
from .base import db_loader
from .base import skip_case_unless
from .base import skip_if
from .base import skip_unless
try:
    from playhouse import _sqlite_udf as cython_udf
except ImportError:
    cython_udf = None


def requires_cython(method):
    return skip_unless(lambda: cython_udf is not None)(method)

def requires_vtfunc(testcase):
    return skip_case_unless(lambda: vtfunc is not None)(testcase)


database = db_loader('sqlite')
register_all(database)


class User(TestModel):
    username = TextField()


class APIResponse(TestModel):
    url = TextField(default='')
    data = TextField(default='')
    timestamp = DateTimeField(default=datetime.datetime.now)


class Generic(TestModel):
    value = IntegerField(default=0)
    x = Field(null=True)


MODELS = [User, APIResponse, Generic]


class FixedOffset(datetime.tzinfo):
    def __init__(self, offset, name, dstoffset=42):
        if isinstance(offset, int):
            offset = datetime.timedelta(minutes=offset)
        if isinstance(dstoffset, int):
            dstoffset = datetime.timedelta(minutes=dstoffset)
        self.__offset = offset
        self.__name = name
        self.__dstoffset = dstoffset

    def utcoffset(self, dt):
        return self.__offset

    def tzname(self, dt):
        return self.__name

    def dst(self, dt):
        return self.__dstoffset


class BaseTestUDF(ModelTestCase):
    database = database

    def sql1(self, sql, *params):
        cursor = self.database.execute_sql(sql, params)
        return cursor.fetchone()[0]


class TestAggregates(BaseTestUDF):
    requires = [Generic]

    def _store_values(self, *values):
        with self.database.atomic():
            for value in values:
                Generic.create(x=value)

    def mts(self, seconds):
        return (datetime.datetime(2015, 1, 1) +
                datetime.timedelta(seconds=seconds))

    def test_min_avg_tdiff(self):
        self.assertEqual(self.sql1('select mintdiff(x) from generic;'), None)
        self.assertEqual(self.sql1('select avgtdiff(x) from generic;'), None)

        self._store_values(self.mts(10))
        self.assertEqual(self.sql1('select mintdiff(x) from generic;'), None)
        self.assertEqual(self.sql1('select avgtdiff(x) from generic;'), 0)

        self._store_values(self.mts(15))
        self.assertEqual(self.sql1('select mintdiff(x) from generic;'), 5)
        self.assertEqual(self.sql1('select avgtdiff(x) from generic;'), 5)

        self._store_values(
            self.mts(22),
            self.mts(52),
            self.mts(18),
            self.mts(41),
            self.mts(2),
            self.mts(33))
        self.assertEqual(self.sql1('select mintdiff(x) from generic;'), 3)
        self.assertEqual(
            round(self.sql1('select avgtdiff(x) from generic;'), 1),
            7.1)

        self._store_values(self.mts(22))
        self.assertEqual(self.sql1('select mintdiff(x) from generic;'), 0)

    def test_duration(self):
        self.assertEqual(self.sql1('select duration(x) from generic;'), None)

        self._store_values(self.mts(10))
        self.assertEqual(self.sql1('select duration(x) from generic;'), 0)

        self._store_values(self.mts(15))
        self.assertEqual(self.sql1('select duration(x) from generic;'), 5)

        self._store_values(
            self.mts(22),
            self.mts(11),
            self.mts(52),
            self.mts(18),
            self.mts(41),
            self.mts(2),
            self.mts(33))
        self.assertEqual(self.sql1('select duration(x) from generic;'), 50)

    @requires_cython
    def test_median(self):
        self.assertEqual(self.sql1('select median(x) from generic;'), None)

        self._store_values(1)
        self.assertEqual(self.sql1('select median(x) from generic;'), 1)

        self._store_values(3, 6, 6, 6, 7, 7, 7, 7, 12, 12, 17)
        self.assertEqual(self.sql1('select median(x) from generic;'), 7)

        Generic.delete().execute()
        self._store_values(9, 2, 2, 3, 3, 1)
        self.assertEqual(self.sql1('select median(x) from generic;'), 3)

        Generic.delete().execute()
        self._store_values(4, 4, 1, 8, 2, 2, 5, 8, 1)
        self.assertEqual(self.sql1('select median(x) from generic;'), 4)

    def test_mode(self):
        self.assertEqual(self.sql1('select mode(x) from generic;'), None)

        self._store_values(1)
        self.assertEqual(self.sql1('select mode(x) from generic;'), 1)

        self._store_values(4, 5, 6, 1, 3, 4, 1, 4, 9, 3, 4)
        self.assertEqual(self.sql1('select mode(x) from generic;'), 4)

    def test_ranges(self):
        self.assertEqual(self.sql1('select minrange(x) from generic'), None)
        self.assertEqual(self.sql1('select avgrange(x) from generic'), None)
        self.assertEqual(self.sql1('select range(x) from generic'), None)

        self._store_values(1)
        self.assertEqual(self.sql1('select minrange(x) from generic'), 0)
        self.assertEqual(self.sql1('select avgrange(x) from generic'), 0)
        self.assertEqual(self.sql1('select range(x) from generic'), 0)

        self._store_values(4, 8, 13, 19)
        self.assertEqual(self.sql1('select minrange(x) from generic'), 3)
        self.assertEqual(self.sql1('select avgrange(x) from generic'), 4.5)
        self.assertEqual(self.sql1('select range(x) from generic'), 18)

        Generic.delete().execute()
        self._store_values(19, 4, 5, 20, 5, 8)
        self.assertEqual(self.sql1('select range(x) from generic'), 16)


class TestScalarFunctions(BaseTestUDF):
    requires = MODELS

    def test_if_then_else(self):
        for i in range(4):
            User.create(username='u%d' % (i + 1))
        with self.assertQueryCount(1):
            query = (User
                     .select(
                         User.username,
                         fn.if_then_else(
                             User.username << ['u1', 'u2'],
                             'one or two',
                             'other').alias('name_type'))
                     .order_by(User.id))
            self.assertEqual([row.name_type for row in query], [
                'one or two',
                'one or two',
                'other',
                'other'])

    def test_strip_tz(self):
        dt = datetime.datetime(2015, 1, 1, 12, 0)
        # 13 hours, 37 minutes.
        dt_tz = dt.replace(tzinfo=FixedOffset(13 * 60 + 37, 'US/LFK'))
        api_dt = APIResponse.create(timestamp=dt)
        api_dt_tz = APIResponse.create(timestamp=dt_tz)

        # Re-fetch from the database.
        api_dt_db = APIResponse.get(APIResponse.id == api_dt.id)
        api_dt_tz_db = APIResponse.get(APIResponse.id == api_dt_tz.id)

        # Assert the timezone is present, first of all, and that they were
        # stored in the database.
        self.assertEqual(api_dt_db.timestamp, dt)

        query = (APIResponse
                 .select(
                     APIResponse.id,
                     fn.strip_tz(APIResponse.timestamp).alias('ts'))
                 .order_by(APIResponse.id))
        ts, ts_tz = query[:]

        self.assertEqual(ts.ts, dt)
        self.assertEqual(ts_tz.ts, dt)

    def test_human_delta(self):
        values = [0, 1, 30, 300, 3600, 7530, 300000]
        for value in values:
            Generic.create(value=value)

        delta = fn.human_delta(Generic.value).coerce(False)
        query = (Generic
                 .select(
                     Generic.value,
                     delta.alias('delta'))
                 .order_by(Generic.value))
        results = query.tuples()[:]
        self.assertEqual(results, [
            (0, '0 seconds'),
            (1, '1 second'),
            (30, '30 seconds'),
            (300, '5 minutes'),
            (3600, '1 hour'),
            (7530, '2 hours, 5 minutes, 30 seconds'),
            (300000, '3 days, 11 hours, 20 minutes'),
        ])

    def test_file_ext(self):
        data = (
            ('test.py', '.py'),
            ('test.x.py', '.py'),
            ('test', ''),
            ('test.', '.'),
            ('/foo.bar/test/nug.py', '.py'),
            ('/foo.bar/test/nug', ''),
        )
        for filename, ext in data:
            res = self.sql1('SELECT file_ext(?)', filename)
            self.assertEqual(res, ext)

    def test_gz(self):
        random.seed(1)
        A = ord('A')
        z = ord('z')
        with self.database.atomic():
            def randstr(l):
                return ''.join([
                    chr(random.randint(A, z))
                    for _ in range(l)])

            data = (
                'a',
                'a' * 1024,
                randstr(1024),
                randstr(4096),
                randstr(1024 * 64))
            for s in data:
                compressed = self.sql1('select gzip(?)', s)
                decompressed = self.sql1('select gunzip(?)', compressed)
                self.assertEqual(decompressed.decode('utf-8'), s)

    def test_hostname(self):
        r = json.dumps({'success': True})
        data = (
            ('http://charlesleifer.com/api/', r),
            ('https://a.charlesleifer.com/api/foo', r),
            ('www.nugget.com', r),
            ('nugz.com', r),
            ('http://a.b.c.peewee/foo', r),
            ('http://charlesleifer.com/xx', r),
            ('https://charlesleifer.com/xx', r),
        )
        with self.database.atomic():
            for url, response in data:
                APIResponse.create(url=url, data=data)

        with self.assertQueryCount(1):
            query = (APIResponse
                     .select(
                         fn.hostname(APIResponse.url).alias('host'),
                         fn.COUNT(APIResponse.id).alias('count'))
                     .group_by(fn.hostname(APIResponse.url))
                     .order_by(
                         fn.COUNT(APIResponse.id).desc(),
                         fn.hostname(APIResponse.url)))
            results = query.tuples()[:]

        self.assertEqual(results, [
            ('charlesleifer.com', 3),
            ('', 2),
            ('a.b.c.peewee', 1),
            ('a.charlesleifer.com', 1)])

    @skip_if(sqlite3.sqlite_version_info < (3, 9))
    def test_toggle(self):
        self.assertEqual(self.sql1('select toggle(?)', 'foo'), 1)
        self.assertEqual(self.sql1('select toggle(?)', 'bar'), 1)
        self.assertEqual(self.sql1('select toggle(?)', 'foo'), 0)
        self.assertEqual(self.sql1('select toggle(?)', 'foo'), 1)
        self.assertEqual(self.sql1('select toggle(?)', 'bar'), 0)

        self.assertEqual(self.sql1('select clear_toggles()'), None)
        self.assertEqual(self.sql1('select toggle(?)', 'foo'), 1)

    def test_setting(self):
        self.assertEqual(self.sql1('select setting(?, ?)', 'k1', 'v1'), 'v1')
        self.assertEqual(self.sql1('select setting(?, ?)', 'k2', 'v2'), 'v2')

        self.assertEqual(self.sql1('select setting(?)', 'k1'), 'v1')

        self.assertEqual(self.sql1('select setting(?, ?)', 'k2', 'v2-x'), 'v2-x')
        self.assertEqual(self.sql1('select setting(?)', 'k2'), 'v2-x')

        self.assertEqual(self.sql1('select setting(?)', 'kx'), None)

        self.assertEqual(self.sql1('select clear_settings()'), None)
        self.assertEqual(self.sql1('select setting(?)', 'k1'), None)

    def test_random_range(self):
        vals = ((1, 10), (1, 100), (0, 2), (1, 5, 2))
        results = []
        for params in vals:
            random.seed(1)
            results.append(random.randrange(*params))

        for params, expected in zip(vals, results):
            random.seed(1)
            if len(params) == 3:
                pstr = '?, ?, ?'
            else:
                pstr = '?, ?'
            self.assertEqual(
                self.sql1('select randomrange(%s)' % pstr, *params),
                expected)

    def test_sqrt(self):
        self.assertEqual(self.sql1('select sqrt(?)', 4), 2)
        self.assertEqual(round(self.sql1('select sqrt(?)', 2), 2), 1.41)

    def test_tonumber(self):
        data = (
            ('123', 123),
            ('1.23', 1.23),
            ('1e4', 10000),
            ('-10', -10),
            ('x', None),
            ('13d', None),
        )
        for inp, outp in data:
            self.assertEqual(self.sql1('select tonumber(?)', inp), outp)

    @requires_cython
    def test_leven(self):
        self.assertEqual(
            self.sql1('select levenshtein_dist(?, ?)', 'abc', 'ba'),
            2)

        self.assertEqual(
            self.sql1('select levenshtein_dist(?, ?)', 'abcde', 'eba'),
            4)

        self.assertEqual(
            self.sql1('select levenshtein_dist(?, ?)', 'abcde', 'abcde'),
            0)

    @requires_cython
    def test_str_dist(self):
        self.assertEqual(
            self.sql1('select str_dist(?, ?)', 'abc', 'ba'),
            3)

        self.assertEqual(
            self.sql1('select str_dist(?, ?)', 'abcde', 'eba'),
            6)

        self.assertEqual(
            self.sql1('select str_dist(?, ?)', 'abcde', 'abcde'),
            0)

    def test_substr_count(self):
        self.assertEqual(
            self.sql1('select substr_count(?, ?)', 'foo bar baz', 'a'), 2)
        self.assertEqual(
            self.sql1('select substr_count(?, ?)', 'foo bor baz', 'o'), 3)
        self.assertEqual(
            self.sql1('select substr_count(?, ?)', 'foodooboope', 'oo'), 3)
        self.assertEqual(self.sql1('select substr_count(?, ?)', 'xx', ''), 0)
        self.assertEqual(self.sql1('select substr_count(?, ?)', '', ''), 0)

    def test_strip_chars(self):
        self.assertEqual(
            self.sql1('select strip_chars(?, ?)', '  hey foo ', ' '),
            'hey foo')


@requires_vtfunc
class TestVirtualTableFunctions(ModelTestCase):
    database = database
    requires = MODELS

    def sqln(self, sql, *p):
        cursor = self.database.execute_sql(sql, p)
        return cursor.fetchall()

    def test_regex_search(self):
        usernames = [
            'charlie',
            'hu3y17',
            'zaizee2012',
            '1234.56789',
            'hurr durr']
        for username in usernames:
            User.create(username=username)

        rgx = '[0-9]+'
        results = self.sqln(
            ('SELECT user.username, regex_search.match '
             'FROM user, regex_search(?, user.username) '
             'ORDER BY regex_search.match'),
            rgx)
        self.assertEqual([row for row in results], [
            ('1234.56789', '1234'),
            ('hu3y17', '17'),
            ('zaizee2012', '2012'),
            ('hu3y17', '3'),
            ('1234.56789', '56789'),
        ])

    def test_date_series(self):
        ONE_DAY = 86400
        def assertValues(start, stop, step_seconds, expected):
            results = self.sqln('select * from date_series(?, ?, ?)',
                                start, stop, step_seconds)
            self.assertEqual(results, expected)

        assertValues('2015-01-01', '2015-01-05', 86400, [
            ('2015-01-01',),
            ('2015-01-02',),
            ('2015-01-03',),
            ('2015-01-04',),
            ('2015-01-05',),
        ])

        assertValues('2015-01-01', '2015-01-05', 86400 / 2, [
            ('2015-01-01 00:00:00',),
            ('2015-01-01 12:00:00',),
            ('2015-01-02 00:00:00',),
            ('2015-01-02 12:00:00',),
            ('2015-01-03 00:00:00',),
            ('2015-01-03 12:00:00',),
            ('2015-01-04 00:00:00',),
            ('2015-01-04 12:00:00',),
            ('2015-01-05 00:00:00',),
        ])

        assertValues('14:20:15', '14:24', 30, [
            ('14:20:15',),
            ('14:20:45',),
            ('14:21:15',),
            ('14:21:45',),
            ('14:22:15',),
            ('14:22:45',),
            ('14:23:15',),
            ('14:23:45',),
        ])
