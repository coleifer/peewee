import ctypes
import datetime
import decimal
import sys

from peewee import ImproperlyConfigured
from peewee import sqlite3
from playhouse.sqlite_ext import *

sqlite3_lib_version = sqlite3.sqlite_version_info

# Peewee assumes that the `pysqlite2` module was compiled against the
# BerkeleyDB SQLite libraries.
try:
    from pysqlite2 import dbapi2 as berkeleydb
except ImportError:
    import sqlite3 as berkeleydb

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
        if not PYSQLITE_BERKELEYDB:
            message = ('Your Python SQLite driver (%s) does not appear to '
                       'have been compiled against the BerkeleyDB SQLite '
                       'library.' % berkeleydb)
            if LIBSQLITE_BERKELEYDB:
                message += (' However, the libsqlite on your system is the '
                            'BerkeleyDB implementation. Try recompiling '
                            'pysqlite.')
            else:
                message += (' Additionally, the libsqlite on your system '
                            'does not appear to be the BerkeleyDB '
                            'implementation.')
            raise ImproperlyConfigured(message)

        conn = berkeleydb.connect(database, **kwargs)
        conn.isolation_level = None
        self._add_conn_hooks(conn)
        return conn

    def _set_pragmas(self, conn):
        # `multiversion` is weird. It checks first whether another connection
        # from the BTree cache is available, and then switches to that, which
        # may have the handle of the DB_Env. If that happens, then we get
        # an error stating that you cannot set `multiversion` despite the
        # fact we have not done any operations and it's a brand new conn.
        if self._pragmas:
            cursor = conn.cursor()
            for pragma, value in self._pragmas:
                if pragma == 'multiversion':
                    try:
                        cursor.execute('PRAGMA %s = %s;' % (pragma, value))
                    except berkeleydb.OperationalError:
                        pass
                else:
                    cursor.execute('PRAGMA %s = %s;' % (pragma, value))
            cursor.close()

    @classmethod
    def check_pysqlite(cls):
        try:
            from pysqlite2 import dbapi2 as sqlite3
        except ImportError:
            import sqlite3
        conn = sqlite3.connect(':memory:')
        try:
            results = conn.execute('PRAGMA compile_options;').fetchall()
        finally:
            conn.close()
        for option, in results:
            if option == 'BERKELEY_DB':
                return True
        return False

    @classmethod
    def check_libsqlite(cls):
        # Checking compile options is not supported.
        if sys.platform.startswith('win'):
            library = 'libsqlite3.dll'
        elif sys.platform == 'darwin':
            library = 'libsqlite3.dylib'
        else:
            library = 'libsqlite3.so'

        try:
            libsqlite = ctypes.CDLL(library)
        except OSError:
            return False

        return libsqlite.sqlite3_compileoption_used('BERKELEY_DB') == 1


if sqlite3_lib_version < (3, 6, 23):
    # Checking compile flags is not supported in older SQLite versions.
    PYSQLITE_BERKELEYDB = False
    LIBSQLITE_BERKELEYDB = False
else:
    PYSQLITE_BERKELEYDB = BerkeleyDatabase.check_pysqlite()
    LIBSQLITE_BERKELEYDB = BerkeleyDatabase.check_libsqlite()
