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
from peewee import BooleanField as _BooleanField
from peewee import DateField as _DateField
from peewee import DateTimeField as _DateTimeField
from peewee import DecimalField as _DecimalField
from peewee import logger
from peewee import PY3
from peewee import TimeField as _TimeField
from peewee import transaction as _transaction


class ConnectionWrapper(apsw.Connection):
    def cursor(self):
        base_cursor = super(ConnectionWrapper, self).cursor()
        return CursorProxy(base_cursor)


class CursorProxy(object):
    def __init__(self, cursor_obj):
        self.cursor_obj = cursor_obj
        self.implements = set(['description', 'fetchone'])

    def __getattr__(self, attr):
        if attr in self.implements:
            return self.__getattribute__(attr)
        return getattr(self.cursor_obj, attr)

    @property
    def description(self):
        try:
            return self.cursor_obj.getdescription()
        except apsw.ExecutionCompleteError:
            return []

    if PY3:
        def fetchone(self):
            try:
                return next(self.cursor_obj)
            except StopIteration:
                pass
    else:
        def fetchone(self):
            try:
                return self.cursor_obj.next()
            except StopIteration:
                pass


class transaction(_transaction):
    def __init__(self, db, lock_type='deferred'):
        self.db = db
        self.lock_type = lock_type

    def _begin(self):
        self.db.begin(self.lock_type)


class APSWDatabase(SqliteDatabase):
    def __init__(self, database, timeout=None, **kwargs):
        self.timeout = timeout
        self._modules = {}
        super(APSWDatabase, self).__init__(database, **kwargs)

    def register_module(self, mod_name, mod_inst):
        self._modules[mod_name] = mod_inst

    def unregister_module(self, mod_name):
        del(self._modules[mod_name])

    def _connect(self, database, **kwargs):
        conn = ConnectionWrapper(database, **kwargs)
        if self.timeout is not None:
            conn.setbusytimeout(self.timeout)
        conn.createscalarfunction('date_part', _sqlite_date_part, 2)
        conn.createscalarfunction('date_trunc', _sqlite_date_trunc, 2)
        for mod_name, mod_inst in self._modules.items():
            conn.createmodule(mod_name, mod_inst)
        return conn

    def _execute_sql(self, cursor, sql, params):
        cursor.execute(sql, params or ())
        return cursor

    def execute_sql(self, sql, params=None, require_commit=True):
        cursor = self.get_cursor()
        wrap_transaction = require_commit and self.get_autocommit()
        if wrap_transaction:
            cursor.execute('begin;')
            try:
                self._execute_sql(cursor, sql, params)
            except:
                cursor.execute('rollback;')
                raise
            else:
                cursor.execute('commit;')
        else:
            cursor = self._execute_sql(cursor, sql, params)
        logger.debug((sql, params))
        return cursor

    def last_insert_id(self, cursor, model):
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
