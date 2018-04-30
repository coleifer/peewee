import json
import math
import re
import struct
import sys

from peewee import *
from peewee import Alias
from peewee import EnclosedNodeList
from peewee import Entity
from peewee import Expression
from peewee import Function
from peewee import Node
from peewee import NodeList
from peewee import OP
from peewee import Select
from peewee import VirtualField
from peewee import merge_dict
from peewee import sort_models
from peewee import sqlite3
from peewee import text_type
try:
    from playhouse._sqlite_ext import (
        backup,
        backup_to_file,
        Blob,
        ConnectionHelper,
        register_bloomfilter,
        register_hash_functions,
        register_rank_functions,
        sqlite_get_db_status,
        sqlite_get_status,
        TableFunction,
        ZeroBlob,
    )
    CYTHON_SQLITE_EXTENSIONS = True
except ImportError:
    CYTHON_SQLITE_EXTENSIONS = False


if sys.version_info[0] == 3:
    basestring = str


FTS3_MATCHINFO = 'pcx'
FTS4_MATCHINFO = 'pcnalx'
if sqlite3 is not None:
    FTS_VERSION = 4 if sqlite3.sqlite_version_info[:3] >= (3, 7, 4) else 3
else:
    FTS_VERSION = 3

FTS5_MIN_SQLITE_VERSION = (3, 9, 0)


class RowIDField(AutoField):
    auto_increment = True
    column_name = name = required_name = 'rowid'

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


class JSONPath(Node):
    def __init__(self, path=None):
        self._path = path or []

    def __getitem__(self, idx):
        path = list(self._path)
        if isinstance(idx, int):
            path.append('[%s]' % idx)
        else:
            path.append('.%s' % idx)
        return JSONPath(path)
    __getattr__ = __getitem__

    def __sql__(self, ctx):
        return ctx.sql(Value('$%s' % ''.join(self._path)))

J = JSONPath()

class JSONField(TextField):
    field_type = 'JSON'

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
        if isinstance(path, JSONPath):
            return path
        if path.startswith('[') or not path:
            return '$%s' % path
        return '$.%s' % path

    def clean_paths(self, paths):
        return [self.clean_path(path) for path in paths]

    def length(self, *paths):
        if paths:
            return fn.json_array_length(self, *self.clean_paths(paths))
        return fn.json_array_length(self)

    def extract(self, *paths):
        return fn.json_extract(self, *self.clean_paths(paths))

    def __getitem__(self, path):
        if not isinstance(path, tuple):
            path = (path,)
        return self.extract(*path)

    def _value_for_insertion(self, value):
        if isinstance(value, (list, tuple, dict)):
            return fn.json(json.dumps(value))
        return value

    def _insert_like(self, fn, pairs, mapping):
        npairs = len(pairs)
        if npairs == 1 and isinstance(pairs[0], dict):
            # We were passed a single dictionary to update the field with.
            mapping.update(pairs[0])
            npairs = 0
        elif npairs % 2 != 0:
            raise ValueError('Unequal key and value parameters.')

        accum = []
        if npairs:
            for i in range(0, npairs, 2):
                accum.append(self.clean_path(pairs[i]))
                accum.append(self._value_for_insertion(pairs[i + 1]))
        if mapping:
            for key in mapping:
                val = mapping[key]
                accum.append(self.clean_path(key))
                accum.append(self._value_for_insertion(val))
        return fn(self, *accum)

    def insert(self, *pairs, **data):
        return self._insert_like(fn.json_insert, pairs, data)

    def replace(self, *pairs, **data):
        return self._insert_like(fn.json_replace, pairs, data)

    def set(self, *pairs, **data):
        return self._insert_like(fn.json_set, pairs, data)

    def remove(self, *paths):
        return fn.json_remove(self, *self.clean_paths(paths))

    def update(self, data):
        return fn.json_patch(self, self._value_for_insertion(data))

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
    def __init__(self, unindexed=False, column_name=None, **k):
        if k:
            raise ValueError('SearchField does not accept these keyword '
                             'arguments: %s.' % sorted(k))
        super(SearchField, self).__init__(unindexed=unindexed,
                                          column_name=column_name, null=True)


class VirtualTableSchemaManager(SchemaManager):
    def _create_virtual_table(self, safe=True, **options):
        options = self.model.clean_options(
            merge_dict(self.model._meta.options, options))

        # Structure:
        # CREATE VIRTUAL TABLE <model>
        # USING <extension_module>
        # ([prefix_arguments, ...] fields, ... [arguments, ...], [options...])
        ctx = self._create_context()
        ctx.literal('CREATE VIRTUAL TABLE ')
        if safe:
            ctx.literal('IF NOT EXISTS ')
        (ctx
         .sql(self.model)
         .literal(' USING '))

        ext_module = self.model._meta.extension_module
        if isinstance(ext_module, Node):
            return ctx.sql(ext_module)

        ctx.sql(SQL(ext_module)).literal(' ')
        arguments = []
        meta = self.model._meta

        if meta.prefix_arguments:
            arguments.extend([SQL(a) for a in meta.prefix_arguments])

        # Constraints, data-types, foreign and primary keys are all omitted.
        for field in meta.sorted_fields:
            if isinstance(field, (RowIDField)) or field._hidden:
                continue
            field_def = [Entity(field.column_name)]
            if field.unindexed:
                field_def.append(SQL('UNINDEXED'))
            arguments.append(NodeList(field_def))

        if meta.arguments:
            arguments.extend([SQL(a) for a in meta.arguments])

        if options:
            arguments.extend(self._create_table_option_sql(options))
        return ctx.sql(EnclosedNodeList(arguments))

    def _create_table(self, safe=True, **options):
        if issubclass(self.model, VirtualModel):
            return self._create_virtual_table(safe, **options)

        return super(VirtualTableSchemaManager, self)._create_table(
            safe, **options)


class VirtualModel(Model):
    class Meta:
        arguments = None
        extension_module = None
        prefix_arguments = None
        primary_key = False
        schema_manager_class = VirtualTableSchemaManager

    @classmethod
    def clean_options(cls, options):
        return options


class BaseFTSModel(VirtualModel):
    @classmethod
    def clean_options(cls, options):
        content = options.get('content')
        prefix = options.get('prefix')
        tokenize = options.get('tokenize')

        if isinstance(content, basestring) and content == '':
            # Special-case content-less full-text search tables.
            options['content'] = "''"
        elif isinstance(content, Field):
            # Special-case to ensure fields are fully-qualified.
            options['content'] = Entity(content.model._meta.table_name,
                                        content.column_name)

        if prefix:
            if isinstance(prefix, (list, tuple)):
                prefix = ','.join([str(i) for i in prefix])
            options['prefix'] = "'%s'" % prefix.strip("' ")

        if tokenize and cls._meta.extension_module.lower() == 'fts5':
            # Tokenizers need to be in quoted string for FTS5, but not for FTS3
            # or FTS4.
            options['tokenize'] = '"%s"' % tokenize

        return options


class FTSModel(BaseFTSModel):
    """
    VirtualModel class for creating tables that use either the FTS3 or FTS4
    search extensions. Peewee automatically determines which version of the
    FTS extension is supported and will use FTS4 if possible.
    """
    # FTS3/4 uses "docid" in the same way a normal table uses "rowid".
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
    def bm25f(cls, *weights):
        match_info = fn.matchinfo(cls._meta.entity, FTS4_MATCHINFO)
        return fn.fts_bm25f(match_info, *weights)

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
    def search_bm25f(cls, term, weights=None, with_score=False,
                     score_alias='score', explicit_ordering=False):
        """Full-text search for selected `term` using BM25 algorithm."""
        return cls._search(
            term,
            weights,
            with_score,
            score_alias,
            cls.bm25f,
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


_alphabet = 'abcdefghijklmnopqrstuvwxyz'
_alphanum = (set('\t ,"(){}*:_+0123456789') |
             set(_alphabet) |
             set(_alphabet.upper()) |
             set((chr(26),)))
_invalid_ascii = set(chr(p) for p in range(128) if chr(p) not in _alphanum)
_quote_re = re.compile('(?:[^\s"]|"(?:\\.|[^"])*")+')


class FTS5Model(BaseFTSModel):
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
    # FTS5 does not support declared primary keys, but we can use the
    # implicit rowid.
    rowid = RowIDField()

    class Meta:
        extension_module = 'fts5'

    _error_messages = {
        'field_type': ('Besides the implicit `rowid` column, all columns must '
                       'be instances of SearchField'),
        'index': 'Secondary indexes are not supported for FTS5 models',
        'pk': 'FTS5 models must use the default `rowid` primary key',
    }

    @classmethod
    def validate_model(cls):
        # Perform FTS5-specific validation and options post-processing.
        if cls._meta.primary_key.name != 'rowid':
            raise ImproperlyConfigured(cls._error_messages['pk'])
        for field in cls._meta.fields.values():
            if not isinstance(field, (SearchField, RowIDField)):
                raise ImproperlyConfigured(cls._error_messages['field_type'])
        if cls._meta.indexes:
            raise ImproperlyConfigured(cls._error_messages['index'])

    @classmethod
    def fts5_installed(cls):
        if sqlite3.sqlite_version_info[:3] < FTS5_MIN_SQLITE_VERSION:
            return False

        # Test in-memory DB to determine if the FTS5 extension is installed.
        tmp_db = sqlite3.connect(':memory:')
        try:
            tmp_db.execute('CREATE VIRTUAL TABLE fts5test USING fts5 (data);')
        except:
            try:
                tmp_db.enable_load_extension(True)
                tmp_db.load_extension('fts5')
            except:
                return False
            else:
                cls._meta.database.load_extension('fts5')
        finally:
            tmp_db.close()

        return True

    @staticmethod
    def validate_query(query):
        """
        Simple helper function to indicate whether a search query is a
        valid FTS5 query. Note: this simply looks at the characters being
        used, and is not guaranteed to catch all problematic queries.
        """
        tokens = _quote_re.findall(query)
        for token in tokens:
            if token.startswith('"') and token.endswith('"'):
                continue
            if set(token) & _invalid_ascii:
                return False
        return True

    @staticmethod
    def clean_query(query, replace=chr(26)):
        """
        Clean a query of invalid tokens.
        """
        accum = []
        any_invalid = False
        tokens = _quote_re.findall(query)
        for token in tokens:
            if token.startswith('"') and token.endswith('"'):
                accum.append(token)
                continue
            token_set = set(token)
            invalid_for_token = token_set & _invalid_ascii
            if invalid_for_token:
                any_invalid = True
                for c in invalid_for_token:
                    token = token.replace(c, replace)
            accum.append(token)

        if any_invalid:
            return ' '.join(accum)
        return query

    @classmethod
    def match(cls, term):
        """
        Generate a `MATCH` expression appropriate for searching this table.
        """
        return match(cls._meta.entity, term)

    @classmethod
    def rank(cls, *args):
        if args:
            return cls.bm25(*args)
        else:
            return SQL('rank')

    @classmethod
    def bm25(cls, *weights):
        return fn.bm25(cls._meta.entity, *weights)

    @classmethod
    def search(cls, term, weights=None, with_score=False, score_alias='score',
               explicit_ordering=False):
        """Full-text search using selected `term`."""
        return cls.search_bm25(
            FTS5Model.clean_query(term),
            weights,
            with_score,
            score_alias,
            explicit_ordering)

    @classmethod
    def search_bm25(cls, term, weights=None, with_score=False,
                    score_alias='score', explicit_ordering=False):
        """Full-text search using selected `term`."""
        if not weights:
            rank = SQL('rank')
        elif isinstance(weights, dict):
            weight_args = []
            for field in cls._meta.sorted_fields:
                if isinstance(field, SearchField) and not field.unindexed:
                    weight_args.append(
                        weights.get(field, weights.get(field.name, 1.0)))
            rank = fn.bm25(cls._meta.entity, *weight_args)
        else:
            rank = fn.bm25(cls._meta.entity, *weights)

        selection = ()
        order_by = rank
        if with_score:
            selection = (cls, rank.alias(score_alias))
        if with_score and not explicit_ordering:
            order_by = SQL(score_alias)

        return (cls
                .select(*selection)
                .where(cls.match(FTS5Model.clean_query(term)))
                .order_by(order_by))

    @classmethod
    def _fts_cmd(cls, cmd, **extra_params):
        tbl = cls._meta.entity
        columns = [tbl]
        values = [cmd]
        for key, value in extra_params.items():
            columns.append(Entity(key))
            values.append(value)

        inner_clause = EnclosedClause(tbl)
        clause = Clause(
            SQL('INSERT INTO'),
            cls._meta.entity,
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
    def VocabModel(cls, table_type='row', table=None):
        if table_type not in ('row', 'col', 'instance'):
            raise ValueError('table_type must be either "row", "col" or '
                             '"instance".')

        attr = '_vocab_model_%s' % table_type

        if not hasattr(cls, attr):
            class Meta:
                database = cls._meta.database
                table_name = table or cls._meta.table_name + '_v'
                extension_module = fn.fts5vocab(
                    cls._meta.entity,
                    SQL(table_type))

            attrs = {
                'term': VirtualField(TextField),
                'doc': IntegerField(),
                'cnt': IntegerField(),
                'rowid': RowIDField(),
                'Meta': Meta,
            }
            if table_type == 'col':
                attrs['col'] = VirtualField(TextField)
            elif table_type == 'instance':
                attrs['offset'] = VirtualField(IntegerField)

            class_name = '%sVocab' % cls.__name__
            setattr(cls, attr, type(class_name, (VirtualModel,), attrs))

        return getattr(cls, attr)


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


class LSMTable(VirtualModel):
    class Meta:
        extension_module = 'lsm1'
        filename = None

    @classmethod
    def clean_options(cls, options):
        filename = cls._meta.filename
        if not filename:
            raise ValueError('LSM1 extension requires that you specify a '
                             'filename for the LSM database.')
        else:
            if len(filename) >= 2 and filename[0] != '"':
                filename = '"%s"' % filename
        if not cls._meta.primary_key:
            raise ValueError('LSM1 models must specify a primary-key field.')

        key = cls._meta.primary_key
        if isinstance(key, AutoField):
            raise ValueError('LSM1 models must explicitly declare a primary '
                             'key field.')
        if not isinstance(key, (TextField, BlobField, IntegerField)):
            raise ValueError('LSM1 key must be a TextField, BlobField, or '
                             'IntegerField.')
        key._hidden = True
        if isinstance(key, IntegerField):
            data_type = 'UINT'
        elif isinstance(key, BlobField):
            data_type = 'BLOB'
        else:
            data_type = 'TEXT'
        cls._meta.prefix_arguments = [filename, '"%s"' % key.name, data_type]

        # Does the key map to a scalar value, or a tuple of values?
        if len(cls._meta.sorted_fields) == 2:
            cls._meta._value_field = cls._meta.sorted_fields[1]
        else:
            cls._meta._value_field = None

        return options

    @classmethod
    def load_extension(cls, path='lsm.so'):
        cls._meta.database.load_extension(path)

    @staticmethod
    def slice_to_expr(key, idx):
        if idx.start is not None and idx.stop is not None:
            return key.between(idx.start, idx.stop)
        elif idx.start is not None:
            return key >= idx.start
        elif idx.stop is not None:
            return key <= idx.stop

    @staticmethod
    def _apply_lookup_to_query(query, key, lookup):
        if isinstance(lookup, slice):
            expr = LSMTable.slice_to_expr(key, lookup)
            if expr is not None:
                query = query.where(expr)
            return query, False
        elif isinstance(lookup, Expression):
            return query.where(lookup), False
        else:
            return query.where(key == lookup), True

    @classmethod
    def get_by_id(cls, pk):
        query, is_single = cls._apply_lookup_to_query(
            cls.select().namedtuples(),
            cls._meta.primary_key,
            pk)

        if is_single:
            try:
                row = query.get()
            except cls.DoesNotExist:
                raise KeyError(pk)
            return row[1] if cls._meta._value_field is not None else row
        else:
            return query

    @classmethod
    def set_by_id(cls, key, value):
        if cls._meta._value_field is not None:
            data = {cls._meta._value_field: value}
        elif isinstance(value, tuple):
            data = {}
            for field, fval in zip(cls._meta.sorted_fields[1:], value):
                data[field] = fval
        elif isinstance(value, dict):
            data = value
        elif isinstance(value, cls):
            data = value.__dict__
        data[cls._meta.primary_key] = key
        cls.replace(data).execute()

    @classmethod
    def delete_by_id(cls, pk):
        query, is_single = cls._apply_lookup_to_query(
            cls.delete(),
            cls._meta.primary_key,
            pk)
        return query.execute()


OP.MATCH = 'MATCH'

def _sqlite_regexp(regex, value):
    return re.search(regex, value, re.I) is not None


class SqliteExtDatabase(SqliteDatabase):
    def __init__(self, database, c_extensions=None, rank_functions=True,
                 hash_functions=False, regexp_function=False,
                 bloomfilter=False, json_contains=False, *args, **kwargs):
        super(SqliteExtDatabase, self).__init__(database, *args, **kwargs)
        self._row_factory = None

        if c_extensions and not CYTHON_SQLITE_EXTENSIONS:
            raise ImproperlyConfigured('SqliteExtDatabase initialized with '
                                       'C extensions, but shared library was '
                                       'not found!')
        prefer_c = CYTHON_SQLITE_EXTENSIONS and (c_extensions is not False)
        if rank_functions:
            if prefer_c:
                register_rank_functions(self)
            else:
                self.register_function(bm25, 'fts_bm25')
                self.register_function(rank, 'fts_rank')
                self.register_function(bm25, 'fts_bm25f')  # Fall back to bm25.
                self.register_function(bm25, 'fts_lucene')
        if hash_functions:
            if not prefer_c:
                raise ValueError('C extension required to register hash '
                                 'functions.')
            register_hash_functions(self)
        if regexp_function:
            self.register_function(_sqlite_regexp, 'regexp', 2)
        if bloomfilter:
            if not prefer_c:
                raise ValueError('C extension required to use bloomfilter.')
            register_bloomfilter(self)
        if json_contains:
            self.register_function(_json_contains, 'json_contains')

        self._c_extensions = prefer_c

    def _add_conn_hooks(self, conn):
        super(SqliteExtDatabase, self)._add_conn_hooks(conn)
        if self._row_factory:
            conn.row_factory = self._row_factory

    def row_factory(self, fn):
        self._row_factory = fn


if CYTHON_SQLITE_EXTENSIONS:
    SQLITE_STATUS_MEMORY_USED = 0
    SQLITE_STATUS_PAGECACHE_USED = 1
    SQLITE_STATUS_PAGECACHE_OVERFLOW = 2
    SQLITE_STATUS_SCRATCH_USED = 3
    SQLITE_STATUS_SCRATCH_OVERFLOW = 4
    SQLITE_STATUS_MALLOC_SIZE = 5
    SQLITE_STATUS_PARSER_STACK = 6
    SQLITE_STATUS_PAGECACHE_SIZE = 7
    SQLITE_STATUS_SCRATCH_SIZE = 8
    SQLITE_STATUS_MALLOC_COUNT = 9
    SQLITE_DBSTATUS_LOOKASIDE_USED = 0
    SQLITE_DBSTATUS_CACHE_USED = 1
    SQLITE_DBSTATUS_SCHEMA_USED = 2
    SQLITE_DBSTATUS_STMT_USED = 3
    SQLITE_DBSTATUS_LOOKASIDE_HIT = 4
    SQLITE_DBSTATUS_LOOKASIDE_MISS_SIZE = 5
    SQLITE_DBSTATUS_LOOKASIDE_MISS_FULL = 6
    SQLITE_DBSTATUS_CACHE_HIT = 7
    SQLITE_DBSTATUS_CACHE_MISS = 8
    SQLITE_DBSTATUS_CACHE_WRITE = 9
    SQLITE_DBSTATUS_DEFERRED_FKS = 10
    #SQLITE_DBSTATUS_CACHE_USED_SHARED = 11

    def __status__(flag, return_highwater=False):
        """
        Expose a sqlite3_status() call for a particular flag as a property of the
        Database object.
        """
        def getter(self):
            result = sqlite_get_status(flag)
            return result[1] if return_highwater else result
        return property(getter)

    def __dbstatus__(flag, return_highwater=False, return_current=False):
        """
        Expose a sqlite3_dbstatus() call for a particular flag as a property of the
        Database instance. Unlike sqlite3_status(), the dbstatus properties pertain
        to the current connection.
        """
        def getter(self):
            result = sqlite_get_db_status(self._state.conn, flag)
            if return_current:
                return result[0]
            return result[1] if return_highwater else result
        return property(getter)

    class CSqliteExtDatabase(SqliteExtDatabase):
        def __init__(self, *args, **kwargs):
            self._conn_helper = None
            self._commit_hook = self._rollback_hook = self._update_hook = None
            self._replace_busy_handler = False
            super(CSqliteExtDatabase, self).__init__(*args, **kwargs)

        def init(self, database, replace_busy_handler=False, **kwargs):
            super(CSqliteExtDatabase, self).init(database, **kwargs)
            self._replace_busy_handler = replace_busy_handler

        def _close(self, conn):
            if self._commit_hook:
                self._conn_helper.set_commit_hook(None)
            if self._rollback_hook:
                self._conn_helper.set_rollback_hook(None)
            if self._update_hook:
                self._conn_helper.set_update_hook(None)
            return super(CSqliteExtDatabase, self)._close(conn)

        def _add_conn_hooks(self, conn):
            super(CSqliteExtDatabase, self)._add_conn_hooks(conn)
            self._conn_helper = ConnectionHelper(conn)
            if self._commit_hook is not None:
                self._conn_helper.set_commit_hook(self._commit_hook)
            if self._rollback_hook is not None:
                self._conn_helper.set_rollback_hook(self._rollback_hook)
            if self._update_hook is not None:
                self._conn_helper.set_update_hook(self._update_hook)
            if self._replace_busy_handler:
                self._conn_helper.set_busy_handler(self.timeout or 5000)

        def on_commit(self, fn):
            self._commit_hook = fn
            if not self.is_closed():
                self._conn_helper.set_commit_hook(fn)
            return fn

        def on_rollback(self, fn):
            self._rollback_hook = fn
            if not self.is_closed():
                self._conn_helper.set_rollback_hook(fn)
            return fn

        def on_update(self, fn):
            self._update_hook = fn
            if not self.is_closed():
                self._conn_helper.set_update_hook(fn)
            return fn

        def changes(self):
            return self._conn_helper.changes()

        @property
        def last_insert_rowid(self):
            return self._conn_helper.last_insert_rowid()

        @property
        def autocommit(self):
            return self._conn_helper.autocommit()

        def backup(self, destination):
            return backup(self.connection(), destination.connection())

        def backup_to_file(self, filename):
            return backup_to_file(self.connection(), filename)

        def blob_open(self, table, column, rowid, read_only=False):
            return Blob(self, table, column, rowid, read_only)

        # Status properties.
        memory_used = __status__(SQLITE_STATUS_MEMORY_USED)
        malloc_size = __status__(SQLITE_STATUS_MALLOC_SIZE, True)
        malloc_count = __status__(SQLITE_STATUS_MALLOC_COUNT)
        pagecache_used = __status__(SQLITE_STATUS_PAGECACHE_USED)
        pagecache_overflow = __status__(SQLITE_STATUS_PAGECACHE_OVERFLOW)
        pagecache_size = __status__(SQLITE_STATUS_PAGECACHE_SIZE, True)
        scratch_used = __status__(SQLITE_STATUS_SCRATCH_USED)
        scratch_overflow = __status__(SQLITE_STATUS_SCRATCH_OVERFLOW)
        scratch_size = __status__(SQLITE_STATUS_SCRATCH_SIZE, True)

        # Connection status properties.
        lookaside_used = __dbstatus__(SQLITE_DBSTATUS_LOOKASIDE_USED)
        lookaside_hit = __dbstatus__(SQLITE_DBSTATUS_LOOKASIDE_HIT, True)
        lookaside_miss = __dbstatus__(SQLITE_DBSTATUS_LOOKASIDE_MISS_SIZE,
                                      True)
        lookaside_miss_full = __dbstatus__(SQLITE_DBSTATUS_LOOKASIDE_MISS_FULL,
                                           True)
        cache_used = __dbstatus__(SQLITE_DBSTATUS_CACHE_USED, False, True)
        #cache_used_shared = __dbstatus__(SQLITE_DBSTATUS_CACHE_USED_SHARED,
        #                                 False, True)
        schema_used = __dbstatus__(SQLITE_DBSTATUS_SCHEMA_USED, False, True)
        statement_used = __dbstatus__(SQLITE_DBSTATUS_STMT_USED, False, True)
        cache_hit = __dbstatus__(SQLITE_DBSTATUS_CACHE_HIT, False, True)
        cache_miss = __dbstatus__(SQLITE_DBSTATUS_CACHE_MISS, False, True)
        cache_write = __dbstatus__(SQLITE_DBSTATUS_CACHE_WRITE, False, True)


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


def _json_contains(src_json, obj_json):
    stack = []
    try:
        stack.append((json.loads(obj_json), json.loads(src_json)))
    except:
        # Invalid JSON!
        return False

    while stack:
        obj, src = stack.pop()
        if isinstance(src, dict):
            if isinstance(obj, dict):
                for key in obj:
                    if key not in src:
                        return False
                    stack.append((obj[key], src[key]))
            elif isinstance(obj, list):
                for item in obj:
                    if item not in src:
                        return False
            elif obj not in src:
                return False
        elif isinstance(src, list):
            if isinstance(obj, dict):
                return False
            elif isinstance(obj, list):
                try:
                    for i in range(len(obj)):
                        stack.append((obj[i], src[i]))
                except IndexError:
                    return False
            elif obj not in src:
                return False
        elif obj != src:
            return False
    return True
