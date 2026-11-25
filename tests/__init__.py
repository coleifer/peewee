import sqlite3
import unittest

from peewee import ImproperlyConfigured
from peewee import NotSupportedError
from peewee import OperationalError

# Each test module is collected as its own suite, so a duplicate class
# name across modules cannot shadow another module's tests.
MODULES = []

# Core modules.
from . import db_tests
MODULES.append(db_tests)
from . import fields
MODULES.append(fields)
from . import manytomany
MODULES.append(manytomany)
from . import models
MODULES.append(models)
from . import model_sql
MODULES.append(model_sql)
from . import prefetch_tests
MODULES.append(prefetch_tests)
from . import results
MODULES.append(results)
from . import schema
MODULES.append(schema)
from . import sql
MODULES.append(sql)
from . import transactions
MODULES.append(transactions)
from . import with_related_tests
MODULES.append(with_related_tests)

# Extensions.
try:
    from . import apsw_ext
    MODULES.append(apsw_ext)
except ImportError:
    print('Unable to import APSW extension tests, skipping.')
from . import cockroachdb
MODULES.append(cockroachdb)
try:
    from . import cysqlite_ext
    MODULES.append(cysqlite_ext)
except ImportError:
    print('Unable to import cysqlite tests, skipping.')
from . import dataset
MODULES.append(dataset)
from . import db_url
MODULES.append(db_url)
from . import extra_fields
MODULES.append(extra_fields)
try:
    from . import flask_utils
    MODULES.append(flask_utils)
except ImportError:
    print('Unable to import flask tests, skipping.')
try:
    from . import fts_parser
    MODULES.append(fts_parser)
except ImportError:
    print('Unable to import fts parser tests, skipping.')
from . import hybrid
MODULES.append(hybrid)
try:
    from . import json_field
    MODULES.append(json_field)
except NotSupportedError:
    print('Unable to import json_field tests, requires sqlite >= 3.38.')
from . import kv
MODULES.append(kv)
from . import migrations
MODULES.append(migrations)
from . import mysql_ext
MODULES.append(mysql_ext)
from . import pool
MODULES.append(pool)
from . import schema_diff
MODULES.append(schema_diff)
try:
    from . import postgres
    MODULES.append(postgres)
except (ImportError, ImproperlyConfigured):
    print('Unable to import postgres extension tests, skipping.')
except OperationalError:
    print('Postgresql test database "peewee_test" not found, skipping '
          'the postgres_ext tests.')
from . import pwiz_integration
MODULES.append(pwiz_integration)
from . import reflection
MODULES.append(reflection)
from . import shortcuts
MODULES.append(shortcuts)
from . import signals
MODULES.append(signals)
try:
    from . import sqlcipher_ext
    MODULES.append(sqlcipher_ext)
except ImportError:
    print('Unable to import SQLCipher extension tests, skipping.')
try:
    from . import sqlite
    MODULES.append(sqlite)
except ImportError:
    print('Unable to import sqlite extension tests, skipping.')
if sqlite3.sqlite_version_info >= (3, 38, 0):
    try:
        from . import sqlite_changelog
        MODULES.append(sqlite_changelog)
    except (ImportError, NotSupportedError):
        print('Unable to import sqlite changelog tests, skipping.')
else:
    print('Unable to run sqlite changelog tests, requires sqlite >= 3.38.')
from . import sqliteq
MODULES.append(sqliteq)
from . import sqlite_udf
MODULES.append(sqlite_udf)
from . import test_utils
MODULES.append(test_utils)
try:
    from . import pwasyncio
    MODULES.append(pwasyncio)
except (ImportError, SyntaxError):
    print('Unable to import asyncio tests, skipping.')
try:
    from . import pydantic_utils
    MODULES.append(pydantic_utils)
except (ImportError, SyntaxError):
    print('Unable to import pydantic tests, skipping.')


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for module in MODULES:
        suite.addTests(loader.loadTestsFromModule(module))
    return suite
