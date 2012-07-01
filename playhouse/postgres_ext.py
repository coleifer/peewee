from peewee import *
from peewee import PostgresqlAdapter, Database, Column, Field

from psycopg2.extras import register_hstore


class hstore_fn(R):
    op = ''

    def sql_select(self, model_class):
        return '%s(%s)' % (self.op, self.params[0]), self.params[1]

    def sql_where(self):
        raise NotImplementedError

class hkeys(hstore_fn):
    op = 'akeys'

class hvalues(hstore_fn):
    op = 'avals'

class hmatrix(hstore_fn):
    op = 'hstore_to_matrix'

class hstore_fn_params(R):
    op = ''
    select_template = '%s(%%s, %s) AS %%s'
    where_template = '%s(%s, %%s)'

    def sql_select(self, model_class):
        tmpl = self.select_template % (self.op, '%%s')
        return tmpl, self.params[0], self.params[1], self.params[2]

    def sql_where(self):
        tmpl = self.where_template % (self.op, self.params[0])
        return tmpl, self.params[1]

class hslice(hstore_fn_params):
    op = 'slice'

class hexist(hstore_fn_params):
    op = 'exist'

class hdefined(hstore_fn_params):
    op = 'defined'

class hstore_update_only(R):
    def sql_select(self, model_class):
        raise NotImplementedError

    def sql_where(self):
        raise NotImplementedError

class hupdate(hstore_update_only):
    def sql_update(self):
        return ('%s || %%s' % self.params[0]), self.params[1]

class hdelete(hstore_update_only):
    def sql_update(self):
        return ('delete(%s, %%s)' % self.params[0]), self.params[1]


class PostgresqlExtAdapter(PostgresqlAdapter):
    def __init__(self, *args, **kwargs):
        super(PostgresqlExtAdapter, self).__init__(*args, **kwargs)
        self.operations.update(self.get_operations_overrides())

    def get_operations_overrides(self):
        return {
            'hcontains_dict': '@> (%s)',
            'hcontains_keys': '?& (%s)',
            'hcontains_key': '? %s'
        }

    def connect(self, database, **kwargs):
        conn = super(PostgresqlExtAdapter, self).connect(database, **kwargs)
        register_hstore(conn, globally=True)
        return conn

    def get_field_overrides(self):
        overrides = super(PostgresqlExtAdapter, self).get_field_overrides()
        overrides.update({'hash': 'hstore'})
        return overrides

    def op_override(self, field, op, value):
        if isinstance(field, HStoreField):
            if op == 'contains':
                if isinstance(value, dict):
                    return 'hcontains_dict'
                elif isinstance(value, (list, tuple)):
                    return 'hcontains_keys'
                elif isinstance(value, basestring):
                    return 'hcontains_key'
        return op


class PostgresqlExtDatabase(PostgresqlDatabase):
    def __init__(self, database, **connect_kwargs):
        Database.__init__(self, PostgresqlExtAdapter(), database, **connect_kwargs)

    def create_index(self, model_class, field_name, unique=False):
        field_obj = model_class._meta.fields[field_name]
        if isinstance(field_obj, HStoreField):
            framing = 'CREATE INDEX %(index)s ON %(table)s USING GIST (%(field)s);'
        else:
            framing = None
        self.execute(self.create_index_query(model_class, field_name, unique, framing))


class HStoreColumn(Column):
    db_field = 'hash'


class HStoreField(Field):
    column_class = HStoreColumn

    def __init__(self, *args, **kwargs):
        super(HStoreField, self).__init__(*args, **kwargs)
        self.db_index = True

    def python_value(self, v):
        return v or {}

    def keys(self, alias='keys'):
        return hkeys(self.name, alias)

    def values(self, alias='values'):
        return hvalues(self.name, alias)
