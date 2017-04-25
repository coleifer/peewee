import sys

from peewee import *
from peewee import sqlite3


if sys.version_info[0] == 3:
    basestring = str


FTS3_MATCHINFO = 'pcx'
FTS4_MATCHINFO = 'pcnalx'
FTS_VERSION = 4 if sqlite3.sqlite_version_info[:3] >= (3, 7, 4) else 3


class RowIDField(VirtualField):
    column_name = name = required_name = 'rowid'
    field_class = IntegerField
    primary_key = True

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
        return NodeList(node_list, SQL('AUTOINCREMENT'))


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
        ctx.sql(self.model).literal(' USING %s ' % self.model._meta.extension)

        arguments = []
        meta = self.model._meta

        # Constraints, data-types, foreign and primary keys are all omitted.
        for field in meta.sorted_fields:
            field_def = [Entity(field.column_name)]
            if field.unindexed:
                field_def.append(SQL('UNINDEXED'))
            arguments.append(NodeList(field_def))

        arguments.extend(self._create_table_option_sql(options))
        return ctx.sql(EnclosedNodeList(arguments))

    def _create_table(self, safe=True, **options):
        if isinstance(self.model, VirtualModel):
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
        extension_options = None
        primary_key = False
        schema_manager_class = VirtualTableSchemaManager
        virtual_table = True

    @classmethod
    def clean_options(cls, options):
        return options
