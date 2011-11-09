#     (\
#     (  \  /(o)\     caw!
#     (   \/  ()/ /)
#      (   `;.))'".) 
#       `(/////.-'
#    =====))=))===() 
#      ///'       
#     //
#    '
from __future__ import with_statement
from datetime import datetime
import decimal
import logging
import os
import re
import threading
import time

try:
    import sqlite3
except ImportError:
    sqlite3 = None

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    import MySQLdb as mysql
except ImportError:
    mysql = None

__all__ = [
    'ImproperlyConfigured', 'SqliteDatabase', 'MySQLDatabase', 'PostgresqlDatabase',
    'asc', 'desc', 'Count', 'Max', 'Min', 'Sum', 'Q', 'Field', 'CharField', 'TextField',
    'DateTimeField', 'BooleanField', 'DecimalField', 'FloatField', 'IntegerField',
    'PrimaryKeyField', 'ForeignKeyField', 'Model', 'filter_query', 'annotate_query',
]

class ImproperlyConfigured(Exception):
    pass

if sqlite3 is None and psycopg2 is None and mysql is None:
    raise ImproperlyConfigured('Either sqlite3, psycopg2 or MySQLdb must be installed')

if sqlite3:
    sqlite3.register_adapter(decimal.Decimal, lambda v: str(v))
    sqlite3.register_converter('decimal', lambda v: decimal.Decimal(v))


DATABASE_NAME = os.environ.get('PEEWEE_DATABASE', 'peewee.db')
logger = logging.getLogger('peewee.logger')


class BaseAdapter(object):
    """
    The various subclasses of `BaseAdapter` provide a bridge between the high-
    level `Database` abstraction and the underlying python libraries like
    psycopg2.  It also provides a way to unify the pythonic field types with
    the underlying column types used by the database engine.
    
    The `BaseAdapter` provides two types of mappings:    
    - mapping between filter operations and their database equivalents
    - mapping between basic field types and their database column types
    
    The `BaseAdapter` also is the mechanism used by the `Database` class to:
    - handle connections with the database
    - extract information from the database cursor
    """
    operations = {'eq': '= %s'}
    interpolation = '%s'
    
    def get_field_types(self):
        field_types = {
            'integer': 'INTEGER',
            'float': 'REAL',
            'decimal': 'DECIMAL',
            'string': 'VARCHAR',
            'text': 'TEXT',
            'datetime': 'DATETIME',
            'primary_key': 'INTEGER',
            'foreign_key': 'INTEGER',
            'boolean': 'SMALLINT',
        }
        field_types.update(self.get_field_overrides())
        return field_types
    
    def get_field_overrides(self):
        return {}
    
    def connect(self, database, **kwargs):
        raise NotImplementedError
    
    def close(self, conn):
        conn.close()
    
    def lookup_cast(self, lookup, value):
        if lookup in ('contains', 'icontains'):
            return '%%%s%%' % value
        elif lookup in ('startswith', 'istartswith'):
            return '%s%%' % value
        return value
    
    def last_insert_id(self, cursor, model):
        return cursor.lastrowid
    
    def rows_affected(self, cursor):
        return cursor.rowcount


class SqliteAdapter(BaseAdapter):
    # note the sqlite library uses a non-standard interpolation string
    operations = {
        'lt': '< ?',
        'lte': '<= ?',
        'gt': '> ?',
        'gte': '>= ?',
        'eq': '= ?',
        'ne': '!= ?', # watch yourself with this one
        'in': 'IN (%s)', # special-case to list q-marks
        'is': 'IS ?',
        'icontains': "LIKE ? ESCAPE '\\'", # surround param with %'s
        'contains': "GLOB ?", # surround param with *'s
        'istartswith': "LIKE ? ESCAPE '\\'",
        'startswith': "GLOB ?",
    }
    interpolation = '?'
    
    def connect(self, database, **kwargs):
        if not sqlite3:
            raise ImproperlyConfigured('sqlite3 must be installed on the system')
        return sqlite3.connect(database, **kwargs)
    
    def lookup_cast(self, lookup, value):
        if lookup == 'contains':
            return '*%s*' % value
        elif lookup == 'icontains':
            return '%%%s%%' % value
        elif lookup == 'startswith':
            return '%s*' % value
        elif lookup == 'istartswith':
            return '%s%%' % value
        return value


class PostgresqlAdapter(BaseAdapter):
    operations = {
        'lt': '< %s',
        'lte': '<= %s',
        'gt': '> %s',
        'gte': '>= %s',
        'eq': '= %s',
        'ne': '!= %s', # watch yourself with this one
        'in': 'IN (%s)', # special-case to list q-marks
        'is': 'IS %s',
        'icontains': 'ILIKE %s', # surround param with %'s
        'contains': 'LIKE %s', # surround param with *'s
        'istartswith': 'ILIKE %s',
        'startswith': 'LIKE %s',
    }
        
    def connect(self, database, **kwargs):
        if not psycopg2:
            raise ImproperlyConfigured('psycopg2 must be installed on the system')
        return psycopg2.connect(database=database, **kwargs)
    
    def get_field_overrides(self):
        return {
            'primary_key': 'SERIAL',
            'datetime': 'TIMESTAMP',
            'decimal': 'NUMERIC',
        }
    
    def last_insert_id(self, cursor, model):
        cursor.execute("SELECT CURRVAL('\"%s_%s_seq\"')" % (
            model._meta.db_table, model._meta.pk_name))
        return cursor.fetchone()[0]
    

class MySQLAdapter(BaseAdapter):
    operations = {
        'lt': '< %s',
        'lte': '<= %s',
        'gt': '> %s',
        'gte': '>= %s',
        'eq': '= %s',
        'ne': '!= %s', # watch yourself with this one
        'in': 'IN (%s)', # special-case to list q-marks
        'is': 'IS %s',
        'icontains': 'LIKE %s', # surround param with %'s
        'contains': 'LIKE BINARY %s', # surround param with *'s
        'istartswith': 'LIKE %s',
        'startswith': 'LIKE BINARY %s',
    }

    def connect(self, database, **kwargs):
        if not mysql:
            raise ImproperlyConfigured('MySQLdb must be installed on the system')
        return mysql.connect(db=database, **kwargs)

    def get_field_overrides(self):
        return {
            'primary_key': 'integer AUTO_INCREMENT',
            'boolean': 'bool',
            'float': 'double precision',
            'text': 'longtext',
            'decimal': 'numeric',
        }


class Database(object):
    """
    A high-level api for working with the supported database engines.  `Database`
    provides a wrapper around some of the functions performed by the `Adapter`,
    in addition providing support for:
    - execution of SQL queries
    - creating and dropping tables and indexes
    """
    def __init__(self, adapter, database, threadlocals=False, **connect_kwargs):
        self.adapter = adapter
        self.database = database
        self.connect_kwargs = connect_kwargs
        
        if threadlocals:
            self.__local = threading.local()
        else:
            self.__local = type('DummyLocal', (object,), {})
        
        self._conn_lock = threading.Lock()
    
    def connect(self):
        with self._conn_lock:
            self.__local.conn = self.adapter.connect(self.database, **self.connect_kwargs)
            self.__local.closed = False
    
    def close(self):
        with self._conn_lock:
            self.adapter.close(self.__local.conn)
            self.__local.closed = True
    
    def get_conn(self):
        if not hasattr(self.__local, 'closed') or self.__local.closed:
            self.connect()
        return self.__local.conn
    
    def get_cursor(self):
        return self.get_conn().cursor()
    
    def execute(self, sql, params=None, commit=False):
        cursor = self.get_cursor()
        res = cursor.execute(sql, params or ())
        if commit:
            self.commit()
        logger.debug((sql, params))
        return cursor
    
    def commit(self):
        self.get_conn().commit()
    
    def rollback(self):
        self.get_conn().rollback()
    
    def last_insert_id(self, cursor, model):
        return self.adapter.last_insert_id(cursor, model)
    
    def rows_affected(self, cursor):
        return self.adapter.rows_affected(cursor)
    
    def column_for_field(self, db_field):
        try:
            return self.adapter.get_field_types()[db_field]
        except KeyError:
            raise AttributeError('Unknown field type: "%s", valid types are: %s' % \
                db_field, ', '.join(self.adapter.get_field_types().keys())
            )
    
    def create_table(self, model_class, safe=False):
        framing = safe and "CREATE TABLE IF NOT EXISTS %s (%s);" or "CREATE TABLE %s (%s);"
        columns = []

        for field in model_class._meta.fields.values():
            columns.append(field.to_sql())

        query = framing % (model_class._meta.db_table, ', '.join(columns))
        
        self.execute(query, commit=True)
    
    def create_index(self, model_class, field, unique=False):
        framing = 'CREATE %(unique)s INDEX %(model)s_%(field)s ON %(model)s(%(field)s);'
        
        if field not in model_class._meta.fields:
            raise AttributeError(
                'Field %s not on model %s' % (field, model_class)
            )
        
        unique_expr = ternary(unique, 'UNIQUE', '')
        
        query = framing % {
            'unique': unique_expr,
            'model': model_class._meta.db_table,
            'field': field
        }
        
        self.execute(query, commit=True)
    
    def drop_table(self, model_class, fail_silently=False):
        framing = fail_silently and 'DROP TABLE IF EXISTS %s;' or 'DROP TABLE %s;'
        self.execute(framing % model_class._meta.db_table, commit=True)
    
    def get_indexes_for_table(self, table):
        raise NotImplementedError
    
    def get_tables(self):
        raise NotImplementedError


class SqliteDatabase(Database):
    def __init__(self, database, **connect_kwargs):
        super(SqliteDatabase, self).__init__(SqliteAdapter(), database, **connect_kwargs)
    
    def get_indexes_for_table(self, table):
        res = self.execute('PRAGMA index_list(%s);' % table)
        rows = sorted([(r[1], r[2] == 1) for r in res.fetchall()])
        return rows
    
    def get_tables(self):
        res = self.execute('select name from sqlite_master where type="table" order by name')
        return [r[0] for r in res.fetchall()]


class PostgresqlDatabase(Database):
    def __init__(self, database, **connect_kwargs):
        super(PostgresqlDatabase, self).__init__(PostgresqlAdapter(), database, **connect_kwargs)
    
    def get_indexes_for_table(self, table):
        res = self.execute("""
            SELECT c2.relname, i.indisprimary, i.indisunique
            FROM pg_catalog.pg_class c, pg_catalog.pg_class c2, pg_catalog.pg_index i
            WHERE c.relname = %s AND c.oid = i.indrelid AND i.indexrelid = c2.oid
            ORDER BY i.indisprimary DESC, i.indisunique DESC, c2.relname""", (table,))
        return sorted([(r[0], r[1]) for r in res.fetchall()])
    
    def get_tables(self):
        res = self.execute("""
            SELECT c.relname
            FROM pg_catalog.pg_class c
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'v', '')
                AND n.nspname NOT IN ('pg_catalog', 'pg_toast')
                AND pg_catalog.pg_table_is_visible(c.oid)
            ORDER BY c.relname""")
        return [row[0] for row in res.fetchall()]


class MySQLDatabase(Database):
    def __init__(self, database, **connect_kwargs):
        super(MySQLDatabase, self).__init__(MySQLAdapter(), database, **connect_kwargs)
    
    def get_indexes_for_table(self, table):
        res = self.execute('SHOW INDEXES IN %s;' % table)
        rows = sorted([(r[2], r[1] == 0) for r in res.fetchall()])
        return rows
    
    def get_tables(self):
        res = self.execute('SHOW TABLES;')
        return [r[0] for r in res.fetchall()]


class QueryResultWrapper(object):
    """
    Provides an iterator over the results of a raw Query, additionally doing
    two things:
    - converts rows from the database into model instances
    - ensures that multiple iterations do not result in multiple queries
    """
    def __init__(self, model, cursor):
        self.model = model
        self.cursor = cursor
        self._result_cache = []
        self._populated = False
    
    def model_from_rowset(self, model_class, row_dict):
        instance = model_class()
        for attr, value in row_dict.iteritems():
            if attr in instance._meta.fields:
                field = instance._meta.fields[attr]
                setattr(instance, attr, field.python_value(value))
            else:
                setattr(instance, attr, value)
        return instance    
    
    def _row_to_dict(self, row, result_cursor):
        return dict((result_cursor.description[i][0], value)
            for i, value in enumerate(row))
    
    def __iter__(self):
        if not self._populated:
            return self
        else:
            return iter(self._result_cache)
    
    def next(self):
        row = self.cursor.fetchone()
        if row:
            row_dict = self._row_to_dict(row, self.cursor)
            instance = self.model_from_rowset(self.model, row_dict)
            self._result_cache.append(instance)
            return instance
        else:
            self._populated = True
            raise StopIteration


# create
class DoesNotExist(Exception):
    pass


# semantic wrappers for ordering the results of a `SelectQuery`
def asc(f):
    return (f, 'ASC')

def desc(f):
    return (f, 'DESC')

# wrappers for performing aggregation in a `SelectQuery`
def Count(f, alias='count'):
    return ('COUNT', f, alias)

def Max(f, alias='max'):
    return ('MAX', f, alias)

def Min(f, alias='min'):
    return ('MIN', f, alias)

def Sum(f, alias='sum'):
    return ('SUM', f, alias)

# decorator for query methods to indicate that they change the state of the
# underlying data structures
def returns_clone(func):
    def inner(self, *args, **kwargs):
        clone = self.clone()
        res = func(clone, *args, **kwargs)
        return clone
    return inner

# helpers
ternary = lambda cond, t, f: (cond and [t] or [f])[0]


class Node(object):
    def __init__(self, connector='AND'):
        self.connector = connector
        self.children = []
        self.negated = False
    
    def connect(self, rhs, connector):
        if isinstance(rhs, Q):
            if connector == self.connector:
                self.children.append(rhs)
                return self
            else:
                p = Node(connector)
                p.children = [self, rhs]
                return p
        elif isinstance(rhs, Node):
            p = Node(connector)
            p.children = [self, rhs]
            return p
    
    def __or__(self, rhs):
        return self.connect(rhs, 'OR')

    def __and__(self, rhs):
        return self.connect(rhs, 'AND')
    
    def __invert__(self):
        self.negated = not self.negated
        return self

    def __nonzero__(self):
        return bool(self.children)
    
    def __unicode__(self):
        query = []
        nodes = []
        for child in self.children:
            if isinstance(child, Q):
                query.append(unicode(child))
            elif isinstance(child, Node):
                nodes.append('(%s)' % unicode(child))
        query.extend(nodes)
        connector = ' %s ' % self.connector
        query = connector.join(query)
        if self.negated:
            query = 'NOT %s' % query
        return query
    

class Q(object):
    def __init__(self, **kwargs):
        self.query = kwargs
        self.parent = None
        self.negated = False
    
    def connect(self, connector):
        if self.parent is None:
            self.parent = Node(connector)
            self.parent.children.append(self)
    
    def __or__(self, rhs):
        self.connect('OR')
        return self.parent | rhs
    
    def __and__(self, rhs):
        self.connect('AND')
        return self.parent & rhs
    
    def __invert__(self):
        self.negated = not self.negated
        return self
    
    def __unicode__(self):
        bits = ['%s = %s' % (k, v) for k, v in self.query.items()]
        if len(self.query.items()) > 1:
            connector = ' AND '
            expr = '(%s)' % connector.join(bits)
        else:
            expr = bits[0]
        if self.negated:
            expr = 'NOT %s' % expr
        return expr


def parseq(*args, **kwargs):
    node = Node()
    
    for piece in args:
        if isinstance(piece, (Q, Node)):
            node.children.append(piece)
        else:
            raise TypeError('Unknown object: %s', piece)

    if kwargs:
        node.children.append(Q(**kwargs))

    return node


class EmptyResultException(Exception):
    pass


class BaseQuery(object):
    query_separator = '__'
    requires_commit = True
    force_alias = False
    
    def __init__(self, model):
        self.model = model
        self.query_context = model
        self.database = self.model._meta.database
        self.operations = self.database.adapter.operations
        self.interpolation = self.database.adapter.interpolation
        
        self._dirty = True
        self._where = {}
        self._joins = {}
        self._joined_models = set()
    
    def _clone_dict_graph(self, dg):
        cloned = {}
        for node, edges in dg.items():
            cloned[node] = list(edges)
        return cloned
    
    def clone_where(self):
        return self._clone_dict_graph(self._where)
    
    def clone_joins(self):
        return self._clone_dict_graph(self._joins)
    
    def clone(self):
        raise NotImplementedError
    
    def lookup_cast(self, lookup, value):
        return self.database.adapter.lookup_cast(lookup, value)
    
    def parse_query_args(self, model, **query):
        parsed = {}
        for lhs, rhs in query.iteritems():
            if self.query_separator in lhs:
                lhs, op = lhs.rsplit(self.query_separator, 1)
            else:
                op = 'eq'
            
            try:
                field = model._meta.get_field_by_name(lhs)
            except AttributeError:
                field = model._meta.get_related_field_by_name(lhs)
                if field is None:
                    raise
                if isinstance(rhs, Model):
                    rhs = rhs.get_pk()
            
            if op == 'in':
                if isinstance(rhs, SelectQuery):
                    lookup_value = rhs
                    operation = 'IN (%s)'
                else:
                    if not rhs:
                        raise EmptyResultException
                    lookup_value = [field.db_value(o) for o in rhs]
                    operation = self.operations[op] % \
                        (','.join([self.interpolation for v in lookup_value]))
            elif op == 'is':
                if rhs is not None:
                    raise ValueError('__is lookups only accept None')
                operation = 'IS NULL'
                lookup_value = []
            else:
                lookup_value = field.db_value(rhs)
                operation = self.operations[op]
            
            parsed[field.name] = (operation, self.lookup_cast(op, lookup_value))
        
        return parsed
    
    @returns_clone
    def where(self, *args, **kwargs):
        self._where.setdefault(self.query_context, [])
        parsed = parseq(*args, **kwargs)
        if parsed:
            self._where[self.query_context].append(parsed)

    @returns_clone
    def join(self, model, join_type=None, on=None):
        if self.query_context._meta.rel_exists(model):
            self._joined_models.add(model)
            self._joins.setdefault(self.query_context, [])
            self._joins[self.query_context].append((model, join_type, on))
            self.query_context = model
        else:
            raise AttributeError('No foreign key found between %s and %s' % \
                (self.query_context.__name__, model.__name__))

    @returns_clone
    def switch(self, model):
        if model == self.model:
            self.query_context = model
            return

        if model in self._joined_models:
            self.query_context = model
            return
        raise AttributeError('You must JOIN on %s' % model.__name__)
    
    def use_aliases(self):
        return len(self._joined_models) > 0 or self.force_alias

    def combine_field(self, alias, field_name):
        if alias:
            return '%s.%s' % (alias, field_name)
        return field_name
    
    def follow_joins(self, current, alias_map, alias_required, alias_count, seen=None):
        computed = []
        seen = seen or set()
        
        if current not in self._joins:
            return computed
        
        for i, (model, join_type, on) in enumerate(self._joins[current]):
            seen.add(model)
            
            if alias_required:
                alias_count += 1
                alias_map[model] = 't%d' % alias_count
            else:
                alias_map[model] = ''
            
            from_model = current
            field = from_model._meta.get_related_field_for_model(model, on)
            if field:
                left_field = field.name
                right_field = model._meta.pk_name
            else:
                field = from_model._meta.get_reverse_related_field_for_model(model, on)
                left_field = from_model._meta.pk_name
                right_field = field.name
            
            if join_type is None:
                if field.null and model not in self._where:
                    join_type = 'LEFT OUTER'
                else:
                    join_type = 'INNER'
            
            computed.append(
                '%s JOIN %s AS %s ON %s = %s' % (
                    join_type,
                    model._meta.db_table,
                    alias_map[model],
                    self.combine_field(alias_map[from_model], left_field),
                    self.combine_field(alias_map[model], right_field),
                )
            )
            
            computed.extend(self.follow_joins(model, alias_map, alias_required, alias_count, seen))
        
        return computed
    
    def compile_where(self):
        alias_count = 0
        alias_map = {}

        alias_required = self.use_aliases()

        where_with_alias = []
        where_data = []
        
        if alias_required:
            alias_count += 1
            alias_map[self.model] = 't%d' % alias_count
        else:
            alias_map[self.model] = ''
        
        computed_joins = self.follow_joins(self.model, alias_map, alias_required, alias_count)
        
        for model in sorted(self._where, key=lambda m: alias_map[m]):
            for node in self._where[model]:
                query, data = self.parse_node(node, model, alias_map)
                where_with_alias.append(query)
                where_data.extend(data)
        
        return computed_joins, where_with_alias, where_data, alias_map
    
    def convert_where_to_params(self, where_data):
        flattened = []
        for clause in where_data:
            if isinstance(clause, (tuple, list)):
                flattened.extend(clause)
            else:
                flattened.append(clause)
        return flattened
    
    def parse_node(self, node, model, alias_map):
        query = []
        query_data = []
        nodes = []
        for child in node.children:
            if isinstance(child, Q):
                parsed, data = self.parse_q(child, model, alias_map)
                query.append(parsed)
                query_data.extend(data)
            elif isinstance(child, Node):
                parsed, data = self.parse_node(child, model, alias_map)
                query.append('(%s)' % parsed)
                query_data.extend(data)
        query.extend(nodes)
        connector = ' %s ' % node.connector
        query = connector.join(query)
        if node.negated:
            query = 'NOT (%s)' % query
        return query, query_data
    
    def parse_q(self, q, model, alias_map):
        query = []
        query_data = []
        parsed = self.parse_query_args(model, **q.query)
        for (name, lookup) in parsed.iteritems():
            operation, value = lookup
            if isinstance(value, SelectQuery):
                sql, value = self.convert_subquery(value)
                operation = operation % sql

            query_data.append(value)
            
            combined = self.combine_field(alias_map[model], name)
            query.append('%s %s' % (combined, operation))
        
        if len(query) > 1:
            query = '(%s)' % (' AND '.join(query))
        else:
            query = query[0]
        
        if q.negated:
            query = 'NOT %s' % query
        
        return query, query_data

    def convert_subquery(self, subquery):
        subquery.query, orig_query = subquery.model._meta.pk_name, subquery.query
        subquery.force_alias, orig_alias = True, subquery.force_alias
        sql, data = subquery.sql()
        subquery.query = orig_query
        subquery.force_alias = orig_alias
        return sql, data
    
    def raw_execute(self):
        query, params = self.sql()
        return self.database.execute(query, params, self.requires_commit)


class RawQuery(BaseQuery):
    def __init__(self, model, query, *params):
        self._sql = query
        self._params = list(params)
        super(RawQuery, self).__init__(model)
    
    def sql(self):
        return self._sql, self._params
    
    def execute(self):
        return QueryResultWrapper(self.model, self.raw_execute())
    
    def join(self):
        raise AttributeError('Raw queries do not support joining programmatically')
    
    def where(self):
        raise AttributeError('Raw queries do not support querying programmatically')
    
    def switch(self):
        raise AttributeError('Raw queries do not support switching contexts')
    
    def __iter__(self):
        return self.execute()


class SelectQuery(BaseQuery):
    requires_commit = False
    
    def __init__(self, model, query=None):
        self.query = query or '*'
        self._group_by = []
        self._having = []
        self._order_by = []
        self._limit = None
        self._offset = None
        self._distinct = False
        self._qr = None
        super(SelectQuery, self).__init__(model)
    
    def clone(self):
        query = SelectQuery(self.model, self.query)
        query.query_context = self.query_context
        query._group_by = list(self._group_by)
        query._having = list(self._having)
        query._order_by = list(self._order_by)
        query._limit = self._limit
        query._offset = self._offset
        query._distinct = self._distinct
        query._qr = self._qr
        query._where = self.clone_where()
        query._joined_models = self._joined_models.copy()
        query._joins = self.clone_joins()
        return query
    
    @returns_clone
    def paginate(self, page, paginate_by=20):
        if page > 0:
            page -= 1
        self._limit = paginate_by
        self._offset = page * paginate_by
    
    @returns_clone
    def limit(self, num_rows):
        self._limit = num_rows
    
    @returns_clone
    def offset(self, num_rows):
        self._offset = num_rows
    
    def count(self):
        tmp_lim, tmp_off = self._limit, self._offset
        self._limit = self._offset = None
        
        tmp_query = self.query
        
        if self.use_aliases():
            self.query = 'COUNT(t1.%s)' % (self.model._meta.pk_name)
        else:
            self.query = 'COUNT(%s)' % (self.model._meta.pk_name)
        
        res = self.database.execute(*self.sql())
        
        # restore
        self.query = tmp_query
        self._limit = tmp_lim
        self._offset = tmp_off
        
        return res.fetchone()[0]
    
    @returns_clone
    def group_by(self, clause):
        model = self.query_context
        
        if isinstance(clause, basestring):
            fields = (clause,)
        elif isinstance(clause, (list, tuple)):
            fields = clause
        elif issubclass(clause, Model):
            model = clause
            fields = clause._meta.get_field_names()
        
        self._group_by.append((model, fields))
    
    @returns_clone
    def having(self, clause):
        self._having.append(clause)
    
    @returns_clone
    def distinct(self):
        self._distinct = True
    
    @returns_clone
    def order_by(self, *clauses):
        order_by = []
        
        for clause in clauses:
            if isinstance(clause, tuple):
                if len(clause) == 3:
                    model, field, ordering = clause
                elif len(clause) == 2:
                    if isinstance(clause[0], basestring):
                        model = self.query_context
                        field, ordering = clause
                    else:
                        model, field = clause
                        ordering = 'ASC'
                else:
                    raise ValueError('Incorrect arguments passed in order_by clause')
            else:
                model = self.query_context
                field = clause
                ordering = 'ASC'
        
            order_by.append(
                (model, field, ordering)
            )
        
        self._order_by = order_by
    
    def exists(self):
        clone = self.paginate(1, 1)
        clone.query = '(1) AS a'
        curs = self.database.execute(*clone.sql())
        return bool(curs.fetchone())
    
    def get(self, *args, **kwargs):
        try:
            orig_ctx = self.query_context
            self.query_context = self.model
            obj = self.where(*args, **kwargs).paginate(1, 1).execute().next()
            return obj
        except StopIteration:
            raise self.model.DoesNotExist('instance matching query does not exist:\nSQL: %s\nPARAMS: %s' % (
                self.sql()
            ))
        finally:
            self.query_context = orig_ctx
    
    def filter(self, *args, **kwargs):
        return filter_query(self, *args, **kwargs)
    
    def annotate(self, related_model, aggregation=None):
        return annotate_query(self, related_model, aggregation)

    def parse_select_query(self, alias_map):
        if isinstance(self.query, (list, tuple)):
            query = {self.model: self.query}
        else:
            query = self.query
        
        if isinstance(query, basestring):
            if query in ('*', self.model._meta.pk_name) and self.use_aliases():
                return '%s.%s' % (alias_map[self.model], query)
            return query
        elif isinstance(query, dict):
            qparts = []
            aggregates = []
            for model, cols in query.iteritems():
                alias = alias_map.get(model, '')
                for col in cols:
                    if isinstance(col, tuple):
                        func, col, col_alias = col
                        aggregates.append('%s(%s) AS %s' % \
                            (func, self.combine_field(alias, col), col_alias)
                        )
                    else:
                        qparts.append(self.combine_field(alias, col))
            return ', '.join(qparts + aggregates)
        else:
            raise TypeError('Unknown type encountered parsing select query')
    
    def sql(self):
        joins, where, where_data, alias_map = self.compile_where()
        
        table = self.model._meta.db_table

        params = []
        group_by = []
        
        if self.use_aliases():
            table = '%s AS %s' % (table, alias_map[self.model])
            for model, clause in self._group_by:
                alias = alias_map[model]
                for field in clause:
                    group_by.append(self.combine_field(alias, field))
        else:
            group_by = [c[1] for c in self._group_by]

        parsed_query = self.parse_select_query(alias_map)
        
        if self._distinct:
            sel = 'SELECT DISTINCT'
        else:
            sel = 'SELECT'
        
        select = '%s %s FROM %s' % (sel, parsed_query, table)
        joins = '\n'.join(joins)
        where = ' AND '.join(where)
        group_by = ', '.join(group_by)
        having = ' AND '.join(self._having)
        
        order_by = []
        for piece in self._order_by:
            model, field, ordering = piece
            if self.use_aliases() and field in model._meta.fields:
                field = '%s.%s' % (alias_map[model], field)
            order_by.append('%s %s' % (field, ordering))
        
        pieces = [select]
        
        if joins:
            pieces.append(joins)
        if where:
            pieces.append('WHERE %s' % where)
            params.extend(self.convert_where_to_params(where_data))
        
        if group_by:
            pieces.append('GROUP BY %s' % group_by)
        if having:
            pieces.append('HAVING %s' % having)
        if order_by:
            pieces.append('ORDER BY %s' % ', '.join(order_by))
        if self._limit:
            pieces.append('LIMIT %d' % self._limit)
        if self._offset:
            pieces.append('OFFSET %d' % self._offset)
        
        return ' '.join(pieces), params
    
    def execute(self):
        if self._dirty or not self._qr:
            try:
                self._qr = QueryResultWrapper(self.model, self.raw_execute())
                self._dirty = False
                return self._qr
            except EmptyResultException:
                return iter([])
        else:
            # call the __iter__ method directly
            return iter(self._qr)
    
    def __iter__(self):
        return self.execute()


class UpdateQuery(BaseQuery):
    def __init__(self, model, **kwargs):
        self.update_query = kwargs
        super(UpdateQuery, self).__init__(model)
    
    def clone(self):
        query = UpdateQuery(self.model, **self.update_query)
        query._where = self.clone_where()
        query._joined_models = self._joined_models.copy()
        query._joins = self.clone_joins()
        return query
    
    def parse_update(self):
        sets = {}
        for k, v in self.update_query.iteritems():
            try:
                field = self.model._meta.get_field_by_name(k)
            except AttributeError:
                field = self.model._meta.get_related_field_by_name(k)
                if field is None:
                    raise
            
            sets[field.name] = field.db_value(v)
        
        return sets
    
    def sql(self):
        joins, where, where_data, alias_map = self.compile_where()
        set_statement = self.parse_update()

        params = []
        update_params = []

        for k, v in set_statement.iteritems():
            params.append(v)
            update_params.append('%s=%s' % (k, self.interpolation))
        
        update = 'UPDATE %s SET %s' % (
            self.model._meta.db_table, ', '.join(update_params))
        where = ' AND '.join(where)
        
        pieces = [update]
        
        if where:
            pieces.append('WHERE %s' % where)
            params.extend(self.convert_where_to_params(where_data))
        
        return ' '.join(pieces), params
    
    def join(self, *args, **kwargs):
        raise AttributeError('Update queries do not support JOINs in sqlite')
    
    def execute(self):
        result = self.raw_execute()
        return self.database.rows_affected(result)


class DeleteQuery(BaseQuery):
    def clone(self):
        query = DeleteQuery(self.model)
        query._where = self.clone_where()
        query._joined_models = self._joined_models.copy()
        query._joins = self.clone_joins()
        return query
    
    def sql(self):
        joins, where, where_data, alias_map = self.compile_where()

        params = []
        
        delete = 'DELETE FROM %s' % (self.model._meta.db_table)
        where = ' AND '.join(where)
        
        pieces = [delete]
        
        if where:
            pieces.append('WHERE %s' % where)
            params.extend(self.convert_where_to_params(where_data))
        
        return ' '.join(pieces), params
    
    def join(self, *args, **kwargs):
        raise AttributeError('Update queries do not support JOINs in sqlite')
    
    def execute(self):
        result = self.raw_execute()
        return self.database.rows_affected(result)


class InsertQuery(BaseQuery):
    def __init__(self, model, **kwargs):
        self.insert_query = kwargs
        super(InsertQuery, self).__init__(model)
    
    def parse_insert(self):
        cols = []
        vals = []
        for k, v in self.insert_query.iteritems():
            field = self.model._meta.get_field_by_name(k)
            cols.append(k)
            vals.append(field.db_value(v))
        
        return cols, vals
    
    def sql(self):
        cols, vals = self.parse_insert()
        
        insert = 'INSERT INTO %s (%s) VALUES (%s)' % (
            self.model._meta.db_table,
            ','.join(cols),
            ','.join(self.interpolation for v in vals)
        )
        
        return insert, vals
    
    def where(self, *args, **kwargs):
        raise AttributeError('Insert queries do not support WHERE clauses')
    
    def join(self, *args, **kwargs):
        raise AttributeError('Insert queries do not support JOINs')
    
    def execute(self):
        result = self.raw_execute()
        return self.database.last_insert_id(result, self.model)


def model_or_select(m_or_q):
    if isinstance(m_or_q, BaseQuery):
        return (m_or_q.model, m_or_q)
    else:
        return (m_or_q, m_or_q.select())

def convert_lookup(model, joins, lookup):
    operations = model._meta.database.adapter.operations
    
    pieces = lookup.split('__')
    operation = None
    
    query_model = model
    
    if len(pieces) > 1:
        if pieces[-1] in operations:
            operation = pieces.pop()
        
        lookup = pieces.pop()
        
        # we have some joins
        if len(pieces):
            query_model = model
            
            for piece in pieces:
                # piece is something like 'blog' or 'entry_set'
                joined_model = None
                for field in query_model._meta.get_fields():
                    if not isinstance(field, ForeignKeyField):
                        continue
                    
                    if piece in (field.descriptor, field.related_name):
                        joined_model = field.to
                
                if not joined_model:
                    try:
                        joined_model = query_model._meta.reverse_relations[piece]
                    except KeyError:
                        raise ValueError('Unknown relation: "%s" of "%s"' % (
                            piece,
                            query_model,
                        ))
                
                joins.setdefault(query_model, set())
                joins[query_model].add(joined_model)
                query_model = joined_model
    
    if operation:
        lookup = '%s__%s' % (lookup, operation)
    
    return query_model, joins, lookup


def filter_query(model_or_query, *args, **kwargs):
    """
    Provide a django-like interface for executing queries
    """
    model, select_query = model_or_select(model_or_query)
    
    query = {} # mapping of models to queries
    joins = {} # a graph of joins needed, passed into the convert_lookup function
    
    # due to quirks in the way where clauses are defined, Q() queries can only
    # work on a single table -- this will need to be redesigned so Q() objects
    # can work on multiple models
    def fix_q(node_or_q, joins):
        if isinstance(node_or_q, Node):
            for child in node_or_q.children:
                query_model = fix_q(child, joins)
        elif isinstance(node_or_q, Q):
            new_query = {}
            for raw_lookup, value in node_or_q.query.items():
                # do we have a query model at this point?
                query_model, joins, lookup = convert_lookup(model, joins, raw_lookup)
                new_query[lookup] = value
            node_or_q.query = new_query
        return query_model
    
    for node_or_q in args:
        queried_model = fix_q(node_or_q, joins)
        query.setdefault(queried_model, [])
        query[queried_model].append(node_or_q)
    
    # iterate over keyword lookups and determine lookups and necessary joins
    for raw_lookup, value in kwargs.items():
        queried_model, joins, lookup = convert_lookup(model, joins, raw_lookup)
        query.setdefault(queried_model, [])
        query[queried_model].append((lookup, value))
    
    def follow_joins(current, query):
        if current in joins:
            for joined_model in joins[current]:
                query = query.switch(current)
                if joined_model not in query._joined_models:
                    query = query.join(joined_model)
                query = follow_joins(joined_model, query)
        return query
    select_query = follow_joins(model, select_query)
    
    for model, lookups in query.items():
        qargs, qkwargs = [], {}
        for lookup in lookups:
            if isinstance(lookup, tuple):
                qkwargs[lookup[0]] = lookup[1]
            else:
                qargs.append(lookup)
        select_query = select_query.switch(model).where(*qargs, **qkwargs)

    return select_query

def annotate_query(select_query, related_model, aggregation):
    aggregation = aggregation or Count(related_model._meta.pk_name)
    model = select_query.model
    
    select_query = select_query.switch(model)
    cols = select_query.query
    
    # ensure the join is there
    if related_model not in select_query._joined_models:
        select_query = select_query.join(related_model).switch(model)
    
    # query for it
    if isinstance(cols, dict):
        selection = cols
        group_by = cols[model]
    elif isinstance(cols, basestring):
        selection = {model: [cols]}
        if cols == '*':
            group_by = model
        else:
            group_by = [col.strip() for col in cols.split(',')]
    elif isinstance(cols, (list, tuple)):
        selection = {model: cols}
        group_by = cols
    else:
        raise ValueError('Unknown type passed in to select query: "%s"' % type(cols))
    
    # query for the related object
    selection[related_model] = [aggregation]
    
    select_query.query = selection
    return select_query.group_by(group_by)


class Field(object):
    db_field = ''
    default = None
    field_template = "%(column_type)s%(nullable)s"
    _field_counter = 0
    _order = 0

    def get_attributes(self):
        return {}
    
    def __init__(self, null=False, db_index=False, unique=False, verbose_name=None,
                 help_text=None, *args, **kwargs):
        self.null = null
        self.db_index = db_index
        self.unique = unique
        self.attributes = self.get_attributes()
        self.default = kwargs.get('default', None)
        self.verbose_name = verbose_name
        self.help_text = help_text
        
        kwargs['nullable'] = ternary(self.null, '', ' NOT NULL')
        self.attributes.update(kwargs)
        
        Field._field_counter += 1
        self._order = Field._field_counter
    
    def add_to_class(self, klass, name):
        self.name = name
        self.model = klass
        self.verbose_name = self.verbose_name or re.sub('_+', ' ', name).title()
        setattr(klass, name, None)
    
    def render_field_template(self):
        col_type = self.model._meta.database.column_for_field(self.db_field)
        self.attributes['column_type'] = col_type
        return self.field_template % self.attributes
    
    def to_sql(self):
        rendered = self.render_field_template()
        return '%s %s' % (self.name, rendered)
    
    def null_wrapper(self, value, default=None):
        if (self.null and value is None) or default is None:
            return value
        return value or default
    
    def db_value(self, value):
        return value
    
    def python_value(self, value):
        return value
    
    def lookup_value(self, lookup_type, value):
        return self.db_value(value)

    def class_prepared(self):
        pass


class CharField(Field):
    db_field = 'string'
    field_template = '%(column_type)s(%(max_length)d)%(nullable)s'
    
    def get_attributes(self):
        return {'max_length': 255}
    
    def db_value(self, value):
        if self.null and value is None:
            return value
        value = value or ''
        return value[:self.attributes['max_length']]
    
    def lookup_value(self, lookup_type, value):
        if lookup_type == 'contains':
            return '*%s*' % self.db_value(value)
        elif lookup_type == 'icontains':
            return '%%%s%%' % self.db_value(value)
        else:
            return self.db_value(value)
    

class TextField(Field):
    db_field = 'text'
    
    def db_value(self, value):
        return self.null_wrapper(value, '')
    
    def lookup_value(self, lookup_type, value):
        if lookup_type == 'contains':
            return '*%s*' % self.db_value(value)
        elif lookup_type == 'icontains':
            return '%%%s%%' % self.db_value(value)
        else:
            return self.db_value(value)


class DateTimeField(Field):
    db_field = 'datetime'
    
    def python_value(self, value):
        if isinstance(value, basestring):
            value = value.rsplit('.', 1)[0]
            return datetime(*time.strptime(value, '%Y-%m-%d %H:%M:%S')[:6])
        return value


class IntegerField(Field):
    db_field = 'integer'
    
    def db_value(self, value):
        return self.null_wrapper(value, 0)
    
    def python_value(self, value):
        if value is not None:
            return int(value)


class BooleanField(IntegerField):
    db_field = 'boolean'
    
    def db_value(self, value):
        if value:
            return 1
        return 0
    
    def python_value(self, value):
        return bool(value)


class FloatField(Field):
    db_field = 'float'
    
    def db_value(self, value):
        return self.null_wrapper(value, 0.0)
    
    def python_value(self, value):
        if value is not None:
            return float(value)


class DecimalField(Field):
    db_field = 'decimal'
    field_template = '%(column_type)s(%(max_digits)d, %(decimal_places)d)%(nullable)s'
    
    def get_attributes(self):
        return {
            'max_digits': 10,
            'decimal_places': 5,
        }
    
    def db_value(self, value):
        return self.null_wrapper(value, decimal.Decimal(0))
    
    def python_value(self, value):
        if value is not None:
            if isinstance(value, decimal.Decimal):
                return value
            return decimal.Decimal(str(value))


class PrimaryKeyField(IntegerField):
    db_field = 'primary_key'
    field_template = "%(column_type)s NOT NULL PRIMARY KEY"


class ForeignRelatedObject(object):    
    def __init__(self, to, field):
        self.to = to
        self.field = field
        self.field_name = self.field.name
        self.cache_name = '_cache_%s' % self.field_name
    
    def __get__(self, instance, instance_type=None):
        if not getattr(instance, self.cache_name, None):
            id = getattr(instance, self.field_name, 0)
            qr = self.to.select().where(**{self.to._meta.pk_name: id})
            try:
                setattr(instance, self.cache_name, qr.get())
            except self.to.DoesNotExist:
                if not self.field.null:
                    raise
        return getattr(instance, self.cache_name, None)
    
    def __set__(self, instance, obj):
        assert isinstance(obj, self.to), "Cannot assign %s, invalid type" % obj
        setattr(instance, self.field_name, obj.get_pk())
        setattr(instance, self.cache_name, obj)


class ReverseForeignRelatedObject(object):
    def __init__(self, related_model, name):
        self.field_name = name
        self.related_model = related_model
    
    def __get__(self, instance, instance_type=None):
        query = {self.field_name: instance.get_pk()}
        qr = self.related_model.select().where(**query)
        return qr


class ForeignKeyField(IntegerField):
    db_field = 'foreign_key'
    field_template = '%(column_type)s%(nullable)s REFERENCES %(to_table)s (%(to_pk)s)%(cascade)s%(extra)s'
    
    def __init__(self, to, null=False, related_name=None, cascade=False, extra=None, *args, **kwargs):
        self.to = to
        self.related_name = related_name
        self.cascade = cascade
        self.extra = extra

        kwargs.update({
            'cascade': ' ON DELETE CASCADE' if self.cascade else '',
            'extra': self.extra or '',
        })
        super(ForeignKeyField, self).__init__(null=null, *args, **kwargs)
    
    def add_to_class(self, klass, name):
        self.descriptor = name
        self.name = name + '_id'
        self.model = klass

        if self.to == 'self':
            self.to = self.model

        self.verbose_name = self.verbose_name or re.sub('_', ' ', name).title()
        
        if self.related_name is None:
            self.related_name = klass._meta.db_table + '_set'
        
        klass._meta.rel_fields[name] = self.name
        setattr(klass, self.descriptor, ForeignRelatedObject(self.to, self))
        setattr(klass, self.name, None)
        
        reverse_rel = ReverseForeignRelatedObject(klass, self.name)
        setattr(self.to, self.related_name, reverse_rel)
        self.to._meta.reverse_relations[self.related_name] = klass
    
    def lookup_value(self, lookup_type, value):
        if isinstance(value, Model):
            return value.get_pk()
        return value or None
    
    def db_value(self, value):
        if isinstance(value, Model):
            return value.get_pk()
        return value

    def class_prepared(self):
        # unfortunately because we may not know the primary key field
        # at the time this field's add_to_class() method is called, we
        # need to update the attributes after the class has been built
        self.attributes.update({
            'to_table': self.to._meta.db_table,
            'to_pk': self.to._meta.pk_name,
        })


# define a default database object in the module scope
database = SqliteDatabase(DATABASE_NAME)


class BaseModelOptions(object):
    ordering = None

    def __init__(self, model_class, options=None):
        # configurable options
        options = options or {'database': database}
        for k, v in options.items():
            setattr(self, k, v)
        
        self.rel_fields = {}
        self.reverse_relations = {}
        self.fields = {}
        self.model_class = model_class
    
    def get_sorted_fields(self):
        return sorted(self.fields.items(), key=lambda (k,v): (k == self.pk_name and 1 or 2, v._order))
    
    def get_field_names(self):
        return [f[0] for f in self.get_sorted_fields()]
    
    def get_fields(self):
        return [f[1] for f in self.get_sorted_fields()]
    
    def get_field_by_name(self, name):
        if name in self.fields:
            return self.fields[name]
        raise AttributeError('Field named %s not found' % name)
    
    def get_related_field_by_name(self, name):
        if name in self.rel_fields:
            return self.fields[self.rel_fields[name]]
    
    def get_related_field_for_model(self, model, name=None):
        for field in self.fields.values():
            if isinstance(field, ForeignKeyField) and field.to == model:
                if name is None or name == field.name or name == field.descriptor:
                    return field
    
    def get_reverse_related_field_for_model(self, model, name=None):
        for field in model._meta.fields.values():
            if isinstance(field, ForeignKeyField) and field.to == self.model_class:
                if name is None or name == field.name or name == field.descriptor:
                    return field
    
    def rel_exists(self, model):
        return self.get_related_field_for_model(model) or \
               self.get_reverse_related_field_for_model(model)


class BaseModel(type):
    inheritable_options = ['database', 'ordering']
    
    def __new__(cls, name, bases, attrs):
        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)

        attr_dict = {}
        meta = attrs.pop('Meta', None)
        if meta:
            attr_dict = meta.__dict__
        
        for b in bases:
            base_meta = getattr(b, '_meta', None)
            if not base_meta:
                continue
            
            for (k, v) in base_meta.__dict__.items():
                if k in cls.inheritable_options and k not in attr_dict:
                    attr_dict[k] = v
        
        _meta = BaseModelOptions(cls, attr_dict)
        
        if not hasattr(_meta, 'db_table'):
            _meta.db_table = re.sub('[^a-z]+', '_', cls.__name__.lower())

        setattr(cls, '_meta', _meta)
        
        _meta.pk_name = None

        for name, attr in cls.__dict__.items():
            if isinstance(attr, Field):
                attr.add_to_class(cls, name)
                _meta.fields[attr.name] = attr
                if isinstance(attr, PrimaryKeyField):
                    _meta.pk_name = attr.name
        
        if _meta.pk_name is None:
            _meta.pk_name = 'id'
            pk = PrimaryKeyField()
            pk.add_to_class(cls, _meta.pk_name)
            _meta.fields[_meta.pk_name] = pk

        _meta.model_name = cls.__name__

        for field in _meta.fields.values():
            field.class_prepared()
                
        if hasattr(cls, '__unicode__'):
            setattr(cls, '__repr__', lambda self: '<%s: %s>' % (
                _meta.model_name, self.__unicode__()))

        exception_class = type('%sDoesNotExist' % _meta.model_name, (DoesNotExist,), {})
        cls.DoesNotExist = exception_class
        
        return cls


class Model(object):
    __metaclass__ = BaseModel
    
    def __init__(self, *args, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    
    def __eq__(self, other):
        return other.__class__ == self.__class__ and \
               self.get_pk() and \
               other.get_pk() == self.get_pk()
    
    def get_field_dict(self):
        def get_field_val(field):
            field_value = getattr(self, field.name)
            if not self.get_pk() and field_value is None and field.default is not None:
                if callable(field.default):
                    field_value = field.default()
                else:
                    field_value = field.default
                setattr(self, field.name, field_value)
            return (field.name, field_value)
        
        pairs = map(get_field_val, self._meta.fields.values())
        return dict(pairs)
    
    @classmethod
    def table_exists(cls):
        return cls._meta.db_table in cls._meta.database.get_tables()
    
    @classmethod
    def create_table(cls, fail_silently=False):
        if fail_silently and cls.table_exists():
            return

        cls._meta.database.create_table(cls)
        
        for field_name, field_obj in cls._meta.fields.items():
            if isinstance(field_obj, PrimaryKeyField):
                cls._meta.database.create_index(cls, field_obj.name, True)
            elif isinstance(field_obj, ForeignKeyField):
                cls._meta.database.create_index(cls, field_obj.name, field_obj.unique)
            elif field_obj.db_index or field_obj.unique:
                cls._meta.database.create_index(cls, field_obj.name, field_obj.unique)
    
    @classmethod
    def drop_table(cls, fail_silently=False):
        cls._meta.database.drop_table(cls, fail_silently)
    
    @classmethod
    def filter(cls, *args, **kwargs):
        return filter_query(cls, *args, **kwargs)
    
    @classmethod
    def select(cls, query=None):
        select_query = SelectQuery(cls, query)
        if cls._meta.ordering:
            select_query = select_query.order_by(*cls._meta.ordering)
        return select_query
    
    @classmethod
    def update(cls, **query):
        return UpdateQuery(cls, **query)
    
    @classmethod
    def insert(cls, **query):
        return InsertQuery(cls, **query)
    
    @classmethod
    def delete(cls, **query):
        return DeleteQuery(cls, **query)
    
    @classmethod
    def raw(cls, sql, *params):
        return RawQuery(cls, sql, *params)

    @classmethod
    def create(cls, **query):
        inst = cls(**query)
        inst.save()
        return inst

    @classmethod
    def get_or_create(cls, **query):
        try:
            inst = cls.get(**query)
        except cls.DoesNotExist:
            inst = cls.create(**query)
        return inst
    
    @classmethod            
    def get(cls, *args, **kwargs):
        return cls.select().get(*args, **kwargs)
    
    def get_pk(self):
        return getattr(self, self._meta.pk_name, None)
    
    def save(self):
        field_dict = self.get_field_dict()
        field_dict.pop(self._meta.pk_name)
        if self.get_pk():
            update = self.update(
                **field_dict
            ).where(**{self._meta.pk_name: self.get_pk()})
            update.execute()
        else:
            insert = self.insert(**field_dict)
            new_pk = insert.execute()
            setattr(self, self._meta.pk_name, new_pk)

    def delete_instance(self):
        return self.delete().where(**{
            self._meta.pk_name: self.get_pk()
        }).execute()
