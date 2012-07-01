from peewee import *
from peewee import PostgresqlAdapter, Database, Column, Field

from psycopg2 import extensions
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

class lindex(R):
    def sql_select(self, model_class):
        tmpl = 'index(%s, %%s) AS %s'
        col, alias = self.params[0], self.params[-1]
        return tmpl, col, alias, self.params[1]

class lsubtree(R):
    def sql_select(self, model_class):
        tmpl = 'subltree(%s, %%s, %%s) AS %s'
        col, alias = self.params[0], self.params[-1]
        return tmpl, col, alias, self.params[1], self.params[2]

class lsubpath(R):
    def sql_select(self, model_class):
        tmpl = 'subpath(%%s, %s) AS %%s'
        col, alias = self.params[0], self.params[-1]
        if len(self.params) == 4:
            tmpl = tmpl % '%%s, %%s'
            return tmpl, col, alias, self.params[1], self.params[2]
        else:
            tmpl = tmpl % '%%s'
            return tmpl, col, alias, self.params[1]

class nlevel(R):
    def sql_select(self, model_class):
        return 'nlevel', self.params[0], self.params[1]


def _get_ltree_oids(conn):
    curs = conn.cursor()
    rv0, rv1 = [], []

    typarray = conn.server_version >= 80300 and "typarray" or "NULL"

    # get the oid for the hstore
    curs.execute("""
        SELECT t.oid, %s
        FROM pg_type t JOIN pg_namespace ns
        ON typnamespace = ns.oid
        WHERE typname = 'ltree';
    """ % typarray)

    for oids in curs:
        rv0.append(oids[0])
        rv1.append(oids[1])

    return tuple(rv0), tuple(rv1)

def _cast_fn(val, curs):
    return val

def register_ltree(conn):
    oid = _get_ltree_oids(conn)
    if not oid[0]:
        return False
    else:
        array_oid = oid[1]
        oid = oid[0]

    if isinstance(oid, int):
        oid = (oid,)

    if array_oid is not None:
        if isinstance(array_oid, int):
            array_oid = (array_oid,)
        else:
            array_oid = tuple([x for x in array_oid if x])

    ltree = extensions.new_type(oid, "LTREE", _cast_fn)
    extensions.register_type(ltree, None)

    if array_oid:
        ltree_array = extensions.new_array_type(array_oid, "LTREEARRAY", ltree)
        extensions.register_type(ltree_array, None)

    return True


class PostgresqlExtAdapter(PostgresqlAdapter):
    def __init__(self, *args, **kwargs):
        super(PostgresqlExtAdapter, self).__init__(*args, **kwargs)
        self.operations.update(self.get_operations_overrides())

    def get_operations_overrides(self):
        return {
            'hcontains_dict': '@> (%s)',
            'hcontains_keys': '?& (%s)',
            'hcontains_key': '? %s',
            'lparents': '@> %s',
            'lchildren': '<@ %s',
            'lmatch': '~ %s',
            'lmatch_text': '@ %s',
        }

    def connect(self, database, **kwargs):
        conn = super(PostgresqlExtAdapter, self).connect(database, **kwargs)
        register_hstore(conn, globally=True)
        self._ltree_support = register_ltree(conn)
        return conn

    def get_field_overrides(self):
        overrides = super(PostgresqlExtAdapter, self).get_field_overrides()
        overrides.update({'hash': 'hstore', 'tree': 'ltree'})
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
        elif isinstance(field, LTreeField):
            if op == 'contains':
                return 'lmatch'
            elif op == 'startswith':
                return 'lchildren'
        return op

    def lookup_cast(self, field, op, value):
        if op == 'hcontains_keys':
            return [value]
        return super(PostgresqlExtAdapter, self).lookup_cast(field, op, value)


class PostgresqlExtDatabase(PostgresqlDatabase):
    def __init__(self, database, **connect_kwargs):
        Database.__init__(self, PostgresqlExtAdapter(), database, **connect_kwargs)

    def create_index(self, model_class, field_name, unique=False):
        field_obj = model_class._meta.fields[field_name]
        if isinstance(field_obj, (HStoreField, LTreeField)):
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


class LTreeColumn(Column):
    db_field = 'tree'


class LTreeField(Field):
    column_class = LTreeColumn

    def __init__(self, *args, **kwargs):
        super(LTreeField, self).__init__(*args, **kwargs)
        self.db_index = True
