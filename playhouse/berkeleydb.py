import datetime
import decimal

from playhouse.sqlite_ext import *
from pysqlite2 import dbapi2 as berkeleydb

berkeleydb.register_adapter(decimal.Decimal, str)
berkeleydb.register_adapter(datetime.date, str)
berkeleydb.register_adapter(datetime.time, str)


class BerkeleyDatabase(SqliteExtDatabase):
    def _connect(self, database, **kwargs):
        conn = berkeleydb.connect(database, **kwargs)
        self._add_conn_hooks(conn)
        return conn
