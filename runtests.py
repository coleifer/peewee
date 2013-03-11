#!/usr/bin/env python
import optparse
import os
import sys
import unittest

def collect():
    import tests
    runtests(tests, 1)

def runtests(module, verbosity):
    suite = unittest.TestLoader().loadTestsFromModule(module)
    results = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return results.failures, results.errors

def get_option_parser():
    parser = optparse.OptionParser()
    parser.add_option('-e', '--engine', dest='engine', default='sqlite', help='Database engine to test, one of [sqlite3, postgres, mysql]')
    parser.add_option('-v', '--verbosity', dest='verbosity', default=1, type='int', help='Verbosity of output')
    parser.add_option('-a', '--all', dest='all', default=False, action='store_true', help='Run all tests, including extras')
    parser.add_option('-x', '--extra', dest='extra', default=False, action='store_true', help='Run only extras tests')
    return parser

if __name__ == '__main__':
    parser = get_option_parser()
    options, args = parser.parse_args()

    os.environ['PEEWEE_TEST_BACKEND'] = options.engine
    os.environ['PEEWEE_TEST_VERBOSITY'] = str(options.verbosity)

    import tests

    if options.all or options.extra:
        modules = [tests]
        from playhouse import tests_signals, tests_gfk, tests_migrate
        modules.append(tests_signals)
        modules.append(tests_gfk)
        modules.append(tests_migrate)

        #from playhouse import tests as extras_tests
        #modules.append(extras_tests)
        try:
            from playhouse import tests_apsw
            modules.append(tests_apsw)
        except ImportError:
            print 'Unable to import apsw tests, skipping'

        try:
            from playhouse import tests_postgres
            modules.append(tests_postgres)
        except ImportError:
            print 'Unable to import postgres_ext tests, skipping'
    else:
        modules = [tests]

    if options.extra:
        modules.remove(tests)

    results = []
    any_failures = False
    any_errors = False
    for module in modules:
        failures, errors = runtests(module, options.verbosity)
        any_failures = any_failures or bool(failures)
        any_errors = any_errors or bool(errors)

    if any_errors:
        sys.exit(2)
    elif any_failures:
        sys.exit(1)
    sys.exit(0)
