#!/usr/bin/env python
import optparse
import os
import sys
import unittest


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
    from extras import tests as extras_tests

    if options.all:
        modules = [tests, extras_tests]
    elif options.extra:
        modules = [extras_tests]
    else:
        modules = [tests]

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
