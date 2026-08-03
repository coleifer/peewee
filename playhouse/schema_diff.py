"""
Diff database schema against model definitions.

Detects basic changes:

* tables to create
    Tables in the database that no model covers are ignored, and tables
    are never proposed for dropping.
* columns to add/drop
    Column diff does not introspect types/nullability/defaults/constraints.
    Renames are shown as an add + drop.
* indexes to add/drop
    Index diff looks at columns being indexed and unique flag. Partial and
    expression indexes are compared by name only.

Usage::

    diff = diff_models(db, [User, Tweet])
    if diff:
        print(diff)

Each attribute of the result maps directly onto a SchemaMigrator call:

* ``create_tables``: model classes (in dependency order)
* ``add_columns``: model fields to add
* ``drop_columns``: list of ``(table, column name)``
* ``add_indexes``: list of :class:`IndexDiff`
* ``drop_indexes``: list of :class:`IndexDiff`
"""
import re
from collections import namedtuple

from peewee import *
from peewee import sort_models

__all__ = ['IndexDiff', 'SchemaDiff', 'diff_models']


_IndexDiff = namedtuple('_IndexDiff', (
    'table',
    'name',
    'columns',
    'unique'))

class IndexDiff(_IndexDiff):
    __slots__ = ()

    def display(self, op):
        if self.columns is None:
            return '%s index %s.%s' % (op, self.table, self.name)
        return '%s index %s%s (%s)%s' % (
            op, self.table, '.%s' % self.name if self.name else '',
            ', '.join(self.columns), ' unique' if self.unique else '')


_SchemaDiff = namedtuple('_SchemaDiff', (
    'create_tables',
    'add_columns',
    'drop_columns',
    'add_indexes',
    'drop_indexes'))

class SchemaDiff(_SchemaDiff):
    __slots__ = ()

    def __bool__(self):
        return any(self)

    def __str__(self):
        accum = ['create table %s' % m._meta.table_name
                 for m in self.create_tables]
        accum.extend('add column %s.%s' % (f.model._meta.table_name,
                                           f.column_name)
                     for f in self.add_columns)
        accum.extend('drop column %s.%s' % tc for tc in self.drop_columns)
        accum.extend(idx.display('add') for idx in self.add_indexes)
        accum.extend(idx.display('drop') for idx in self.drop_indexes)
        return '\n'.join(accum)


def _model_indexes(model):
    # Plain indexes as a (columns, unique) signature. Partial and expression
    # indexes carry no signature, just their (deterministic) name.
    plain, named = set(), set()
    for index in model._meta.fields_to_index():
        if not isinstance(index, Index):
            continue  # SQL declarations are out of scope.
        parts = index._expressions
        if index._where is None and all(isinstance(p, Field) for p in parts):
            plain.add((tuple(p.column_name for p in parts),
                       bool(index._unique)))
        elif index._name:
            named.add(index._name)
    return plain, named


def _is_partial(index):
    return bool(index.sql and re.search(r'\)\s*WHERE\s', index.sql, re.I))


def _database_indexes(database, table, schema=None):
    # Every index as name -> (columns, unique) signature, or name -> None
    # when partial / expression. Primary-key indexes are excluded.
    indexes = {}
    for index in database.get_indexes(table, schema):
        if index.name == 'PRIMARY' or index.name.endswith('_pkey') or \
           index.name.startswith('sqlite_autoindex_'):
            continue
        if None in index.columns or _is_partial(index):
            indexes[index.name] = None
        else:
            indexes[index.name] = (tuple(index.columns), bool(index.unique))
    return indexes


def diff_models(database, models):
    """
    Compare the database schema against the given models.

    :return: a `SchemaDiff` (falsy when everything matches).
    """
    create_tables = []
    add_columns, drop_columns = [], []
    add_indexes, drop_indexes = [], []

    tables = {}  # Cache per schema.
    seen = set()
    for model in sort_models(models):
        meta = model._meta
        if getattr(meta, 'extension_module', None):
            continue  # Virtual tables (sqlite fts, etc).
        table, schema = meta.table_name, meta.schema
        if (schema, table) in seen:
            # Multiple models mapped to same table - skip.
            continue

        seen.add((schema, table))
        if schema not in tables:
            tables[schema] = set(database.get_tables(schema))
        if table not in tables[schema]:
            create_tables.append(model)
            continue

        columns = set(c.name for c in database.get_columns(table, schema))
        fields = {field.column_name: field for field in meta.sorted_fields}
        add_columns.extend(field for name, field in fields.items()
                           if name not in columns)
        drop_columns.extend((table, name)
                            for name in sorted(columns - set(fields)))

        # Pair database indexes with declarations - named (partial and
        # expression) indexes by name, plain indexes by signature - and
        # whatever fails to pair is a change. Names pair first: the
        # database may report a named index (e.g. ts.desc()) as plain.
        plain, named = _model_indexes(model)
        db_indexes = _database_indexes(database, table, schema)
        for name, signature in sorted(db_indexes.items()):
            if name in named:
                named.remove(name)
            elif signature in plain:
                plain.remove(signature)
            elif signature is None:
                drop_indexes.append(IndexDiff(table, name, None, None))
            else:
                cols, unique = signature
                drop_indexes.append(IndexDiff(table, name, cols, unique))

        for name in sorted(named):
            add_indexes.append(IndexDiff(table, name, None, None))
        for cols, unique in sorted(plain):
            add_indexes.append(IndexDiff(table, None, cols, unique))

    return SchemaDiff(create_tables, add_columns, drop_columns,
                      add_indexes, drop_indexes)
