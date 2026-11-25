"""
Vector search with the pgvector extension: https://github.com/pgvector/pgvector

The extension must be created in the database:

    db.execute_sql('CREATE EXTENSION IF NOT EXISTS vector')
"""
from peewee import *
from peewee import Expression
from peewee import Node
from peewee import WrappedNode


# Distance metric -> operator. Smaller number for a nearer vector, so "ip" is
# the negative inner product.
METRICS = {
    'l2': '<->',
    'ip': '<#>',
    'cosine': '<=>',
    'l1': '<+>',
    'hamming': '<~>',
    'jaccard': '<%%>'}


def _dump_list(value, dimensions):
    return '[%s]' % ','.join(str(float(item)) for item in value)


def _load_list(value):
    return [float(item) for item in value[1:-1].split(',')]


def _dump_bits(value, dimensions):
    return ''.join('1' if bit else '0' for bit in value)


def _load_bits(value):
    return [int(bit) for bit in value]


def _dump_sparse(value, dimensions):
    if not isinstance(value, dict):
        value = {i: item for i, item in enumerate(value) if item}
    # sparsevec numbers its elements from 1.
    items = ','.join('%d:%s' % (i + 1, float(item))
                     for i, item in sorted(value.items()))
    return '{%s}/%d' % (items, dimensions)


def _load_sparse(value):
    items = value[1:value.index('}')]
    return {int(i) - 1: float(v) for i, v in
            (item.split(':') for item in items.split(',') if item)}


# Element type -> (column type, parameter type, serializer, parser).
# Bit parameters are sent as varbit. A cast to bit(n) pads or truncates a
# string of the wrong length, where varbit lets the server reject it.
VECTOR_TYPES = {
    'float': ('vector', 'vector', _dump_list, _load_list),
    'half': ('halfvec', 'halfvec', _dump_list, _load_list),
    'bit': ('bit', 'varbit', _dump_bits, _load_bits),
    'sparse': ('sparsevec', 'sparsevec', _dump_sparse, _load_sparse)}


class _OperatorClass(WrappedNode):
    # Index column with its operator class, e.g. "embedding" vector_l2_ops.
    def __init__(self, node, name):
        super(_OperatorClass, self).__init__(node)
        self.name = name

    def __sql__(self, ctx):
        return ctx.sql(self.node).literal(' %s' % self.name)


class VectorField(Field):
    """
    Vector stored in a pgvector column. Python lists (or any iterable of
    numbers) are serialized on write and parsed on read. Sparse vectors are
    read as dicts of index to value. Strings in pgvector's text format pass
    through unchanged.

    index=True declares an approximate index for the field's metric.
    """
    default_index_type = 'hnsw'

    def __init__(self, dimensions, element_type='float', distance_metric=None,
                 index_options=None, **kwargs):
        if element_type not in VECTOR_TYPES:
            raise ValueError('element_type must be one of: %s.' %
                             ', '.join(sorted(VECTOR_TYPES)))
        self.dimensions = dimensions
        self.element_type = element_type
        self.distance_metric = distance_metric
        self.index_options = index_options
        self.field_type = VECTOR_TYPES[element_type][0].upper()
        super(VectorField, self).__init__(**kwargs)

    def get_modifiers(self):
        return [self.dimensions]

    def db_value(self, value):
        if value is None or isinstance(value, Node):
            return value
        if isinstance(value, (bytes, bytearray, memoryview)):
            # Iterating bytes yields one number per byte, which would be
            # stored silently as the wrong vector.
            raise TypeError('VectorField does not accept bytes. Use a list '
                            'of numbers or pgvector\'s text format.')
        _, param_type, dump, _ = VECTOR_TYPES[self.element_type]
        if not isinstance(value, str):
            value = dump(value, self.dimensions)
        # Without the cast a parameter is text, which Postgres will not
        # coerce to a vector inside an expression such as CASE.
        return Value(value).cast(param_type)

    def python_value(self, value):
        if not isinstance(value, str):
            return value
        _, _, _, load = VECTOR_TYPES[self.element_type]
        return load(value)

    def _e(name, many=False):
        # Without to_value() a list operand is expanded into one parameter
        # per element. IN takes a list of vectors, or a subquery.
        def inner(self, rhs):
            if many:
                if not isinstance(rhs, Node):
                    rhs = [self.to_value(item) for item in rhs]
            elif rhs is not None:
                rhs = self.to_value(rhs)
            return getattr(Field, name)(self, rhs)
        return inner
    __eq__ = _e('__eq__')
    __ne__ = _e('__ne__')
    __lshift__ = in_ = _e('in_', True)
    not_in = _e('not_in', True)
    __hash__ = Field.__hash__

    def _metric(self, metric=None):
        return metric or self.distance_metric or (
            'hamming' if self.element_type == 'bit' else 'l2')

    def distance(self, vector, metric=None):
        """Distance between this column and a vector, column or subquery."""
        return Expression(self, METRICS[self._metric(metric)],
                          self.to_value(vector))

    def get_index(self):
        # pgvector has no default operator class. An index serves the one
        # metric named by its operator class, e.g. vector_cosine_ops.
        column_type, _, _, _ = VECTOR_TYPES[self.element_type]
        opclass = '%s_%s_ops' % (column_type, self._metric())
        return ModelIndex(self.model, (_OperatorClass(self, opclass),),
                          unique=self.unique, using=self.index_type,
                          options=self.index_options)
