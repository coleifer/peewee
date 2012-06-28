import apsw
from peewee import *
from peewee import SqliteAdapter, SqliteDatabase, Database, logger
from peewee import BooleanField as _BooleanField, DateField as _DateField, TimeField as _TimeField, \
    DateTimeField as _DateTimeField, DecimalField as _DecimalField, transaction as _transaction


class ConnectionWrapper(apsw.Connection):
    def cursor(self):
        base_cursor = super(ConnectionWrapper, self).cursor()
        return CursorProxy(base_cursor)


class CursorProxy(object):
    def __init__(self, cursor_obj):
        self.cursor_obj = cursor_obj
        self.implements = set(['description', 'fetchone', 'fetchmany'])

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

    def fetchone(self):
        return self.cursor_obj.next()

    def fetchmany(self, n):
        results = []
        for i, res in enumerate(self.cursor_obj):
            results.append(res)
            if i == n:
                break
        return results


class transaction(_transaction):
    def __init__(self, db, lock_type='deferred'):
        self.db = db
        self.lock_type = lock_type

    def __enter__(self):
        self._orig = self.db.get_autocommit()
        self.db.set_autocommit(False)
        self.db.begin(self.lock_type)


class APSWAdapter(SqliteAdapter):
    def __init__(self, timeout=None):
        self.timeout = timeout

    def connect(self, database, **kwargs):
        conn = ConnectionWrapper(database, **kwargs)
        if self.timeout is not None:
            conn.setbusytimeout(self.timeout)
        return conn


class APSWDatabase(SqliteDatabase):
    def __init__(self, database, **connect_kwargs):
        adapter = APSWAdapter(connect_kwargs.pop('timeout', None))
        Database.__init__(self, adapter, database, **connect_kwargs)

    def execute(self, sql, params=None, require_commit=True):
        cursor = self.get_cursor()
        wrap_transaction = require_commit and self.get_autocommit()
        if wrap_transaction:
            cursor.execute('begin;')
        res = cursor.execute(sql, params or ())
        if wrap_transaction:
            cursor.execute('commit;')
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
