import os
import sys

from peewee import *
from peewee import sqlite3
from playhouse.sqlite_ext import *
from playhouse._sqlite_ext import TableFunction

from .base import BaseTestCase
from .base import ModelTestCase
from .base import TestModel
from .base import requires_models
from .base import skip_case_unless
from .base import skip_if
from .sqlite_helpers import json_installed


database = SqliteExtDatabase(':memory:', c_extensions=False, timeout=0.1)


CLOSURE_EXTENSION = os.environ.get('PEEWEE_CLOSURE_EXTENSION')
if not CLOSURE_EXTENSION and os.path.exists('closure.so'):
    CLOSURE_EXTENSION = 'closure.so'

LSM_EXTENSION = os.environ.get('LSM_EXTENSION')
if not LSM_EXTENSION and os.path.exists('lsm.so'):
    LSM_EXTENSION = 'lsm.so'

try:
    from playhouse._sqlite_ext import peewee_rank
    CYTHON_EXTENSION = True
except ImportError:
    CYTHON_EXTENSION = False


class WeightedAverage(object):
    def __init__(self):
        self.total = 0.
        self.count = 0.

    def step(self, value, weight=None):
        weight = weight or 1.
        self.total += weight
        self.count += (weight * value)

    def finalize(self):
        if self.total != 0.:
            return self.count / self.total
        return 0.

def _cmp(l, r):
    if l < r:
        return -1
    return 1 if r < l else 0

def collate_reverse(s1, s2):
    return -_cmp(s1, s2)

@database.collation()
def collate_case_insensitive(s1, s2):
    return _cmp(s1.lower(), s2.lower())

def title_case(s): return s.title()

@database.func()
def rstrip(s, n):
    return s.rstrip(n)

database.register_aggregate(WeightedAverage, 'weighted_avg', 1)
database.register_aggregate(WeightedAverage, 'weighted_avg2', 2)
database.register_collation(collate_reverse)
database.register_function(title_case)


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
        options = {'tokenize': 'porter', 'content': Post.message}


class Document(FTSModel, TestModel):
    message = TextField()
    class Meta:
        options = {'tokenize': 'porter'}


class MultiColumn(FTSModel, TestModel):
    c1 = TextField()
    c2 = TextField()
    c3 = TextField()
    c4 = IntegerField()
    class Meta:
        options = {'tokenize': 'porter'}


class RowIDModel(TestModel):
    rowid = RowIDField()
    data = IntegerField()


class APIData(TestModel):
    data = JSONField()
    value = TextField()


class Metadata(TestModel):
    data = JSONField()


class KeyData(TestModel):
    key = TextField()
    data = JSONField()


class Values(TestModel):
    klass = IntegerField()
    value = FloatField()
    weight = FloatField()


class FTS5Test(FTS5Model):
    title = SearchField()
    data = SearchField()
    misc = SearchField(unindexed=True)


class Series(TableFunction):
    columns = ['value']
    params = ['start', 'stop', 'step']
    name = 'series'

    def initialize(self, start=0, stop=None, step=1):
        self.start = start
        self.stop = stop or float('inf')
        self.step = step
        self.curr = self.start

    def iterate(self, idx):
        if self.curr > self.stop:
            raise StopIteration

        ret = self.curr
        self.curr += self.step
        return (ret,)


class RegexSearch(TableFunction):
    columns = ['match']
    params = ['regex', 'search_string']
    name = 'regex_search'

    def initialize(self, regex=None, search_string=None):
        if regex and search_string:
            self._iter = re.finditer(regex, search_string)
        else:
            self._iter = None

    def iterate(self, idx):
        # We do not need `idx`, so just ignore it.
        if self._iter is None:
            raise StopIteration
        else:
            return (next(self._iter).group(0),)


class Split(TableFunction):
    params = ['data']
    columns = ['part']
    name = 'str_split'

    def initialize(self, data=None):
        self._parts = data.split()
        self._idx = 0

    def iterate(self, idx):
        if self._idx < len(self._parts):
            result = (self._parts[self._idx],)
            self._idx += 1
            return result
        raise StopIteration


@skip_case_unless(sqlite3.sqlite_version_info[:2] >= (3, 9))
class TestTableFunction(BaseTestCase):
    def setUp(self):
        super(TestTableFunction, self).setUp()
        self.conn = sqlite3.connect(':memory:')

    def tearDown(self):
        super(TestTableFunction, self).tearDown()
        self.conn.close()

    def test_split(self):
        Split.register(self.conn)
        curs = self.conn.execute('select part from str_split(?) order by part '
                                 'limit 3', ('well hello huey and zaizee',))
        self.assertEqual([row for row, in curs.fetchall()],
                         ['and', 'hello', 'huey'])

    def test_split_tbl(self):
        Split.register(self.conn)
        self.conn.execute('create table post (content TEXT);')
        self.conn.execute('insert into post (content) values (?), (?), (?)',
                          ('huey secret post',
                           'mickey message',
                           'zaizee diary'))
        curs = self.conn.execute('SELECT * FROM post, str_split(post.content)')
        results = curs.fetchall()
        self.assertEqual(results, [
            ('huey secret post', 'huey'),
            ('huey secret post', 'secret'),
            ('huey secret post', 'post'),
            ('mickey message', 'mickey'),
            ('mickey message', 'message'),
            ('zaizee diary', 'zaizee'),
            ('zaizee diary', 'diary'),
        ])

    def test_series(self):
        Series.register(self.conn)

        def assertSeries(params, values, extra_sql=''):
            param_sql = ', '.join('?' * len(params))
            sql = 'SELECT * FROM series(%s)' % param_sql
            if extra_sql:
                sql = ' '.join((sql, extra_sql))
            curs = self.conn.execute(sql, params)
            self.assertEqual([row for row, in curs.fetchall()], values)

        assertSeries((0, 10, 2), [0, 2, 4, 6, 8, 10])
        assertSeries((5, None, 20), [5, 25, 45, 65, 85], 'LIMIT 5')
        assertSeries((4, 0, -1), [4, 3, 2], 'LIMIT 3')
        assertSeries((3, 5, 3), [3])
        assertSeries((3, 3, 1), [3])

    def test_series_tbl(self):
        Series.register(self.conn)
        self.conn.execute('CREATE TABLE nums (id INTEGER PRIMARY KEY)')
        self.conn.execute('INSERT INTO nums DEFAULT VALUES;')
        self.conn.execute('INSERT INTO nums DEFAULT VALUES;')
        curs = self.conn.execute(
            'SELECT * FROM nums, series(nums.id, nums.id + 2)')
        results = curs.fetchall()
        self.assertEqual(results, [
            (1, 1), (1, 2), (1, 3),
            (2, 2), (2, 3), (2, 4)])

        curs = self.conn.execute(
            'SELECT * FROM nums, series(nums.id) LIMIT 3')
        results = curs.fetchall()
        self.assertEqual(results, [(1, 1), (1, 2), (1, 3)])

    def test_regex(self):
        RegexSearch.register(self.conn)

        def assertResults(regex, search_string, values):
            sql = 'SELECT * FROM regex_search(?, ?)'
            curs = self.conn.execute(sql, (regex, search_string))
            self.assertEqual([row for row, in curs.fetchall()], values)

        assertResults(
            '[0-9]+',
            'foo 123 45 bar 678 nuggie 9.0',
            ['123', '45', '678', '9', '0'])
        assertResults(
            '[\w]+@[\w]+\.[\w]{2,3}',
            ('Dear charlie@example.com, this is nug@baz.com. I am writing on '
             'behalf of zaizee@foo.io. He dislikes your blog.'),
            ['charlie@example.com', 'nug@baz.com', 'zaizee@foo.io'])
        assertResults(
            '[a-z]+',
            '123.pDDFeewXee',
            ['p', 'eew', 'ee'])
        assertResults(
            '[0-9]+',
            'hello',
            [])

    def test_regex_tbl(self):
        messages = (
            'hello foo@example.fap, this is nuggie@example.fap. How are you?',
            'baz@example.com wishes to let charlie@crappyblog.com know that '
            'huey@example.com hates his blog',
            'testing no emails.',
            '')
        RegexSearch.register(self.conn)

        self.conn.execute('create table posts (id integer primary key, msg)')
        self.conn.execute('insert into posts (msg) values (?), (?), (?), (?)',
                          messages)
        cur = self.conn.execute('select posts.id, regex_search.rowid, regex_search.match '
                                'FROM posts, regex_search(?, posts.msg)',
                                ('[\w]+@[\w]+\.\w{2,3}',))
        results = cur.fetchall()
        self.assertEqual(results, [
            (1, 1, 'foo@example.fap'),
            (1, 2, 'nuggie@example.fap'),
            (2, 3, 'baz@example.com'),
            (2, 4, 'charlie@crappyblog.com'),
            (2, 5, 'huey@example.com'),
        ])


@skip_case_unless(json_installed)
class TestJSONField(ModelTestCase):
    database = database
    requires = [APIData, Metadata]
    test_data = [
        {'metadata': {'tags': ['python', 'sqlite']},
         'title': 'My List of Python and SQLite Resources',
         'url': 'http://charlesleifer.com/blog/my-list-of-python-and-sqlite-resources/'},
        {'metadata': {'tags': ['nosql', 'python', 'sqlite', 'cython']},
         'title': "Using SQLite4's LSM Storage Engine as a Stand-alone NoSQL Database with Python",
         'url': 'http://charlesleifer.com/blog/using-sqlite4-s-lsm-storage-engine-as-a-stand-alone-nosql-database-with-python/'},
        {'metadata': {'tags': ['sqlite', 'search', 'python', 'peewee']},
         'title': 'Building the SQLite FTS5 Search Extension',
         'url': 'http://charlesleifer.com/blog/building-the-sqlite-fts5-search-extension/'},
        {'metadata': {'tags': ['nosql', 'python', 'unqlite', 'cython']},
         'title': 'Introduction to the fast new UnQLite Python Bindings',
         'url': 'http://charlesleifer.com/blog/introduction-to-the-fast-new-unqlite-python-bindings/'},
        {'metadata': {'tags': ['python', 'walrus', 'redis', 'nosql']},
         'title': 'Alternative Redis-Like Databases with Python',
         'url': 'http://charlesleifer.com/blog/alternative-redis-like-databases-with-python/'},
    ]

    def setUp(self):
        super(TestJSONField, self).setUp()
        for entry in self.test_data:
            APIData.create(data=entry, value=entry['title'])
        self.Q = APIData.select().order_by(APIData.id)

    def test_schema(self):
        self.assertSQL(APIData._schema._create_table(), (
            'CREATE TABLE IF NOT EXISTS "apidata" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"data" JSON NOT NULL, '
            '"value" TEXT NOT NULL)'), [])

        self.assertSQL(Metadata._schema._create_table(), (
            'CREATE TABLE IF NOT EXISTS "metadata" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"data" JSON NOT NULL)'), [])

    def test_extract_array_agg(self):
        value = (APIData
                 .select(fn.json_group_array(
                     APIData.data.extract('metadata.tags[0]')))
                 .order_by(APIData.id)
                 .scalar())
        data = json.loads(value)
        self.assertEqual(data, ['python', 'nosql', 'sqlite', 'nosql',
                                'python'])

    def test_extract(self):
        titles = self.Q.columns(APIData.data.extract('title')).tuples()
        self.assertEqual([row for row, in titles], [
            'My List of Python and SQLite Resources',
            'Using SQLite4\'s LSM Storage Engine as a Stand-alone NoSQL Database with Python',
            'Building the SQLite FTS5 Search Extension',
            'Introduction to the fast new UnQLite Python Bindings',
            'Alternative Redis-Like Databases with Python',
        ])

        tags = (self.Q
                .columns(APIData.data.extract('metadata.tags').alias('tags'))
                .dicts())
        self.assertEqual(list(tags), [
            {'tags': ['python', 'sqlite']},
            {'tags': ['nosql', 'python', 'sqlite', 'cython']},
            {'tags': ['sqlite', 'search', 'python', 'peewee']},
            {'tags': ['nosql', 'python', 'unqlite', 'cython']},
            {'tags': ['python', 'walrus', 'redis', 'nosql']},
        ])

        missing = self.Q.columns(APIData.data.extract('foo.bar')).tuples()
        self.assertEqual([row for row, in missing], [None] * 5)

    def test_length(self):
        tag_len = (self.Q
                   .columns(APIData.data.length('metadata.tags').alias('len'))
                   .dicts())
        self.assertEqual(list(tag_len), [
            {'len': 2},
            {'len': 4},
            {'len': 4},
            {'len': 4},
            {'len': 4},
        ])

    def test_remove(self):
        query = (self.Q
                 .columns(
                     fn.json_extract(
                         APIData.data.remove('metadata.tags'),
                         '$.metadata'))
                 .tuples())
        self.assertEqual([row for row, in query], ['{}'] * 5)

        Clone = APIData.alias()
        query = (APIData
                 .update(
                     data=(Clone
                           .select(Clone.data.remove('metadata.tags[2]'))
                           .where(Clone.id == APIData.id)))
                 .where(
                     APIData.value.contains('LSM Storage') |
                     APIData.value.contains('UnQLite Python')))
        result = query.execute()
        self.assertEqual(result, 2)

        tag_len = (self.Q
                   .columns(APIData.data.length('metadata.tags').alias('len'))
                   .dicts())
        self.assertEqual(list(tag_len), [
            {'len': 2},
            {'len': 3},
            {'len': 4},
            {'len': 3},
            {'len': 4},
        ])

    def test_set(self):
        query = (self.Q
                 .columns(
                     fn.json_extract(
                         APIData.data.set(
                             'metadata',
                             {'k1': {'k2': 'bar'}}),
                         '$.metadata.k1'))
                 .tuples())
        self.assertEqual(
            [json.loads(row) for row, in query],
            [{'k2': 'bar'}] * 5)

        Clone = APIData.alias()
        query = (APIData
                 .update(
                     data=(Clone
                           .select(Clone.data.set('title', 'hello'))
                           .where(Clone.id == APIData.id)))
                 .where(APIData.value.contains('LSM Storage'))
                 .execute())
        self.assertEqual(query, 1)

        titles = self.Q.columns(APIData.data.extract('title')).tuples()
        for idx, (row,) in enumerate(titles):
            if idx == 1:
                self.assertEqual(row, 'hello')
            else:
                self.assertNotEqual(row, 'hello')

    def test_multi_set(self):
        Clone = APIData.alias()
        set_query = (Clone
                     .select(Clone.data.set(
                         'foo', 'foo value',
                         'tagz', ['list', 'of', 'tags'],
                         'x.y.z', 3,
                         'metadata.foo', None,
                         'bar.baze', True))
                     .where(Clone.id == APIData.id))
        query = (APIData
                 .update(data=set_query)
                 .where(APIData.value.contains('LSM Storage'))
                 .execute())
        self.assertEqual(query, 1)

        result = APIData.select().where(APIData.value.contains('LSM storage')).get()
        self.assertEqual(result.data, {
            'bar': {'baze': 1},
            'foo': 'foo value',
            'metadata': {'tags': ['nosql', 'python', 'sqlite', 'cython'], 'foo': None},
            'tagz': ['list', 'of', 'tags'],
            'title': 'Using SQLite4\'s LSM Storage Engine as a Stand-alone NoSQL Database with Python',
            'url': 'http://charlesleifer.com/blog/using-sqlite4-s-lsm-storage-engine-as-a-stand-alone-nosql-database-with-python/',
            'x': {'y': {'z': 3}},
        })

    def test_children(self):
        children = APIData.data.children().alias('children')
        query = (APIData
                 .select(children.c.value.alias('value'))
                 .from_(APIData, children)
                 .where(children.c.key.in_(['title', 'url']))
                 .order_by(SQL('1'))
                 .tuples())
        self.assertEqual([row for row, in query], [
            'Alternative Redis-Like Databases with Python',
            'Building the SQLite FTS5 Search Extension',
            'Introduction to the fast new UnQLite Python Bindings',
            'My List of Python and SQLite Resources',
            'Using SQLite4\'s LSM Storage Engine as a Stand-alone NoSQL Database with Python',
            'http://charlesleifer.com/blog/alternative-redis-like-databases-with-python/',
            'http://charlesleifer.com/blog/building-the-sqlite-fts5-search-extension/',
            'http://charlesleifer.com/blog/introduction-to-the-fast-new-unqlite-python-bindings/',
            'http://charlesleifer.com/blog/my-list-of-python-and-sqlite-resources/',
            'http://charlesleifer.com/blog/using-sqlite4-s-lsm-storage-engine-as-a-stand-alone-nosql-database-with-python/',
        ])

    test_metadata = [
        {'filename': 'peewee.py', 'size': 200000, 'mimetype': 'text/python',
         'tags': ['peewee', 'main', 'python'],
         'metadata': {'modified': '2018-02-01 13:37:00', 'perms': 'rw'}},
        {'filename': 'runtests.py', 'size': 2300, 'mimetype': 'text/python',
         'tags': ['tests', 'peewee', 'python'],
         'metadata': {'modified': '2018-01-02 00:00:00', 'perms': 'rwx'}},
        {'filename': 'playhouse/sqlite_ext.py', 'size': 41000,
         'mimetype': 'text/python', 'tags': ['sqlite', 'peewee', 'python'],
         'metadata': {'modified': '2018-02-01 14:01:00', 'perms': 'rw'}},
    ]

    @requires_models(Metadata)
    def test_json_path(self):
        with self.database.atomic():
            for metadata in self.test_metadata:
                Metadata.create(data=metadata)

        query = (Metadata
                 .select(Metadata.data.extract(J.tags[0]).alias('tag'),
                         Metadata.data[J.filename].alias('filename'),
                         Metadata.data[J.metadata.perms].alias('perms'))
                 .order_by(fn.json_extract(Metadata.data, J['filename']))
                 .namedtuples())
        self.assertSQL(query, (
            'SELECT json_extract("t1"."data", ?) AS "tag", '
            'json_extract("t1"."data", ?) AS "filename", '
            'json_extract("t1"."data", ?) AS "perms" '
            'FROM "metadata" AS "t1" '
            'ORDER BY json_extract("t1"."data", ?)'),
            ['$.tags[0]', '$.filename', '$.metadata.perms', '$.filename'])
        accum = [(row.filename, row.tag, row.perms) for row in query]
        self.assertEqual(accum, [
            ('peewee.py', 'peewee', 'rw'),
            ('playhouse/sqlite_ext.py', 'sqlite', 'rw'),
            ('runtests.py', 'tests', 'rwx')])

        n = (Metadata
             .update(data=Metadata.data.set(
                 J.metadata.modified, '2018-02-01 15:00:00',
                 J['metadata']['misc'], 1337))
             .where(Metadata.data[J.tags[0]] != 'tests')
             .execute())
        self.assertEqual(n, 2)

        peewee = Metadata.get(Metadata.data[J.filename] == 'peewee.py')
        self.assertEqual(peewee.data['metadata']['modified'],
                         '2018-02-01 15:00:00')
        self.assertEqual(peewee.data['metadata']['misc'], 1337)


class TestSqliteExtensions(BaseTestCase):
    def test_virtual_model(self):
        class Test(VirtualModel):
            class Meta:
                database = database
                extension_module = 'ext1337'
                options = {'huey': 'cat', 'mickey': 'dog'}
                primary_key = False

        class SubTest(Test): pass

        self.assertSQL(Test._schema._create_table(), (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "test" '
            'USING ext1337 '
            '(huey=cat, mickey=dog)'), [])
        self.assertSQL(SubTest._schema._create_table(), (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "subtest" '
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
            'CREATE TABLE IF NOT EXISTS "autoincrement" '
            '("id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, '
            '"data" TEXT NOT NULL)'), [])


class TestFullTextSearch(ModelTestCase):
    database = database
    requires = [
        Post,
        ContentPost,
        ContentPostMessage,
        Document,
        MultiColumn]

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

    def test_fts_manual(self):
        messages = [Document.create(message=message)
                    for message in self.messages]
        query = (Document
                 .select()
                 .where(Document.match('believe'))
                 .order_by(Document.docid))
        self.assertMessages(query, [0, 3])

        query = Document.search('believe')
        self.assertMessages(query, [3, 0])

        query = Document.search('things', with_score=True)
        self.assertEqual([(row.message, row.score) for row in query], [
            (self.messages[4], -2. / 3),
            (self.messages[2], -1. / 3)])

    def test_fts_delete_row(self):
        posts = [Post.create(message=msg) for msg in self.messages]
        ContentPost.rebuild()
        query = (ContentPost
                 .select(ContentPost, ContentPost.rank().alias('score'))
                 .where(ContentPost.match('believe'))
                 .order_by(ContentPost.docid))
        self.assertMessages(query, [0, 3])

        query = (ContentPost
                 .select(ContentPost.docid)
                 .order_by(ContentPost.docid))
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
        assertResults('zzzzz', [
            (1, -.67),
            (2, -.33),
        ])

        self.assertEqual(
            [x.score for x in MultiColumn.search('ddddd', with_score=True)],
            [-.25, -.25, -.25, -.25])

    def test_bm25(self):
        def assertResults(term, col_idx, expected):
            query = MultiColumn.search_bm25(term, [1.0, 0, 0, 0], True)
            self.assertEqual(
                [(mc.c4, round(mc.score, 2)) for mc in query],
                expected)

        self._create_multi_column()
        MultiColumn.create(c1='aaaaa fffff', c4=5)

        assertResults('aaaaa', 1, [
            (5, -0.39),
            (1, -0.3)])
        assertResults('fffff', 1, [
            (5, -0.39),
            (3, -0.3)])
        assertResults('eeeee', 1, [(2, -0.97)])

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

    def test_bm25_alt_corpus(self):
        for message in self.messages:
            Document.create(message=message)

        def assertResults(term, expected):
            query = Document.search_bm25(term, with_score=True)
            cleaned = [
                (round(doc.score, 2), ' '.join(doc.message.split()[:2]))
                for doc in query]
            self.assertEqual(cleaned, expected)

        assertResults('things', [
            (-0.45, 'Faith has'),
            (-0.36, 'Be faithful')])

        # Indeterminate order since all are 0.0. All phrases contain the word
        # faith, so there is no meaningful score.
        results = [round(x.score, 2)
                   for x in Document.search_bm25('faith', with_score=True)]
        self.assertEqual(results, [-0., -0., -0., -0., -0.])

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
              .order_by(ModelClass.docid))
        self.assertMessages(pq, range(len(self.messages)))

        pq = (ModelClass
              .select()
              .where(ModelClass.match('believe'))
              .order_by(ModelClass.docid))
        self.assertMessages(pq, [0, 3])

        pq = (ModelClass
              .select()
              .where(ModelClass.match('thin*'))
              .order_by(ModelClass.docid))
        self.assertMessages(pq, [2, 4])

        pq = (ModelClass
              .select()
              .where(ModelClass.match('"it is"'))
              .order_by(ModelClass.docid))
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

    def test_fts_auto_field(self):
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


@skip_case_unless(CYTHON_EXTENSION)
class TestFullTextSearchCython(TestFullTextSearch):
    database = SqliteExtDatabase(':memory:', c_extensions=CYTHON_EXTENSION)

    def test_c_extensions(self):
        self.assertTrue(self.database._c_extensions)
        self.assertTrue(Post._meta.database._c_extensions)

    def test_bm25f(self):
        def assertResults(term, col_idx, expected):
            query = MultiColumn.search_bm25f(term, [1.0, 0, 0, 0], True)
            self.assertEqual(
                [(mc.c4, round(mc.score, 2)) for mc in query],
                expected)

        self._create_multi_column()
        MultiColumn.create(c1='aaaaa fffff', c4=5)

        assertResults('aaaaa', 1, [
            (5, -0.76),
            (1, -0.62)])
        assertResults('fffff', 1, [
            (5, -0.76),
            (3, -0.65)])
        assertResults('eeeee', 1, [(2, -2.13)])

        # No column specified, use the first text field.
        query = MultiColumn.search_bm25f('aaaaa OR fffff', [1., 3., 0, 0], 1)
        self.assertEqual([(mc.c4, round(mc.score, 2)) for mc in query], [
            (1, -14.46),
            (5, -12.01),
            (3, -11.16)])

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


@skip_case_unless(CYTHON_EXTENSION)
class TestMurmurHash(ModelTestCase):
    database = SqliteExtDatabase(':memory:', c_extensions=CYTHON_EXTENSION,
                                 hash_functions=True)

    def assertHash(self, s, e, fn_name='murmurhash'):
        func = getattr(fn, fn_name)
        query = Select(columns=[func(s)])
        cursor = self.database.execute(query)
        self.assertEqual(cursor.fetchone()[0], e)

    def test_murmur_hash(self):
        self.assertHash('testkey', 2871421366)
        self.assertHash('murmur', 3883399899)
        self.assertHash('', 0)
        self.assertHash('this is a test of a longer string', 2569735385)
        self.assertHash(None, None)

    @skip_if(sys.version_info[0] == 3)
    def test_checksums(self):
        self.assertHash('testkey', -225678656, 'crc32')
        self.assertHash('murmur', 1507884895, 'crc32')
        self.assertHash('', 0, 'crc32')

        self.assertHash('testkey', 203686666, 'adler32')
        self.assertHash('murmur', 155714217, 'adler32')
        self.assertHash('', 1, 'adler32')


class TestUserDefinedCallbacks(ModelTestCase):
    database = database
    requires = [Post, Values]

    def test_custom_agg(self):
        data = (
            (1, 3.4, 1.0),
            (1, 6.4, 2.3),
            (1, 4.3, 0.9),
            (2, 3.4, 1.4),
            (3, 2.7, 1.1),
            (3, 2.5, 1.1),
        )
        for klass, value, wt in data:
            Values.create(klass=klass, value=value, weight=wt)

        vq = (Values
              .select(
                  Values.klass,
                  fn.weighted_avg(Values.value).alias('wtavg'),
                  fn.avg(Values.value).alias('avg'))
              .group_by(Values.klass))
        q_data = [(v.klass, v.wtavg, v.avg) for v in vq]
        self.assertEqual(q_data, [
            (1, 4.7, 4.7),
            (2, 3.4, 3.4),
            (3, 2.6, 2.6)])

        vq = (Values
              .select(
                  Values.klass,
                  fn.weighted_avg2(Values.value, Values.weight).alias('wtavg'),
                  fn.avg(Values.value).alias('avg'))
              .group_by(Values.klass))
        q_data = [(v.klass, str(v.wtavg)[:4], v.avg) for v in vq]
        self.assertEqual(q_data, [
            (1, '5.23', 4.7),
            (2, '3.4', 3.4),
            (3, '2.6', 2.6)])

    def test_custom_collation(self):
        for i in [1, 4, 3, 5, 2]:
            Post.create(message='p%d' % i)

        pq = Post.select().order_by(NodeList((Post.message, SQL('collate collate_reverse'))))
        self.assertEqual([p.message for p in pq], ['p5', 'p4', 'p3', 'p2', 'p1'])

    def test_collation_decorator(self):
        posts = [Post.create(message=m) for m in ['aaa', 'Aab', 'ccc', 'Bba', 'BbB']]
        pq = Post.select().order_by(collate_case_insensitive.collation(Post.message))
        self.assertEqual([p.message for p in pq], [
            'aaa',
            'Aab',
            'Bba',
            'BbB',
            'ccc'])

    def test_custom_function(self):
        p1 = Post.create(message='this is a test')
        p2 = Post.create(message='another TEST')

        sq = Post.select().where(fn.title_case(Post.message) == 'This Is A Test')
        self.assertEqual(list(sq), [p1])

        sq = Post.select(fn.title_case(Post.message)).tuples()
        self.assertEqual([x[0] for x in sq], [
            'This Is A Test',
            'Another Test',
        ])

    def test_function_decorator(self):
        [Post.create(message=m) for m in ['testing', 'chatting  ', '  foo']]
        pq = Post.select(fn.rstrip(Post.message, 'ing')).order_by(Post.id)
        self.assertEqual([x[0] for x in pq.tuples()], [
            'test', 'chatting  ', '  foo'])

        pq = Post.select(fn.rstrip(Post.message, ' ')).order_by(Post.id)
        self.assertEqual([x[0] for x in pq.tuples()], [
            'testing', 'chatting', '  foo'])


class TestRowIDField(ModelTestCase):
    database = database
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
            'FROM "rowidmodel" AS "t1" '
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

    def test_insert_many_with_rowid_with_field_validation(self):
        RowIDModel.insert_many([{RowIDModel.rowid: 5, RowIDModel.data: 1}]).execute()
        self.assertEqual(5, RowIDModel.select(RowIDModel.rowid).first().rowid)


class TestTransitiveClosure(BaseTestCase):
    def test_model_factory(self):
        class Category(TestModel):
            name = CharField()
            parent = ForeignKeyField('self', null=True)

        Closure = ClosureTable(Category)
        self.assertEqual(Closure._meta.extension_module, 'transitive_closure')
        self.assertEqual(Closure._meta.columns, {})
        self.assertEqual(Closure._meta.fields, {})
        self.assertFalse(Closure._meta.primary_key)
        self.assertEqual(Closure._meta.options, {
            'idcolumn': 'id',
            'parentcolumn': 'parent_id',
            'tablename': 'category',
        })

        class Alt(TestModel):
            pk = AutoField()
            ref = ForeignKeyField('self', null=True)

        Closure = ClosureTable(Alt)
        self.assertEqual(Closure._meta.columns, {})
        self.assertEqual(Closure._meta.fields, {})
        self.assertFalse(Closure._meta.primary_key)
        self.assertEqual(Closure._meta.options, {
            'idcolumn': 'pk',
            'parentcolumn': 'ref_id',
            'tablename': 'alt',
        })

        class NoForeignKey(TestModel):
            pass
        self.assertRaises(ValueError, ClosureTable, NoForeignKey)


class BaseExtModel(TestModel):
    class Meta:
        database = database


@skip_case_unless(CLOSURE_EXTENSION)
class TestTransitiveClosureManyToMany(BaseTestCase):
    def setUp(self):
        super(TestTransitiveClosureManyToMany, self).setUp()
        database.load_extension(CLOSURE_EXTENSION.rstrip('.so'))
        database.close()

    def tearDown(self):
        super(TestTransitiveClosureManyToMany, self).tearDown()
        database.unload_extension(CLOSURE_EXTENSION.rstrip('.so'))
        database.close()

    def test_manytomany(self):
        class Person(BaseExtModel):
            name = CharField()

        class Relationship(BaseExtModel):
            person = ForeignKeyField(Person)
            relation = ForeignKeyField(Person, backref='related_to')

        PersonClosure = ClosureTable(
            Person,
            referencing_class=Relationship,
            foreign_key=Relationship.relation,
            referencing_key=Relationship.person)

        database.drop_tables([Person, Relationship, PersonClosure], safe=True)
        database.create_tables([Person, Relationship, PersonClosure])

        c = Person.create(name='charlie')
        m = Person.create(name='mickey')
        h = Person.create(name='huey')
        z = Person.create(name='zaizee')
        Relationship.create(person=c, relation=h)
        Relationship.create(person=c, relation=m)
        Relationship.create(person=h, relation=z)
        Relationship.create(person=h, relation=m)

        def assertPeople(query, expected):
            self.assertEqual(sorted([p.name for p in query]), expected)

        PC = PersonClosure
        assertPeople(PC.descendants(c), [])
        assertPeople(PC.ancestors(c), ['huey', 'mickey', 'zaizee'])
        assertPeople(PC.siblings(c), ['huey'])

        assertPeople(PC.descendants(h), ['charlie'])
        assertPeople(PC.ancestors(h), ['mickey', 'zaizee'])
        assertPeople(PC.siblings(h), ['charlie'])

        assertPeople(PC.descendants(z), ['charlie', 'huey'])
        assertPeople(PC.ancestors(z), [])
        assertPeople(PC.siblings(z), [])


@skip_case_unless(CLOSURE_EXTENSION and os.path.exists(CLOSURE_EXTENSION))
class TestTransitiveClosureIntegration(BaseTestCase):
    tree = {
        'books': [
            {'fiction': [
                {'scifi': [
                    {'hard scifi': []},
                    {'dystopian': []}]},
                {'westerns': []},
                {'classics': []},
            ]},
            {'non-fiction': [
                {'biographies': []},
                {'essays': []},
            ]},
        ]
    }

    def setUp(self):
        super(TestTransitiveClosureIntegration, self).setUp()
        database.load_extension(CLOSURE_EXTENSION.rstrip('.so'))
        database.close()

    def tearDown(self):
        super(TestTransitiveClosureIntegration, self).tearDown()
        database.unload_extension(CLOSURE_EXTENSION.rstrip('.so'))
        database.close()

    def initialize_models(self):
        class Category(BaseExtModel):
            name = CharField()
            parent = ForeignKeyField('self', null=True)
            @classmethod
            def g(cls, name):
                return cls.get(cls.name == name)

        Closure = ClosureTable(Category)
        database.drop_tables([Category, Closure], safe=True)
        database.create_tables([Category, Closure])

        def build_tree(nodes, parent=None):
            for name, subnodes in nodes.items():
                category = Category.create(name=name, parent=parent)
                if subnodes:
                    for subnode in subnodes:
                        build_tree(subnode, category)

        build_tree(self.tree)
        return Category, Closure

    def assertNodes(self, query, *expected):
        self.assertEqual(
            set([category.name for category in query]),
            set(expected))

    def test_build_tree(self):
        Category, Closure = self.initialize_models()
        self.assertEqual(Category.select().count(), 10)

    def test_descendants(self):
        Category, Closure = self.initialize_models()
        books = Category.g('books')
        self.assertNodes(
            Closure.descendants(books),
            'fiction', 'scifi', 'hard scifi', 'dystopian',
            'westerns', 'classics', 'non-fiction', 'biographies', 'essays')

        self.assertNodes(Closure.descendants(books, 0), 'books')
        self.assertNodes(
            Closure.descendants(books, 1), 'fiction', 'non-fiction')
        self.assertNodes(
            Closure.descendants(books, 2),
            'scifi', 'westerns', 'classics', 'biographies', 'essays')
        self.assertNodes(
            Closure.descendants(books, 3), 'hard scifi', 'dystopian')

        fiction = Category.g('fiction')
        self.assertNodes(
            Closure.descendants(fiction),
            'scifi', 'hard scifi', 'dystopian', 'westerns', 'classics')
        self.assertNodes(
            Closure.descendants(fiction, 1),
            'scifi', 'westerns', 'classics')
        self.assertNodes(
            Closure.descendants(fiction, 2), 'hard scifi', 'dystopian')

        self.assertNodes(
            Closure.descendants(Category.g('scifi')),
            'hard scifi', 'dystopian')
        self.assertNodes(
            Closure.descendants(Category.g('scifi'), include_node=True),
            'scifi', 'hard scifi', 'dystopian')
        self.assertNodes(Closure.descendants(Category.g('hard scifi'), 1))

    def test_ancestors(self):
        Category, Closure = self.initialize_models()

        hard_scifi = Category.g('hard scifi')
        self.assertNodes(
            Closure.ancestors(hard_scifi),
            'scifi', 'fiction', 'books')
        self.assertNodes(
            Closure.ancestors(hard_scifi, include_node=True),
            'hard scifi', 'scifi', 'fiction', 'books')
        self.assertNodes(Closure.ancestors(hard_scifi, 2), 'fiction')
        self.assertNodes(Closure.ancestors(hard_scifi, 3), 'books')

        non_fiction = Category.g('non-fiction')
        self.assertNodes(Closure.ancestors(non_fiction), 'books')
        self.assertNodes(Closure.ancestors(non_fiction, include_node=True),
                         'non-fiction', 'books')
        self.assertNodes(Closure.ancestors(non_fiction, 1), 'books')

        books = Category.g('books')
        self.assertNodes(Closure.ancestors(books, include_node=True),
                         'books')
        self.assertNodes(Closure.ancestors(books))
        self.assertNodes(Closure.ancestors(books, 1))

    def test_siblings(self):
        Category, Closure = self.initialize_models()

        self.assertNodes(
            Closure.siblings(Category.g('hard scifi')), 'dystopian')
        self.assertNodes(
            Closure.siblings(Category.g('hard scifi'), include_node=True),
            'hard scifi', 'dystopian')
        self.assertNodes(
            Closure.siblings(Category.g('classics')), 'scifi', 'westerns')
        self.assertNodes(
            Closure.siblings(Category.g('classics'), include_node=True),
            'scifi', 'westerns', 'classics')
        self.assertNodes(
            Closure.siblings(Category.g('fiction')), 'non-fiction')

    def test_tree_changes(self):
        Category, Closure = self.initialize_models()
        books = Category.g('books')
        fiction = Category.g('fiction')
        dystopian = Category.g('dystopian')
        essays = Category.g('essays')
        new_root = Category.create(name='products')
        Category.create(name='magazines', parent=new_root)
        books.parent = new_root
        books.save()
        dystopian.delete_instance()
        essays.parent = books
        essays.save()
        Category.create(name='rants', parent=essays)
        Category.create(name='poetry', parent=books)

        query = (Category
                 .select(Category.name, Closure.depth)
                 .join(Closure, on=(Category.id == Closure.id))
                 .where(Closure.root == new_root)
                 .order_by(Closure.depth, Category.name)
                 .tuples())
        self.assertEqual(list(query), [
            ('products', 0),
            ('books', 1),
            ('magazines', 1),
            ('essays', 2),
            ('fiction', 2),
            ('non-fiction', 2),
            ('poetry', 2),
            ('biographies', 3),
            ('classics', 3),
            ('rants', 3),
            ('scifi', 3),
            ('westerns', 3),
            ('hard scifi', 4),
        ])

    def test_id_not_overwritten(self):
        class Node(BaseExtModel):
            parent = ForeignKeyField('self', null=True)
            name = CharField()

        NodeClosure = ClosureTable(Node)
        database.create_tables([Node, NodeClosure], safe=True)

        root = Node.create(name='root')
        c1 = Node.create(name='c1', parent=root)
        c2 = Node.create(name='c2', parent=root)

        query = NodeClosure.descendants(root)
        self.assertEqual(sorted([(n.id, n.name) for n in query]),
                         [(c1.id, 'c1'), (c2.id, 'c2')])
        database.drop_tables([Node, NodeClosure])


@skip_case_unless(FTS5Model.fts5_installed)
class TestFTS5(ModelTestCase):
    database = database
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
            'CREATE VIRTUAL TABLE IF NOT EXISTS "fts5test" USING fts5 '
            '("title", "data", "misc" UNINDEXED)'), [])

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
            'FROM "fts5test" AS "t1" '
            'WHERE ("fts5test" MATCH ?) ORDER BY rank'), ['bb'])
        self.assertResults(query, ['nug aa dd', 'foo aa bb', 'bar bb cc'])


class KV(LSMTable):
    key = TextField(primary_key=True)
    val_b = BlobField()
    val_i = IntegerField()
    val_f = FloatField()
    val_t = TextField()

    class Meta:
        database = database
        filename = 'test_lsm.ldb'


class KVS(LSMTable):
    key = TextField(primary_key=True)
    value = TextField()

    class Meta:
        database = database
        filename = 'test_lsm.ldb'


class KVI(LSMTable):
    key = IntegerField(primary_key=True)
    value = TextField()

    class Meta:
        database = database
        filename = 'test_lsm.ldb'


@skip_case_unless(LSM_EXTENSION and os.path.exists(LSM_EXTENSION))
class TestLSM1Extension(BaseTestCase):
    def setUp(self):
        super(TestLSM1Extension, self).setUp()
        if os.path.exists(KV._meta.filename):
            os.unlink(KV._meta.filename)

        database.connect()
        database.load_extension(LSM_EXTENSION.rstrip('.so'))

    def tearDown(self):
        super(TestLSM1Extension, self).tearDown()
        database.unload_extension(LSM_EXTENSION.rstrip('.so'))
        database.close()
        if os.path.exists(KV._meta.filename):
            os.unlink(KV._meta.filename)

    def test_lsm_extension(self):
        self.assertSQL(KV._schema._create_table(), (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "kv" USING lsm1 '
            '("test_lsm.ldb", "key", TEXT, "val_b", "val_i", '
            '"val_f", "val_t")'), [])

        self.assertSQL(KVS._schema._create_table(), (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "kvs" USING lsm1 '
            '("test_lsm.ldb", "key", TEXT, "value")'), [])

        self.assertSQL(KVI._schema._create_table(), (
            'CREATE VIRTUAL TABLE IF NOT EXISTS "kvi" USING lsm1 '
            '("test_lsm.ldb", "key", UINT, "value")'), [])

    def test_lsm_crud_operations(self):
        database.create_tables([KV])

        with database.transaction():
            KV.create(key='k0', val_b=None, val_i=0, val_f=0.1, val_t='v0')

        v0 = KV['k0']
        self.assertEqual(v0.key, 'k0')
        self.assertEqual(v0.val_b, None)
        self.assertEqual(v0.val_i, 0)
        self.assertEqual(v0.val_f, 0.1)
        self.assertEqual(v0.val_t, 'v0')

        self.assertRaises(KeyError, lambda: KV['k1'])

        # Test that updates work as expected.
        KV['k0'] = (None, 1338, 3.14, 'v2-e')

        v0_db = KV['k0']
        self.assertEqual(v0_db.val_i, 1338)
        self.assertEqual(v0_db.val_f, 3.14)
        self.assertEqual(v0_db.val_t, 'v2-e')

        self.assertEqual(len([item for item in KV.select()]), 1)

        del KV['k0']
        self.assertEqual(len([item for item in KV.select()]), 0)

    def test_insert_replace(self):
        database.create_tables([KVS])
        KVS.insert({'key': 'k0', 'value': 'v0'}).execute()
        self.assertEqual(KVS['k0'], 'v0')

        KVS.replace({'key': 'k0', 'value': 'v0-e'}).execute()
        self.assertEqual(KVS['k0'], 'v0-e')

        # Implicit.
        KVS['k0'] = 'v0-x'
        self.assertEqual(KVS['k0'], 'v0-x')

    def test_index_performance(self):
        database.create_tables([KVS])

        data = [{'key': 'k%s' % i, 'value': 'v%s' % i} for i in range(20)]
        KVS.insert_many(data).execute()

        self.assertEqual(KVS.select().count(), 20)
        self.assertEqual(KVS['k0'], 'v0')
        self.assertEqual(KVS['k19'], 'v19')

        keys = [row.key for row in KVS['k4.1':'k8.9']]
        self.assertEqual(keys, ['k5', 'k6', 'k7', 'k8'])

        keys = [row.key for row in KVS[:'k13']]
        self.assertEqual(keys, ['k0', 'k1', 'k10', 'k11', 'k12', 'k13'])

        keys = [row.key for row in KVS['k5':]]
        self.assertEqual(keys, ['k5', 'k6', 'k7', 'k8', 'k9'])

        data = [tuple(row) for row in KVS[KVS.key > 'k5']]
        self.assertEqual(data, [
            ('k6', 'v6'),
            ('k7', 'v7'),
            ('k8', 'v8'),
            ('k9', 'v9')])

        del KVS[KVS.key.between('k10', 'k18')]
        self.assertEqual([row.key for row in KVS[:'k2']],
                         ['k0', 'k1', 'k19', 'k2'])

        del KVS['k3.1':'k8.1']
        self.assertEqual([row.key for row in KVS[:]],
                         ['k0', 'k1', 'k19', 'k2', 'k3', 'k9'])

        del KVS['k1']
        self.assertRaises(KeyError, lambda: KVS['k1'])

    def test_index_uint(self):
        database.create_tables([KVI])
        data = [{'key': i, 'value': 'v%s' % i} for i in range(100)]

        with database.transaction():
            KVI.insert_many(data).execute()

        keys = [row.key for row in KVI[27:33]]
        self.assertEqual(keys, [27, 28, 29, 30, 31, 32, 33])

        keys = [row.key for row in KVI[KVI.key < 4]]
        self.assertEqual(keys, [0, 1, 2, 3])

        keys = [row.key for row in KVI[KVI.key > 95]]
        self.assertEqual(keys, [96, 97, 98, 99])


@skip_case_unless(json_installed)
class TestJsonContains(ModelTestCase):
    database = SqliteExtDatabase(':memory:', json_contains=True)
    requires = [KeyData]
    test_data = (
        ('a', {'k1': 'v1', 'k2': 'v2', 'k3': 'v3'}),
        ('b', {'k2': 'v2', 'k3': 'v3', 'k4': 'v4'}),
        ('c', {'k3': 'v3', 'x1': {'y1': 'z1', 'y2': 'z2'}}),
        ('d', {'k4': 'v4', 'x1': {'y2': 'z2', 'y3': [0, 1, 2]}}),
        ('e', ['foo', 'bar', [0, 1, 2]]),
    )

    def setUp(self):
        super(TestJsonContains, self).setUp()
        with self.database.atomic():
            for key, data in self.test_data:
                KeyData.create(key=key, data=data)

    def assertContains(self, obj, expected):
        contains = fn.json_contains(KeyData.data, json.dumps(obj))
        query = (KeyData
                 .select(KeyData.key)
                 .where(contains)
                 .order_by(KeyData.key)
                 .namedtuples())
        self.assertEqual([m.key for m in query], expected)

    def test_json_contains(self):
        # Simple checks for key.
        self.assertContains('k1', ['a'])
        self.assertContains('k2', ['a', 'b'])
        self.assertContains('k3', ['a', 'b', 'c'])
        self.assertContains('kx', [])
        self.assertContains('y1', [])

        # Partial dictionary.
        self.assertContains({'k1': 'v1'}, ['a'])
        self.assertContains({'k2': 'v2'}, ['a', 'b'])
        self.assertContains({'k3': 'v3'}, ['a', 'b', 'c'])
        self.assertContains({'k2': 'v2', 'k3': 'v3'}, ['a', 'b'])

        self.assertContains({'k2': 'vx'}, [])
        self.assertContains({'k2': 'v2', 'k3': 'vx'}, [])
        self.assertContains({'y1': 'z1'}, [])

        # List, interpreted as list of keys.
        self.assertContains(['k1', 'k2'], ['a'])
        self.assertContains(['k4'], ['b', 'd'])
        self.assertContains(['kx'], [])
        self.assertContains(['y1'], [])

        # List, interpreted as ordered list of items.
        self.assertContains(['foo'], ['e'])
        self.assertContains(['foo', 'bar'], ['e'])
        self.assertContains(['bar', 'foo'], [])

        # Nested dictionaries.
        self.assertContains({'x1': 'y1'}, ['c'])
        self.assertContains({'x1': ['y1']}, ['c'])
        self.assertContains({'x1': {'y1': 'z1'}}, ['c'])
        self.assertContains({'x1': {'y2': 'z2'}}, ['c', 'd'])
        self.assertContains({'x1': {'y2': 'z2'}, 'k4': 'v4'}, ['d'])

        self.assertContains({'x1': {'yx': 'z1'}}, [])
        self.assertContains({'x1': {'y1': 'z1', 'y3': 'z3'}}, [])
        self.assertContains({'x1': {'y2': 'zx'}}, [])
        self.assertContains({'x1': {'k4': 'v4'}}, [])

        # Mixing dictionaries and lists.
        self.assertContains({'x1': {'y2': 'z2', 'y3': [0]}}, ['d'])
        self.assertContains({'x1': {'y2': 'z2', 'y3': [0, 1, 2]}}, ['d'])

        self.assertContains({'x1': {'y2': 'z2', 'y3': [0, 1, 2, 4]}}, [])
        self.assertContains({'x1': {'y2': 'z2', 'y3': [0, 2]}}, [])
