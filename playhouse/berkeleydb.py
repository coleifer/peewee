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
    def _connect(self, database, cache_size=None, multiversion=None,
                 page_size=None, **kwargs):
        conn = berkeleydb.connect(database, **kwargs)
        conn.isolation_level = None
        if cache_size or multiversion or page_size:
            cursor = conn.cursor()
            if multiversion:
                cursor.execute('PRAGMA multiversion = on;')
            if page_size:
                cursor.execute('PRAGMA page_size = %d;' % page_size)
            if cache_size:
                cursor.execute('PRAGMA cache_size = %d;' % cache_size)
            cursor.close()
        self._add_conn_hooks(conn)
        return conn
