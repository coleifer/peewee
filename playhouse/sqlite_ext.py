"""
Sqlite3 extensions
==================

* Define custom aggregates, collations and functions
* Basic support for virtual tables
* Basic support for FTS3/4
* Specify isolation level in transactions

Example usage of the Full-text search:

class Document(FTSModel):
    title = TextField()  # type affinities are ignored in FTS
    content = TextField()

Document.create_table(tokenize='porter')  # use the porter stemmer

# populate the documents using normal operations.
for doc in documents:
    Document.create(title=doc['title'], content=doc['content'])

# use the "match" operation for FTS queries.
matching_docs = Document.select().where(match(Document.title, 'some query'))

# to sort by best match, use the custom "rank" function.
best_docs = (Document
             .select(Document, Document.rank('score'))
             .where(match(Document.title, 'some query'))
             .order_by(SQL('score').desc()))

# or use the shortcut method.
best_docs = Document.match('some phrase')
"""
import inspect
import sqlite3
import struct

from peewee import *
from peewee import Expression
from peewee import QueryCompiler
from peewee import transaction


FTS_VER = sqlite3.sqlite_version_info[:3] >= (3, 7, 4) and 'FTS4' or 'FTS3'


class PrimaryKeyAutoIncrementField(PrimaryKeyField):
    def __ddl__(self, column_type):
        ddl = super(PrimaryKeyAutoIncrementField, self).__ddl__(column_type)
        return ddl + [SQL('AUTOINCREMENT')]

class SqliteQueryCompiler(QueryCompiler):
    """
    Subclass of QueryCompiler that can be used to construct virtual tables.
    """
    def _create_table(self, model_class, safe=False, options=None):
        clause = super(SqliteQueryCompiler, self)._create_table(
            model_class, safe=safe)

        if issubclass(model_class, VirtualModel):
            statement = 'CREATE VIRTUAL TABLE'
            # If we are using a special extension, need to insert that after the
            # table name node.
            clause.nodes.insert(2, SQL('USING %s' % model_class._extension))
        else:
            statement = 'CREATE TABLE'
        if safe:
            statement += 'IF NOT EXISTS'
        clause.nodes[0] = SQL(statement)  # Overwrite the statement.

        if options:
            columns_constraints = clause.nodes[-1]
            for k, v in options.items():
                if isinstance(v, Field):
                    value = v._as_entity(with_table=True)
                elif inspect.isclass(v) and issubclass(v, Model):
                    value = v._as_entity()
                else:
                    value = SQL(v)
                option = Clause(SQL(k), value)
                option.glue = '='
                columns_constraints.nodes.append(option)

        return clause

    def create_table(self, model_class, safe=False, options=None):
        return self.parse_node(self._create_table(model_class, safe, options))

class VirtualModel(Model):
    """Model class stored using a Sqlite virtual table."""
    _extension = ''

class FTSModel(VirtualModel):
    _extension = FTS_VER

    @classmethod
    def create_table(cls, fail_silently=False, **options):
        if fail_silently and cls.table_exists():
            return

        cls._meta.database.create_table(cls, options=options)
        cls._create_indexes()

    @classmethod
    def _fts_cmd(cls, cmd):
        tbl = cls._meta.db_table
        res = cls._meta.database.execute_sql(
            "INSERT INTO %s(%s) VALUES('%s');" % (tbl, tbl, cmd))
        return res.fetchone()

    @classmethod
    def optimize(cls):
        return cls._fts_cmd('optimize')

    @classmethod
    def rebuild(cls):
        return cls._fts_cmd('rebuild')

    @classmethod
    def integrity_check(cls):
        return cls._fts_cmd('integrity-check')

    @classmethod
    def merge(cls, blocks=200, segments=8):
        return cls._fts_cmd('merge=%s,%s' % (blocks, segments))

    @classmethod
    def automerge(cls, state=True):
        return cls._fts_cmd('automerge=%s' % (state and '1' or '0'))

    @classmethod
    def match(cls, search):
        return (cls
                .select(cls, cls.rank().alias('score'))
                .where(match(cls._as_entity(), search))
                .order_by(SQL('score').desc()))

    @classmethod
    def rank(cls, alias=None):
        rank_fn = Rank(cls)
        if alias:
            return rank_fn.alias(alias)
        return rank_fn


class SqliteExtDatabase(SqliteDatabase):
    """
    Database class which provides additional Sqlite-specific functionality:

    * Register custom aggregates, collations and functions
    * Specify a row factory
    * Advanced transactions (specify isolation level)
    """
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

    def aggregate(self, num_params, name=None):
        def decorator(klass):
            self.register_aggregate(klass, num_params, name)
            return klass
        return decorator

    def register_collation(self, fn, name=None):
        name = name or fn.__name__
        def _collation(*args):
            expressions = args + (SQL('collate %s' % name),)
            return Clause(*expressions)
        fn.collation = _collation
        self._collations[name] = fn

    def collation(self, name=None):
        def decorator(fn):
            self.register_collation(fn, name)
            return fn
        return decorator

    def register_function(self, fn, name=None, num_params=None):
        if num_params is None:
            num_params = self._argc(fn)
        self._functions[name or fn.__name__] = (fn, num_params)

    def func(self, name=None, num_params=None):
        def decorator(fn):
            self.register_function(fn, name, num_params)
            return fn
        return decorator

    def unregister_aggregate(self, name):
        del(self._aggregates[name])

    def unregister_collation(self, name):
        del(self._collations[name])

    def unregister_function(self, name):
        del(self._functions[name])

    def row_factory(self, fn):
        self._row_factory = fn

    def create_table(self, model_class, safe=False, options=None):
        sql, params = self.compiler().create_table(model_class, safe, options)
        return self.execute_sql(sql, params)

    def create_index(self, model_class, field_name, unique=False):
        if issubclass(model_class, FTSModel):
            return
        return super(SqliteExtDatabase, self).create_index(
            model_class, field_name, unique)

    def granular_transaction(self, lock_type='deferred'):
        assert lock_type.lower() in ('deferred', 'immediate', 'exclusive')
        return granular_transaction(self, lock_type)


class granular_transaction(transaction):
    def __init__(self, db, lock_type='deferred'):
        self.db = db
        self.conn = self.db.get_conn()
        self.lock_type = lock_type

    def __enter__(self):
        self._orig_isolation = self.conn.isolation_level
        self.conn.isolation_level = self.lock_type
        return super(granular_transaction, self).__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            super(granular_transaction, self).__exit__(
                exc_type, exc_val, exc_tb)
        finally:
            self.conn.isolation_level = self._orig_isolation


OP_MATCH = 'match'
SqliteExtDatabase.register_ops({
    OP_MATCH: 'MATCH',
})

def match(lhs, rhs):
    return Expression(lhs, OP_MATCH, rhs)

# Shortcut for calculating ranks.
Rank = lambda model: fn.rank(fn.matchinfo(SQL(model._meta.db_table)))

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
