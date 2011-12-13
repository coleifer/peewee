#!/usr/bin/env python
import os
import unittest


def collect():
    start_dir = os.path.abspath(os.path.dirname(__file__))
    return unittest.defaultTestLoader.discover(start_dir)


if __name__ == '__main__':
    backend = os.environ.get('PEEWEE_TEST_BACKEND') or 'sqlite'
    print 'RUNNING PEEWEE TESTS WITH [%s]' % backend
    print '=============================================='
    unittest.main(module='tests')

