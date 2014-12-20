# encoding=utf-8

import datetime
import decimal
import itertools
import logging
import operator
import os
import threading
import time
import unittest
import sys
try:
    from Queue import Queue
except ImportError:
    from queue import Queue
from contextlib import contextmanager
from functools import wraps

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

from peewee import *
from peewee import AliasMap
from peewee import DeleteQuery
from peewee import InsertQuery
from peewee import logger
from peewee import ModelQueryResultWrapper
from peewee import NaiveQueryResultWrapper
from peewee import prefetch_add_subquery
from peewee import print_
from peewee import QueryCompiler
from peewee import R
from peewee import RawQuery
from peewee import SelectQuery
from peewee import sort_models_topologically
from peewee import transaction
from peewee import UpdateQuery


if sys.version_info[0] < 3:
    import codecs
    ulit = lambda s: codecs.unicode_escape_decode(s)[0]
    binary_construct = buffer
    binary_types = buffer
else:
    ulit = lambda s: s
    binary_construct = lambda s: bytes(s.encode('raw_unicode_escape'))
    binary_types = (bytes, memoryview)


#
# TEST CASE USED TO PROVIDE ACCESS TO DATABASE
# FOR EXECUTION OF "LIVE" QUERIES
#

class ModelTestCase(BasePeeweeTestCase):
    requires = None

    def setUp(self):
        super(ModelTestCase, self).setUp()
        drop_tables(self.requires)
        create_tables(self.requires)

    def tearDown(self):
        drop_tables(self.requires)

    def create_user(self, username):
        return User.create(username=username)

    def create_users(self, n):
        for i in range(n):
            self.create_user('u%d' % (i + 1))



if __name__ == '__main__':
    unittest.main(argv=sys.argv)
