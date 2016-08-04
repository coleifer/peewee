"""

Aggregate all the test modules and run from the command-line. For information
about running tests, see the README located in the `playhouse/tests` directory.
"""
import sys
import unittest

from playhouse.tests.test_apis import *
from playhouse.tests.test_compound_queries import *
from playhouse.tests.test_database import *
from playhouse.tests.test_fields import *
from playhouse.tests.test_helpers import *
from playhouse.tests.test_introspection import *
from playhouse.tests.test_keys import *
from playhouse.tests.test_models import *
from playhouse.tests.test_queries import *
from playhouse.tests.test_query_results import *
from playhouse.tests.test_transactions import *


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
