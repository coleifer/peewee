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
    usage = 'usage: %prog [-e engine_name, other options] module1, module2 ...'
    parser = optparse.OptionParser(usage=usage)
    basic = optparse.OptionGroup(parser, 'Basic test options')
    basic.add_option(
        '-e',
        '--engine',
        dest='engine',
        help=('Database engine to test, one of '
              '[sqlite, postgres, mysql, apsw, sqlcipher]'))
    basic.add_option('-v', '--verbosity', dest='verbosity', default=1, type='int', help='Verbosity of output')

    parser.add_option_group(basic)
    return parser

def collect_modules(options, args):
    modules = []
    from peewee import print_

    for arg in args:
        try:
            __import__('tests.%s' % arg)
            modules.append(sys.modules['tests.%s' % arg])
        except ImportError:
            print_('ERROR: unable to import requested tests: "tests.%s"' % arg)

    if not modules:
        import tests
        modules.insert(0, tests)

    return modules

if __name__ == '__main__':
    parser = get_option_parser()
    options, args = parser.parse_args()

    if options.engine:
        os.environ['PEEWEE_TEST_BACKEND'] = options.engine
    os.environ['PEEWEE_TEST_VERBOSITY'] = str(options.verbosity)

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
