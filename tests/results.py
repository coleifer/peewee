from peewee import *

from .base import get_in_memory_db
from .base import ModelTestCase
from .base_models import *


def lange(x, y=None):
    if y is None:
        value = range(x)
    else:
        value = range(x, y)
    return list(value)


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


class TestModelObjectCursorWrapper(ModelTestCase):
    database = get_in_memory_db()
    requires = [User, Tweet]

    def test_model_objects(self):
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
