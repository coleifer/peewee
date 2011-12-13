#!/usr/bin/env python
import os
import sys
import unittest
import tests

def runtests(*test_args):
    backend = os.environ.get('PEEWEE_TEST_BACKEND') or 'sqlite'
    print 'RUNNING PEEWEE TESTS WITH [%s]' % backend
    print '=============================================='
    suite = unittest.TestLoader().loadTestsFromModule(tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.failures:
        sys.exit(1)
    elif result.errors:
        sys.exit(2)
    sys.exit(0)

if __name__ == '__main__':
    runtests(*sys.argv[1:])
