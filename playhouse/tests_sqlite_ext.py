import sqlite3; sqlite3.enable_callback_tracebacks(True)
import unittest

from peewee import *
from playhouse import sqlite_ext as sqe

# use a disk-backed db since memory dbs only exist for a single connection and
# we need to share the db w/2 for the locking tests.  additionally, set the
# sqlite_busy_timeout to 100ms so when we test locking it doesn't take forever
ext_db = sqe.SqliteExtDatabase('tmp.db', timeout=.1)

# test aggregate.
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

# test collations
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

# test function
def title_case(s):
    return s.title()

@ext_db.func()
def rstrip(s, n):
    return s.rstrip(n)

# register test aggregates / collations / functions
ext_db.register_aggregate(WeightedAverage, 1, 'weighted_avg')
ext_db.register_aggregate(WeightedAverage, 2, 'weighted_avg2')
ext_db.register_collation(collate_reverse)
ext_db.register_function(title_case)


class BaseExtModel(sqe.Model):
    class Meta:
        database = ext_db

class Post(BaseExtModel):
    message = TextField()

class FTSPost(Post, sqe.FTSModel):
    """Automatically managed and populated via the Post model."""
    pass

class FTSDoc(sqe.FTSModel):
    """Manually managed and populated using queries."""
    message = TextField()
    class Meta:
        database = ext_db

class ManagedDoc(sqe.FTSModel):
    message = TextField()
    class Meta:
        database = ext_db

class MultiColumn(sqe.FTSModel):
    c1 = CharField(default='')
    c2 = CharField(default='')
    c3 = CharField(default='')
    c4 = IntegerField()

    class Meta:
        database = ext_db

class Values(BaseExtModel):
    klass = IntegerField()
    value = FloatField()
    weight = FloatField()



class SqliteExtTestCase(unittest.TestCase):
    messages = [
        'A faith is a necessity to a man. Woe to him who believes in nothing.',
        'All who call on God in true faith, earnestly from the heart, will '
        'certainly be heard, and will receive what they have asked and desired.',
        'Be faithful in small things because it is in them that your strength lies.',
        'Faith consists in believing when it is beyond the power of reason to believe.',
        'Faith has to do with things that are not seen and hope with things that are not at hand.',
    ]
    values = [
        ('aaaaa bbbbb ccccc ddddd', 'aaaaa ccccc', 'zzzzz zzzzz', 1),
        ('bbbbb ccccc ddddd eeeee', 'bbbbb', 'zzzzz', 2),
        ('ccccc ccccc ddddd fffff', 'ccccc', 'yyyyy', 3),
        ('ddddd', 'ccccc', 'xxxxx', 4),
    ]

    def setUp(self):
        FTSDoc.drop_table(True)
        ManagedDoc.drop_table(True)
        FTSPost.drop_table(True)
        Post.drop_table(True)
        MultiColumn.drop_table(True)
        Values.drop_table(True)
        Values.create_table()
        MultiColumn.create_table(tokenize='porter')
        Post.create_table()
        FTSPost.create_table(tokenize='porter', content=Post)
        ManagedDoc.create_table(tokenize='porter', content=Post.message)
        FTSDoc.create_table(tokenize='porter')

    def test_pk_autoincrement(self):
        class AutoInc(Model):
            id = sqe.PrimaryKeyAutoIncrementField()
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

        q = FTSDoc.select().where(FTSDoc.match('believe')).order_by(FTSDoc.id)
        self.assertMessages(q, [0, 3])

        q = FTSDoc.search('believe')
        self.assertMessages(q, [3, 0])

        q = FTSDoc.search('things')
        self.assertEqual([(x.message, x.score) for x in q], [
            (self.messages[4], 2.0 / 3),
            (self.messages[2], 1.0 / 3),
        ])

    def _create_multi_column(self):
        for c1, c2, c3, c4 in self.values:
            MultiColumn.create(c1=c1, c2=c2, c3=c3, c4=c4)

    def test_fts_multi_column(self):
        def assertResults(term, expected):
            results = [
                (x.c4, round(x.score, 2))
                for x in MultiColumn.search(term)]
            self.assertEqual(results, expected)

        self._create_multi_column()

        # `bbbbb` appears two times in `c1`, one time in `c2`.
        assertResults('bbbbb', [
            (2, 1.5),  # 1/2 + 1/1
            (1, 0.5),  # 1/2
        ])

        # `ccccc` appears four times in `c1`, three times in `c2`.
        assertResults('ccccc', [
            (3, .83),  # 2/4 + 1/3
            (1, .58), # 1/4 + 1/3
            (4, .33), # 1/3
            (2, .25), # 1/4
        ])

        # `zzzzz` appears three times in c3.
        assertResults('zzzzz', [
            (1, .67),
            (2, .33),
        ])

        self.assertEqual(
            [x.score for x in MultiColumn.search('ddddd')],
            [.25, .25, .25, .25])

    def test_bm25(self):
        def assertResults(term, col_idx, expected):
            query = MultiColumn.search_bm25(term, MultiColumn.c1)
            self.assertEqual(
                [(mc.c4, round(mc.score, 2)) for mc in query],
                expected)

        self._create_multi_column()
        MultiColumn.create(c1='aaaaa fffff', c4=5)

        assertResults('aaaaa', 1, [
            (5, 0.39),
            (1, 0.3),
        ])
        assertResults('fffff', 1, [
            (5, 0.39),
            (3, 0.3),
        ])
        assertResults('eeeee', 1, [
            (2, 0.97),
        ])

        # No column specified, use the first text field.
        query = MultiColumn.search_bm25('fffff')
        self.assertEqual([(mc.c4, round(mc.score, 2)) for mc in query], [
            (5, 0.39),
            (3, 0.3),
        ])

        # Use helpers.
        query = (MultiColumn
                 .select(
                     MultiColumn.c4,
                     MultiColumn.bm25(MultiColumn.c1).alias('score'))
                 .where(MultiColumn.match('aaaaa'))
                 .order_by(SQL('score').desc()))
        self.assertEqual([(mc.c4, round(mc.score, 2)) for mc in query], [
            (5, 0.39),
            (1, 0.3),
        ])

    def test_bm25_alt_corpus(self):
        for message in self.messages:
            FTSDoc.create(message=message)

        def assertResults(term, expected):
            query = FTSDoc.search_bm25(term)
            cleaned = [
                (round(doc.score, 2), ' '.join(doc.message.split()[:2]))
                for doc in query]
            self.assertEqual(cleaned, expected)

        assertResults('things', [
            (0.45, 'Faith has'),
            (0.36, 'Be faithful'),
        ])

        # Indeterminate order since all are 0.0. All phrases contain the word
        # faith, so there is no meaningful score.
        results = [x.score for x in FTSDoc.search_bm25('faith')]
        self.assertEqual(results, [0., 0., 0., 0., 0.])

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
              .order_by(ModelClass.id))
        self.assertMessages(pq, range(len(self.messages)))

        pq = (ModelClass
              .select()
              .where(ModelClass.match('believe'))
              .order_by(ModelClass.id))
        self.assertMessages(pq, [0, 3])

        pq = (ModelClass
              .select()
              .where(ModelClass.match('thin*'))
              .order_by(ModelClass.id))
        self.assertMessages(pq, [2, 4])

        pq = (ModelClass
              .select()
              .where(ModelClass.match('"it is"'))
              .order_by(ModelClass.id))
        self.assertMessages(pq, [2, 3])

        pq = ModelClass.search('things')
        self.assertEqual([(x.message, x.score) for x in pq], [
            (self.messages[4], 2.0 / 3),
            (self.messages[2], 1.0 / 3),
        ])

        pq = (ModelClass
              .select(sqe.Rank(ModelClass))
              .where(ModelClass.match('faithful'))
              .tuples())
        self.assertEqual([x[0] for x in pq], [.2] * 5)

        pq = (ModelClass
              .search('faithful')
              .dicts())
        self.assertEqual([x['score'] for x in pq], [.2] * 5)

    def test_fts_auto_model(self):
        self._test_fts_auto(FTSPost)

    def test_fts_auto_field(self):
        self._test_fts_auto(ManagedDoc)

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

    def test_granular_transaction(self):
        conn = ext_db.get_conn()

        def test_locked_dbw(isolation_level):
            with ext_db.granular_transaction(isolation_level):
                Post.create(message='p1')  # Will not be saved.
                conn2 = ext_db._connect(ext_db.database, **ext_db.connect_kwargs)
                conn2.execute('insert into post (message) values (?);', ('x1',))
        self.assertRaises(sqlite3.OperationalError, test_locked_dbw, 'exclusive')
        self.assertRaises(sqlite3.OperationalError, test_locked_dbw, 'immediate')
        self.assertRaises(sqlite3.OperationalError, test_locked_dbw, 'deferred')

        def test_locked_dbr(isolation_level):
            with ext_db.granular_transaction(isolation_level):
                Post.create(message='p2')
                conn2 = ext_db._connect(ext_db.database, **ext_db.connect_kwargs)
                res = conn2.execute('select message from post')
                return res.fetchall()

        # no read-only stuff with exclusive locks
        self.assertRaises(sqlite3.OperationalError, test_locked_dbr, 'exclusive')

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

        with ext_db.granular_transaction('deferred'):
            Post.create(message='p4')

        res = conn2.execute('select message from post order by message;')
        self.assertEqual([x[0] for x in res.fetchall()], [
            'p2', 'p2', 'p4'])
