"""
Cursor wrapper, row type, and query execution tests.
"""
import datetime

from peewee import *

from .base import get_in_memory_db
from .base import BaseTestCase
from .base import DatabaseTestCase
from .base import ModelTestCase
from .base_models import *


def lange(x, y=None):
    if y is None:
        value = range(x)
    else:
        value = range(x, y)
    return list(value)


# ===========================================================================
# Cursor wrapper behavior
# ===========================================================================

class TestCursorWrapper(ModelTestCase):
    requires = [User]

    def test_iteration(self):
        for i in range(10):
            User.create(username=str(i))

        query = User.select().order_by(User.id)
        cursor = query.execute()

        first_five = []
        for i, u in enumerate(cursor):
            first_five.append(int(u.username))
            if i == 4: break

        self.assertEqual(first_five, lange(5))
        names = lambda i: [int(obj.username) for obj in i]
        self.assertEqual(names(query[5:]), lange(5, 10))
        self.assertEqual(names(query[2:5]), lange(2, 5))

        for i in range(2):
            self.assertEqual(names(cursor), lange(10))

    def test_count(self):
        for i in range(5): User.create(username=str(i))
        with self.assertQueryCount(1):
            query = User.select()
            self.assertEqual(len(query), 5)

            cursor = query.execute()
            self.assertEqual(len(cursor), 5)

        with self.assertQueryCount(1):
            query = query.where(User.username != '0')
            cursor = query.execute()
            self.assertEqual(len(cursor), 4)
            self.assertEqual(len(query), 4)

    def test_nested_iteration(self):
        for i in range(4): User.create(username=str(i))
        with self.assertQueryCount(1):
            query = User.select().order_by(User.username)
            outer = []
            inner = []
            for o_user in query:
                outer.append(int(o_user.username))
                for i_user in query:
                    inner.append(int(i_user.username))

            self.assertEqual(outer, lange(4))
            self.assertEqual(inner, lange(4) * 4)

    def test_iterator_protocol(self):
        for i in range(3): User.create(username=str(i))

        with self.assertQueryCount(1):
            query = User.select().order_by(User.id)
            cursor = query.execute()
            for _ in range(2):
                for user in cursor: pass

            it = iter(cursor)
            for obj in it:
                pass
            self.assertRaises(StopIteration, next, it)
            self.assertEqual([int(u.username) for u in cursor], lange(3))
            self.assertEqual(query[0].username, '0')
            self.assertEqual(query[2].username, '2')
            self.assertRaises(StopIteration, next, it)

    def test_cursor_getitem(self):
        for i in range(5): User.create(username=str(i))

        with self.assertQueryCount(1):
            cursor = User.select().order_by(User.username).execute()
            self.assertEqual(cursor[2].username, '2')
            self.assertEqual(len(cursor.row_cache), 3)
            self.assertEqual(cursor[0].username, '0')
            self.assertEqual(len(cursor.row_cache), 3)
            self.assertEqual(cursor[4].username, '4')
            self.assertEqual(cursor[-1].username, '4')

    def test_iterator(self):
        for i in range(3): User.create(username=str(i))

        with self.assertQueryCount(1):
            cursor = User.select().order_by(User.id).execute()
            usernames = [int(u.username) for u in cursor.iterator()]
            self.assertEqual(usernames, lange(3))

        self.assertTrue(cursor.populated)
        self.assertEqual(cursor.row_cache, [])

        with self.assertQueryCount(0):
            self.assertEqual(list(cursor), [])

    def test_query_iterator(self):
        for i in range(3): User.create(username=str(i))

        with self.assertQueryCount(1):
            query = User.select().order_by(User.id)
            usernames = [int(u.username) for u in query.iterator()]
            self.assertEqual(usernames, lange(3))

        with self.assertQueryCount(0):
            self.assertEqual(list(query), [])

    def test_row_cache(self):
        def assertCache(cursor, n):
            self.assertEqual([int(u.username) for u in cursor.row_cache],
                             lange(n))

        for i in range(10): User.create(username=str(i))

        with self.assertQueryCount(1):
            cursor = User.select().order_by(User.id).execute()
            cursor.fill_cache(5)
            self.assertFalse(cursor.populated)
            assertCache(cursor, 5)

            cursor.fill_cache(5)
            assertCache(cursor, 5)

            cursor.fill_cache(6)
            assertCache(cursor, 6)
            self.assertFalse(cursor.populated)

            cursor.fill_cache(11)
            self.assertTrue(cursor.populated)
            assertCache(cursor, 10)

    def test_noop_cursor_wrapper_type(self):
        from peewee import CursorWrapper
        query = User.noop()
        result = query.execute()
        self.assertIsInstance(result, CursorWrapper)


# ===========================================================================
# Row types (dicts, tuples, named tuples) and converter specification
# ===========================================================================

class TestRowTypes(ModelTestCase):
    requires = [User, Tweet]

    def test_result_column_suffix_collisions(self):
        User.create(username='u1')
        cases = [
            (('value', 'value', 'value_2'),
             {'value': 'v0', 'value_2': 'v1', 'value_2_2': 'v2'}),
            (('value', 'value_2', 'value'),
             {'value': 'v0', 'value_2': 'v1', 'value_3': 'v2'}),
            (('value', 'value', 'value_2', 'value_2_2', 'value'),
             {'value': 'v0', 'value_2': 'v1', 'value_2_2': 'v2',
              'value_2_2_2': 'v3', 'value_3': 'v4'})]
        for aliases, expected in cases:
            queries = [self.make_query(*aliases),
                       Select(columns=[Value('v%d' % i).alias(alias)
                                       for i, alias in enumerate(aliases)])
                       .bind(self.database)]
            for query in queries:
                self.assertEqual(query.dicts().get(), expected)
                self.assertEqual(query.objects(dict).get(), expected)
                self.assertEqual(query.namedtuples().get()._asdict(), expected)

    def make_query(self, *exprs):
        count = 0
        accum = []
        for expr in exprs:
            if isinstance(expr, str):
                accum.append(Value('v%d' % count).alias(expr))
                count += 1
            else:
                accum.append(expr)
        return User.select(*accum).order_by(User.username)

    def test_namedtuples_non_identifier(self):
        User.create(username='u1')
        query = User.select(User.username, SQL('1')).namedtuples()
        row, = list(query)
        self.assertEqual(row.username, 'u1')
        self.assertEqual(row[1], 1)

    def test_namedtuples(self):
        User.create(username='u1')

        query = self.make_query(User.username).namedtuples()
        self.assertEqual([u.username for u in query], ['u1'])

        row = query[0]
        self.assertEqual(repr(row), 'Row(username=\'u1\')')

        query = (self
                 .make_query(User.username, 'username', 'username')
                 .namedtuples())
        row, = list(query)
        self.assertEqual(row, ('u1', 'v0', 'v1'))
        self.assertEqual(row.username, 'u1')
        self.assertEqual(row.username_2, 'v0')
        self.assertEqual(row.username_3, 'v1')

        query = (self
                 .make_query('username', User.username)
                 .namedtuples())
        row, = list(query)
        self.assertEqual(row, ('v0', 'u1'))
        self.assertEqual(row.username, 'v0')
        self.assertEqual(row.username_2, 'u1')

        query = (self
                 .make_query('"foo"', '"t1"."foo"()', 'foo ')
                 .namedtuples())
        row, = list(query)
        self.assertEqual(row, ('v0', 'v1', 'v2'))
        self.assertEqual(row.foo, 'v0')
        self.assertEqual(row.foo_2, 'v1')
        self.assertEqual(row.foo_3, 'v2')

    def test_dicts(self):
        User.create(username='u1')

        query = self.make_query(User.username).dicts()
        self.assertEqual(list(query), [{'username': 'u1'}])

        query = (self
                 .make_query(User.username, 'username', 'username')
                 .dicts())
        row, = list(query)
        self.assertEqual(row, {
            'username': 'u1',
            'username_2': 'v0',
            'username_3': 'v1'})

        query = (self
                 .make_query('username', User.username)
                 .dicts())
        row, = list(query)
        self.assertEqual(row, {
            'username': 'v0',
            'username_2': 'u1'})

        query = (self
                 .make_query('"foo"', '"t1"."foo"()', 'foo ')
                 .dicts())
        row, = list(query)
        self.assertEqual(row, {
            '"foo"': 'v0',
            '"t1"."foo"()': 'v1',
            'foo ': 'v2'})

    def test_dicts_flat(self):
        u = User.create(username='u1')
        tweets = [Tweet.create(user=u, content='t%d' % (i + 1))
                  for i in range(3)]

        query = (Tweet
                 .select(Tweet, User.username)
                 .join(User)
                 .order_by(Tweet.id)
                 .dicts())
        with self.assertQueryCount(1):
            results = [(r['id'], r['content'], r['username']) for r in query]
            self.assertEqual(results, [
                (t.id, t.content, 'u1') for t in tweets])

    def test_model_objects(self):
        User.create(username='u1')

        query = self.make_query(User.username).objects()
        self.assertEqual([u.username for u in query], ['u1'])

        query = (self
                 .make_query(User.username, 'username', 'username')
                 .objects())
        row, = list(query)
        self.assertEqual(row.username, 'u1')
        self.assertEqual(row.username_2, 'v0')
        self.assertEqual(row.username_3, 'v1')

        query = (self
                 .make_query('username', User.username)
                 .objects())
        row, = list(query)
        self.assertEqual(row.username, 'v0')
        self.assertEqual(row.username_2, 'u1')

        query = (self
                 .make_query('"foo"', '"t1"."foo"()', 'foo ')
                 .objects())
        row, = list(query)
        self.assertEqual(row.foo, 'v0')
        self.assertEqual(row.foo_2, 'v1')
        self.assertEqual(row.foo_3, 'v2')

    def test_model_objects_flat(self):
        huey = User.create(username='huey')
        mickey = User.create(username='mickey')
        for user, tweet in ((huey, 'meow'), (huey, 'purr'), (mickey, 'woof')):
            Tweet.create(user=user, content=tweet)

        query = (Tweet
                 .select(Tweet, User.username)
                 .join(User)
                 .order_by(Tweet.id)
                 .objects())
        with self.assertQueryCount(1):
            self.assertEqual([(t.username, t.content) for t in query], [
                ('huey', 'meow'),
                ('huey', 'purr'),
                ('mickey', 'woof')])

    def test_models(self):
        huey = User.create(username='huey')
        mickey = User.create(username='mickey')
        tids = []
        for user, tweet in ((huey, 'meow'), (huey, 'purr'), (mickey, 'woof')):
            tids.append(Tweet.create(user=user, content=tweet).id)

        query = (Tweet
                 .select(Tweet, User)
                 .join(User)
                 .order_by(Tweet.id))
        with self.assertQueryCount(1):
            accum = [(t.user.id, t.user.username, t.id, t.content)
                     for t in query]
            self.assertEqual(accum, [
                (huey.id, 'huey', tids[0], 'meow'),
                (huey.id, 'huey', tids[1], 'purr'),
                (mickey.id, 'mickey', tids[2], 'woof')])

    def test_model_tuples(self):
        User.create(username='huey')
        result = list(User.select(User.username).tuples())
        self.assertEqual(result, [('huey',)])

    def test_model_tuples_with_join(self):
        huey = User.create(username='huey')
        Tweet.create(user=huey, content='meow')
        Tweet.create(user=huey, content='purr')
        query = (Tweet
                 .select(Tweet.content, User.username)
                 .join(User)
                 .order_by(Tweet.content)
                 .tuples())
        result = list(query)
        self.assertEqual(result, [('meow', 'huey'), ('purr', 'huey')])

    def test_peek_n_model(self):
        for name in ('alpha', 'bravo', 'charlie'):
            User.create(username=name)
        query = User.select().order_by(User.username)
        rows = query.peek(n=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].username, 'alpha')
        self.assertEqual(rows[1].username, 'bravo')

    def test_model_namedtuple_with_join(self):
        u = User.create(username='huey')
        Tweet.create(user=u, content='meow')
        query = (Tweet
                 .select(Tweet.content, User.username)
                 .join(User)
                 .namedtuples())
        rows = list(query)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].content, 'meow')
        self.assertEqual(rows[0].username, 'huey')

    def test_model_raw_get_does_not_exist(self):
        query = User.raw('SELECT * FROM users WHERE username = ' +
                         self.database.param, 'nobody')
        self.assertRaises(User.DoesNotExist, query.get)

    def test_peek_empty_model(self):
        query = User.select().where(User.username == 'nobody')
        self.assertIsNone(query.peek(n=1))

    def test_first_empty_model(self):
        query = User.select().where(User.username == 'nobody')
        self.assertIsNone(query.first())


class Reg(TestModel):
    key = TextField()
    ts = DateTimeField()

class TestSpecifyConverter(ModelTestCase):
    requires = [Reg]

    def test_specify_converter(self):
        D = lambda d: datetime.datetime(2020, 1, d)
        for i in range(1, 4):
            Reg.create(key='k%s' % i, ts=D(i))

        RA = Reg.alias()
        subq = RA.select(RA.key, RA.ts, RA.ts.alias('aliased'))

        ra_a = subq.c.aliased.alias('aliased')
        q = (Reg
             .select(Reg.key, subq.c.ts.alias('ts'),
                     ra_a.converter(Reg.ts.python_value))
             .join(subq, on=(Reg.key == subq.c.key).alias('rsub'))
             .order_by(Reg.key))
        results = [(r.key, r.ts, r.aliased) for r in q.objects()]
        self.assertEqual(results, [
            ('k1', D(1), D(1)),
            ('k2', D(2), D(2)),
            ('k3', D(3), D(3))])

        results2 = [(r.key, r.rsub.ts, r.rsub.aliased)
                    for r in q]
        self.assertEqual(results, [
            ('k1', D(1), D(1)),
            ('k2', D(2), D(2)),
            ('k3', D(3), D(3))])


# ===========================================================================
# Raw query execution with Table objects
# ===========================================================================

# Lightweight Table objects for testing raw query execution.
# NOTE: QUser and QTweet have identical definitions in model_sql.py
# for query cloning tests.
QUser = Table('users', ['id', 'username'])
QTweet = Table('tweet', ['id', 'user_id', 'content'])
QRegister = Table('register', ['id', 'value'])


class TestQueryExecution(DatabaseTestCase):
    # setUp writes raw sqlite DDL and the inserts rely on lastrowid.
    database = get_in_memory_db()

    def setUp(self):
        super(TestQueryExecution, self).setUp()
        QUser.bind(self.database)
        QTweet.bind(self.database)
        QRegister.bind(self.database)
        self.execute('CREATE TABLE "users" (id INTEGER NOT NULL PRIMARY KEY, '
                     'username TEXT)')
        self.execute('CREATE TABLE "tweet" (id INTEGER NOT NULL PRIMARY KEY, '
                     'user_id INTEGER NOT NULL, content TEXT, FOREIGN KEY '
                     '(user_id) REFERENCES users (id))')
        self.execute('CREATE TABLE "register" ('
                     'id INTEGER NOT NULL PRIMARY KEY, '
                     'value REAL)')

    def tearDown(self):
        self.execute('DROP TABLE "tweet";')
        self.execute('DROP TABLE "users";')
        self.execute('DROP TABLE "register";')
        super(TestQueryExecution, self).tearDown()

    def create_user_tweets(self, username, *tweets):
        user_id = QUser.insert({QUser.username: username}).execute()
        for tweet in tweets:
            QTweet.insert({
                QTweet.user_id: user_id,
                QTweet.content: tweet}).execute()
        return user_id

    def test_selection(self):
        huey_id = self.create_user_tweets('huey', 'meow', 'purr')
        query = QUser.select()
        self.assertEqual(query[:], [{'id': huey_id, 'username': 'huey'}])

        query = (QTweet
                 .select(QTweet.content, QUser.username)
                 .join(QUser, on=(QTweet.user_id == QUser.id))
                 .order_by(QTweet.id))
        self.assertEqual(query[:], [
            {'content': 'meow', 'username': 'huey'},
            {'content': 'purr', 'username': 'huey'}])

    def test_namedtuples_non_identifier(self):
        self.create_user_tweets('huey')
        query = QUser.select(QUser.username, SQL('1')).namedtuples()
        row, = list(query)
        self.assertEqual(row.username, 'huey')
        self.assertEqual(row[1], 1)

    def test_select_peek_first(self):
        huey_id = self.create_user_tweets('huey', 'meow', 'purr', 'hiss')
        query = QTweet.select(QTweet.content).order_by(QTweet.id)
        self.assertEqual(query.peek(n=2), [
            {'content': 'meow'},
            {'content': 'purr'}])
        self.assertEqual(query.first(), {'content': 'meow'})

        query = QTweet.select().where(QTweet.id == 0)
        self.assertIsNone(query.peek(n=2))
        self.assertIsNone(query.first())

    def test_select_get(self):
        huey_id = self.create_user_tweets('huey')
        self.assertEqual(
            QUser.select().where(QUser.username == 'huey').get(),
            {'id': huey_id, 'username': 'huey'})
        self.assertIsNone(
            QUser.select().where(QUser.username == 'x').get())

    def test_select_count(self):
        huey_id = self.create_user_tweets('huey', 'meow', 'purr')
        mickey_id = self.create_user_tweets('mickey', 'woof', 'pant', 'whine')

        self.assertEqual(QUser.select().count(), 2)
        self.assertEqual(QTweet.select().count(), 5)

        query = QTweet.select().where(QTweet.user_id == mickey_id)
        self.assertEqual(query.count(), 3)

        query = (QTweet
                 .select()
                 .join(QUser, on=(QTweet.user_id == QUser.id))
                 .where(QUser.username == 'foo'))
        self.assertEqual(query.count(), 0)

    def test_select_exists(self):
        self.create_user_tweets('huey')
        self.assertTrue(
            QUser.select().where(QUser.username == 'huey').exists())
        self.assertFalse(
            QUser.select().where(QUser.username == 'foo').exists())

    def test_scalar(self):
        values = [1.0, 1.5, 2.0, 5.0, 8.0]
        (QRegister
         .insert([{QRegister.value: value} for value in values])
         .execute())

        query = QRegister.select(fn.AVG(QRegister.value))
        self.assertEqual(query.scalar(), 3.5)

        query = query.where(QRegister.value < 5)
        self.assertEqual(query.scalar(), 1.5)

        query = (QRegister
                 .select(
                     fn.SUM(QRegister.value),
                     fn.COUNT(QRegister.value),
                     fn.SUM(QRegister.value) / fn.COUNT(QRegister.value)))
        self.assertEqual(query.scalar(as_tuple=True), (17.5, 5, 3.5))

        query = query.where(QRegister.value >= 2)
        self.assertEqual(query.scalar(as_tuple=True), (15, 3, 5))

    def test_scalars(self):
        values = [1.0, 1.5, 2.0, 5.0, 8.0]
        (QRegister
         .insert([{QRegister.value: value} for value in values])
         .execute())

        query = QRegister.select(QRegister.value).order_by(QRegister.value)
        self.assertEqual(list(query.scalars()), values)

        query = query.where(QRegister.value < 5)
        self.assertEqual(list(query.scalars()), [1.0, 1.5, 2.0])

    def test_slicing_select(self):
        values = [1., 1., 2., 3., 5., 8.]
        (QRegister
         .insert([(v,) for v in values], columns=(QRegister.value,))
         .execute())

        query = (QRegister
                 .select(QRegister.value)
                 .order_by(QRegister.value)
                 .tuples())
        with self.assertQueryCount(1):
            self.assertEqual(query[0], (1.,))
            self.assertEqual(query[:2], [(1.,), (1.,)])
            self.assertEqual(query[1:4], [(1.,), (2.,), (3.,)])
            self.assertEqual(query[-1], (8.,))
            self.assertEqual(query[-2], (5.,))
            self.assertEqual(query[-2:], [(5.,), (8.,)])
            self.assertEqual(query[2:-2], [(2.,), (3.,)])

    def test_scalar_empty(self):
        result = QRegister.select(fn.MAX(QRegister.value)).scalar()
        self.assertIsNone(result)

    def test_scalar_as_tuple_empty(self):
        result = (QRegister
                  .select(fn.MAX(QRegister.value), fn.MIN(QRegister.value))
                  .scalar(as_tuple=True))
        self.assertEqual(result, (None, None))

    def test_scalar_as_dict_empty(self):
        result = (QRegister
                  .select(fn.COUNT(QRegister.value).alias('ct'))
                  .scalar(as_dict=True))
        self.assertEqual(result, {'ct': 0})

    def test_iterate_empty(self):
        self.assertEqual(list(QUser.select()), [])

    def test_len_empty(self):
        query = QUser.select()
        # Force iteration, then check len.
        list(query)
        self.assertEqual(len(query), 0)

    def test_getitem_empty(self):
        query = QUser.select()
        self.assertEqual(query[:], [])

    def test_scalar_as_dict(self):
        for v in (10., 20., 30.):
            QRegister.insert({QRegister.value: v}).execute()
        result = (QRegister
                  .select(fn.SUM(QRegister.value).alias('total'),
                          fn.COUNT(QRegister.value).alias('ct'))
                  .scalar(as_dict=True))
        self.assertEqual(result, {'total': 60., 'ct': 3})

    def test_getitem_invalid_type_error(self):
        QUser.insert({QUser.username: 'u1'}).execute()
        query = QUser.select()
        cursor = query.execute()
        self.assertRaises(ValueError, cursor.__getitem__, 'bad')

    def test_fill_cache_negative_error(self):
        QUser.insert({QUser.username: 'u1'}).execute()
        query = QUser.select()
        cursor = query.execute()
        self.assertRaises(ValueError, cursor.fill_cache, -1)

    def test_count_clear_limit(self):
        for i in range(5):
            QUser.insert({QUser.username: 'u%d' % i}).execute()
        query = QUser.select().limit(2).offset(1)
        # Normal count respects limit.
        self.assertEqual(query.count(), 2)
        # clear_limit ignores it.
        self.assertEqual(query.count(clear_limit=True), 5)


# ===========================================================================
# CursorWrapper column dedupe helpers
# ===========================================================================

class TestDedupeColumns(BaseTestCase):
    def test_dedupe_columns(self):
        from peewee import CursorWrapper
        cw = CursorWrapper.__new__(CursorWrapper)
        result = cw.dedupe_columns(['name', 'value', 'name', 'name'])
        self.assertEqual(result, ['name', 'value', 'name_2', 'name_3'])

    def test_dedupe_columns_with_expressions(self):
        from peewee import CursorWrapper
        cw = CursorWrapper.__new__(CursorWrapper)
        result = cw.dedupe_columns(['"t1"."name"', 'SUM("t1"."value")'])
        self.assertEqual(result, ['name', 'value'])

    def test_dedupe_columns_no_identifier_cleanup(self):
        from peewee import CursorWrapper
        cw = CursorWrapper.__new__(CursorWrapper)
        result = cw.dedupe_columns(
            ['name', 'value', 'name'], valid_identifiers=False)
        self.assertEqual(result, ['name', 'value', 'name_2'])

