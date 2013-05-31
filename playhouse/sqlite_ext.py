import inspect
import sqlite3
import struct

from peewee import *
from peewee import Expr, QueryCompiler, R, transaction


FTS_VER = sqlite3.sqlite_version_info[:3] >= (3, 7, 4) and 'FTS4' or 'FTS3'

class SqliteQueryCompiler(QueryCompiler):
    def create_table_sql(self, model_class, safe=False, vt_options=None):
        if issubclass(model_class, VirtualModel):
            parts = ['CREATE VIRTUAL TABLE']
            using = ['USING %s' % model_class.extension]
        else:
            parts = ['CREATE TABLE']
            using = []
        if safe:
            parts.append('IF NOT EXISTS')
        parts.append(self.quote(model_class._meta.db_table))
        parts.extend(using)
        fields = [self.field_sql(f) for f in model_class._meta.get_fields()]
        if vt_options:
            fields.extend('%s=%s' % (k, v) for k, v in vt_options.items())
        parts.append('(%s)' % ', '.join(fields))
        return parts

    def create_table(self, model_class, safe=False, vt_options=None):
        return ' '.join(self.create_table_sql(
            model_class,
            safe=safe,
            vt_options=vt_options))

class VirtualModel(Model):
    extension = ''

class FTSModel(VirtualModel):
    extension = FTS_VER

    @classmethod
    def create_table(cls, fail_silently=False, **options):
        if fail_silently and cls.table_exists():
            return

        if 'content_model' in options:
            options['content'] = options.pop('content_model')._meta.db_table

        cls._meta.database.create_table(cls, vt_options=options)
        cls._create_indexes()

    @classmethod
    def optimize(cls):
        return cls._meta.database.optimize(cls)

    @classmethod
    def rebuild(cls):
        return cls._meta.database.rebuild(cls)

    @classmethod
    def integrity_check(cls):
        return cls._meta.database.integrity_check(cls)

    @classmethod
    def merge(cls, blocks=200, segments=8):
        return cls._meta.database.merge(cls, blocks, segments)

    @classmethod
    def automerge(cls, state=True):
        return cls._meta.database.automerge(cls, state)


class SqliteExtDatabase(SqliteDatabase):
    compiler_class = SqliteQueryCompiler

    def __init__(self, *args, **kwargs):
        super(SqliteExtDatabase, self).__init__(*args, **kwargs)
        self._aggregates = {}
        self._collations = {}
        self._functions = {}
        self._row_factory = None
        self.register_function(rank, 'rank', 1)

    def _connect(self, database, **kwargs):
        conn = super(SqliteExtDatabase, self)._connect(database, **kwargs)
        for name, (klass, num_params) in self._aggregates.items():
            conn.create_aggregate(name, num_params, klass)
        for name, fn in self._collations.items():
            conn.create_collation(name, fn)
        for name, (fn, num_params) in self._functions.items():
            conn.create_function(name, num_params, fn)
        if self._row_factory:
            conn.row_factory = self._row_factory
        return conn

    def _argc(self, fn):
        return len(inspect.getargspec(fn).args)

    def register_aggregate(self, klass, num_params, name=None):
        self._aggregates[name or klass.__name__.lower()] = (klass, num_params)

    def register_collation(self, fn, name=None):
        self._collations[name or fn.__name__] = fn

    def register_function(self, fn, name=None, num_params=None):
        if num_params is None:
            num_params = self._argc(fn)
        self._functions[name or fn.__name__] = (fn, num_params)

    def unregister_aggregate(self, name):
        del(self._aggregates[name])

    def unregister_collation(self, name):
        del(self._collations[name])

    def unregister_function(self, name):
        del(self._functions[name])

    def row_factory(self, fn):
        self._row_factory = fn

    def create_table(self, model_class, safe=False, vt_options=None):
        qc = self.compiler()
        create_sql = qc.create_table(model_class, safe, vt_options)
        return self.execute_sql(create_sql)

    def create_index(self, model_class, field_name, unique=False):
        if issubclass(model_class, FTSModel):
            return
        return super(SqliteExtDatabase, self).create_index(model_class, field_name, unique)

    def _fts_cmd(self, model_class, cmd):
        tbl = model_class._meta.db_table
        res = self.execute_sql("INSERT INTO %s(%s) VALUES('%s');" % (tbl, tbl, cmd))
        return res.fetchone()

    def optimize(self, model_class):
        return self._fts_cmd(model_class, 'optimize')

    def rebuild(self, model_class):
        return self._fts_cmd(model_class, 'rebuild')

    def integrity_check(self, model_class):
        return self._fts_cmd(model_class, 'integrity-check')

    def merge(self, model_class, blocks=200, segments=8):
        return self._fts_cmd(model_class, 'merge=%s,%s' % (blocks, segments))

    def automerge(self, model_class, state=True):
        return self._fts_cmd(model_class, 'automerge=%s' % (state and '1' or '0'))

    def granular_transaction(self, lock_type='deferred'):
        assert lock_type.lower() in ('deferred', 'immediate', 'exclusive')
        return granular_transaction(self, lock_type)


SqliteExtDatabase.register_ops({
    'match': 'MATCH',
})
def match(lhs, rhs):
    return Expr(lhs, 'match', rhs)


class granular_transaction(transaction):
    def __init__(self, db, lock_type='deferred'):
        self.db = db
        self.conn = self.db.get_conn()
        self.lock_type = lock_type

    def __enter__(self):
        self._orig = self.db.get_autocommit()
        self.db.set_autocommit(False)
        self._orig_isolation = self.conn.isolation_level
        self.conn.isolation_level = self.lock_type

    def __exit__(self, exc_type, exc_val, exc_tb):
        success = super(granular_transaction, self).__exit__(
            exc_type,
            exc_val,
            exc_tb)
        self.conn.isolation_level = self._orig_isolation
        return success


# Shortcut for calculating ranks.
Rank = lambda model: fn.rank(fn.matchinfo(R(model._meta.db_table)))

def _parse_match_info(buf):
    # see http://sqlite.org/fts3.html#matchinfo
    bufsize = len(buf) # length in bytes
    return [struct.unpack('@I', buf[i:i+4])[0] for i in range(0, bufsize, 4)]

# Ranking implementation, which parse matchinfo.
def rank(match_info):
    # handle match_info called w/default args 'pcx' - based on the example rank
    # function http://sqlite.org/fts3.html#appendix_a
    info = _parse_match_info(match_info)
    score = 0.0
    phrase_ct = info[0]
    col_ct = info[1]
    for phrase in range(phrase_ct):
        phrase_info_idx = 2 + (phrase * col_ct * 3)
        for col in range(0, col_ct):
            col_idx = phrase_info_idx + (col * 3)
            hit_count = info[col_idx]
            global_hit_count = info[col_idx + 1]
            if hit_count > 0:
                score += float(hit_count) / global_hit_count
    return score
