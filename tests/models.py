import datetime
import sys
import time
import unittest

from peewee import *
from peewee import Entity
from peewee import NodeList
from peewee import sort_models

from .base import db
from .base import get_in_memory_db
from .base import mock
from .base import new_connection
from .base import requires_models
from .base import requires_mysql
from .base import requires_postgresql
from .base import requires_sqlite
from .base import skip_if
from .base import skip_unless
from .base import BaseTestCase
from .base import IS_MYSQL
from .base import IS_MYSQL_ADVANCED_FEATURES
from .base import IS_POSTGRESQL
from .base import IS_SQLITE
from .base import IS_SQLITE_OLD
from .base import IS_SQLITE_15  # Row-values.
from .base import IS_SQLITE_24  # Upsert.
from .base import IS_SQLITE_25  # Window functions.
from .base import IS_SQLITE_30  # FILTER clause functions.
from .base import IS_SQLITE_9
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


class CPK(TestModel):
    key = CharField()
    value = IntegerField()
    extra = IntegerField()
    class Meta:
        primary_key = CompositeKey('key', 'value')


class City(TestModel):
    name = CharField()

class Venue(TestModel):
    name = CharField()
    city = ForeignKeyField(City, backref='venues')
    city_n = ForeignKeyField(City, backref='venues_n', null=True)

class Event(TestModel):
    name = CharField()
    venue = ForeignKeyField(Venue, backref='events', null=True)


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

        if not IS_SQLITE:
            with self.database.atomic() as txn:
                self.assertRaises(IntegrityError, PostNote.create, note='pxn')
                txn.rollback()

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

    @requires_models(User)
    def test_bulk_create(self):
        users = [User(username='u%s' % i) for i in range(5)]
        self.assertEqual(User.select().count(), 0)

        with self.assertQueryCount(1):
            User.bulk_create(users)

        self.assertEqual(User.select().count(), 5)
        self.assertEqual([u.username for u in User.select().order_by(User.id)],
                         ['u0', 'u1', 'u2', 'u3', 'u4'])

        if IS_POSTGRESQL:
            self.assertEqual([u.id for u in User.select().order_by(User.id)],
                             [user.id for user in users])

    @requires_models(User)
    def test_bulk_create_empty(self):
        self.assertEqual(User.select().count(), 0)
        User.bulk_create([])

    @requires_models(User)
    def test_bulk_create_batching(self):
        users = [User(username=str(i)) for i in range(10)]
        with self.assertQueryCount(4):
            User.bulk_create(users, 3)

        self.assertEqual(User.select().count(), 10)
        self.assertEqual([u.username for u in User.select().order_by(User.id)],
                         list('0123456789'))

        if IS_POSTGRESQL:
            self.assertEqual([u.id for u in User.select().order_by(User.id)],
                             [user.id for user in users])

    @requires_models(Person)
    def test_bulk_create_error(self):
        people = [Person(first='a', last='b'),
                  Person(first='b', last='c'),
                  Person(first='a', last='b')]
        with self.assertRaises(IntegrityError):
            with self.database.atomic():
                Person.bulk_create(people)
        self.assertEqual(Person.select().count(), 0)

    @requires_models(CPK)
    def test_bulk_create_composite_key(self):
        self.assertEqual(CPK.select().count(), 0)
        items = [CPK(key='k1', value=1, extra=1),
                 CPK(key='k2', value=2, extra=2)]
        CPK.bulk_create(items)
        self.assertEqual([(c.key, c.value, c.extra) for c in items],
                         [('k1', 1, 1), ('k2', 2, 2)])

        query = CPK.select().order_by(CPK.key).tuples()
        self.assertEqual(list(query), [('k1', 1, 1), ('k2', 2, 2)])

    @requires_models(Person)
    def test_bulk_update(self):
        data = [('f%s' % i, 'l%s' % i, datetime.date(1980, i, i))
                for i in range(1, 5)]
        Person.insert_many(data).execute()

        p1, p2, p3, p4 = list(Person.select().order_by(Person.id))
        p1.first = 'f1-x'
        p1.last = 'l1-x'
        p2.first = 'f2-y'
        p3.last = 'l3-z'

        with self.assertQueryCount(1):
            n = Person.bulk_update([p1, p2, p3, p4], ['first', 'last'])
            self.assertEqual(n, 3 if IS_MYSQL else 4)

        query = Person.select().order_by(Person.id)
        self.assertEqual([(p.first, p.last) for p in query], [
            ('f1-x', 'l1-x'),
            ('f2-y', 'l2'),
            ('f3', 'l3-z'),
            ('f4', 'l4')])

        # Modify multiple fields, but only update "first".
        p1.first = 'f1-x2'
        p1.last = 'l1-x2'
        p2.first = 'f2-y2'
        p3.last = 'f3-z2'
        with self.assertQueryCount(2):  # Two batches, so two queries.
            n = Person.bulk_update([p1, p2, p3, p4], [Person.first], 2)
            self.assertEqual(n, 2 if IS_MYSQL else 4)

        query = Person.select().order_by(Person.id)
        self.assertEqual([(p.first, p.last) for p in query], [
            ('f1-x2', 'l1-x'),
            ('f2-y2', 'l2'),
            ('f3', 'l3-z'),
            ('f4', 'l4')])

    @requires_models(User, Tweet)
    def test_bulk_update_foreign_key(self):
        for username in ('charlie', 'huey', 'zaizee'):
            user = User.create(username=username)
            for i in range(2):
                Tweet.create(user=user, content='%s-%s' % (username, i))

        c, h, z = list(User.select().order_by(User.id))
        c0, c1, h0, h1, z0, z1 = list(Tweet.select().order_by(Tweet.id))
        c0.content = 'charlie-0x'
        c1.user = h
        h0.user = z
        h1.content = 'huey-1x'
        z0.user = c
        z0.content = 'zaizee-0x'

        with self.assertQueryCount(1):
            Tweet.bulk_update([c0, c1, h0, h1, z0, z1], ['user', 'content'])

        query = (Tweet
                 .select(Tweet.content, User.username)
                 .join(User)
                 .order_by(Tweet.id)
                 .objects())
        self.assertEqual([(t.username, t.content) for t in query], [
            ('charlie', 'charlie-0x'),
            ('huey', 'charlie-1'),
            ('zaizee', 'huey-0'),
            ('huey', 'huey-1x'),
            ('charlie', 'zaizee-0x'),
            ('zaizee', 'zaizee-1')])

    @requires_models(Person)
    def test_bulk_update_integrityerror(self):
        people = [Person(first='f%s' % i, last='l%s' % i, dob='1980-01-01')
                  for i in range(10)]
        Person.bulk_create(people)

        # Get list of people w/the IDs populated. They will not be set if the
        # underlying DB is Sqlite or MySQL.
        people = list(Person.select().order_by(Person.id))

        # First we'll just modify all the first and last names.
        for person in people:
            person.first += '-x'
            person.last += '-x'

        # Now we'll introduce an issue that will cause an integrity error.
        p3, p7 = people[3], people[7]
        p3.first = p7.first = 'fx'
        p3.last = p7.last = 'lx'
        with self.assertRaises(IntegrityError):
            with self.assertQueryCount(1):
                with self.database.atomic():
                    Person.bulk_update(people, fields=['first', 'last'])

        with self.assertRaises(IntegrityError):
            # 10 objects, batch size=4, so 0-3, 4-7, 8&9. But we never get to 8
            # and 9 because of the integrity error processing the 2nd batch.
            with self.assertQueryCount(2):
                with self.database.atomic():
                    Person.bulk_update(people, ['first', 'last'], 4)

        # Ensure no changes were made.
        vals = [(p.first, p.last) for p in Person.select().order_by(Person.id)]
        self.assertEqual(vals, [('f%s' % i, 'l%s' % i) for i in range(10)])

    @requires_models(User, Tweet)
    def test_bulk_update_apply_dbvalue(self):
        u = User.create(username='u')
        t1, t2, t3 = [Tweet.create(user=u, content=str(i)) for i in (1, 2, 3)]

        # If we don't end up applying the field's db_value() to these timestamp
        # values, then we will end up with bad data or an error when attempting
        # to do the update.
        t1.timestamp = datetime.datetime(2019, 1, 2, 3, 4, 5)
        t2.timestamp = datetime.date(2019, 1, 3)
        t3.timestamp = 1337133700  # 2012-05-15T21:1:40.
        t3_dt = datetime.datetime.fromtimestamp(1337133700)
        Tweet.bulk_update([t1, t2, t3], fields=['timestamp'])

        # Ensure that the values were handled appropriately.
        t1, t2, t3 = list(Tweet.select().order_by(Tweet.id))
        self.assertEqual(t1.timestamp, datetime.datetime(2019, 1, 2, 3, 4, 5))
        self.assertEqual(t2.timestamp, datetime.datetime(2019, 1, 3, 0, 0, 0))
        self.assertEqual(t3.timestamp, t3_dt)

    @skip_if(IS_SQLITE_OLD or IS_MYSQL)
    @requires_models(CPK)
    def test_bulk_update_cte(self):
        CPK.insert_many([('k1', 1, 1), ('k2', 2, 2), ('k3', 3, 3)]).execute()

        # We can also do a bulk-update using ValuesList when the primary-key of
        # the model is a composite-pk.
        new_values = [('k1', 1, 10), ('k3', 3, 30)]
        cte = ValuesList(new_values).cte('new_values', columns=('k', 'v', 'x'))

        # We have to use a subquery to update the individual column, as SQLite
        # does not support UPDATE/FROM syntax.
        subq = (cte
                .select(cte.c.x)
                .where(CPK._meta.primary_key == (cte.c.k, cte.c.v)))

        # Perform the update, assigning extra the new value from the values
        # list, and restricting the overall update using the composite pk.
        res = (CPK
               .update(extra=subq)
               .where(CPK._meta.primary_key.in_(cte.select(cte.c.k, cte.c.v)))
               .with_cte(cte)
               .execute())

        self.assertEqual(list(sorted(CPK.select().tuples())), [
            ('k1', 1, 10), ('k2', 2, 2), ('k3', 3, 30)])

    @requires_models(User)
    def test_insert_rowcount(self):
        User.create(username='u0')  # Ensure that last insert ID != rowcount.

        iq = User.insert_many([(u,) for u in ('u1', 'u2', 'u3')])
        if IS_POSTGRESQL:
            iq = iq.returning()
        self.assertEqual(iq.execute(), 3)

        # Now explicitly specify empty returning() for all DBs.
        iq = User.insert_many([(u,) for u in ('u4', 'u5')]).returning()
        self.assertEqual(iq.execute(), 2)

        query = (User
                 .select(User.username.concat('-x'))
                 .where(User.username.in_(['u1', 'u2'])))
        iq = User.insert_from(query, ['username'])
        if IS_POSTGRESQL:
            iq = iq.returning()
        self.assertEqual(iq.execute(), 2)

        query = (User
                 .select(User.username.concat('-y'))
                 .where(User.username.in_(['u3', 'u4'])))
        iq = User.insert_from(query, ['username']).returning()
        self.assertEqual(iq.execute(), 2)

    @skip_if(IS_POSTGRESQL, 'requires sqlite or mysql')
    @requires_models(Emp)
    def test_replace_rowcount(self):
        Emp.create(first='beanie', last='cat', empno='998')

        data = [
            ('beanie', 'cat', '999'),
            ('mickey', 'dog', '123')]
        fields = (Emp.first, Emp.last, Emp.empno)

        # MySQL returns 3, Sqlite 2. However, older stdlib sqlite3 does not
        # work properly, so we don't assert a result count here.
        Emp.replace_many(data, fields=fields).execute()

        query = Emp.select(Emp.first, Emp.last, Emp.empno).order_by(Emp.last)
        self.assertEqual(list(query.tuples()), [
            ('beanie', 'cat', '999'),
            ('mickey', 'dog', '123')])

    @requires_models(User, Tweet)
    def test_get_shortcut(self):
        huey = self.add_user('huey')
        self.add_tweets(huey, 'meow', 'purr', 'wheeze')
        mickey = self.add_user('mickey')
        self.add_tweets(mickey, 'woof', 'yip')

        # Lookup using just the ID.
        huey_db = User.get(huey.id)
        self.assertEqual(huey.id, huey_db.id)

        # Lookup using an expression.
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
        user = User(username='charlie')
        tweet = Tweet(user=user, content='foo')

        self.assertTrue(user.save())
        self.assertTrue(user.id is not None)
        self.assertTrue(tweet.user_id is None)
        self.assertTrue(tweet.save())
        self.assertEqual(tweet.user_id, user.id)

        tweet_db = Tweet.get(Tweet.content == 'foo')
        self.assertEqual(tweet_db.user.username, 'charlie')

    @requires_models(User, Tweet)
    def test_model_select(self):
        huey = self.add_user('huey')
        mickey = self.add_user('mickey')
        zaizee = self.add_user('zaizee')

        self.add_tweets(huey, 'meow', 'hiss', 'purr')
        self.add_tweets(mickey, 'woof', 'whine')

        with self.assertQueryCount(1):
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

        with self.assertQueryCount(1):
            UA = User.alias()
            query = (Favorite
                     .select(Favorite, Tweet, User, UA)
                     .join(Tweet)
                     .join(User)
                     .switch(Favorite)
                     .join(UA, on=Favorite.user)
                     .order_by(Favorite.id))

            accum = [(f.tweet.user.username, f.tweet.content, f.user.username)
                     for f in query]

        self.assertEqual(accum, [
            ('mickey', 'woof', 'huey'),
            ('huey', 'meow', 'mickey'),
            ('huey', 'purr', 'mickey')])

        with self.assertQueryCount(5):
            # Test intermediate models not selected.
            query = (Favorite
                     .select()
                     .join(Tweet)
                     .switch(Favorite)
                     .join(User)
                     .where(User.username == 'mickey')
                     .order_by(Favorite.id))

            accum = [(f.user.username, f.tweet.content) for f in query]

        self.assertEqual(accum, [('mickey', 'meow'), ('mickey', 'purr')])

    @requires_models(A, B, C)
    def test_join_issue_1482(self):
        a1 = A.create(a='a1')
        b1 = B.create(a=a1, b='b1')
        c1 = C.create(b=b1, c='c1')

        with self.assertQueryCount(3):
            query = C.select().join(B).join(A).where(A.a == 'a1')
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

        with self.assertQueryCount(1):
            query = C.select(C, A.a).join(B).join(A).order_by(C.c)
            accum = [(c.c, c.b.a.a) for c in query]

        self.assertEqual(accum, [
            ('c111', 'a1'),
            ('c112', 'a1'),
            ('c211', 'a2')])

        with self.assertQueryCount(1):
            query = C.select(C, B, A).join(B).join(A).order_by(C.c)
            accum = [(c.c, c.b.b, c.b.a.a) for c in query]

        self.assertEqual(accum, [
            ('c111', 'b11', 'a1'),
            ('c112', 'b11', 'a1'),
            ('c211', 'b21', 'a2')])

    @requires_models(City, Venue, Event)
    def test_join_empty_relations(self):
        with self.database.atomic():
            city = City.create(name='Topeka')
            venue1 = Venue.create(name='House', city=city, city_n=city)
            venue2 = Venue.create(name='Nowhere', city=city, city_n=None)

            event1 = Event.create(name='House Party', venue=venue1)
            event2 = Event.create(name='Holiday')
            event3 = Event.create(name='Nowhere Party', venue=venue2)

        with self.assertQueryCount(1):
            query = (Event
                     .select(Event, Venue, City)
                     .join(Venue, JOIN.LEFT_OUTER)
                     .join(City, JOIN.LEFT_OUTER, on=Venue.city)
                     .order_by(Event.id))

            # Here we have two left-outer joins, and the second Event
            # ("Holiday"), does not have an associated Venue (hence, no City).
            # Peewee would attach an empty Venue() model to the event, however.
            # It did this since we are selecting from Venue/City and Venue is
            # an intermediary model. It is more correct for Event.venue to be
            # None in this case. This is now patched / fixed.
            r = [(e.name, e.venue and e.venue.city.name or None)
                 for e in query]
            self.assertEqual(r, [
                ('House Party', 'Topeka'),
                ('Holiday', None),
                ('Nowhere Party', 'Topeka')])

        with self.assertQueryCount(1):
            query = (Event
                     .select(Event, Venue, City)
                     .join(Venue, JOIN.INNER)
                     .join(City, JOIN.LEFT_OUTER, on=Venue.city_n)
                     .order_by(Event.id))

            # Here we have an inner join and a left-outer join. The furthest
            # object (City) will be NULL for the "Nowhere Party". Make sure
            # that the object is left as None and not populated with an empty
            # City instance.
            accum = []
            for event in query:
                city_name = event.venue.city_n and event.venue.city_n.name
                accum.append((event.name, event.venue.name, city_name))

            self.assertEqual(accum, [
                ('House Party', 'House', 'Topeka'),
                ('Nowhere Party', 'Nowhere', None)])

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
        with self.assertQueryCount(1):
            query = (Relationship
                     .select(Relationship, Person, PA)
                     .join(Person, on=Relationship.from_person)
                     .switch(Relationship)
                     .join(PA, on=Relationship.to_person)
                     .order_by(Relationship.id))
            results = [(r.from_person.first, r.to_person.first) for r in query]

        self.assertEqual(results, [
            ('huey', 'zaizee'),
            ('zaizee', 'huey'),
            ('mickey', 'huey')])

    @requires_models(User)
    def test_peek(self):
        for username in ('huey', 'mickey', 'zaizee'):
            self.add_user(username)

        with self.assertQueryCount(1):
            query = User.select(User.username).order_by(User.username).dicts()
            self.assertEqual(query.peek(n=1), {'username': 'huey'})
            self.assertEqual(query.peek(n=2), [{'username': 'huey'},
                                               {'username': 'mickey'}])

    @requires_models(User, Tweet, Favorite)
    def test_multi_join(self):
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

        TweetUser = User.alias('u2')

        with self.assertQueryCount(1):
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
        with self.assertQueryCount(1):
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

            data = [(user.username, user.tweet.content) for user in query]

        # Failing on travis-ci...old SQLite?
        if not IS_SQLITE_OLD:
            self.assertEqual(data, [
                ('huey', 'hiss'),
                ('mickey', 'grr')])

        with self.assertQueryCount(1):
            query = (Tweet
                     .select(Tweet, User)
                     .join(max_q, on=predicate)
                     .switch(Tweet)
                     .join(User))
            data = [(note.user.username, note.content) for note in query]

        self.assertEqual(data, [
            ('huey', 'hiss'),
            ('mickey', 'grr')])

    @requires_models(User, Tweet)
    def test_join_subquery_2(self):
        self._create_user_tweets()

        with self.assertQueryCount(1):
            users = (User
                     .select(User.id, User.username)
                     .where(User.username.in_(['huey', 'zaizee'])))
            query = (Tweet
                     .select(Tweet.content.alias('content'),
                             users.c.username.alias('username'))
                     .join(users, on=(Tweet.user == users.c.id))
                     .order_by(Tweet.id))

            self.assertSQL(query, (
                'SELECT "t1"."content" AS "content", '
                '"t2"."username" AS "username"'
                ' FROM "tweet" AS "t1" '
                'INNER JOIN (SELECT "t3"."id", "t3"."username" '
                'FROM "users" AS "t3" '
                'WHERE ("t3"."username" IN (?, ?))) AS "t2" '
                'ON ("t1"."user_id" = "t2"."id") '
                'ORDER BY "t1"."id"'), ['huey', 'zaizee'])

            results = [(t.content, t.user.username) for t in query]
            self.assertEqual(results, [
                ('meow', 'huey'),
                ('purr', 'huey'),
                ('hiss', 'huey')])

    @skip_if(IS_SQLITE_OLD or (IS_MYSQL and not IS_MYSQL_ADVANCED_FEATURES))
    @requires_models(User, Tweet)
    def test_join_subquery_cte(self):
        self._create_user_tweets()

        cte = (User
               .select(User.id, User.username)
               .where(User.username.in_(['huey', 'zaizee']))\
               .cte('cats'))

        with self.assertQueryCount(1):
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

            self.assertEqual([t.content for t in query],
                             ['meow', 'purr', 'hiss'])

    @skip_if(IS_MYSQL)  # MariaDB does not support LIMIT in subqueries!
    @requires_models(User)
    def test_subquery_emulate_window(self):
        # We have duplicated users. Select a maximum of 2 instances of the
        # username.
        name2count = {
            'beanie': 6,
            'huey': 5,
            'mickey': 3,
            'pipey': 1,
            'zaizee': 4}
        names = []
        for name, count in sorted(name2count.items()):
            names += [name] * count
        User.insert_many([(n,) for n in names], [User.username]).execute()

        # The results we are trying to obtain.
        expected = [
            ('beanie', 1), ('beanie', 2),
            ('huey', 7), ('huey', 8),
            ('mickey', 12), ('mickey', 13),
            ('pipey', 15),
            ('zaizee', 16), ('zaizee', 17)]

        with self.assertQueryCount(1):
            # Using a self-join.
            UA = User.alias()
            query = (User
                     .select(User.username, UA.id)
                     .join(UA, on=((UA.username == User.username) &
                                   (UA.id >= User.id)))
                     .group_by(User.username, UA.id)
                     .having(fn.COUNT(UA.id) < 3)
                     .order_by(User.username, UA.id))
            self.assertEqual(query.tuples()[:], expected)

        with self.assertQueryCount(1):
            # Using a correlated subquery.
            subq = (UA
                    .select(UA.id)
                    .where(User.username == UA.username)
                    .order_by(UA.id)
                    .limit(2))
            query = (User
                     .select(User.username, User.id)
                     .where(User.id.in_(subq.alias('subq')))
                     .order_by(User.username, User.id))
            self.assertEqual(query.tuples()[:], expected)

    @requires_models(User, Tweet)
    def test_subquery_alias_selection(self):
        data = (
            ('huey', ('meow', 'hiss', 'purr')),
            ('mickey', ('woof', 'bark')),
            ('zaizee', ()))
        with self.database.atomic():
            for username, tweets in data:
                user = User.create(username=username)
                for tweet in tweets:
                    Tweet.create(user=user, content=tweet)

        with self.assertQueryCount(1):
            subq = (Tweet
                    .select(fn.COUNT(Tweet.id))
                    .where(Tweet.user == User.id))
            query = (User
                     .select(User.username, subq.alias('tweet_count'))
                     .order_by(User.id))
            self.assertEqual([(u.username, u.tweet_count) for u in query], [
                ('huey', 3),
                ('mickey', 2),
                ('zaizee', 0)])

    @requires_postgresql
    @requires_models(User)
    def test_join_on_valueslist(self):
        for username in ('huey', 'mickey', 'zaizee'):
            User.create(username=username)

        vl = ValuesList([('huey',), ('zaizee',)], columns=['username'])
        with self.assertQueryCount(1):
            query = (User
                     .select(vl.c.username)
                     .join(vl, on=(User.username == vl.c.username))
                     .order_by(vl.c.username.desc()))
            self.assertEqual([u.username for u in query], ['zaizee', 'huey'])

    @skip_if(IS_SQLITE_OLD or IS_MYSQL)
    @requires_models(User)
    def test_multi_update(self):
        data = [(i, 'u%s' % i) for i in range(1, 4)]
        User.insert_many(data, fields=[User.id, User.username]).execute()

        data = [(i, 'u%sx' % i) for i in range(1, 3)]
        vl = ValuesList(data)
        cte = vl.select().cte('uv', columns=('id', 'username'))
        subq = cte.select(cte.c.username).where(cte.c.id == User.id)
        res = (User
               .update(username=subq)
               .where(User.id.in_(cte.select(cte.c.id)))
               .with_cte(cte)
               .execute())
        query = User.select().order_by(User.id)
        self.assertEqual([(u.id, u.username) for u in query], [
            (1, 'u1x'),
            (2, 'u2x'),
            (3, 'u3')])

    @requires_models(User, Tweet)
    def test_insert_query_value(self):
        huey = self.add_user('huey')
        query = User.select(User.id).where(User.username == 'huey')
        tid = Tweet.insert(content='meow', user=query).execute()
        tweet = Tweet[tid]
        self.assertEqual(tweet.user.id, huey.id)
        self.assertEqual(tweet.user.username, 'huey')

    @skip_if(IS_SQLITE and not IS_SQLITE_9, 'requires sqlite >= 3.9')
    @requires_models(Register)
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

    @requires_models(User, Tweet)
    def test_union_column_resolution(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        q1 = User.select().where(User.id == 1)
        q2 = User.select()
        union = q1 | q2
        self.assertSQL(union, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'WHERE ("t1"."id" = ?) '
            'UNION '
            'SELECT "t2"."id", "t2"."username" FROM "users" AS "t2"'), [1])

        results = [(user.id, user.username) for user in union]
        self.assertEqual(sorted(results), [
            (1, 'u1'),
            (2, 'u2')])

        t1_1 = Tweet.create(user=u1, content='u1-t1')
        t1_2 = Tweet.create(user=u1, content='u1-t2')
        t2_1 = Tweet.create(user=u2, content='u2-t1')

        with self.assertQueryCount(1):
            q1 = Tweet.select(Tweet, User).join(User).where(User.id == 1)
            q2 = Tweet.select(Tweet, User).join(User)
            union = q1 | q2

            self.assertSQL(union, (
                'SELECT "t1"."id", "t1"."user_id", "t1"."content", '
                '"t1"."timestamp", "t2"."id", "t2"."username" '
                'FROM "tweet" AS "t1" '
                'INNER JOIN "users" AS "t2" ON ("t1"."user_id" = "t2"."id") '
                'WHERE ("t2"."id" = ?) '
                'UNION '
                'SELECT "t3"."id", "t3"."user_id", "t3"."content", '
                '"t3"."timestamp", "t4"."id", "t4"."username" '
                'FROM "tweet" AS "t3" '
                'INNER JOIN "users" AS "t4" ON ("t3"."user_id" = "t4"."id")'),
                [1])

            results = [(t.id, t.content, t.user.username) for t in union]
            self.assertEqual(sorted(results), [
                (1, 'u1-t1', 'u1'),
                (2, 'u1-t2', 'u1'),
                (3, 'u2-t1', 'u2')])

        with self.assertQueryCount(1):
            union_flat = (q1 | q2).objects()
            results = [(t.id, t.content, t.username) for t in union_flat]
            self.assertEqual(sorted(results), [
                (1, 'u1-t1', 'u1'),
                (2, 'u1-t2', 'u1'),
                (3, 'u2-t1', 'u2')])

    @requires_models(User, Tweet)
    def test_compound_select_as_subquery(self):
        with self.database.atomic():
            for i in range(5):
                user = User.create(username='u%s' % i)
                for j in range(i * 2):
                    Tweet.create(user=user, content='t%s-%s' % (i, j))

        q1 = (Tweet
              .select(Tweet.id, Tweet.content, User.username)
              .join(User)
              .where(User.username == 'u3'))
        q2 = (Tweet
              .select(Tweet.id, Tweet.content, User.username)
              .join(User)
              .where(User.username.in_(['u2', 'u4'])))
        union = (q1 | q2)

        q = (union
             .select_from(union.c.username, fn.COUNT(union.c.id).alias('ct'))
             .group_by(union.c.username)
             .order_by(fn.COUNT(union.c.id).desc())
             .dicts())
        self.assertEqual(list(q), [
            {'username': 'u4', 'ct': 8},
            {'username': 'u3', 'ct': 6},
            {'username': 'u2', 'ct': 4}])

    @requires_models(User, Tweet)
    def test_union_with_join(self):
        u1, u2 = [User.create(username='u%s' % i) for i in (1, 2)]
        for u, ts in ((u1, ('t1', 't2')), (u2, ('t1',))):
            for t in ts:
                Tweet.create(user=u, content='%s-%s' % (u.username, t))

        with self.assertQueryCount(1):
            q1 = (User
                  .select(User, Tweet)
                  .join(Tweet, on=(Tweet.user == User.id).alias('foo')))
            q2 = (User
                  .select(User, Tweet)
                  .join(Tweet, on=(Tweet.user == User.id).alias('foo')))

            self.assertEqual(
                sorted([(user.username, user.foo.content) for user in q1]),
                [('u1', 'u1-t1'), ('u1', 'u1-t2'), ('u2', 'u2-t1')])

        with self.assertQueryCount(1):
            uq = q1.union_all(q2)
            result = [(user.username, user.foo.content) for user in uq]
            self.assertEqual(sorted(result), [
                ('u1', 'u1-t1'),
                ('u1', 'u1-t1'),
                ('u1', 'u1-t2'),
                ('u1', 'u1-t2'),
                ('u2', 'u2-t1'),
                ('u2', 'u2-t1'),
            ])

    @skip_if(IS_SQLITE_OLD or (IS_MYSQL and not IS_MYSQL_ADVANCED_FEATURES))
    @requires_models(User)
    def test_union_cte(self):
        with self.database.atomic():
            (User
             .insert_many({'username': 'u%s' % i} for i in range(10))
             .execute())

        lhs = User.select().where(User.username.in_(['u1', 'u3']))
        rhs = User.select().where(User.username.in_(['u5', 'u7']))
        u_cte = (lhs | rhs).cte('users_union')

        query = (User
                 .select(User.username)
                 .join(u_cte, on=(User.id == u_cte.c.id))
                 .where(User.username.in_(['u1', 'u7']))
                 .with_cte(u_cte))
        self.assertEqual(sorted([u.username for u in query]), ['u1', 'u7'])

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

        with self.assertQueryCount(1):
            query = (Tweet
                     .select(Tweet, User)
                     .from_(Tweet, User)
                     .where(
                         (Tweet.user == User.id) &
                         (User.username == 'huey'))
                     .order_by(Tweet.id)
                     .dicts())

            self.assertEqual([t['content'] for t in query],
                             ['meow', 'hiss', 'purr'])
            self.assertEqual([t['username'] for t in query],
                             ['huey', 'huey', 'huey'])

    @requires_models(Point)
    def test_subquery_in_select_expression(self):
        for x, y in ((1, 1), (1, 2), (10, 10), (10, 20)):
            Point.create(x=x, y=y)

        with self.assertQueryCount(1):
            PA = Point.alias('pa')
            subq = PA.select(fn.SUM(PA.y)).where(PA.x == Point.x)
            query = (Point
                     .select(Point.x, Point.y, subq.alias('sy'))
                     .order_by(Point.x, Point.y))
            self.assertEqual(list(query.tuples()), [
                (1, 1, 3),
                (1, 2, 3),
                (10, 10, 30),
                (10, 20, 30)])

        with self.assertQueryCount(1):
            query = (Point
                     .select(Point.x, (Point.y + subq).alias('sy'))
                     .order_by(Point.x, Point.y))
            self.assertEqual(list(query.tuples()), [
                (1, 4), (1, 5),
                (10, 40), (10, 50)])

    @requires_models(User, Tweet)
    def test_filtering(self):
        with self.database.atomic():
            huey = self.add_user('huey')
            mickey = self.add_user('mickey')
            self.add_tweets(huey, 'meow', 'hiss', 'purr')
            self.add_tweets(mickey, 'woof', 'wheeze')

        with self.assertQueryCount(1):
            query = Tweet.filter(user__username='huey').order_by(Tweet.content)
            self.assertEqual([row.content for row in query],
                             ['hiss', 'meow', 'purr'])

        with self.assertQueryCount(1):
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

    def test_deferred_fk_dependency_graph(self):
        class AUser(TestModel):
            foo = DeferredForeignKey('Tweet')
        class ZTweet(TestModel):
            user = ForeignKeyField(AUser, backref='ztweets')

        self.assertEqual(sort_models([AUser, ZTweet]), [AUser, ZTweet])

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
        with self.assertQueryCount(5):
            huey.delete_instance(recursive=True)

        queries = [logrecord.msg for logrecord in self._qh.queries[-5:]]
        self.assertEqual(sorted(queries), [
            ('DELETE FROM "favorite" WHERE ('
             '"favorite"."tweet_id" IN ('
             'SELECT "t1"."id" FROM "tweet" AS "t1" WHERE ('
             '"t1"."user_id" = ?)))', [huey.id]),
            ('DELETE FROM "favorite" WHERE ("favorite"."user_id" = ?)',
             [huey.id]),
            ('DELETE FROM "tweet" WHERE ("tweet"."user_id" = ?)', [huey.id]),
            ('DELETE FROM "users" WHERE ("users"."id" = ?)', [huey.id]),
            ('UPDATE "account" SET "user_id" = ? '
             'WHERE ("account"."user_id" = ?)',
             [None, huey.id]),
        ])

        # Only one user left.
        self.assertEqual(User.select().count(), 1)

        # Huey's account has had the FK cleared out.
        acct = Account.get(Account.email == 'huey@meow.com')
        self.assertTrue(acct.user is None)

        # Huey owned a favorite and one of huey's tweets was the other fav.
        self.assertEqual(Favorite.select().count(), 0)

        # The only tweet left is mickey's.
        self.assertEqual(Tweet.select().count(), 1)
        tweet = Tweet.get()
        self.assertEqual(tweet.content, 'woof')

    def test_delete_nullable(self):
        huey = User.get(User.username == 'huey')
        # Favorite -> Tweet -> User (other users' favorites of huey's tweets)
        # Favorite -> User (huey's favorite tweets)
        # Account -> User (huey's account)
        # User ... for a total of 5. Favorite x2, Tweet, Account, User.
        with self.assertQueryCount(5):
            huey.delete_instance(recursive=True, delete_nullable=True)

        # Get the last 5 delete queries.
        queries = [logrecord.msg for logrecord in self._qh.queries[-5:]]
        self.assertEqual(sorted(queries), [
            ('DELETE FROM "account" WHERE ("account"."user_id" = ?)',
             [huey.id]),
            ('DELETE FROM "favorite" WHERE ('
             '"favorite"."tweet_id" IN ('
             'SELECT "t1"."id" FROM "tweet" AS "t1" WHERE ('
             '"t1"."user_id" = ?)))', [huey.id]),
            ('DELETE FROM "favorite" WHERE ("favorite"."user_id" = ?)',
             [huey.id]),
            ('DELETE FROM "tweet" WHERE ("tweet"."user_id" = ?)', [huey.id]),
            ('DELETE FROM "users" WHERE ("users"."id" = ?)', [huey.id]),
        ])

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

    def test_default_present_on_insert(self):
        # Although value is not specified, it has a default, which is included
        # in the INSERT.
        query = Sample.insert(counter=0)
        self.assertSQL(query, (
            'INSERT INTO "sample" ("counter", "value") '
            'VALUES (?, ?)'), [0, 1.0])

        # Default values are also included when doing bulk inserts.
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

        # Defaults are not present when doing a read query.
        with self.assertQueryCount(1):
            # Simple query.
            query = (SampleMeta.select(SampleMeta.sample)
                     .order_by(SampleMeta.value))
            sm1_db, sm2_db = list(query)
            self.assertIsNone(sm1_db.value)
            self.assertIsNone(sm2_db.value)

        with self.assertQueryCount(1):
            # Join-graph query.
            query = (SampleMeta
                     .select(SampleMeta.sample,
                             Sample.counter)
                     .join(Sample)
                     .order_by(SampleMeta.value))

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

        query = Sample.select(counter_group)
        self.assertEqual(query.scalar(), '0,1,2')

    def test_safe_python_value(self):
        for i in range(3):
            Sample.create(counter=i, value=i)

        counter_group = fn.GROUP_CONCAT(Sample.counter)
        query = Sample.select(counter_group.alias('counter'))
        self.assertEqual(query.get().counter, '0,1,2')
        self.assertEqual(query.scalar(), '0,1,2')

        query = Sample.select(counter_group.alias('counter_group'))
        self.assertEqual(query.get().counter_group, '0,1,2')
        self.assertEqual(query.scalar(), '0,1,2')

    def test_conv_using_python_value(self):
        for i in range(3):
            Sample.create(counter=i, value=i)

        counter = (fn
                   .GROUP_CONCAT(Sample.counter)
                   .python_value(lambda x: [int(i) for i in x.split(',')]))
        query = Sample.select(counter.alias('counter'))
        self.assertEqual(query.get().counter, [0, 1, 2])

        query = Sample.select(counter.alias('counter_group'))
        self.assertEqual(query.get().counter_group, [0, 1, 2])

        query = Sample.select(counter)
        self.assertEqual(query.scalar(), [0, 1, 2])

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

    def test_join_aliased_columns(self):
        query = (Tweet
                 .select(Tweet.id.alias('tweet_id'), Tweet.content)
                 .order_by(Tweet.id))
        self.assertEqual([(t.tweet_id, t.content) for t in query], [
            (1, 'meow'),
            (2, 'purr'),
            (3, 'hiss'),
            (4, 'woof')])

        query = (Tweet
                 .select(Tweet.id.alias('tweet_id'), Tweet.content)
                 .join(User)
                 .where(User.username == 'huey')
                 .order_by(Tweet.id))
        self.assertEqual([(t.tweet_id, t.content) for t in query], [
            (1, 'meow'),
            (2, 'purr')])

    def test_join(self):
        UA = User.alias('ua')
        query = self._test_query(lambda: UA).join(UA)
        self.assertTweets(query)

    def test_join_on(self):
        UA = User.alias('ua')
        query = self._test_query(lambda: UA).join(UA, on=(Tweet.user == UA.id))
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

    def test_join_on_alias_attr(self):
        UA = User.alias('ua')
        q = self._test_query(lambda: UA)
        q = q.join(UA, on=(Tweet.user == UA.id).alias('foo'), attr='bar')
        self.assertTweets(q, 'bar')

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
        with self.assertQueryCount(1):
            query = (User
                     .select(User, TA, UA)
                     .join(TA)
                     .join(UA, on=(TA.user_id == UA.id).alias('foo'))
                     .order_by(User.username, TA.content))

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
            with self.assertQueryCount(1):
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

                data = [(t.content, t.user.username) for t in query]
                self.assertEqual(data, [('meow', 'huey'), ('purr', 'huey')])


@skip_unless(IS_POSTGRESQL or IS_MYSQL_ADVANCED_FEATURES or IS_SQLITE_25,
             'window function')
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
                 .order_by(Sample.counter, Sample.value)
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
                 .order_by(Sample.counter, Sample.value)
                 .tuples())
        self.assertEqual(list(query), expected)

    def test_mixed_ordering(self):
        s = fn.SUM(Sample.value).over(order_by=[Sample.value])
        query = (Sample
                 .select(Sample.counter, Sample.value, s.alias('rtotal'))
                 .order_by(Sample.id))
        # We end up with window going 1., 3., 10., 20., 100..
        # So:
        # 1 |  10 | (1 + 3 + 10)
        # 1 |  20 | (1 + 3 + 10  + 20)
        # 2 |   1 | (1)
        # 2 |   3 | (1 + 3)
        # 3 | 100 | (1 + 3 + 10 + 20 + 100)
        self.assertEqual([(r.counter, r.value, r.rtotal) for r in query], [
            (1, 10., 14.),
            (1, 20., 34.),
            (2, 1., 1.),
            (2, 3., 4.),
            (3, 100., 134.)])

    def test_reuse_window(self):
        w = Window(order_by=[Sample.value])
        with self.database.atomic():
            Sample.delete().execute()
            for i in range(10):
                Sample.create(counter=i, value=10 * i)

        query = (Sample
                 .select(Sample.counter, Sample.value,
                         fn.NTILE(4).over(w).alias('quartile'),
                         fn.NTILE(5).over(w).alias('quintile'),
                         fn.NTILE(100).over(w).alias('percentile'))
                 .window(w)
                 .order_by(Sample.id))
        results = [(r.counter, r.value, r.quartile, r.quintile, r.percentile)
                   for r in query]
        self.assertEqual(results, [
            # ct, v, 4tile, 5tile, 100tile
            (0, 0., 1, 1, 1),
            (1, 10., 1, 1, 2),
            (2, 20., 1, 2, 3),
            (3, 30., 2, 2, 4),
            (4, 40., 2, 3, 5),
            (5, 50., 2, 3, 6),
            (6, 60., 3, 4, 7),
            (7, 70., 3, 4, 8),
            (8, 80., 4, 5, 9),
            (9, 90., 4, 5, 10),
        ])

    def test_ordered_window(self):
        window = Window(partition_by=[Sample.counter],
                        order_by=[Sample.value.desc()])
        query = (Sample
                 .select(Sample.counter, Sample.value,
                         fn.RANK().over(window=window).alias('rank'))
                 .window(window)
                 .order_by(Sample.counter, fn.RANK().over(window=window))
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
                         fn.LAG(Sample.counter, 1).over(order_by=[Sample.id]))
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

    def test_frame_types(self):
        Sample.create(counter=1, value=20.)
        Sample.create(counter=2, value=1.)  # Observe logical peer handling.

        # Defaults to RANGE.
        query = (Sample
                 .select(Sample.counter, Sample.value,
                         fn.SUM(Sample.value).over(
                             order_by=[Sample.counter, Sample.value]))
                 .order_by(Sample.id))
        self.assertEqual(list(query.tuples()), [
            (1, 10., 10.),
            (1, 20., 50.),
            (2, 1., 52.),
            (2, 3., 55.),
            (3, 100., 155.),
            (1, 20., 50.),
            (2, 1., 52.)])

        # Explicitly specify ROWS.
        query = (Sample
                 .select(Sample.counter, Sample.value,
                         fn.SUM(Sample.value).over(
                             order_by=[Sample.counter, Sample.value],
                             frame_type=Window.ROWS))
                 .order_by(Sample.counter, Sample.value))
        self.assertEqual(list(query.tuples()), [
            (1, 10., 10.),
            (1, 20., 30.),
            (1, 20., 50.),
            (2, 1., 51.),
            (2, 1., 52.),
            (2, 3., 55.),
            (3, 100., 155.)])

        # Including a boundary results in ROWS.
        query = (Sample
                 .select(Sample.counter, Sample.value,
                         fn.SUM(Sample.value).over(
                             order_by=[Sample.counter, Sample.value],
                             start=Window.preceding(2)))
                 .order_by(Sample.counter, Sample.value))
        self.assertEqual(list(query.tuples()), [
            (1, 10., 10.),
            (1, 20., 30.),
            (1, 20., 50.),
            (2, 1., 41.),
            (2, 1., 22.),
            (2, 3., 5.),
            (3, 100., 104.)])

    @skip_if(IS_MYSQL, 'requires OVER() with FILTER')
    def test_filter_clause(self):
        condsum = fn.SUM(Sample.value).filter(Sample.counter > 1).over(
            order_by=[Sample.id], start=Window.preceding(1))
        query = (Sample
                 .select(Sample.counter, Sample.value, condsum.alias('cs'))
                 .order_by(Sample.value))
        self.assertEqual(list(query.tuples()), [
            (2, 1., 1.),
            (2, 3., 4.),
            (1, 10., None),
            (1, 20., None),
            (3, 100., 103.),
        ])

    @skip_if(IS_MYSQL or (IS_SQLITE and not IS_SQLITE_30),
             'requires FILTER with aggregates')
    def test_filter_with_aggregate(self):
        condsum = fn.SUM(Sample.value).filter(Sample.counter > 1)
        query = (Sample
                 .select(Sample.counter, condsum.alias('cs'))
                 .group_by(Sample.counter)
                 .order_by(Sample.counter))
        self.assertEqual(list(query.tuples()), [
            (1, None),
            (2, 4.),
            (3, 100.)])


@skip_if(IS_SQLITE or (IS_MYSQL and not IS_MYSQL_ADVANCED_FEATURES))
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

            self.assertRaises((OperationalError, InternalError), will_fail)


class ServerDefault(TestModel):
    timestamp = DateTimeField(constraints=[SQL('default (now())')])


@requires_postgresql
class TestReturningIntegration(ModelTestCase):
    requires = [User]

    def test_simple_returning(self):
        query = User.insert(username='charlie')
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") VALUES (?) '
            'RETURNING "users"."id"'),
            ['charlie'])

        self.assertEqual(query.execute(), 1)

        # By default returns a tuple.
        query = User.insert(username='huey')
        self.assertEqual(query.execute(), 2)
        self.assertEqual(list(query), [(2,)])

        # If we specify a returning clause we get user instances.
        query = User.insert(username='snoobie').returning(User)
        query.execute()
        self.assertEqual([x.username for x in query], ['snoobie'])

        query = (User
                 .insert(username='zaizee')
                 .returning(User.id, User.username)
                 .dicts())
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") VALUES (?) '
            'RETURNING "users"."id", "users"."username"'), ['zaizee'])

        cursor = query.execute()
        row, = list(cursor)
        self.assertEqual(row, {'id': 4, 'username': 'zaizee'})

        query = (User
                 .insert(username='mickey')
                 .returning(User)
                 .objects())
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") VALUES (?) '
            'RETURNING "users"."id", "users"."username"'), ['mickey'])
        cursor = query.execute()
        row, = list(cursor)
        self.assertEqual(row.id, 5)
        self.assertEqual(row.username, 'mickey')

        # Can specify aliases.
        query = (User
                 .insert(username='sipp')
                 .returning(User.username.alias('new_username')))
        self.assertEqual([x.new_username for x in query.execute()], ['sipp'])

    def test_simple_returning_insert_update_delete(self):
        res = User.insert(username='charlie').returning(User).execute()
        self.assertEqual([u.username for u in res], ['charlie'])

        res = (User
               .update(username='charlie2')
               .where(User.id == 1)
               .returning(User)
               .execute())
        # Subsequent iterations are cached.
        for _ in range(2):
            self.assertEqual([u.username for u in res], ['charlie2'])

        res = (User
               .delete()
               .where(User.id == 1)
               .returning(User)
               .execute())
        # Subsequent iterations are cached.
        for _ in range(2):
            self.assertEqual([u.username for u in res], ['charlie2'])

    def test_simple_insert_update_delete_no_returning(self):
        query = User.insert(username='charlie')
        self.assertEqual(query.execute(), 1)

        query = User.insert(username='huey')
        self.assertEqual(query.execute(), 2)

        query = User.update(username='huey2').where(User.username == 'huey')
        self.assertEqual(query.execute(), 1)
        self.assertEqual(query.execute(), 0)  # No rows updated!

        query = User.delete().where(User.username == 'huey2')
        self.assertEqual(query.execute(), 1)
        self.assertEqual(query.execute(), 0)  # No rows updated!

    @requires_models(ServerDefault)
    def test_returning_server_defaults(self):
        query = (ServerDefault
                 .insert()
                 .returning(ServerDefault.id, ServerDefault.timestamp))
        self.assertSQL(query, (
            'INSERT INTO "server_default" '
            'DEFAULT VALUES '
            'RETURNING "server_default"."id", "server_default"."timestamp"'),
            [])

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
            'INSERT INTO "category" ("name") VALUES (?) '
            'RETURNING "category"."name"'), ['root'])

        self.assertEqual(query.execute(), 'root')

    def test_returning_multi(self):
        data = [{'username': 'huey'}, {'username': 'mickey'}]
        query = User.insert_many(data)
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") VALUES (?), (?) '
            'RETURNING "users"."id"'), ['huey', 'mickey'])

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
            'RETURNING "users"."id"'), [])

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
            'WHERE ("users"."username" = ?) '
            'RETURNING "users"."id", "users"."username"'), ['ziggy', 'zaizee'])
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
            'DELETE FROM "users" WHERE ("users"."username" = ?) '
            'RETURNING "users"."id", "users"."username"'), ['zaizee'])
        data = query.execute()
        user = data[0]
        self.assertEqual(user.username, 'zaizee')
        self.assertEqual(user.id, zaizee_id)


class Member(TestModel):
    name = TextField()
    recommendedby = ForeignKeyField('self', null=True)


class TestCTEIntegration(ModelTestCase):
    requires = [Category]

    def setUp(self):
        super(TestCTEIntegration, self).setUp()
        CC = Category.create
        root = CC(name='root')
        p1 = CC(name='p1', parent=root)
        p2 = CC(name='p2', parent=root)
        p3 = CC(name='p3', parent=root)
        c11 = CC(name='c11', parent=p1)
        c12 = CC(name='c12', parent=p1)
        c31 = CC(name='c31', parent=p3)

    @skip_if(IS_SQLITE_OLD or (IS_MYSQL and not IS_MYSQL_ADVANCED_FEATURES))
    @requires_models(Member)
    def test_docs_example(self):
        f = Member.create(name='founder')
        gen2_1 = Member.create(name='g2-1', recommendedby=f)
        gen2_2 = Member.create(name='g2-2', recommendedby=f)
        gen2_3 = Member.create(name='g2-3', recommendedby=f)
        gen3_1_1 = Member.create(name='g3-1-1', recommendedby=gen2_1)
        gen3_1_2 = Member.create(name='g3-1-2', recommendedby=gen2_1)
        gen3_3_1 = Member.create(name='g3-3-1', recommendedby=gen2_3)

        # Get recommender chain for 331.
        base = (Member
                .select(Member.recommendedby)
                .where(Member.id == gen3_3_1.id)
                .cte('recommenders', recursive=True, columns=('recommender',)))

        MA = Member.alias()
        recursive = (MA
                     .select(MA.recommendedby)
                     .join(base, on=(MA.id == base.c.recommender)))

        cte = base.union_all(recursive)
        query = (cte
                 .select_from(cte.c.recommender, Member.name)
                 .join(Member, on=(cte.c.recommender == Member.id))
                 .order_by(Member.id.desc()))
        self.assertEqual([m.name for m in query], ['g2-3', 'founder'])

    @skip_if(IS_SQLITE_OLD or (IS_MYSQL and not IS_MYSQL_ADVANCED_FEATURES))
    def test_simple_cte(self):
        cte = (Category
               .select(Category.name, Category.parent)
               .cte('catz', columns=('name', 'parent')))

        cte_sql = ('WITH "catz" ("name", "parent") AS ('
                   'SELECT "t1"."name", "t1"."parent_id" '
                   'FROM "category" AS "t1") '
                   'SELECT "catz"."name", "catz"."parent" AS "pname" '
                   'FROM "catz" '
                   'ORDER BY "catz"."name"')

        query = (Category
                 .select(cte.c.name, cte.c.parent.alias('pname'))
                 .from_(cte)
                 .order_by(cte.c.name)
                 .with_cte(cte))
        self.assertSQL(query, cte_sql, [])

        query2 = (cte.select_from(cte.c.name, cte.c.parent.alias('pname'))
                  .order_by(cte.c.name))
        self.assertSQL(query2, cte_sql, [])

        self.assertEqual([(row.name, row.pname) for row in query], [
            ('c11', 'p1'),
            ('c12', 'p1'),
            ('c31', 'p3'),
            ('p1', 'root'),
            ('p2', 'root'),
            ('p3', 'root'),
            ('root', None)])
        self.assertEqual([(row.name, row.pname) for row in query],
                         [(row.name, row.pname) for row in query2])

    @skip_if(IS_SQLITE_OLD or (IS_MYSQL and not IS_MYSQL_ADVANCED_FEATURES))
    def test_cte_join(self):
        cte = (Category
               .select(Category.name)
               .cte('parents', columns=('name',)))

        query = (Category
                 .select(Category.name, cte.c.name.alias('pname'))
                 .join(cte, on=(Category.parent == cte.c.name))
                 .order_by(Category.name)
                 .with_cte(cte))

        self.assertSQL(query, (
            'WITH "parents" ("name") AS ('
            'SELECT "t1"."name" FROM "category" AS "t1") '
            'SELECT "t2"."name", "parents"."name" AS "pname" '
            'FROM "category" AS "t2" '
            'INNER JOIN "parents" ON ("t2"."parent_id" = "parents"."name") '
            'ORDER BY "t2"."name"'), [])
        self.assertEqual([(c.name, c.parents['pname']) for c in query], [
            ('c11', 'p1'),
            ('c12', 'p1'),
            ('c31', 'p3'),
            ('p1', 'root'),
            ('p2', 'root'),
            ('p3', 'root'),
        ])

    @skip_if(IS_SQLITE_OLD or IS_MYSQL, 'requires recursive cte support')
    def test_recursive_cte(self):
        def get_parents(cname):
            C1 = Category.alias()
            C2 = Category.alias()

            level = SQL('1').cast('integer').alias('level')
            path = C1.name.cast('text').alias('path')

            base = (C1
                    .select(C1.name, C1.parent, level, path)
                    .where(C1.name == cname)
                    .cte('parents', recursive=True))

            rlevel = (base.c.level + 1).alias('level')
            rpath = base.c.path.concat('->').concat(C2.name).alias('path')
            recursive = (C2
                         .select(C2.name, C2.parent, rlevel, rpath)
                         .from_(base)
                         .join(C2, on=(C2.name == base.c.parent_id)))

            cte = base + recursive
            query = (cte
                     .select_from(cte.c.name, cte.c.level, cte.c.path)
                     .order_by(cte.c.level))
            self.assertSQL(query, (
                'WITH RECURSIVE "parents" AS ('
                'SELECT "t1"."name", "t1"."parent_id", '
                'CAST(1 AS integer) AS "level", '
                'CAST("t1"."name" AS text) AS "path" '
                'FROM "category" AS "t1" '
                'WHERE ("t1"."name" = ?) '
                'UNION ALL '
                'SELECT "t2"."name", "t2"."parent_id", '
                '("parents"."level" + ?) AS "level", '
                '(("parents"."path" || ?) || "t2"."name") AS "path" '
                'FROM "parents" '
                'INNER JOIN "category" AS "t2" '
                'ON ("t2"."name" = "parents"."parent_id")) '
                'SELECT "parents"."name", "parents"."level", "parents"."path" '
                'FROM "parents" '
                'ORDER BY "parents"."level"'), [cname, 1, '->'])
            return query

        data = [row for row in get_parents('c31').tuples()]
        self.assertEqual(data, [
            ('c31', 1, 'c31'),
            ('p3', 2, 'c31->p3'),
            ('root', 3, 'c31->p3->root')])

        data = [(c.name, c.level, c.path)
                for c in get_parents('c12').namedtuples()]
        self.assertEqual(data, [
            ('c12', 1, 'c12'),
            ('p1', 2, 'c12->p1'),
            ('root', 3, 'c12->p1->root')])

        query = get_parents('root')
        data = [(r.name, r.level, r.path) for r in query]
        self.assertEqual(data, [('root', 1, 'root')])

    @skip_if(IS_SQLITE_OLD or IS_MYSQL, 'requires recursive cte support')
    def test_recursive_cte2(self):
        hierarchy = (Category
                     .select(Category.name, Value(0).alias('level'))
                     .where(Category.parent.is_null(True))
                     .cte(name='hierarchy', recursive=True))

        C = Category.alias()
        recursive = (C
                     .select(C.name, (hierarchy.c.level + 1).alias('level'))
                     .join(hierarchy, on=(C.parent == hierarchy.c.name)))

        cte = hierarchy.union_all(recursive)
        query = (cte
                 .select_from(cte.c.name, cte.c.level)
                 .order_by(cte.c.name))
        self.assertEqual([(r.name, r.level) for r in query], [
            ('c11', 2),
            ('c12', 2),
            ('c31', 2),
            ('p1', 1),
            ('p2', 1),
            ('p3', 1),
            ('root', 0)])

    @skip_if(IS_SQLITE_OLD or IS_MYSQL, 'requires recursive cte support')
    def test_recursive_cte_docs_example(self):
        # Define the base case of our recursive CTE. This will be categories that
        # have a null parent foreign-key.
        Base = Category.alias()
        level = Value(1).cast('integer').alias('level')
        path = Base.name.cast('text').alias('path')
        base_case = (Base
                     .select(Base.name, Base.parent, level, path)
                     .where(Base.parent.is_null())
                     .cte('base', recursive=True))

        # Define the recursive terms.
        RTerm = Category.alias()
        rlevel = (base_case.c.level + 1).alias('level')
        rpath = base_case.c.path.concat('->').concat(RTerm.name).alias('path')
        recursive = (RTerm
                     .select(RTerm.name, RTerm.parent, rlevel, rpath)
                     .join(base_case, on=(RTerm.parent == base_case.c.name)))

        # The recursive CTE is created by taking the base case and UNION ALL with
        # the recursive term.
        cte = base_case.union_all(recursive)

        # We will now query from the CTE to get the categories, their levels,  and
        # their paths.
        query = (cte
                 .select_from(cte.c.name, cte.c.level, cte.c.path)
                 .order_by(cte.c.path))
        data = [(obj.name, obj.level, obj.path) for obj in query]
        self.assertEqual(data, [
            ('root', 1, 'root'),
            ('p1', 2, 'root->p1'),
            ('c11', 3, 'root->p1->c11'),
            ('c12', 3, 'root->p1->c12'),
            ('p2', 2, 'root->p2'),
            ('p3', 2, 'root->p3'),
            ('c31', 3, 'root->p3->c31')])

    @requires_models(Sample)
    @skip_if(IS_SQLITE_OLD or IS_MYSQL, 'sqlite too old for ctes, mysql flaky')
    def test_cte_reuse_aggregate(self):
        data = (
            (1, (1.25, 1.5, 1.75)),
            (2, (2.1, 2.3, 2.5, 2.7, 2.9)),
            (3, (3.5, 3.5)))
        with self.database.atomic():
            for counter, values in data:
                (Sample
                 .insert_many([(counter, value) for value in values],
                              fields=[Sample.counter, Sample.value])
                 .execute())

        cte = (Sample
               .select(Sample.counter, fn.AVG(Sample.value).alias('avg_value'))
               .group_by(Sample.counter)
               .cte('count_to_avg', columns=('counter', 'avg_value')))

        query = (Sample
                 .select(Sample.counter,
                         (Sample.value - cte.c.avg_value).alias('diff'))
                 .join(cte, on=(Sample.counter == cte.c.counter))
                 .where(Sample.value > cte.c.avg_value)
                 .order_by(Sample.value)
                 .with_cte(cte))
        self.assertEqual([(a, round(b, 2)) for a, b in query.tuples()], [
            (1, .25),
            (2, .2),
            (2, .4)])


@skip_if(not IS_SQLITE_15, 'requires row-values')
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

    def test_tuple_subquery(self):
        ua, ub, uc = [User.create(username=username) for username in 'abc']
        UA = User.alias()
        subquery = (UA
                    .select(UA.username, UA.id)
                    .where(UA.username != 'b'))

        query = (User
                 .select(User.username)
                 .where(Tuple(User.username, User.id).in_(subquery))
                 .order_by(User.username))
        self.assertEqual([u.username for u in query], ['a', 'c'])

    @requires_models(CPK)
    def test_row_value_composite_key(self):
        CPK.insert_many([('k1', 1, 1), ('k2', 2, 2), ('k3', 3, 3)]).execute()

        cpk = CPK.get(CPK._meta.primary_key == ('k2', 2))
        self.assertEqual(cpk._pk, ('k2', 2))

        cpk = CPK['k3', 3]
        self.assertEqual(cpk._pk, ('k3', 3))

        uq = CPK.update(extra=20).where(CPK._meta.primary_key != ('k2', 2))
        uq.execute()

        self.assertEqual(list(sorted(CPK.select().tuples())), [
            ('k1', 1, 20), ('k2', 2, 2), ('k3', 3, 20)])


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

    @skip_if(IS_SQLITE, 'sqlite is not supported')
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


class TestMetaTableName(BaseTestCase):
    def test_table_name_behavior(self):
        def make_model(model_name, table=None):
            class Meta:
                legacy_table_names = False
                table_name = table
            return type(model_name, (Model,), {'Meta': Meta})
        def assertTableName(expected, model_name, table_name=None):
            model_class = make_model(model_name, table_name)
            self.assertEqual(model_class._meta.table_name, expected)

        assertTableName('users', 'User', 'users')
        assertTableName('tweet', 'Tweet')
        assertTableName('user_profile', 'UserProfile')
        assertTableName('activity_log_status', 'ActivityLogStatus')

        assertTableName('camel_case', 'CamelCase')
        assertTableName('camel_camel_case', 'CamelCamelCase')
        assertTableName('camel2_camel2_case', 'Camel2Camel2Case')
        assertTableName('http_request', 'HTTPRequest')
        assertTableName('api_response', 'APIResponse')
        assertTableName('api_response', 'API_Response')
        assertTableName('web_http_request', 'WebHTTPRequest')
        assertTableName('get_http_response_code', 'getHTTPResponseCode')
        assertTableName('foo_bar', 'foo_Bar')
        assertTableName('foo_bar', 'Foo__Bar')


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

        class Child(Base): pass
        class GrandChild(Child): pass

        for ModelClass in (Child, GrandChild):
            self.assertEqual(ModelClass._meta.constraints, ['c1', 'c2'])
            self.assertTrue(ModelClass._meta.database is db)
            self.assertEqual(ModelClass._meta.indexes, [(('username',), True)])
            self.assertEqual(ModelClass._meta.options, {'key': 'value'})
            self.assertTrue(ModelClass._meta.only_save_dirty)
            self.assertEqual(ModelClass._meta.schema, 'magic')

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

    def test_temporary_inheritance(self):
        class T0(TestModel): pass
        class T1(TestModel):
            class Meta:
                temporary = True

        class T2(T1): pass
        class T3(T1):
            class Meta:
                temporary = False

        self.assertFalse(T0._meta.temporary)
        self.assertTrue(T1._meta.temporary)
        self.assertTrue(T2._meta.temporary)
        self.assertFalse(T3._meta.temporary)


class TestModelSetDatabase(BaseTestCase):
    def test_set_database(self):
        class Register(Model):
            value = IntegerField()

        db_a = get_in_memory_db()
        db_b = get_in_memory_db()
        Register._meta.set_database(db_a)
        Register.create_table()
        Register._meta.set_database(db_b)
        self.assertFalse(Register.table_exists())
        self.assertEqual(db_a.get_tables(), ['register'])
        self.assertEqual(db_b.get_tables(), [])
        db_a.close()
        db_b.close()


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


class OnConflictTests(object):
    requires = [Emp]
    test_data = (
        ('huey', 'cat', '123'),
        ('zaizee', 'cat', '124'),
        ('mickey', 'dog', '125'),
    )

    def setUp(self):
        super(OnConflictTests, self).setUp()
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


def requires_upsert(m):
    return skip_unless(IS_SQLITE_24 or IS_POSTGRESQL, 'requires upsert')(m)


class KV(TestModel):
    key = CharField(unique=True)
    value = IntegerField()


class PGOnConflictTests(OnConflictTests):
    @requires_upsert
    def test_update(self):
        # Conflict on empno - we'll preserve name and update the ID. This will
        # overwrite the previous row and set a new ID.
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

        # Conflicts on first/last name. The first name is preserved while the
        # last-name is updated. The new empno is thrown out.
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

    @requires_upsert
    @requires_models(OCTest)
    def test_update_atomic(self):
        # Add a new row with the given "a" value. If a conflict occurs,
        # re-insert with b=b+2.
        query = OCTest.insert(a='foo', b=1).on_conflict(
            conflict_target=(OCTest.a,),
            update={OCTest.b: OCTest.b + 2})

        # First execution returns rowid=1. Second execution hits the conflict-
        # resolution, and will update the value in "b" from 1 -> 3.
        rowid1 = query.execute()
        rowid2 = query.clone().execute()
        self.assertEqual(rowid1, rowid2)

        obj = OCTest.get()
        self.assertEqual(obj.a, 'foo')
        self.assertEqual(obj.b, 3)

        query = OCTest.insert(a='foo', b=4, c=5).on_conflict(
            conflict_target=[OCTest.a],
            preserve=[OCTest.c],
            update={OCTest.b: OCTest.b + 100})
        self.assertEqual(query.execute(), rowid2)

        obj = OCTest.get()
        self.assertEqual(obj.a, 'foo')
        self.assertEqual(obj.b, 103)
        self.assertEqual(obj.c, 5)

    @requires_upsert
    @requires_models(OCTest)
    def test_update_where_clause(self):
        # Add a new row with the given "a" value. If a conflict occurs,
        # re-insert with b=b+2 so long as the original b < 3.
        query = OCTest.insert(a='foo', b=1).on_conflict(
            conflict_target=(OCTest.a,),
            update={OCTest.b: OCTest.b + 2},
            where=(OCTest.b < 3))

        # First execution returns rowid=1. Second execution hits the conflict-
        # resolution, and will update the value in "b" from 1 -> 3.
        rowid1 = query.execute()
        rowid2 = query.clone().execute()
        self.assertEqual(rowid1, rowid2)

        obj = OCTest.get()
        self.assertEqual(obj.a, 'foo')
        self.assertEqual(obj.b, 3)

        # Third execution also returns rowid=1. The WHERE clause prevents us
        # from updating "b" again. If this is SQLite, we get the rowid back, if
        # this is Postgresql we get None (since nothing happened).
        rowid3 = query.clone().execute()
        if IS_SQLITE:
            self.assertEqual(rowid1, rowid3)
        else:
            self.assertTrue(rowid3 is None)

        # Because we didn't satisfy the WHERE clause, the value in "b" is
        # not incremented again.
        obj = OCTest.get()
        self.assertEqual(obj.a, 'foo')
        self.assertEqual(obj.b, 3)

    @requires_upsert
    @requires_models(Emp)  # Has unique on first/last, unique on empno.
    def test_conflict_update_excluded(self):
        e1 = Emp.create(first='huey', last='c', empno='10')
        e2 = Emp.create(first='zaizee', last='c', empno='20')

        res = (Emp.insert(first='huey', last='c', empno='30')
               .on_conflict(conflict_target=(Emp.first, Emp.last),
                            update={Emp.empno: Emp.empno + EXCLUDED.empno},
                            where=(EXCLUDED.empno != Emp.empno))
               .execute())

        data = sorted(Emp.select(Emp.first, Emp.last, Emp.empno).tuples())
        self.assertEqual(data, [('huey', 'c', '1030'), ('zaizee', 'c', '20')])

    @requires_upsert
    @requires_models(KV)
    def test_conflict_update_excluded2(self):
        KV.create(key='k1', value=1)

        query = (KV.insert(key='k1', value=10)
                 .on_conflict(conflict_target=[KV.key],
                              update={KV.value: KV.value + EXCLUDED.value},
                              where=(EXCLUDED.value > KV.value)))
        query.execute()
        self.assertEqual(KV.select(KV.key, KV.value).tuples()[:], [('k1', 11)])

        # Running it again will have no effect this time, since the new value
        # (10) is not greater than the pre-existing row value (11).
        query.execute()
        self.assertEqual(KV.select(KV.key, KV.value).tuples()[:], [('k1', 11)])

    @requires_upsert
    @requires_models(UKVP)
    def test_conflict_target_constraint_where(self):
        u1 = UKVP.create(key='k1', value=1, extra=1)
        u2 = UKVP.create(key='k2', value=2, extra=2)

        fields = [UKVP.key, UKVP.value, UKVP.extra]
        data = [('k1', 1, 2), ('k2', 2, 3)]

        # XXX: SQLite does not seem to accept parameterized values for the
        # conflict target WHERE clause (e.g., the partial index). So we have to
        # express this literally as ("extra" > 1) rather than using an
        # expression which will be parameterized. Hopefully SQLite's authors
        # decide this is a bug and fix it.
        if IS_SQLITE:
            conflict_where = UKVP.extra > SQL('1')
        else:
            conflict_where = UKVP.extra > 1

        res = (UKVP.insert_many(data, fields)
               .on_conflict(conflict_target=(UKVP.key, UKVP.value),
                            conflict_where=conflict_where,
                            preserve=(UKVP.extra,))
               .execute())

        # How many rows exist? The first one would not have triggered the
        # conflict resolution, since the existing k1/1 row's "extra" value was
        # not greater than 1, thus it did not satisfy the index condition.
        # The second row (k2/2/3) would have triggered the resolution.
        self.assertEqual(UKVP.select().count(), 3)
        query = (UKVP
                 .select(UKVP.key, UKVP.value, UKVP.extra)
                 .order_by(UKVP.key, UKVP.value, UKVP.extra)
                 .tuples())

        self.assertEqual(list(query), [
            ('k1', 1, 1),
            ('k1', 1, 2),
            ('k2', 2, 3)])

        # Verify the primary-key of k2 did not change.
        u2_db = UKVP.get(UKVP.key == 'k2')
        self.assertEqual(u2_db.id, u2.id)


@requires_mysql
class TestUpsertMySQL(OnConflictTests, ModelTestCase):
    def test_replace(self):
        # Unique constraint on first/last would fail - replace.
        query = (Emp
                 .insert(first='mickey', last='dog', empno='1337')
                 .on_conflict('replace')
                 .execute())
        self.assertData([
            ('huey', 'cat', '123'),
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337')])

        # Unique constraint on empno would fail - replace.
        query = (Emp
                 .insert(first='nuggie', last='dog', empno='123')
                 .on_conflict('replace')
                 .execute())
        self.assertData([
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337'),
            ('nuggie', 'dog', '123')])

        # No problems, data added.
        query = (Emp
                 .insert(first='beanie', last='cat', empno='126')
                 .on_conflict('replace')
                 .execute())
        self.assertData([
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337'),
            ('nuggie', 'dog', '123'),
            ('beanie', 'cat', '126')])

    @requires_models(OCTest)
    def test_update(self):
        pk = (OCTest
              .insert(a='a', b=3)
              .on_conflict(update={OCTest.b: 1337})
              .execute())
        oc = OCTest.get(OCTest.a == 'a')
        self.assertEqual(oc.b, 3)

        pk2 = (OCTest
               .insert(a='a', b=4)
               .on_conflict(update={OCTest.b: OCTest.b + 10})
               .execute())
        self.assertEqual(pk, pk2)
        self.assertEqual(OCTest.select().count(), 1)

        oc = OCTest.get(OCTest.a == 'a')
        self.assertEqual(oc.b, 13)

        pk3 = (OCTest
               .insert(a='a2', b=5)
               .on_conflict(update={OCTest.b: 1337})
               .execute())
        self.assertTrue(pk3 != pk2)
        self.assertEqual(OCTest.select().count(), 2)

        oc = OCTest.get(OCTest.a == 'a2')
        self.assertEqual(oc.b, 5)

    @requires_models(OCTest)
    def test_update_preserve(self):
        OCTest.create(a='a', b=3)

        pk = (OCTest
              .insert(a='a', b=4)
              .on_conflict(preserve=[OCTest.b])
              .execute())
        oc = OCTest.get(OCTest.a == 'a')
        self.assertEqual(oc.b, 4)

        pk2 = (OCTest
               .insert(a='a', b=5, c=6)
               .on_conflict(
                   preserve=[OCTest.c],
                   update={OCTest.b: OCTest.b + 100})
               .execute())
        self.assertEqual(pk, pk2)
        self.assertEqual(OCTest.select().count(), 1)

        oc = OCTest.get(OCTest.a == 'a')
        self.assertEqual(oc.b, 104)
        self.assertEqual(oc.c, 6)


class TestReplaceSqlite(OnConflictTests, ModelTestCase):
    database = get_in_memory_db()

    def test_replace(self):
        # Unique constraint on first/last would fail - replace.
        query = (Emp
                 .insert(first='mickey', last='dog', empno='1337')
                 .on_conflict('replace')
                 .execute())
        self.assertData([
            ('huey', 'cat', '123'),
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337')])

        # Unique constraint on empno would fail - replace.
        query = (Emp
                 .insert(first='nuggie', last='dog', empno='123')
                 .on_conflict('replace')
                 .execute())
        self.assertData([
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337'),
            ('nuggie', 'dog', '123')])

        # No problems, data added.
        query = (Emp
                 .insert(first='beanie', last='cat', empno='126')
                 .on_conflict('replace')
                 .execute())
        self.assertData([
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337'),
            ('nuggie', 'dog', '123'),
            ('beanie', 'cat', '126')])

    def test_model_replace(self):
        Emp.replace(first='mickey', last='dog', empno='1337').execute()
        self.assertData([
            ('huey', 'cat', '123'),
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337')])

        Emp.replace(first='beanie', last='cat', empno='999').execute()
        self.assertData([
            ('huey', 'cat', '123'),
            ('zaizee', 'cat', '124'),
            ('mickey', 'dog', '1337'),
            ('beanie', 'cat', '999')])

        Emp.replace_many([('h', 'cat', '123'), ('z', 'cat', '124'),
                          ('b', 'cat', '125')],
                         fields=[Emp.first, Emp.last, Emp.empno]).execute()
        self.assertData([
            ('mickey', 'dog', '1337'),
            ('beanie', 'cat', '999'),
            ('h', 'cat', '123'),
            ('z', 'cat', '124'),
            ('b', 'cat', '125')])


@requires_sqlite
class TestUpsertSqlite(PGOnConflictTests, ModelTestCase):
    database = get_in_memory_db()

    @skip_if(IS_SQLITE_24, 'requires sqlite < 3.24')
    def test_no_preserve_update_where(self):
        # Ensure on SQLite < 3.24 we cannot update or preserve values.
        base = Emp.insert(first='foo', last='bar', empno='125')

        preserve = base.on_conflict(preserve=[Emp.last])
        self.assertRaises(ValueError, preserve.execute)

        update = base.on_conflict(update={Emp.empno: 'xxx'})
        self.assertRaises(ValueError, update.execute)

        where = base.on_conflict(where=(Emp.id > 10))
        self.assertRaises(ValueError, where.execute)

    @skip_unless(IS_SQLITE_24, 'requires sqlite >= 3.24')
    def test_update_meets_requirements(self):
        # Ensure that on >= 3.24 any updates meet the minimum criteria.
        base = Emp.insert(first='foo', last='bar', empno='125')

        # Must specify update or preserve.
        no_update_preserve = base.on_conflict(conflict_target=(Emp.empno,))
        self.assertRaises(ValueError, no_update_preserve.execute)

        # Must specify a conflict target.
        no_conflict_target = base.on_conflict(update={Emp.empno: '125.1'})
        self.assertRaises(ValueError, no_conflict_target.execute)

    @skip_unless(IS_SQLITE_24, 'requires sqlite >= 3.24')
    def test_do_nothing(self):
        query = (Emp
                 .insert(first='foo', last='bar', empno='123')
                 .on_conflict('nothing'))
        self.assertSQL(query, (
            'INSERT INTO "emp" ("first", "last", "empno") '
            'VALUES (?, ?, ?) ON CONFLICT DO NOTHING'), ['foo', 'bar', '123'])

        query.execute()  # Conflict occurs with empno='123'.
        self.assertData(list(self.test_data))


class UKV(TestModel):
    key = TextField()
    value = TextField()
    extra = TextField(default='')

    class Meta:
        constraints = [
            SQL('constraint ukv_key_value unique(key, value)'),
        ]


class UKVRel(TestModel):
    key = TextField()
    value = TextField()
    extra = TextField()

    class Meta:
        indexes = (
            (('key', 'value'), True),
        )


@requires_postgresql
class TestUpsertPostgresql(PGOnConflictTests, ModelTestCase):
    @requires_models(UKV)
    def test_conflict_target_constraint(self):
        u1 = UKV.create(key='k1', value='v1')
        u2 = UKV.create(key='k2', value='v2')

        ret = (UKV.insert(key='k1', value='v1', extra='e1')
               .on_conflict(conflict_target=(UKV.key, UKV.value),
                            preserve=(UKV.extra,))
               .execute())
        self.assertEqual(ret, u1.id)

        # Changes were saved successfully.
        u1_db = UKV.get(UKV.key == 'k1')
        self.assertEqual(u1_db.key, 'k1')
        self.assertEqual(u1_db.value, 'v1')
        self.assertEqual(u1_db.extra, 'e1')
        self.assertEqual(UKV.select().count(), 2)

        ret = (UKV.insert(key='k2', value='v2', extra='e2')
               .on_conflict(conflict_constraint='ukv_key_value',
                            preserve=(UKV.extra,))
               .execute())
        self.assertEqual(ret, u2.id)

        # Changes were saved successfully.
        u2_db = UKV.get(UKV.key == 'k2')
        self.assertEqual(u2_db.key, 'k2')
        self.assertEqual(u2_db.value, 'v2')
        self.assertEqual(u2_db.extra, 'e2')
        self.assertEqual(UKV.select().count(), 2)

        ret = (UKV.insert(key='k3', value='v3', extra='e3')
               .on_conflict(conflict_target=[UKV.key, UKV.value],
                            preserve=[UKV.extra])
               .execute())
        self.assertTrue(ret > u2_db.id)
        self.assertEqual(UKV.select().count(), 3)

    @requires_models(UKV, UKVRel)
    def test_conflict_ambiguous_column(self):
        # k1/v1/e1, k2/v2/e0, k3/v3/e1
        for i in [1, 2, 3]:
            UKV.create(key='k%s' % i, value='v%s' % i, extra='e%s' % (i % 2))

        UKVRel.create(key='k1', value='v1', extra='x1')
        UKVRel.create(key='k2', value='v2', extra='x2')

        subq = UKV.select(UKV.key, UKV.value, UKV.extra)
        query = (UKVRel
                 .insert_from(subq, [UKVRel.key, UKVRel.value, UKVRel.extra])
                 .on_conflict(conflict_target=[UKVRel.key, UKVRel.value],
                              preserve=[UKVRel.extra],
                              where=(UKVRel.key != 'k2')))
        self.assertSQL(query, (
            'INSERT INTO "ukv_rel" ("key", "value", "extra") '
            'SELECT "t1"."key", "t1"."value", "t1"."extra" FROM "ukv" AS "t1" '
            'ON CONFLICT ("key", "value") DO UPDATE '
            'SET "extra" = EXCLUDED."extra" '
            'WHERE ("ukv_rel"."key" != ?) RETURNING "ukv_rel"."id"'), ['k2'])

        query.execute()
        query = (UKVRel
                 .select(UKVRel.key, UKVRel.value, UKVRel.extra)
                 .order_by(UKVRel.key))
        self.assertEqual(list(query.tuples()), [
            ('k1', 'v1', 'e1'),
            ('k2', 'v2', 'x2'),
            ('k3', 'v3', 'e1')])


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

        with self.assertQueryCount(1):
            amount = fn.MAX(Transaction.amount).alias('amount')
            query = (Transaction
                     .select(amount, TUser.username)
                     .join(TUser)
                     .group_by(TUser.username)
                     .order_by(TUser.username))
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


@requires_postgresql
class TestSequence(ModelTestCase):
    requires = [SequenceModel]

    def test_create_table(self):
        query = SequenceModel._schema._create_table()
        self.assertSQL(query, (
            'CREATE TABLE IF NOT EXISTS "sequence_model" ('
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


@requires_postgresql
class TestUpdateFromIntegration(ModelTestCase):
    requires = [User]

    def test_update_from(self):
        u1, u2 = [User.create(username=username) for username in ('u1', 'u2')]
        data = [(u1.id, 'u1-x'), (u2.id, 'u2-x')]
        vl = ValuesList(data, columns=('id', 'username'), alias='tmp')
        (User
         .update({User.username: vl.c.username})
         .from_(vl)
         .where(User.id == vl.c.id)
         .execute())

        usernames = [u.username for u in User.select().order_by(User.username)]
        self.assertEqual(usernames, ['u1-x', 'u2-x'])

    def test_update_from_subselect(self):
        u1, u2 = [User.create(username=username) for username in ('u1', 'u2')]
        data = [(u1.id, 'u1-y'), (u2.id, 'u2-y')]
        vl = ValuesList(data, columns=('id', 'username'), alias='tmp')
        subq = vl.select(vl.c.id, vl.c.username)
        (User
         .update({User.username: subq.c.username})
         .from_(subq)
         .where(User.id == subq.c.id)
         .execute())

        usernames = [u.username for u in User.select().order_by(User.username)]
        self.assertEqual(usernames, ['u1-y', 'u2-y'])

    @requires_models(User, Tweet)
    def test_update_from_simple(self):
        u = User.create(username='u1')
        t1 = Tweet.create(user=u, content='t1')
        t2 = Tweet.create(user=u, content='t2')

        (User
         .update({User.username: Tweet.content})
         .from_(Tweet)
         .where(Tweet.content == 't2')
         .execute())

        self.assertEqual(User.get(User.id == u.id).username, 't2')


@requires_postgresql
class TestLateralJoin(ModelTestCase):
    requires = [User, Tweet]

    def test_lateral_join(self):
        with self.database.atomic():
            for i in range(3):
                u = User.create(username='u%s' % i)
                for j in range(4):
                    Tweet.create(user=u, content='u%s-t%s' % (i, j))

        # GOAL: query users and their 2 most-recent tweets (by ID).
        TA = Tweet.alias()

        # The "outer loop" will be iterating over the users whose tweets we are
        # trying to find.
        user_query = (User
                      .select(User.id, User.username)
                      .order_by(User.id)
                      .alias('uq'))

        # The inner loop will select tweets and is correlated to the outer loop
        # via the WHERE clause. Note that we are using a LIMIT clause.
        tweet_query = (TA
                       .select(TA.id, TA.content)
                       .where(TA.user == user_query.c.id)
                       .order_by(TA.id.desc())
                       .limit(2)
                       .alias('pq'))

        join = NodeList((user_query, SQL('LEFT JOIN LATERAL'), tweet_query,
                         SQL('ON %s', [True])))
        query = (Tweet
                 .select(user_query.c.username, tweet_query.c.content)
                 .from_(join)
                 .dicts())
        self.assertEqual([row for row in query], [
            {'username': 'u0', 'content': 'u0-t3'},
            {'username': 'u0', 'content': 'u0-t2'},
            {'username': 'u1', 'content': 'u1-t3'},
            {'username': 'u1', 'content': 'u1-t2'},
            {'username': 'u2', 'content': 'u2-t3'},
            {'username': 'u2', 'content': 'u2-t2'}])


class Task(TestModel):
    heading = ForeignKeyField('self', backref='tasks', null=True)
    project = ForeignKeyField('self', backref='projects', null=True)
    title = TextField()
    type = IntegerField()

    PROJECT = 1
    HEADING = 2


class TestMultiSelfJoin(ModelTestCase):
    requires = [Task]

    def setUp(self):
        super(TestMultiSelfJoin, self).setUp()

        with self.database.atomic():
            p_dev = Task.create(title='dev', type=Task.PROJECT)
            p_p = Task.create(title='peewee', project=p_dev, type=Task.PROJECT)
            p_h = Task.create(title='huey', project=p_dev, type=Task.PROJECT)

            heading_data = (
                ('peewee-1', p_p, 2),
                ('peewee-2', p_p, 0),
                ('huey-1', p_h, 1),
                ('huey-2', p_h, 1))
            for title, proj, n_subtasks in heading_data:
                t = Task.create(title=title, project=proj, type=Task.HEADING)
                for i in range(n_subtasks):
                    Task.create(title='%s-%s' % (title, i + 1), project=proj,
                                heading=t, type=Task.HEADING)

    def test_multi_self_join(self):
        Project = Task.alias()
        Heading = Task.alias()
        query = (Task
                 .select(Task, Project, Heading)
                 .join(Heading, JOIN.LEFT_OUTER,
                       on=(Task.heading == Heading.id).alias('heading'))
                 .switch(Task)
                 .join(Project, JOIN.LEFT_OUTER,
                       on=(Task.project == Project.id).alias('project'))
                 .order_by(Task.id))

        with self.assertQueryCount(1):
            accum = []
            for task in query:
                h_title = task.heading.title if task.heading else None
                p_title = task.project.title if task.project else None
                accum.append((task.title, h_title, p_title))

        self.assertEqual(accum, [
            # title - heading - project
            ('dev', None, None),
            ('peewee', None, 'dev'),
            ('huey', None, 'dev'),
            ('peewee-1', None, 'peewee'),
            ('peewee-1-1', 'peewee-1', 'peewee'),
            ('peewee-1-2', 'peewee-1', 'peewee'),
            ('peewee-2', None, 'peewee'),
            ('huey-1', None, 'huey'),
            ('huey-1-1', 'huey-1', 'huey'),
            ('huey-2', None, 'huey'),
            ('huey-2-1', 'huey-2', 'huey'),
        ])


class Product(TestModel):
    name = TextField()
    price = IntegerField()
    flags = IntegerField(constraints=[SQL('DEFAULT 99')])
    status = CharField(constraints=[Check("status IN ('a', 'b', 'c')")])

    class Meta:
        constraints = [Check('price > 0')]


class TestModelConstraints(ModelTestCase):
    requires = [Product]

    @skip_if(IS_MYSQL)  # MySQL fails intermittently on Travis-CI (?).
    def test_model_constraints(self):
        p = Product.create(name='p1', price=1, status='a')
        self.assertTrue(p.flags is None)

        # Price was saved successfully, flags got server-side default value.
        p_db = Product.get(Product.id == p.id)
        self.assertEqual(p_db.price, 1)
        self.assertEqual(p_db.flags, 99)
        self.assertEqual(p_db.status, 'a')

        # Cannot update price with invalid value, must be > 0.
        with self.database.atomic():
            p.price = -1
            self.assertRaises(IntegrityError, p.save)

        # Nor can we create a new product with an invalid price.
        with self.database.atomic():
            self.assertRaises(IntegrityError, Product.create, name='p2',
                              price=0, status='a')

        # Cannot set status to a value other than 1, 2 or 3.
        with self.database.atomic():
            p.price = 1
            p.status = 'd'
            self.assertRaises(IntegrityError, p.save)

        # Cannot create a new product with invalid status.
        with self.database.atomic():
            self.assertRaises(IntegrityError, Product.create, name='p3',
                              price=1, status='x')


class TestModelFieldReprs(BaseTestCase):
    def test_model_reprs(self):
        class User(Model):
            username = TextField(primary_key=True)
        class Tweet(Model):
            user = ForeignKeyField(User, backref='tweets')
            content = TextField()
            timestamp = TimestampField()
        class EAV(Model):
            entity = TextField()
            attribute = TextField()
            value = TextField()
            class Meta:
                primary_key = CompositeKey('entity', 'attribute')
        class NoPK(Model):
            key = TextField()
            class Meta:
                primary_key = False

        self.assertEqual(repr(User), '<Model: User>')
        self.assertEqual(repr(Tweet), '<Model: Tweet>')
        self.assertEqual(repr(EAV), '<Model: EAV>')
        self.assertEqual(repr(NoPK), '<Model: NoPK>')

        self.assertEqual(repr(User()), '<User: None>')
        self.assertEqual(repr(Tweet()), '<Tweet: None>')
        self.assertEqual(repr(EAV()), '<EAV: (None, None)>')
        self.assertEqual(repr(NoPK()), '<NoPK: n/a>')

        self.assertEqual(repr(User(username='huey')), '<User: huey>')
        self.assertEqual(repr(Tweet(id=1337)), '<Tweet: 1337>')
        self.assertEqual(repr(EAV(entity='e', attribute='a')),
                         "<EAV: ('e', 'a')>")
        self.assertEqual(repr(NoPK(key='k')), '<NoPK: n/a>')

        self.assertEqual(repr(User.username), '<TextField: User.username>')
        self.assertEqual(repr(Tweet.user), '<ForeignKeyField: Tweet.user>')
        self.assertEqual(repr(EAV.entity), '<TextField: EAV.entity>')

        self.assertEqual(repr(TextField()), '<TextField: (unbound)>')

    def test_model_str_method(self):
        class User(Model):
            username = TextField(primary_key=True)

            def __str__(self):
                return self.username.title()

        u = User(username='charlie')
        self.assertEqual(repr(u), '<User: Charlie>')


class TestGetWithSecondDatabase(ModelTestCase):
    database = get_in_memory_db()
    requires = [User]

    def test_get_with_second_database(self):
        User.create(username='huey')
        query = User.select().where(User.username == 'huey')
        self.assertEqual(query.get().username, 'huey')

        alt_db = get_in_memory_db()
        with User.bind_ctx(alt_db):
            User.create_table()

        self.assertRaises(User.DoesNotExist, query.get, alt_db)
        with User.bind_ctx(alt_db):
            User.create(username='zaizee')

        query = User.select().where(User.username == 'zaizee')
        self.assertRaises(User.DoesNotExist, query.get)
        self.assertEqual(query.get(alt_db).username, 'zaizee')


class TestMixModelsTables(ModelTestCase):
    database = get_in_memory_db()
    requires = [User]

    def test_mix_models_tables(self):
        Tbl = User._meta.table
        self.assertEqual(Tbl.insert({Tbl.username: 'huey'}).execute(), 1)

        huey = Tbl.select(User.username).get()
        self.assertEqual(huey, {'username': 'huey'})

        huey = User.select(Tbl.username).get()
        self.assertEqual(huey.username, 'huey')

        Tbl.update(username='huey-x').where(Tbl.username == 'huey').execute()
        self.assertEqual(User.select().get().username, 'huey-x')

        Tbl.delete().where(User.username == 'huey-x').execute()
        self.assertEqual(Tbl.select().count(), 0)


class TestDatabaseExecuteQuery(ModelTestCase):
    database = get_in_memory_db()
    requires = [User]

    def test_execute_query(self):
        for username in ('huey', 'zaizee'):
            User.create(username=username)

        query = User.select().order_by(User.username.desc())
        cursor = self.database.execute(query)
        self.assertEqual([row[1] for row in cursor], ['zaizee', 'huey'])


class Datum(TestModel):
    key = TextField()
    value = IntegerField(null=True)

class TestNullOrdering(ModelTestCase):
    requires = [Datum]

    def test_null_ordering(self):
        values = [('k1', 1), ('ka', None), ('k2', 2), ('kb', None)]
        Datum.insert_many(values, fields=[Datum.key, Datum.value]).execute()

        def assertOrder(ordering, expected):
            query = Datum.select().order_by(*ordering)
            self.assertEqual([d.key for d in query], expected)

        # Ascending order.
        nulls_last = (Datum.value.asc(nulls='last'), Datum.key)
        assertOrder(nulls_last, ['k1', 'k2', 'ka', 'kb'])

        nulls_first = (Datum.value.asc(nulls='first'), Datum.key)
        assertOrder(nulls_first, ['ka', 'kb', 'k1', 'k2'])

        # Descending order.
        nulls_last = (Datum.value.desc(nulls='last'), Datum.key)
        assertOrder(nulls_last, ['k2', 'k1', 'ka', 'kb'])

        nulls_first = (Datum.value.desc(nulls='first'), Datum.key)
        assertOrder(nulls_first, ['ka', 'kb', 'k2', 'k1'])

        # Invalid values.
        self.assertRaises(ValueError, Datum.value.desc, nulls='bar')
        self.assertRaises(ValueError, Datum.value.asc, nulls='foo')


class Student(TestModel):
    name = TextField()

class Course(TestModel):
    name = TextField()

class Attendance(TestModel):
    student = ForeignKeyField(Student)
    course = ForeignKeyField(Course)


class TestManyToManyJoining(ModelTestCase):
    requires = [Student, Course, Attendance]

    def setUp(self):
        super(TestManyToManyJoining, self).setUp()

        data = (
            ('charlie', ('eng101', 'cs101', 'cs111')),
            ('huey', ('cats1', 'cats2', 'cats3')),
            ('zaizee', ('cats2', 'cats3')))
        c = {}
        with self.database.atomic():
            for name, courses in data:
                student = Student.create(name=name)
                for course in courses:
                    if course not in c:
                        c[course] = Course.create(name=course)
                    Attendance.create(student=student, course=c[course])

    def assertQuery(self, query):
        with self.assertQueryCount(1):
            query = query.order_by(Attendance.id)
            results = [(a.student.name, a.course.name) for a in query]
            self.assertEqual(results, [
                ('charlie', 'eng101'),
                ('charlie', 'cs101'),
                ('charlie', 'cs111'),
                ('huey', 'cats1'),
                ('huey', 'cats2'),
                ('zaizee', 'cats2')])

    def test_join_subquery(self):
        courses = (Course
                   .select(Course.id, Course.name)
                   .order_by(Course.id)
                   .limit(5))
        query = (Attendance
                 .select(Attendance, Student, courses.c.name)
                 .join_from(Attendance, Student)
                 .join_from(Attendance, courses,
                            on=(Attendance.course == courses.c.id)))
        self.assertQuery(query)

    @skip_if(IS_MYSQL)
    def test_join_where_subquery(self):
        courses = Course.select().order_by(Course.id).limit(5)
        query = (Attendance
                 .select(Attendance, Student, Course)
                 .join_from(Attendance, Student)
                 .join_from(Attendance, Course)
                 .where(Attendance.course.in_(courses)))
        self.assertQuery(query)
