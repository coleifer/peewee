import os
import sys
import threading
import time
import unittest
from functools import partial

try:
    import gevent
    from gevent.event import Event as GreenEvent
except ImportError:
    gevent = None

from peewee import *
from playhouse.sqliteq import ResultTimeout
from playhouse.sqliteq import SqliteQueueDatabase
from playhouse.sqliteq import WriterPaused

from .base import BaseTestCase
from .base import TestModel
from .base import db_loader
from .base import skip_case_if


get_db = partial(db_loader, 'sqlite', db_class=SqliteQueueDatabase)
db = db_loader('sqlite')


class User(TestModel):
    name = TextField(unique=True)

    class Meta:
        table_name = 'threaded_db_test_user'


class BaseTestQueueDatabase(object):
    database_config = {}
    n_rows = 20
    n_threads = 20

    def setUp(self):
        super(BaseTestQueueDatabase, self).setUp()
        User._meta.database = db
        with db:
            db.create_tables([User], safe=True)

        User._meta.database = \
                self.database = get_db(**self.database_config)

        # Sanity check at startup.
        self.assertEqual(self.database.queue_size(), 0)

    def tearDown(self):
        super(BaseTestQueueDatabase, self).tearDown()
        User._meta.database = db
        with db:
            User.drop_table()
        if not self.database.is_closed():
            self.database.close()
        if not db.is_closed():
            db.close()
        filename = db.database
        if os.path.exists(filename):
            os.unlink(filename)

    def test_query_error(self):
        self.database.start()
        curs = self.database.execute_sql('foo bar baz')
        self.assertRaises(OperationalError, curs.fetchone)
        self.database.stop()

    def test_integrity_error(self):
        self.database.start()
        u = User.create(name='u')
        self.assertRaises(IntegrityError, User.create, name='u')

    def test_query_execution(self):
        qr = User.select().execute()
        self.assertEqual(self.database.queue_size(), 0)

        self.database.start()

        users = list(qr)
        huey = User.create(name='huey')
        mickey = User.create(name='mickey')

        self.assertTrue(huey.id is not None)
        self.assertTrue(mickey.id is not None)
        self.assertEqual(self.database.queue_size(), 0)

        self.database.stop()

    def create_thread(self, fn, *args):
        raise NotImplementedError

    def create_event(self):
        raise NotImplementedError

    def test_multiple_threads(self):
        def create_rows(idx, nrows):
            for i in range(idx, idx + nrows):
                User.create(name='u-%s' % i)

        total = self.n_threads * self.n_rows
        self.database.start()
        threads = [self.create_thread(create_rows, i, self.n_rows)
                   for i in range(0, total, self.n_rows)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(User.select().count(), total)
        self.database.stop()

    def test_pause(self):
        event_a = self.create_event()
        event_b = self.create_event()

        def create_user(name, event, expect_paused):
            event.wait()
            if expect_paused:
                self.assertRaises(WriterPaused, lambda: User.create(name=name))
            else:
                User.create(name=name)

        self.database.start()

        t_a = self.create_thread(create_user, 'a', event_a, True)
        t_a.start()
        t_b = self.create_thread(create_user, 'b', event_b, False)
        t_b.start()

        User.create(name='c')
        self.assertEqual(User.select().count(), 1)

        # Pause operations but preserve the writer thread/connection.
        self.database.pause()

        event_a.set()
        self.assertEqual(User.select().count(), 1)
        t_a.join()

        self.database.unpause()
        self.assertEqual(User.select().count(), 1)

        event_b.set()
        t_b.join()
        self.assertEqual(User.select().count(), 2)

        self.database.stop()

    def test_restart(self):
        self.database.start()
        User.create(name='a')
        self.database.stop()
        self.database._results_timeout = 0.0001

        self.assertRaises(ResultTimeout, User.create, name='b')
        self.assertEqual(User.select().count(), 1)

        self.database.start()  # Will execute the pending "b" INSERT.
        self.database._results_timeout = None

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

        self.database.start()
        [t.join() for t in threads]
        self.database.stop()

        self.assertEqual(sorted(D), ['charlie', 'huey', 'users', 'zaizee'])

    def test_next_method(self):
        self.database.start()

        User.create(name='mickey')
        User.create(name='huey')
        query = iter(User.select().order_by(User.name))
        self.assertEqual(next(query).name, 'huey')
        self.assertEqual(next(query).name, 'mickey')
        self.assertRaises(StopIteration, lambda: next(query))

        self.assertEqual(
            next(self.database.execute_sql('PRAGMA journal_mode'))[0],
            'wal')

        self.database.stop()


class TestThreadedDatabaseThreads(BaseTestQueueDatabase, BaseTestCase):
    database_config = {'use_gevent': False}

    def tearDown(self):
        self.database._results_timeout = None
        super(TestThreadedDatabaseThreads, self).tearDown()

    def create_thread(self, fn, *args):
        t = threading.Thread(target=fn, args=args)
        t.daemon = True
        return t

    def create_event(self):
        return threading.Event()

    def test_timeout(self):
        @self.database.func()
        def slow(n):
            time.sleep(n)
            return 'slept %0.2f' % n

        self.database.start()

        # Make the result timeout very small, then call our function which
        # will cause the query results to time-out.
        self.database._results_timeout = 0.001
        def do_query():
            cursor = self.database.execute_sql('select slow(?)', (0.01,),
                                               commit=True)
            self.assertEqual(cursor.fetchone()[0], 'slept 0.01')

        self.assertRaises(ResultTimeout, do_query)
        self.database.stop()


@skip_case_if(gevent is None)
class TestThreadedDatabaseGreenlets(BaseTestQueueDatabase, BaseTestCase):
    database_config = {'use_gevent': True}
    n_rows = 10
    n_threads = 40

    def create_thread(self, fn, *args):
        return gevent.Greenlet(fn, *args)

    def create_event(self):
        return GreenEvent()
