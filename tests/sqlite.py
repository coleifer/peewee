from decimal import Decimal as D
import datetime
import json

from peewee import *
from playhouse.sqlite_ext import *

from .base import BaseTestCase
from .base import IS_CYSQLITE
from .base import ModelTestCase
from .base import TestModel
from .base import get_in_memory_db
from .base import requires_models
from .base import skip_unless
from .base import skip_unless_db
from .sqlite_helpers import compile_option
from .sqlite_helpers import json_text_installed
from .sqlite_helpers import jsonb_installed


database = SqliteDatabase(':memory:', rank_functions=True, timeout=100)


try:
    from playhouse._sqlite_udf import peewee_rank
    CYTHON_EXTENSION = True
except ImportError:
    CYTHON_EXTENSION = False

# The cysqlite job runs the executing extension tests against cysqlite.
# Every other job uses the stdlib driver above.
if IS_CYSQLITE:
    from playhouse.cysqlite_ext import CySqliteDatabase
    ext_database = CySqliteDatabase('peewee_test.db', timeout=100)
    if CYTHON_EXTENSION:
        # CySqliteDatabase's native rank functions include no bm25f.
        from playhouse.sqlite_udf import bm25f
        ext_database.register_function(bm25f, 'fts_bm25f')
else:
    ext_database = database


class Post(TestModel):
    message = TextField()


class ContentPost(FTSModel, Post):
    class Meta:
        options = {
            'content': Post,
            'tokenize': 'porter'}


class ContentPostMessage(FTSModel, TestModel):
    message = TextField()
    class Meta:
        options = {'tokenize': 'porter', 'content': Post}


class Document(FTSModel, TestModel):
    message = TextField()
    class Meta:
        options = {'tokenize': 'porter'}


class MultiColumn(FTSModel, TestModel):
    c1 = SearchField()
    c2 = SearchField()
    c3 = SearchField()
    c4 = IntegerField()
    class Meta:
        options = {'tokenize': 'porter'}


class RowIDModel(TestModel):
    rowid = RowIDField()
    data = IntegerField()


class KeyData(TestModel):
    key = TextField()
    data = JSONField()

class JBData(TestModel):
    key = TextField()
    data = JSONBField()


class FTS5Test(FTS5Model):
    title = SearchField()
    data = SearchField()
    misc = SearchField(unindexed=True)

    class Meta:
        legacy_table_names = False


class FTS5Document(FTS5Model):
    message = SearchField()
    class Meta:
        options = {'tokenize': 'porter'}


class ContentPost5(FTS5Model):
    message = SearchField()
    class Meta:
        options = {'content': Post, 'content_rowid': Post.id}


class FTS5Contentless(FTS5Model):
    title = SearchField()
    data = SearchField()
    class Meta:
        legacy_table_names = False
        options = {'content': '', 'contentless_delete': 1}


class FTS5ContentlessUnindexed(FTS5Model):
    title = SearchField()
    meta = SearchField(unindexed=True)
    class Meta:
        legacy_table_names = False
        options = {
            'content': '',
            'contentless_delete': 1,
            'contentless_unindexed': 1}

    @classmethod
    def drop_table(cls, *args, **kwargs):
        super(FTS5ContentlessUnindexed, cls).drop_table(*args, **kwargs)
        # Sqlite drop of a contentless_unindexed fts5 table (thru at least
        # 3.54) orphans the _content shadow table, breaking re-creation.
        cls._meta.database.execute_sql(
            'DROP TABLE IF EXISTS "%s_content"' % cls._meta.table_name)


class FTS5DeleteCommand(FTS5Model):
    # Contentless, with the attribute name mapped to a different column.
    body = SearchField(column_name='msg')
    note = SearchField(unindexed=True)
    class Meta:
        legacy_table_names = False
        options = {'content': ''}


FTS5Vocab = FTS5Test.VocabModel()
FTS5VocabCol = FTS5Test.VocabModel('col')
FTS5VocabInstance = FTS5Test.VocabModel('instance')


class SearchWeight(FTSModel, TestModel):
    # FTS4 model for exercising dict-form search weights. The implicit `rowid`
    # primary-key precedes these content columns.
    title = SearchField()
    body = SearchField()
    class Meta:
        options = {'tokenize': 'porter'}


class SearchWeight5(FTS5Model):
    # FTS5 model with an UNINDEXED column between two indexed columns, so a
    # mis-placed weight is observable in the ranking.
    title = SearchField()
    extra = SearchField(unindexed=True)
    body = SearchField()
    class Meta:
        legacy_table_names = False


class DT(TestModel):
    key = TextField(primary_key=True)
    d = DateTimeField()
    iso = ISODateTimeField()


class TestJSONField(ModelTestCase):
    database = ext_database
    requires = [KeyData]

    def test_schema(self):
        self.assertSQL(KeyData._schema._create_table(), (
            'CREATE TABLE IF NOT EXISTS "key_data" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"key" TEXT NOT NULL, '
            '"data" TEXT NOT NULL)'), [])

    def test_create_read_update(self):
        test_values = (
            'simple string',
            '',
            1337,
            0.0,
            True,
            False,
            ['foo', 'bar', ['baz', 'nug']],
            {'k1': 'v1', 'k2': {'x1': 'y1', 'x2': 'y2'}},
            {'a': 1, 'b': 0.0, 'c': True, 'd': False, 'e': None, 'f': [0, 1],
             'g': {'h': 'ijkl'}},
        )

        # Create a row using the given test value. Verify we can read the value
        # back from the database, and also that we can query for the row using
        # the value in the WHERE clause.
        for i, value in enumerate(test_values):
            # We can create and re-read values.
            KeyData.create(key='k%s' % i, data=value)
            kd_db = KeyData.get(KeyData.key == 'k%s' % i)
            self.assertEqual(kd_db.data, value)

            # We can read the data back using the value in the WHERE clause.
            kd_db = KeyData.get(KeyData.data == value)
            self.assertEqual(kd_db.key, 'k%s' % i)

        # Verify we can use values in UPDATE query.
        kd = KeyData.create(key='kx', data='')
        for value in test_values:
            nrows = (KeyData
                     .update(data=value)
                     .where(KeyData.key == 'kx')
                     .execute())
            self.assertEqual(nrows, 1)
            kd_db = KeyData.get(KeyData.key == 'kx')
            self.assertEqual(kd_db.data, value)

    def test_key_with_special_chars(self):
        kd = KeyData.create(key='k1', data={'k 1': {'k.. 2': {'{k3}': 'v4'}}})
        def assertMatch(expr):
            obj = KeyData.select().where(expr.is_null(False)).get()
            self.assertEqual(obj.key, 'k1')

        assertMatch(KeyData.data['k 1'])
        assertMatch(KeyData.data['k 1']['k.. 2'])
        assertMatch(KeyData.data['k 1']['k.. 2']['{k3}'])

    def test_json_unicode(self):
        with self.database.atomic():
            KeyData.delete().execute()

        # Two Chinese characters.
        unicode_str = b'\xe4\xb8\xad\xe6\x96\x87'.decode('utf8')
        data = {'foo': unicode_str}
        kd = KeyData.create(key='k1', data=data)

        kd_db = KeyData.get(KeyData.key == 'k1')
        self.assertEqual(kd_db.data, {'foo': unicode_str})

    def test_json_to_json(self):
        kd1 = KeyData.create(key='k1', data={'k1': 'v1', 'k2': 'v2'})
        subq = (KeyData
                .select(KeyData.data)
                .where(KeyData.key == 'k1'))

        # Assign value using a subquery.
        KeyData.create(key='k2', data=subq)
        kd2_db = KeyData.get(KeyData.key == 'k2')
        self.assertEqual(kd2_db.data, {'k1': 'v1', 'k2': 'v2'})

    def test_json_bulk_update_top_level_list(self):
        kd1 = KeyData.create(key='k1', data=['a', 'b', 'c'])
        kd2 = KeyData.create(key='k2', data=['d', 'e', 'f'])

        kd1.data = ['g', 'h', 'i']
        kd2.data = ['j', 'k', 'l']
        KeyData.bulk_update([kd1, kd2], fields=[KeyData.data])
        kd1_db = KeyData.get(KeyData.key == 'k1')
        kd2_db = KeyData.get(KeyData.key == 'k2')
        self.assertEqual(kd1_db.data, ['g', 'h', 'i'])
        self.assertEqual(kd2_db.data, ['j', 'k', 'l'])

    def test_json_bulk_update_top_level_dict(self):
        kd1 = KeyData.create(key='k1', data={'x': 'y1'})
        kd2 = KeyData.create(key='k2', data={'x': 'y2'})

        kd1.data = {'x': 'z1'}
        kd2.data = {'X': 'Z2'}
        KeyData.bulk_update([kd1, kd2], fields=[KeyData.data])
        kd1_db = KeyData.get(KeyData.key == 'k1')
        kd2_db = KeyData.get(KeyData.key == 'k2')
        self.assertEqual(kd1_db.data, {'x': 'z1'})
        self.assertEqual(kd2_db.data, {'X': 'Z2'})

    def test_json_multi_ops(self):
        data = (
            ('k1', [0, 1]),
            ('k2', [1, 2]),
            ('k3', {'x3': 'y3'}),
            ('k4', {'x4': 'y4'}))
        res = KeyData.insert_many(data).execute()
        if self.database.returning_clause:
            self.assertEqual([r for r, in res], [1, 2, 3, 4])
        else:
            self.assertEqual(res, 4)

        vals = [[1, 2], [2, 3], {'x3': 'y3'}, {'x5': 'y5'}]
        pw_vals = [Value(v, unpack=False) for v in vals]

        query = KeyData.select().where(KeyData.data.in_(pw_vals))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."key", "t1"."data" '
            'FROM "key_data" AS "t1" '
            'WHERE ("t1"."data" IN (json(?), json(?), json(?), json(?)))'),
            ['[1, 2]', '[2, 3]', '{"x3": "y3"}', '{"x5": "y5"}'])

        self.assertEqual(query.count(), 2)
        self.assertEqual(sorted([k.key for k in query]), ['k2', 'k3'])

        query = KeyData.select().where(KeyData.data == [1, 2])
        self.assertEqual(query.count(), 1)
        self.assertEqual(query.get().key, 'k2')

        query = KeyData.select().where(KeyData.data == {'x3': 'y3'})
        self.assertEqual(query.count(), 1)
        self.assertEqual(query.get().key, 'k3')

    def test_select_json_value(self):
        data = (
            ('k1', {'a': {'b': 'c', 'd': [2, 1, 0]}}),
        )
        KeyData.insert_many(data).execute()

        kd = (KeyData
              .select(KeyData.data['a'].alias('a'))
              .get())
        self.assertEqual(kd.a, {'b': 'c', 'd': [2, 1, 0]})

        kd = (KeyData
              .select(KeyData.data['a']['b'].alias('b'))
              .get())
        self.assertEqual(kd.b, 'c')

        kd = (KeyData
              .select(KeyData.data['a']['d'].alias('d'))
              .get())
        self.assertEqual(kd.d, [2, 1, 0])

        kd = (KeyData
              .select(KeyData.data['a']['d'][0].alias('d0'))
              .get())
        self.assertEqual(kd.d0, 2)


class TestJSONFieldFunctions(ModelTestCase):
    database = ext_database
    requires = [KeyData]
    test_data = [
        ('a', {'k1': 'v1', 'x1': {'y1': 'z1'}}),
        ('b', {'k2': 'v2', 'x2': {'y2': 'z2'}}),
        ('c', {'k1': 'v1', 'k2': 'v2'}),
        ('d', {'x1': {'y1': 'z1', 'y2': 'z2'}}),
        ('e', {'l1': [0, 1, 2], 'l2': [1, [3, 3], 7]}),
    ]
    M = KeyData

    def setUp(self):
        super(TestJSONFieldFunctions, self).setUp()
        KeyData = self.M
        with self.database.atomic():
            for key, data in self.test_data:
                KeyData.create(key=key, data=data)

        self.Q = KeyData.select().order_by(KeyData.key)

    def assertRows(self, where, expected):
        self.assertEqual([kd.key for kd in self.Q.where(where)], expected)

    def assertData(self, key, expected):
        KeyData = self.M
        self.assertEqual(KeyData.get(KeyData.key == key).data, expected)

    def test_json_group_functions(self):
        KeyData = self.M
        with self.database.atomic():
            KeyData.delete().execute()
            for i in range(10):
                # e.g., {v: 0, v0: {items: []}}, {v: 2, v2: {items: [0, 1]}}
                KeyData.create(key='k%s' % i, data={'v': i, 'v%s' % i: {
                    'items': list(range(i))}})

        jga_key = fn.json_group_array(KeyData.key)
        query = (KeyData
                 .select(jga_key)
                 .where(KeyData.data['v'] < 4)
                 .order_by(KeyData.key))
        self.assertEqual(json.loads(query.scalar()), ['k0', 'k1', 'k2', 'k3'])

        # Can specify json.loads as the converter for the function.
        query = (KeyData
                 .select(jga_key.python_value(json.loads))
                 .where(KeyData.data['v'] > 6)
                 .order_by(KeyData.key))
        self.assertEqual(query.scalar(), ['k7', 'k8', 'k9'])

        # Aggregating a list of ints?
        jga_id = fn.json_group_array(KeyData.id)
        query = (KeyData
                 .select(jga_id)
                 .where(KeyData.data['v'] < 4)
                 .order_by(KeyData.id))
        self.assertEqual(json.loads(query.scalar()), [1, 2, 3, 4])

        query = (KeyData
                 .select(jga_id.python_value(json.loads))
                 .where(KeyData.data['v'] > 6)
                 .order_by(KeyData.id))
        self.assertEqual(query.scalar(), [8, 9, 10])

        # Using json_group_object.
        jgo_key = fn.json_group_object(KeyData.key, KeyData.data['v'])
        res = (KeyData
               .select(jgo_key)
               .where(KeyData.data['v'] < 4)
               .scalar())
        self.assertEqual(json.loads(res), {'k0': 0, 'k1': 1, 'k2': 2, 'k3': 3})

        query = (KeyData
                 .select(jgo_key.python_value(json.loads))
                 .where(KeyData.data['v'] < 4))
        self.assertEqual(query.scalar(), {'k0': 0, 'k1': 1, 'k2': 2, 'k3': 3})

    def test_extract(self):
        KeyData = self.M
        self.assertRows((KeyData.data['k1'] == 'v1'), ['a', 'c'])
        self.assertRows((KeyData.data['k2'] == 'v2'), ['b', 'c'])
        self.assertRows((KeyData.data['x1']['y1'] == 'z1'), ['a', 'd'])
        self.assertRows((KeyData.data['l1'][1] == 1), ['e'])
        self.assertRows((KeyData.data['l2'][1][1] == 3), ['e'])

    @skip_unless(json_text_installed())
    def test_extract_text_json(self):
        KeyData = self.M
        D = KeyData.data
        self.assertRows((D.extract('$.k1') == 'v1'), ['a', 'c'])
        self.assertRows((D.extract_text('$.k1') == 'v1'), ['a', 'c'])
        self.assertRows((D.extract_json('$.k1') == '"v1"'), ['a', 'c'])
        self.assertRows((D.extract_text('k2') == 'v2'), ['b', 'c'])
        self.assertRows((D.extract_json('k2') == '"v2"'), ['b', 'c'])
        self.assertRows((D.extract_text('$.x1.y1') == 'z1'), ['a', 'd'])
        self.assertRows((D.extract_json('$.x1.y1') == '"z1"'), ['a', 'd'])
        self.assertRows((D.extract_text('$.l1[1]') == 1), ['e'])
        self.assertRows((D.extract_text('$.l2[1][1]') == 3), ['e'])
        self.assertRows((D.extract_json('x1') == '{"y1":"z1"}'), ['a'])

    def test_extract_multiple(self):
        KeyData = self.M
        query = KeyData.select(
            KeyData.key,
            KeyData.data.extract('$.k1', '$.k2').alias('keys'))
        self.assertEqual(sorted((k.key, k.keys) for k in query), [
            ('a', ['v1', None]),
            ('b', [None, 'v2']),
            ('c', ['v1', 'v2']),
            ('d', [None, None]),
            ('e', [None, None])])

    def test_insert(self):
        KeyData = self.M
        # Existing values are not overwritten.
        query = KeyData.update(data=KeyData.data['k1'].insert('v1-x'))
        self.assertEqual(query.execute(), 5)

        self.assertData('a', {'k1': 'v1', 'x1': {'y1': 'z1'}})
        self.assertData('b', {'k1': 'v1-x', 'k2': 'v2', 'x2': {'y2': 'z2'}})
        self.assertData('c', {'k1': 'v1', 'k2': 'v2'})
        self.assertData('d', {'k1': 'v1-x', 'x1': {'y1': 'z1', 'y2': 'z2'}})
        self.assertData('e', {'k1': 'v1-x', 'l1': [0, 1, 2],
                              'l2': [1, [3, 3], 7]})

    def test_insert_json(self):
        KeyData = self.M
        set_json = KeyData.data['k1'].insert([0])
        query = KeyData.update(data=set_json)
        self.assertEqual(query.execute(), 5)

        self.assertData('a', {'k1': 'v1', 'x1': {'y1': 'z1'}})
        self.assertData('b', {'k1': [0], 'k2': 'v2', 'x2': {'y2': 'z2'}})
        self.assertData('c', {'k1': 'v1', 'k2': 'v2'})
        self.assertData('d', {'k1': [0], 'x1': {'y1': 'z1', 'y2': 'z2'}})
        self.assertData('e', {'k1': [0], 'l1': [0, 1, 2],
                              'l2': [1, [3, 3], 7]})

    def test_replace(self):
        KeyData = self.M
        # Only existing values are overwritten.
        query = KeyData.update(data=KeyData.data['k1'].replace('v1-x'))
        self.assertEqual(query.execute(), 5)

        self.assertData('a', {'k1': 'v1-x', 'x1': {'y1': 'z1'}})
        self.assertData('b', {'k2': 'v2', 'x2': {'y2': 'z2'}})
        self.assertData('c', {'k1': 'v1-x', 'k2': 'v2'})
        self.assertData('d', {'x1': {'y1': 'z1', 'y2': 'z2'}})
        self.assertData('e', {'l1': [0, 1, 2], 'l2': [1, [3, 3], 7]})

    def test_replace_json(self):
        KeyData = self.M
        set_json = KeyData.data['k1'].replace([0])
        query = KeyData.update(data=set_json)
        self.assertEqual(query.execute(), 5)

        self.assertData('a', {'k1': [0], 'x1': {'y1': 'z1'}})
        self.assertData('b', {'k2': 'v2', 'x2': {'y2': 'z2'}})
        self.assertData('c', {'k1': [0], 'k2': 'v2'})
        self.assertData('d', {'x1': {'y1': 'z1', 'y2': 'z2'}})
        self.assertData('e', {'l1': [0, 1, 2], 'l2': [1, [3, 3], 7]})

    def test_set(self):
        KeyData = self.M
        query = (KeyData
                 .update({KeyData.data: KeyData.data['k1'].set('v1-x')})
                 .where(KeyData.data['k1'] == 'v1'))
        self.assertEqual(query.execute(), 2)
        self.assertRows((KeyData.data['k1'] == 'v1-x'), ['a', 'c'])

        self.assertData('a', {'k1': 'v1-x', 'x1': {'y1': 'z1'}})

    def test_set_json(self):
        KeyData = self.M
        set_json = KeyData.data['x1'].set({'y1': 'z1-x', 'y3': 'z3'})
        query = (KeyData
                 .update({KeyData.data: set_json})
                 .where(KeyData.data['x1']['y1'] == 'z1'))
        self.assertEqual(query.execute(), 2)
        self.assertRows((KeyData.data['x1']['y1'] == 'z1-x'), ['a', 'd'])

        self.assertData('a', {'k1': 'v1', 'x1': {'y1': 'z1-x', 'y3': 'z3'}})
        self.assertData('d', {'x1': {'y1': 'z1-x', 'y3': 'z3'}})

    def test_append(self):
        KeyData = self.M
        for value in ('ix', [], ['c1'], ['c1', 'c2'], {}, {'k1': 'v1'},
                      {'k1': 'v1', 'k2': 'v2'}, None, 1):
            KeyData.delete().execute()
            KeyData.create(key='a0', data=[])
            KeyData.create(key='a1', data=['i1'])
            KeyData.create(key='a2', data=['i1', 'i2'])
            KeyData.create(key='n0', data={'arr': []})
            KeyData.create(key='n1', data={'arr': ['i1']})
            KeyData.create(key='n2', data={'arr': ['i1', 'i2']})

            query = (KeyData
                     .update(data=KeyData.data.append(value))
                     .where(KeyData.key.startswith('a')))
            self.assertEqual(query.execute(), 3)

            query = (KeyData
                     .select(KeyData.key, fn.json(KeyData.data))
                     .where(KeyData.key.startswith('a')))
            self.assertEqual(sorted((row.key, row.data) for row in query),
                             [('a0', [value]), ('a1', ['i1', value]),
                              ('a2', ['i1', 'i2', value])])

            query = (KeyData
                     .update(data=KeyData.data['arr'].append(value))
                     .where(KeyData.key.startswith('n')))
            self.assertEqual(query.execute(), 3)

            query = (KeyData
                     .select(KeyData.key, fn.json(KeyData.data))
                     .where(KeyData.key.startswith('n')))
            self.assertEqual(sorted((row.key, row.data) for row in query),
                             [('n0', {'arr': [value]}),
                              ('n1', {'arr': ['i1', value]}),
                              ('n2', {'arr': ['i1', 'i2', value]})])

    def test_update(self):
        KeyData = self.M
        merged = KeyData.data.update({'x1': {'y1': 'z1-x', 'y3': 'z3'}})
        query = (KeyData
                 .update({KeyData.data: merged})
                 .where(KeyData.data['x1']['y1'] == 'z1'))
        self.assertEqual(query.execute(), 2)
        self.assertRows((KeyData.data['x1']['y1'] == 'z1-x'), ['a', 'd'])

        self.assertData('a', {'k1': 'v1', 'x1': {'y1': 'z1-x', 'y3': 'z3'}})
        self.assertData('d', {'x1': {'y1': 'z1-x', 'y2': 'z2', 'y3': 'z3'}})

    def test_update_with_removal(self):
        KeyData = self.M
        m = KeyData.data.update({'k1': None, 'x1': {'y1': None, 'y3': 'z3'}})
        query = KeyData.update(data=m).where(KeyData.data['x1']['y1'] == 'z1')
        self.assertEqual(query.execute(), 2)
        self.assertRows((KeyData.data['x1']['y3'] == 'z3'), ['a', 'd'])

        self.assertData('a', {'x1': {'y3': 'z3'}})
        self.assertData('d', {'x1': {'y2': 'z2', 'y3': 'z3'}})

    def test_update_nested(self):
        KeyData = self.M
        merged = KeyData.data['x1'].update({'y1': 'z1-x', 'y3': 'z3'})
        query = (KeyData
                 .update(data=merged)
                 .where(KeyData.data['x1']['y1'] == 'z1'))
        self.assertEqual(query.execute(), 2)
        self.assertRows((KeyData.data['x1']['y1'] == 'z1-x'), ['a', 'd'])

        self.assertData('a', {'k1': 'v1', 'x1': {'y1': 'z1-x', 'y3': 'z3'}})
        self.assertData('d', {'x1': {'y1': 'z1-x', 'y2': 'z2', 'y3': 'z3'}})

    def test_updated_nested_with_removal(self):
        KeyData = self.M
        merged = KeyData.data['x1'].update({'o1': 'p1', 'y1': None})
        nrows = (KeyData
                 .update(data=merged)
                 .where(KeyData.data['x1']['y1'] == 'z1')
                 .execute())
        self.assertRows((KeyData.data['x1']['o1'] == 'p1'), ['a', 'd'])
        self.assertData('a', {'k1': 'v1', 'x1': {'o1': 'p1'}})
        self.assertData('d', {'x1': {'o1': 'p1', 'y2': 'z2'}})

    def test_remove(self):
        KeyData = self.M
        query = (KeyData
                 .update(data=KeyData.data['k1'].remove())
                 .where(KeyData.data['k1'] == 'v1'))
        self.assertEqual(query.execute(), 2)

        self.assertData('a', {'x1': {'y1': 'z1'}})
        self.assertData('c', {'k2': 'v2'})

        nrows = (KeyData
                 .update(data=KeyData.data['l2'][1][1].remove())
                 .where(KeyData.key == 'e')
                 .execute())
        self.assertData('e', {'l1': [0, 1, 2], 'l2': [1, [3], 7]})

    def test_simple_update(self):
        KeyData = self.M
        nrows = (KeyData
                 .update(data={'foo': 'bar'})
                 .where(KeyData.key.in_(['a', 'b']))
                 .execute())
        self.assertData('a', {'foo': 'bar'})
        self.assertData('b', {'foo': 'bar'})

    def test_children(self):
        KeyData = self.M
        children = KeyData.data.children().alias('children')
        query = (KeyData
                 .select(KeyData.key, children.c.fullkey.alias('fullkey'))
                 .from_(KeyData, children)
                 .where(~children.c.fullkey.contains('k'))
                 .order_by(KeyData.id, SQL('fullkey')))
        accum = [(row.key, row.fullkey) for row in query]
        self.assertEqual(accum, [
            ('a', '$.x1'),
            ('b', '$.x2'),
            ('d', '$.x1'),
            ('e', '$.l1'), ('e', '$.l2')])

    def test_tree(self):
        KeyData = self.M
        tree = KeyData.data.tree().alias('tree')
        query = (KeyData
                 .select(tree.c.fullkey.alias('fullkey'))
                 .from_(KeyData, tree)
                 .where(KeyData.key == 'd')
                 .order_by(SQL('1'))
                 .tuples())
        self.assertEqual([fullkey for fullkey, in query], [
            '$',
            '$.x1',
            '$.x1.y1',
            '$.x1.y2'])


@skip_unless(jsonb_installed(), 'requires sqlite jsonb support')
class TestJSONBFieldFunctions(TestJSONFieldFunctions):
    requires = [JBData]
    M = JBData

    def assertData(self, key, expected):
        q = JBData.select(fn.json(JBData.data)).where(JBData.key == key)
        self.assertEqual(q.get().data, expected)

    def test_extract_multiple(self):
        # We need to override this, otherwise we end up with jsonb returned.
        expr = fn.json(JBData.data.extract('$.k1', '$.k2'))
        query = JBData.select(
            JBData.key,
            expr.python_value(json.loads).alias('keys'))
        self.assertEqual(sorted((k.key, k.keys) for k in query), [
            ('a', ['v1', None]),
            ('b', [None, 'v2']),
            ('c', ['v1', 'v2']),
            ('d', [None, None]),
            ('e', [None, None])])


class TestSqliteExtensions(BaseTestCase):
    def test_virtual_model(self):
        class Test(VirtualModel):
            class Meta:
                database = database
                extension_module = 'ext1337'
                legacy_table_names = False
                options = {'huey': 'cat', 'mickey': 'dog'}
                primary_key = False

        class SubTest(Test): pass

        self.assertSQL(Test._schema._create_table(), (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "test" '
            'USING ext1337 '
            '(huey=cat, mickey=dog)'), [])
        self.assertSQL(SubTest._schema._create_table(), (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "sub_test" '
            'USING ext1337 '
            '(huey=cat, mickey=dog)'), [])
        self.assertSQL(
            Test._schema._create_table(huey='kitten', zaizee='cat'),
            ('CREATE VIRTUAL TABLE IF NOT EXISTS "test" '
             'USING ext1337 (huey=kitten, mickey=dog, zaizee=cat)'), [])

    def test_autoincrement_field(self):
        class AutoIncrement(TestModel):
            id = AutoIncrementField()
            data = TextField()
            class Meta:
                database = database

        self.assertSQL(AutoIncrement._schema._create_table(), (
            'CREATE TABLE IF NOT EXISTS "auto_increment" '
            '("id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, '
            '"data" TEXT NOT NULL)'), [])


class BaseFTSTestCase(object):
    messages = (
        ('A faith is a necessity to a man. Woe to him who believes in '
         'nothing.'),
        ('All who call on God in true faith, earnestly from the heart, will '
         'certainly be heard, and will receive what they have asked and '
         'desired.'),
        ('Be faithful in small things because it is in them that your '
         'strength lies.'),
        ('Faith consists in believing when it is beyond the power of reason '
         'to believe.'),
        ('Faith has to do with things that are not seen and hope with things '
         'that are not at hand.'))
    values = (
        ('aaaaa bbbbb ccccc ddddd', 'aaaaa ccccc', 'zzzzz zzzzz', 1),
        ('bbbbb ccccc ddddd eeeee', 'bbbbb', 'zzzzz', 2),
        ('ccccc ccccc ddddd fffff', 'ccccc', 'yyyyy', 3),
        ('ddddd', 'ccccc', 'xxxxx', 4))

    def assertMessages(self, query, indexes):
        self.assertEqual([obj.message for obj in query],
                         [self.messages[idx] for idx in indexes])


class TestFullTextSearch(BaseFTSTestCase, ModelTestCase):
    database = ext_database
    requires = [
        Post,
        ContentPost,
        ContentPostMessage,
        Document,
        MultiColumn]

    @requires_models(Document)
    def test_fts_insert_or_replace(self):
        # We can use replace to create a new row.
        n = Document.replace(rowid=100, message='m100').execute()
        self.assertEqual(n, 100)
        self.assertEqual(Document.select().count(), 1)

        # We can use replace to update an existing row.
        n = Document.replace(rowid=100, message='x100').execute()
        self.assertEqual(n, 100)
        self.assertEqual(Document.select().count(), 1)

        # Adds a new row.
        n = Document.replace(rowid=101, message='x101').execute()
        self.assertEqual(n, 101)
        self.assertEqual(Document.select().count(), 2)

        query = Document.select().order_by(Document.message)
        self.assertEqual(list(query.tuples()), [(100, 'x100'), (101, 'x101')])

    @requires_models(Document)
    def test_fts_manual(self):
        messages = [Document.create(message=message)
                    for message in self.messages]
        query = (Document
                 .select()
                 .where(Document.match('believe'))
                 .order_by(Document.rowid))
        self.assertMessages(query, [0, 3])

        query = Document.search('believe')
        self.assertMessages(query, [3, 0])

        # Test peewee's "rank" algorithm, as presented in the SQLite FTS3 docs.
        query = Document.search('things', with_score=True)
        self.assertEqual([(row.message, row.score) for row in query], [
            (self.messages[4], -2. / 3),
            (self.messages[2], -1. / 3)])

        # Test peewee's bm25 ranking algorithm.
        query = Document.search_bm25('things', with_score=True)
        self.assertEqual([(d.message, round(d.score, 2)) for d in query], [
            (self.messages[4], -0.45),
            (self.messages[2], -0.36)])

        # Another test of bm25 ranking.
        query = Document.search_bm25('believe', with_score=True)
        self.assertEqual([(d.message, round(d.score, 2)) for d in query], [
            (self.messages[3], -0.49),
            (self.messages[0], -0.35)])

        query = Document.search_bm25('god faith', with_score=True)
        self.assertEqual([(d.message, round(d.score, 2)) for d in query], [
            (self.messages[1], -0.92)])

        query = Document.search_bm25('"it is"', with_score=True)
        self.assertEqual([(d.message, round(d.score, 2)) for d in query], [
            (self.messages[2], -0.36),
            (self.messages[3], -0.36)])

    @requires_models(Document)
    def test_bm25_all_zero_scores(self):
        for message in self.messages:
            Document.create(message=message)

        # Indeterminate order since all are 0.0. All phrases contain the word
        # faith, so there is no meaningful score.
        query = Document.search_bm25('faith', with_score=True)
        self.assertEqual([round(d.score, 2) for d in query], [-0.] * 5)

    def test_fts_delete_row(self):
        posts = [Post.create(message=msg) for msg in self.messages]
        ContentPost.rebuild()
        query = (ContentPost
                 .select(ContentPost, ContentPost.rank().alias('score'))
                 .where(ContentPost.match('believe'))
                 .order_by(ContentPost.rowid))
        self.assertMessages(query, [0, 3])

        query = (ContentPost
                 .select(ContentPost.rowid)
                 .order_by(ContentPost.rowid))
        for content_post in query:
            self.assertEqual(content_post.delete_instance(), 1)

        for post in posts:
            self.assertEqual(
                (ContentPost
                 .delete()
                 .where(ContentPost.message == post.message)
                 .execute()), 1)

        # None of the deletes were processed since the table is managed.
        self.assertEqual(ContentPost.select().count(), 5)

        documents = [Document.create(message=message) for message in
                     self.messages]
        self.assertEqual(Document.select().count(), 5)

        for document in documents:
            self.assertEqual(
                (Document
                 .delete()
                 .where(Document.message == document.message)
                 .execute()), 1)

        self.assertEqual(Document.select().count(), 0)

    def _create_multi_column(self):
        for c1, c2, c3, c4 in self.values:
            MultiColumn.create(c1=c1, c2=c2, c3=c3, c4=c4)

    @requires_models(MultiColumn)
    def test_fts_multi_column(self):
        def assertResults(term, expected):
            results = [(x.c4, round(x.score, 2))
                       for x in MultiColumn.search(term, with_score=True)]
            self.assertEqual(results, expected)

        self._create_multi_column()
        assertResults('bbbbb', [
            (2, -1.5),  # 1/2 + 1/1
            (1, -0.5)])  # 1/2

        # `ccccc` appears four times in `c1`, three times in `c2`.
        assertResults('ccccc', [
            (3, -.83),  # 2/4 + 1/3
            (1, -.58), # 1/4 + 1/3
            (4, -.33), # 1/3
            (2, -.25), # 1/4
        ])

        # `zzzzz` appears three times in c3.
        assertResults('zzzzz', [(1, -.67), (2, -.33)])

        self.assertEqual(
            [x.score for x in MultiColumn.search('ddddd', with_score=True)],
            [-.25, -.25, -.25, -.25])

    @requires_models(MultiColumn)
    def test_bm25(self):
        def assertResults(term, expected):
            query = MultiColumn.search_bm25(term, [1.0, 0, 0, 0], True)
            self.assertEqual(
                [(mc.c4, round(mc.score, 2)) for mc in query],
                expected)

        self._create_multi_column()
        MultiColumn.create(c1='aaaaa fffff', c4=5)

        assertResults('aaaaa', [(5, -0.39), (1, -0.3)])
        assertResults('fffff', [(5, -0.39), (3, -0.3)])
        assertResults('eeeee', [(2, -0.97)])

        # No column specified, use the first text field.
        query = MultiColumn.search_bm25('fffff', [1.0, 0, 0, 0], True)
        self.assertEqual([(mc.c4, round(mc.score, 2)) for mc in query], [
            (5, -0.39),
            (3, -0.3)])

        # Use helpers.
        query = (MultiColumn
                 .select(
                     MultiColumn.c4,
                     MultiColumn.bm25(1.0).alias('score'))
                 .where(MultiColumn.match('aaaaa'))
                 .order_by(SQL('score')))
        self.assertEqual([(mc.c4, round(mc.score, 2)) for mc in query], [
            (5, -0.39),
            (1, -0.3)])

        def assertAllColumns(term, expected):
            query = MultiColumn.search_bm25(term, with_score=True)
            self.assertEqual(
                [(mc.c4, round(mc.score, 2)) for mc in query],
                expected)

        assertAllColumns('aaaaa ddddd', [(1, -1.08)])
        assertAllColumns('zzzzz ddddd', [(1, -0.36), (2, -0.34)])
        assertAllColumns('ccccc bbbbb ddddd', [(2, -1.39), (1, -0.3)])

    @skip_unless(CYTHON_EXTENSION, 'requires _sqlite_udf c extension')
    def test_bm25f(self):
        def assertResults(term, expected):
            query = MultiColumn.search_bm25f(term, [1.0, 0, 0, 0], True)
            self.assertEqual(
                [(mc.c4, round(mc.score, 2)) for mc in query],
                expected)

        self._create_multi_column()
        MultiColumn.create(c1='aaaaa fffff', c4=5)

        assertResults('aaaaa', [(5, -0.76), (1, -0.62)])
        assertResults('fffff', [(5, -0.76), (3, -0.65)])
        assertResults('eeeee', [(2, -2.13)])

        # No column specified, use the first text field.
        query = MultiColumn.search_bm25f('aaaaa OR fffff', [1., 3., 0, 0], 1)
        self.assertEqual([(mc.c4, round(mc.score, 2)) for mc in query], [
            (1, -14.18),
            (5, -12.01),
            (3, -11.48)])

    @skip_unless(CYTHON_EXTENSION, 'requires _sqlite_udf c extension')
    def test_lucene(self):
        for message in self.messages:
            Document.create(message=message)

        def assertResults(term, expected, sort_cleaned=False):
            query = Document.search_lucene(term, with_score=True)
            cleaned = [
                (round(doc.score, 3), ' '.join(doc.message.split()[:2]))
                for doc in query]
            if sort_cleaned:
                cleaned = sorted(cleaned)
            self.assertEqual(cleaned, expected)

        assertResults('things', [
            (-0.166, 'Faith has'),
            (-0.137, 'Be faithful')])

        assertResults('faith', [
            (0.036, 'All who'),
            (0.042, 'Faith has'),
            (0.047, 'A faith'),
            (0.049, 'Be faithful'),
            (0.049, 'Faith consists')], sort_cleaned=True)

    def _test_fts_auto(self, ModelClass):
        posts = []
        for message in self.messages:
            posts.append(Post.create(message=message))

        # Nothing matches, index is not built.
        pq = ModelClass.select().where(ModelClass.match('faith'))
        self.assertEqual(list(pq), [])

        ModelClass.rebuild()
        ModelClass.optimize()

        # it will stem faithful -> faith b/c we use the porter tokenizer
        pq = (ModelClass
              .select()
              .where(ModelClass.match('faith'))
              .order_by(ModelClass.rowid))
        self.assertMessages(pq, range(len(self.messages)))

        pq = (ModelClass
              .select()
              .where(ModelClass.match('believe'))
              .order_by(ModelClass.rowid))
        self.assertMessages(pq, [0, 3])

        pq = (ModelClass
              .select()
              .where(ModelClass.match('thin*'))
              .order_by(ModelClass.rowid))
        self.assertMessages(pq, [2, 4])

        pq = (ModelClass
              .select()
              .where(ModelClass.match('"it is"'))
              .order_by(ModelClass.rowid))
        self.assertMessages(pq, [2, 3])

        pq = ModelClass.search('things', with_score=True)
        self.assertEqual([(x.message, x.score) for x in pq], [
            (self.messages[4], -2.0 / 3),
            (self.messages[2], -1.0 / 3),
        ])

        pq = (ModelClass
              .select(ModelClass.rank())
              .where(ModelClass.match('faithful'))
              .tuples())
        self.assertEqual([x[0] for x in pq], [-.2] * 5)

        pq = (ModelClass
              .search('faithful', with_score=True)
              .dicts())
        self.assertEqual([x['score'] for x in pq], [-.2] * 5)

    def test_fts_auto_model(self):
        self._test_fts_auto(ContentPost)

    def test_fts_auto_table_name(self):
        self._test_fts_auto(ContentPostMessage)

    def test_weighting(self):
        self._create_multi_column()
        def assertResults(method, term, weights, expected):
            results = [
                (x.c4, round(x.score, 2))
                for x in method(term, weights=weights, with_score=True)]
            self.assertEqual(results, expected)

        assertResults(MultiColumn.search, 'bbbbb', None, [
            (2, -1.5),  # 1/2 + 1/1
            (1, -0.5),  # 1/2
        ])
        assertResults(MultiColumn.search, 'bbbbb', [1., 5., 0.], [
            (2, -5.5),  # 1/2 + (5 * 1/1)
            (1, -0.5),  # 1/2 + (5 * 0)
        ])
        assertResults(MultiColumn.search, 'bbbbb', [1., .5, 0.], [
            (2, -1.),  # 1/2 + (.5 * 1/1)
            (1, -0.5),  # 1/2 + (.5 * 0)
        ])
        assertResults(MultiColumn.search, 'bbbbb', [1., -1., 0.], [
            (1, -0.5),  # 1/2 + (-1 * 0)
            (2, 0.5),  # 1/2 + (-1 * 1/1)
        ])

        # BM25
        assertResults(MultiColumn.search_bm25, 'bbbbb', None, [
            (2, -0.85),
            (1, -0.)])
        assertResults(MultiColumn.search_bm25, 'bbbbb', [1., 5., 0.], [
            (2, -4.24),
            (1, -0.)])
        assertResults(MultiColumn.search_bm25, 'bbbbb', [1., .5, 0.], [
            (2, -0.42),
            (1, -0.)])
        assertResults(MultiColumn.search_bm25, 'bbbbb', [1., -1., 0.], [
            (1, -0.),
            (2, 0.85)])

    @requires_models(SearchWeight)
    def test_search_dict_weights(self):
        # The dict form of `weights` must skip the rowid pk and match the list
        # form.
        SearchWeight.create(title='alpha alpha', body='common words')  # 1
        SearchWeight.create(title='common words', body='alpha alpha')  # 2
        SearchWeight.create(title='common', body='words')              # 3

        def results(weights):
            return [(x.rowid, round(x.score, 5)) for x in
                    SearchWeight.search_bm25('alpha', weights=weights,
                                             with_score=True)]

        # Weighting the title 3x ranks the title match (rowid 1) ahead of the
        # body match (rowid 2). The dict forms must match the list form
        # exactly.
        by_list = results([3., 1.])
        self.assertEqual([rowid for rowid, _ in by_list], [1, 2])
        self.assertEqual(
            results({SearchWeight.title: 3., SearchWeight.body: 1.}),
            by_list)
        self.assertEqual(results({'title': 3., 'body': 1.}), by_list)

        # Weighting the body instead flips the ranking.
        self.assertEqual(
            [rowid for rowid, _ in results({'body': 3., 'title': 1.})], [2, 1])

    def test_fts_match_single_column(self):
        data = (
            ('m1c1 aaaa', 'm1c2 bbbb', 'm1c3 cccc'),
            ('m2c1 dddd', 'm2c2 eeee', 'm2c3 ffff'),
            ('m3c1 cccc', 'm3c2 bbbb', 'm3c3 aaaa'),
        )
        for c1, c2, c3 in data:
            MultiColumn.create(c1=c1, c2=c2, c3=c3, c4=0)

        def assertSearch(field, value, expected):
            query = (MultiColumn
                     .select()
                     .where(field.match(value))
                     .order_by(MultiColumn.c1))
            self.assertEqual([mc.c1[:2] for mc in query], expected)

        assertSearch(MultiColumn.c1, 'aaaa', ['m1'])
        assertSearch(MultiColumn.c1, 'bbbb', [])
        assertSearch(MultiColumn.c1, 'cccc', ['m3'])
        assertSearch(MultiColumn.c2, 'bbbb', ['m1', 'm3'])
        assertSearch(MultiColumn.c2, 'eeee', ['m2'])
        assertSearch(MultiColumn.c3, 'cccc', ['m1'])
        assertSearch(MultiColumn.c3, 'aaaa', ['m3'])

    def test_fts_score_single_column(self):
        data = (
            ('m1c1 aaaa', 'm1c2 bbbb', 'm1c3 cccc'),
            ('m2c1 dddd', 'm2c2 eeee', 'm2c3 ffff'),
            ('m3c1 cccc', 'm3c2 bbbb aaaa', 'm3c3 aaaa aaaa'),
        )
        for c1, c2, c3 in data:
            MultiColumn.create(c1=c1, c2=c2, c3=c3, c4=0)

        def assertQueryScore(field, search_term, expected, *weights):
            rank = MultiColumn.bm25(*weights)
            query = (MultiColumn
                     .select(MultiColumn, rank.alias('score'))
                     .where(field.match(search_term))
                     .order_by(rank))
            results = [(r.c1[:2], round(r.score, 2)) for r in query]
            self.assertEqual(results, expected)

        assertQueryScore(MultiColumn.c1, 'aaaa', [('m1', -0.51)])
        assertQueryScore(MultiColumn.c1, 'dddd', [('m2', -0.51)])
        assertQueryScore(MultiColumn.c2, 'bbbb', [('m1', -0.), ('m3', -0.)])
        assertQueryScore(MultiColumn.c2, 'eeee', [('m2', -0.51)])
        assertQueryScore(MultiColumn.c3, 'aaaa', [('m3', -0.62)])

        assertQueryScore(MultiColumn.c1, 'aaaa', [('m1', -1.02)], 2., 0., 0.)
        assertQueryScore(MultiColumn.c2, 'bbbb', [('m1', -0.), ('m3', -0.)],
                         0., 1.0, 0.)
        assertQueryScore(MultiColumn.c2, 'eeee', [('m2', -1.02)], 0., 2., 0.)
        assertQueryScore(MultiColumn.c3, 'aaaa', [('m3', -0.31)], 0., 1., 0.5)

    @skip_unless(compile_option('enable_fts4'))
    @requires_models(MultiColumn)
    def test_match_column_queries(self):
        data = (
            ('alpha one', 'apple aspires to ace artsy beta launch'),
            ('beta two', 'beta boasts better broadcast over apple'),
            ('gamma three', 'gold gray green gamma ray delta data'),
            ('delta four', 'delta data indicates downturn for apple beta'),
        )
        MC = MultiColumn

        for i, (title, message) in enumerate(data):
            MC.create(c1=title, c2=message, c3='', c4=i)

        def assertQ(expr, idxscore):
            q = (MC
                 .select(MC, MC.bm25().alias('score'))
                 .where(expr)
                 .order_by(SQL('score'), MC.c4))
            self.assertEqual([(r.c4, round(r.score, 2)) for r in q], idxscore)

        # Single whitespace does not affect the mapping of col->term. We can
        # also store the column value in quotes if single-quotes are used.
        assertQ(MC.match('beta'), [(1, -0.85), (0, -0.), (3, -0.)])
        assertQ(MC.match('c1:beta'), [(1, -0.85)])
        assertQ(MC.match('c1: beta'), [(1, -0.85)])
        assertQ(MC.match('c1: ^bet*'), [(1, -0.85)])
        assertQ(MC.match('c1: \'beta\''), [(1, -0.85)])
        assertQ(MC.match('"beta"'), [(1, -0.85), (0, -0.), (3, -0.)])

        # Alternatively, just specify the column explicitly.
        assertQ(MC.c1.match('beta'), [(1, -0.85)])
        assertQ(MC.c1.match(' beta '), [(1, -0.85)])
        assertQ(MC.c1.match('"beta"'), [(1, -0.85)])
        assertQ(MC.c1.match('"^bet*"'), [(1, -0.85)])

        #                 apple   beta   delta   gamma
        # 0  |  alpha  |    X       X
        # 1  |  beta   |    X       X
        # 2  |  gamma  |                   X       X
        # 3  |  delta  |    X       X      X
        #
        assertQ(MC.match('delta NOT gamma'), [(3, -0.85)])
        assertQ(MC.match('delta NOT c2:gamma'), [(3, -0.85)])
        assertQ(MC.match('"delta"'), [(3, -0.85), (2, -0.)])
        assertQ(MC.match('c1:delta OR c2:delta'), [(3, -0.85), (2, -0.)])
        assertQ(MC.match('"^delta"'), [(3, -1.69)])

        assertQ(MC.match('(delta AND c2:apple) OR c1:alpha'),
                [(3, -0.85), (0, -0.85)])
        assertQ(MC.match('(c2:delta AND c2:apple) OR c1:alpha'),
                [(0, -0.85), (3, -0.)])
        assertQ(MC.match('c2:delta c2:apple OR c1:alpha'),
                [(0, -0.85), (3, -0.)])
        assertQ(MC.match('(c2:delta AND c2:apple) OR beta'),
                [(1, -0.85), (3, -0.), (0, -0.)])
        assertQ(MC.match('c2:delta AND (c2:apple OR c1:alpha)'),
                [(3, -0.)])

        # c2 apple (0,1,3) OR (...irrelevant...).
        assertQ(MC.match('c2:apple OR c1:alpha NOT delta'),
                [(0, -0.85), (1, -0.), (3, -0.)])
        assertQ(MC.match('c2:apple OR (c1:alpha NOT c2:delta)'),
                [(0, -0.85), (1, -0.), (3, -0.)])
        # c2 apple OR c1 alpha (0, 1, 3) AND NOT delta (2, 3) -> (0, 1).
        assertQ(MC.match('(c2:apple OR c1:alpha) NOT delta'),
                [(0, -0.85), (1, -0.)])


@skip_unless(FTS5Model.fts5_installed(), 'requires fts5')
class TestFTS5(BaseFTSTestCase, ModelTestCase):
    database = ext_database
    requires = [FTS5Test]
    test_corpus = (
        ('foo aa bb', 'aa bb cc ' * 10, 1),
        ('bar bb cc', 'bb cc dd ' * 9, 2),
        ('baze cc dd', 'cc dd ee ' * 8, 3),
        ('nug aa dd', 'bb cc ' * 7, 4))

    def setUp(self):
        super(TestFTS5, self).setUp()
        for title, data, misc in self.test_corpus:
            FTS5Test.create(title=title, data=data, misc=misc)

    def test_create_table(self):
        query = FTS5Test._schema._create_table()
        self.assertSQL(query, (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "fts5_test" USING fts5 '
            '("title", "data", "misc" UNINDEXED)'), [])

    def test_custom_fts5_command(self):
        merge_sql = FTS5Test._fts_cmd_sql('merge', rank=4)
        self.assertSQL(merge_sql, (
            'INSERT INTO "fts5_test" ("fts5_test", "rank") VALUES (?, ?)'),
            ['merge', 4])
        FTS5Test.merge(4)  # Runs without error.
        FTS5Test.automerge(64)  # fts5 accepts levels up to 64.
        self.assertRaises(ValueError, FTS5Test.automerge, 65)
        self.assertRaises(ValueError, FTS5Test.automerge, -1)

        FTS5Test.insert_many([{'title': 'k%08d' % i, 'data': 'v%08d' % i}
                              for i in range(100)]).execute()

        FTS5Test.integrity_check(rank=0)
        FTS5Test.optimize()

    def test_create_table_options(self):
        class Test1(FTS5Model):
            f1 = SearchField()
            f2 = SearchField(unindexed=True)
            f3 = SearchField()

            class Meta:
                database = self.database
                options = {
                    'prefix': (2, 3),
                    'tokenize': 'porter unicode61',
                    'content': Post,
                    'content_rowid': Post.id}

        query = Test1._schema._create_table()
        self.assertSQL(query, (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "test1" USING fts5 ('
            '"f1", "f2" UNINDEXED, "f3", '
            'content="post", content_rowid="id", '
            'prefix=\'2,3\', tokenize="porter unicode61")'), [])

        # fts5 must accept the generated DDL (content tbl resolved lazily).
        self.database.create_tables([Test1])
        self.database.drop_tables([Test1])

    def test_content_option_rejects_field(self):
        class BadIndex(FTS5Model):
            message = SearchField()

            class Meta:
                database = self.database
                options = {'content': Post.message}

        self.assertRaises(ImproperlyConfigured, BadIndex._schema._create_table)

    def assertResults(self, query, expected, scores=False, alias='score'):
        if scores:
            results = [(obj.title, round(getattr(obj, alias), 7))
                       for obj in query]
        else:
            results = [obj.title for obj in query]
        self.assertEqual(results, expected)

    def test_search(self):
        query = FTS5Test.search('bb')
        self.assertSQL(query, (
            'SELECT "t1"."rowid", "t1"."title", "t1"."data", "t1"."misc" '
            'FROM "fts5_test" AS "t1" '
            'WHERE ("fts5_test" MATCH ?) ORDER BY rank'), ['bb'])
        self.assertResults(query, ['nug aa dd', 'foo aa bb', 'bar bb cc'])

        self.assertResults(FTS5Test.search('baze OR dd'),
                           ['baze cc dd', 'bar bb cc', 'nug aa dd'])

    @requires_models(SearchWeight5)
    def test_search_dict_weights_unindexed(self):
        # FTS5 bm25() weights are positional across all columns, including
        # UNINDEXED ones, so a dict weight on `body` must not land on `extra`.
        # The two rows below are rowid 1 and rowid 2.
        SearchWeight5.create(title='alpha', extra='junk', body='common')
        SearchWeight5.create(title='common', extra='junk', body='alpha')

        def order(weights):
            return [x.rowid for x in
                    SearchWeight5.search_bm25('alpha', weights=weights)]

        # Positional list over (title, extra, body): weighting body ranks the
        # body match (rowid 2) first. The dict forms must match.
        by_list = order([1., 1., 5.])
        self.assertEqual(by_list, [2, 1])
        self.assertEqual(order({SearchWeight5.body: 5.}), by_list)
        self.assertEqual(order({'body': 5.}), by_list)
        # Equal weights leave the default ordering.
        self.assertEqual(order([1., 1., 1.]), [1, 2])

    @requires_models(FTS5Document)
    def test_fts_manual(self):
        messages = [FTS5Document.create(message=message)
                    for message in self.messages]
        query = (FTS5Document
                 .select()
                 .where(FTS5Document.match('believe'))
                 .order_by(FTS5Document.rowid))
        self.assertMessages(query, [0, 3])

        query = FTS5Document.search('believe')
        self.assertMessages(query, [3, 0])

        # Test SQLite's built-in ranking algorithm (bm25). The results should
        # be comparable to our user-defined implementation.
        query = FTS5Document.search('things', with_score=True)
        self.assertEqual([(d.message, round(d.score, 2)) for d in query], [
            (self.messages[4], -0.45),
            (self.messages[2], -0.37)])

        # Another test of bm25 ranking.
        query = FTS5Document.search_bm25('believe', with_score=True)
        self.assertEqual([(d.message, round(d.score, 2)) for d in query], [
            (self.messages[3], -0.49),
            (self.messages[0], -0.36)])

        query = FTS5Document.search_bm25('god faith', with_score=True)
        self.assertEqual([(d.message, round(d.score, 2)) for d in query], [
            (self.messages[1], -0.93)])

        query = FTS5Document.search_bm25('"it is"', with_score=True)
        self.assertEqual([(d.message, round(d.score, 2)) for d in query], [
            (self.messages[2], -0.37),
            (self.messages[3], -0.37)])

    def test_match_column_queries(self):
        data = (
            ('alpha one', 'apple aspires to ace artsy beta launch'),
            ('beta two', 'beta boasts better broadcast over apple'),
            ('gamma three', 'gold gray green gamma ray delta data'),
            ('delta four', 'delta data indicates downturn for apple beta'),
        )
        FT = FTS5Test

        for i, (title, message) in enumerate(data):
            FT.create(title=title, data=message, misc=str(i))

        def assertQ(expr, idxscore):
            q = (FT
                 .select(FT, FT.bm25().alias('score'))
                 .where(expr)
                 .order_by(SQL('score'), FT.misc.cast('int')))
            self.assertEqual([(int(r.misc), round(r.score, 2)) for r in q],
                             idxscore)

        # Single whitespace does not affect the mapping of col->term. We can
        # also store the column value in quotes if single-quotes are used.
        assertQ(FT.match('beta'), [(1, -0.74), (0, -0.57), (3, -0.57)])
        assertQ(FT.match('title: beta'), [(1, -2.08)])
        assertQ(FT.match('title: ^bet*'), [(1, -2.08)])
        assertQ(FT.match('title: "beta"'), [(1, -2.08)])
        assertQ(FT.match('"beta"'), [(1, -0.74), (0, -0.57), (3, -0.57)])

        # Alternatively, just specify the column explicitly.
        assertQ(FT.title.match('beta'), [(1, -2.08)])
        assertQ(FT.title.match(' beta '), [(1, -2.08)])
        assertQ(FT.title.match('"beta"'), [(1, -2.08)])
        assertQ(FT.title.match('^bet*'), [(1, -2.08)])
        assertQ(FT.title.match('"^bet*"'), [])  # No wildcards in quotes!

        #                 apple   beta   delta   gamma
        # 0  |  alpha  |    X       X
        # 1  |  beta   |    X       X
        # 2  |  gamma  |                   X       X
        # 3  |  delta  |    X       X      X
        #
        assertQ(FT.match('delta NOT gamma'), [(3, -1.53)])
        assertQ(FT.match('delta NOT data:gamma'), [(3, -1.53)])
        assertQ(FT.match('"delta"'), [(3, -1.53), (2, -1.2)])
        assertQ(FT.match('title:delta OR data:delta'), [(3, -3.21), (2, -1.2)])
        assertQ(FT.match('"^delta"'), [(3, -1.53), (2, -1.2)])  # Different.
        assertQ(FT.match('^delta'), [(3, -2.57)])  # Different from FTS4.

        assertQ(FT.match('(delta AND data:apple) OR title:alpha'),
                [(3, -2.09), (0, -2.02)])
        assertQ(FT.match('(data:delta AND data:apple) OR title:alpha'),
                [(0, -2.02), (3, -1.76)])
        assertQ(FT.match('data:delta data:apple OR title:alpha'),
                [(0, -2.02), (3, -1.76)])
        assertQ(FT.match('(data:delta AND data:apple) OR beta'),
                [(3, -2.33), (1, -0.74), (0, -0.57)])
        assertQ(FT.match('data:delta AND (data:apple OR title:alpha)'),
                [(3, -1.76)])

        # data apple (0,1,3) OR (...irrelevant...).
        assertQ(FT.match('data:apple OR title:alpha NOT delta'),
                [(0, -2.58), (1, -0.58), (3, -0.57)])
        assertQ(FT.match('data:apple OR (title:alpha NOT data:delta)'),
                [(0, -2.58), (1, -0.58), (3, -0.57)])
        # data apple OR title alpha (0, 1, 3) AND NOT delta (2, 3) -> (0, 1).
        assertQ(FT.match('(data:apple OR title:alpha) NOT delta'),
                [(0, -2.58), (1, -0.58)])

    def test_highlight_function(self):
        query = (FTS5Test
                 .search('dd')
                 .select(FTS5Test.title.highlight('[', ']').alias('hi')))
        accum = [row.hi for row in query]
        self.assertEqual(accum, ['baze cc [dd]', 'bar bb cc', 'nug aa [dd]'])

        query = (FTS5Test
                 .search('bb')
                 .select(FTS5Test.data.highlight('[', ']').alias('hi')))
        accum = [row.hi[:7] for row in query]
        self.assertEqual(accum, ['[bb] cc', 'aa [bb]', '[bb] cc'])

    def test_snippet_function(self):
        snip = FTS5Test.data.snippet('[', ']', max_tokens=5).alias('snip')
        query = FTS5Test.search('dd').select(snip)
        accum = [row.snip for row in query]
        self.assertEqual(accum, [
            'cc [dd] ee cc [dd]...',
            'bb cc [dd] bb cc...',
            'bb cc bb cc bb...'])

    @requires_models(Post, ContentPost5)
    def test_fts5_external_content(self):
        for message in self.messages:
            Post.create(message=message)
        ContentPost5.rebuild()
        ContentPost5.integrity_check(rank=1)

        query = ContentPost5.select().where(ContentPost5.match('faith'))
        self.assertEqual(sorted(r.rowid for r in query), [1, 2, 4, 5])

        # Column values are read through from the content table.
        query = ContentPost5.search('nothing')
        self.assertEqual([r.message for r in query], [self.messages[0]])

        # Out-of-band update: the index is stale but reads are current.
        Post.update(message='replaced entirely').where(Post.id == 1).execute()
        query = ContentPost5.select().where(ContentPost5.match('nothing'))
        self.assertEqual([(r.rowid, r.message) for r in query],
                         [(1, 'replaced entirely')])

        ContentPost5.integrity_check(rank=0)  # Does not verify content.
        self.assertRaises(DatabaseError, ContentPost5.integrity_check, 1)

        # Resync using the fts5 delete command w/the old values.
        ContentPost5._fts_cmd('delete', rowid=1, message=self.messages[0])
        ContentPost5.insert({'rowid': 1, 'message': 'replaced entirely'}).execute()
        ContentPost5.integrity_check(rank=1)
        query = ContentPost5.select().where(ContentPost5.match('faith'))
        self.assertEqual(sorted(r.rowid for r in query), [2, 4, 5])

    @requires_models(Post, ContentPost5)
    def test_fts5_delete_command_external(self):
        for message in self.messages:
            Post.create(message=message)
        ContentPost5.rebuild()

        # Remove a row whose content row is already gone, supplying the
        # values as they were indexed.
        Post.delete_by_id(1)
        ContentPost5.delete_command(1, message=self.messages[0])
        ContentPost5.integrity_check(rank=1)
        query = ContentPost5.select().where(ContentPost5.match('faith'))
        self.assertEqual(sorted(r.rowid for r in query), [2, 4, 5])

        # An update is the delete command w/the old values followed by a
        # plain insert of the new ones.
        Post.update(message='changed entirely').where(Post.id == 2).execute()
        ContentPost5.delete_command(2, message=self.messages[1])
        ContentPost5.insert({'rowid': 2, 'message': 'changed entirely'}).execute()
        ContentPost5.integrity_check(rank=1)
        query = ContentPost5.select().where(ContentPost5.match('changed'))
        self.assertEqual([(r.rowid, r.message) for r in query],
                         [(2, 'changed entirely')])
        query = ContentPost5.select().where(ContentPost5.match('faith'))
        self.assertEqual(sorted(r.rowid for r in query), [4, 5])

        # All indexed columns are required and unknown columns are rejected.
        # Either mistake would otherwise corrupt the index silently.
        self.assertRaises(ValueError, ContentPost5.delete_command, 3)
        self.assertRaises(ValueError, ContentPost5.delete_command, 3,
                          message=self.messages[2], other='x')
        ContentPost5.integrity_check(rank=1)

    @requires_models(FTS5DeleteCommand)
    def test_fts5_delete_command_contentless(self):
        FD = FTS5DeleteCommand
        FD.insert({'rowid': 1, 'body': 'alpha beta', 'note': 'x'}).execute()
        FD.insert({'rowid': 2, 'body': 'beta gamma', 'note': 'y'}).execute()

        # Plain DELETE is refused on a contentless table, but the delete
        # command works when the original values are supplied. The attribute
        # name maps to the underlying column and unindexed columns may be
        # omitted.
        self.assertRaises(OperationalError,
                          FD.delete().where(FD.rowid == 1).execute)
        FD.delete_command(1, body='alpha beta')
        self.assertEqual([r.rowid for r in FD.search('beta')], [2])
        FD.integrity_check()

    @skip_unless_db(lambda db: db.server_version >= (3, 43), 'sqlite >= 3.43')
    @requires_models(FTS5Contentless)
    def test_fts5_contentless_delete(self):
        FC = FTS5Contentless
        FC.insert({'rowid': 1, 'title': 'alpha one', 'data': 'first'}).execute()
        FC.insert({'rowid': 2, 'title': 'beta two', 'data': 'second'}).execute()

        # Only the rowid is stored, other columns select as NULL.
        query = FC.search('alpha')
        self.assertEqual([(r.rowid, r.title) for r in query], [(1, None)])

        self.assertEqual(FC.delete().where(FC.rowid == 1).execute(), 1)
        self.assertEqual([r.rowid for r in FC.search('alpha')], [])

        # Updates must assign all indexed columns together.
        FC.update(title='beta renamed', data='2nd').where(FC.rowid == 2).execute()
        self.assertEqual([r.rowid for r in FC.search('renamed')], [2])
        self.assertRaises(
            OperationalError,
            FC.update(title='partial').where(FC.rowid == 2).execute)

    @skip_unless_db(lambda db: db.server_version >= (3, 47), 'sqlite >= 3.47')
    @requires_models(FTS5ContentlessUnindexed)
    def test_fts5_contentless_unindexed(self):
        FC = FTS5ContentlessUnindexed
        FC.insert({'rowid': 1, 'title': 'hello world', 'meta': 'kept'}).execute()
        query = FC.search('hello')
        self.assertEqual([(r.rowid, r.title, r.meta) for r in query],
                         [(1, None, 'kept')])

        # Stored unindexed columns may be updated independently.
        FC.update(meta='changed').where(FC.rowid == 1).execute()
        self.assertEqual([r.meta for r in FC.select()], ['changed'])

    @requires_models(FTS5Vocab, FTS5VocabCol, FTS5VocabInstance)
    def test_vocab_model(self):
        self.assertEqual(
            [v._meta.table_name
             for v in (FTS5Vocab, FTS5VocabCol, FTS5VocabInstance)],
            ['fts5_test_v', 'fts5_test_v_col', 'fts5_test_v_instance'])

        query = FTS5Vocab.select().order_by(FTS5Vocab.term)
        self.assertEqual([(v.term, v.doc, v.cnt) for v in query], [
            ('aa', 2, 12), ('bar', 1, 1), ('baze', 1, 1), ('bb', 3, 28),
            ('cc', 4, 36), ('dd', 3, 19), ('ee', 1, 8), ('foo', 1, 1),
            ('nug', 1, 1)])

        query = (FTS5VocabCol
                 .select()
                 .where(FTS5VocabCol.term == 'aa')
                 .order_by(FTS5VocabCol.col))
        self.assertEqual([(v.term, v.col, v.doc, v.cnt) for v in query],
                         [('aa', 'data', 1, 10), ('aa', 'title', 2, 2)])

        query = (FTS5VocabInstance
                 .select()
                 .where(FTS5VocabInstance.term == 'foo'))
        self.assertEqual([(v.term, v.doc, v.col, v.offset) for v in query],
                         [('foo', 1, 'title', 0)])

    def test_clean_query(self):
        cases = (
            ('test', 'test'),
            ('"test"', '"test"'),
            ('"test\u2022"', '"test\u2022"'),
            ('test\u2022', 'test\u2022'),
            ('test-', 'test\x1a'),
            ('"test-"', '"test-"'),
            ('\\"test-', '\x1a test\x1a'),
            ('--test--', '\x1a\x1atest\x1a\x1a'),
            ('-test- "-test-"', '\x1atest\x1a "-test-"'),
        )
        for a, b in cases:
            self.assertEqual(FTS5Test.clean_query(a), b)


class TestRowIDField(ModelTestCase):
    database = ext_database
    requires = [RowIDModel]

    def test_model_meta(self):
        self.assertEqual(RowIDModel._meta.sorted_field_names, ['rowid', 'data'])
        self.assertEqual(RowIDModel._meta.primary_key.name, 'rowid')
        self.assertTrue(RowIDModel._meta.auto_increment)

    def test_rowid_field(self):
        r1 = RowIDModel.create(data=10)
        self.assertEqual(r1.rowid, 1)
        self.assertEqual(r1.data, 10)

        r2 = RowIDModel.create(data=20)
        self.assertEqual(r2.rowid, 2)
        self.assertEqual(r2.data, 20)

        query = RowIDModel.select().where(RowIDModel.rowid == 2)
        self.assertSQL(query, (
            'SELECT "t1"."rowid", "t1"."data" '
            'FROM "row_id_model" AS "t1" '
            'WHERE ("t1"."rowid" = ?)'), [2])
        r_db = query.get()
        self.assertEqual(r_db.rowid, 2)
        self.assertEqual(r_db.data, 20)

        r_db2 = query.columns(RowIDModel.rowid, RowIDModel.data).get()
        self.assertEqual(r_db2.rowid, 2)
        self.assertEqual(r_db2.data, 20)

    def test_insert_with_rowid(self):
        RowIDModel.insert({RowIDModel.rowid: 5, RowIDModel.data: 1}).execute()
        self.assertEqual(5, RowIDModel.select(RowIDModel.rowid).first().rowid)

    def test_insert_many_with_rowid_without_field_validation(self):
        RowIDModel.insert_many([{RowIDModel.rowid: 5, RowIDModel.data: 1}]).execute()
        self.assertEqual(5, RowIDModel.select(RowIDModel.rowid).first().rowid)


class TDecModel(TestModel):
    value = TDecimalField(max_digits=24, decimal_places=16, auto_round=True)


class TestTDecimalField(ModelTestCase):
    database = ext_database
    requires = [TDecModel]

    def test_tdecimal_field(self):
        value = D('12345678.0123456789012345')
        value_ov = D('12345678.012345678901234567890123456789')

        td1 = TDecModel.create(value=value)
        td2 = TDecModel.create(value=value_ov)

        td1_db = TDecModel.get(TDecModel.id == td1.id)
        self.assertEqual(td1_db.value, value)

        td2_db = TDecModel.get(TDecModel.id == td2.id)
        self.assertEqual(td2_db.value, D('12345678.0123456789012346'))


class TestISODateTimeField(ModelTestCase):
    # ISODateTimeField is a sqlite_ext field.
    database = get_in_memory_db()
    requires = [DT]

    def test_aware_datetimes(self):
        class _UTC(datetime.tzinfo):
            def utcoffset(self, dt): return datetime.timedelta(0)
            def tzname(self, dt): return "UTC"
            def dst(self, dt): return datetime.timedelta(0)

        UTC = _UTC()

        d1 = datetime.datetime(2026, 1, 2, 3, 4, 5)
        d2 = d1.astimezone(UTC)

        dt = DT.create(key='k1', d=d1, iso=d2)
        self.assertEqual(dt.d, d1)
        self.assertEqual(dt.iso, d2)

        dt = DT['k1']
        self.assertEqual(dt.d, d1)
        self.assertEqual(dt.iso, d2)

        raw = self.database.execute_sql('select * from dt').fetchone()
        self.assertEqual(raw, ('k1', str(d1), d2.isoformat()))

    def test_string_input(self):
        d_obj = datetime.datetime(2026, 1, 2, 3, 4, 5)
        DT.create(key='k2', d='2026-01-02 03:04:05',
                  iso='2026-01-02 03:04:05')
        dt = DT['k2']
        self.assertEqual(dt.iso, d_obj)

        # String input is normalized to isoformat on write.
        raw = self.database.execute_sql(
            'select iso from dt where key = ?', ('k2',)).fetchone()
        self.assertEqual(raw, ('2026-01-02T03:04:05',))

        query = DT.select().where(DT.iso >= '2026-01-01')
        self.assertEqual([d.key for d in query], ['k2'])
