from peewee import *

from .base import db
from .base import DatabaseTestCase


User = Table('users', ['id', 'username'])
Tweet = Table('tweet', ['id', 'user_id', 'content'])


class TestQueryExecution(DatabaseTestCase):
    def setUp(self):
        super(TestQueryExecution, self).setUp()
        User.bind(db)
        Tweet.bind(db)
        self.execute('CREATE TABLE "users" (id INTEGER NOT NULL PRIMARY KEY, '
                     'username TEXT)')
        self.execute('CREATE TABLE "tweet" (id INTEGER NOT NULL PRIMARY KEY, '
                     'user_id INTEGER NOT NULL, content TEXT, FOREIGN KEY '
                     '(user_id) REFERENCES users (id))')

    def tearDown(self):
        self.execute('DROP TABLE "tweet";')
        self.execute('DROP TABLE "users";')
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

    def test_select_peek(self):
        huey_id = self.create_user_tweets('huey', 'meow', 'purr', 'hiss')
        query = Tweet.select(Tweet.content).order_by(Tweet.id)
        self.assertEqual(query.peek(n=2), [
            {'content': 'meow'},
            {'content': 'purr'}])

        self.assertEqual(query.first(), {'content': 'meow'})
        self.assertEqual(query.get(), {'content': 'meow'})

        query = Tweet.select().where(Tweet.id == 0)
        self.assertIsNone(query.peek(n=2))
        self.assertIsNone(query.first())
