from peewee import *

from .base import BaseTestCase
from .base import DatabaseTestCase
from .base import TestModel
from .base import get_in_memory_db


User = Table('users', ['id', 'username'])
Tweet = Table('tweet', ['id', 'user_id', 'content'])
Register = Table('register', ['id', 'value'])


class TestQueryExecution(DatabaseTestCase):
    database = get_in_memory_db()

    def setUp(self):
        super(TestQueryExecution, self).setUp()
        User.bind(self.database)
        Tweet.bind(self.database)
        Register.bind(self.database)
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
        user_id = User.insert({User.username: username}).execute()
        for tweet in tweets:
            Tweet.insert({
                Tweet.user_id: user_id,
                Tweet.content: tweet}).execute()
        return user_id

    def test_selection(self):
        huey_id = self.create_user_tweets('huey', 'meow', 'purr')
        query = User.select()
        self.assertEqual(query[:], [{'id': huey_id, 'username': 'huey'}])

        query = (Tweet
                 .select(Tweet.content, User.username)
                 .join(User, on=(Tweet.user_id == User.id))
                 .order_by(Tweet.id))
        self.assertEqual(query[:], [
            {'content': 'meow', 'username': 'huey'},
            {'content': 'purr', 'username': 'huey'}])

    def test_select_peek_first(self):
        huey_id = self.create_user_tweets('huey', 'meow', 'purr', 'hiss')
        query = Tweet.select(Tweet.content).order_by(Tweet.id)
        self.assertEqual(query.peek(n=2), [
            {'content': 'meow'},
            {'content': 'purr'}])
        self.assertEqual(query.first(), {'content': 'meow'})

        query = Tweet.select().where(Tweet.id == 0)
        self.assertIsNone(query.peek(n=2))
        self.assertIsNone(query.first())

    def test_select_get(self):
        huey_id = self.create_user_tweets('huey')
        self.assertEqual(User.select().where(User.username == 'huey').get(), {
            'id': huey_id, 'username': 'huey'})
        self.assertIsNone(User.select().where(User.username == 'x').get())

    def test_select_count(self):
        huey_id = self.create_user_tweets('huey', 'meow', 'purr')
        mickey_id = self.create_user_tweets('mickey', 'woof', 'pant', 'whine')

        self.assertEqual(User.select().count(), 2)
        self.assertEqual(Tweet.select().count(), 5)

        query = Tweet.select().where(Tweet.user_id == mickey_id)
        self.assertEqual(query.count(), 3)

        query = (Tweet
                 .select()
                 .join(User, on=(Tweet.user_id == User.id))
                 .where(User.username == 'foo'))
        self.assertEqual(query.count(), 0)

    def test_select_exists(self):
        self.create_user_tweets('huey')
        self.assertTrue(User.select().where(User.username == 'huey').exists())
        self.assertFalse(User.select().where(User.username == 'foo').exists())

    def test_scalar(self):
        values = [1.0, 1.5, 2.0, 5.0, 8.0]
        (Register
         .insert([{Register.value: value} for value in values])
         .execute())

        query = Register.select(fn.AVG(Register.value))
        self.assertEqual(query.scalar(), 3.5)

        query = query.where(Register.value < 5)
        self.assertEqual(query.scalar(), 1.5)

        query = (Register
                 .select(
                     fn.SUM(Register.value),
                     fn.COUNT(Register.value),
                     fn.SUM(Register.value) / fn.COUNT(Register.value)))
        self.assertEqual(query.scalar(as_tuple=True), (17.5, 5, 3.5))

        query = query.where(Register.value >= 2)
        self.assertEqual(query.scalar(as_tuple=True), (15, 3, 5))

    def test_slicing_select(self):
        values = [1., 1., 2., 3., 5., 8.]
        (Register
         .insert([(v,) for v in values], columns=(Register.value,))
         .execute())

        query = (Register
                 .select(Register.value)
                 .order_by(Register.value)
                 .tuples())
        with self.assertQueryCount(1):
            self.assertEqual(query[0], (1.,))
            self.assertEqual(query[:2], [(1.,), (1.,)])
            self.assertEqual(query[1:4], [(1.,), (2.,), (3.,)])
            self.assertEqual(query[-1], (8.,))
            self.assertEqual(query[-2], (5.,))
            self.assertEqual(query[-2:], [(5.,), (8.,)])
            self.assertEqual(query[2:-2], [(2.,), (3.,)])


class TestQueryCloning(BaseTestCase):
    def test_clone_tables(self):
        self._do_test_clone(User, Tweet)

    def test_clone_models(self):
        class User(TestModel):
            username = TextField()
            class Meta:
                table_name = 'users'
        class Tweet(TestModel):
            user = ForeignKeyField(User, backref='tweets')
            content = TextField()
        self._do_test_clone(User, Tweet)

    def _do_test_clone(self, User, Tweet):
        query = Tweet.select(Tweet.id)
        base_sql = 'SELECT "t1"."id" FROM "tweet" AS "t1"'
        self.assertSQL(query, base_sql, [])

        qj = query.join(User, on=(Tweet.user_id == User.id))
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qj, (
            'SELECT "t1"."id" FROM "tweet" AS "t1" '
            'INNER JOIN "users" AS "t2" ON ("t1"."user_id" = "t2"."id")'), [])

        qw = query.where(Tweet.id > 3)
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qw, base_sql + ' WHERE ("t1"."id" > ?)', [3])

        qw2 = qw.where(Tweet.id < 6)
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qw, base_sql + ' WHERE ("t1"."id" > ?)', [3])
        self.assertSQL(qw2, base_sql + (' WHERE (("t1"."id" > ?) '
                                        'AND ("t1"."id" < ?))'), [3, 6])

        qo = query.order_by(Tweet.id)
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qo, base_sql + ' ORDER BY "t1"."id"', [])

        qo2 = qo.order_by(Tweet.content, Tweet.id)
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qo, base_sql + ' ORDER BY "t1"."id"', [])
        self.assertSQL(qo2,
                       base_sql + ' ORDER BY "t1"."content", "t1"."id"', [])

        qg = query.group_by(Tweet.id)
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qg, base_sql + ' GROUP BY "t1"."id"', [])
