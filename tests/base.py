from contextlib import contextmanager
from functools import wraps
import datetime
import logging
import os
import unittest
try:
    from unittest import mock
except ImportError:
    from .libs import mock

from peewee import *
from playhouse.mysql_ext import MySQLConnectorDatabase


logger = logging.getLogger('peewee')


def db_loader(engine, name='peewee_test', db_class=None, **params):
    if db_class is None:
        engine_aliases = {
            SqliteDatabase: ['sqlite', 'sqlite3'],
            MySQLDatabase: ['mysql'],
            PostgresqlDatabase: ['postgres', 'postgresql'],
            MySQLConnectorDatabase: ['mysqlconnector'],
        }
        engine_map = dict((alias, db) for db, aliases in engine_aliases.items()
                          for alias in aliases)
        if engine.lower() not in engine_map:
            raise Exception('Unsupported engine: %s.' % engine)
        db_class = engine_map[engine.lower()]
    if issubclass(db_class, SqliteDatabase) and not name.endswith('.db'):
        name = '%s.db' % name if name != ':memory:' else name
    elif issubclass(db_class, MySQLDatabase):
        params.update(MYSQL_PARAMS)
    elif issubclass(db_class, PostgresqlDatabase):
        params.update(PSQL_PARAMS)
    return db_class(name, **params)


def get_in_memory_db(**params):
    return db_loader('sqlite3', ':memory:', **params)


BACKEND = os.environ.get('PEEWEE_TEST_BACKEND') or 'sqlite'
VERBOSITY = int(os.environ.get('PEEWEE_TEST_VERBOSITY') or 1)

IS_SQLITE = BACKEND in ('sqlite', 'sqlite3')
IS_MYSQL = BACKEND in ('mysql', 'mysqlconnector')
IS_POSTGRESQL = BACKEND in ('postgres', 'postgresql')


def make_db_params(key):
    params = {}
    env_vars = [(part, 'PEEWEE_%s_%s' % (key, part.upper()))
                for part in ('host', 'port', 'user', 'password')]
    for param, env_var in env_vars:
        value = os.environ.get(env_var)
        if value:
            params[param] = int(value) if param == 'port' else value
    return params

MYSQL_PARAMS = make_db_params('MYSQL')
PSQL_PARAMS = make_db_params('PSQL')

if VERBOSITY > 1:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
if VERBOSITY > 2:
    handler.setLevel(logging.DEBUG)


def new_connection():
    return db_loader(BACKEND, 'peewee_test')


db = new_connection()


class TestModel(Model):
    class Meta:
        database = db


def __sql__(q, **state):
    return Context(**state).sql(q).query()


class QueryLogHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        self.queries = []
        logging.Handler.__init__(self, *args, **kwargs)

    def emit(self, record):
        self.queries.append(record)


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

    @contextmanager
    def assertRaisesCtx(self, exceptions):
        try:
            yield
        except Exception as exc:
            if not isinstance(exc, exceptions):
                raise AssertionError('Got %s, expected %s' % (exc, exceptions))
        else:
            raise AssertionError('No exception was raised.')

    def assertSQL(self, query, sql, params=None, **state):
        database = getattr(self, 'database', None) or db
        state.setdefault('conflict_statement', database.conflict_statement)
        state.setdefault('conflict_update', database.conflict_update)
        qsql, qparams = __sql__(query, **state)
        self.assertEqual(qsql, sql)
        if params is not None:
            self.assertEqual(qparams, params)

    @property
    def history(self):
        return self._qh.queries

    def reset_sql_history(self):
        self._qh.queries = []

    @contextmanager
    def assertQueryCount(self, num):
        qc = len(self.history)
        yield
        self.assertEqual(len(self.history) - qc, num)


class DatabaseTestCase(BaseTestCase):
    database = db

    def setUp(self):
        if not self.database.is_closed():
            self.database.close()
        self.database.connect()
        super(DatabaseTestCase, self).setUp()

    def tearDown(self):
        super(DatabaseTestCase, self).tearDown()
        self.database.close()

    def execute(self, sql, params=None):
        return self.database.execute_sql(sql, params)


class ModelDatabaseTestCase(DatabaseTestCase):
    database = db
    requires = None

    def setUp(self):
        super(ModelDatabaseTestCase, self).setUp()
        self._db_mapping = {}
        # Override the model's database object with test db.
        if self.requires:
            for model in self.requires:
                self._db_mapping[model] = model._meta.database
                model._meta.set_database(self.database)

    def tearDown(self):
        # Restore the model's previous database object.
        if self.requires:
            for model in self.requires:
                model._meta.set_database(self._db_mapping[model])

        super(ModelDatabaseTestCase, self).tearDown()


class ModelTestCase(ModelDatabaseTestCase):
    database = db
    requires = None

    def setUp(self):
        super(ModelTestCase, self).setUp()
        if self.requires:
            self.database.drop_tables(self.requires, safe=True)
            self.database.create_tables(self.requires)

    def tearDown(self):
        # Restore the model's previous database object.
        try:
            if self.requires:
                self.database.drop_tables(self.requires, safe=True)
        finally:
            super(ModelTestCase, self).tearDown()


def requires_models(*models):
    def decorator(method):
        @wraps(method)
        def inner(self):
            _db_mapping = {}
            for model in models:
                _db_mapping[model] = model._meta.database
                model._meta.set_database(self.database)
            self.database.drop_tables(models, safe=True)
            self.database.create_tables(models)

            try:
                method(self)
            finally:
                try:
                    self.database.drop_tables(models)
                except:
                    pass
                for model in models:
                    model._meta.set_database(_db_mapping[model])
        return inner
    return decorator


def skip_if(expr):
    def decorator(method):
        @wraps(method)
        def inner(self):
            should_skip = expr() if callable(expr) else expr
            if not should_skip:
                return method(self)
            elif VERBOSITY > 1:
                print('Skipping %s test.' % method.__name__)
        return inner
    return decorator


def skip_unless(expr):
    return skip_if((lambda: not expr()) if callable(expr) else not expr)


def skip_case_if(expr):
    def decorator(klass):
        should_skip = expr() if callable(expr) else expr
        if not should_skip:
            return klass
        elif VERBOSITY > 1:
            print('Skipping %s test.' % klass.__name__)
            class Dummy(object): pass
            return Dummy
    return decorator


def skip_case_unless(expr):
    return skip_case_if((lambda: not expr()) if callable(expr) else not expr)
