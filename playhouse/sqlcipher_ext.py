import datetime, decimal, sys
from peewee import *
from playhouse.sqlite_ext import SqliteExtDatabase

if sys.version_info[0] != 3: from pysqlcipher import dbapi2 as _sc
else:
    try: from sqlcipher3 import dbapi2 as _sc
    except ImportError: from pysqlcipher3 import dbapi2 as _sc

_sc.register_adapter(decimal.Decimal, str)
_sc.register_adapter(datetime.date, str)
_sc.register_adapter(datetime.time, str)
_v = _sc.sqlite_version_info

class _S(_sc):
    v = _v

    def c(self):
        p = dict(self.connect_params)
        k = p.pop('passphrase', '').replace("'", "''")
        o = _sc.connect(self.database, isolation_level=None, **p)
        try:
            if k: o.execute("PRAGMA key='%s'" % k)
            self._add_conn_hooks(o)
        except:
            o.close()
            raise
        return o

    def s(self, k):
        if not self.is_closed(): raise ImproperlyConfigured('Open db, use rekey()')
        self.connect_params['passphrase'] = k

    def r(self, k):
        if self.is_closed(): self.connect()
        self.execute_sql("PRAGMA rekey='%s'" % k.replace("'", "''"))
        self.connect_params['passphrase'] = k
        return True


class SCDB(_S, SqliteDatabase): pass
class SCExtDB(_S, SqliteExtDatabase): pass

