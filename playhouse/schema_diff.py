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
    expressions indexes are compared by name only.

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


class IndexDiff(namedtuple('IndexDiff', ('table', 'name', 'columns',
                                         'unique', 'op'))):
    def __str__(self):
        if self.columns is None:
            return '%s index %s.%s' % (self.op, self.table, self.name)
        return '%s index %s%s (%s)%s' % (
            self.op, self.table, '.%s' % self.name if self.name else '',
            ', '.join(self.columns), ' unique' if self.unique else '')


class SchemaDiff(namedtuple('SchemaDiff', ('create_tables', 'add_columns',
                                           'drop_columns', 'add_indexes',
                                           'drop_indexes'))):
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
        accum.extend(str(idx) for idx in self.add_indexes)
        accum.extend(str(idx) for idx in self.drop_indexes)
        return '\n'.join(accum)


def _model_indexes(model):
    # Simple indexes as (columns tuple, unique), and partial/expression indexes
    # by name only.
    simple = set()
    partial = set()
    for index in model._meta.fields_to_index():
        if not isinstance(index, Index):
            continue  # SQL declarations are out of scope.
        if index._where is None and \
           all(isinstance(part, Field) for part in index._expressions):
            simple.add((tuple(part.column_name
                              for part in index._expressions),
                        bool(index._unique)))
        elif index._name:
            partial.add(index._name)
    return simple, partial


def _is_partial(index):
    return bool(index.sql and re.search(r'\)\s*WHERE\s', index.sql, re.I))


def _database_indexes(database, table, schema=None):
    simple = {}
    partial = set()  # Partial / expression indexes.
    for index in database.get_indexes(table, schema):
        if index.name == 'PRIMARY' or index.name.endswith('_pkey') or \
           index.name.startswith('sqlite_autoindex_'):
            continue

        if None in index.columns or _is_partial(index):
            partial.add(index.name)
        else:
            simple[(tuple(index.columns), bool(index.unique))] = index.name

    return simple, partial


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

        code_simple, code_partial = _model_indexes(model)
        db_simple, db_partial = _database_indexes(database, table, schema)

        simple = {name: sig for sig, name in db_simple.items()}
        found = {simple[name] for name in code_partial
                 if name in simple}
        remaining = set(db_simple) - found

        # Partial/expression indexes that are expected, less any named or plain
        # indexes found.
        for name in sorted(code_partial - db_partial - set(simple)):
            add_indexes.append(IndexDiff(table, name, None, None, 'add'))
        # Plain indexes that are expected.
        for cols, unique in sorted(code_simple - remaining):
            add_indexes.append(IndexDiff(table, None, cols, unique, 'add'))

        for cols, unique in sorted(remaining - code_simple):
            drop_indexes.append(IndexDiff(table, db_simple[(cols, unique)],
                                          cols, unique, 'drop'))
        # Partial/expression indexes in db, but not in code.
        for name in sorted(db_partial - code_partial):
            drop_indexes.append(IndexDiff(table, name, None, None, 'drop'))

    return SchemaDiff(create_tables, add_columns, drop_columns,
                      add_indexes, drop_indexes)
