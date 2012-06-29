import apsw
from peewee import *
from peewee import SqliteAdapter, SqliteDatabase, Database, logger
from peewee import BooleanField as _BooleanField, DateField as _DateField, TimeField as _TimeField, \
    DateTimeField as _DateTimeField, DecimalField as _DecimalField, transaction as _transaction


class VirtualModel(Model):
    _extension_module = ''

    @classmethod
    def create_table(cls, fail_silently=False, extra='', **options):
        if fail_silently and cls.table_exists():
            return

        cls._meta.database.create_table(cls, extra=extra, vt_options=options)

        for field_name, field_obj in cls._meta.fields.items():
            if isinstance(field_obj, ForeignKeyField):
                cls._meta.database.create_foreign_key(cls, field_obj)
            elif field_obj.db_index or field_obj.unique:
                cls._meta.database.create_index(cls, field_obj.name, field_obj.unique)


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
        try:
            return self.cursor_obj.next()
        except StopIteration:
            pass

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
        self._modules = {}

    def connect(self, database, **kwargs):
        conn = ConnectionWrapper(database, **kwargs)
        if self.timeout is not None:
            conn.setbusytimeout(self.timeout)
        for mod_name, mod_inst in self._modules.items():
            conn.createmodule(mod_name, mod_inst)
        return conn

    def register_module(self, mod_name, mod_inst):
        self._modules[mod_name] = mod_inst

    def unregister_module(self, mod_name):
        del(self._modules[mod_name])


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

    def create_table(self, model_class, safe=False, extra='', vt_options=None):
        if issubclass(model_class, VirtualModel):
            if vt_options:
                options = ', %s' % (', '.join('%s=%s' % (k, v) for k, v in vt_options.items()))
            else:
                options = ''
            framing = 'CREATE VIRTUAL TABLE %%s%%s USING %s (%%s%s)%%s;' % (model_class._extension_module, options)
        else:
            framing = None

        self.execute(self.create_table_query(model_class, safe, extra, framing))

    def create_index(self, model_class, field_name, unique=False):
        if issubclass(model_class, VirtualModel):
            return
        return super(APSWDatabase, self).create_index(model_class, field_name, unique)


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
