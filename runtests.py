#!/usr/bin/env python
import optparse
import os
import shutil
import sys
import unittest


def collect():
    import tests
    runtests(tests, 1)

def runtests(suite, verbosity):
    results = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return results.failures, results.errors

def get_option_parser():
    parser = optparse.OptionParser()
    basic = optparse.OptionGroup(parser, 'Basic test options')
    basic.add_option(
        '-e',
        '--engine',
        dest='engine',
        help=('Database engine to test, one of '
              '[sqlite, postgres, mysql, apsw, sqlcipher, berkeleydb]'))
    basic.add_option('-v', '--verbosity', dest='verbosity', default=1, type='int', help='Verbosity of output')

    suite = optparse.OptionGroup(parser, 'Simple test suite options')
    suite.add_option('-a', '--all', dest='all', default=False, action='store_true', help='Run all tests, including extras')
    suite.add_option('-x', '--extra', dest='extra', default=False, action='store_true', help='Run only extras tests')

    cases = optparse.OptionGroup(parser, 'Individual test module options')
    cases.add_option('--apsw', dest='apsw', default=False, action='store_true', help='apsw tests (requires apsw)')
    cases.add_option('--berkeleydb', dest='berkeleydb', default=False, action='store_true', help='berkeleydb tests (requires pysqlite compiled against berkeleydb)')
    cases.add_option('--csv', dest='csv', default=False, action='store_true', help='csv tests')
    cases.add_option('--dataset', dest='dataset', default=False, action='store_true', help='dataset tests')
    cases.add_option('--db-url', dest='db_url', default=False, action='store_true', help='db url tests')
    cases.add_option('--djpeewee', dest='djpeewee', default=False, action='store_true', help='djpeewee tests')
    cases.add_option('--fields', dest='fields', default=False, action='store_true', help='extra field tests')
    cases.add_option('--flask', dest='flask', default=False, action='store_true', help='flask utils tests')
    cases.add_option('--gfk', dest='gfk', default=False, action='store_true', help='gfk tests')
    cases.add_option('--hybrid', dest='hybrid', default=False, action='store_true', help='hybrid property/method tests')
    cases.add_option('--kv', dest='kv', default=False, action='store_true', help='key/value store tests')
    cases.add_option('--manytomany', dest='manytomany', default=False, action='store_true', help='manytomany field tests')
    cases.add_option('--migrations', dest='migrations', default=False, action='store_true', help='migration helper tests (requires psycopg2)')
    cases.add_option('--pool', dest='pool', default=False, action='store_true', help='connection pool tests')
    cases.add_option('--postgres-ext', dest='postgres_ext', default=False, action='store_true', help='postgres_ext tests (requires psycopg2)')
    cases.add_option('--pwiz', dest='pwiz', default=False, action='store_true', help='pwiz, model code generator')
    cases.add_option('--read-slave', dest='read_slave', default=False, action='store_true', help='read_slave tests')
    cases.add_option('--reflection', dest='reflection', default=False, action='store_true', help='reflection schema introspector')
    cases.add_option('--signals', dest='signals', default=False, action='store_true', help='signals tests')
    cases.add_option('--shortcuts', dest='shortcuts', default=False, action='store_true', help='shortcuts tests')
    cases.add_option('--speedups', dest='speedups', default=False, action='store_true', help='speedups c extension tests')
    cases.add_option('--sqlcipher-ext', dest='sqlcipher', default=False, action='store_true', help='sqlcipher_ext tests (requires pysqlcipher)')
    cases.add_option('--sqliteq', dest='sqliteq', default=False, action='store_true', help='sqliteq tests')
    cases.add_option('--sqlite-c-ext', dest='sqlite_c', default=False, action='store_true', help='sqlite c extension tests')
    cases.add_option('--sqlite-ext', dest='sqlite_ext', default=False, action='store_true', help='sqlite_ext tests')
    cases.add_option('--sqlite-udf', dest='sqlite_udf', default=False, action='store_true', help='sqlite_udf tests')
    cases.add_option('--test-utils', dest='test_utils', default=False, action='store_true', help='test_utils tests')

    parser.add_option_group(basic)
    parser.add_option_group(suite)
    parser.add_option_group(cases)
    return parser

def collect_modules(options):
    modules = []
    xtra = lambda op: op or options.extra or options.all
    if xtra(options.apsw):
        try:
            from playhouse.tests import test_apsw
            modules.append(test_apsw)
        except ImportError:
            print_('Unable to import apsw tests, skipping')
    if xtra(options.berkeleydb):
        try:
            from playhouse.tests import test_berkeleydb
            modules.append(test_berkeleydb)
        except ImportError:
            print_('Unable to import berkeleydb tests, skipping')
    if xtra(options.csv):
        from playhouse.tests import test_csv_utils
        modules.append(test_csv_utils)
    if xtra(options.dataset):
        from playhouse.tests import test_dataset
        modules.append(test_dataset)
    if xtra(options.db_url):
        from playhouse.tests import test_db_url
        modules.append(test_db_url)
    if xtra(options.djpeewee):
        from playhouse.tests import test_djpeewee
        modules.append(test_djpeewee)
    if xtra(options.fields):
        from playhouse.tests import test_extra_fields
        from playhouse.tests import test_manytomany
        modules.append(test_extra_fields)
        if test_manytomany not in modules:
            modules.append(test_manytomany)
    if xtra(options.flask):
        try:
            import flask
        except ImportError:
            print_('Unable to import Flask tests, Flask is not installed.')
        else:
            from playhouse.tests import test_flask_utils
            modules.append(test_flask_utils)
    if xtra(options.gfk):
        from playhouse.tests import test_gfk
        modules.append(test_gfk)
    if xtra(options.hybrid):
        from playhouse.tests import test_hybrid
        modules.append(test_hybrid)
    if xtra(options.kv):
        from playhouse.tests import test_kv
        modules.append(test_kv)
    if xtra(options.manytomany):
        from playhouse.tests import test_manytomany
        if test_manytomany not in modules:
            modules.append(test_manytomany)
    if xtra(options.migrations):
        try:
            from playhouse.tests import test_migrate
            modules.append(test_migrate)
        except ImportError:
            print_('Unable to import migration tests, skipping')
    if xtra(options.pool):
        try:
            from playhouse.tests import test_pool
            modules.append(test_pool)
        except ImportError:
            print_('Unable to import connection pool tests, skipping')
    if xtra(options.postgres_ext):
        try:
            from playhouse.tests import test_postgres
            modules.append(test_postgres)
        except ImportError:
            print_('Unable to import postgres-ext tests, skipping')
    if xtra(options.pwiz):
        from playhouse.tests import test_pwiz
        modules.append(test_pwiz)
    if xtra(options.read_slave):
        from playhouse.tests import test_read_slave
        modules.append(test_read_slave)
    if xtra(options.reflection):
        from playhouse.tests import test_reflection
        modules.append(test_reflection)
    if xtra(options.signals):
        from playhouse.tests import test_signals
        modules.append(test_signals)
    if xtra(options.shortcuts):
        from playhouse.tests import test_shortcuts
        modules.append(test_shortcuts)
    if xtra(options.speedups):
        try:
            from playhouse.tests import test_speedups
            modules.append(test_speedups)
        except ImportError:
            print_('Unable to import speedups tests, skipping')
    if xtra(options.sqlcipher):
        try:
            from playhouse.tests import test_sqlcipher_ext
            modules.append(test_sqlcipher_ext)
        except ImportError:
            print_('Unable to import pysqlcipher tests, skipping')
    if xtra(options.sqliteq):
        from playhouse.tests import test_sqliteq
        modules.append(test_sqliteq)
    if xtra(options.sqlite_c):
        try:
            from playhouse.tests import test_sqlite_c_ext
            modules.append(test_sqlite_c_ext)
        except ImportError:
            print_('Unable to import SQLite C extension tests, skipping')
    if xtra(options.sqlite_ext):
        from playhouse.tests import test_sqlite_ext
        modules.append(test_sqlite_ext)
    if xtra(options.sqlite_udf):
        from playhouse.tests import test_sqlite_udf
        modules.append(test_sqlite_udf)
    if xtra(options.test_utils):
        from playhouse.tests import test_test_utils
        modules.append(test_test_utils)

    if not modules or options.all:
        import tests
        modules.insert(0, tests)
    return modules

if __name__ == '__main__':
    parser = get_option_parser()
    options, args = parser.parse_args()

    if options.engine:
        os.environ['PEEWEE_TEST_BACKEND'] = options.engine
    os.environ['PEEWEE_TEST_VERBOSITY'] = str(options.verbosity)

    from peewee import print_

    suite = unittest.TestSuite()
    for module in collect_modules(options):
        print_('Adding tests for "%s"' % module.__name__)
        module_suite = unittest.TestLoader().loadTestsFromModule(module)
        suite.addTest(module_suite)

    failures, errors = runtests(suite, options.verbosity)

    files_to_delete = [
        'peewee_test.db',
        'peewee_test',
        'tmp.db',
        'peewee_test.bdb.db',
        'peewee_test.cipher.db']
    paths_to_delete = ['peewee_test.bdb.db-journal']
    for filename in files_to_delete:
        if os.path.exists(filename):
            os.unlink(filename)
    for path in paths_to_delete:
        if os.path.exists(path):
            shutil.rmtree(path)

    if errors:
        sys.exit(2)
    elif failures:
        sys.exit(1)

    sys.exit(0)
