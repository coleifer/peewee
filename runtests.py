#!/usr/bin/env python
import sys
import unittest

from os.path import dirname, abspath

import tests

def runtests(*test_args):
    suite = unittest.TestLoader().loadTestsFromModule(tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit()

if __name__ == '__main__':
    runtests(*sys.argv[1:])
