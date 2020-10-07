import sys
import unittest

from peewee import OperationalError

# Core modules.
from .db_tests import *
from .expressions import *
from .fields import *
from .keys import *
from .manytomany import *
from .models import *
from .model_save import *
from .model_sql import *
from .prefetch_tests import *
from .queries import *
from .regressions import *
from .results import *
from .schema import *
from .sql import *
from .transactions import *

# Extensions.
try:
    from .apsw_ext import *
except ImportError:
    print('Unable to import APSW extension tests, skipping.')
try:
    from .cockroachdb import *
except ImportError:
    print('Unable to import CockroachDB tests, skipping.')
try:
    from .cysqlite import *
except ImportError:
    print('Unable to import sqlite C extension tests, skipping.')
from .dataset import *
from .db_url import *
from .extra_fields import *
from .hybrid import *
from .kv import *
from .migrations import *
try:
    import mysql.connector
    from .mysql_ext import *
except ImportError:
    print('Unable to import mysql-connector, skipping mysql_ext tests.')
from .pool import *
try:
    from .postgres import *
except ImportError:
    print('Unable to import postgres extension tests, skipping.')
except OperationalError:
    print('Postgresql test database "peewee_test" not found, skipping '
          'the postgres_ext tests.')
from .pwiz_integration import *
from .reflection import *
from .shortcuts import *
from .signals import *
try:
    from .sqlcipher_ext import *
except ImportError:
    print('Unable to import SQLCipher extension tests, skipping.')
try:
    from .sqlite import *
except ImportError:
    print('Unable to import sqlite extension tests, skipping.')
try:
    from .sqlite_changelog import *
except ImportError:
    print('Unable to import sqlite changelog tests, skipping.')
from .sqliteq import *
from .sqlite_udf import *
from .test_utils import *


if __name__ == '__main__':
    from peewee import print_
    print_("""\033[1;31m
     ______   ______     ______     __     __     ______     ______
    /\  == \ /\  ___\   /\  ___\   /\ \  _ \ \   /\  ___\   /\  ___\\
    \ \  _-/ \ \  __\   \ \  __\   \ \ \/ ".\ \  \ \  __\   \ \  __\\
     \ \_\    \ \_____\  \ \_____\  \ \__/".~\_\  \ \_____\  \ \_____\\
      \/_/     \/_____/   \/_____/   \/_/   \/_/   \/_____/   \/_____/
    \033[0m""")
    unittest.main(argv=sys.argv)
