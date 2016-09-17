from functools import partial
import sys
import threading
import unittest

try:
    import gevent
except ImportError:
    gevent = None

from peewee import *
from playhouse.sqliteq import SqliteQueueDatabase
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

    def setUp(self):
        super(BaseTestQueueDatabase, self).setUp()
        with db.execution_context():
            User.create_table(True)
        User._meta.database = \
                self.db = get_db(**self.database_config)

        # Sanity check at startup.
        self.assertEqual(self.db.queue_size(), (0, 0))

    def tearDown(self):
        super(BaseTestQueueDatabase, self).tearDown()
        User._meta.database = db
        with db.execution_context():
            User.drop_table()

    def test_query_execution(self):
        qr = User.select().execute()
        self.assertEqual(self.db.queue_size(), (0, 1))

        self.db.start()
        self.assertEqual(list(qr), [])
        self.assertEqual(self.db.queue_size(), (0, 0))
        self.db.stop()


class TestThreadedDatabaseThreads(BaseTestQueueDatabase, PeeweeTestCase):
    database_config = {'use_gevent': False}


@skip_if(lambda: gevent is None)
class TestThreadedDatabaseGreenlets(BaseTestQueueDatabase, PeeweeTestCase):
    database_config = {'use_gevent': True}


if __name__ == '__main__':
    unittest.main(argv=sys.argv)
