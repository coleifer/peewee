#coding:utf-8
import datetime
import json
import os
import unittest
import uuid
import sys

import psycopg2

from peewee import create_model_tables
from peewee import drop_model_tables
from peewee import print_
from peewee import UUIDField
from playhouse.postgres_ext import *


TEST_VERBOSITY = int(os.environ.get('PEEWEE_TEST_VERBOSITY') or 1)
test_db = PostgresqlExtDatabase('peewee_test', user='postgres')
test_ss_db = PostgresqlExtDatabase(
    'peewee_test',
    server_side_cursors=True,
    user='postgres')


class BaseModel(Model):
    class Meta:
        database = test_db

class Testing(BaseModel):
    name = CharField()
    data = HStoreField()

    class Meta:
        order_by = ('name',)

try:
    class TestingJson(BaseModel):
        data = JSONField()
except:
    TestingJson = None

class TestingID(BaseModel):
    uniq = UUIDField()

class UUIDData(BaseModel):
    id = UUIDField(primary_key=True)
    data = CharField()

class UUIDRelatedModel(BaseModel):
    data = ForeignKeyField(UUIDData, null=True, related_name='related_models')
    value = IntegerField(default=0)

class TZModel(BaseModel):
    dt = DateTimeTZField()

class ArrayModel(BaseModel):
    tags = ArrayField(CharField)
    ints = ArrayField(IntegerField, dimensions=2)

class SSCursorModel(Model):
    data = CharField()

    class Meta:
        database = test_ss_db

class NormalModel(BaseModel):
    data = CharField()

class FTSModel(BaseModel):
    title = CharField()
    data = TextField()
    fts_data = TSVectorField()

MODELS = [
    Testing,
    TestingID,
    UUIDData,
    UUIDRelatedModel,
    ArrayModel,
    FTSModel,
]

class BasePostgresqlExtTestCase(unittest.TestCase):
    def setUp(self):
        drop_model_tables(MODELS, fail_silently=True)
        create_model_tables(MODELS)


class TestUUIDField(BasePostgresqlExtTestCase):
    def test_uuid(self):
        uuid_str = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
        uuid_obj = uuid.UUID(uuid_str)

        t1 = TestingID.create(uniq=uuid_obj)
        t1_db = TestingID.get(TestingID.uniq == uuid_str)
        self.assertEqual(t1, t1_db)

        t2 = TestingID.get(TestingID.uniq == uuid_obj)
        self.assertEqual(t1, t2)

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


class TestTZField(BasePostgresqlExtTestCase):
    def test_tz_field(self):
        TZModel.drop_table(True)
        TZModel.create_table()

        test_db.execute_sql('set time zone "us/central";')

        dt = datetime.datetime.now()
        tz = TZModel.create(dt=dt)
        self.assertTrue(tz.dt.tzinfo is None)

        tz = TZModel.get(TZModel.id == tz.id)
        self.assertFalse(tz.dt.tzinfo is None)


class TestHStoreField(BasePostgresqlExtTestCase):
    def setUp(self):
        super(TestHStoreField, self).setUp()
        self.t1 = None
        self.t2 = None

    def create(self):
        self.t1 = Testing.create(name='t1', data={'k1': 'v1', 'k2': 'v2'})
        self.t2 = Testing.create(name='t2', data={'k2': 'v2', 'k3': 'v3'})

    def test_hstore_storage(self):
        self.create()
        self.assertEqual(Testing.get(name='t1').data, {'k1': 'v1', 'k2': 'v2'})
        self.assertEqual(Testing.get(name='t2').data, {'k2': 'v2', 'k3': 'v3'})

        self.t1.data = {'k4': 'v4'}
        self.t1.save()
        self.assertEqual(Testing.get(name='t1').data, {'k4': 'v4'})

        t = Testing.create(name='t3', data={})
        self.assertEqual(Testing.get(name='t3').data, {})

    def test_hstore_selecting(self):
        self.create()

        sq = Testing.select(Testing.name, Testing.data.keys().alias('keys'))
        self.assertEqual([(x.name, sorted(x.keys)) for x in sq], [
            ('t1', ['k1', 'k2']), ('t2', ['k2', 'k3'])
        ])

        sq = Testing.select(Testing.name, Testing.data.values().alias('vals'))
        self.assertEqual([(x.name, sorted(x.vals)) for x in sq], [
            ('t1', ['v1', 'v2']), ('t2', ['v2', 'v3'])
        ])

        sq = Testing.select(Testing.name, Testing.data.items().alias('mtx'))
        self.assertEqual([(x.name, sorted(x.mtx)) for x in sq], [
            ('t1', [['k1', 'v1'], ['k2', 'v2']]),
            ('t2', [['k2', 'v2'], ['k3', 'v3']]),
        ])

        sq = Testing.select(Testing.name, Testing.data.slice('k2', 'k3').alias('kz'))
        self.assertEqual([(x.name, x.kz) for x in sq], [
            ('t1', {'k2': 'v2'}),
            ('t2', {'k2': 'v2', 'k3': 'v3'}),
        ])

        sq = Testing.select(Testing.name, Testing.data.slice('k4').alias('kz'))
        self.assertEqual([(x.name, x.kz) for x in sq], [
            ('t1', {}),
            ('t2', {}),
        ])

        sq = Testing.select(Testing.name, Testing.data.exists('k3').alias('ke'))
        self.assertEqual([(x.name, x.ke) for x in sq], [
            ('t1', False),
            ('t2', True),
        ])

        sq = Testing.select(Testing.name, Testing.data.defined('k3').alias('ke'))
        self.assertEqual([(x.name, x.ke) for x in sq], [
            ('t1', False),
            ('t2', True),
        ])

        sq = Testing.select(Testing.name, Testing.data['k1'].alias('k1'))
        self.assertEqual([(x.name, x.k1) for x in sq], [
            ('t1', 'v1'),
            ('t2', None),
        ])

        sq = Testing.select(Testing.name).where(Testing.data['k1'] == 'v1')
        self.assertEqual([x.name for x in sq], ['t1'])

    def test_hstore_filtering(self):
        self.create()

        sq = Testing.select().where(Testing.data == {'k1': 'v1', 'k2': 'v2'})
        self.assertEqual([x.name for x in sq], ['t1'])

        sq = Testing.select().where(Testing.data == {'k2': 'v2'})
        self.assertEqual([x.name for x in sq], [])

        # test single key
        sq = Testing.select().where(Testing.data.contains('k3'))
        self.assertEqual([x.name for x in sq], ['t2'])

        # test list of keys
        sq = Testing.select().where(Testing.data.contains(['k2', 'k3']))
        self.assertEqual([x.name for x in sq], ['t2'])

        sq = Testing.select().where(Testing.data.contains(['k2']))
        self.assertEqual([x.name for x in sq], ['t1', 't2'])

        # test dict
        sq = Testing.select().where(Testing.data.contains({'k2': 'v2', 'k3': 'v3'}))
        self.assertEqual([x.name for x in sq], ['t2'])

        sq = Testing.select().where(Testing.data.contains({'k2': 'v2'}))
        self.assertEqual([x.name for x in sq], ['t1', 't2'])

        sq = Testing.select().where(Testing.data.contains({'k2': 'v3'}))
        self.assertEqual([x.name for x in sq], [])

    def test_hstore_filter_functions(self):
        self.create()

        sq = Testing.select().where(Testing.data.exists('k2') == True)
        self.assertEqual([x.name for x in sq], ['t1', 't2'])

        sq = Testing.select().where(Testing.data.exists('k3') == True)
        self.assertEqual([x.name for x in sq], ['t2'])

        sq = Testing.select().where(Testing.data.defined('k2') == True)
        self.assertEqual([x.name for x in sq], ['t1', 't2'])

        sq = Testing.select().where(Testing.data.defined('k3') == True)
        self.assertEqual([x.name for x in sq], ['t2'])

    def test_hstore_update_functions(self):
        self.create()

        rc = Testing.update(data=Testing.data.update(k4='v4')).where(
            Testing.name == 't1'
        ).execute()
        self.assertEqual(rc, 1)
        self.assertEqual(Testing.get(name='t1').data, {'k1': 'v1', 'k2': 'v2', 'k4': 'v4'})

        rc = Testing.update(data=Testing.data.update(k5='v5', k6='v6')).where(
            Testing.name == 't2'
        ).execute()
        self.assertEqual(rc, 1)
        self.assertEqual(Testing.get(name='t2').data, {'k2': 'v2', 'k3': 'v3', 'k5': 'v5', 'k6': 'v6'})

        rc = Testing.update(data=Testing.data.update(k2='vxxx')).execute()
        self.assertEqual(rc, 2)
        self.assertEqual([x.data for x in Testing.select()], [
            {'k1': 'v1', 'k2': 'vxxx', 'k4': 'v4'},
            {'k2': 'vxxx', 'k3': 'v3', 'k5': 'v5', 'k6': 'v6'}
        ])

        rc = Testing.update(data=Testing.data.delete('k4')).where(
            Testing.name == 't1'
        ).execute()
        self.assertEqual(rc, 1)
        self.assertEqual(Testing.get(name='t1').data, {'k1': 'v1', 'k2': 'vxxx'})

        rc = Testing.update(data=Testing.data.delete('k5')).execute()
        self.assertEqual(rc, 2)
        self.assertEqual([x.data for x in Testing.select()], [
            {'k1': 'v1', 'k2': 'vxxx'},
            {'k2': 'vxxx', 'k3': 'v3', 'k6': 'v6'}
        ])

        rc = Testing.update(data=Testing.data.delete('k1', 'k2')).execute()
        self.assertEqual(rc, 2)
        self.assertEqual([x.data for x in Testing.select()], [
            {},
            {'k3': 'v3', 'k6': 'v6'}
        ])


class TestArrayField(BasePostgresqlExtTestCase):
    def _create_am(self):
        return ArrayModel.create(
            tags=['alpha', 'beta', 'gamma', 'delta'],
            ints=[[1, 2], [3, 4], [5, 6]])

    def test_array_storage_retrieval(self):
        am = self._create_am()
        am_db = ArrayModel.get(ArrayModel.id == am.id)
        self.assertEqual(am_db.tags, ['alpha', 'beta', 'gamma', 'delta'])
        self.assertEqual(am_db.ints, [[1, 2], [3, 4], [5, 6]])

    def test_array_search(self):
        def assertAM(where, *instances):
            query = (ArrayModel
                     .select()
                     .where(where)
                     .order_by(ArrayModel.id))
            self.assertEqual([x.id for x in query], [x.id for x in instances])

        am = self._create_am()
        am2 = ArrayModel.create(tags=['alpha', 'beta'], ints=[[1, 1]])
        am3 = ArrayModel.create(tags=['delta'], ints=[[3, 4]])
        am4 = ArrayModel.create(tags=['中文'], ints=[[3, 4]])
        am5 = ArrayModel.create(tags=['中文', '汉语'], ints=[[3, 4]])

        assertAM((Param('beta') == fn.Any(ArrayModel.tags)), am, am2)
        assertAM((Param('delta') == fn.Any(ArrayModel.tags)), am, am3)
        assertAM((Param('omega') == fn.Any(ArrayModel.tags)))

        # Check the contains operator.
        assertAM(SQL("tags @> ARRAY['beta']::varchar[]"), am, am2)

        # Use the nicer API.
        assertAM(ArrayModel.tags.contains('beta'), am, am2)
        assertAM(ArrayModel.tags.contains('omega', 'delta'))
        assertAM(ArrayModel.tags.contains('汉语'), am5)
        assertAM(ArrayModel.tags.contains('alpha', 'delta'), am)

        # Check for any.
        assertAM(ArrayModel.tags.contains_any('beta'), am, am2)
        assertAM(ArrayModel.tags.contains_any('中文'), am4, am5)
        assertAM(ArrayModel.tags.contains_any('omega', 'delta'), am, am3)
        assertAM(ArrayModel.tags.contains_any('alpha', 'delta'), am, am2, am3)

    def test_array_index_slice(self):
        self._create_am()
        res = (ArrayModel
               .select(ArrayModel.tags[1].alias('arrtags'))
               .dicts()
               .get())
        self.assertEqual(res['arrtags'], 'beta')

        res = (ArrayModel
               .select(ArrayModel.tags[2:4].alias('foo'))
               .dicts()
               .get())
        self.assertEqual(res['foo'], ['gamma', 'delta'])

        res = (ArrayModel
               .select(ArrayModel.ints[1][1].alias('ints'))
               .dicts()
               .get())
        self.assertEqual(res['ints'], 4)

        res = (ArrayModel
               .select(ArrayModel.ints[1:2][0].alias('ints'))
               .dicts()
               .get())
        self.assertEqual(res['ints'], [[3], [5]])


class TestTSVectorField(BasePostgresqlExtTestCase):
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
        for idx, msg in enumerate(self.messages):
            FTSModel.create(
                title=str(idx),
                data=msg,
                fts_data=fn.to_tsvector(msg))

    def assertMessages(self, expr, expected):
        query = FTSModel.select().where(expr).order_by(FTSModel.id)
        titles = [row.title for row in query]
        self.assertEqual(list(map(int, titles)), expected)

    def test_sql(self):
        query = FTSModel.select().where(Match(FTSModel.data, 'foo bar'))
        self.assertEqual(query.sql(), (
            'SELECT "t1"."id", "t1"."title", "t1"."data", "t1"."fts_data" '
            'FROM "ftsmodel" AS t1 '
            'WHERE (to_tsvector("t1"."data") @@ to_tsquery(%s))',
            ['foo bar']
        ))

    def test_match_function(self):
        self.assertMessages(Match(FTSModel.data, 'heart'), [1])
        self.assertMessages(Match(FTSModel.data, 'god'), [1])
        self.assertMessages(Match(FTSModel.data, 'faith'), [0, 1, 2, 3, 4])
        self.assertMessages(Match(FTSModel.data, 'thing'), [2, 4])
        self.assertMessages(Match(FTSModel.data, 'faith & things'), [2, 4])
        self.assertMessages(Match(FTSModel.data, 'god | things'), [1, 2, 4])
        self.assertMessages(Match(FTSModel.data, 'god & things'), [])

    def test_tsvector_field(self):
        self.assertMessages(FTSModel.fts_data.match('heart'), [1])
        self.assertMessages(FTSModel.fts_data.match('god'), [1])
        self.assertMessages(FTSModel.fts_data.match('faith'), [0, 1, 2, 3, 4])
        self.assertMessages(FTSModel.fts_data.match('thing'), [2, 4])
        self.assertMessages(FTSModel.fts_data.match('faith & things'), [2, 4])
        self.assertMessages(FTSModel.fts_data.match('god | things'), [1, 2, 4])
        self.assertMessages(FTSModel.fts_data.match('god & things'), [])


class SSCursorTestCase(unittest.TestCase):
    counter = 0

    def setUp(self):
        self.close_conn()  # Close open connection.
        SSCursorModel.drop_table(True)
        NormalModel.drop_table(True)
        SSCursorModel.create_table()
        NormalModel.create_table()
        self.counter = 0
        for i in range(3):
            self.create()

    def create(self):
        self.counter += 1
        SSCursorModel.create(data=self.counter)
        NormalModel.create(data=self.counter)

    def close_conn(self):
        if not test_ss_db.is_closed():
            test_ss_db.close()

    def assertList(self, iterable):
        self.assertEqual(
            [x.data for x in iterable],
            [str(i) for i in range(1, self.counter + 1)])

    def test_model_interaction(self):
        query = SSCursorModel.select().order_by(SSCursorModel.data)
        self.assertList(query)

        # Apparently psycopg2cffi uses a differnt exception type
        if 'PyPy' in sys.version:
            exceptionClass = psycopg2.OperationalError
        else:
            exceptionClass = psycopg2.ProgrammingError

        query2 = query.clone()
        qr = query2.execute()
        self.assertList(qr)

        # The cursor is named and is still "alive" because we can still try
        # to fetch results.
        self.assertTrue(qr.cursor.name is not None)
        self.assertEqual(qr.cursor.fetchone(), None)

        # Execute the query in a transaction.
        with test_ss_db.transaction():
            query3 = query.clone()
            qr2 = query3.execute()

            # Different named cursor
            self.assertFalse(qr2.cursor.name == qr.cursor.name)
            self.assertList(qr2)

        # After the transaction we cannot fetch a result because the cursor
        # is dead.
        self.assertRaises(exceptionClass, qr2.cursor.fetchone)

        # Try using the helper.
        query4 = query.clone()
        self.assertList(ServerSide(query4))

        # Named cursor is dead.
        self.assertRaises(exceptionClass, query4._qr.cursor.fetchone)

    def test_serverside_normal_model(self):
        query = NormalModel.select().order_by(NormalModel.data)
        self.assertList(query)

        # Apparently psycopg2cffi uses a differnt exception type
        if 'PyPy' in sys.version:
            exceptionClass = psycopg2.OperationalError
        else:
            exceptionClass = psycopg2.ProgrammingError

        # We can ask for more results from a normal query.
        self.assertEqual(query._qr.cursor.fetchone(), None)

        clone = query.clone()
        self.assertList(ServerSide(clone))

        # Named cursor is dead.
        self.assertRaises(exceptionClass, clone._qr.cursor.fetchone)

        # Ensure where clause is preserved.
        query = query.where(NormalModel.data == '2')
        data = [x.data for x in ServerSide(query)]
        self.assertEqual(data, ['2'])

    def test_ss_cursor(self):
        tbl = SSCursorModel._meta.db_table
        name = str(uuid.uuid1())

        # Apparently psycopg2cffi uses a differnt exception type
        if 'PyPy' in sys.version:
            exceptionClass = psycopg2.OperationalError
        else:
            exceptionClass = psycopg2.ProgrammingError

        # Get a named cursor and execute a select query.
        cursor = test_ss_db.get_cursor(name=name)
        cursor.execute('select data from %s order by id' % tbl)

        # Ensure the cursor attributes are as we expect.
        self.assertEqual(cursor.description, None)
        self.assertEqual(cursor.name, name)
        self.assertFalse(cursor.withhold)  # Close cursor after commit.

        # Cursor works and populates description after fetching one row.
        self.assertEqual(cursor.fetchone(), ('1',))
        self.assertEqual(cursor.description[0].name, 'data')

        # Explicitly close the cursor.
        test_ss_db.commit()
        self.assertRaises(exceptionClass, cursor.fetchone)

        # This would not work is the named cursor was still holding a ref to
        # the table.
        test_ss_db.execute_sql('truncate table %s;' % tbl)
        test_ss_db.commit()

def json_ok():
    if TestingJson is None:
        return False
    conn = test_db.get_conn()
    return conn.server_version >= 90300

if json_ok():
    from psycopg2.extras import Json

    class TestJsonField(unittest.TestCase):
        def setUp(self):
            TestingJson.drop_table(True)
            TestingJson.create_table()

        def test_json_field(self):
            data = {'k1': ['a1', 'a2'], 'k2': {'k3': 'v3'}}
            tj = TestingJson.create(data=data)
            tj_db = TestingJson.get(tj._pk_expr())
            self.assertEqual(tj_db.data, data)

        def test_json_lookup_methods(self):
            data = {
                'gp1': {
                    'p1': {'c1': 'foo'},
                    'p2': {'c2': 'bar'},
                },
                'gp2': {}}
            tj = TestingJson.create(data=data)

            def assertLookup(lookup, expected):
                query = (TestingJson
                         .select(lookup)
                         .where(tj._pk_expr())
                         .dicts())
                self.assertEqual(query.get(), expected)

            expr = TestingJson.data['gp1']['p1'].alias('pdata')
            assertLookup(expr, {'pdata': '{"c1": "foo"}'})
            assertLookup(expr.as_json(), {'pdata': {'c1': 'foo'}})

            expr = TestingJson.data['gp1']['p1']['c1'].alias('cdata')
            assertLookup(expr, {'cdata': 'foo'})
            assertLookup(expr.as_json(), {'cdata': 'foo'})

            tj.data = [
                {'i1': ['foo', 'bar', 'baze']},
                ['nugget', 'mickey']]
            tj.save()

            expr = TestingJson.data[0]['i1'].alias('idata')
            assertLookup(expr, {'idata': '["foo", "bar", "baze"]'})
            assertLookup(expr.as_json(), {'idata': ['foo', 'bar', 'baze']})

            expr = TestingJson.data[1][1].alias('ldata')
            assertLookup(expr, {'ldata': 'mickey'})
            assertLookup(expr.as_json(), {'ldata': 'mickey'})

        def test_json_path(self):
            data = {
                'foo': {
                    'baz': {
                        'bar': ['i1', 'i2', 'i3'],
                        'baze': ['j1', 'j2'],
                    }}}
            tj = TestingJson.create(data=data)

            def assertPath(path, expected):
                query = (TestingJson
                         .select(path)
                         .where(tj._pk_expr())
                         .dicts())
                self.assertEqual(query.get(), expected)

            expr = TestingJson.data.path('foo', 'baz', 'bar').alias('p')
            assertPath(expr, {'p': '["i1", "i2", "i3"]'})
            assertPath(expr.as_json(), {'p': ['i1', 'i2', 'i3']})

            expr = TestingJson.data.path('foo', 'baz', 'baze', 1).alias('p')
            assertPath(expr, {'p': 'j2'})
            assertPath(expr.as_json(), {'p': 'j2'})

        def test_json_field_sql(self):
            tj = TestingJson.select().where(TestingJson.data == {'foo': 'bar'})
            sql, params = tj.sql()
            self.assertEqual(sql, (
                'SELECT "t1"."id", "t1"."data" '
                'FROM "testingjson" AS t1 WHERE ("t1"."data" = %s)'))
            self.assertEqual(params[0].adapted, {'foo': 'bar'})

            tj = TestingJson.select().where(TestingJson.data['foo'] == 'bar')
            sql, params = tj.sql()
            self.assertEqual(sql, (
                'SELECT "t1"."id", "t1"."data" '
                'FROM "testingjson" AS t1 WHERE ("t1"."data"->>%s = %s)'))
            self.assertEqual(params, ['foo', 'bar'])

        def assertItems(self, where, *items):
            query = TestingJson.select().where(where).order_by(TestingJson.id)
            self.assertEqual(
                [item.id for item in query],
                [item.id for item in items])

        def test_lookup(self):
            t1 = TestingJson.create(data={'k1': 'v1', 'k2': {'k3': 'v3'}})
            t2 = TestingJson.create(data={'k1': 'x1', 'k2': {'k3': 'x3'}})
            t3 = TestingJson.create(data={'k1': 'v1', 'j2': {'j3': 'v3'}})
            self.assertItems((TestingJson.data['k2']['k3'] == 'v3'), t1)
            self.assertItems((TestingJson.data['k1'] == 'v1'), t1, t3)

            # Valid key, no matching value.
            self.assertItems((TestingJson.data['k2'] == 'v1'))

            # Non-existent key.
            self.assertItems((TestingJson.data['not-here'] == 'v1'))

            # Non-existent nested key.
            self.assertItems((TestingJson.data['not-here']['xxx'] == 'v1'))

            self.assertItems((TestingJson.data['k2']['xxx'] == 'v1'))

elif TEST_VERBOSITY > 0:
    print_('Skipping postgres "Json" tests, unsupported version.')
