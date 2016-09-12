from functools import partial
import sys
import threading
import unittest

try:
    import gevent
except ImportError:
    gevent = None

from peewee import *
from playhouse.sqliteq import GreenletEnvironment
from playhouse.sqliteq import SqliteThreadDatabase
from playhouse.sqliteq import ThreadEnvironment
from playhouse.tests.base import database_initializer
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import skip_if


get_db = partial(
    database_initializer.get_database,
    'sqlite',
    db_class=SqliteThreadDatabase)

db = database_initializer.get_database('sqlite')

class User(Model):
    name = TextField(unique=True)
    class Meta:
        database = db
        db_table = 'threaded_db_test_user'


class BaseTestThreadedDatabase(object):
    environment_type = None

    def setUp(self):
        super(BaseTestThreadedDatabase, self).setUp()
        with db.execution_context():
            User.create_table(True)
        User._meta.database = \
                self.db = get_db(environment_type=self.environment_type)

        # Sanity check at startup.
        self.assertEqual(self.db.queue_size(), 0)

    def tearDown(self):
        super(BaseTestThreadedDatabase, self).tearDown()
        User._meta.database = db
        with db.execution_context():
            User.drop_table()

    def test_query_execution(self):
        qr = User.select().execute()
        self.assertEqual(self.db.queue_size(), 1)

        self.db.start_worker()
        self.assertEqual(list(qr), [])
        self.assertEqual(self.db.queue_size(), 0)
        self.db.shutdown()


class TestThreadedDatabaseThreads(BaseTestThreadedDatabase, PeeweeTestCase):
    environment_type = ThreadEnvironment


@skip_if(lambda: gevent is None)
class TestThreadedDatabaseGreenlets(BaseTestThreadedDatabase, PeeweeTestCase):
    environment_type = GreenletEnvironment


if __name__ == '__main__':
    unittest.main(argv=sys.argv)
