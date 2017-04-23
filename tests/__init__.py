"""

Aggregate all the test modules and run from the command-line. For information
about running tests, see the README located in the `playhouse/tests` directory.
"""
import sys
import unittest

from .database import *
from .fields import *
from .manytomany import *
from .models import *
from .model_sql import *
from .queries import *
from .results import *
from .schema import *
from .sql import *
from .transactions import *

from .db_url import *
from .hybrid import *
from .pool import *
from .shortcuts import *
from .signals import *
#from playhouse.tests.test_introspection import *
#from playhouse.tests.test_keys import *


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
