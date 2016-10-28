from functools import partial
import os
import sys
import threading
import time
import unittest

try:
    import gevent
    from gevent.event import Event as GreenEvent
except ImportError:
    gevent = None

from peewee import *
from playhouse.sqliteq import ResultTimeout
from playhouse.sqliteq import SqliteQueueDatabase
from playhouse.sqliteq import WriterPaused
from playhouse.tests.base import database_initializer
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import skip_if


get_db = partial(
    database_initializer.get_database,
    'sqlite',
    db_class=SqliteQueueDatabase)

db = database_initializer.get_database('sqlite')

class User(Model):
    name = TextField(unique=True)
    class Meta:
        database = db
        db_table = 'threaded_db_test_user'


class BaseTestQueueDatabase(object):
    database_config = {}
    n_rows = 50
    n_threads = 20

    def setUp(self):
        super(BaseTestQueueDatabase, self).setUp()
        with db.execution_context():
            User.create_table(True)
        User._meta.database = \
                self.db = get_db(**self.database_config)

        # Sanity check at startup.
        self.assertEqual(self.db.queue_size(), 0)

    def tearDown(self):
        super(BaseTestQueueDatabase, self).tearDown()
        User._meta.database = db
        with db.execution_context():
            User.drop_table()
        if not self.db.is_closed():
            self.db.close()
        if not db.is_closed():
            db.close()
        filename = db.database
        if os.path.exists(filename):
            os.unlink(filename)

    def test_query_execution(self):
        qr = User.select().execute()
        self.assertEqual(self.db.queue_size(), 0)

        self.db.start()

        users = list(qr)
        huey = User.create(name='huey')
        mickey = User.create(name='mickey')

        self.assertTrue(huey.id is not None)
        self.assertTrue(mickey.id is not None)
        self.assertEqual(self.db.queue_size(), 0)

        self.db.stop()

    def create_thread(self, fn, *args):
        raise NotImplementedError

    def create_event(self):
        raise NotImplementedError

    def test_multiple_threads(self):
        def create_rows(idx, nrows):
            for i in range(idx, idx + nrows):
                User.create(name='u-%s' % i)

        total = self.n_threads * self.n_rows
        self.db.start()
        threads = [self.create_thread(create_rows, i, self.n_rows)
                   for i in range(0, total, self.n_rows)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(User.select().count(), total)
        self.db.stop()

    def test_pause(self):
        event_a = self.create_event()
        event_b = self.create_event()

        def create_user(name, event, expect_paused):
            event.wait()
            if expect_paused:
                self.assertRaises(WriterPaused, lambda: User.create(name=name))
            else:
                User.create(name=name)

        self.db.start()

        t_a = self.create_thread(create_user, 'a', event_a, True)
        t_a.start()
        t_b = self.create_thread(create_user, 'b', event_b, False)
        t_b.start()

        User.create(name='c')
        self.assertEqual(User.select().count(), 1)

        # Pause operations but preserve the writer thread/connection.
        self.db.pause()

        event_a.set()
        self.assertEqual(User.select().count(), 1)
        t_a.join()

        self.db.unpause()
        self.assertEqual(User.select().count(), 1)

        event_b.set()
        t_b.join()
        self.assertEqual(User.select().count(), 2)

        self.db.stop()

    def test_restart(self):
        self.db.start()
        User.create(name='a')
        self.db.stop()
        self.db._results_timeout = 0.0001

        self.assertRaises(ResultTimeout, User.create, name='b')
        self.assertEqual(User.select().count(), 1)

        self.db.start()  # Will execute the pending "b" INSERT.
        self.db._results_timeout = None

        User.create(name='c')
        self.assertEqual(User.select().count(), 3)
        self.assertEqual(sorted(u.name for u in User.select()),
                         ['a', 'b', 'c'])

    def test_waiting(self):
        D = {}

        def create_user(name):
            D[name] = User.create(name=name).id

        threads = [self.create_thread(create_user, name)
                   for name in ('huey', 'charlie', 'zaizee')]
        [t.start() for t in threads]

        def get_users():
            D['users'] = [(user.id, user.name) for user in User.select()]

        tg = self.create_thread(get_users)
        tg.start()
        threads.append(tg)

        self.db.start()
        [t.join() for t in threads]
        self.db.stop()

        self.assertEqual(sorted(D), ['charlie', 'huey', 'users', 'zaizee'])

    def test_next_method(self):
        self.db.start()

        User.create(name='mickey')
        User.create(name='huey')
        query = iter(User.select().order_by(User.name))
        self.assertEqual(next(query).name, 'huey')
        self.assertEqual(next(query).name, 'mickey')
        self.assertRaises(StopIteration, lambda: next(query))

        self.assertEqual(
            next(self.db.execute_sql('PRAGMA journal_mode'))[0],
            'wal')

        self.db.stop()


class TestThreadedDatabaseThreads(BaseTestQueueDatabase, PeeweeTestCase):
    database_config = {'use_gevent': False}

    def tearDown(self):
        self.db._results_timeout = None
        super(TestThreadedDatabaseThreads, self).tearDown()

    def create_thread(self, fn, *args):
        t = threading.Thread(target=fn, args=args)
        t.daemon = True
        return t

    def create_event(self):
        return threading.Event()

    def test_timeout(self):
        @self.db.func()
        def slow(n):
            time.sleep(n)
            return 'I slept for %s seconds' % n

        self.db.start()

        # Make the result timeout very small, then call our function which
        # will cause the query results to time-out.
        self.db._results_timeout = 0.001
        self.assertRaises(
            ResultTimeout,
            lambda: self.db.execute_sql('select slow(?)', (0.005,)).fetchone())
        self.db.stop()


@skip_if(lambda: gevent is None)
class TestThreadedDatabaseGreenlets(BaseTestQueueDatabase, PeeweeTestCase):
    database_config = {'use_gevent': True}
    n_rows = 20
    n_threads = 200

    def create_thread(self, fn, *args):
        return gevent.Greenlet(fn, *args)

    def create_event(self):
        return GreenEvent()


if __name__ == '__main__':
    unittest.main(argv=sys.argv)
