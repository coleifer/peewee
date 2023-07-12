import json

try:
    import bz2
except ImportError:
    bz2 = None
try:
    import zlib
except ImportError:
    zlib = None
try:
    import cPickle as pickle
except ImportError:
    import pickle

from peewee import BlobField, TextField, Function
from peewee import buffer_type


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

        self.algorithm = algorithm
        self.compress = compress_module.compress
        self.decompress = compress_module.decompress
        super(CompressedField, self).__init__(*args, **kwargs)

    def python_value(self, value):
        if value is not None:
            return self.decompress(value)

    def db_value(self, value):
        if value is not None:
            return self._constructor(
                self.compress(value, self.compression_level))


class PickleField(BlobField):
    def python_value(self, value):
        if value is not None:
            if isinstance(value, buffer_type):
                value = bytes(value)
            return pickle.loads(value)

    def db_value(self, value):
        if value is not None:
            pickled = pickle.dumps(value, pickle.HIGHEST_PROTOCOL)
            return self._constructor(pickled)


class JSONField(TextField):
    field_type = 'JSON'

    # noinspection PyProtectedMember
    def db_value(self, value):
        ensure_ascii = getattr(self.model._meta.database, 'json_ensure_ascii', True)
        indent = 2 if getattr(self.model._meta.database, 'json_use_detailed', False) else None

        if value is not None:
            return json.dumps(value, ensure_ascii=ensure_ascii, indent=indent)

    def python_value(self, value):
        if value is not None:
            return json.loads(value)

    def jextract(self, jpath: str) -> Function:
        # jpath example: '$.key1.key2'
        return fn.JSON_EXTRACT(self, jpath)
