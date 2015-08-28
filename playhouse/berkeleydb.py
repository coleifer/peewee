import datetime
import decimal

from playhouse.sqlite_ext import *

# Peewee assumes that the `pysqlite2` module was compiled against the
# BerkeleyDB SQLite libraries.
from pysqlite2 import dbapi2 as berkeleydb

berkeleydb.register_adapter(decimal.Decimal, str)
berkeleydb.register_adapter(datetime.date, str)
berkeleydb.register_adapter(datetime.time, str)


class BerkeleyDatabase(SqliteExtDatabase):
    def __init__(self, database, pragmas=None, cache_size=None, page_size=None,
                 multiversion=None, *args, **kwargs):
        super(BerkeleyDatabase, self).__init__(
            database, pragmas=pragmas, *args, **kwargs)
        if multiversion:
            self._pragmas.append(('multiversion', 'on'))
        if page_size:
            self._pragmas.append(('page_size', page_size))
        if cache_size:
            self._pragmas.append(('cache_size', cache_size))

    def _connect(self, database, **kwargs):
        conn = berkeleydb.connect(database, **kwargs)
        conn.isolation_level = None
        self._add_conn_hooks(conn)
        return conn
