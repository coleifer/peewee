"""
Vector search with the sqlite-vec extension: https://github.com/asg017/sqlite-vec

The extension must be loaded by each connection:

    import sqlite_vec
    db.load_extension(sqlite_vec.loadable_path())
"""
import array
import re

from peewee import *
from peewee import Node
from peewee import NodeList
from playhouse.sqlite_ext import RowIDField
from playhouse.sqlite_ext import VirtualModel
from playhouse.sqlite_ext import VirtualTableSchemaManager
from playhouse.sqlite_ext import match


# Element type -> (array typecode, function tagging the blob for sqlite-vec).
# Float32 is the default blob interpretation and needs no tag.
VECTOR_TYPES = {
    'float': ('f', None),
    'int8': ('b', fn.vec_int8),
    'bit': (None, fn.vec_bit)}

# Peewee field type -> vec0 metadata/auxiliary column type.
VEC0_TYPES = {
    'AUTO': 'integer',
    'BIGAUTO': 'integer',
    'BIGINT': 'integer',
    'BLOB': 'blob',
    'BOOL': 'boolean',
    'CHAR': 'text',
    'DOUBLE': 'float',
    'FLOAT': 'float',
    'INT': 'integer',
    'SMALLINT': 'integer',
    'TEXT': 'text',
    'UUID': 'text',
    'VARCHAR': 'text'}

# vec0 does not parse quoted identifiers.
_identifier_re = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _pack_bits(bits):
    # sqlite-vec stores the first element in the least-significant bit.
    accum = bytearray((len(bits) + 7) // 8)
    for i, bit in enumerate(bits):
        if bit:
            accum[i >> 3] |= 1 << (i & 7)
    return bytes(accum)


def _unpack_bits(data):
    return [(byte >> i) & 1 for byte in data for i in range(8)]


class VectorField(Field):
    """
    Vector stored as a sqlite-vec blob. Python lists (or any iterable of
    numbers) are packed on write and unpacked on read. Bytes and JSON text
    pass through unchanged.

    Usable as a vec0 column or as a plain BLOB column on a regular table.
    """
    field_type = 'BLOB'

    def __init__(self, dimensions, element_type='float', distance_metric=None,
                 **kwargs):
        if element_type not in VECTOR_TYPES:
            raise ValueError('element_type must be one of: %s.' %
                             ', '.join(sorted(VECTOR_TYPES)))
        if element_type == 'bit' and dimensions % 8:
            raise ValueError('bit vector dimensions must be a multiple of 8.')
        self.dimensions = dimensions
        self.element_type = element_type
        self.distance_metric = distance_metric
        super(VectorField, self).__init__(**kwargs)

    def db_value(self, value):
        if value is None or isinstance(value, Node):
            return value
        typecode, tag = VECTOR_TYPES[self.element_type]
        if not isinstance(value, (bytes, bytearray, memoryview, str)):
            if typecode is None:
                value = _pack_bits(value)
            else:
                value = array.array(typecode, value).tobytes()
        return tag(value) if tag is not None else value

    def python_value(self, value):
        if not isinstance(value, bytes):
            return value
        typecode, _ = VECTOR_TYPES[self.element_type]
        if typecode is None:
            return _unpack_bits(value)
        return array.array(typecode, value).tolist()

    def match(self, vector):
        """KNN constraint for a vec0 query. Requires a k or LIMIT."""
        return match(self, self.to_value(vector))

    def distance(self, vector, metric=None):
        """Distance between this column and a vector or another column."""
        if metric is None:
            metric = self.distance_metric or (
                'hamming' if self.element_type == 'bit' else 'l2')
        func = getattr(fn, 'vec_distance_%s' % metric.lower())
        return func(self, self.to_value(vector), coerce=False)


class Vec0SchemaManager(VirtualTableSchemaManager):
    def _virtual_column_def(self, field):
        name = field.column_name
        if not _identifier_re.match(name):
            raise ImproperlyConfigured('vec0 column names must be plain '
                                       'identifiers, got "%s".' % name)

        if isinstance(field, VectorField):
            accum = [SQL('%s %s[%d]' % (name, field.element_type,
                                        field.dimensions))]
            if field.distance_metric:
                accum.append(SQL('distance_metric=%s' % field.distance_metric))
            return NodeList(accum)

        vec_type = VEC0_TYPES.get(field.field_type)
        if vec_type is None:
            raise ImproperlyConfigured('vec0 has no column type for %s "%s".' %
                                       (type(field).__name__, field.name))
        if field.unindexed:
            name = '+' + name  # Auxiliary column.
        accum = [SQL(name), SQL(vec_type)]
        if field.primary_key:
            accum.append(SQL('PRIMARY KEY'))
        if field.constraints:
            accum.extend(field.constraints)
        return NodeList(accum)


class VecModel(VirtualModel):
    """
    vec0 virtual table. Column roles:

    * VectorField: vector column, searchable with match().
    * IntegerField, TextField, FloatField, BooleanField: metadata column,
      usable in the WHERE clause of a KNN query.
    * constraints=[SQL('PARTITION KEY')]: partition key (integer or text).
    * unindexed=True: auxiliary column, stored but not filterable.

    The implicit rowid may be replaced with an integer or text primary key.
    """
    rowid = RowIDField()
    distance = FloatField(_hidden=True)
    k = IntegerField(_hidden=True)

    class Meta:
        extension_module = 'vec0'
        # vec0 cannot update partition keys, so only write what changed.
        only_save_dirty = True
        schema_manager_class = Vec0SchemaManager

    @classmethod
    def validate_model(cls):
        if cls._meta.fields_to_index():
            raise ImproperlyConfigured('vec0 tables do not support indexes.')
        cls._schema._virtual_columns()

    @classmethod
    def search(cls, vector, k, field=None):
        """
        Select the k nearest neighbors of vector, closest first. The vector
        field may be omitted when the model has only one.
        """
        if field is None:
            fields = [f for f in cls._meta.sorted_fields
                      if isinstance(f, VectorField)]
            if len(fields) != 1:
                raise ValueError('search() requires a field when the model '
                                 'does not have exactly one VectorField.')
            field, = fields
        return (cls
                .select()
                .where(field.match(vector), cls.k == k)
                .order_by(cls.distance))
