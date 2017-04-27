#!/usr/bin/env python
import importlib
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
    #cases.add_option('--apsw', dest='apsw', default=False, action='store_true', help='apsw tests (requires apsw)')
    #cases.add_option('--berkeleydb', dest='berkeleydb', default=False, action='store_true', help='berkeleydb tests (requires pysqlite compiled against berkeleydb)')
    cases.add_option('--db-url', dest='db_url', default=False, action='store_true', help='db url tests')
    cases.add_option('--hybrid', dest='hybrid', default=False, action='store_true', help='hybrid property/method tests')
    cases.add_option('--migrations', dest='migrations', default=False, action='store_true', help='migration helper tests (requires psycopg2)')
    cases.add_option('--pool', dest='pool', default=False, action='store_true', help='connection pool tests')
    cases.add_option('--postgres-ext', dest='postgres_ext', default=False, action='store_true', help='postgres_ext tests (requires psycopg2)')
    cases.add_option('--pwiz', dest='pwiz', default=False, action='store_true', help='pwiz, model code generator')
    cases.add_option('--reflection', dest='reflection', default=False, action='store_true', help='reflection schema introspector')
    cases.add_option('--signals', dest='signals', default=False, action='store_true', help='signals tests')
    cases.add_option('--shortcuts', dest='shortcuts', default=False, action='store_true', help='shortcuts tests')
    #cases.add_option('--speedups', dest='speedups', default=False, action='store_true', help='speedups c extension tests')
    #cases.add_option('--sqlcipher-ext', dest='sqlcipher', default=False, action='store_true', help='sqlcipher_ext tests (requires pysqlcipher)')
    #cases.add_option('--sqliteq', dest='sqliteq', default=False, action='store_true', help='sqliteq tests')
    #cases.add_option('--sqlite-c-ext', dest='sqlite_c', default=False, action='store_true', help='sqlite c extension tests')
    cases.add_option('--sqlite-ext', dest='sqlite_ext', default=False, action='store_true', help='sqlite_ext tests')
    #cases.add_option('--sqlite-udf', dest='sqlite_udf', default=False, action='store_true', help='sqlite_udf tests')

    parser.add_option_group(basic)
    parser.add_option_group(suite)
    parser.add_option_group(cases)
    return parser

def collect_modules(options, args):
    modules = []
    xtra = lambda op: op or options.extra or options.all

    for arg in args:
        try:
            modules.append(importlib.import_module('tests.%s' % arg))
        except ImportError:
            print_('ERROR: unable to import requested tests: "tests.%s"' % arg)

    #if xtra(options.apsw):
    #    try:
    #        from playhouse.tests import test_apsw
    #        modules.append(test_apsw)
    #    except ImportError:
    #        print_('Unable to import apsw tests, skipping')
    #if xtra(options.berkeleydb):
    #    try:
    #        from playhouse.tests import test_berkeleydb
    #        modules.append(test_berkeleydb)
    #    except ImportError:
    #        print_('Unable to import berkeleydb tests, skipping')
    if xtra(options.db_url):
        import tests.db_url
        modules.append(tests.db_url)
    if xtra(options.hybrid):
        import tests.hybrid
        modules.append(tests.hybrid)
    if xtra(options.migrations):
        import tests.migrations
        modules.append(tests.migrations)
    if xtra(options.pool):
        import tests.pool
        modules.append(tests.pool)
    if xtra(options.postgres_ext):
        try:
            import tests.postgres
            modules.append(tests.postgres)
        except ImportError:
            print_('Unable to import postgres-ext tests, skipping')
    if xtra(options.pwiz):
        import tests.pwiz_integration
        modules.append(tests.pwiz_integration)
    if xtra(options.reflection):
        import tests.reflection
        modules.append(tests.reflection)
    if xtra(options.signals):
        import tests.signals
        modules.append(tests.signals)
    if xtra(options.shortcuts):
        import tests.shortcuts
        modules.append(tests.shortcuts)
    #if xtra(options.speedups):
    #    try:
    #        import tests.speedups
    #        modules.append(tests.speedups)
    #    except ImportError:
    #        print_('Unable to import speedups tests, skipping')
    #if xtra(options.sqlcipher):
    #    try:
    #        from playhouse.tests import test_sqlcipher_ext
    #        modules.append(test_sqlcipher_ext)
    #    except ImportError:
    #        print_('Unable to import pysqlcipher tests, skipping')
    #if xtra(options.sqliteq):
    #    from playhouse.tests import test_sqliteq
    #    modules.append(test_sqliteq)
    #if xtra(options.sqlite_c):
    #    try:
    #        from playhouse.tests import test_sqlite_c_ext
    #        modules.append(test_sqlite_c_ext)
    #    except ImportError:
    #        print_('Unable to import SQLite C extension tests, skipping')
    if xtra(options.sqlite_ext):
        import tests.sqlite
        modules.append(tests.sqlite)
    #if xtra(options.sqlite_udf):
    #    from playhouse.tests import test_sqlite_udf
    #    modules.append(test_sqlite_udf)

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
    for module in collect_modules(options, args):
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
