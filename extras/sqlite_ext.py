import hashlib
import inspect
import sqlite3
import struct
from peewee import *
from peewee import SqliteAdapter, Database


class VirtualModel(Model):
    _extension_module = ''


class FTSModel(VirtualModel):
    _extension_module = sqlite3.sqlite_version_info[:3] >= (3, 7, 4) and 'FTS4' or 'FTS3'

    @classmethod
    def create_table(cls, fail_silently=False, extra='', **options):
        if fail_silently and cls.table_exists():
            return

        if 'content_model' in options:
            options['content'] = options.pop('content_model')._meta.db_table

        cls._meta.database.create_table(cls, extra=extra, vt_options=options)

        for field_name, field_obj in cls._meta.fields.items():
            if isinstance(field_obj, ForeignKeyField):
                cls._meta.database.create_foreign_key(cls, field_obj)
            elif field_obj.db_index or field_obj.unique:
                cls._meta.database.create_index(cls, field_obj.name, field_obj.unique)

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


class Rank(R):
    def __init__(self, alias='score'):
        self.alias = alias

    def sql_select(self, model_class):
        return 'rank(matchinfo(%s))' % model_class._meta.db_table, self.alias


class SqliteExtAdapter(SqliteAdapter):
    def __init__(self, *args, **kwargs):
        super(SqliteExtAdapter, self).__init__(*args, **kwargs)
        self.operations['match'] = 'MATCH %s'
        self._aggregates = {}
        self._collations = {}
        self._functions = {}
        self._row_factory = None
        self.register_function(rank, 'rank', 1)

    def connect(self, database, **kwargs):
        conn = super(SqliteExtAdapter, self).connect(database, **kwargs)
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


class granular_transaction(object):
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
        if exc_type:
            self.db.rollback()
        else:
            self.db.commit()
        self.db.set_autocommit(self._orig)
        self.conn.isolation_level = self._orig_isolation


class SqliteExtDatabase(SqliteDatabase):
    def __init__(self, database, **connect_kwargs):
        Database.__init__(self, SqliteExtAdapter(), database, **connect_kwargs)

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
        if issubclass(model_class, FTSModel):
            return
        return super(SqliteExtDatabase, self).create_index(model_class, field_name, unique)

    def _fts_cmd(self, model_class, cmd):
        tbl = model_class._meta.db_table
        res = self.execute("INSERT INTO %s(%s) VALUES('%s');" % (tbl, tbl, cmd))
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


# example aggregate
class WeightedAverage(object):
    def __init__(self):
        self.total_weight = 0.0
        self.total_ct = 0.0

    def step(self, value, wt=None):
        wt = wt or 1.0
        self.total_weight += wt
        self.total_ct += wt * value

    def finalize(self):
        if self.total_weight != 0.0:
            return self.total_ct / self.total_weight
        return 0.0

# example collations
def collate_reverse(s1, s2):
    return -cmp(s1, s2)


def _parse_match_info(buf):
    # see http://sqlite.org/fts3.html#matchinfo
    bufsize = len(buf) # length in bytes
    return [struct.unpack('@I', buf[i:i+4])[0] for i in range(0, bufsize, 4)]

# example functions
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

def md5(s):
    return hashlib.md5(s).hexdigest()

def sha1(s):
    return hashlib.sha1(s).hexdigest()

def sha512(s):
    return hashlib.sha512(s).hexdigest()
