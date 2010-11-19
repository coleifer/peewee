#     (\
#     (  \  /(o)\     caw!
#     (   \/  ()/ /)
#      (   `;.))'".) 
#       `(/////.-'
#    =====))=))===() 
#      ///'       
#     //
#    '            
from datetime import datetime
import logging
import os
import re
import sqlite3
import time


DATABASE_NAME = os.environ.get('PEEWEE_DATABASE', 'peewee.db')
logger = logging.getLogger('peewee.logger')


class Database(object):
    def __init__(self, database):
        self.database = database
    
    def connect(self):
        self.conn = sqlite3.connect(self.database)
    
    def close(self):
        self.conn.close()
    
    def execute(self, sql, params=None, commit=False):
        cursor = self.conn.cursor()
        res = cursor.execute(sql, params or ())
        if commit:
            self.conn.commit()
        logger.debug(sql)
        return res
    
    def last_insert_id(self):
        result = self.execute("SELECT last_insert_rowid();")
        return result.fetchone()[0]
    
    def create_table(self, model_class):
        framing = "CREATE TABLE IF NOT EXISTS %s (%s);"
        columns = []

        for field in model_class._meta.fields.values():
            columns.append(field.to_sql())

        query = framing % (model_class._meta.db_table, ', '.join(columns))
        
        self.execute(query, commit=True)
    
    def drop_table(self, model_class):
        self.execute('DROP TABLE %s;' % model_class._meta.db_table, commit=True)


database = Database(DATABASE_NAME)


class QueryResultWrapper(object):
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


def asc(f):
    return (f, 'ASC')

def desc(f):
    return (f, 'DESC')

# select wrappers
def Count(f, alias='count'):
    return ('COUNT', f, alias)

def Max(f, alias='max'):
    return ('MAX', f, alias)

def Min(f, alias='min'):
    return ('MIN', f, alias)

def mark_query_dirty(func):
    def inner(self, *args, **kwargs):
        self._dirty = True
        return func(self, *args, **kwargs)
    return inner


class BaseQuery(object):
    operations = {
        'lt': '< ?',
        'lte': '<= ?',
        'gt': '> ?',
        'gte': '>= ?',
        'eq': '= ?',
        'in': 'IN (%s)', # special-case to list q-marks
        'is': 'IS ?',
        'icontains': "LIKE ? ESCAPE '\\'", # surround param with %'s
        'contains': "GLOB ?", # surround param with *'s
    }
    query_separator = '__'
    requires_commit = True
    
    def __init__(self, model):
        self.model = model
        self.query_context = model
        self._where = {}
        self._joins = []
        self._dirty = True
    
    def parse_query_args(self, **query):
        parsed = {}
        for lhs, rhs in query.iteritems():
            if self.query_separator in lhs:
                lhs, op = lhs.rsplit(self.query_separator, 1)
            else:
                op = 'eq'

            field = self.query_context._meta.get_field_by_name(lhs)
            if op == 'in':
                lookup_value = [field.lookup_value(op, o) for o in rhs]
                operation = self.operations[op] % (','.join(['?' for v in lookup_value]))
            else:
                lookup_value = field.lookup_value(op, rhs)
                operation = self.operations[op]
            
            parsed[field.name] = (operation, lookup_value)
        
        return parsed
    
    @mark_query_dirty
    def where(self, query='', **kwargs):
        self._where.setdefault(self.query_context, {})
        if query != '':
            if '__raw__' in self._where[self.query_context]:
                raise ValueError('A raw query has already been specified')
            self._where[self.query_context]['__raw__'] = query
        if kwargs:
            parsed = self.parse_query_args(**kwargs)
            self._where[self.query_context].update(**parsed)
        
        return self
    
    @mark_query_dirty
    def join(self, model, join_type=None):
        if self.query_context._meta.rel_exists(model):
            self._joins.append((model, join_type))
            self.query_context = model
        else:
            raise AttributeError('No foreign key found between %s and %s' % \
                (self.query_context.__name__, model.__name__))
        return self
    
    def use_aliases(self):
        return len(self._joins) > 0
    
    def combine_field(self, alias, field_name):
        if alias:
            return '%s.%s' % (alias, field_name)
        return field_name
    
    def compile_where(self):
        alias_count = 0
        alias_map = {}

        alias_required = self.use_aliases()

        joins = list(self._joins)
        if self._where or len(joins):
            joins.insert(0, (self.model, None))
        
        where_with_alias = []
        where_data = []
        computed_joins = []

        for i, (model, join_type) in enumerate(joins):
            if alias_required:
                alias_count += 1
                alias_map[model] = 't%d' % alias_count
            else:
                alias_map[model] = ''
            
            if model in self._where:
                for name, lookup in self._where[model].iteritems():
                    if name == '__raw__':
                        where_with_alias.append(lookup)
                    else:
                        operation, value = lookup
                        where_data.append(value)
                        combined = self.combine_field(alias_map[model], name)
                        where_with_alias.append('%s %s' % (combined, operation))
            
            if i > 0:
                from_model = joins[i-1][0]
                field = from_model._meta.get_related_field_for_model(model)
                if field:
                    left_field = field.name
                    right_field = 'id'                        
                else:
                    field = from_model._meta.get_reverse_related_field_for_model(model)
                    left_field = 'id'
                    right_field = field.name
                
                if join_type is None:
                    if field.null and model not in self._where:
                        join_type = 'LEFT OUTER'
                    else:
                        join_type = 'INNER'
                
                computed_joins.append(
                    '%s JOIN %s AS %s ON %s = %s' % (
                        join_type,
                        model._meta.db_table,
                        alias_map[model],
                        self.combine_field(alias_map[from_model], left_field),
                        self.combine_field(alias_map[model], right_field),
                    )
                )
        
        return computed_joins, where_with_alias, where_data, alias_map
    
    def raw_execute(self):
        query, params = self.sql()
        db = self.model._meta.get_database()
        result = db.execute(query, params, self.requires_commit)
        return result


class SelectQuery(BaseQuery):
    """
    Model.select('*').where(field=val).join(RelModel).where(rel_field=val)
    """
    requires_commit = False
    
    def __init__(self, model, query=None):
        """
        Allow a string or a dictionary keyed by model->fields
        
        .select('t1.*, COUNT(t2.id) AS count') or
        .select({Blog: '*', Entry: Count('id')})
        """
        self.query = query or '*'
        self._group_by = []
        self._having = []
        self._order_by = []
        self._pagination = None # return all by default
        self._distinct = False
        self._qr = None
        super(SelectQuery, self).__init__(model)
    
    @mark_query_dirty
    def paginate(self, page_num, paginate_by=20):
        self._pagination = (page_num, paginate_by)
        return self
    
    def count(self):
        tmp_pagination = self._pagination
        self._pagination = None
        
        tmp_query = self.query
        
        if self.use_aliases():
            self.query = 'COUNT(t1.id)'
        else:
            self.query = 'COUNT(id)'
        
        db = self.model._meta.get_database()
        res = db.execute(*self.sql())
        
        self.query = tmp_query
        self._pagination = tmp_pagination
        
        return res.fetchone()[0]
    
    @mark_query_dirty
    def group_by(self, clause):
        self._group_by.append((self.query_context, clause))
        return self
    
    @mark_query_dirty
    def having(self, clause):
        self._having.append(clause)
        return self
    
    @mark_query_dirty
    def distinct(self):
        self._distinct = True
        return self
    
    @mark_query_dirty
    def order_by(self, field_or_string):
        if isinstance(field_or_string, tuple):
            field_or_string, ordering = field_or_string
        else:
            ordering = 'ASC'
        
        self._order_by.append(
            (self.query_context, field_or_string, ordering)
        )
        
        return self

    def parse_select_query(self, alias_map):
        if isinstance(self.query, basestring):
            if self.query == '*' and self.use_aliases():
                return '%s.*' % alias_map[self.model]
            return self.query
        elif isinstance(self.query, dict):
            qparts = []
            for model, cols in self.query.iteritems():
                alias = alias_map.get(model, '')
                for col in cols:
                    if isinstance(col, tuple):
                        func, col, col_alias = col
                        qparts.append('%s(%s) AS %s' % \
                            (func, self.combine_field(alias, col), col_alias)
                        )
                    else:
                        qparts.append(self.combine_field(alias, col))
            return ', '.join(qparts)
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
                group_by.append(self.combine_field(alias, clause))
        else:
            group_by = list(self._group_by)

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
            for clause in where_data:
                if isinstance(clause, (tuple, list)):
                    params.extend(clause)
                else:
                    params.append(clause)
        if group_by:
            pieces.append('GROUP BY %s' % group_by)
        if having:
            pieces.append('HAVING %s' % having)
        if order_by:
            pieces.append('ORDER BY %s' % ', '.join(order_by))
        if self._pagination:
            page, paginate_by = self._pagination
            if page > 0:
                page -= 1
            pieces.append('LIMIT %d OFFSET %d' % (paginate_by, page * paginate_by))
        
        return ' '.join(pieces), params
    
    def execute(self):
        if self._dirty:
            self._qr = QueryResultWrapper(self.model, self.raw_execute())
            self._dirty = False
            return self._qr
        else:
            # call the __iter__ method directly
            return iter(self._qr)
    
    def __iter__(self):
        return self.execute()


class UpdateQuery(BaseQuery):
    """
    Model.update(field=val, field2=val2).where(some_field=some_val)
    """
    def __init__(self, model, **kwargs):
        self.update_query = kwargs
        super(UpdateQuery, self).__init__(model)
    
    def parse_update(self):
        sets = {}
        for k, v in self.update_query.iteritems():
            field = self.model._meta.get_field_by_name(k)
            sets[field.name] = field.lookup_value(None, v)
        
        return sets
    
    def sql(self):
        joins, where, where_data, alias_map = self.compile_where()
        set_statement = self.parse_update()

        params = []
        update_params = []

        for k, v in set_statement.iteritems():
            params.append(v)
            update_params.append('%s=?' % k)
        
        update = 'UPDATE %s SET %s' % (
            self.model._meta.db_table, ', '.join(update_params))
        where = ' AND '.join(where)
        
        pieces = [update]
        
        if where:
            pieces.append('WHERE %s' % where)
            params.extend(where_data)
        
        return ' '.join(pieces), params
    
    def join(self, *args, **kwargs):
        raise AttributeError('Update queries do not support JOINs in sqlite')
    
    def execute(self):
        result = self.raw_execute()
        return result.rowcount


class DeleteQuery(BaseQuery):
    """
    Model.delete().where(some_field=some_val)
    """
    def sql(self):
        joins, where, where_data, alias_map = self.compile_where()

        params = []
        
        delete = 'DELETE FROM %s' % (self.model._meta.db_table)
        where = ' AND '.join(where)
        
        pieces = [delete]
        
        if where:
            pieces.append('WHERE %s' % where)
            params.extend(where_data)
        
        return ' '.join(pieces), params
    
    def join(self, *args, **kwargs):
        raise AttributeError('Update queries do not support JOINs in sqlite')
    
    def execute(self):
        result = self.raw_execute()
        return result.rowcount


class InsertQuery(BaseQuery):
    """
    Model.insert(field=val, field2=val2)
    """
    def __init__(self, model, **kwargs):
        self.insert_query = kwargs
        super(InsertQuery, self).__init__(model)
    
    def parse_insert(self):
        cols = []
        vals = []
        for k, v in self.insert_query.iteritems():
            field = self.model._meta.get_field_by_name(k)
            cols.append(k)
            vals.append(field.lookup_value(None, v))
        
        return cols, vals
    
    def sql(self):
        cols, vals = self.parse_insert()
        
        insert = 'INSERT INTO %s (%s) VALUES (%s)' % (
            self.model._meta.db_table, ','.join(cols), ','.join('?' for v in vals))
        
        return insert, vals
    
    def where(self, *args, **kwargs):
        raise AttributeError('Insert queries do not support WHERE clauses')
    
    def join(self, *args, **kwargs):
        raise AttributeError('Insert queries do not support JOINs')
    
    def execute(self):
        result = self.raw_execute()
        return result.lastrowid


class Field(object):
    db_field = ''
    field_template = "%(db_field)s"

    def get_attributes(self):
        return {}
    
    def __init__(self, *args, **kwargs):
        self.attributes = self.get_attributes()
        if 'db_field' not in kwargs:
            kwargs['db_field'] = self.db_field
        self.attributes.update(kwargs)
    
    def add_to_class(self, klass, name):
        self.name = name
        setattr(klass, name, None)
    
    def render_field_template(self):
        return self.field_template % self.attributes
    
    def to_sql(self):
        rendered = self.render_field_template()
        return '"%s" %s' % (self.name, rendered)
    
    def db_value(self, value):
        return value
    
    def python_value(self, value):
        return value
    
    def lookup_value(self, lookup_type, value):
        return self.db_value(value)


class CharField(Field):
    db_field = 'VARCHAR'
    field_template = "%(db_field)s(%(max_length)d) NOT NULL"
    
    def get_attributes(self):
        return {'max_length': 255}
    
    def db_value(self, value):
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
    db_field = 'TEXT'
    
    def db_value(self, value):
        return value or ''
    
    def lookup_value(self, lookup_type, value):
        if lookup_type == 'contains':
            return '*%s*' % self.db_value(value)
        elif lookup_type == 'icontains':
            return '%%%s%%' % self.db_value(value)
        else:
            return self.db_value(value)


class DateTimeField(Field):
    db_field = 'DATETIME'
    field_template = "%(db_field)s"
    
    def python_value(self, value):
        if value is not None:
            return datetime(*time.strptime(value, '%Y-%m-%d %H:%M:%S')[:6])
    
    def db_value(self, value):
        return value or None


class IntegerField(Field):
    db_field = 'INTEGER'
    field_template = "%(db_field)s NOT NULL"
    
    def db_value(self, value):
        return value or 0
    
    def python_value(self, value):
        return int(value or 0)


class FloatField(Field):
    db_field = 'REAL'
    field_template = "%(db_field)s NOT NULL"
    
    def db_value(self, value):
        return value or 0.0
    
    def python_value(self, value):
        return float(value or 0)


class PrimaryKeyField(IntegerField):
    field_template = "%(db_field)s NOT NULL PRIMARY KEY"


class ForeignRelatedObject(object):    
    def __init__(self, to, name):
        self.field_name = name
        self.to = to
        self.cache_name = '_cache_%s' % name
    
    def __get__(self, instance, instance_type=None):
        if not getattr(instance, self.cache_name, None):
            id = getattr(instance, self.field_name, 0)
            qr = self.to.select().where(id=id).execute()
            setattr(instance, self.cache_name, qr.next())
        return getattr(instance, self.cache_name)
    
    def __set__(self, instance, obj):
        assert isinstance(obj, self.to), "Cannot assign %s, invalid type" % obj
        setattr(instance, self.field_name, obj.id)
        setattr(instance, self.cache_name, obj)


class ReverseForeignRelatedObject(object):
    def __init__(self, related_model, name):
        self.field_name = name
        self.related_model = related_model
    
    def __get__(self, instance, instance_type=None):
        query = {self.field_name: instance.id}
        qr = self.related_model.select().where(**query)
        return qr


class ForeignKeyField(IntegerField):
    field_template = '%(db_field)s %(nullable)s REFERENCES "%(to_table)s" ("id")'
    
    def __init__(self, to, null=False, *args, **kwargs):
        self.to = to
        self.null = null
        kwargs['to_table'] = to._meta.db_table
        if null:
            kwargs['nullable'] = ''
        else:
            kwargs['nullable'] = 'NOT NULL'
        super(ForeignKeyField, self).__init__(*args, **kwargs)
    
    def add_to_class(self, klass, name):
        self.descriptor = name
        self.name = name + '_id'
        self.related_name = klass._meta.db_table + '_set'
        setattr(klass, self.descriptor, ForeignRelatedObject(self.to, self.name))
        setattr(klass, self.name, None)
        
        reverse_rel = ReverseForeignRelatedObject(klass, self.name)
        setattr(self.to, self.related_name, reverse_rel)
    
    def lookup_value(self, lookup_type, value):
        if isinstance(value, Model):
            return value.id
        return value or None


class BaseModel(type):
    def __new__(cls, name, bases, attrs):
        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)

        class Meta(object):
            fields = {}
            
            def __init__(self, model_class):
                self.model_class = model_class

            def get_database(self):
                return self.model_class.database
            
            def get_field_by_name(self, name):
                if name in self.fields:
                    return self.fields[name]
                raise AttributeError('Field named %s not found' % name)
            
            def get_related_field_for_model(self, model):
                for field in self.fields.values():
                    if isinstance(field, ForeignKeyField) and field.to == model:
                        return field
            
            def get_reverse_related_field_for_model(self, model):
                for field in model._meta.fields.values():
                    if isinstance(field, ForeignKeyField) and field.to == self.model_class:
                        return field
            
            def rel_exists(self, model):
                return self.get_related_field_for_model(model) or \
                       self.get_reverse_related_field_for_model(model)
            
        
        _meta = Meta(cls)
        setattr(cls, '_meta', _meta)
        
        _meta.db_table = re.sub('[^a-z]+', '_', cls.__name__.lower())
        
        has_primary_key = False

        for name, attr in cls.__dict__.items():
            if isinstance(attr, Field):
                attr.add_to_class(cls, name)
                _meta.fields[attr.name] = attr
                if isinstance(attr, PrimaryKeyField):
                    has_primary_key = True
        
        if not has_primary_key:
            pk = PrimaryKeyField()
            pk.add_to_class(cls, 'id')
            _meta.fields['id'] = pk
                
        if hasattr(cls, '__unicode__'):
            setattr(cls, '__repr__', lambda self: '<%s: %s>' % (
                self.__class__.__name__, self.__unicode__()))
        
        return cls


class Model(object):
    __metaclass__ = BaseModel
    database = database
    
    def __init__(self, *args, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    
    def __eq__(self, other):
        return other.__class__ == self.__class__ and self.id and other.id == self.id
    
    def get_field_dict(self):
        field_val = lambda f: (f.name, getattr(self, f.name))
        pairs = map(field_val, self._meta.fields.values())
        return dict(pairs)
    
    @classmethod
    def create_table(cls):
        cls.database.create_table(cls)
    
    @classmethod
    def drop_table(cls):
        cls.database.drop_table(cls)
    
    @classmethod
    def select(cls, query=None):
        return SelectQuery(cls, query)
    
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
    def get(cls, **query):
        return cls.select().where(**query).paginate(1, 1).execute().next()
    
    def save(self):
        field_dict = self.get_field_dict()
        field_dict.pop('id')
        if self.id:
            update = self.update(**field_dict).where(id=self.id)
            update.execute()
        else:
            insert = self.insert(**field_dict)
            self.id = insert.execute()
