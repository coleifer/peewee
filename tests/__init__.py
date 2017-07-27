import sys
import unittest

from peewee import OperationalError

# Core modules.
from .database import *
from .fields import *
from .keys import *
from .manytomany import *
from .models import *
from .model_sql import *
from .prefetch import *
from .queries import *
from .results import *
from .schema import *
from .sql import *
from .transactions import *

# Extensions.
try:
    from .apsw_ext import *
except ImportError:
    print('Unable to import APSW extension tests, skipping.')
if sys.version_info[0] == 2:
    try:
        from .cysqlite import *
    except ImportError:
        print('Unable to import cython sqlite extension tests, skipping.')
from .dataset import *
from .db_url import *
from .hybrid import *
from .migrations import *
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
from .sqliteq import *
from .sqlite_udf import *


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
