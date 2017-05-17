import json
import math
import struct
import sys

from peewee import *
from peewee import sqlite3
try:
    from playhouse._sqlite_ext import peewee_bm25 as cy_bm25
    from playhouse._sqlite_ext import peewee_lucene as cy_lucene
    from playhouse._sqlite_ext import peewee_murmurhash as cy_murmurhash
    from playhouse._sqlite_ext import peewee_rank as cy_rank
    CYTHON_SQLITE_EXTENSIONS = True
except ImportError:
    CYTHON_SQLITE_EXTENSIONS = False


if sys.version_info[0] == 3:
    basestring = str


FTS3_MATCHINFO = 'pcx'
FTS4_MATCHINFO = 'pcnalx'
FTS_VERSION = 4 if sqlite3.sqlite_version_info[:3] >= (3, 7, 4) else 3


class RowIDField(VirtualField):
    auto_increment = True
    column_name = name = required_name = 'rowid'
    field_class = AutoField

    def __init__(self, *args, **kwargs):
        kwargs['primary_key'] = True
        super(RowIDField, self).__init__(*args, **kwargs)

    def bind(self, model, name, *args):
        if name != self.required_name:
            raise ValueError('%s must be named "%s".' %
                             (type(self), self.required_name))
        super(RowIDField, self).bind(model, name, *args)


class DocIDField(RowIDField):
    column_name = name = required_name = 'docid'


class AutoIncrementField(AutoField):
    def ddl(self, ctx):
        node_list = super(AutoIncrementField, self).ddl(ctx)
        return NodeList((node_list, SQL('AUTOINCREMENT')))


class JSONField(TextField):
    def python_value(self, value):
        if value is not None:
            try:
                return json.loads(value)
            except (TypeError, ValueError):
                return value

    def db_value(self, value):
        if value is not None:
            return json.dumps(value)

    def clean_path(self, path):
        if path.startswith('[') or not path:
            return '$%s' % path
        return '$.%s' % path

    def length(self, path=None):
        if path:
            return fn.json_array_length(self, self.clean_path(path))
        return fn.json_array_length(self)

    def extract(self, path):
        return fn.json_extract(self, self.clean_path(path))

    def _value_for_insertion(self, value):
        if isinstance(value, (list, tuple, dict)):
            return fn.json(json.dumps(value))
        return value

    def _insert_like(self, fn, pairs):
        npairs = len(pairs)
        if npairs % 2 != 0:
            raise ValueError('Unequal key and value parameters.')
        accum = []
        for i in range(0, npairs, 2):
            accum.append(self.clean_path(pairs[i]))
            accum.append(self._value_for_insertion(pairs[i + 1]))
        return fn(self, *accum)

    def insert(self, *pairs):
        return self._insert_like(fn.json_insert, pairs)

    def replace(self, *pairs):
        return self._insert_like(fn.json_replace, pairs)

    def set(self, *pairs):
        return self._insert_like(fn.json_set, pairs)

    def remove(self, *paths):
        return fn.json_remove(self, *[self.clean_path(path) for path in paths])

    def json_type(self, path=None):
        if path:
            return fn.json_type(self, self.clean_path(path))
        return fn.json_type(self)

    def children(self, path=None):
        """
        Schema of `json_each` and `json_tree`:

        key,
        value,
        type TEXT (object, array, string, etc),
        atom (value for primitive/scalar types, NULL for array and object)
        id INTEGER (unique identifier for element)
        parent INTEGER (unique identifier of parent element or NULL)
        fullkey TEXT (full path describing element)
        path TEXT (path to the container of the current element)
        json JSON hidden (1st input parameter to function)
        root TEXT hidden (2nd input parameter, path at which to start)
        """
        if path:
            return fn.json_each(self, self.clean_path(path))
        return fn.json_each(self)

    def tree(self, path=None):
        if path:
            return fn.json_tree(self, self.clean_path(path))
        return fn.json_tree(self)


class SearchField(Field):
    def __init__(self, unindexed=False, column_name=None, coerce=None, **k):
        if k:
            raise ValueError('SearchField does not accept these keyword '
                             'arguments: %s.' % sorted(k))
        super(SearchField, self).__init__(unindexed=unindexed, coerce=coerce,
                                          column_name=column_name, null=True)


class VirtualTableSchemaManager(SchemaManager):
    def _create_virtual_table(self, safe=True, **options):
        ctx = self._create_context()
        ctx.literal('CREATE VIRTUAL TABLE ')
        if safe:
            ctx.literal('IF NOT EXISTS ')
        (ctx
         .sql(self.model)
         .literal(' USING %s ' % self.model._meta.extension_module))

        arguments = []
        meta = self.model._meta

        # Constraints, data-types, foreign and primary keys are all omitted.
        for field in meta.sorted_fields:
            field_def = [Entity(field.column_name)]
            if field.unindexed:
                field_def.append(SQL('UNINDEXED'))
            arguments.append(NodeList(field_def))

        options = self.model.clean_options(
            merge_dict(self.model._meta.options, options))
        if options:
            arguments.extend(self._create_table_option_sql(options))
        return ctx.sql(EnclosedNodeList(arguments))

    def _create_table(self, safe=True, **options):
        if issubclass(self.model, VirtualModel):
            ctx = self._create_virtual_table(safe, **options)
        else:
            ctx = super(VirtualTableSchemaManager, self)._create_table(
                safe, **options)
        if getattr(self.model._meta, 'without_rowid', False):
            ctx.literal(' WITHOUT ROWID')
        return ctx


class VirtualModel(Model):
    class Meta:
        extension_module = None
        primary_key = False
        schema_manager_class = VirtualTableSchemaManager

    @classmethod
    def clean_options(cls, options):
        return options


class BaseFTSModel(VirtualModel):
    @classmethod
    def clean_options(cls, options):
        tokenize = options.get('tokenize')
        content = options.get('content')
        if tokenize:
            # Tokenizers need to be in quoted string.
            options['tokenize'] = '"%s"' % tokenize
        if isinstance(content, basestring) and content == '':
            # Special-case content-less full-text search tables.
            options['content'] = "''"
        elif isinstance(content, Field):
            # Special-case to ensure fields are fully-qualified.
            options['content'] = Entity(content.model._meta.table_name,
                                        content.column_name)
        return options


class FTSModel(BaseFTSModel):
    """
    VirtualModel class for creating tables that use either the FTS3 or FTS4
    search extensions. Peewee automatically determines which version of the
    FTS extension is supported and will use FTS4 if possible.

    Note: because FTS5 is significantly different from FTS3 and FTS4, there is
    a separate model class for FTS5 virtual tables.
    """
    # FTS3/4 does not support declared primary keys, but we can use the
    # implicit docid.
    docid = DocIDField()

    class Meta:
        extension_module = 'FTS%s' % FTS_VERSION

    @classmethod
    def _fts_cmd(cls, cmd):
        tbl = cls._meta.table_name
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
        return match(cls._meta.entity, term)

    @classmethod
    def rank(cls, *weights):
        matchinfo = fn.matchinfo(cls._meta.entity, FTS3_MATCHINFO)
        return fn.fts_rank(matchinfo, *weights)

    @classmethod
    def bm25(cls, *weights):
        match_info = fn.matchinfo(cls._meta.entity, FTS4_MATCHINFO)
        return fn.fts_bm25(match_info, *weights)

    @classmethod
    def lucene(cls, *weights):
        match_info = fn.matchinfo(cls._meta.entity, FTS4_MATCHINFO)
        return fn.fts_lucene(match_info, *weights)

    @classmethod
    def _search(cls, term, weights, with_score, score_alias, score_fn,
                explicit_ordering):
        if not weights:
            rank = score_fn()
        elif isinstance(weights, dict):
            weight_args = []
            for field in cls._meta.sorted_fields:
                # Attempt to get the specified weight of the field by looking
                # it up using it's field instance followed by name.
                field_weight = weights.get(field, weights.get(field.name, 1.0))
                weight_args.append(field_weight)
            rank = score_fn(*weight_args)
        else:
            rank = score_fn(*weights)

        selection = ()
        order_by = rank
        if with_score:
            selection = (cls, rank.alias(score_alias))
        if with_score and not explicit_ordering:
            order_by = SQL(score_alias)

        return (cls
                .select(*selection)
                .where(cls.match(term))
                .order_by(order_by))

    @classmethod
    def search(cls, term, weights=None, with_score=False, score_alias='score',
               explicit_ordering=False):
        """Full-text search using selected `term`."""
        return cls._search(
            term,
            weights,
            with_score,
            score_alias,
            cls.rank,
            explicit_ordering)

    @classmethod
    def search_bm25(cls, term, weights=None, with_score=False,
                    score_alias='score', explicit_ordering=False):
        """Full-text search for selected `term` using BM25 algorithm."""
        return cls._search(
            term,
            weights,
            with_score,
            score_alias,
            cls.bm25,
            explicit_ordering)

    @classmethod
    def search_lucene(cls, term, weights=None, with_score=False,
                      score_alias='score', explicit_ordering=False):
        """Full-text search for selected `term` using BM25 algorithm."""
        return cls._search(
            term,
            weights,
            with_score,
            score_alias,
            cls.lucene,
            explicit_ordering)


def ClosureTable(model_class, foreign_key=None, referencing_class=None,
                 referencing_key=None):
    """Model factory for the transitive closure extension."""
    if referencing_class is None:
        referencing_class = model_class

    if foreign_key is None:
        for field_obj in model_class._meta.refs:
            if field_obj.rel_model is model_class:
                foreign_key = field_obj
                break
        else:
            raise ValueError('Unable to find self-referential foreign key.')

    source_key = model_class._meta.primary_key
    if referencing_key is None:
        referencing_key = source_key

    class BaseClosureTable(VirtualModel):
        depth = VirtualField(IntegerField)
        id = VirtualField(IntegerField)
        idcolumn = VirtualField(TextField)
        parentcolumn = VirtualField(TextField)
        root = VirtualField(IntegerField)
        tablename = VirtualField(TextField)

        class Meta:
            extension_module = 'transitive_closure'

        @classmethod
        def descendants(cls, node, depth=None, include_node=False):
            query = (model_class
                     .select(model_class, cls.depth.alias('depth'))
                     .join(cls, on=(source_key == cls.id))
                     .where(cls.root == node)
                     .objects())
            if depth is not None:
                query = query.where(cls.depth == depth)
            elif not include_node:
                query = query.where(cls.depth > 0)
            return query

        @classmethod
        def ancestors(cls, node, depth=None, include_node=False):
            query = (model_class
                     .select(model_class, cls.depth.alias('depth'))
                     .join(cls, on=(source_key == cls.root))
                     .where(cls.id == node)
                     .objects())
            if depth:
                query = query.where(cls.depth == depth)
            elif not include_node:
                query = query.where(cls.depth > 0)
            return query

        @classmethod
        def siblings(cls, node, include_node=False):
            if referencing_class is model_class:
                # self-join
                fk_value = node.__data__.get(foreign_key.name)
                query = model_class.select().where(foreign_key == fk_value)
            else:
                # siblings as given in reference_class
                siblings = (referencing_class
                            .select(referencing_key)
                            .join(cls, on=(foreign_key == cls.root))
                            .where((cls.id == node) & (cls.depth == 1)))

                # the according models
                query = (model_class
                         .select()
                         .where(source_key << siblings)
                         .objects())

            if not include_node:
                query = query.where(source_key != node)

            return query

    class Meta:
        database = referencing_class._meta.database
        options = {
            'tablename': referencing_class._meta.table_name,
            'idcolumn': referencing_key.column_name,
            'parentcolumn': foreign_key.column_name}
        primary_key = False

    name = '%sClosure' % model_class.__name__
    return type(name, (BaseClosureTable,), {'Meta': Meta})


OP.MATCH = 'MATCH'


class SqliteExtDatabase(SqliteDatabase):
    operations = {OP.MATCH: 'MATCH'}

    def __init__(self, database, c_extensions=None, *args, **kwargs):
        super(SqliteExtDatabase, self).__init__(database, *args, **kwargs)
        self._aggregates = {}
        self._collations = {}
        self._functions = {}
        self._extensions = set()
        self._row_factory = None

        if c_extensions and not CYTHON_SQLITE_EXTENSIONS:
            raise ImproperlyConfigured('SqliteExtDatabase initialized with '
                                       'C extensions, but shared library was '
                                       'not found!')
        elif CYTHON_SQLITE_EXTENSIONS and (c_extensions is not False):
            self.register_function(cy_bm25, 'fts_bm25', -1)
            self.register_function(cy_lucene, 'fts_lucene', -1)
            self.register_function(cy_murmurhash, 'murmurhash', -1)
            self.register_function(cy_rank, 'fts_rank', -1)
            self._c_extensions = True
        else:
            self.register_function(bm25, 'fts_bm25', -1)
            self.register_function(rank, 'fts_rank', -1)
            self._c_extensions = False

    def _add_conn_hooks(self, conn):
        super(SqliteExtDatabase, self)._add_conn_hooks(conn)
        self._load_aggregates(conn)
        self._load_collations(conn)
        self._load_functions(conn)
        if self._row_factory:
            conn.row_factory = self._row_factory
        if self._extensions:
            self._load_extensions(conn)

    def _load_aggregates(self, conn):
        for name, (klass, num_params) in self._aggregates.items():
            conn.create_aggregate(name, num_params, klass)

    def _load_collations(self, conn):
        for name, fn in self._collations.items():
            conn.create_collation(name, fn)

    def _load_functions(self, conn):
        for name, (fn, num_params) in self._functions.items():
            conn.create_function(name, num_params, fn)

    def _load_extensions(self, conn):
        conn.enable_load_extension(True)
        for extension in self._extensions:
            conn.load_extension(extension)

    def register_aggregate(self, klass, name=None, num_params=-1):
        self._aggregates[name or klass.__name__.lower()] = (klass, num_params)
        if not self.is_closed():
            self._load_aggregates(self.connection())

    def aggregate(self, name=None, num_params=-1):
        def decorator(klass):
            self.register_aggregate(klass, name, num_params)
            return klass
        return decorator

    def register_collation(self, fn, name=None):
        name = name or fn.__name__
        def _collation(*args):
            expressions = args + (SQL('collate %s' % name),)
            return NodeList(expressions)
        fn.collation = _collation
        self._collations[name] = fn
        if not self.is_closed():
            self._load_collations(self.connection())

    def collation(self, name=None):
        def decorator(fn):
            self.register_collation(fn, name)
            return fn
        return decorator

    def register_function(self, fn, name=None, num_params=-1):
        self._functions[name or fn.__name__] = (fn, num_params)
        if not self.is_closed():
            self._load_functions(self.connection())

    def func(self, name=None, num_params=-1):
        def decorator(fn):
            self.register_function(fn, name, num_params)
            return fn
        return decorator

    def load_extension(self, extension):
        self._extensions.add(extension)
        if not self.is_closed():
            conn = self.connection()
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


def match(lhs, rhs):
    return Expression(lhs, OP.MATCH, rhs)

def _parse_match_info(buf):
    # See http://sqlite.org/fts3.html#matchinfo
    bufsize = len(buf)  # Length in bytes.
    return [struct.unpack('@I', buf[i:i+4])[0] for i in range(0, bufsize, 4)]

# Ranking implementation, which parse matchinfo.
def rank(raw_match_info, *raw_weights):
    # Handle match_info called w/default args 'pcx' - based on the example rank
    # function http://sqlite.org/fts3.html#appendix_a
    match_info = _parse_match_info(raw_match_info)
    score = 0.0

    p, c = match_info[:2]
    if not raw_weights:
        weights = [1] * c
    else:
        weights = [0] * c
        for i, weight in enumerate(raw_weights):
            weights[i] = weight

    for phrase_num in range(p):
        phrase_info_idx = 2 + (phrase_num * c * 3)
        for col_num in range(c):
            weight = weights[col_num]
            if not weight:
                continue

            col_idx = phrase_info_idx + (col_num * 3)
            x1, x2 = match_info[col_idx:col_idx + 2]
            if x1 > 0:
                score += weight * (float(x1) / x2)

    return -score

# Okapi BM25 ranking implementation (FTS4 only).
def bm25(raw_match_info, *args):
    """
    Usage:

        # Format string *must* be pcnalx
        # Second parameter to bm25 specifies the index of the column, on
        # the table being queries.
        bm25(matchinfo(document_tbl, 'pcnalx'), 1) AS rank
    """
    match_info = _parse_match_info(raw_match_info)
    K = 1.2
    B = 0.75
    score = 0.0

    P_O, C_O, N_O, A_O = range(4)
    term_count = match_info[P_O]
    col_count = match_info[C_O]
    total_docs = match_info[N_O]
    L_O = A_O + col_count
    X_O = L_O + col_count

    if not args:
        weights = [1] * col_count
    else:
        weights = [0] * col_count
        for i, weight in enumerate(args):
            weights[i] = args[i]

    for i in range(term_count):
        for j in range(col_count):
            weight = weights[j]
            if weight == 0:
                continue

            avg_length = float(match_info[A_O + j])
            doc_length = float(match_info[L_O + j])
            if avg_length == 0:
                D = 0
            else:
                D = 1 - B + (B * (doc_length / avg_length))

            x = X_O + (3 * j * (i + 1))
            term_frequency = float(match_info[x])
            docs_with_term = float(match_info[x + 2])

            idf = max(
                math.log(
                    (total_docs - docs_with_term + 0.5) /
                    (docs_with_term + 0.5)),
                0)
            denom = term_frequency + (K * D)
            if denom == 0:
                rhs = 0
            else:
                rhs = (term_frequency * (K + 1)) / denom

            score += (idf * rhs) * weight

    return -score
