import sys
import unittest

from peewee import *

from .base import db
from .base import get_in_memory_db
from .base import requires_models
from .base import ModelTestCase
from .base import TestModel
from .base_models import *


class TestModelAPIs(ModelTestCase):
    def add_user(self, username):
        return User.create(username=username)

    def add_tweets(self, user, *tweets):
        for tweet in tweets:
            Tweet.create(user=user, content=tweet)

    @requires_models(User, Tweet)
    def test_assertQueryCount(self):
        self.add_tweets(self.add_user('charlie'), 'foo', 'bar', 'baz')
        def do_test(n):
            with self.assertQueryCount(n):
                authors = [tweet.user.username for tweet in Tweet.select()]

        self.assertRaises(AssertionError, do_test, 1)
        self.assertRaises(AssertionError, do_test, 3)
        do_test(4)
        self.assertRaises(AssertionError, do_test, 5)

    @requires_models(User, Tweet)
    def test_create(self):
        with self.assertQueryCount(1):
            huey = self.add_user('huey')
            self.assertEqual(huey.username, 'huey')
            self.assertTrue(isinstance(huey.id, int))
            self.assertTrue(huey.id > 0)

        with self.assertQueryCount(1):
            tweet = Tweet.create(user=huey, content='meow')
            self.assertEqual(tweet.user.id, huey.id)
            self.assertEqual(tweet.user.username, 'huey')
            self.assertEqual(tweet.content, 'meow')
            self.assertTrue(isinstance(tweet.id, int))
            self.assertTrue(tweet.id > 0)

    @requires_models(User, Tweet)
    def test_model_select(self):
        query = (Tweet
                 .select(Tweet.content, User.username)
                 .join(User)
                 .order_by(User.username, Tweet.content))
        self.assertSQL(query, (
            'SELECT "t1"."content", "t2"."username" '
            'FROM "tweet" AS "t1" '
            'INNER JOIN "users" AS "t2" '
            'ON ("t1"."user_id" = "t2"."id") '
            'ORDER BY "t2"."username", "t1"."content"'), [])

        huey = self.add_user('huey')
        mickey = self.add_user('mickey')
        zaizee = self.add_user('zaizee')

        self.add_tweets(huey, 'meow', 'hiss', 'purr')
        self.add_tweets(mickey, 'woof', 'whine')

        with self.assertQueryCount(1):
            tweets = list(query)
            self.assertEqual([(t.content, t.user.username) for t in tweets], [
                ('hiss', 'huey'),
                ('meow', 'huey'),
                ('purr', 'huey'),
                ('whine', 'mickey'),
                ('woof', 'mickey')])

    @requires_models(User, Tweet, Favorite)
    def test_multi_join(self):
        TweetUser = User.alias('u2')

        query = (Favorite
                 .select(Favorite.id,
                         Tweet.content,
                         User.username,
                         TweetUser.username)
                 .join(Tweet)
                 .join(TweetUser, on=(Tweet.user == TweetUser.id))
                 .switch(Favorite)
                 .join(User)
                 .order_by(Tweet.content, Favorite.id))
        self.assertSQL(query, (
            'SELECT '
            '"t1"."id", "t2"."content", "t3"."username", "u2"."username" '
            'FROM "favorite" AS "t1" '
            'INNER JOIN "tweet" AS "t2" ON ("t1"."tweet_id" = "t2"."id") '
            'INNER JOIN "users" AS "u2" ON ("t2"."user_id" = "u2"."id") '
            'INNER JOIN "users" AS "t3" ON ("t1"."user_id" = "t3"."id") '
            'ORDER BY "t2"."content", "t1"."id"'), [])

        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        u3 = User.create(username='u3')
        t1_1 = Tweet.create(user=u1, content='t1-1')
        t1_2 = Tweet.create(user=u1, content='t1-2')
        t2_1 = Tweet.create(user=u2, content='t2-1')
        t2_2 = Tweet.create(user=u2, content='t2-2')
        favorites = ((u1, t2_1),
                     (u1, t2_2),
                     (u2, t1_1),
                     (u3, t1_2),
                     (u3, t2_2))
        for user, tweet in favorites:
            Favorite.create(user=user, tweet=tweet)

        with self.assertQueryCount(1):
            accum = [(f.tweet.user.username, f.tweet.content, f.user.username)
                     for f in query]
            self.assertEqual(accum, [
                ('u1', 't1-1', 'u2'),
                ('u1', 't1-2', 'u3'),
                ('u2', 't2-1', 'u1'),
                ('u2', 't2-2', 'u1'),
                ('u2', 't2-2', 'u3')])

    @requires_models(Register)
    def test_compound_select(self):
        for i in range(10):
            Register.create(value=i)

        q1 = Register.select().where(Register.value < 2)
        q2 = Register.select().where(Register.value > 7)
        c1 = (q1 | q2).order_by(SQL('1'))

        self.assertSQL(c1, (
            'SELECT "t1"."id", "t1"."value" FROM "register" AS "t1" '
            'WHERE ("t1"."value" < ?) UNION '
            'SELECT "a1"."id", "a1"."value" FROM "register" AS "a1" '
            'WHERE ("a1"."value" > ?) ORDER BY 1'), [2, 7])

        self.assertEqual([row.value for row in c1], [0, 1, 8, 9])

        q3 = Register.select().where(Register.value == 5)
        c2 = (c1.order_by() | q3).order_by(SQL('"value"'))

        self.assertSQL(c2, (
            'SELECT "t1"."id", "t1"."value" FROM "register" AS "t1" '
            'WHERE ("t1"."value" < ?) UNION '
            'SELECT "a1"."id", "a1"."value" FROM "register" AS "a1" '
            'WHERE ("a1"."value" > ?) UNION '
            'SELECT "b1"."id", "b1"."value" FROM "register" AS "b1" '
            'WHERE ("b1"."value" = ?) ORDER BY "value"'), [2, 7, 5])

        self.assertEqual([row.value for row in c2], [0, 1, 5, 8, 9])

    @requires_models(Category)
    def test_self_referential_fk(self):
        self.assertTrue(Category.parent.rel_model is Category)

        root = Category.create(name='root')
        c1 = Category.create(parent=root, name='child-1')
        c2 = Category.create(parent=root, name='child-2')

        with self.assertQueryCount(1):
            Parent = Category.alias('p')
            query = (Category
                     .select(
                         Parent.name,
                         Category.name)
                     .join(Parent, on=(Category.parent == Parent.name))
                     .where(Category.parent == root)
                     .order_by(Category.name))
            c1_db, c2_db = list(query)

            self.assertEqual(c1_db.name, 'child-1')
            self.assertEqual(c1_db.parent.name, 'root')
            self.assertEqual(c2_db.name, 'child-2')
            self.assertEqual(c2_db.parent.name, 'root')

    def test_deferred_fk(self):
        class Note(TestModel):
            foo = DeferredForeignKey('Foo', backref='notes')

        class Foo(TestModel):
            pass

        self.assertTrue(Note.foo.rel_model is Foo)
        f = Foo(id=1337)
        self.assertSQL(f.notes, (
            'SELECT "t1"."id", "t1"."foo_id" FROM "note" AS "t1" '
            'WHERE ("t1"."foo_id" = ?)'), [1337])

    @requires_models(User, Tweet)
    def test_joins_with_aliases(self):
        data = (
            ('huey', 'meow'),
            ('mickey', 'bark'),
            ('mickey', 'whine'),
            ('huey', 'purr'),
            ('mickey', 'woof'))
        users = {}
        for username, tweet in data:
            if username not in users:
                users[username] = user = User.create(username=username)
            else:
                user = users[username]
            Tweet.create(user=user, content=tweet)

        query = (Tweet
                 .select(Tweet, User)
                 .join(User)
                 .order_by(User.username, Tweet.content))
        with self.assertQueryCount(1):
            results = [(tweet.user.username, tweet.content) for tweet in query]
        self.assertEqual(results, sorted(data))

        UA = User.alias('ua')
        import ipdb
        ipdb.set_trace()
        query = (Tweet
                 .select(Tweet, UA)
                 .join(UA)
                 .order_by(UA.username, Tweet.content))
        with self.assertQueryCount(1):
            results = [(tweet.user.username, tweet.content) for tweet in query]
        self.assertEqual(results, sorted(data))

        UA2 = User.alias('ua2')
        query = (Tweet
                 .select(Tweet, UA2)
                 .join(UA2, on=(Tweet.user == UA2.id).alias('foo'))
                 .order_by(UA2.username, Tweet.content))
        with self.assertQueryCount(1):
            results = [(tweet.foo.username, tweet.content) for tweet in query]
        self.assertEqual(results, sorted(data))

    @requires_models(User, Tweet)
    def test_backref_joins(self):
        data = (
            ('huey', 'meow'),
            ('huey', 'purr'),
            ('zaizee', 'hiss'),
            ('mickey', 'woof'))
        users = {}

        for username, tweet in data:
            if username not in users:
                users[username] = user = User.create(username=username)
            else:
                user = users[username]
            Tweet.create(user=user, content=tweet)

        query = (User
                 .select(User, Tweet)
                 .join(Tweet)
                 .order_by(User.username, Tweet.id))

        with self.assertQueryCount(1):
            result = [(user.username, user.tweets.content) for user in query]

        self.assertEqual(result, sorted(data))

        TA = Tweet.alias('ta')
        query = (User
                 .select(User.username, TA.content)
                 .join(TA, on=(User.id == TA.user_id).alias('foo'))
                 .order_by(User.username, TA.id))

        with self.assertQueryCount(1):
            results = [(user.username, user.foo.content) for user in query]

        self.assertEqual(result, sorted(data))
