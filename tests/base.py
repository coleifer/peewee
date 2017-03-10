from contextlib import contextmanager
import logging
import os
import unittest

from peewee import *


BACKEND = os.environ.get('PEEWEE_TEST_BACKEND') or 'sqlite'
if BACKEND == 'sqlite':
    db = SqliteDatabase(':memory:')
elif BACKEND == 'postgres':
    db = PostgreqlDatabase('peewee_test')
elif BACKEND == 'mysql':
    db = MySQLDatabase('peewee_test')
else:
    raise Exception('Unsupported test backend. Use one of: "sqlite", '
                    '"postgres", or "mysql".')


class TestModel(Model):
    class Meta:
        database = db


def __sql__(q):
    return Context().sql(q).query()


class QueryLogHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        self.queries = []
        logging.Handler.__init__(self, *args, **kwargs)

    def emit(self, record):
        self.queries.append(record)


logger = logging.getLogger('peewee')


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self._qh = QueryLogHandler()
        logger.setLevel(logging.DEBUG)
        logger.addHandler(self._qh)

    def tearDown(self):
        logger.removeHandler(self._qh)

    def assertIsNone(self, value):
        self.assertTrue(value is None, '%r is not None' % value)

    def assertIsNotNone(self, value):
        self.assertTrue(value is not None, '%r is None' % value)

    def assertSQL(self, query, sql, params=None):
        qsql, qparams = __sql__(query)
        self.assertEqual(qsql, sql)
        if params is not None:
            self.assertEqual(qparams, params)

    @property
    def history(self):
        return self._qh.queries

    @contextmanager
    def assertQueryCount(self, num):
        qc = len(self.history)
        yield
        self.assertEqual(len(self.history) - qc, num)


class DatabaseTestCase(BaseTestCase):
    def setUp(self):
        db.connect()
        super(DatabaseTestCase, self).setUp()

    def tearDown(self):
        super(DatabaseTestCase, self).tearDown()
        db.close()


class ModelTestCase(DatabaseTestCase):
    requires = None

    def setUp(self):
        super(ModelTestCase, self).setUp()
        if self.requires:
            db.drop_tables(self.requires, safe=True)
            db.create_tables(self.requires)

    def tearDown(self):
        if self.requires:
            db.drop_tables(self.requires, safe=True)
        super(ModelTestCase, self).tearDown()
