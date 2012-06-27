import apsw
from peewee import *
from peewee import SqliteAdapter, SqliteDatabase, Database, logger
from peewee import BooleanField as _BooleanField, DateField as _DateField, TimeField as _TimeField, \
    DateTimeField as _DateTimeField


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
            return self.cursor_obj.description
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


class APSWAdapter(SqliteAdapter):
    def connect(self, database, **kwargs):
        return ConnectionWrapper(database, **kwargs)


class APSWDatabase(SqliteDatabase):
    def __init__(self, database, **connect_kwargs):
        Database.__init__(self, APSWAdapter(), database, **connect_kwargs)

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


def nh(s, v):
    if v is not None:
        return str(v)

class BooleanField(_BooleanField):
    def db_value(self, v):
        if v is not None:
            return v and 1 or 0

class DateField(_DateField):
    db_value = nh

class TimeField(_TimeField):
    db_value = nh

class DateTimeField(_DateTimeField):
    db_value = nh
