#!/usr/bin/env python
import optparse
import os
import shutil
import sys
import unittest


USER = os.environ.get('USER') or 'root'


def runtests(suite, verbosity=1, failfast=False):
    runner = unittest.TextTestRunner(verbosity=verbosity, failfast=failfast)
    results = runner.run(suite)
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
              '[sqlite, postgres, mysql, mysqlconnector, apsw, sqlcipher,'
              ' cockroachdb]'))
    basic.add_option('-v', '--verbosity', dest='verbosity', default=1,
                     type='int', help='Verbosity of output')
    basic.add_option('-f', '--failfast', action='store_true', default=False,
                     dest='failfast', help='Exit on first failure/error.')
    parser.add_option_group(basic)

    db_param_map = (
        ('MySQL', 'MYSQL', (
            # param  default disp default val
            ('host', 'localhost', 'localhost'),
            ('port', '3306', ''),
            ('user', USER, USER),
            ('password', 'blank', ''))),
        ('Postgresql', 'PSQL', (
            ('host', 'localhost', os.environ.get('PGHOST', '')),
            ('port', '5432', ''),
            ('user', 'postgres', os.environ.get('PGUSER', '')),
            ('password', 'blank', os.environ.get('PGPASSWORD', '')))),
        ('CockroachDB', 'CRDB', (
            # param  default disp default val
            ('host', 'localhost', 'localhost'),
            ('port', '26257', ''),
            ('user', 'root', 'root'),
            ('password', 'blank', ''))))
    for name, prefix, param_list in db_param_map:
        group = optparse.OptionGroup(parser, '%s connection options' % name)
        for param, default_disp, default_val in param_list:
            dest = '%s_%s' % (prefix.lower(), param)
            opt = '--%s-%s' % (prefix.lower(), param)
            group.add_option(opt, default=default_val, dest=dest, help=(
                '%s database %s. Default %s.' % (name, param, default_disp)))

        parser.add_option_group(group)
    return parser

def collect_tests(args):
    suite = unittest.TestSuite()

    if not args:
        import tests
        module_suite = unittest.TestLoader().loadTestsFromModule(tests)
        suite.addTest(module_suite)
    else:
        cleaned = ['tests.%s' % arg if not arg.startswith('tests.') else arg
                   for arg in args]
        user_suite = unittest.TestLoader().loadTestsFromNames(cleaned)
        suite.addTest(user_suite)

    return suite

if __name__ == '__main__':
    parser = get_option_parser()
    options, args = parser.parse_args()

    if options.engine:
        os.environ['PEEWEE_TEST_BACKEND'] = options.engine

    for db in ('mysql', 'psql', 'crdb'):
        for key in ('host', 'port', 'user', 'password'):
            att_name = '_'.join((db, key))
            value = getattr(options, att_name, None)
            if value:
                os.environ['PEEWEE_%s' % att_name.upper()] = value

    os.environ['PEEWEE_TEST_VERBOSITY'] = str(options.verbosity)

    suite = collect_tests(args)
    failures, errors = runtests(suite, options.verbosity, options.failfast)

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
