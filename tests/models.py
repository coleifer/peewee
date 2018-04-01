import datetime
import sys
import time
import unittest

from peewee import *
from peewee import sqlite3

from .base import db
from .base import get_in_memory_db
from .base import mock
from .base import new_connection
from .base import requires_models
from .base import skip_case_unless
from .base import skip_if
from .base import skip_unless
from .base import BaseTestCase
from .base import IS_MYSQL
from .base import IS_POSTGRESQL
from .base import IS_SQLITE
from .base import ModelTestCase
from .base import TestModel
from .base_models import *


if sys.version_info[0] >= 3:
    long = int


class Color(TestModel):
    name = CharField(primary_key=True)
    is_neutral = BooleanField(default=False)


class Post(TestModel):
    content = TextField(column_name='Content')
    timestamp = DateTimeField(column_name='TimeStamp',
                              default=datetime.datetime.now)


class PostNote(TestModel):
    post = ForeignKeyField(Post, backref='notes', primary_key=True)
    note = TextField()


class Point(TestModel):
    x = IntegerField()
    y = IntegerField()
    class Meta:
        primary_key = False


IS_OLD_SQLITE = IS_SQLITE and sqlite3.sqlite_version_info < (3, 18)


class TestModelAPIs(ModelTestCase):
    def add_user(self, username):
        return User.create(username=username)

    def add_tweets(self, user, *tweets):
        accum = []
        for tweet in tweets:
            accum.append(Tweet.create(user=user, content=tweet))
        return accum

    @requires_models(Point)
    def test_no_primary_key(self):
        p11 = Point.create(x=1, y=1)
        p33 = Point.create(x=3, y=3)

        p_db = Point.get((Point.x == 3) & (Point.y == 3))
        self.assertEqual(p_db.x, 3)
        self.assertEqual(p_db.y, 3)

    @requires_models(Post, PostNote)
    def test_pk_is_fk(self):
        with self.database.atomic():
            p1 = Post.create(content='p1')
            p2 = Post.create(content='p2')
            p1n = PostNote.create(post=p1, note='p1n')
            p2n = PostNote.create(post=p2, note='p2n')

        with self.assertQueryCount(2):
            pn = PostNote.get(PostNote.note == 'p1n')
            self.assertEqual(pn.post.content, 'p1')

        with self.assertQueryCount(1):
            pn = (PostNote
                  .select(PostNote, Post)
                  .join(Post)
                  .where(PostNote.note == 'p2n')
                  .get())
            self.assertEqual(pn.post.content, 'p2')

        self.assertRaises(Post.DoesNotExist, PostNote.create, note='pxn')

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

    @requires_models(Post)
    def test_column_field_translation(self):
        ts = datetime.datetime(2017, 2, 1, 13, 37)
        ts2 = datetime.datetime(2017, 2, 2, 13, 37)
        p = Post.create(content='p1', timestamp=ts)
        p2 = Post.create(content='p2', timestamp=ts2)

        p_db = Post.get(Post.content == 'p1')
        self.assertEqual(p_db.content, 'p1')
        self.assertEqual(p_db.timestamp, ts)

        pd1, pd2 = Post.select().order_by(Post.id).dicts()
        self.assertEqual(pd1['content'], 'p1')
        self.assertEqual(pd1['timestamp'], ts)
        self.assertEqual(pd2['content'], 'p2')
        self.assertEqual(pd2['timestamp'], ts2)

    @requires_models(User, Tweet)
    def test_create(self):
        with self.assertQueryCount(1):
            huey = self.add_user('huey')
            self.assertEqual(huey.username, 'huey')
            self.assertTrue(isinstance(huey.id, (int, long)))
            self.assertTrue(huey.id > 0)

        with self.assertQueryCount(1):
            tweet = Tweet.create(user=huey, content='meow')
            self.assertEqual(tweet.user.id, huey.id)
            self.assertEqual(tweet.user.username, 'huey')
            self.assertEqual(tweet.content, 'meow')
            self.assertTrue(isinstance(tweet.id, int))
            self.assertTrue(tweet.id > 0)

    @requires_models(User, Tweet)
    def test_get_shortcut(self):
        huey = self.add_user('huey')
        self.add_tweets(huey, 'meow', 'purr', 'wheeze')
        mickey = self.add_user('mickey')
        self.add_tweets(mickey, 'woof', 'yip')

        huey_db = User.get(User.username == 'huey')
        self.assertEqual(huey.id, huey_db.id)
        mickey_db = User.get(User.username == 'mickey')
        self.assertEqual(mickey.id, mickey_db.id)
        self.assertEqual(User.get(username='mickey').id, mickey.id)

        # No results is an exception.
        self.assertRaises(User.DoesNotExist, User.get, User.username == 'x')
        # Multiple results is OK.
        tweet = Tweet.get(Tweet.user == huey_db)
        self.assertTrue(tweet.content in ('meow', 'purr', 'wheeze'))

        # We cannot traverse a join like this.
        @self.database.atomic()
        def has_error():
            Tweet.get(User.username == 'huey')
        self.assertRaises(Exception, has_error)

        # This is OK, though.
        tweet = Tweet.get(user__username='mickey')
        self.assertTrue(tweet.content in ('woof', 'yip'))

        tweet = Tweet.get(content__ilike='w%',
                          user__username__ilike='%ck%')
        self.assertEqual(tweet.content, 'woof')

    @requires_models(User)
    def test_get_with_alias(self):
        huey = self.add_user('huey')
        query = (User
                 .select(User.username.alias('name'))
                 .where(User.username == 'huey'))
        obj = query.dicts().get()
        self.assertEqual(obj, {'name': 'huey'})

        obj = query.objects().get()
        self.assertEqual(obj.name, 'huey')

    @requires_models(User, Tweet)
    def test_get_or_none(self):
        huey = self.add_user('huey')
        self.assertEqual(User.get_or_none(User.username == 'huey').username,
                         'huey')
        self.assertIsNone(User.get_or_none(User.username == 'foo'))

    @requires_models(User, Color)
    def test_get_by_id(self):
        huey = self.add_user('huey')
        self.assertEqual(User.get_by_id(huey.id).username, 'huey')

        Color.insert_many([
            {'name': 'red', 'is_neutral': False},
            {'name': 'blue', 'is_neutral': False}]).execute()
        self.assertEqual(Color.get_by_id('red').name, 'red')
        self.assertRaises(Color.DoesNotExist, Color.get_by_id, 'green')

        self.assertEqual(Color['red'].name, 'red')
        self.assertRaises(Color.DoesNotExist, lambda: Color['green'])

    @requires_models(User, Color)
    def test_get_set_item(self):
        huey = self.add_user('huey')
        huey_db = User[huey.id]
        self.assertEqual(huey_db.username, 'huey')

        User[huey.id] = {'username': 'huey-x'}
        huey_db = User[huey.id]
        self.assertEqual(huey_db.username, 'huey-x')
        del User[huey.id]
        self.assertEqual(len(User), 0)

        # Allow creation by specifying None for key.
        User[None] = {'username': 'zaizee'}
        User.get(User.username == 'zaizee')

    @requires_models(User)
    def test_get_or_create(self):
        huey, created = User.get_or_create(username='huey')
        self.assertTrue(created)
        huey2, created2 = User.get_or_create(username='huey')
        self.assertFalse(created2)
        self.assertEqual(huey.id, huey2.id)

    @requires_models(Category)
    def test_get_or_create_self_referential_fk(self):
        parent = Category.create(name='parent')
        child, created = Category.get_or_create(parent=parent, name='child')
        child_db = Category.get(Category.parent == parent)
        self.assertEqual(child_db.parent.name, 'parent')
        self.assertEqual(child_db.name, 'child')

    @requires_models(Person)
    def test_save(self):
        huey = Person(first='huey', last='cat', dob=datetime.date(2010, 7, 1))
        self.assertTrue(huey.save() > 0)
        self.assertTrue(huey.id is not None)  # Ensure PK is set.
        orig_id = huey.id

        # Test initial save (INSERT) worked and data is all present.
        huey_db = Person.get(first='huey', last='cat')
        self.assertEqual(huey_db.id, huey.id)
        self.assertEqual(huey_db.first, 'huey')
        self.assertEqual(huey_db.last, 'cat')
        self.assertEqual(huey_db.dob, datetime.date(2010, 7, 1))

        # Make a change and do a second save (UPDATE).
        huey.dob = datetime.date(2010, 7, 2)
        self.assertTrue(huey.save() > 0)
        self.assertEqual(huey.id, orig_id)

        # Test UPDATE worked correctly.
        huey_db = Person.get(first='huey', last='cat')
        self.assertEqual(huey_db.id, huey.id)
        self.assertEqual(huey_db.first, 'huey')
        self.assertEqual(huey_db.last, 'cat')
        self.assertEqual(huey_db.dob, datetime.date(2010, 7, 2))

        self.assertEqual(Person.select().count(), 1)

    @requires_models(Person)
    def test_save_only(self):
        huey = Person(first='huey', last='cat', dob=datetime.date(2010, 7, 1))
        huey.save()

        huey.first = 'huker'
        huey.last = 'kitten'
        self.assertTrue(huey.save(only=('first',)) > 0)

        huey_db = Person.get_by_id(huey.id)
        self.assertEqual(huey_db.first, 'huker')
        self.assertEqual(huey_db.last, 'cat')
        self.assertEqual(huey_db.dob, datetime.date(2010, 7, 1))

        huey.first = 'hubie'
        self.assertTrue(huey.save(only=[Person.last]) > 0)

        huey_db = Person.get_by_id(huey.id)
        self.assertEqual(huey_db.first, 'huker')
        self.assertEqual(huey_db.last, 'kitten')
        self.assertEqual(huey_db.dob, datetime.date(2010, 7, 1))

        self.assertEqual(Person.select().count(), 1)

    @requires_models(Color, User)
    def test_save_force(self):
        huey = User(username='huey')
        self.assertTrue(huey.save() > 0)
        huey_id = huey.id

        huey.username = 'zaizee'
        self.assertTrue(huey.save(force_insert=True, only=('username',)) > 0)
        zaizee_id = huey.id
        self.assertTrue(huey_id != zaizee_id)

        query = User.select().order_by(User.username)
        self.assertEqual([user.username for user in query], ['huey', 'zaizee'])

        color = Color(name='red')
        self.assertFalse(bool(color.save()))
        self.assertEqual(Color.select().count(), 0)

        color = Color(name='blue')
        color.save(force_insert=True)
        self.assertEqual(Color.select().count(), 1)

        with self.database.atomic():
            self.assertRaises(IntegrityError,
                              color.save,
                              force_insert=True)

    @requires_models(User, Tweet)
    def test_populate_unsaved_relations(self):
        u = User(username='huey')
        t = Tweet(user=u, content='meow')
        u.save()
        t.save()
        t_db = Tweet.get(Tweet.content == 'meow')
        self.assertEqual(t_db.user.username, 'huey')

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
    def test_join_two_fks(self):
        with self.database.atomic():
            huey = self.add_user('huey')
            mickey = self.add_user('mickey')
            h_m, h_p, h_h = self.add_tweets(huey, 'meow', 'purr', 'hiss')
            m_w, m_b = self.add_tweets(mickey, 'woof', 'bark')
            Favorite.create(user=huey, tweet=m_w)
            Favorite.create(user=mickey, tweet=h_m)
            Favorite.create(user=mickey, tweet=h_p)

        UA = User.alias()

        query = (Favorite
                 .select(Favorite, Tweet, User, UA)
                 .join(Tweet)
                 .join(User)
                 .switch(Favorite)
                 .join(UA, on=Favorite.user)
                 .order_by(Favorite.id))
        with self.assertQueryCount(1):
            accum = [(f.tweet.user.username, f.tweet.content, f.user.username)
                     for f in query]

        self.assertEqual(accum, [
            ('mickey', 'woof', 'huey'),
            ('huey', 'meow', 'mickey'),
            ('huey', 'purr', 'mickey')])

        # Test intermediate models not selected.
        query = (Favorite
                 .select()
                 .join(Tweet)
                 .switch(Favorite)
                 .join(User)
                 .where(User.username == 'mickey')
                 .order_by(Favorite.id))
        with self.assertQueryCount(5):
            accum = [(f.user.username, f.tweet.content) for f in query]

        self.assertEqual(accum, [('mickey', 'meow'), ('mickey', 'purr')])

    @requires_models(A, B, C)
    def test_join_issue_1482(self):
        a1 = A.create(a='a1')
        b1 = B.create(a=a1, b='b1')
        c1 = C.create(b=b1, c='c1')

        query = (C
                 .select()
                 .join(B)
                 .join(A)
                 .where(A.a == 'a1'))
        with self.assertQueryCount(3):
            accum = [(c.c, c.b.b, c.b.a.a) for c in query]

        self.assertEqual(accum, [('c1', 'b1', 'a1')])

    @requires_models(A, B, C)
    def test_join_empty_intermediate_model(self):
        a1 = A.create(a='a1')
        a2 = A.create(a='a2')
        b11 = B.create(a=a1, b='b11')
        b12 = B.create(a=a1, b='b12')
        b21 = B.create(a=a2, b='b21')
        c111 = C.create(b=b11, c='c111')
        c112 = C.create(b=b11, c='c112')
        c211 = C.create(b=b21, c='c211')

        query = (C
                 .select(C, A.a)
                 .join(B)
                 .join(A)
                 .order_by(C.c))
        with self.assertQueryCount(1):
            accum = [(c.c, c.b.a.a) for c in query]
        self.assertEqual(accum, [
            ('c111', 'a1'),
            ('c112', 'a1'),
            ('c211', 'a2')])

        query = (C
                 .select(C, B, A)
                 .join(B)
                 .join(A)
                 .order_by(C.c))
        with self.assertQueryCount(1):
            accum = [(c.c, c.b.b, c.b.a.a) for c in query]
        self.assertEqual(accum, [
            ('c111', 'b11', 'a1'),
            ('c112', 'b11', 'a1'),
            ('c211', 'b21', 'a2')])

    @requires_models(Relationship, Person)
    def test_join_same_model_twice(self):
        d = datetime.date(2010, 1, 1)
        huey = Person.create(first='huey', last='cat', dob=d)
        zaizee = Person.create(first='zaizee', last='cat', dob=d)
        mickey = Person.create(first='mickey', last='dog', dob=d)
        relationships = (
            (huey, zaizee),
            (zaizee, huey),
            (mickey, huey),
        )
        for src, dest in relationships:
            Relationship.create(from_person=src, to_person=dest)

        PA = Person.alias()
        query = (Relationship
                 .select(Relationship, Person, PA)
                 .join(Person, on=Relationship.from_person)
                 .switch(Relationship)
                 .join(PA, on=Relationship.to_person)
                 .order_by(Relationship.id))
        with self.assertQueryCount(1):
            results = [(r.from_person.first, r.to_person.first) for r in query]

        self.assertEqual(results, [
            ('huey', 'zaizee'),
            ('zaizee', 'huey'),
            ('mickey', 'huey')])

    @requires_models(User)
    def test_peek(self):
        for username in ('huey', 'mickey', 'zaizee'):
            self.add_user(username)

        query = User.select(User.username).order_by(User.username).dicts()
        with self.assertQueryCount(1):
            self.assertEqual(query.peek(n=1), {'username': 'huey'})
            self.assertEqual(query.peek(n=2), [{'username': 'huey'},
                                               {'username': 'mickey'}])

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

        res = query.count()
        self.assertEqual(res, 5)

    def _create_user_tweets(self):
        data = (('huey', ('meow', 'purr', 'hiss')),
                ('zaizee', ()),
                ('mickey', ('woof', 'grr')))

        with self.database.atomic():
            ts = int(time.time())
            for username, tweets in data:
                user = User.create(username=username)
                for tweet in tweets:
                    Tweet.create(user=user, content=tweet, timestamp=ts)
                    ts += 1

    @requires_models(User, Tweet)
    def test_join_subquery(self):
        self._create_user_tweets()

        # Select note user and timestamp of most recent tweet.
        TA = Tweet.alias()
        max_q = (TA
                 .select(TA.user, fn.MAX(TA.timestamp).alias('max_ts'))
                 .group_by(TA.user)
                 .alias('max_q'))

        predicate = ((Tweet.user == max_q.c.user_id) &
                     (Tweet.timestamp == max_q.c.max_ts))
        latest = (Tweet
                  .select(Tweet.user, Tweet.content, Tweet.timestamp)
                  .join(max_q, on=predicate)
                  .alias('latest'))

        query = (User
                 .select(User, latest.c.content, latest.c.timestamp)
                 .join(latest, on=(User.id == latest.c.user_id)))

        with self.assertQueryCount(1):
            data = [(user.username, user.tweet.content) for user in query]

        # Failing on travis-ci...old SQLite?
        if not IS_OLD_SQLITE:
            self.assertEqual(data, [
                ('huey', 'hiss'),
                ('mickey', 'grr')])

        query = (Tweet
                 .select(Tweet, User)
                 .join(max_q, on=predicate)
                 .switch(Tweet)
                 .join(User))
        with self.assertQueryCount(1):
            data = [(note.user.username, note.content) for note in query]

        self.assertEqual(data, [
            ('huey', 'hiss'),
            ('mickey', 'grr')])

    @requires_models(User, Tweet)
    def test_join_subquery_2(self):
        self._create_user_tweets()

        users = (User
                 .select(User.id, User.username)
                 .where(User.username.in_(['huey', 'zaizee'])))
        query = (Tweet
                 .select(Tweet.content, users.c.username)
                 .join(users, on=(Tweet.user == users.c.id))
                 .order_by(Tweet.id))

        self.assertSQL(query, (
            'SELECT "t1"."content", "t2"."username" '
            'FROM "tweet" AS "t1" '
            'INNER JOIN (SELECT "t3"."id", "t3"."username" '
            'FROM "users" AS "t3" '
            'WHERE ("t3"."username" IN (?, ?))) AS "t2" '
            'ON ("t1"."user_id" = "t2"."id") '
            'ORDER BY "t1"."id"'), ['huey', 'zaizee'])
        with self.assertQueryCount(1):
            results = [(t.content, t.user.username) for t in query]
            if IS_OLD_SQLITE:
                self.assertEqual(results, [
                    ('meow', None),
                    ('purr', None),
                    ('hiss', None)])
            else:
                self.assertEqual(results, [
                    ('meow', 'huey'),
                    ('purr', 'huey'),
                    ('hiss', 'huey')])

    @requires_models(User, Tweet)
    @skip_if(IS_MYSQL or IS_OLD_SQLITE)
    def test_join_subquery_cte(self):
        self._create_user_tweets()

        cte = (User
               .select(User.id, User.username)
               .where(User.username.in_(['huey', 'zaizee']))\
               .cte('cats'))

        # Attempt join with subquery as common-table expression.
        query = (Tweet
                 .select(Tweet.content, cte.c.username)
                 .join(cte, on=(Tweet.user == cte.c.id))
                 .order_by(Tweet.id)
                 .with_cte(cte))
        self.assertSQL(query, (
            'WITH "cats" AS ('
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'WHERE ("t1"."username" IN (?, ?))) '
            'SELECT "t2"."content", "cats"."username" FROM "tweet" AS "t2" '
            'INNER JOIN "cats" ON ("t2"."user_id" = "cats"."id") '
            'ORDER BY "t2"."id"'), ['huey', 'zaizee'])
        with self.assertQueryCount(1):
            self.assertEqual([t.content for t in query],
                             ['meow', 'purr', 'hiss'])

    @requires_models(User, Tweet)
    def test_insert_query_value(self):
        huey = self.add_user('huey')
        query = User.select(User.id).where(User.username == 'huey')
        tid = Tweet.insert(content='meow', user=query).execute()
        tweet = Tweet[tid]
        self.assertEqual(tweet.user.id, huey.id)
        self.assertEqual(tweet.user.username, 'huey')

    @requires_models(Register)
    @skip_if(IS_SQLITE and sqlite3.sqlite_version_info < (3, 9))
    def test_compound_select(self):
        for i in range(10):
            Register.create(value=i)

        q1 = Register.select().where(Register.value < 2)
        q2 = Register.select().where(Register.value > 7)
        c1 = (q1 | q2).order_by(SQL('2'))

        self.assertSQL(c1, (
            'SELECT "t1"."id", "t1"."value" FROM "register" AS "t1" '
            'WHERE ("t1"."value" < ?) UNION '
            'SELECT "t2"."id", "t2"."value" FROM "register" AS "t2" '
            'WHERE ("t2"."value" > ?) ORDER BY 2'), [2, 7])

        self.assertEqual([row.value for row in c1], [0, 1, 8, 9],
                         [row.__data__ for row in c1])
        self.assertEqual(c1.count(), 4)

        q3 = Register.select().where(Register.value == 5)
        c2 = (c1.order_by() | q3).order_by(SQL('2'))

        self.assertSQL(c2, (
            'SELECT "t1"."id", "t1"."value" FROM "register" AS "t1" '
            'WHERE ("t1"."value" < ?) UNION '
            'SELECT "t2"."id", "t2"."value" FROM "register" AS "t2" '
            'WHERE ("t2"."value" > ?) UNION '
            'SELECT "t2"."id", "t2"."value" FROM "register" AS "t2" '
            'WHERE ("t2"."value" = ?) ORDER BY 2'), [2, 7, 5])

        self.assertEqual([row.value for row in c2], [0, 1, 5, 8, 9])
        self.assertEqual(c2.count(), 5)

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
                     .where(Category.parent == root)
                     .order_by(Category.name))
            query = query.join(Parent, on=(Category.parent == Parent.name))
            c1_db, c2_db = list(query)

            self.assertEqual(c1_db.name, 'child-1')
            self.assertEqual(c1_db.parent.name, 'root')
            self.assertEqual(c2_db.name, 'child-2')
            self.assertEqual(c2_db.parent.name, 'root')

    @requires_models(Category)
    def test_empty_joined_instance(self):
        root = Category.create(name='a')
        c1 = Category.create(name='c1', parent=root)
        c2 = Category.create(name='c2', parent=root)

        with self.assertQueryCount(1):
            Parent = Category.alias('p')
            query = (Category
                     .select(Category, Parent)
                     .join(Parent, JOIN.LEFT_OUTER,
                           on=(Category.parent == Parent.name))
                     .order_by(Category.name))
            result = [(category.name, category.parent is None)
                      for category in query]

        self.assertEqual(result, [('a', True), ('c1', False), ('c2', False)])

    @requires_models(User, Tweet)
    def test_from_multi_table(self):
        self.add_tweets(self.add_user('huey'), 'meow', 'hiss', 'purr')
        self.add_tweets(self.add_user('mickey'), 'woof', 'wheeze')
        query = (Tweet
                 .select(Tweet, User)
                 .from_(Tweet, User)
                 .where(
                     (Tweet.user == User.id) &
                     (User.username == 'huey'))
                 .order_by(Tweet.id)
                 .dicts())

        with self.assertQueryCount(1):
            self.assertEqual([t['content'] for t in query],
                             ['meow', 'hiss', 'purr'])
            self.assertEqual([t['username'] for t in query],
                             ['huey', 'huey', 'huey'])

    @requires_models(User, Tweet)
    def test_filtering(self):
        with self.database.atomic():
            huey = self.add_user('huey')
            mickey = self.add_user('mickey')
            self.add_tweets(huey, 'meow', 'hiss', 'purr')
            self.add_tweets(mickey, 'woof', 'wheeze')

        query = Tweet.filter(user__username='huey').order_by(Tweet.content)
        self.assertEqual([row.content for row in query],
                         ['hiss', 'meow', 'purr'])

        query = User.filter(tweets__content__ilike='w%')
        self.assertEqual([user.username for user in query],
                         ['mickey', 'mickey'])

    def test_deferred_fk(self):
        class Note(TestModel):
            foo = DeferredForeignKey('Foo', backref='notes')

        class Foo(TestModel):
            note = ForeignKeyField(Note)

        self.assertTrue(Note.foo.rel_model is Foo)
        self.assertTrue(Foo.note.rel_model is Note)
        f = Foo(id=1337)
        self.assertSQL(f.notes, (
            'SELECT "t1"."id", "t1"."foo_id" FROM "note" AS "t1" '
            'WHERE ("t1"."foo_id" = ?)'), [1337])

    def test_table_schema(self):
        class Schema(TestModel):
            pass

        self.assertTrue(Schema._meta.schema is None)
        self.assertSQL(Schema.select(), (
            'SELECT "t1"."id" FROM "schema" AS "t1"'), [])

        Schema._meta.schema = 'test'
        self.assertSQL(Schema.select(), (
            'SELECT "t1"."id" FROM "test"."schema" AS "t1"'), [])

        Schema._meta.schema = 'another'
        self.assertSQL(Schema.select(), (
            'SELECT "t1"."id" FROM "another"."schema" AS "t1"'), [])

    @requires_models(User)
    def test_noop(self):
        query = User.noop()
        self.assertEqual(list(query), [])

    @requires_models(User)
    def test_iteration(self):
        self.assertEqual(list(User), [])
        self.assertEqual(len(User), 0)
        self.assertTrue(User)

        User.insert_many((['charlie'], ['huey']), [User.username]).execute()
        self.assertEqual(sorted(u.username for u in User), ['charlie', 'huey'])
        self.assertEqual(len(User), 2)
        self.assertTrue(User)

    @requires_models(User)
    def test_iterator(self):
        users = ['charlie', 'huey', 'zaizee']
        with self.database.atomic():
            for username in users:
                User.create(username=username)

        with self.assertQueryCount(1):
            query = User.select().order_by(User.username).iterator()
            self.assertEqual([u.username for u in query], users)

            self.assertEqual(list(query), [])

    @requires_models(User)
    def test_select_count(self):
        users = [self.add_user(u) for u in ('huey', 'charlie', 'mickey')]
        self.assertEqual(User.select().count(), 3)

        qr = User.select().execute()
        self.assertEqual(qr.count, 0)

        list(qr)
        self.assertEqual(qr.count, 3)

    @requires_models(User)
    def test_batch_commit(self):
        commit_method = self.database.commit

        def assertBatch(n_rows, batch_size, n_commits):
            User.delete().execute()
            user_data = [{'username': 'u%s' % i} for i in range(n_rows)]
            with mock.patch.object(self.database, 'commit') as mock_commit:
                mock_commit.side_effect = commit_method
                for row in self.database.batch_commit(user_data, batch_size):
                    User.create(**row)

                self.assertEqual(mock_commit.call_count, n_commits)
                self.assertEqual(User.select().count(), n_rows)

        assertBatch(6, 1, 6)
        assertBatch(6, 2, 3)
        assertBatch(6, 3, 2)
        assertBatch(6, 4, 2)
        assertBatch(6, 6, 1)
        assertBatch(6, 7, 1)


class TestRaw(ModelTestCase):
    database = get_in_memory_db()
    requires = [User]

    def test_raw(self):
        with self.database.atomic():
            for username in ('charlie', 'chuck', 'huey', 'zaizee'):
                User.create(username=username)

        query = (User
                 .raw('SELECT username, SUBSTR(username, 1, 1) AS first '
                      'FROM users '
                      'WHERE SUBSTR(username, 1, 1) = ? '
                      'ORDER BY username DESC', 'c'))
        self.assertEqual([(row.username, row.first) for row in query],
                         [('chuck', 'c'), ('charlie', 'c')])

    def test_raw_iterator(self):
        (User
         .insert_many([('charlie',), ('huey',)], fields=[User.username])
         .execute())

        with self.assertQueryCount(1):
            query = User.raw('SELECT * FROM users ORDER BY id')
            results = [user.username for user in query.iterator()]
            self.assertEqual(results, ['charlie', 'huey'])

            # Since we used iterator(), the results were not cached.
            self.assertEqual([u.username for u in query], [])


class TestDeleteInstance(ModelTestCase):
    database = get_in_memory_db()
    requires = [User, Account, Tweet, Favorite]

    def setUp(self):
        super(TestDeleteInstance, self).setUp()
        with self.database.atomic():
            huey = User.create(username='huey')
            acct = Account.create(user=huey, email='huey@meow.com')
            for content in ('meow', 'purr'):
                Tweet.create(user=huey, content=content)
            mickey = User.create(username='mickey')
            woof = Tweet.create(user=mickey, content='woof')
            Favorite.create(user=huey, tweet=woof)
            Favorite.create(user=mickey, tweet=Tweet.create(user=huey,
                                                            content='hiss'))

    def test_delete_instance_recursive(self):
        huey = User.get(User.username == 'huey')
        huey.delete_instance(recursive=True)
        self.assertEqual(User.select().count(), 1)

        acct = Account.get(Account.email == 'huey@meow.com')
        self.assertTrue(acct.user is None)

        self.assertEqual(Favorite.select().count(), 0)

        self.assertEqual(Tweet.select().count(), 1)
        tweet = Tweet.get()
        self.assertEqual(tweet.content, 'woof')

    def test_delete_nullable(self):
        huey = User.get(User.username == 'huey')
        huey.delete_instance(recursive=True, delete_nullable=True)
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(Account.select().count(), 0)
        self.assertEqual(Favorite.select().count(), 0)

        self.assertEqual(Tweet.select().count(), 1)
        tweet = Tweet.get()
        self.assertEqual(tweet.content, 'woof')


def incrementer():
    d = {'value': 0}
    def increment():
        d['value'] += 1
        return d['value']
    return increment

class AutoCounter(TestModel):
    counter = IntegerField(default=incrementer())
    control = IntegerField(default=1)


class TestDefaultDirtyBehavior(ModelTestCase):
    database = get_in_memory_db()
    requires = [AutoCounter]

    def tearDown(self):
        super(TestDefaultDirtyBehavior, self).tearDown()
        AutoCounter._meta.only_save_dirty = False

    def test_default_dirty(self):
        AutoCounter._meta.only_save_dirty = True

        ac = AutoCounter()
        ac.save()
        self.assertEqual(ac.counter, 1)
        self.assertEqual(ac.control, 1)

        ac_db = AutoCounter.get((AutoCounter.counter == 1) &
                                (AutoCounter.control == 1))
        self.assertEqual(ac_db.counter, 1)
        self.assertEqual(ac_db.control, 1)

        # No changes.
        self.assertFalse(ac_db.save())

        ac = AutoCounter.create()
        self.assertEqual(ac.counter, 2)
        self.assertEqual(ac.control, 1)

        AutoCounter._meta.only_save_dirty = False

        ac = AutoCounter()
        self.assertEqual(ac.counter, 3)
        self.assertEqual(ac.control, 1)
        ac.save()

        ac_db = AutoCounter.get(AutoCounter.id == ac.id)
        self.assertEqual(ac_db.counter, 3)


class TestDefaultValues(ModelTestCase):
    database = get_in_memory_db()
    requires = [Sample, SampleMeta]

    def test_default_absent_on_insert(self):
        query = Sample.insert(counter=0)
        self.assertSQL(query, (
            'INSERT INTO "sample" ("counter", "value") '
            'VALUES (?, ?)'), [0, 1.0])

        query = Sample.insert_many([
            {'counter': '0'},
            {'counter': 1, 'value': 2},
            {'counter': '2'}])
        self.assertSQL(query, (
            'INSERT INTO "sample" ("counter", "value") '
            'VALUES (?, ?), (?, ?), (?, ?)'), [0, 1.0, 1, 2.0, 2, 1.0])

        query = Sample.insert_many([(0,), (1, 2.)],
                                   fields=[Sample.counter])
        self.assertSQL(query, (
            'INSERT INTO "sample" ("counter", "value") '
            'VALUES (?, ?), (?, ?)'), [0, 1.0, 1, 2.0])


    def test_default_present_on_create(self):
        s = Sample.create(counter=3)
        s_db = Sample.get(Sample.counter == 3)
        self.assertEqual(s_db.value, 1.)

    def test_defaults_from_cursor(self):
        s = Sample.create(counter=1)
        sm1 = SampleMeta.create(sample=s, value=1.)
        sm2 = SampleMeta.create(sample=s, value=2.)

        # Simple query.
        query = SampleMeta.select(SampleMeta.sample).order_by(SampleMeta.value)

        with self.assertQueryCount(1):
            sm1_db, sm2_db = list(query)
            self.assertIsNone(sm1_db.value)
            self.assertIsNone(sm2_db.value)

        # Join-graph query.
        query = (SampleMeta
                 .select(SampleMeta.sample,
                         Sample.counter)
                 .join(Sample)
                 .order_by(SampleMeta.value))

        with self.assertQueryCount(1):
            sm1_db, sm2_db = list(query)
            self.assertIsNone(sm1_db.value)
            self.assertIsNone(sm2_db.value)
            self.assertIsNone(sm1_db.sample.value)
            self.assertIsNone(sm2_db.sample.value)
            self.assertEqual(sm1_db.sample.counter, 1)
            self.assertEqual(sm2_db.sample.counter, 1)


class TestFunctionCoerce(ModelTestCase):
    database = get_in_memory_db()
    requires = [Sample]

    def test_coerce(self):
        for i in range(3):
            Sample.create(counter=i, value=i)

        counter_group = fn.GROUP_CONCAT(Sample.counter).coerce(False)
        query = Sample.select(counter_group.alias('counter'))
        self.assertEqual(query.get().counter, '0,1,2')

        query = Sample.select(counter_group.alias('counter_group'))
        self.assertEqual(query.get().counter_group, '0,1,2')

    @requires_models(Category)
    def test_no_coerce_count(self):
        for i in range(10):
            Category.create(name=str(i))

        # COUNT() does not result in the value being coerced.
        query = Category.select(fn.COUNT(Category.name))
        self.assertEqual(query.scalar(), 10)

        # Force the value to be coerced using the field's db_value().
        query = Category.select(fn.COUNT(Category.name).coerce(True))
        self.assertEqual(query.scalar(), '10')


class TestJoinModelAlias(ModelTestCase):
    data = (
        ('huey', 'meow'),
        ('huey', 'purr'),
        ('zaizee', 'hiss'),
        ('mickey', 'woof'))
    requires = [User, Tweet]

    def setUp(self):
        super(TestJoinModelAlias, self).setUp()
        users = {}
        for username, tweet in self.data:
            if username not in users:
                users[username] = user = User.create(username=username)
            else:
                user = users[username]
            Tweet.create(user=user, content=tweet)

    def _test_query(self, alias_expr):
        UA = alias_expr()
        return (Tweet
                .select(Tweet, UA)
                .order_by(UA.username, Tweet.content))

    def assertTweets(self, query, user_attr='user'):
        with self.assertQueryCount(1):
            data = [(getattr(tweet, user_attr).username, tweet.content)
                    for tweet in query]
        self.assertEqual(sorted(self.data), data)

    def test_control(self):
        self.assertTweets(self._test_query(lambda: User).join(User))

    def test_join(self):
        UA = User.alias('ua')
        query = self._test_query(lambda: UA).join(UA)
        self.assertTweets(query)

    def test_join_on(self):
        UA = User.alias('ua')
        query = self._test_query(lambda: UA)
        query = query.join(UA, on=(Tweet.user == UA.id))
        self.assertTweets(query)

    def test_join_on_field(self):
        UA = User.alias('ua')
        query = self._test_query(lambda: UA)
        query = query.join(UA, on=Tweet.user)
        self.assertTweets(query)

    def test_join_on_alias(self):
        UA = User.alias('ua')
        query = self._test_query(lambda: UA)
        query = query.join(UA, on=(Tweet.user == UA.id).alias('foo'))
        self.assertTweets(query, 'foo')

    def test_join_attr(self):
        UA = User.alias('ua')
        query = self._test_query(lambda: UA).join(UA, attr='baz')
        self.assertTweets(query, 'baz')

    def _test_query_backref(self, alias_expr):
        TA = alias_expr()
        return (User
                .select(User, TA)
                .order_by(User.username, TA.content))

    def assertUsers(self, query, tweet_attr='tweet'):
        with self.assertQueryCount(1):
            data = [(user.username, getattr(user, tweet_attr).content)
                    for user in query]
        self.assertEqual(sorted(self.data), data)

    def test_control_backref(self):
        self.assertUsers(self._test_query_backref(lambda: Tweet).join(Tweet))

    def test_join_backref(self):
        TA = Tweet.alias('ta')
        query = self._test_query_backref(lambda: TA).join(TA)
        self.assertUsers(query)

    def test_join_on_backref(self):
        TA = Tweet.alias('ta')
        query = self._test_query_backref(lambda: TA)
        query = query.join(TA, on=(User.id == TA.user_id))
        self.assertUsers(query)

    def test_join_on_field_backref(self):
        TA = Tweet.alias('ta')
        query = self._test_query_backref(lambda: TA)
        query = query.join(TA, on=TA.user)
        self.assertUsers(query)

    def test_join_on_alias_backref(self):
        TA = Tweet.alias('ta')
        query = self._test_query_backref(lambda: TA)
        query = query.join(TA, on=(User.id == TA.user_id).alias('foo'))
        self.assertUsers(query, 'foo')

    def test_join_attr_backref(self):
        TA = Tweet.alias('ta')
        query = self._test_query_backref(lambda: TA).join(TA, attr='baz')
        self.assertUsers(query, 'baz')

    def test_join_alias_twice(self):
        # Test that a model-alias can be both the source and the dest by
        # joining from User -> Tweet -> User (as "foo").
        TA = Tweet.alias('ta')
        UA = User.alias('ua')
        query = (User
                 .select(User, TA, UA)
                 .join(TA)
                 .join(UA, on=(TA.user_id == UA.id).alias('foo'))
                 .order_by(User.username, TA.content))
        with self.assertQueryCount(1):
            data = [(row.username, row.tweet.content, row.tweet.foo.username)
                    for row in query]

        self.assertEqual(data, [
            ('huey', 'meow', 'huey'),
            ('huey', 'purr', 'huey'),
            ('mickey', 'woof', 'mickey'),
            ('zaizee', 'hiss', 'zaizee')])

    def test_alias_filter(self):
        UA = User.alias('ua')
        lookups = ({'ua__username': 'huey'}, {'user__username': 'huey'})
        for lookup in lookups:
            query = (Tweet
                     .select(Tweet.content, UA.username)
                     .join(UA)
                     .filter(**lookup)
                     .order_by(Tweet.content))
            self.assertSQL(query, (
                'SELECT "t1"."content", "ua"."username" '
                'FROM "tweet" AS "t1" '
                'INNER JOIN "users" AS "ua" '
                'ON ("t1"."user_id" = "ua"."id") '
                'WHERE ("ua"."username" = ?) '
                'ORDER BY "t1"."content"'), ['huey'])
            with self.assertQueryCount(1):
                data = [(t.content, t.user.username) for t in query]
                self.assertEqual(data, [('meow', 'huey'), ('purr', 'huey')])


@skip_case_unless(isinstance(db, PostgresqlDatabase))
class TestWindowFunctionIntegration(ModelTestCase):
    requires = [Sample]

    def setUp(self):
        super(TestWindowFunctionIntegration, self).setUp()
        values = ((1, 10), (1, 20), (2, 1), (2, 3), (3, 100))
        with self.database.atomic():
            for counter, value in values:
                Sample.create(counter=counter, value=value)

    def test_simple_partition(self):
        query = (Sample
                 .select(Sample.counter, Sample.value,
                         fn.AVG(Sample.value).over(
                             partition_by=[Sample.counter]))
                 .order_by(Sample.counter)
                 .tuples())
        expected = [
            (1, 10., 15.),
            (1, 20., 15.),
            (2, 1., 2.),
            (2, 3., 2.),
            (3, 100., 100.)]
        self.assertEqual(list(query), expected)

        window = Window(partition_by=[Sample.counter])
        query = (Sample
                 .select(Sample.counter, Sample.value,
                         fn.AVG(Sample.value).over(window))
                 .window(window)
                 .order_by(Sample.counter)
                 .tuples())
        self.assertEqual(list(query), expected)

    def test_ordered_window(self):
        window = Window(partition_by=[Sample.counter],
                        order_by=[Sample.value.desc()])
        query = (Sample
                 .select(Sample.counter, Sample.value,
                         fn.RANK().over(window=window).alias('rank'))
                 .window(window)
                 .order_by(Sample.counter, SQL('rank'))
                 .tuples())
        self.assertEqual(list(query), [
            (1, 20., 1),
            (1, 10., 2),
            (2, 3., 1),
            (2, 1., 2),
            (3, 100., 1)])

    def test_two_windows(self):
        w1 = Window(partition_by=[Sample.counter]).alias('w1')
        w2 = Window(order_by=[Sample.counter]).alias('w2')
        query = (Sample
                 .select(Sample.counter, Sample.value,
                         fn.AVG(Sample.value).over(window=w1),
                         fn.RANK().over(window=w2))
                 .window(w1, w2)
                 .order_by(Sample.id)
                 .tuples())
        self.assertEqual(list(query), [
            (1, 10., 15., 1),
            (1, 20., 15., 1),
            (2, 1., 2., 3),
            (2, 3., 2., 3),
            (3, 100., 100., 5)])

    def test_empty_over(self):
        query = (Sample
                 .select(Sample.counter, Sample.value,
                         fn.LAG(Sample.counter, 1).over())
                 .order_by(Sample.id)
                 .tuples())
        self.assertEqual(list(query), [
            (1, 10., None),
            (1, 20., 1),
            (2, 1., 1),
            (2, 3., 2),
            (3, 100., 2)])

    def test_bounds(self):
        query = (Sample
                 .select(Sample.value,
                         fn.SUM(Sample.value).over(
                             partition_by=[Sample.counter],
                             start=Window.preceding(),
                             end=Window.following(1)))
                 .order_by(Sample.id)
                 .tuples())
        self.assertEqual(list(query), [
            (10., 30.),
            (20., 30.),
            (1., 4.),
            (3., 4.),
            (100., 100.)])

        query = (Sample
                 .select(Sample.counter, Sample.value,
                         fn.SUM(Sample.value).over(
                             order_by=[Sample.id],
                             start=Window.preceding(2)))
                 .order_by(Sample.id)
                 .tuples())
        self.assertEqual(list(query), [
            (1, 10., 10.),
            (1, 20., 30.),
            (2, 1., 31.),
            (2, 3., 24.),
            (3, 100., 104.)])


@skip_case_unless(isinstance(db, PostgresqlDatabase))
class TestForUpdateIntegration(ModelTestCase):
    requires = [User]

    def setUp(self):
        super(TestForUpdateIntegration, self).setUp()
        self.alt_db = new_connection()
        class AltUser(User):
            class Meta:
                database = self.alt_db
                table_name = User._meta.table_name
        self.AltUser = AltUser

    def tearDown(self):
        self.alt_db.close()
        super(TestForUpdateIntegration, self).tearDown()

    def test_for_update(self):
        User.create(username='huey')
        zaizee = User.create(username='zaizee')

        AltUser = self.AltUser

        with self.database.manual_commit():
            users = User.select(User.username == 'zaizee').for_update()
            updated = (User
                       .update(username='ziggy')
                       .where(User.username == 'zaizee')
                       .execute())
            self.assertEqual(updated, 1)

            query = (AltUser
                     .select(AltUser.username)
                     .where(AltUser.id == zaizee.id))
            self.assertEqual(query.get().username, 'zaizee')

            self.database.commit()
            self.assertEqual(query.get().username, 'ziggy')

    def test_for_update_nowait(self):
        User.create(username='huey')
        zaizee = User.create(username='zaizee')

        AltUser = self.AltUser

        with self.database.manual_commit():
            users = (User
                     .select(User.username)
                     .where(User.username == 'zaizee')
                     .for_update('FOR UPDATE NOWAIT')
                     .execute())

            def will_fail():
                return (AltUser
                        .select()
                        .where(AltUser.username == 'zaizee')
                        .for_update('FOR UPDATE NOWAIT')
                        .get())

            self.assertRaises(OperationalError, will_fail)


class ServerDefault(TestModel):
    timestamp = DateTimeField(constraints=[SQL('default (now())')])


@skip_case_unless(isinstance(db, PostgresqlDatabase))
class TestReturningIntegration(ModelTestCase):
    requires = [User]

    def test_simple_returning(self):
        query = User.insert(username='charlie')
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") VALUES (?) RETURNING "id"'),
            ['charlie'])

        self.assertEqual(query.execute(), 1)

        query = User.insert(username='huey')
        self.assertEqual(query.execute(), 2)
        self.assertEqual(list(query), [(2,)])

        query = (User
                 .insert(username='zaizee')
                 .returning(User.id, User.username)
                 .dicts())
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") VALUES (?) '
            'RETURNING "id", "username"'), ['zaizee'])

        cursor = query.execute()
        row, = list(cursor)
        self.assertEqual(row, {'id': 3, 'username': 'zaizee'})

        query = (User
                 .insert(username='mickey')
                 .returning(User)
                 .objects())
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") VALUES (?) '
            'RETURNING "id", "username"'), ['mickey'])
        cursor = query.execute()
        row, = list(cursor)
        self.assertEqual(row.id, 4)
        self.assertEqual(row.username, 'mickey')

    @requires_models(ServerDefault)
    def test_returning_server_defaults(self):
        query = (ServerDefault
                 .insert()
                 .returning(ServerDefault.id, ServerDefault.timestamp))
        self.assertSQL(query, (
            'INSERT INTO "serverdefault" '
            'DEFAULT VALUES '
            'RETURNING "id", "timestamp"'), [])

        with self.assertQueryCount(1):
            cursor = query.dicts().execute()
            row, = list(cursor)

        self.assertTrue(row['timestamp'] is not None)

        obj = ServerDefault.get(ServerDefault.id == row['id'])
        self.assertEqual(obj.timestamp, row['timestamp'])

    def test_no_return(self):
        query = User.insert(username='huey').returning()
        self.assertIsNone(query.execute())

        user = User.get(User.username == 'huey')
        self.assertEqual(user.username, 'huey')
        self.assertTrue(user.id >= 1)

    @requires_models(Category)
    def test_non_int_pk_returning(self):
        query = Category.insert(name='root')
        self.assertSQL(query, (
            'INSERT INTO "category" ("name") VALUES (?) RETURNING "name"'),
            ['root'])

        self.assertEqual(query.execute(), 'root')

    def test_returning_multi(self):
        data = [{'username': 'huey'}, {'username': 'mickey'}]
        query = User.insert_many(data)
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") VALUES (?), (?) RETURNING "id"'),
            ['huey', 'mickey'])

        data = query.execute()

        # Check that the result wrapper is correctly set up.
        self.assertTrue(len(data.select) == 1 and data.select[0] is User.id)
        self.assertEqual(list(data), [(1,), (2,)])

        query = (User
                 .insert_many([{'username': 'foo'},
                               {'username': 'bar'},
                               {'username': 'baz'}])
                 .returning(User.id, User.username)
                 .namedtuples())
        data = query.execute()
        self.assertEqual([(row.id, row.username) for row in data], [
            (3, 'foo'),
            (4, 'bar'),
            (5, 'baz')])

    @requires_models(Category)
    def test_returning_query(self):
        for name in ('huey', 'mickey', 'zaizee'):
            Category.create(name=name)

        source = Category.select(Category.name).order_by(Category.name)
        query = User.insert_from(source, (User.username,))
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") '
            'SELECT "t1"."name" FROM "category" AS "t1" ORDER BY "t1"."name" '
            'RETURNING "id"'), [])

        data = query.execute()

        # Check that the result wrapper is correctly set up.
        self.assertTrue(len(data.select) == 1 and data.select[0] is User.id)
        self.assertEqual(list(data), [(1,), (2,), (3,)])

    def test_update_returning(self):
        id_list = User.insert_many([{'username': 'huey'},
                                    {'username': 'zaizee'}]).execute()
        huey_id, zaizee_id = [pk for pk, in id_list]

        query = (User
                 .update(username='ziggy')
                 .where(User.username == 'zaizee')
                 .returning(User.id, User.username))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = ? '
            'WHERE ("username" = ?) '
            'RETURNING "id", "username"'), ['ziggy', 'zaizee'])
        data = query.execute()
        user = data[0]
        self.assertEqual(user.username, 'ziggy')
        self.assertEqual(user.id, zaizee_id)

    def test_delete_returning(self):
        id_list = User.insert_many([{'username': 'huey'},
                                    {'username': 'zaizee'}]).execute()
        huey_id, zaizee_id = [pk for pk, in id_list]

        query = (User
                 .delete()
                 .where(User.username == 'zaizee')
                 .returning(User.id, User.username))
        self.assertSQL(query, (
            'DELETE FROM "users" WHERE ("username" = ?) '
            'RETURNING "id", "username"'), ['zaizee'])
        data = query.execute()
        user = data[0]
        self.assertEqual(user.username, 'zaizee')
        self.assertEqual(user.id, zaizee_id)


supports_tuples = sqlite3.sqlite_version_info >= (3, 15, 0)


@skip_case_unless(isinstance(db, PostgresqlDatabase) or
                  (isinstance(db, SqliteDatabase) and supports_tuples))
class TestTupleComparison(ModelTestCase):
    requires = [User]

    def test_tuples(self):
        ua, ub, uc = [User.create(username=username) for username in 'abc']
        query = User.select().where(
            Tuple(User.username, User.id) == ('b', ub.id))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'WHERE (("t1"."username", "t1"."id") = (?, ?))'), ['b', ub.id])
        self.assertEqual(query.count(), 1)
        obj = query.get()
        self.assertEqual(obj, ub)


class TestModelGraph(BaseTestCase):
    def test_bind_model_database(self):
        class User(Model): pass
        class Tweet(Model):
            user = ForeignKeyField(User)
        class Relationship(Model):
            from_user = ForeignKeyField(User, backref='relationships')
            to_user = ForeignKeyField(User, backref='related_to')
        class Flag(Model):
            tweet = ForeignKeyField(Tweet)
        class Unrelated(Model): pass

        fake_db = SqliteDatabase(None)
        User.bind(fake_db)
        for model in (User, Tweet, Relationship, Flag):
            self.assertTrue(model._meta.database is fake_db)
        self.assertTrue(Unrelated._meta.database is None)
        User.bind(None)

        with User.bind_ctx(fake_db) as (FUser,):
            self.assertTrue(FUser._meta.database is fake_db)
            self.assertTrue(Unrelated._meta.database is None)

        self.assertTrue(User._meta.database is None)


class TestFieldInheritance(BaseTestCase):
    def test_field_inheritance(self):
        class BaseModel(Model):
            class Meta:
                database = get_in_memory_db()

        class BasePost(BaseModel):
            content = TextField()
            timestamp = TimestampField()

        class Photo(BasePost):
            image = TextField()

        class Note(BasePost):
            category = TextField()

        self.assertEqual(BasePost._meta.sorted_field_names,
                         ['id', 'content', 'timestamp'])
        self.assertEqual(BasePost._meta.sorted_fields, [
            BasePost.id,
            BasePost.content,
            BasePost.timestamp])

        self.assertEqual(Photo._meta.sorted_field_names,
                         ['id', 'content', 'timestamp', 'image'])
        self.assertEqual(Photo._meta.sorted_fields, [
            Photo.id,
            Photo.content,
            Photo.timestamp,
            Photo.image])

        self.assertEqual(Note._meta.sorted_field_names,
                         ['id', 'content', 'timestamp', 'category'])
        self.assertEqual(Note._meta.sorted_fields, [
            Note.id,
            Note.content,
            Note.timestamp,
            Note.category])

        self.assertTrue(id(Photo.id) != id(Note.id))

    def test_foreign_key_field_inheritance(self):
        class BaseModel(Model):
            class Meta:
                database = get_in_memory_db()

        class Category(BaseModel):
            name = TextField()

        class BasePost(BaseModel):
            category = ForeignKeyField(Category)
            timestamp = TimestampField()

        class Photo(BasePost):
            image = TextField()

        class Note(BasePost):
            content = TextField()

        self.assertEqual(BasePost._meta.sorted_field_names,
                         ['id', 'category', 'timestamp'])
        self.assertEqual(BasePost._meta.sorted_fields, [
            BasePost.id,
            BasePost.category,
            BasePost.timestamp])

        self.assertEqual(Photo._meta.sorted_field_names,
                         ['id', 'category', 'timestamp', 'image'])
        self.assertEqual(Photo._meta.sorted_fields, [
            Photo.id,
            Photo.category,
            Photo.timestamp,
            Photo.image])

        self.assertEqual(Note._meta.sorted_field_names,
                         ['id', 'category', 'timestamp', 'content'])
        self.assertEqual(Note._meta.sorted_fields, [
            Note.id,
            Note.category,
            Note.timestamp,
            Note.content])

        self.assertEqual(Category._meta.backrefs, {
            BasePost.category: BasePost,
            Photo.category: Photo,
            Note.category: Note})
        self.assertEqual(BasePost._meta.refs, {BasePost.category: Category})
        self.assertEqual(Photo._meta.refs, {Photo.category: Category})
        self.assertEqual(Note._meta.refs, {Note.category: Category})

        self.assertEqual(BasePost.category.backref, 'basepost_set')
        self.assertEqual(Photo.category.backref, 'photo_set')
        self.assertEqual(Note.category.backref, 'note_set')

    def test_foreign_key_pk_inheritance(self):
        class BaseModel(Model):
            class Meta:
                database = get_in_memory_db()
        class Account(BaseModel): pass
        class BaseUser(BaseModel):
            account = ForeignKeyField(Account, primary_key=True)
        class User(BaseUser):
            username = TextField()
        class Admin(BaseUser):
            role = TextField()

        self.assertEqual(Account._meta.backrefs, {
            Admin.account: Admin,
            User.account: User,
            BaseUser.account: BaseUser})

        self.assertEqual(BaseUser.account.backref, 'baseuser_set')
        self.assertEqual(User.account.backref, 'user_set')
        self.assertEqual(Admin.account.backref, 'admin_set')
        self.assertTrue(Account.user_set.model is Account)
        self.assertTrue(Account.admin_set.model is Account)
        self.assertTrue(Account.user_set.rel_model is User)
        self.assertTrue(Account.admin_set.rel_model is Admin)

        self.assertSQL(Account._schema._create_table(), (
            'CREATE TABLE IF NOT EXISTS "account" ('
            '"id" INTEGER NOT NULL PRIMARY KEY)'), [])

        self.assertSQL(User._schema._create_table(), (
            'CREATE TABLE IF NOT EXISTS "user" ('
            '"account_id" INTEGER NOT NULL PRIMARY KEY, '
            '"username" TEXT NOT NULL, '
            'FOREIGN KEY ("account_id") REFERENCES "account" ("id"))'), [])

        self.assertSQL(Admin._schema._create_table(), (
            'CREATE TABLE IF NOT EXISTS "admin" ('
            '"account_id" INTEGER NOT NULL PRIMARY KEY, '
            '"role" TEXT NOT NULL, '
            'FOREIGN KEY ("account_id") REFERENCES "account" ("id"))'), [])

    def test_backref_inheritance(self):
        class Category(TestModel): pass
        def backref(fk_field):
            return '%ss' % fk_field.model._meta.name
        class BasePost(TestModel):
            category = ForeignKeyField(Category, backref=backref)
        class Note(BasePost): pass
        class Photo(BasePost): pass

        self.assertEqual(Category._meta.backrefs, {
            BasePost.category: BasePost,
            Note.category: Note,
            Photo.category: Photo})
        self.assertEqual(BasePost.category.backref, 'baseposts')
        self.assertEqual(Note.category.backref, 'notes')
        self.assertEqual(Photo.category.backref, 'photos')
        self.assertTrue(Category.baseposts.rel_model is BasePost)
        self.assertTrue(Category.baseposts.model is Category)
        self.assertTrue(Category.notes.rel_model is Note)
        self.assertTrue(Category.notes.model is Category)
        self.assertTrue(Category.photos.rel_model is Photo)
        self.assertTrue(Category.photos.model is Category)

        class BaseItem(TestModel):
            category = ForeignKeyField(Category, backref='items')
        class ItemA(BaseItem): pass
        class ItemB(BaseItem): pass

        self.assertEqual(BaseItem.category.backref, 'items')
        self.assertEqual(ItemA.category.backref, 'itema_set')
        self.assertEqual(ItemB.category.backref, 'itemb_set')
        self.assertTrue(Category.items.rel_model is BaseItem)
        self.assertTrue(Category.itema_set.rel_model is ItemA)
        self.assertTrue(Category.itema_set.model is Category)
        self.assertTrue(Category.itemb_set.rel_model is ItemB)
        self.assertTrue(Category.itemb_set.model is Category)

    @skip_if(IS_SQLITE)
    def test_deferred_fk_creation(self):
        class B(TestModel):
            a = DeferredForeignKey('A', null=True)
            b = TextField()
        class A(TestModel):
            a = TextField()

        db.create_tables([A, B])

        try:
            # Test that we can create B with null "a_id" column:
            a = A.create(a='a')
            b = B.create(b='b')

            # Test that we can create B that has no corresponding A:
            fake_a = A(id=31337)
            b2 = B.create(a=fake_a, b='b2')
            b2_db = B.get(B.a == fake_a)
            self.assertEqual(b2_db.b, 'b2')

            # Ensure error occurs trying to create_foreign_key.
            with db.atomic():
                self.assertRaises(
                    IntegrityError,
                    B._schema.create_foreign_key,
                    B.a)

            b2_db.delete_instance()

            # We can now create the foreign key.
            B._schema.create_foreign_key(B.a)

            # The foreign-key is enforced:
            with db.atomic():
                self.assertRaises(IntegrityError, B.create, a=fake_a, b='b3')
        finally:
            db.drop_tables([A, B])


class TestMetaInheritance(BaseTestCase):
    def test_table_name(self):
        class Foo(Model):
            class Meta:
                def table_function(klass):
                    return 'xxx_%s' % klass.__name__.lower()

        class Bar(Foo): pass
        class Baze(Foo):
            class Meta:
                table_name = 'yyy_baze'
        class Biz(Baze): pass
        class Nug(Foo):
            class Meta:
                def table_function(klass):
                    return 'zzz_%s' % klass.__name__.lower()

        self.assertEqual(Foo._meta.table_name, 'xxx_foo')
        self.assertEqual(Bar._meta.table_name, 'xxx_bar')
        self.assertEqual(Baze._meta.table_name, 'yyy_baze')
        self.assertEqual(Biz._meta.table_name, 'xxx_biz')
        self.assertEqual(Nug._meta.table_name, 'zzz_nug')

    def test_composite_key_inheritance(self):
        class Foo(Model):
            key = TextField()
            value = TextField()

            class Meta:
                primary_key = CompositeKey('key', 'value')

        class Bar(Foo): pass
        class Baze(Foo):
            value = IntegerField()

        foo = Foo(key='k1', value='v1')
        self.assertEqual(foo.__composite_key__, ('k1', 'v1'))

        bar = Bar(key='k2', value='v2')
        self.assertEqual(bar.__composite_key__, ('k2', 'v2'))

        baze = Baze(key='k3', value=3)
        self.assertEqual(baze.__composite_key__, ('k3', 3))

    def test_no_primary_key_inheritable(self):
        class Foo(Model):
            data = TextField()

            class Meta:
                primary_key = False

        class Bar(Foo): pass
        class Baze(Foo):
            pk = AutoField()
        class Zai(Foo):
            zee = TextField(primary_key=True)

        self.assertFalse(Foo._meta.primary_key)
        self.assertEqual(Foo._meta.sorted_field_names, ['data'])
        self.assertFalse(Bar._meta.primary_key)
        self.assertEqual(Bar._meta.sorted_field_names, ['data'])

        self.assertTrue(Baze._meta.primary_key is Baze.pk)
        self.assertEqual(Baze._meta.sorted_field_names, ['pk', 'data'])

        self.assertTrue(Zai._meta.primary_key is Zai.zee)
        self.assertEqual(Zai._meta.sorted_field_names, ['zee', 'data'])

    def test_inheritance(self):
        db = SqliteDatabase(':memory:')

        class Base(Model):
            class Meta:
                constraints = ['c1', 'c2']
                database = db
                indexes = (
                    (('username',), True),
                )
                only_save_dirty = True
                options = {'key': 'value'}
                schema = 'magic'
                table_alias = 'ba'

        class Child(Base): pass
        class GrandChild(Child): pass

        for ModelClass in (Child, GrandChild):
            self.assertEqual(ModelClass._meta.constraints, ['c1', 'c2'])
            self.assertTrue(ModelClass._meta.database is db)
            self.assertEqual(ModelClass._meta.indexes, [(('username',), True)])
            self.assertEqual(ModelClass._meta.options, {'key': 'value'})
            self.assertTrue(ModelClass._meta.only_save_dirty)
            self.assertEqual(ModelClass._meta.schema, 'magic')
            self.assertTrue(ModelClass._meta.table_alias is None)

        class Overrides(Base):
            class Meta:
                constraints = None
                indexes = None
                only_save_dirty = False
                options = {'foo': 'bar'}
                schema = None

        self.assertTrue(Overrides._meta.constraints is None)
        self.assertEqual(Overrides._meta.indexes, [])
        self.assertFalse(Overrides._meta.only_save_dirty)
        self.assertEqual(Overrides._meta.options, {'foo': 'bar'})
        self.assertTrue(Overrides._meta.schema is None)


class TestForeignKeyFieldDescriptors(BaseTestCase):
    def test_foreign_key_field_descriptors(self):
        class User(Model): pass
        class T0(Model):
            user = ForeignKeyField(User)
        class T1(Model):
            user = ForeignKeyField(User, column_name='uid')
        class T2(Model):
            user = ForeignKeyField(User, object_id_name='uid')
        class T3(Model):
            user = ForeignKeyField(User, column_name='x', object_id_name='uid')
        class T4(Model):
            foo = ForeignKeyField(User, column_name='user')
        class T5(Model):
            foo = ForeignKeyField(User, object_id_name='uid')

        self.assertEqual(T0.user.object_id_name, 'user_id')
        self.assertEqual(T1.user.object_id_name, 'uid')
        self.assertEqual(T2.user.object_id_name, 'uid')
        self.assertEqual(T3.user.object_id_name, 'uid')
        self.assertEqual(T4.foo.object_id_name, 'user')
        self.assertEqual(T5.foo.object_id_name, 'uid')

        user = User(id=1337)
        self.assertEqual(T0(user=user).user_id, 1337)
        self.assertEqual(T1(user=user).uid, 1337)
        self.assertEqual(T2(user=user).uid, 1337)
        self.assertEqual(T3(user=user).uid, 1337)
        self.assertEqual(T4(foo=user).user, 1337)
        self.assertEqual(T5(foo=user).uid, 1337)

        def conflicts_with_field():
            class TE(Model):
                user = ForeignKeyField(User, object_id_name='user')

        self.assertRaises(ValueError, conflicts_with_field)

    def test_column_name(self):
        class User(Model): pass
        class T1(Model):
            user = ForeignKeyField(User, column_name='user')

        self.assertEqual(T1.user.column_name, 'user')
        self.assertEqual(T1.user.object_id_name, 'user_id')


class TestModelAliasFieldProperties(ModelTestCase):
    database = get_in_memory_db()

    def test_field_properties(self):
        class Person(TestModel):
            name = TextField()
            dob = DateField()
            class Meta:
                database = self.database

        class Job(TestModel):
            worker = ForeignKeyField(Person, backref='jobs')
            client = ForeignKeyField(Person, backref='jobs_hired')
            class Meta:
                database = self.database

        Worker = Person.alias()
        Client = Person.alias()

        expected_sql = (
            'SELECT "t1"."id", "t1"."worker_id", "t1"."client_id" '
            'FROM "job" AS "t1" '
            'INNER JOIN "person" AS "t2" ON ("t1"."client_id" = "t2"."id") '
            'INNER JOIN "person" AS "t3" ON ("t1"."worker_id" = "t3"."id") '
            'WHERE (date_part(?, "t2"."dob") = ?)')
        expected_params = ['year', 1983]

        query = (Job
                 .select()
                 .join(Client, on=(Job.client == Client.id))
                 .switch(Job)
                 .join(Worker, on=(Job.worker == Worker.id))
                 .where(Client.dob.year == 1983))
        self.assertSQL(query, expected_sql, expected_params)

        query = (Job
                 .select()
                 .join(Client, on=(Job.client == Client.id))
                 .switch(Job)
                 .join(Person, on=(Job.worker == Person.id))
                 .where(Client.dob.year == 1983))
        self.assertSQL(query, expected_sql, expected_params)

        query = (Job
                 .select()
                 .join(Person, on=(Job.client == Person.id))
                 .switch(Job)
                 .join(Worker, on=(Job.worker == Worker.id))
                 .where(Person.dob.year == 1983))
        self.assertSQL(query, expected_sql, expected_params)


class Emp(TestModel):
    first = CharField()
    last = CharField()
    empno = CharField(unique=True)

    class Meta:
        indexes = (
            (('first', 'last'), True),
        )


class OnConflictTestCase(ModelTestCase):
    requires = [Emp]
    test_data = (
        ('huey', 'cat', '123'),
        ('zaizee', 'cat', '124'),
        ('mickey', 'dog', '125'),
    )

    def setUp(self):
        super(OnConflictTestCase, self).setUp()
        for first, last, empno in self.test_data:
            Emp.create(first=first, last=last, empno=empno)

    def assertData(self, expected):
        query = (Emp
                 .select(Emp.first, Emp.last, Emp.empno)
                 .order_by(Emp.id)
                 .tuples())
        self.assertEqual(list(query), expected)

    def test_ignore(self):
        query = (Emp
                 .insert(first='foo', last='bar', empno='123')
                 .on_conflict('ignore')
                 .execute())
        self.assertData(list(self.test_data))


class TestUpsertSqlite(OnConflictTestCase):
    database = get_in_memory_db()

    def test_replace(self):
        query = (Emp
                 .insert(first='mickey', last='dog', empno='1337')
                 .on_conflict('replace')
                 .execute())
        self.assertData([
            ('huey', 'cat', '123'),
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337')])

        query = (Emp
                 .insert(first='nuggie', last='dog', empno='123')
                 .on_conflict('replace')
                 .execute())
        self.assertData([
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337'),
            ('nuggie', 'dog', '123')])


@skip_case_unless(IS_MYSQL)
class TestUpsertMySQL(OnConflictTestCase):
    def test_replace(self):
        query = (Emp
                 .insert(first='mickey', last='dog', empno='1337')
                 .on_conflict('replace')
                 .execute())
        self.assertData([
            ('huey', 'cat', '123'),
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337')])

        query = (Emp
                 .insert(first='nuggie', last='dog', empno='123')
                 .on_conflict('replace')
                 .execute())
        self.assertData([
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337'),
            ('nuggie', 'dog', '123')])


class OCTest(TestModel):
    a = CharField(unique=True)
    b = IntegerField(default=0)


@skip_case_unless(IS_POSTGRESQL)
class TestUpsertPostgresql(OnConflictTestCase):
    def test_update(self):
        res = (Emp
               .insert(first='foo', last='bar', empno='125')
               .on_conflict(
                   conflict_target=(Emp.empno,),
                   preserve=(Emp.first, Emp.last),
                   update={Emp.empno: '125.1'})
               .execute())
        self.assertData([
            ('huey', 'cat', '123'),
            ('zaizee', 'cat', '124'),
            ('foo', 'bar', '125.1')])

        res = (Emp
               .insert(first='foo', last='bar', empno='126')
               .on_conflict(
                   conflict_target=(Emp.first, Emp.last),
                   preserve=(Emp.first,),
                   update={Emp.last: 'baze'})
               .execute())
        self.assertData([
            ('huey', 'cat', '123'),
            ('zaizee', 'cat', '124'),
            ('foo', 'baze', '125.1')])

    @requires_models(OCTest)
    def test_update_atomic(self):
        query = OCTest.insert(a='foo', b=1).on_conflict(
            conflict_target=(OCTest.a,),
            update={OCTest.b: OCTest.b + 2})
        self.assertSQL(query, (
            'INSERT INTO "octest" ("a", "b") VALUES (?, ?) '
            'ON CONFLICT ("a") DO UPDATE SET "b" = ("octest"."b" + ?) '
            'RETURNING "id"'), ['foo', 1, 2])

        rowid1 = query.execute()
        rowid2 = query.clone().execute()
        self.assertEqual(rowid1, rowid2)

        obj = OCTest.get()
        self.assertEqual(obj.a, 'foo')
        self.assertEqual(obj.b, 3)

    @requires_models(OCTest)
    def test_update_where_clause(self):
        query = OCTest.insert(a='foo', b=1).on_conflict(
            conflict_target=(OCTest.a,),
            update={OCTest.b: OCTest.b + 2},
            where=(OCTest.b < 3))
        self.assertSQL(query, (
            'INSERT INTO "octest" ("a", "b") VALUES (?, ?) '
            'ON CONFLICT ("a") DO UPDATE SET "b" = ("octest"."b" + ?) '
            'WHERE ("octest"."b" < ?) '
            'RETURNING "id"'), ['foo', 1, 2, 3])

        rowid1 = query.execute()
        rowid2 = query.clone().execute()
        self.assertEqual(rowid1, rowid2)

        obj = OCTest.get()
        self.assertEqual(obj.a, 'foo')
        self.assertEqual(obj.b, 3)

        rowid3 = query.clone().execute()
        self.assertEqual(rowid1, rowid2)

        # Because we didn't satisfy the WHERE clause, the value in "b" is
        # not incremented again.
        obj = OCTest.get()
        self.assertEqual(obj.a, 'foo')
        self.assertEqual(obj.b, 3)


class TestJoinSubquery(ModelTestCase):
    requires = [Person, Relationship]

    def test_join_subquery(self):
        # Set up some relationships such that there exists a relationship from
        # the left-hand to the right-hand name.
        data = (
            ('charlie', None),
            ('huey', 'charlie'),
            ('mickey', 'charlie'),
            ('zaizee', 'charlie'),
            ('zaizee', 'huey'))
        people = {}
        def get_person(name):
            if name not in people:
                people[name] = Person.create(first=name, last=name,
                                             dob=datetime.date(2017, 1, 1))
            return people[name]

        for person, related_to in data:
            p1 = get_person(person)
            if related_to is not None:
                p2 = get_person(related_to)
                Relationship.create(from_person=p1, to_person=p2)

        # Create the subquery.
        Friend = Person.alias('friend')
        subq = (Relationship
                .select(Friend.first.alias('friend_name'),
                        Relationship.from_person)
                .join(Friend, on=(Relationship.to_person == Friend.id))
                .alias('subq'))

        # Outer query does a LEFT OUTER JOIN. We join on the subquery because
        # it uses an INNER JOIN, saving us doing two LEFT OUTER joins in the
        # single query.
        query = (Person
                 .select(Person.first, subq.c.friend_name)
                 .join(subq, JOIN.LEFT_OUTER,
                       on=(Person.id == subq.c.from_person_id))
                 .order_by(Person.first, subq.c.friend_name))
        self.assertSQL(query, (
            'SELECT "t1"."first", "subq"."friend_name" '
            'FROM "person" AS "t1" '
            'LEFT OUTER JOIN ('
            'SELECT "friend"."first" AS "friend_name", "t2"."from_person_id" '
            'FROM "relationship" AS "t2" '
            'INNER JOIN "person" AS "friend" '
            'ON ("t2"."to_person_id" = "friend"."id")) AS "subq" '
            'ON ("t1"."id" = "subq"."from_person_id") '
            'ORDER BY "t1"."first", "subq"."friend_name"'), [])

        db_data = [row for row in query.tuples()]
        self.assertEqual(db_data, list(data))


class User2(TestModel):
    username = TextField()


class Category2(TestModel):
    name = TextField()
    parent = ForeignKeyField('self', backref='children', null=True)
    user = ForeignKeyField(User2)


class TestGithub1354(ModelTestCase):
    @requires_models(Category2, User2)
    def test_get_or_create_self_referential_fk2(self):
        huey = User2.create(username='huey')
        parent = Category2.create(name='parent', user=huey)
        child, created = Category2.get_or_create(parent=parent, name='child',
                                                 user=huey)
        child_db = Category2.get(Category2.parent == parent)
        self.assertEqual(child_db.user.username, 'huey')
        self.assertEqual(child_db.parent.name, 'parent')
        self.assertEqual(child_db.name, 'child')


class TestCountUnionRegression(ModelTestCase):
    @requires_models(User)
    @skip_if(IS_MYSQL)
    def test_count_union(self):
        with self.database.atomic():
            for i in range(5):
                User.create(username='user-%d' % i)

        lhs = User.select()
        rhs = User.select()
        query = (lhs & rhs)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'INTERSECT '
            'SELECT "t2"."id", "t2"."username" FROM "users" AS "t2"'), [])

        self.assertEqual(query.count(), 5)

        query = query.limit(3)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'INTERSECT '
            'SELECT "t2"."id", "t2"."username" FROM "users" AS "t2" '
            'LIMIT 3'), [])
        self.assertEqual(query.count(), 3)


class TestSumCase(ModelTestCase):
    @requires_models(User)
    def test_sum_case(self):
        for username in ('charlie', 'huey', 'zaizee'):
            User.create(username=username)

        case = Case(None, [(User.username.endswith('e'), 1)], 0)
        e_sum = fn.SUM(case)
        query = (User
                 .select(User.username, e_sum.alias('e_sum'))
                 .group_by(User.username)
                 .order_by(User.username))
        self.assertSQL(query, (
            'SELECT "t1"."username", '
            'SUM(CASE WHEN ("t1"."username" ILIKE ?) THEN ? ELSE ? END) '
            'AS "e_sum" '
            'FROM "users" AS "t1" '
            'GROUP BY "t1"."username" '
            'ORDER BY "t1"."username"'), ['%e', 1, 0])

        data = [(user.username, user.e_sum) for user in query]
        self.assertEqual(data, [
            ('charlie', 1),
            ('huey', 0),
            ('zaizee', 1)])


class TUser(TestModel):
    username = TextField()


class Transaction(TestModel):
    user = ForeignKeyField(TUser, backref='transactions')
    amount = FloatField(default=0.)


class TestMaxAlias(ModelTestCase):
    requires = [Transaction, TUser]

    def test_max_alias(self):
        with self.database.atomic():
            charlie = TUser.create(username='charlie')
            huey = TUser.create(username='huey')

            data = (
                (charlie, 10.),
                (charlie, 20.),
                (charlie, 30.),
                (huey, 1.5),
                (huey, 2.5))
            for user, amount in data:
                Transaction.create(user=user, amount=amount)

        amount = fn.MAX(Transaction.amount).alias('amount')
        query = (Transaction
                 .select(amount, TUser.username)
                 .join(TUser)
                 .group_by(TUser.username)
                 .order_by(TUser.username))
        with self.assertQueryCount(1):
            data = [(txn.amount, txn.user.username) for txn in query]

        self.assertEqual(data, [
            (30., 'charlie'),
            (2.5, 'huey')])


class CNote(TestModel):
    content = TextField()
    timestamp = TimestampField()

class CFile(TestModel):
    filename = CharField(primary_key=True)
    data = TextField()
    timestamp = TimestampField()


class TestCompoundSelectModels(ModelTestCase):
    requires = [CFile, CNote]

    def setUp(self):
        super(TestCompoundSelectModels, self).setUp()
        def generate_ts():
            i = [0]
            def _inner():
                i[0] += 1
                return datetime.datetime(2018, 1, i[0])
            return _inner
        make_ts = generate_ts()
        self.ts = lambda i: datetime.datetime(2018, 1, i)

        with self.database.atomic():
            for content in ('note-a', 'note-b', 'note-c'):
                CNote.create(content=content, timestamp=make_ts())

            file_data = (
                ('peewee.txt', 'peewee orm'),
                ('walrus.txt', 'walrus redis toolkit'),
                ('huey.txt', 'huey task queue'))
            for filename, data in file_data:
                CFile.create(filename=filename, data=data, timestamp=make_ts())

    def test_mix_models_with_model_row_type(self):
        cast = 'CHAR' if IS_MYSQL else 'TEXT'
        lhs = CNote.select(CNote.id.cast(cast).alias('id_text'),
                           CNote.content, CNote.timestamp)
        rhs = CFile.select(CFile.filename, CFile.data, CFile.timestamp)
        query = (lhs | rhs).order_by(SQL('timestamp')).limit(4)

        data = [(n.id_text, n.content, n.timestamp) for n in query]
        self.assertEqual(data, [
            ('1', 'note-a', self.ts(1)),
            ('2', 'note-b', self.ts(2)),
            ('3', 'note-c', self.ts(3)),
            ('peewee.txt', 'peewee orm', self.ts(4))])

    def test_mixed_models_tuple_row_type(self):
        cast = 'CHAR' if IS_MYSQL else 'TEXT'
        lhs = CNote.select(CNote.id.cast(cast).alias('id'),
                           CNote.content, CNote.timestamp)
        rhs = CFile.select(CFile.filename, CFile.data, CFile.timestamp)
        query = (lhs | rhs).order_by(SQL('timestamp')).limit(5)

        self.assertEqual(list(query.tuples()), [
            ('1', 'note-a', self.ts(1)),
            ('2', 'note-b', self.ts(2)),
            ('3', 'note-c', self.ts(3)),
            ('peewee.txt', 'peewee orm', self.ts(4)),
            ('walrus.txt', 'walrus redis toolkit', self.ts(5))])

    def test_mixed_models_dict_row_type(self):
        notes = CNote.select(CNote.content, CNote.timestamp)
        files = CFile.select(CFile.filename, CFile.timestamp)

        query = (notes | files).order_by(SQL('timestamp').desc()).limit(4)
        self.assertEqual(list(query.dicts()), [
            {'content': 'huey.txt', 'timestamp': self.ts(6)},
            {'content': 'walrus.txt', 'timestamp': self.ts(5)},
            {'content': 'peewee.txt', 'timestamp': self.ts(4)},
            {'content': 'note-c', 'timestamp': self.ts(3)}])


class SequenceModel(TestModel):
    seq_id = IntegerField(sequence='seq_id_sequence')
    key = TextField()


@skip_case_unless(IS_POSTGRESQL)
class TestSequence(ModelTestCase):
    requires = [SequenceModel]

    def test_create_table(self):
        query = SequenceModel._schema._create_table()
        self.assertSQL(query, (
            'CREATE TABLE IF NOT EXISTS "sequencemodel" ('
            '"id" SERIAL NOT NULL PRIMARY KEY, '
            '"seq_id" INTEGER NOT NULL DEFAULT NEXTVAL(\'seq_id_sequence\'), '
            '"key" TEXT NOT NULL)'), [])

    def test_sequence(self):
        for key in ('k1', 'k2', 'k3'):
            SequenceModel.create(key=key)

        s1, s2, s3 = SequenceModel.select().order_by(SequenceModel.key)

        self.assertEqual(s1.seq_id, 1)
        self.assertEqual(s2.seq_id, 2)
        self.assertEqual(s3.seq_id, 3)
