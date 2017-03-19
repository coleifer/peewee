from peewee import *

from .base import get_in_memory_db
from .base import DatabaseTestCase


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
