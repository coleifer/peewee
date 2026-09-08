import pickle
try:
    import bz2
except ImportError:
    bz2 = None
try:
    import zlib
except ImportError:
    zlib = None

from peewee import BlobField
from peewee import CharField
from peewee import IntegerField


class CompressedField(BlobField):
    ZLIB = 'zlib'
    BZ2 = 'bz2'
    algorithm_to_import = {
        ZLIB: zlib,
        BZ2: bz2,
    }

    def __init__(self, compression_level=6, algorithm=ZLIB, *args,
                 **kwargs):
        self.compression_level = compression_level
        if algorithm not in self.algorithm_to_import:
            raise ValueError('Unrecognized algorithm %s' % algorithm)
        compress_module = self.algorithm_to_import[algorithm]
        if compress_module is None:
            raise ValueError('Missing library required for %s.' % algorithm)

        self.compress = compress_module.compress
        self.decompress = compress_module.decompress
        super(CompressedField, self).__init__(*args, **kwargs)

    def python_value(self, value):
        if value is not None:
            return self.decompress(value)

    def db_value(self, value):
        if value is not None:
            if isinstance(value, str):
                value = value.encode('utf8')
            return self._constructor(
                self.compress(value, self.compression_level))


class PickleField(BlobField):
    def python_value(self, value):
        if value is not None:
            return pickle.loads(value)

    def db_value(self, value):
        if value is not None:
            pickled = pickle.dumps(value, pickle.HIGHEST_PROTOCOL)
            return self._constructor(pickled)


class EnumFieldMixin(object):
    enum_value_type = None

    def __init__(self, enum_class, *args, **kwargs):
        # Mismatched member values fail late and backend-dependently.
        if self.enum_value_type is not None:
            for member in enum_class:
                if not isinstance(member.value, self.enum_value_type):
                    raise ValueError('%s.%s value %r is not %s' % (
                        enum_class.__name__, member.name, member.value,
                        self.enum_value_type.__name__))
        self.enum_class = enum_class
        kwargs.setdefault('choices', [(m.value, m.name) for m in enum_class])
        super(EnumFieldMixin, self).__init__(*args, **kwargs)

    def db_value(self, value):
        if value is None:
            return value
        value = self.enum_class(value).value
        return super(EnumFieldMixin, self).db_value(value)

    def python_value(self, value):
        if value is None:
            return value
        return self.enum_class(super(EnumFieldMixin, self).python_value(value))


class EnumField(EnumFieldMixin, CharField):
    enum_value_type = str

class IntEnumField(EnumFieldMixin, IntegerField):
    enum_value_type = int
