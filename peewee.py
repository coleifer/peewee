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
import copy
import decimal
import logging
import os
import re
import threading
import time
import warnings

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

if psycopg2:
    import psycopg2.extensions
    psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
    psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)


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
    sequence_support = False
    reserved_tables = []
    quote_char = '"'
    
    def get_field_types(self):
        field_types = {
            'integer': 'INTEGER',
            'bigint': 'INTEGER',
            'float': 'REAL',
            'decimal': 'DECIMAL',
            'double': 'REAL',
            'string': 'VARCHAR',
            'text': 'TEXT',
            'datetime': 'DATETIME',
            'primary_key': 'INTEGER',
            'primary_key_with_sequence': 'INTEGER',
            'foreign_key': 'INTEGER',
            'boolean': 'SMALLINT',
            'blob': 'BLOB',
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
        """
        When a lookup is being performed as a part of a WHERE clause, provides
        a way to alter the incoming value that is passed to the database driver
        as part of the list of parameters
        """
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
        'lt': '< %s',
        'lte': '<= %s',
        'gt': '> %s',
        'gte': '>= %s',
        'eq': '= %s',
        'ne': '!= %s', # watch yourself with this one
        'in': 'IN (%s)', # special-case to list q-marks
        'is': 'IS %s',
        'isnull': 'IS NULL',
        'between': 'BETWEEN %s AND %s',
        'icontains': "LIKE %s ESCAPE '\\'", # surround param with %'s
        'contains': "GLOB %s", # surround param with *'s
        'istartswith': "LIKE %s ESCAPE '\\'",
        'startswith': "GLOB %s",
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
        'isnull': 'IS NULL',
        'between': 'BETWEEN %s AND %s',
        'icontains': 'ILIKE %s', # surround param with %'s
        'contains': 'LIKE %s', # surround param with *'s
        'istartswith': 'ILIKE %s',
        'startswith': 'LIKE %s',
    }
    reserved_tables = ['user']
    sequence_support = True

    def connect(self, database, **kwargs):
        if not psycopg2:
            raise ImproperlyConfigured('psycopg2 must be installed on the system')
        return psycopg2.connect(database=database, **kwargs)
    
    def get_field_overrides(self):
        return {
            'primary_key': 'SERIAL',
            'primary_key_with_sequence': 'INTEGER',
            'datetime': 'TIMESTAMP',
            'decimal': 'NUMERIC',
            'double': 'DOUBLE PRECISION',
            'bigint': 'BIGINT',
            'boolean': 'BOOLEAN',
            'blob': 'BYTEA',
        }
    
    def last_insert_id(self, cursor, model):
        if model._meta.pk_sequence:
            cursor.execute("SELECT CURRVAL('\"%s\"')" % (
                model._meta.pk_sequence))
        else:
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
        'isnull': 'IS NULL',
        'between': 'BETWEEN %s AND %s',
        'icontains': 'LIKE %s', # surround param with %'s
        'contains': 'LIKE BINARY %s', # surround param with *'s
        'istartswith': 'LIKE %s',
        'startswith': 'LIKE BINARY %s',
    }
    quote_char = '`'

    def connect(self, database, **kwargs):
        if not mysql:
            raise ImproperlyConfigured('MySQLdb must be installed on the system')
        conn_kwargs = {
            'charset': 'utf8',
            'use_unicode': True,
        }
        conn_kwargs.update(kwargs)
        return mysql.connect(db=database, **conn_kwargs)

    def get_field_overrides(self):
        return {
            'primary_key': 'integer AUTO_INCREMENT',
            'boolean': 'bool',
            'float': 'float',
            'double': 'double precision',
            'bigint': 'bigint',
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
    def require_sequence_support(func):
        def inner(self, *args, **kwargs):
            if not self.adapter.sequence_support:
                raise ValueError('%s adapter does not support sequences' % (self.adapter))
            return func(self, *args, **kwargs)
        return inner
        
    def __init__(self, adapter, database, threadlocals=False, autocommit=True, **connect_kwargs):
        self.adapter = adapter
        self.database = database
        self.connect_kwargs = connect_kwargs
        
        if threadlocals:
            self.__local = threading.local()
        else:
            self.__local = type('DummyLocal', (object,), {})
        
        self._conn_lock = threading.Lock()
        self.autocommit = autocommit
    
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
    
    def execute(self, sql, params=None):
        cursor = self.get_cursor()
        res = cursor.execute(sql, params or ())
        if self.get_autocommit():
            self.commit()
        logger.debug((sql, params))
        return cursor
    
    def commit(self):
        self.get_conn().commit()
    
    def rollback(self):
        self.get_conn().rollback()
    
    def set_autocommit(self, autocommit):
        self.__local.autocommit = autocommit
    
    def get_autocommit(self):
        if not hasattr(self.__local, 'autocommit'):
            self.set_autocommit(self.autocommit)
        return self.__local.autocommit
    
    def commit_on_success(self, func):
        def inner(*args, **kwargs):
            orig = self.get_autocommit()
            self.set_autocommit(False)
            try:
                res = func(*args, **kwargs)
                self.commit()
            except:
                self.rollback()
                raise
            else:
                return res
            finally:
                self.set_autocommit(orig)
        return inner
    
    def last_insert_id(self, cursor, model):
        return self.adapter.last_insert_id(cursor, model)
    
    def rows_affected(self, cursor):
        return self.adapter.rows_affected(cursor)

    def quote_name(self, name):
        return ''.join((self.adapter.quote_char, name, self.adapter.quote_char))
    
    def column_for_field(self, field):
        return self.column_for_field_type(field.get_db_field())
    
    def column_for_field_type(self, db_field_type):
        try:
            return self.adapter.get_field_types()[db_field_type]
        except KeyError:
            raise AttributeError('Unknown field type: "%s", valid types are: %s' % \
                db_field_type, ', '.join(self.adapter.get_field_types().keys())
            )

    def field_sql(self, field):
        return '%s %s' % (self.quote_name(field.db_column), field.render_field_template())

    def create_table(self, model_class, safe=False):
        if model_class._meta.pk_sequence and self.adapter.sequence_support:
            if not self.sequence_exists(model_class._meta.pk_sequence):
                self.create_sequence(model_class._meta.pk_sequence)
        framing = safe and "CREATE TABLE IF NOT EXISTS %s (%s);" or "CREATE TABLE %s (%s);"
        columns = []

        for field in model_class._meta.get_fields():
            columns.append(self.field_sql(field))

        table = self.quote_name(model_class._meta.db_table)
        query = framing % (table, ', '.join(columns))
        
        self.execute(query)
    
    def create_index(self, model_class, field_name, unique=False):
        framing = 'CREATE %(unique)s INDEX %(index)s ON %(table)s(%(field)s);'
        
        if field_name not in model_class._meta.fields:
            raise AttributeError(
                'Field %s not on model %s' % (field_name, model_class)
            )
        
        field_obj = model_class._meta.fields[field_name]

        db_table = model_class._meta.db_table
        index_name = self.quote_name('%s_%s' % (db_table, field_obj.db_column))
        
        unique_expr = ternary(unique, 'UNIQUE', '')
        
        query = framing % {
            'unique': unique_expr,
            'index': index_name,
            'table': self.quote_name(db_table),
            'field': self.quote_name(field_obj.db_column),
        }
        
        self.execute(query)

    def create_foreign_key(self, model_class, field):
        return self.create_index(model_class, field.name, field.unique)
    
    def drop_table(self, model_class, fail_silently=False):
        framing = fail_silently and 'DROP TABLE IF EXISTS %s;' or 'DROP TABLE %s;'
        self.execute(framing % self.quote_name(model_class._meta.db_table))
    
    def add_column_sql(self, model_class, field_name):
        field = model_class._meta.fields[field_name]
        return 'ALTER TABLE %s ADD COLUMN %s' % (
            self.quote_name(model_class._meta.db_table),
            self.field_sql(field),
        )
    
    def rename_column_sql(self, model_class, field_name, new_name):
        # this assumes that the field on the model points to the *old* fieldname
        field = model_class._meta.fields[field_name]
        return 'ALTER TABLE %s RENAME COLUMN %s TO %s' % (
            self.quote_name(model_class._meta.db_table),
            self.quote_name(field.db_column),
            self.quote_name(new_name),
        )
    
    def drop_column_sql(self, model_class, field_name):
        field = model_class._meta.fields[field_name]
        return 'ALTER TABLE %s DROP COLUMN %s' % (
            self.quote_name(model_class._meta.db_table),
            self.quote_name(field.db_column),
        )
    
    @require_sequence_support
    def create_sequence(self, sequence_name):
        return self.execute('CREATE SEQUENCE %s;' % self.quote_name(sequence_name))
    
    @require_sequence_support
    def drop_sequence(self, sequence_name):
        return self.execute('DROP SEQUENCE %s;' % self.quote_name(sequence_name))
    
    def get_indexes_for_table(self, table):
        raise NotImplementedError
    
    def get_tables(self):
        raise NotImplementedError
    
    def sequence_exists(self):
        raise NotImplementedError


class SqliteDatabase(Database):
    def __init__(self, database, **connect_kwargs):
        super(SqliteDatabase, self).__init__(SqliteAdapter(), database, **connect_kwargs)
    
    def get_indexes_for_table(self, table):
        res = self.execute('PRAGMA index_list(%s);' % self.quote_name(table))
        rows = sorted([(r[1], r[2] == 1) for r in res.fetchall()])
        return rows
    
    def get_tables(self):
        res = self.execute('select name from sqlite_master where type="table" order by name')
        return [r[0] for r in res.fetchall()]
    
    def drop_column_sql(self, model_class, field_name):
        raise NotImplementedError('Sqlite3 does not have direct support for dropping columns')
    
    def rename_column_sql(self, model_class, field_name, new_name):
        raise NotImplementedError('Sqlite3 does not have direct support for renaming columns')


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
    
    def sequence_exists(self, sequence):
        res = self.execute("""
            SELECT COUNT(*)
            FROM pg_class, pg_namespace
            WHERE relkind='S'
                AND pg_class.relnamespace = pg_namespace.oid
                AND relname=%s""", (sequence,))
        return bool(res.fetchone()[0])


class MySQLDatabase(Database):
    def __init__(self, database, **connect_kwargs):
        super(MySQLDatabase, self).__init__(MySQLAdapter(), database, **connect_kwargs)
    
    def create_foreign_key(self, model_class, field):
        framing = """ 
            ALTER TABLE %(table)s ADD CONSTRAINT %(constraint)s
            FOREIGN KEY (%(field)s) REFERENCES %(to)s(%(to_field)s)%(cascade)s;
        """
        db_table = model_class._meta.db_table
        constraint = 'fk_%s_%s_%s' % (
            db_table,
            field.to._meta.db_table,
            field.db_column,
        )
 
        query = framing % {
            'table': self.quote_name(db_table),
            'constraint': self.quote_name(constraint),
            'field': self.quote_name(field.db_column),
            'to': self.quote_name(field.to._meta.db_table),
            'to_field': self.quote_name(field.to._meta.pk_name),
            'cascade': ' ON DELETE CASCADE' if field.cascade else '',
        }
 
        self.execute(query)
        return super(MySQLDatabase, self).create_foreign_key(model_class, field)
    
    def rename_column_sql(self, model_class, field_name, new_name):
        field = model_class._meta.fields[field_name]
        return 'ALTER TABLE %s CHANGE COLUMN %s %s %s' % (
            self.quote_name(model_class._meta.db_table),
            self.quote_name(field.db_column),
            self.quote_name(new_name),
            field.render_field_template(),
        )
    
    def get_indexes_for_table(self, table):
        res = self.execute('SHOW INDEXES IN %s;' % self.quote_name(table))
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
    def __init__(self, model, cursor, meta=None):
        self.model = model
        self.cursor = cursor
        self.query_meta = meta or {}
        self.column_meta = self.query_meta.get('columns')
        self.join_meta = self.query_meta.get('graph')
        
        self.__ct = 0
        self.__idx = 0
        
        self._result_cache = []
        self._populated = False
    
    def model_from_rowset(self, model_class, attr_dict):
        instance = model_class()
        for attr, value in attr_dict.iteritems():
            if attr in instance._meta.columns:
                field = instance._meta.columns[attr]
                setattr(instance, attr, field.python_value(value))
            else:
                setattr(instance, attr, value)
        return instance
    
    def _row_to_dict(self, row):
        return dict((self.cursor.description[i][0], value)
            for i, value in enumerate(row))
    
    def construct_instance(self, row):
        if not self.column_meta:
            # use attribute names pulled from the result cursor description,
            # and do not attempt to follow joined models
            row_dict = self._row_to_dict(row)
            return self.model_from_rowset(self.model, row_dict)
        else:
            # we have columns, models, and a graph of joins to reconstruct
            collected_models = {}
            for i, (model, col) in enumerate(self.column_meta):
                value = row[i]
                
                if isinstance(col, tuple):
                    if len(col) == 3:
                        model = self.model # special-case aggregates
                        col_name = attr = col[2]
                    else:
                        col_name, attr = col
                else:
                    col_name = attr = col
                
                if model not in collected_models:
                    collected_models[model] = model()
                
                instance = collected_models[model]
                
                if col_name in instance._meta.columns:
                    field = instance._meta.columns[attr]
                    setattr(instance, field.name, field.python_value(value))
                else:
                    setattr(instance, attr, value)
            
            return self.follow_joins(self.join_meta, collected_models, self.model)
    
    def follow_joins(self, joins, collected_models, current):
        inst = collected_models[current]
        
        if current not in joins:
            return inst
    
        for joined_model, _, _ in joins[current]:
            if joined_model in collected_models:
                joined_inst = self.follow_joins(joins, collected_models, joined_model)
                fk_field = current._meta.get_related_field_for_model(joined_model)
                
                if not fk_field:
                    continue
                
                if not joined_inst.get_pk():
                    joined_inst.set_pk(getattr(inst, fk_field.id_storage))
                
                setattr(inst, fk_field.name, joined_inst)
                setattr(inst, fk_field.id_storage, joined_inst.get_pk())
        
        return inst
    
    def __iter__(self):
        self.__idx = 0

        if not self._populated:
            return self
        else:
            return iter(self._result_cache)
    
    def first(self):
        try:
            self.__idx = 0 # move to beginning of the list
            inst = self.next()
        except StopIteration:
            inst = None
        
        self.__idx = 0
        return inst

    def fill_cache(self):
        if not self._populated:
            idx = self.__idx
            self.__idx = self.__ct
            for x in self:
                pass
            self.__idx = idx
    
    def iterate(self):
        row = self.cursor.fetchone()
        if row:
            return self.construct_instance(row)
        else:
            self._populated = True
            raise StopIteration
    
    def iterator(self):
        while 1:
            yield self.iterate()
    
    def next(self):
        if self.__idx < self.__ct:
            inst = self._result_cache[self.__idx]
            self.__idx += 1
            return inst
        
        instance = self.iterate()
        self._result_cache.append(instance)
        self.__ct += 1
        self.__idx += 1
        return instance


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
    def __init__(self, connector='AND', children=None):
        self.connector = connector
        self.children = children or []
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
    def __init__(self, _model=None, **kwargs):
        self.model = _model
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


class F(object):
    def __init__(self, field, model=None):
        self.field = field
        self.model = model
        self.op = None
        self.value = None

    def __add__(self, rhs):
        self.op = '+'
        self.value = rhs
        return self

    def __sub__(self, rhs):
        self.op = '-'
        self.value = rhs
        return self


def apply_model(model, item):
    """
    Q() objects take a model, which provides context for the keyword arguments.
    In this way Q() objects can be mixed across models.  The purpose of this
    function is to recurse into a query datastructure and apply the given model
    to all Q() objects that do not have a model explicitly set.
    """
    if isinstance(item, Node):
        for child in item.children:
            apply_model(model, child)
    elif isinstance(item, Q):
        if item.model is None:
            item.model = model

def parseq(model, *args, **kwargs):
    """
    Convert any query into a single Node() object -- used to build up the list
    of where clauses when querying.
    """
    node = Node()
    
    for piece in args:
        apply_model(model, piece)
        if isinstance(piece, (Q, Node)):
            node.children.append(piece)
        else:
            raise TypeError('Unknown object: %s', piece)

    if kwargs:
        node.children.append(Q(model, **kwargs))

    return node

def find_models(item):
    """
    Utility function to find models referenced in a query and return a set()
    containing them.  This function is used to generate the list of models that
    are part of a where clause.
    """
    seen = set()
    if isinstance(item, Node):
        for child in item.children:
            seen.update(find_models(child))
    elif isinstance(item, Q):
        seen.add(item.model)
    return seen


class EmptyResultException(Exception):
    pass


class BaseQuery(object):
    query_separator = '__'
    force_alias = False
    
    def __init__(self, model):
        self.model = model
        self.query_context = model
        self.database = self.model._meta.database
        self.operations = self.database.adapter.operations
        self.interpolation = self.database.adapter.interpolation
        
        self._dirty = True
        self._where = []
        self._where_models = set()
        self._joins = {}
        self._joined_models = set()
    
    def _clone_dict_graph(self, dg):
        cloned = {}
        for node, edges in dg.items():
            cloned[node] = list(edges)
        return cloned
    
    def clone_where(self):
        return list(self._where)
    
    def clone_joins(self):
        return self._clone_dict_graph(self._joins)
    
    def clone(self):
        raise NotImplementedError

    def qn(self, name):
        return self.database.quote_name(name)
    
    def lookup_cast(self, lookup, value):
        return self.database.adapter.lookup_cast(lookup, value)
    
    def parse_query_args(self, model, **query):
        """
        Parse out and normalize clauses in a query.  The query is composed of
        various column+lookup-type/value pairs.  Validates that the lookups
        are valid and returns a list of lookup tuples that have the form:
        (field name, (operation, value))
        """
        parsed = []
        for lhs, rhs in query.iteritems():
            if self.query_separator in lhs:
                lhs, op = lhs.rsplit(self.query_separator, 1)
            else:
                op = 'eq'
            
            if lhs in model._meta.columns:
                lhs = model._meta.columns[lhs].name
            
            try:
                field = model._meta.get_field_by_name(lhs)
            except AttributeError:
                field = model._meta.get_related_field_by_name(lhs)
                if field is None:
                    raise
                    
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
            elif op == 'isnull':
                operation = 'IS NULL' if rhs else 'IS NOT NULL'
                lookup_value = []
            elif isinstance(rhs, F):
                lookup_value = rhs
                operation = self.operations[op] # leave as "%s"
            elif isinstance(rhs, (list, tuple)):
                lookup_value = [field.db_value(o) for o in rhs]
                operation = self.operations[op] % \
                    tuple(self.interpolation for v in lookup_value)
            else:
                lookup_value = field.db_value(rhs)
                operation = self.operations[op] % self.interpolation
            
            parsed.append(
                (field.db_column, (operation, self.lookup_cast(op, lookup_value)))
            )
        
        return parsed
    
    @returns_clone
    def where(self, *args, **kwargs):
        parsed = parseq(self.query_context, *args, **kwargs)
        if parsed:
            self._where.append(parsed)
            self._where_models.update(find_models(parsed))

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

    def combine_field(self, alias, field_col):
        quoted = self.qn(field_col)
        if alias:
            return '%s.%s' % (alias, quoted)
        return quoted

    def safe_combine(self, model, alias, col):
        if col in model._meta.columns:
            return self.combine_field(alias, col)
        elif col in model._meta.fields:
            return self.combine_field(alias, model._meta.fields[col].db_column)
        return col
    
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
                left_field = field.db_column
                right_field = model._meta.pk_name
            else:
                field = from_model._meta.get_reverse_related_field_for_model(model, on)
                left_field = from_model._meta.pk_name
                right_field = field.db_column
            
            if join_type is None:
                if field.null and model not in self._where_models:
                    join_type = 'LEFT OUTER'
                else:
                    join_type = 'INNER'
            
            computed.append(
                '%s JOIN %s AS %s ON %s = %s' % (
                    join_type,
                    self.qn(model._meta.db_table),
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
        if alias_required:
            alias_count += 1
            alias_map[self.model] = 't%d' % alias_count
        else:
            alias_map[self.model] = ''
        
        computed_joins = self.follow_joins(self.model, alias_map, alias_required, alias_count)
        
        clauses = [self.parse_node(node, alias_map) for node in self._where]
        
        return computed_joins, clauses, alias_map
    
    def flatten_clauses(self, clauses):
        where_with_alias = []
        where_data = []
        for query, data in clauses:
            where_with_alias.append(query)
            where_data.extend(data)
        return where_with_alias, where_data
    
    def convert_where_to_params(self, where_data):
        flattened = []
        for clause in where_data:
            if isinstance(clause, (tuple, list)):
                flattened.extend(clause)
            else:
                flattened.append(clause)
        return flattened
    
    def parse_node(self, node, alias_map):
        query = []
        query_data = []
        for child in node.children:
            if isinstance(child, Q):
                parsed, data = self.parse_q(child, alias_map)
                query.append(parsed)
                query_data.extend(data)
            elif isinstance(child, Node):
                parsed, data = self.parse_node(child, alias_map)
                query.append('(%s)' % parsed)
                query_data.extend(data)
        connector = ' %s ' % node.connector
        query = connector.join(query)
        if node.negated:
            query = 'NOT (%s)' % query
        return query, query_data
    
    def parse_q(self, q, alias_map):
        model = q.model or self.model
        query = []
        query_data = []
        parsed = self.parse_query_args(model, **q.query)
        for (name, lookup) in parsed:
            operation, value = lookup
            if isinstance(value, SelectQuery):
                sql, value = self.convert_subquery(value)
                operation = operation % sql

            if isinstance(value, F):
                f_model = value.model or model
                operation = operation % self.parse_f(value, f_model, alias_map)
            else:
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
    
    def parse_f(self, f_object, model, alias_map):
        combined = self.combine_field(alias_map[model], f_object.field)
        if f_object.op is not None:
            combined = '(%s %s %s)' % (combined, f_object.op, f_object.value)

        return combined

    def convert_subquery(self, subquery):
        orig_query = subquery.query
        if subquery.query == '*':
            subquery.query = subquery.model._meta.pk_name
        
        subquery.force_alias, orig_alias = True, subquery.force_alias
        sql, data = subquery.sql()
        subquery.query = orig_query
        subquery.force_alias = orig_alias
        return sql, data
    
    def sorted_models(self, alias_map):
        return [
            (model, alias) \
                for (model, alias) in sorted(alias_map.items(), key=lambda i: i[1])
        ]
    
    def sql(self):
        raise NotImplementedError
    
    def execute(self):
        raise NotImplementedError
    
    def raw_execute(self, query, params):
        return self.database.execute(query, params)


class RawQuery(BaseQuery):
    def __init__(self, model, query, *params):
        self._sql = query
        self._params = list(params)
        super(RawQuery, self).__init__(model)

    def clone(self):
        return RawQuery(self.model, self._sql, *self._params)
    
    def sql(self):
        return self._sql, self._params
    
    def execute(self):
        return QueryResultWrapper(self.model, self.raw_execute(*self.sql()))
    
    def join(self):
        raise AttributeError('Raw queries do not support joining programmatically')
    
    def where(self):
        raise AttributeError('Raw queries do not support querying programmatically')
    
    def switch(self):
        raise AttributeError('Raw queries do not support switching contexts')
    
    def __iter__(self):
        return iter(self.execute())


class SelectQuery(BaseQuery):
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
        query._where_models = set(self._where_models)
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
        if self._distinct:
            return self.wrapped_count()
        
        clone = self.order_by()
        clone._limit = clone._offset = None
        
        if clone.use_aliases():
            clone.query = 'COUNT(t1.%s)' % (clone.model._meta.pk_name)
        else:
            clone.query = 'COUNT(%s)' % (clone.model._meta.pk_name)
        
        res = clone.database.execute(*clone.sql())
        
        return (res.fetchone() or [0])[0]
    
    def wrapped_count(self):
        clone = self.order_by()
        clone._limit = clone._offset = None
        
        sql, params = clone.sql()
        query = 'SELECT COUNT(1) FROM (%s) AS wrapped_select' % sql
        
        res = clone.database.execute(query, params)
        
        return res.fetchone()[0]
    
    @returns_clone
    def group_by(self, *clauses):
        model = self.query_context
        for clause in clauses:
            if isinstance(clause, basestring):
                fields = (clause,)
            elif isinstance(clause, (list, tuple)):
                fields = clause
            elif issubclass(clause, Model):
                model = clause
                fields = clause._meta.get_field_names()
            
            self._group_by.append((model, fields))
    
    @returns_clone
    def having(self, *clauses):
        self._having = clauses
    
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
        orig_ctx = self.query_context
        self.query_context = self.model
        query = self.where(*args, **kwargs).paginate(1, 1)
        try:
            obj = query.execute().next()
            return obj
        except StopIteration:
            raise self.model.DoesNotExist('instance matching query does not exist:\nSQL: %s\nPARAMS: %s' % (
                query.sql()
            ))
        finally:
            self.query_context = orig_ctx
    
    def filter(self, *args, **kwargs):
        return filter_query(self, *args, **kwargs)
    
    def annotate(self, related_model, aggregation=None):
        return annotate_query(self, related_model, aggregation)

    def parse_select_query(self, alias_map):
        q = self.query
        
        if isinstance(q, (list, tuple)):
            q = {self.model: self.query}
        elif isinstance(q, basestring):
            # convert '*' and primary key lookups
            if q == '*':
                q = {self.model: self.model._meta.get_field_names()}
            elif q == self.model._meta.pk_name:
                q = {self.model: [self.model._meta.pk_name]}
            else:
                return q, []
        
        # by now we should have a dictionary if a valid type was passed in
        if not isinstance(q, dict):
            raise TypeError('Unknown type encountered parsing select query')
        
        # gather aliases and models
        sorted_models = self.sorted_models(alias_map)
        
        # normalize if we are working with a dictionary
        columns = []
        aggregates = []
        model_cols = []
        
        for model, alias in sorted_models:
            if model not in q:
                continue
            
            if '*' in q[model]:
                idx = q[model].index('*')
                q[model] =  q[model][:idx] + model._meta.get_field_names() + q[model][idx+1:]
            
            for clause in q[model]:
                if isinstance(clause, tuple):
                    if len(clause) == 3:
                        func, col_name, col_alias = clause
                        column = model._meta.get_column(col_name)
                        aggregates.append('%s(%s) AS %s' % \
                            (func, self.safe_combine(model, alias, column), col_alias)
                        )
                        model_cols.append((model, (func, column, col_alias)))
                    elif len(clause) == 2:
                        col_name, col_alias = clause
                        column = model._meta.get_column(col_name)
                        columns.append('%s AS %s' % \
                            (self.safe_combine(model, alias, column), col_alias)
                        )
                        model_cols.append((model, (column, col_alias)))
                    else:
                        raise ValueError('Clause must be either a 2- or 3-tuple')
                else:
                    column = model._meta.get_column(clause)
                    columns.append(self.safe_combine(model, alias, column))
                    model_cols.append((model, column))
        
        return ', '.join(columns + aggregates), model_cols

    
    def sql_meta(self):
        joins, clauses, alias_map = self.compile_where()
        where, where_data = self.flatten_clauses(clauses)
        
        table = self.qn(self.model._meta.db_table)

        params = []
        group_by = []
        use_aliases = self.use_aliases()
        
        if use_aliases:
            table = '%s AS %s' % (table, alias_map[self.model])

        for model, clause in self._group_by:
            if use_aliases:
                alias = alias_map[model]
            else:
                alias = ''

            for field in clause:
                group_by.append(self.safe_combine(model, alias, field))

        parsed_query, model_cols = self.parse_select_query(alias_map)
        query_meta = {
            'columns': model_cols,
            'graph': self._joins,
        }
        
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
            if use_aliases:
                alias = alias_map[model]
            else:
                alias = ''
            
            order_by.append('%s %s' % (self.safe_combine(model, alias, field), ordering))
        
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
        
        return ' '.join(pieces), params, query_meta
    
    def sql(self):
        query, params, meta = self.sql_meta()
        return query, params
    
    def execute(self):
        if self._dirty or not self._qr:
            try:
                sql, params, meta = self.sql_meta()
            except EmptyResultException:
                return []
            else:
                self._qr = QueryResultWrapper(self.model, self.raw_execute(sql, params), meta)
                self._dirty = False
                return self._qr
        else:
            # call the __iter__ method directly
            return self._qr
    
    def __iter__(self):
        return iter(self.execute())


class UpdateQuery(BaseQuery):
    def __init__(self, model, **kwargs):
        self.update_query = kwargs
        super(UpdateQuery, self).__init__(model)
    
    def clone(self):
        query = UpdateQuery(self.model, **self.update_query)
        query._where = self.clone_where()
        query._where_models = set(self._where_models)
        query._joined_models = self._joined_models.copy()
        query._joins = self.clone_joins()
        return query
    
    def parse_update(self):
        sets = {}
        for k, v in self.update_query.iteritems():
            if k in self.model._meta.columns:
                k = self.model._meta.columns[k].name
            
            try:
                field = self.model._meta.get_field_by_name(k)
            except AttributeError:
                field = self.model._meta.get_related_field_by_name(k)
                if field is None:
                    raise
            
            if not isinstance(v, F):
                v = field.db_value(v)
            
            sets[field.db_column] = v
        
        return sets
    
    def sql(self):
        joins, clauses, alias_map = self.compile_where()
        where, where_data = self.flatten_clauses(clauses)
        set_statement = self.parse_update()

        params = []
        update_params = []
        
        alias = alias_map.get(self.model)

        for k, v in set_statement.iteritems():
            if isinstance(v, F):
                value = self.parse_f(v, v.model or self.model, alias_map)
            else:
                params.append(v)
                value = self.interpolation
            
            update_params.append('%s=%s' % (self.combine_field(alias, k), value))
        
        update = 'UPDATE %s SET %s' % (
            self.qn(self.model._meta.db_table), ', '.join(update_params))
        where = ' AND '.join(where)
        
        pieces = [update]
        
        if where:
            pieces.append('WHERE %s' % where)
            params.extend(self.convert_where_to_params(where_data))
        
        return ' '.join(pieces), params
    
    def join(self, *args, **kwargs):
        raise AttributeError('Update queries do not support JOINs in sqlite')
    
    def execute(self):
        result = self.raw_execute(*self.sql())
        return self.database.rows_affected(result)


class DeleteQuery(BaseQuery):
    def clone(self):
        query = DeleteQuery(self.model)
        query._where = self.clone_where()
        query._where_models = set(self._where_models)
        query._joined_models = self._joined_models.copy()
        query._joins = self.clone_joins()
        return query
    
    def sql(self):
        joins, clauses, alias_map = self.compile_where()
        where, where_data = self.flatten_clauses(clauses)

        params = []
        
        delete = 'DELETE FROM %s' % (self.qn(self.model._meta.db_table))
        where = ' AND '.join(where)
        
        pieces = [delete]
        
        if where:
            pieces.append('WHERE %s' % where)
            params.extend(self.convert_where_to_params(where_data))
        
        return ' '.join(pieces), params
    
    def join(self, *args, **kwargs):
        raise AttributeError('Update queries do not support JOINs in sqlite')
    
    def execute(self):
        result = self.raw_execute(*self.sql())
        return self.database.rows_affected(result)


class InsertQuery(BaseQuery):
    def __init__(self, model, **kwargs):
        self.insert_query = kwargs
        super(InsertQuery, self).__init__(model)
    
    def parse_insert(self):
        cols = []
        vals = []
        for k, v in self.insert_query.iteritems():
            if k in self.model._meta.columns:
                k = self.model._meta.columns[k].name
            
            try:
                field = self.model._meta.get_field_by_name(k)
            except AttributeError:
                field = self.model._meta.get_related_field_by_name(k)
                if field is None:
                    raise
            
            cols.append(self.qn(field.db_column))
            vals.append(field.db_value(v))
        
        return cols, vals
    
    def sql(self):
        cols, vals = self.parse_insert()
        
        insert = 'INSERT INTO %s (%s) VALUES (%s)' % (
            self.qn(self.model._meta.db_table),
            ','.join(cols),
            ','.join(self.interpolation for v in vals)
        )
        
        return insert, vals
    
    def where(self, *args, **kwargs):
        raise AttributeError('Insert queries do not support WHERE clauses')
    
    def join(self, *args, **kwargs):
        raise AttributeError('Insert queries do not support JOINs')
    
    def execute(self):
        result = self.raw_execute(*self.sql())
        return self.database.last_insert_id(result, self.model)


def model_or_select(m_or_q):
    """
    Return both a model and a select query for the provided model *OR* select
    query.
    """
    if isinstance(m_or_q, BaseQuery):
        return (m_or_q.model, m_or_q)
    else:
        return (m_or_q, m_or_q.select())

def convert_lookup(model, joins, lookup):
    """
    Given a model, a graph of joins, and a lookup, return a tuple containing
    a normalized lookup:
    
    (model actually being queried, updated graph of joins, normalized lookup)
    """
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
            for piece in pieces:
                # piece is something like 'blog' or 'entry_set'
                joined_model = None
                for field in query_model._meta.get_fields():
                    if not isinstance(field, ForeignKeyField):
                        continue
                    
                    if piece in (field.name, field.db_column, field.related_name):
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
    
    # traverse Q() objects, find any joins that may be lurking -- clean up the
    # lookups and assign the correct model
    def fix_q(node_or_q, joins):
        if isinstance(node_or_q, Node):
            for child in node_or_q.children:
                fix_q(child, joins)
        elif isinstance(node_or_q, Q):
            new_query = {}
            curr_model = node_or_q.model or model
            for raw_lookup, value in node_or_q.query.items():
                query_model, joins, lookup = convert_lookup(curr_model, joins, raw_lookup)
                new_query[lookup] = value
            node_or_q.model = query_model
            node_or_q.query = new_query
    
    for node_or_q in args:
        fix_q(node_or_q, joins)
    
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
    
    for node in args:
        select_query = select_query.where(node)
    
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
    """
    Perform an aggregation against a related model
    """
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


class FieldDescriptor(object):
    def __init__(self, field):
        self.field = field
        self._cache_name = '__%s' % self.field.name
    
    def __get__(self, instance, instance_type=None):
        if instance:
            return getattr(instance, self._cache_name, None)
        return self.field
    
    def __set__(self, instance, value):
        setattr(instance, self._cache_name, value)


class Field(object):
    db_field = ''
    default = None
    field_template = "%(column_type)s%(nullable)s"
    _field_counter = 0
    _order = 0

    def get_attributes(self):
        return {}
    
    def __init__(self, null=False, db_index=False, unique=False, verbose_name=None,
                 help_text=None, db_column=None, *args, **kwargs):
        self.null = null
        self.db_index = db_index
        self.unique = unique
        self.attributes = self.get_attributes()
        self.default = kwargs.get('default', None)
        self.verbose_name = verbose_name
        self.help_text = help_text
        self.db_column = db_column
        
        kwargs['nullable'] = ternary(self.null, '', ' NOT NULL')
        self.attributes.update(kwargs)
        
        Field._field_counter += 1
        self._order = Field._field_counter
    
    def add_to_class(self, klass, name):
        self.name = name
        self.model = klass
        self.verbose_name = self.verbose_name or re.sub('_+', ' ', name).title()
        self.db_column = self.db_column or self.name
        setattr(klass, name, FieldDescriptor(self))
    
    def get_db_field(self):
        return self.db_field
    
    def render_field_template(self):
        col_type = self.model._meta.database.column_for_field(self)
        self.attributes['column_type'] = col_type
        return self.field_template % self.attributes
    
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


class BigIntegerField(IntegerField):
    db_field = 'bigint'


class BooleanField(IntegerField):
    db_field = 'boolean'
    
    def db_value(self, value):
        return bool(value)
    
    def python_value(self, value):
        return bool(value)


class FloatField(Field):
    db_field = 'float'
    
    def db_value(self, value):
        return self.null_wrapper(value, 0.0)
    
    def python_value(self, value):
        if value is not None:
            return float(value)


class DoubleField(FloatField):
    db_field = 'double'


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
    field_template = "%(column_type)s NOT NULL PRIMARY KEY%(nextval)s"
    sequence = None
    
    def get_attributes(self):
        return {'nextval': ''}
    
    def get_db_field(self):
        if self.model._meta.pk_sequence != None and self.model._meta.database.adapter.sequence_support:
            return 'primary_key_with_sequence'
        return self.db_field


class ForeignRelatedObject(object):    
    def __init__(self, to, field):
        self.to = to
        self.field = field
        self.field_name = self.field.name
        self.field_column = self.field.id_storage
        self.cache_name = '_cache_%s' % self.field_name
    
    def __get__(self, instance, instance_type=None):
        if not instance:
            return self.field
        
        if not getattr(instance, self.cache_name, None):
            id = getattr(instance, self.field_column, 0)
            qr = self.to.select().where(**{self.to._meta.pk_name: id})
            try:
                setattr(instance, self.cache_name, qr.get())
            except self.to.DoesNotExist:
                if not self.field.null:
                    raise
        return getattr(instance, self.cache_name, None)
    
    def __set__(self, instance, obj):
        if self.field.null and obj is None:
            setattr(instance, self.field_column, None)
            setattr(instance, self.cache_name, None)
        else:
            if isinstance(obj, int):
                setattr(instance, self.field_column, obj)
            else:
                assert isinstance(obj, self.to), "Cannot assign %s, invalid type" % obj
                setattr(instance, self.field_column, obj.get_pk())
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
        self._related_name = related_name
        self.cascade = cascade
        self.extra = extra

        kwargs.update({
            'cascade': ' ON DELETE CASCADE' if self.cascade else '',
            'extra': self.extra or '',
        })
        super(ForeignKeyField, self).__init__(null=null, *args, **kwargs)
    
    def add_to_class(self, klass, name):
        self.name = name
        self.model = klass
        self.db_column = self.db_column or self.name + '_id'
        
        if self.name == self.db_column:
            self.id_storage = self.db_column + '_id'
        else:
            self.id_storage = self.db_column

        if self.to == 'self':
            self.to = self.model

        self.verbose_name = self.verbose_name or re.sub('_', ' ', name).title()
        
        if self._related_name is not None:
            self.related_name = self._related_name
        else:
            self.related_name = klass._meta.db_table + '_set'
        
        klass._meta.rel_fields[name] = self.name
        setattr(klass, self.name, ForeignRelatedObject(self.to, self))
        setattr(klass, self.id_storage, None)
        
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
    pk_sequence = None

    def __init__(self, model_class, options=None):
        # configurable options
        options = options or {'database': database}
        for k, v in options.items():
            setattr(self, k, v)
        
        self.rel_fields = {}
        self.reverse_relations = {}
        self.fields = {}
        self.columns = {}
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
    
    def get_column_names(self):
        return self.columns.keys()
    
    def get_column(self, field_or_col):
        if field_or_col in self.fields:
            return self.fields[field_or_col].db_column
        return field_or_col
    
    def get_related_field_by_name(self, name):
        if name in self.rel_fields:
            return self.fields[self.rel_fields[name]]
    
    def get_related_field_for_model(self, model, name=None):
        for field in self.fields.values():
            if isinstance(field, ForeignKeyField) and field.to == model:
                if name is None or name == field.name or name == field.db_column:
                    return field
    
    def get_reverse_related_field_for_model(self, model, name=None):
        for field in model._meta.fields.values():
            if isinstance(field, ForeignKeyField) and field.to == self.model_class:
                if name is None or name == field.name or name == field.db_column:
                    return field
    
    def rel_exists(self, model):
        return self.get_related_field_for_model(model) or \
               self.get_reverse_related_field_for_model(model)


class BaseModel(type):
    inheritable_options = ['database', 'ordering', 'pk_sequence']
    
    def __new__(cls, name, bases, attrs):
        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)

        if not bases:
            return cls

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
                elif k == 'fields':
                    for field_name, field_obj in v.items():
                        if isinstance(field_obj, PrimaryKeyField):
                            continue
                        if field_name in cls.__dict__:
                            continue
                        field_copy = copy.deepcopy(field_obj)
                        setattr(cls, field_name, field_copy)

        _meta = BaseModelOptions(cls, attr_dict)
        
        if not hasattr(_meta, 'db_table'):
            _meta.db_table = re.sub('[^a-z]+', '_', cls.__name__.lower())

        if _meta.db_table in _meta.database.adapter.reserved_tables:
            warnings.warn('Table for %s ("%s") is reserved, please override using Meta.db_table' % (
                cls, _meta.db_table,
            ))

        setattr(cls, '_meta', _meta)

        _meta.pk_name = None

        for name, attr in cls.__dict__.items():
            if isinstance(attr, Field):
                attr.add_to_class(cls, name)
                _meta.fields[attr.name] = attr
                _meta.columns[attr.db_column] = attr
                if isinstance(attr, PrimaryKeyField):
                    _meta.pk_name = attr.name
        
        if _meta.pk_name is None:
            _meta.pk_name = 'id'
            pk = PrimaryKeyField()
            pk.add_to_class(cls, _meta.pk_name)
            _meta.fields[_meta.pk_name] = pk

        _meta.model_name = cls.__name__
        
        if _meta.pk_sequence and _meta.database.adapter.sequence_support:
            pk_field = _meta.fields[_meta.pk_name]
            pk_field.attributes['nextval'] = " default nextval('%s')" % _meta.pk_sequence

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
        self.initialize_defaults()
        
        for k, v in kwargs.items():
            setattr(self, k, v)
    
    def initialize_defaults(self):
        for field in self._meta.fields.values():
            if field.default is not None:
                if callable(field.default):
                    field_value = field.default()
                else:
                    field_value = field.default
                setattr(self, field.name, field_value)
    
    def __eq__(self, other):
        return other.__class__ == self.__class__ and \
               self.get_pk() and \
               other.get_pk() == self.get_pk()
    
    def get_field_dict(self):
        field_dict = {}
        
        for field in self._meta.fields.values():
            if isinstance(field, ForeignKeyField):
                field_dict[field.name] = getattr(self, field.id_storage)
            else:
                field_dict[field.name] = getattr(self, field.name)
        
        return field_dict
    
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
                cls._meta.database.create_foreign_key(cls, field_obj)
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
    
    def set_pk(self, pk):
        pk_field = self._meta.fields[self._meta.pk_name]
        setattr(self, self._meta.pk_name, pk_field.python_value(pk))
    
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
    
    def refresh(self, *fields):
        fields = fields or self._meta.get_field_names()
        obj = self.select(fields).get(**{self._meta.pk_name: self.get_pk()})
        
        for field_name in fields:
            setattr(self, field_name, getattr(obj, field_name))
