import os
import sqlite3
try:
    sqlite3.enable_callback_tracebacks(True)
except AttributeError:
    pass

from peewee import *
from peewee import print_
from playhouse.sqlite_ext import *
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import skip_if
from playhouse.tests.base import skip_unless

# Use a disk-backed db since memory dbs only exist for a single connection and
# we need to share the db w/2 for the locking tests.  additionally, set the
# sqlite_busy_timeout to 100ms so when we test locking it doesn't take forever
ext_db = database_initializer.get_database(
    'sqlite',
    c_extensions=False,
    db_class=SqliteExtDatabase,
    timeout=0.1,
    use_speedups=False)


CLOSURE_EXTENSION = os.environ.get('CLOSURE_EXTENSION')
FTS5_EXTENSION = FTS5Model.fts5_installed()


# Test aggregate.
class WeightedAverage(object):
    def __init__(self):
        self.total_weight = 0.0
        self.total_ct = 0.0

    def step(self, value, wt=None):
        wt = wt or 1.0
        self.total_weight += wt
        self.total_ct += wt * value

    def finalize(self):
        if self.total_weight != 0.0:
            return self.total_ct / self.total_weight
        return 0.0

# Test collations.
def _cmp(l, r):
    if l < r:
        return -1
    elif r < l:
        return 1
    return 0

def collate_reverse(s1, s2):
    return -_cmp(s1, s2)

@ext_db.collation()
def collate_case_insensitive(s1, s2):
    return _cmp(s1.lower(), s2.lower())

# Test functions.
def title_case(s):
    return s.title()

@ext_db.func()
def rstrip(s, n):
    return s.rstrip(n)

# Register test aggregates / collations / functions.
ext_db.register_aggregate(WeightedAverage, 'weighted_avg', 1)
ext_db.register_aggregate(WeightedAverage, 'weighted_avg2', 2)
ext_db.register_collation(collate_reverse)
ext_db.register_function(title_case)


class BaseExtModel(Model):
    class Meta:
        database = ext_db


class Post(BaseExtModel):
    message = TextField()


class FTSPost(Post, FTSModel):
    """Automatically managed and populated via the Post model."""
    # Need to specify this, since the `Post.id` primary key will take
    # precedence.
    docid = DocIDField()

    class Meta:
        extension_options = {
            'content': Post,
            'tokenize': 'porter'}


class FTSDoc(FTSModel):
    """Manually managed and populated using queries."""
    message = TextField()

    class Meta:
        database = ext_db
        extension_options = {'tokenize': 'porter'}


class ManagedDoc(FTSModel):
    message = TextField()

    class Meta:
        database = ext_db
        extension_options = {'tokenize': 'porter', 'content': Post.message}


class MultiColumn(FTSModel):
    c1 = CharField(default='')
    c2 = CharField(default='')
    c3 = CharField(default='')
    c4 = IntegerField()

    class Meta:
        database = ext_db
        extension_options = {'tokenize': 'porter'}


class FTS5Test(FTS5Model):
    title = SearchField()
    data = SearchField()
    misc = SearchField(unindexed=True)

    class Meta:
        database = ext_db


class Values(BaseExtModel):
    klass = IntegerField()
    value = FloatField()
    weight = FloatField()


class RowIDModel(BaseExtModel):
    rowid = RowIDField()
    data = IntegerField()


class TestVirtualModel(VirtualModel):
    class Meta:
        database = ext_db
        extension_module = 'test_ext'
        extension_options = {
            'foo': 'bar',
            'baze': 'nugget'}
        primary_key = False


class APIData(BaseExtModel):
    data = JSONField()
    value = TextField()


class TestVirtualModelChild(TestVirtualModel):
    pass


def json_installed():
    if sqlite3.sqlite_version_info < (3, 9, 0):
        return False
    # Test in-memory DB to determine if the FTS5 extension is installed.
    tmp_db = sqlite3.connect(':memory:')
    try:
        tmp_db.execute('select json(?)', (1337,))
    except:
        return False
    finally:
        tmp_db.close()
    return True


@skip_unless(json_installed)
class TestJSONField(ModelTestCase):
    requires = [
        APIData,
    ]
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
        with ext_db.execution_context():
            for entry in self.test_data:
                APIData.create(data=entry, value=entry['title'])

        self.Q = APIData.select().order_by(APIData.id)

    def test_extract(self):
        titles = self.Q.select(APIData.data.extract('title')).tuples()
        self.assertEqual([row for row, in titles], [
            'My List of Python and SQLite Resources',
            'Using SQLite4\'s LSM Storage Engine as a Stand-alone NoSQL Database with Python',
            'Building the SQLite FTS5 Search Extension',
            'Introduction to the fast new UnQLite Python Bindings',
            'Alternative Redis-Like Databases with Python',
        ])

        tags = (self.Q
                .select(APIData.data.extract('metadata.tags').alias('tags'))
                .dicts())
        self.assertEqual(list(tags), [
            {'tags': ['python', 'sqlite']},
            {'tags': ['nosql', 'python', 'sqlite', 'cython']},
            {'tags': ['sqlite', 'search', 'python', 'peewee']},
            {'tags': ['nosql', 'python', 'unqlite', 'cython']},
            {'tags': ['python', 'walrus', 'redis', 'nosql']},
        ])

        missing = self.Q.select(APIData.data.extract('foo.bar')).tuples()
        self.assertEqual([row for row, in missing], [None] * 5)

    def test_length(self):
        tag_len = (self.Q
                   .select(APIData.data.length('metadata.tags').alias('len'))
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
                 .select(
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
                     APIData.value.contains('UnQLite Python'))
                 .execute())
        self.assertEqual(query, 2)

        tag_len = (self.Q
                   .select(APIData.data.length('metadata.tags').alias('len'))
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
                 .select(
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

        titles = self.Q.select(APIData.data.extract('title')).tuples()
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


class TestFTSModel(ModelTestCase):
    requires = [
        FTSDoc,
        ManagedDoc,
        FTSPost,
        Post,
        MultiColumn,
    ]
    messages = [
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
         'that are not at hand.')]
    values = [
        ('aaaaa bbbbb ccccc ddddd', 'aaaaa ccccc', 'zzzzz zzzzz', 1),
        ('bbbbb ccccc ddddd eeeee', 'bbbbb', 'zzzzz', 2),
        ('ccccc ccccc ddddd fffff', 'ccccc', 'yyyyy', 3),
        ('ddddd', 'ccccc', 'xxxxx', 4)]

    def test_virtual_model_options(self):
        compiler = ext_db.compiler()
        sql, params = compiler.create_table(TestVirtualModel)
        self.assertEqual(sql, (
            'CREATE VIRTUAL TABLE "testvirtualmodel" USING test_ext '
            '(baze=nugget, foo=bar)'))
        self.assertEqual(params, [])

        sql, params = compiler.create_table(TestVirtualModelChild)
        self.assertEqual(sql, (
            'CREATE VIRTUAL TABLE "testvirtualmodelchild" USING test_ext '
            '("id" INTEGER NOT NULL PRIMARY KEY, baze=nugget, foo=bar)'))
        self.assertEqual(params, [])

        test_options = {'baze': 'nugz', 'huey': 'mickey'}
        sql, params = compiler.create_table(
            TestVirtualModel,
            options=test_options)
        self.assertEqual(sql, (
            'CREATE VIRTUAL TABLE "testvirtualmodel" USING test_ext '
            '(baze=nugz, foo=bar, huey=mickey)'))
        self.assertEqual(params, [])

    def test_pk_autoincrement(self):
        class AutoInc(Model):
            id = PrimaryKeyAutoIncrementField()
            foo = CharField()

        compiler = ext_db.compiler()
        sql, params = compiler.create_table(AutoInc)
        self.assertEqual(
            sql,
            'CREATE TABLE "autoinc" '
            '("id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, '
            '"foo" VARCHAR(255) NOT NULL)')

    def assertMessages(self, query, indices):
        self.assertEqual([x.message for x in query], [
            self.messages[i] for i in indices])

    def test_fts_manual(self):
        messages = [FTSDoc.create(message=msg) for msg in self.messages]

        q = (FTSDoc
             .select()
             .where(FTSDoc.match('believe'))
             .order_by(FTSDoc.docid))
        self.assertMessages(q, [0, 3])

        q = FTSDoc.search('believe')
        self.assertMessages(q, [3, 0])

        q = FTSDoc.search('things', with_score=True)
        self.assertEqual([(x.message, x.score) for x in q], [
            (self.messages[4], -2.0 / 3),
            (self.messages[2], -1.0 / 3),
        ])

    def test_fts_delete_row(self):
        posts = [Post.create(message=message) for message in self.messages]
        FTSPost.rebuild()
        query = (FTSPost
                 .select(FTSPost, FTSPost.rank().alias('score'))
                 .where(FTSPost.match('believe'))
                 .order_by(FTSPost.docid))
        self.assertMessages(query, [0, 3])

        fts_posts = FTSPost.select(FTSPost.docid).order_by(FTSPost.docid)
        for fts_post in fts_posts:
            self.assertEqual(fts_post.delete_instance(), 1)

        for post in posts:
            self.assertEqual(
                (FTSPost.delete()
                 .where(FTSPost.message == post.message).execute()),
                1)

        # None of the deletes went through. This is because the table is
        # managed.
        self.assertEqual(FTSPost.select().count(), 5)

        fts_docs = [FTSDoc.create(message=message)
                    for message in self.messages]
        self.assertEqual(FTSDoc.select().count(), 5)

        for fts_doc in fts_docs:
            self.assertEqual(FTSDoc.delete().where(
                FTSDoc.message == fts_doc.message).execute(),
                1)

        self.assertEqual(FTSDoc.select().count(), 0)

    def _create_multi_column(self):
        for c1, c2, c3, c4 in self.values:
            MultiColumn.create(c1=c1, c2=c2, c3=c3, c4=c4)

    def test_fts_multi_column(self):
        def assertResults(term, expected):
            results = [
                (x.c4, round(x.score, 2))
                for x in MultiColumn.search(term, with_score=True)]
            self.assertEqual(results, expected)

        self._create_multi_column()

        # `bbbbb` appears two times in `c1`, one time in `c2`.
        assertResults('bbbbb', [
            (2, -1.5),  # 1/2 + 1/1
            (1, -0.5),  # 1/2
        ])

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
            (1, -0.3),
        ])
        assertResults('fffff', 1, [
            (5, -0.39),
            (3, -0.3),
        ])
        assertResults('eeeee', 1, [
            (2, -0.97),
        ])

        # No column specified, use the first text field.
        query = MultiColumn.search_bm25('fffff', [1.0, 0, 0, 0], True)
        self.assertEqual([(mc.c4, round(mc.score, 2)) for mc in query], [
            (5, -0.39),
            (3, -0.3),
        ])

        # Use helpers.
        query = (MultiColumn
                 .select(
                     MultiColumn.c4,
                     MultiColumn.bm25(1.0).alias('score'))
                 .where(MultiColumn.match('aaaaa'))
                 .order_by(SQL('score')))
        self.assertEqual([(mc.c4, round(mc.score, 2)) for mc in query], [
            (5, -0.39),
            (1, -0.3),
        ])

    def test_bm25_alt_corpus(self):
        for message in self.messages:
            FTSDoc.create(message=message)

        def assertResults(term, expected):
            query = FTSDoc.search_bm25(term, with_score=True)
            cleaned = [
                (round(doc.score, 2), ' '.join(doc.message.split()[:2]))
                for doc in query]
            self.assertEqual(cleaned, expected)

        assertResults('things', [
            (-0.45, 'Faith has'),
            (-0.36, 'Be faithful'),
        ])

        # Indeterminate order since all are 0.0. All phrases contain the word
        # faith, so there is no meaningful score.
        results = [round(x.score, 2)
                   for x in FTSDoc.search_bm25('faith', with_score=True)]
        self.assertEqual(results, [
            -0.,
            -0.,
            -0.,
            -0.,
            -0.])

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
        self._test_fts_auto(FTSPost)

    def test_fts_auto_field(self):
        self._test_fts_auto(ManagedDoc)


class TestUserDefinedCallbacks(ModelTestCase):
    requires = [
        Post,
        Values,
    ]

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
            (3, 2.6, 2.6),
        ])

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
            (3, '2.6', 2.6),
        ])

    def test_custom_collation(self):
        for i in [1, 4, 3, 5, 2]:
            Post.create(message='p%d' % i)

        pq = Post.select().order_by(Clause(Post.message, SQL('collate collate_reverse')))
        self.assertEqual([p.message for p in pq], ['p5', 'p4', 'p3', 'p2', 'p1'])

    def test_collation_decorator(self):
        posts = [Post.create(message=m) for m in ['aaa', 'Aab', 'ccc', 'Bba', 'BbB']]
        pq = Post.select().order_by(collate_case_insensitive.collation(Post.message))
        self.assertEqual([p.message for p in pq], [
            'aaa',
            'Aab',
            'Bba',
            'BbB',
            'ccc',
        ])

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

    def test_lock_type_transaction(self):
        conn = ext_db.get_conn()

        def test_locked_dbw(isolation_level):
            with ext_db.transaction(isolation_level):
                Post.create(message='p1')  # Will not be saved.
                conn2 = ext_db._connect(ext_db.database, **ext_db.connect_kwargs)
                conn2.execute('insert into post (message) values (?);', ('x1',))
        self.assertRaises(sqlite3.OperationalError, test_locked_dbw, 'exclusive')
        self.assertRaises(sqlite3.OperationalError, test_locked_dbw, 'immediate')
        self.assertRaises(sqlite3.OperationalError, test_locked_dbw, 'deferred')

        def test_locked_dbr(isolation_level):
            with ext_db.transaction(isolation_level):
                Post.create(message='p2')
                other_db = database_initializer.get_database(
                    'sqlite',
                    db_class=SqliteExtDatabase,
                    timeout=0.1,
                    use_speedups=False)
                res = other_db.execute_sql('select message from post')
                return res.fetchall()

        # no read-only stuff with exclusive locks
        self.assertRaises(OperationalError, test_locked_dbr, 'exclusive')

        # ok to do readonly w/immediate and deferred (p2 is saved twice)
        self.assertEqual(test_locked_dbr('immediate'), [])
        self.assertEqual(test_locked_dbr('deferred'), [('p2',)])

        # test everything by hand, by setting the default connection to
        # 'exclusive' and turning off autocommit behavior
        ext_db.set_autocommit(False)
        conn.isolation_level = 'exclusive'
        Post.create(message='p3')  # uncommitted

        # now, open a second connection w/exclusive and try to read, it will
        # be locked
        conn2 = ext_db._connect(ext_db.database, **ext_db.connect_kwargs)
        conn2.isolation_level = 'exclusive'
        self.assertRaises(sqlite3.OperationalError, conn2.execute, 'select * from post')

        # rollback the first connection's transaction, releasing the exclusive lock
        conn.rollback()
        ext_db.set_autocommit(True)

        with ext_db.transaction('deferred'):
            Post.create(message='p4')

        res = conn2.execute('select message from post order by message;')
        self.assertEqual([x[0] for x in res.fetchall()], [
            'p2', 'p2', 'p4'])


class TestRowIDField(ModelTestCase):
    requires = [RowIDModel]

    def test_model_meta(self):
        self.assertEqual(RowIDModel._meta.sorted_field_names,
                         ['rowid', 'data'])
        self.assertEqual([f.name for f in RowIDModel._meta.declared_fields],
                         ['data'])
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
        sql, params = query.sql()
        self.assertEqual(sql, (
            'SELECT "t1"."data" '
            'FROM "rowidmodel" AS t1 '
            'WHERE ("t1"."rowid" = ?)'))
        self.assertEqual(params, [2])
        r_db = query.get()
        self.assertEqual(r_db.rowid, None)
        self.assertEqual(r_db.data, 20)

        r_db2 = query.select(RowIDModel.rowid, RowIDModel.data).get()
        self.assertEqual(r_db2.rowid, 2)
        self.assertEqual(r_db2.data, 20)

    def test_insert_with_rowid(self):
        RowIDModel.insert({RowIDModel.rowid: 5, 'data': 1}).execute()
        self.assertEqual(5, RowIDModel.select(RowIDModel.rowid).first().rowid)

    def test_insert_many_with_rowid_without_field_validation(self):
        RowIDModel.insert_many([{RowIDModel.rowid: 5, 'data': 1}], validate_fields=False).execute()
        self.assertEqual(5, RowIDModel.select(RowIDModel.rowid).first().rowid)

    def test_insert_many_with_rowid_with_field_validation(self):
        RowIDModel.insert_many([{RowIDModel.rowid: 5, 'data': 1}], validate_fields=True).execute()
        self.assertEqual(5, RowIDModel.select(RowIDModel.rowid).first().rowid)

class TestTransitiveClosure(PeeweeTestCase):
    def test_model_factory(self):
        class Category(BaseExtModel):
            name = CharField()
            parent = ForeignKeyField('self', null=True)

        Closure = ClosureTable(Category)
        self.assertEqual(Closure._meta.extension_module, 'transitive_closure')
        self.assertEqual(Closure._meta.columns, {})
        self.assertEqual(Closure._meta.fields, {})
        self.assertFalse(Closure._meta.primary_key)
        self.assertEqual(Closure._meta.extension_options, {
            'idcolumn': 'id',
            'parentcolumn': 'parent_id',
            'tablename': 'category',
        })

        class Alt(BaseExtModel):
            pk = PrimaryKeyField()
            ref = ForeignKeyField('self', null=True)

        Closure = ClosureTable(Alt)
        self.assertEqual(Closure._meta.columns, {})
        self.assertEqual(Closure._meta.fields, {})
        self.assertFalse(Closure._meta.primary_key)
        self.assertEqual(Closure._meta.extension_options, {
            'idcolumn': 'pk',
            'parentcolumn': 'ref_id',
            'tablename': 'alt',
        })

        class NoForeignKey(BaseExtModel):
            pass
        self.assertRaises(ValueError, ClosureTable, NoForeignKey)


@skip_unless(lambda: FTS5_EXTENSION)
class TestFTS5Extension(ModelTestCase):
    requires = [FTS5Test]
    corpus = (
        ('foo aa bb', 'aa bb cc ' * 10, 1),
        ('bar bb cc', 'bb cc dd ' * 9, 2),
        ('baze cc dd', 'cc dd ee ' * 8, 3),
        ('nug aa dd', 'bb cc ' * 7, 4),
    )

    def setUp(self):
        super(TestFTS5Extension, self).setUp()
        for title, data, misc in self.corpus:
            FTS5Test.create(title=title, data=data, misc=misc)

    def test_fts5_options(self):
        class Test1(FTS5Model):
            f1 = SearchField()
            f2 = SearchField(unindexed=True)
            f3 = SearchField()

            class Meta:
                database = ext_db
                extension_options = {
                    'prefix': [2, 3],
                    'tokenize': 'porter unicode61',
                    'content': Post,
                    'content_rowid': Post.id,
                }

        create_sql = Test1.sqlall()
        self.assertEqual(len(create_sql), 1)
        self.assertEqual(create_sql[0], (
            'CREATE VIRTUAL TABLE "test1" USING fts5 ('
            '"f1" , "f2"  UNINDEXED, "f3" , '
            'content="post", content_rowid="id", '
            'prefix=\'2,3\', tokenize="porter unicode61")'))

    def assertResults(self, query, expected, scores=False, alias='score'):
        if scores:
            results = [
                (obj.title, round(getattr(obj, alias), 7))
                for obj in query]
        else:
            results = [obj.title for obj in query]
        self.assertEqual(results, expected)

    def test_search(self):
        query = FTS5Test.search('bb')
        self.assertEqual(query.sql(), (
            ('SELECT "t1"."title", "t1"."data", "t1"."misc" '
             'FROM "fts5test" AS t1 '
             'WHERE ("fts5test" MATCH ?) ORDER BY rank'),
            ['bb']))
        self.assertResults(query, ['nug aa dd', 'foo aa bb', 'bar bb cc'])

        query = FTS5Test.search('bb', with_score=True)
        self.assertEqual(query.sql(), (
            ('SELECT "t1"."title", "t1"."data", "t1"."misc", rank AS score '
             'FROM "fts5test" AS t1 '
             'WHERE ("fts5test" MATCH ?) ORDER BY score'),
            ['bb']))
        self.assertResults(query, [
            ('nug aa dd', -2e-06),
            ('foo aa bb', -1.9e-06),
            ('bar bb cc', -1.9e-06)], True)

        query = FTS5Test.search('aa', with_score=True, score_alias='s')
        self.assertResults(query, [
            ('foo aa bb', -1.9e-06),
            ('nug aa dd', -1.2e-06),
        ], True, 's')

    def test_search_bm25(self):
        query = FTS5Test.search_bm25('bb')
        self.assertEqual(query.sql(), (
            ('SELECT "t1"."title", "t1"."data", "t1"."misc" '
             'FROM "fts5test" AS t1 '
             'WHERE ("fts5test" MATCH ?) ORDER BY rank'),
            ['bb']))
        self.assertResults(query, ['nug aa dd', 'foo aa bb', 'bar bb cc'])

        query = FTS5Test.search_bm25('bb', with_score=True)
        self.assertEqual(query.sql(), (
            ('SELECT "t1"."title", "t1"."data", "t1"."misc", rank AS score '
             'FROM "fts5test" AS t1 '
             'WHERE ("fts5test" MATCH ?) ORDER BY score'),
            ['bb']))
        self.assertResults(query, [
            ('nug aa dd', -2e-06),
            ('foo aa bb', -1.9e-06),
            ('bar bb cc', -1.9e-06)], True)

    def test_search_bm25_scores(self):
        query = FTS5Test.search_bm25('bb', {'title': 5.0})
        self.assertEqual(query.sql(), (
            ('SELECT "t1"."title", "t1"."data", "t1"."misc" '
             'FROM "fts5test" AS t1 '
             'WHERE ("fts5test" MATCH ?) ORDER BY bm25("fts5test", ?, ?, ?)'),
            ['bb', 5.0, 1.0, 1.0]))
        self.assertResults(query, ['bar bb cc', 'foo aa bb', 'nug aa dd'])

        query = FTS5Test.search_bm25('bb', {'title': 5.0}, True)
        self.assertEqual(query.sql(), (
            ('SELECT "t1"."title", "t1"."data", "t1"."misc", '
             'bm25("fts5test", ?, ?, ?) AS score '
             'FROM "fts5test" AS t1 '
             'WHERE ("fts5test" MATCH ?) ORDER BY score'),
            [5.0, 1.0, 1.0, 'bb']))
        self.assertResults(query, [
            ('bar bb cc', -2e-06),
            ('foo aa bb', -2e-06),
            ('nug aa dd', -2e-06)], True)

    def test_set_rank(self):
        FTS5Test.set_rank('bm25(10.0, 1.0)')
        query = FTS5Test.search('bb', with_score=True)
        self.assertEqual(query.sql(), (
            ('SELECT "t1"."title", "t1"."data", "t1"."misc", rank AS score '
             'FROM "fts5test" AS t1 '
             'WHERE ("fts5test" MATCH ?) ORDER BY score'),
            ['bb']))
        self.assertResults(query, [
            ('bar bb cc', -2.1e-06),
            ('foo aa bb', -2.1e-06),
            ('nug aa dd', -2e-06)], True)

    def test_vocab_model(self):
        Vocab = FTS5Test.VocabModel()
        if Vocab.table_exists():
            Vocab.drop_table()
        Vocab.create_table()
        query = Vocab.select().where(Vocab.term == 'aa')
        self.assertEqual(
            query.dicts()[:],
            [{'doc': 2, 'term': 'aa', 'cnt': 12}])

        query = Vocab.select().where(Vocab.cnt > 20).order_by(Vocab.cnt)
        self.assertEqual(query.dicts()[:], [
            {'doc': 3, 'term': 'bb', 'cnt': 28},
            {'doc': 4, 'term': 'cc', 'cnt': 36}])

    def test_validate_query(self):
        data = (
            ('testing one two three', True),
            ('"testing one" "two" three', True),
            ('\'testing one\' "two" three', False),
            ('"\'testing one\'" "two" three', True),
            ('k-means', False),
            ('"k-means"', True),
            ('0123 AND (4 OR 5)', True),
            ('it\'s', False),
        )
        for phrase, valid in data:
            self.assertEqual(FTS5Model.validate_query(phrase), valid)

    def test_clean_query(self):
        data = (
            ('testing  one', 'testing  one'),
            ('testing  "one"', 'testing  "one"'),
            ('testing  \'one\'', 'testing _one_'),
            ('foo; bar [1 2 3] it\'s', 'foo_ bar _1 2 3_ it_s'),
        )
        for inval, outval in data:
            self.assertEqual(FTS5Model.clean_query(inval, '_'), outval)


@skip_if(lambda: not CLOSURE_EXTENSION)
class TestTransitiveClosureIntegration(PeeweeTestCase):
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
        ext_db.load_extension(CLOSURE_EXTENSION.rstrip('.so'))
        ext_db.close()

    def tearDown(self):
        super(TestTransitiveClosureIntegration, self).tearDown()
        ext_db.unload_extension(CLOSURE_EXTENSION.rstrip('.so'))
        ext_db.close()

    def initialize_models(self):
        class Category(BaseExtModel):
            name = CharField()
            parent = ForeignKeyField('self', null=True)
            @classmethod
            def g(cls, name):
                return cls.get(cls.name == name)

        Closure = ClosureTable(Category)
        ext_db.drop_tables([Category, Closure], True)
        ext_db.create_tables([Category, Closure])

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
