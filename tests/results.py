"""
Cursor wrapper, row type, and query execution tests.

Test case ordering:
  1. Cursor wrapper behavior (iteration, slicing, indexing)
  2. Row types (dicts, tuples, named tuples)
  3. Specify converter
  4. Raw query execution with Table objects
"""
import datetime

from peewee import *

from .base import get_in_memory_db
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
    database = get_in_memory_db()
    requires = [User]

    def test_iteration(self):
        for i in range(10):
            User.create(username=str(i))

        query = User.select()
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


# ===========================================================================
# Row types (dicts, tuples, named tuples) and converter specification
# ===========================================================================

class TestRowTypes(ModelTestCase):
    database = get_in_memory_db()
    requires = [User, Tweet]

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
        for i in range(3):
            Tweet.create(user=u, content='t%d' % (i + 1))

        query = (Tweet
                 .select(Tweet, User.username)
                 .join(User)
                 .order_by(Tweet.id)
                 .dicts())
        with self.assertQueryCount(1):
            results = [(r['id'], r['content'], r['username']) for r in query]
            self.assertEqual(results, [
                (1, 't1', 'u1'),
                (2, 't2', 'u1'),
                (3, 't3', 'u1')])

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


# ===========================================================================
# Empty result edge cases and error paths
# ===========================================================================

class TestEmptyResultEdgeCases(DatabaseTestCase):
    database = get_in_memory_db()

    def setUp(self):
        super(TestEmptyResultEdgeCases, self).setUp()
        QUser.bind(self.database)
        QRegister.bind(self.database)
        self.execute('CREATE TABLE "users" (id INTEGER NOT NULL PRIMARY KEY, '
                     'username TEXT)')
        self.execute('CREATE TABLE "register" ('
                     'id INTEGER NOT NULL PRIMARY KEY, '
                     'value REAL)')

    def tearDown(self):
        self.execute('DROP TABLE "users";')
        self.execute('DROP TABLE "register";')
        super(TestEmptyResultEdgeCases, self).tearDown()

    def test_count_empty(self):
        self.assertEqual(QUser.select().count(), 0)

    def test_exists_empty(self):
        self.assertFalse(QUser.select().exists())

    def test_first_empty(self):
        self.assertIsNone(QUser.select().first())

    def test_peek_empty(self):
        self.assertIsNone(QUser.select().peek(n=1))

    def test_get_empty(self):
        """Table-level get() returns None when no rows match."""
        self.assertIsNone(
            QUser.select().where(QUser.username == 'nobody').get())

    def test_scalar_empty(self):
        """Scalar on empty result returns None."""
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


class TestScalarVariants(DatabaseTestCase):
    database = get_in_memory_db()

    def setUp(self):
        super(TestScalarVariants, self).setUp()
        QRegister.bind(self.database)
        self.execute('CREATE TABLE "register" ('
                     'id INTEGER NOT NULL PRIMARY KEY, '
                     'value REAL)')
        for v in (10., 20., 30.):
            QRegister.insert({QRegister.value: v}).execute()

    def tearDown(self):
        self.execute('DROP TABLE "register";')
        super(TestScalarVariants, self).tearDown()

    def test_scalar(self):
        result = QRegister.select(fn.SUM(QRegister.value)).scalar()
        self.assertEqual(result, 60.)

    def test_scalar_as_tuple(self):
        result = (QRegister
                  .select(fn.SUM(QRegister.value),
                          fn.COUNT(QRegister.value))
                  .scalar(as_tuple=True))
        self.assertEqual(result, (60., 3))

    def test_scalar_as_dict(self):
        result = (QRegister
                  .select(fn.SUM(QRegister.value).alias('total'),
                          fn.COUNT(QRegister.value).alias('ct'))
                  .scalar(as_dict=True))
        self.assertEqual(result, {'total': 60., 'ct': 3})


# ===========================================================================
# Model-level result type tests
# ===========================================================================

class TestModelResultTypes(ModelTestCase):
    database = get_in_memory_db()
    requires = [User, Tweet]

    def setUp(self):
        super(TestModelResultTypes, self).setUp()
        huey = User.create(username='huey')
        Tweet.create(user=huey, content='meow')
        Tweet.create(user=huey, content='purr')

    def test_model_dicts(self):
        result = list(User.select(User.username).dicts())
        self.assertEqual(result, [{'username': 'huey'}])

    def test_model_tuples(self):
        result = list(User.select(User.username).tuples())
        self.assertEqual(result, [('huey',)])

    def test_model_namedtuples(self):
        result = list(User.select(User.username).namedtuples())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].username, 'huey')

    def test_model_objects(self):
        """objects() maps all selected columns onto the query's model."""
        query = (Tweet
                 .select(Tweet, User)
                 .join(User)
                 .order_by(Tweet.content)
                 .objects())
        results = list(query)
        self.assertEqual(len(results), 2)
        self.assertTrue(isinstance(results[0], Tweet))
        self.assertEqual(results[0].content, 'meow')
        self.assertEqual(results[0].username, 'huey')

    def test_model_dicts_with_join(self):
        """dicts() flattens join results."""
        query = (Tweet
                 .select(Tweet.content, User.username)
                 .join(User)
                 .order_by(Tweet.content)
                 .dicts())
        result = list(query)
        self.assertEqual(result, [
            {'content': 'meow', 'username': 'huey'},
            {'content': 'purr', 'username': 'huey'}])

    def test_model_tuples_with_join(self):
        query = (Tweet
                 .select(Tweet.content, User.username)
                 .join(User)
                 .order_by(Tweet.content)
                 .tuples())
        result = list(query)
        self.assertEqual(result, [('meow', 'huey'), ('purr', 'huey')])


# ===========================================================================
# Model-level get/peek/first edge cases
# ===========================================================================

class TestModelGetEdgeCases(ModelTestCase):
    database = get_in_memory_db()
    requires = [User]

    def test_get_does_not_exist(self):
        """Model.get() raises DoesNotExist when no row matches."""
        self.assertRaises(
            User.DoesNotExist,
            User.get, User.username == 'nobody')

    def test_get_or_none_missing(self):
        result = User.get_or_none(User.username == 'nobody')
        self.assertIsNone(result)

    def test_peek_empty_model(self):
        """peek() on empty Model result returns None."""
        query = User.select().where(User.username == 'nobody')
        self.assertIsNone(query.peek(n=1))

    def test_first_empty_model(self):
        """first() on empty Model result returns None."""
        query = User.select().where(User.username == 'nobody')
        self.assertIsNone(query.first())

    def test_scalar_model(self):
        for u in ('huey', 'mickey', 'zaizee'):
            User.create(username=u)
        count = User.select(fn.COUNT(User.id)).scalar()
        self.assertEqual(count, 3)

    def test_exists_model(self):
        User.create(username='huey')
        self.assertTrue(User.select().where(User.username == 'huey').exists())
        self.assertFalse(User.select().where(User.username == 'x').exists())


# ===========================================================================
# Query .sql() method and CursorWrapper utilities
# ===========================================================================

class TestQuerySqlMethod(ModelTestCase):
    database = get_in_memory_db()
    requires = [User]

    def test_sql_returns_tuple(self):
        """Query.sql() returns (sql_string, params)."""
        query = User.select().where(User.username == 'huey')
        sql, params = query.sql()
        self.assertIn('SELECT', sql)
        self.assertIn('"users"', sql)
        self.assertEqual(params, ['huey'])

    def test_sql_insert(self):
        query = User.insert(username='huey')
        sql, params = query.sql()
        self.assertIn('INSERT', sql)
        self.assertEqual(params, ['huey'])

    def test_sql_update(self):
        query = User.update({User.username: 'zaizee'}).where(User.id == 1)
        sql, params = query.sql()
        self.assertIn('UPDATE', sql)
        self.assertEqual(params, ['zaizee', 1])

    def test_sql_delete(self):
        query = User.delete().where(User.id == 1)
        sql, params = query.sql()
        self.assertIn('DELETE', sql)
        self.assertEqual(params, [1])


class TestDedupeColumns(DatabaseTestCase):
    database = get_in_memory_db()

    def test_dedupe_columns(self):
        """CursorWrapper.dedupe_columns handles duplicates."""
        from peewee import CursorWrapper
        cw = CursorWrapper.__new__(CursorWrapper)
        result = cw.dedupe_columns(['name', 'value', 'name', 'name'])
        self.assertEqual(result, ['name', 'value', 'name_2', 'name_3'])

    def test_dedupe_columns_with_expressions(self):
        """dedupe_columns cleans up messy column descriptions."""
        from peewee import CursorWrapper
        cw = CursorWrapper.__new__(CursorWrapper)
        result = cw.dedupe_columns(['"t1"."name"', 'SUM("t1"."value")'])
        self.assertEqual(result, ['name', 'value'])

    def test_dedupe_columns_no_identifier_cleanup(self):
        """dedupe_columns with valid_identifiers=False preserves raw names."""
        from peewee import CursorWrapper
        cw = CursorWrapper.__new__(CursorWrapper)
        result = cw.dedupe_columns(
            ['name', 'value', 'name'], valid_identifiers=False)
        self.assertEqual(result, ['name', 'value', 'name_2'])
