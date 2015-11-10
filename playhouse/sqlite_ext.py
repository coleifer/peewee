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
import math
try:
    import sqlite3
except ImportError:
    from pysqlite2 import dbapi2 as sqlite3
import struct

from peewee import *
from peewee import EnclosedClause
from peewee import Entity
from peewee import Expression
from peewee import Node
from peewee import OP
from peewee import QueryCompiler
from peewee import transaction


FTS_VER = sqlite3.sqlite_version_info[:3] >= (3, 7, 4) and 'FTS4' or 'FTS3'


class PrimaryKeyAutoIncrementField(PrimaryKeyField):
    def __ddl__(self, column_type):
        ddl = super(PrimaryKeyAutoIncrementField, self).__ddl__(column_type)
        return ddl + [SQL('AUTOINCREMENT')]

class _VirtualFieldMixin(object):
    """
    Field mixin to support virtual table attributes that may not correspond
    to actual columns in the database.
    """
    def add_to_class(self, model_class, name):
        super(_VirtualFieldMixin, self).add_to_class(model_class, name)
        del model_class._meta.fields[self.name]
        del model_class._meta.columns[self.db_column]

class VirtualField(_VirtualFieldMixin, BareField):
    pass

class VirtualIntegerField(_VirtualFieldMixin, IntegerField):
    pass

class VirtualCharField(_VirtualFieldMixin, CharField):
    pass

class VirtualFloatField(_VirtualFieldMixin, FloatField):
    pass

class RowIDField(_VirtualFieldMixin, PrimaryKeyField):
    def add_to_class(self, model_class, name):
        if name != 'rowid':
            raise ValueError('RowIDField must be named `rowid`.')
        return super(RowIDField, self).add_to_class(model_class, name)


class SqliteQueryCompiler(QueryCompiler):
    """
    Subclass of QueryCompiler that can be used to construct virtual tables.
    """
    def _create_table(self, model_class, safe=False, options=None):
        clause = super(SqliteQueryCompiler, self)._create_table(
            model_class, safe=safe)

        if issubclass(model_class, VirtualModel):
            statement = 'CREATE VIRTUAL TABLE'
            # If we are using a special extension, need to insert that after
            # the table name node.
            extension = model_class._extension
            if isinstance(extension, Node):
                parts = clause.nodes[:2] + [SQL('USING'), extension]
                clause = Clause(*parts)
            else:
                clause.nodes.insert(2, SQL('USING %s' % model_class._extension))
        else:
            statement = 'CREATE TABLE'
        if safe:
            statement += ' IF NOT EXISTS'
        clause.nodes[0] = SQL(statement)  # Overwrite the statement.

        table_options = getattr(model_class._meta, 'options', None) or {}
        if options:
            table_options.update(options)

        if table_options:
            columns_constraints = clause.nodes[-1]
            for k, v in sorted(table_options.items()):
                if isinstance(v, Field):
                    value = v.as_entity(with_table=True)
                elif inspect.isclass(v) and issubclass(v, Model):
                    value = v.as_entity()
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
    def match(cls, term):
        """
        Generate a `MATCH` expression appropriate for searching this table.
        """
        return match(cls.as_entity(), term)

    @classmethod
    def rank(cls):
        return Rank(cls)

    @classmethod
    def bm25(cls, field=None, k=1.2, b=0.75):
        if field is None:
            field = find_best_search_field(cls)
        field_idx = cls._meta.get_field_index(field)
        match_info = fn.matchinfo(cls.as_entity(), 'pcxnal')
        return fn.fts_bm25(match_info, field_idx, k, b)

    @classmethod
    def search(cls, term, alias='score'):
        """Full-text search using selected `term`."""
        return (cls
                .select(cls, cls.rank().alias(alias))
                .where(cls.match(term))
                .order_by(SQL(alias).desc()))

    @classmethod
    def search_bm25(cls, term, field=None, k=1.2, b=0.75, alias='score'):
        """Full-text search for selected `term` using BM25 algorithm."""
        if field is None:
            field = find_best_search_field(cls)
        return (cls
                .select(cls, cls.bm25(field, k, b).alias(alias))
                .where(cls.match(term))
                .order_by(SQL(alias).desc()))


class FTS5Model(VirtualModel):
    """
    Requires SQLite >= 3.9.0.

    Table options:

    content: table name of external content, or empty string for "contentless"
    content_rowid: column name of external content primary key
    prefix: integer(s). Ex: '2' or '2 3 4'
    tokenize: porter, unicode61, ascii. Ex: 'porter unicode61'

    The unicode tokenizer supports the following parameters:

    * remove_diacritics (1 or 0, default is 1)
    * tokenchars (string of characters, e.g. '-_'
    * separators (string of characters)

    Parameters are passed as alternating parameter name and value, so:

    {'tokenize': "unicode61 remove_diacritics 0 tokenchars '-_'"}

    Content-less tables:

    If you don't need the full-text content in it's original form, you can
    specify a content-less table. Searches and auxiliary functions will work
    as usual, but the only values returned when SELECT-ing can be rowid. Also
    content-less tables do not support UPDATE or DELETE.

    External content tables:

    You can set up triggers to sync these, e.g.

    -- Create a table. And an external content fts5 table to index it.
    CREATE TABLE tbl(a INTEGER PRIMARY KEY, b);
    CREATE VIRTUAL TABLE ft USING fts5(b, content='tbl', content_rowid='a');

    -- Triggers to keep the FTS index up to date.
    CREATE TRIGGER tbl_ai AFTER INSERT ON tbl BEGIN
      INSERT INTO ft(rowid, b) VALUES (new.a, new.b);
    END;
    CREATE TRIGGER tbl_ad AFTER DELETE ON tbl BEGIN
      INSERT INTO ft(fts_idx, rowid, b) VALUES('delete', old.a, old.b);
    END;
    CREATE TRIGGER tbl_au AFTER UPDATE ON tbl BEGIN
      INSERT INTO ft(fts_idx, rowid, b) VALUES('delete', old.a, old.b);
      INSERT INTO ft(rowid, b) VALUES (new.a, new.b);
    END;

    Built-in auxiliary functions:

    * bm25(tbl[, weight_0, ... weight_n])
    * highlight(tbl, col_idx, prefix, suffix)
    * snippet(tbl, col_idx, prefix, suffix, ?, max_tokens)
    """
    _extension = 'fts5'

    # FTS5 does not support declared primary keys, but we will use the
    # implicit rowid.
    rowid = RowIDField()

    @classmethod
    def fts5_installed(cls):
        # Test in-memory DB to determine if the FTS5 extension is installed.
        tmp_db = sqlite3.connect(':memory:')
        try:
            tmp_db.execute('CREATE VIRTUAL TABLE fts5test USING fts5 (data);')
        except:
            try:
                sqlite3.enable_load_extension(True)
                sqlite3.load_extension('fts5')
            except:
                return False
            else:
                cls._meta.database.load_extension('fts5')
        finally:
            tmp_db.close()

        return True

    @classmethod
    def match(cls, term):
        """
        Generate a `MATCH` expression appropriate for searching this table.
        """
        return match(cls.as_entity(), term)

    @classmethod
    def rank(cls):
        return SQL('rank')

    @classmethod
    def search(cls, term, with_score=False, score_alias='score'):
        """Full-text search using selected `term`."""
        selection = ()
        if with_score:
            selection = (cls, SQL('rank').alias(score_alias))
        return (cls
                .select(*selection)
                .where(cls.match(term))
                .order_by(SQL('rank')))

    @classmethod
    def search_bm25(cls, term, weights=None, with_score=False,
                    score_alias='score'):
        """Full-text search using selected `term`."""
        if not weights:
            return cls.search(term, with_score, score_alias)

        weight_args = []
        for field in cls._meta.get_fields():
            weight_args.append(
                weights.get(field, weights.get(field.name, 1.0)))
        rank = fn.bm25(cls.as_entity(), *weight_args)

        selection = ()
        order_by = rank
        if with_score:
            selection = (cls, rank.alias(score_alias))
            order_by = SQL(score_alias)

        return (cls
                .select(*selection)
                .where(cls.match(term))
                .order_by(order_by))

    @classmethod
    def _fts_cmd(cls, cmd, **extra_params):
        tbl = cls.as_entity()
        columns = [tbl]
        values = [cmd]
        for key, value in extra_params.items():
            columns.append(Entity(key))
            values.append(value)

        inner_clause = EnclosedClause(tbl)
        clause = Clause(
            SQL('INSERT INTO'),
            cls.as_entity(),
            EnclosedClause(*columns),
            SQL('VALUES'),
            EnclosedClause(*values))
        return cls._meta.database.execute(clause)

    @classmethod
    def automerge(cls, level):
        if not (0 <= level <= 16):
            raise ValueError('level must be between 0 and 16')
        return cls._fts_cmd('automerge', rank=level)

    @classmethod
    def merge(cls, npages):
        return cls._fts_cmd('merge', rank=npages)

    @classmethod
    def set_pgsz(cls, pgsz):
        return cls._fts_cmd('pgsz', rank=pgsz)

    @classmethod
    def set_rank(cls, rank_expression):
        return cls._fts_cmd('rank', rank=rank_expression)

    @classmethod
    def delete_all(cls):
        return cls._fts_cmd('delete-all')

    @classmethod
    def VocabModel(cls, table_type='row', table_name=None):
        if table_type not in ('row', 'col'):
            raise ValueError('table_type must be either "row" or "col".')

        attr = '_vocab_model_%s' % table_type

        if not hasattr(cls, attr):
            class Meta:
                database = cls._meta.database
                db_table = table_name or cls._meta.db_table + '_v'
                primary_key = False

            attrs = {
                '_extension': fn.fts5vocab(cls.as_entity(), SQL(table_type)),
                'term': BareField(),
                'doc': IntegerField(),
                'cnt': IntegerField(),
                'Meta': Meta,
            }
            if table_type == 'col':
                attrs['col'] = BareField()

            class_name = '%sVocab' % cls.__name__
            setattr(cls, attr, type(class_name, (VirtualModel,), attrs))

        return getattr(cls, attr)


def ClosureTable(model_class, foreign_key=None):
    """Model factory for the transitive closure extension."""
    if foreign_key is None:
        for field_obj in model_class._meta.rel.values():
            if field_obj.rel_model is model_class:
                foreign_key = field_obj
                break
        else:
            raise ValueError('Unable to find self-referential foreign key.')
    primary_key = model_class._meta.primary_key

    class BaseClosureTable(VirtualModel):
        _extension = 'transitive_closure'

        depth = VirtualIntegerField()
        id = VirtualIntegerField()
        idcolumn = VirtualIntegerField()
        parentcolumn = VirtualIntegerField()
        root = VirtualIntegerField()
        tablename = VirtualCharField()

        @classmethod
        def descendants(cls, node, depth=None, include_node=False):
            query = (model_class
                     .select(model_class, cls.depth.alias('depth'))
                     .join(cls, on=(primary_key == cls.id))
                     .where(cls.root == node))
            if depth is not None:
                query = query.where(cls.depth == depth)
            elif not include_node:
                query = query.where(cls.depth > 0)
            return query

        @classmethod
        def ancestors(cls, node, depth=None, include_node=False):
            query = (model_class
                     .select(model_class, cls.depth.alias('depth'))
                     .join(cls, on=(primary_key == cls.root))
                     .where(cls.id == node))
            if depth:
                query = query.where(cls.depth == depth)
            elif not include_node:
                query = query.where(cls.depth > 0)
            return query

        @classmethod
        def siblings(cls, node, include_node=False):
            fk_value = node._data.get(foreign_key.name)
            query = model_class.select().where(foreign_key == fk_value)
            if not include_node:
                query = query.where(primary_key != node)
            return query

    class Meta:
        database = model_class._meta.database
        options = {
            'tablename': model_class._meta.db_table,
            'idcolumn': model_class._meta.primary_key.db_column,
            'parentcolumn': foreign_key.db_column}
        primary_key = False

    name = '%sClosure' % model_class.__name__
    return type(name, (BaseClosureTable,), {'Meta': Meta})


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
        self._extensions = set([])
        self._row_factory = None
        self.register_function(rank, 'fts_rank', 1)
        self.register_function(bm25, 'fts_bm25', -1)

    def _add_conn_hooks(self, conn):
        # Registers date_part, date_trunc and regexp helpers.
        super(SqliteExtDatabase, self)._add_conn_hooks(conn)

        self._load_aggregates(conn)
        self._load_collations(conn)
        self._load_functions(conn)
        if self._row_factory:
            conn.row_factory = self._row_factory
        if self._extensions:
            conn.enable_load_extension(True)
            for extension in self._extensions:
                conn.load_extension(extension)

    def _load_aggregates(self, conn):
        for name, (klass, num_params) in self._aggregates.items():
            conn.create_aggregate(name, num_params, klass)

    def _load_collations(self, conn):
        for name, fn in self._collations.items():
            conn.create_collation(name, fn)

    def _load_functions(self, conn):
        for name, (fn, num_params) in self._functions.items():
            conn.create_function(name, num_params, fn)

    def register_aggregate(self, klass, name=None, num_params=-1):
        self._aggregates[name or klass.__name__.lower()] = (klass, num_params)
        if not self.is_closed():
            self._load_aggregates(self.get_conn())

    def aggregate(self, name=None, num_params=-1):
        def decorator(klass):
            self.register_aggregate(klass, name, num_params)
            return klass
        return decorator

    def register_collation(self, fn, name=None):
        name = name or fn.__name__
        def _collation(*args):
            expressions = args + (SQL('collate %s' % name),)
            return Clause(*expressions)
        fn.collation = _collation
        self._collations[name] = fn
        if not self.is_closed():
            self._load_collations(self.get_conn())

    def collation(self, name=None):
        def decorator(fn):
            self.register_collation(fn, name)
            return fn
        return decorator

    def register_function(self, fn, name=None, num_params=-1):
        self._functions[name or fn.__name__] = (fn, num_params)
        if not self.is_closed():
            self._load_functions(self.get_conn())

    def func(self, name=None, num_params=-1):
        def decorator(fn):
            self.register_function(fn, name, num_params)
            return fn
        return decorator

    def load_extension(self, extension):
        self._extensions.add(extension)
        if not self.is_closed():
            conn = self.get_conn()
            conn.enable_load_extension(True)
            conn.load_extension(extension)

    def unregister_aggregate(self, name):
        del(self._aggregates[name])

    def unregister_collation(self, name):
        del(self._collations[name])

    def unregister_function(self, name):
        del(self._functions[name])

    def unload_extension(self, extension):
        self._extensions.remove(extension)

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

    def _begin(self):
        self.db.begin(self.lock_type)


OP.MATCH = 'match'
SqliteExtDatabase.register_ops({
    OP.MATCH: 'MATCH',
})

def match(lhs, rhs):
    return Expression(lhs, OP.MATCH, rhs)

# Shortcut for calculating ranks.
Rank = lambda model: fn.fts_rank(fn.matchinfo(model.as_entity()))
BM25 = lambda mc, idx: fn.fts_bm25(fn.matchinfo(mc.as_entity(), 'pcxnal'), idx)

def find_best_search_field(model_class):
    for field_class in [TextField, CharField]:
        for model_field in model_class._meta.get_fields():
            if isinstance(model_field, field_class):
                return model_field
    return model_class._meta.get_fields()[-1]

def _parse_match_info(buf):
    # See http://sqlite.org/fts3.html#matchinfo
    bufsize = len(buf)  # Length in bytes.
    return [struct.unpack('@I', buf[i:i+4])[0] for i in range(0, bufsize, 4)]

# Ranking implementation, which parse matchinfo.
def rank(raw_match_info):
    # Handle match_info called w/default args 'pcx' - based on the example rank
    # function http://sqlite.org/fts3.html#appendix_a
    match_info = _parse_match_info(raw_match_info)
    score = 0.0
    p, c = match_info[:2]
    for phrase_num in range(p):
        phrase_info_idx = 2 + (phrase_num * c * 3)
        for col_num in range(c):
            col_idx = phrase_info_idx + (col_num * 3)
            x1, x2 = match_info[col_idx:col_idx + 2]
            if x1 > 0:
                score += float(x1) / x2
    return score

# Okapi BM25 ranking implementation (FTS4 only).
def bm25(raw_match_info, column_index, k1=1.2, b=0.75):
    """
    Usage:

        # Format string *must* be pcxnal
        # Second parameter to bm25 specifies the index of the column, on
        # the table being queries.
        bm25(matchinfo(document_tbl, 'pcxnal'), 1) AS rank
    """
    match_info = _parse_match_info(raw_match_info)
    score = 0.0
    # p, 1 --> num terms
    # c, 1 --> num cols
    # x, (3 * p * c) --> for each phrase/column,
    #     term_freq for this column
    #     term_freq for all columns
    #     total documents containing this term
    # n, 1 --> total rows in table
    # a, c --> for each column, avg number of tokens in this column
    # l, c --> for each column, length of value for this column (in this row)
    # s, c --> ignore
    p, c = match_info[:2]
    n_idx = 2 + (3 * p * c)
    a_idx = n_idx + 1
    l_idx = a_idx + c
    n = match_info[n_idx]
    a = match_info[a_idx: a_idx + c]
    l = match_info[l_idx: l_idx + c]

    total_docs = n
    avg_length = float(a[column_index])
    doc_length = float(l[column_index])
    if avg_length == 0:
        D = 0
    else:
        D = 1 - b + (b * (doc_length / avg_length))

    for phrase in range(p):
        # p, c, p0c01, p0c02, p0c03, p0c11, p0c12, p0c13, p1c01, p1c02, p1c03..
        # So if we're interested in column <i>, the counts will be at indexes
        x_idx = 2 + (3 * column_index * (phrase + 1))
        term_freq = float(match_info[x_idx])
        term_matches = float(match_info[x_idx + 2])

        # The `max` check here is based on a suggestion in the Wikipedia
        # article. For terms that are common to a majority of documents, the
        # idf function can return negative values. Applying the max() here
        # weeds out those values.
        idf = max(
            math.log(
                (total_docs - term_matches + 0.5) /
                (term_matches + 0.5)),
            0)

        denom = term_freq + (k1 * D)
        if denom == 0:
            rhs = 0
        else:
            rhs = (term_freq * (k1 + 1)) / denom

        score += (idf * rhs)

    return score
