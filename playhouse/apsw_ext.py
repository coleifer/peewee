"""
Peewee integration with APSW, "another python sqlite wrapper".

Project page: https://code.google.com/p/apsw/

APSW is a really neat library that provides a thin wrapper on top of SQLite's
C interface.

Here are just a few reasons to use APSW, taken from the documentation:

* APSW gives all functionality of SQLite, including virtual tables, virtual
  file system, blob i/o, backups and file control.
* Connections can be shared across threads without any additional locking.
* Transactions are managed explicitly by your code.
* APSW can handle nested transactions.
* Unicode is handled correctly.
* APSW is faster.
"""
import apsw
from peewee import *
from peewee import _sqlite_date_part
from peewee import _sqlite_date_trunc
from peewee import _sqlite_regexp
from peewee import BooleanField as _BooleanField
from peewee import DateField as _DateField
from peewee import DateTimeField as _DateTimeField
from peewee import DecimalField as _DecimalField
from peewee import logger
from peewee import savepoint
from peewee import TimeField as _TimeField
from peewee import transaction as _transaction
from playhouse.sqlite_ext import SqliteExtDatabase
from playhouse.sqlite_ext import VirtualCharField
from playhouse.sqlite_ext import VirtualField
from playhouse.sqlite_ext import VirtualFloatField
from playhouse.sqlite_ext import VirtualIntegerField
from playhouse.sqlite_ext import VirtualModel


class transaction(_transaction):
    def __init__(self, db, lock_type='deferred'):
        self.db = db
        self.lock_type = lock_type

    def _begin(self):
        self.db.begin(self.lock_type)


class APSWDatabase(SqliteExtDatabase):
    def __init__(self, database, timeout=None, **kwargs):
        self.timeout = timeout
        self._modules = {}
        super(APSWDatabase, self).__init__(database, **kwargs)

    def register_module(self, mod_name, mod_inst):
        self._modules[mod_name] = mod_inst

    def unregister_module(self, mod_name):
        del(self._modules[mod_name])

    def _connect(self, database, **kwargs):
        conn = apsw.Connection(database, **kwargs)
        try:
            self._add_conn_hooks(conn)
        except:
            conn.close()
            raise
        if self.timeout is not None:
            conn.setbusytimeout(self.timeout)
        try:
            self._add_conn_hooks(conn)
        except:
            conn.close()
            raise
        return conn

    def _add_conn_hooks(self, conn):
        super(APSWDatabase, self)._add_conn_hooks(conn)
        self._load_modules(conn)  # APSW-only.

    def _load_modules(self, conn):
        for mod_name, mod_inst in self._modules.items():
            conn.createmodule(mod_name, mod_inst)
        return conn

    def _load_aggregates(self, conn):
        for name, (klass, num_params) in self._aggregates.items():
            def make_aggregate():
                instance = klass()
                return (instance, instance.step, instance.finalize)
            conn.createaggregatefunction(name, make_aggregate)

    def _load_collations(self, conn):
        for name, fn in self._collations.items():
            conn.createcollation(name, fn)

    def _load_functions(self, conn):
        for name, (fn, num_params) in self._functions.items():
            conn.createscalarfunction(name, fn, num_params)

    def _load_extensions(self, conn):
        conn.enableloadextension(True)
        for extension in self._extensions:
            conn.loadextension(extension)

    def load_extension(self, extension):
        self._extensions.add(extension)
        if not self.is_closed():
            conn = self.get_conn()
            conn.enableloadextension(True)
            conn.loadextension(extension)

    def _execute_sql(self, cursor, sql, params):
        cursor.execute(sql, params or ())
        return cursor

    def execute_sql(self, sql, params=None, require_commit=True):
        logger.debug((sql, params))
        with self.exception_wrapper():
            cursor = self.get_cursor()
            self._execute_sql(cursor, sql, params)
        return cursor

    def last_insert_id(self, cursor, model):
        if model._meta.auto_increment:
            return cursor.getconnection().last_insert_rowid()

    def rows_affected(self, cursor):
        return cursor.getconnection().changes()

    def begin(self, lock_type='deferred'):
        self.get_cursor().execute('begin %s;' % lock_type)

    def commit(self):
        self.get_cursor().execute('commit;')

    def rollback(self):
        self.get_cursor().execute('rollback;')

    def transaction(self, lock_type='deferred'):
        return transaction(self, lock_type)

    def savepoint(self, sid=None):
        return savepoint(self, sid)


def nh(s, v):
    if v is not None:
        return str(v)

class BooleanField(_BooleanField):
    def db_value(self, v):
        v = super(BooleanField, self).db_value(v)
        if v is not None:
            return v and 1 or 0

class DateField(_DateField):
    db_value = nh

class TimeField(_TimeField):
    db_value = nh

class DateTimeField(_DateTimeField):
    db_value = nh

class DecimalField(_DecimalField):
    db_value = nh
