import sys
import unittest

from peewee import *
from peewee import sqlite3

from .base import db
from .base import get_in_memory_db
from .base import new_connection
from .base import requires_models
from .base import skip_case_unless
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
        self.assertEqual(ac.counter, 3)  # One extra when fetched from db.
        self.assertEqual(ac.control, 1)

        AutoCounter._meta.only_save_dirty = False

        ac = AutoCounter()
        self.assertEqual(ac.counter, 4)
        self.assertEqual(ac.control, 1)
        ac.save()

        ac_db = AutoCounter.get(AutoCounter.id == ac.id)
        self.assertEqual(ac_db.counter, 4)


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
        query = query.join(TA, on=TA.user_id)
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


@skip_case_unless(isinstance(db, PostgresqlDatabase))
class TestReturningIntegration(ModelTestCase):
    requires = [User]

    def test_simple_returning(self):
        query = User.insert(username='charlie')
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") VALUES (?) RETURNING "id"'),
            ['charlie'])

        self.assertEqual(query.execute(), 1)

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
