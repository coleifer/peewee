try:
    import cPickle as pickle
except ImportError:
    import pickle
import re
import sys

PY2 = sys.version_info[0] == 2

# Conditional standard library imports.
try:
    from cStringIO import StringIO
except ImportError:
    if sys.version_info[0] == 2:
        from StringIO import StringIO
    else:
        from io import StringIO

try:
    import bz2
except ImportError:
    bz2 = None

try:
    import zlib
except ImportError:
    zlib = None

try:
    from Crypto.Cipher import AES
    from Crypto import Random
except ImportError:
    AES = Random = None

try:
    from bcrypt import hashpw, gensalt
except ImportError:
    hashpw = gensalt = None

from peewee import *
from peewee import binary_construct
from peewee import Field
from peewee import FieldDescriptor
from peewee import SelectQuery
from peewee import unicode_type

if hashpw and gensalt:
    class PasswordHash(bytes):
        def check_password(self, password):
            password = password.encode('utf-8')
            return hashpw(password, self) == self


    class PasswordField(BlobField):
        def __init__(self, iterations=12, *args, **kwargs):
            if None in (hashpw, gensalt):
                raise ValueError('Missing library required for PasswordField: bcrypt')
            self.bcrypt_iterations = iterations
            self.raw_password = None
            super(PasswordField, self).__init__(*args, **kwargs)

        def db_value(self, value):
            """Convert the python value for storage in the database."""
            if isinstance(value, PasswordHash):
                return bytes(value)

            if isinstance(value, unicode_type):
                value = value.encode('utf-8')
            salt = gensalt(self.bcrypt_iterations)
            return value if value is None else hashpw(value, salt)

        def python_value(self, value):
            """Convert the database value to a pythonic value."""
            if isinstance(value, unicode_type):
                value = value.encode('utf-8')

            return PasswordHash(value)

class DeferredThroughModel(object):
    def set_field(self, model_class, field, name):
        self.model_class = model_class
        self.field = field
        self.name = name

    def set_model(self, through_model):
        self.field._through_model = through_model
        self.field.add_to_class(self.model_class, self.name)

class ManyToManyField(Field):
    def __init__(self, rel_model, related_name=None, through_model=None,
                 _is_backref=False):
        if through_model is not None and not (
                isinstance(through_model, (Proxy, DeferredThroughModel)) or
                issubclass(through_model, Model)):
            raise TypeError('Unexpected value for `through_model`.  Expected '
                            '`Model`, `Proxy` or `DeferredThroughModel`.')
        self.rel_model = rel_model
        self._related_name = related_name
        self._through_model = through_model
        self._is_backref = _is_backref
        self.primary_key = False
        self.verbose_name = None

    def _get_descriptor(self):
        return ManyToManyFieldDescriptor(self)

    def add_to_class(self, model_class, name):
        if isinstance(self._through_model, Proxy):
            def callback(through_model):
                self._through_model = through_model
                self.add_to_class(model_class, name)
            self._through_model.attach_callback(callback)
            return
        elif isinstance(self._through_model, DeferredThroughModel):
            self._through_model.set_field(model_class, self, name)
            return

        self.name = name
        self.model_class = model_class
        if not self.verbose_name:
            self.verbose_name = re.sub('_+', ' ', name).title()
        setattr(model_class, name, self._get_descriptor())

        if not self._is_backref:
            backref = ManyToManyField(
                self.model_class,
                through_model=self._through_model,
                _is_backref=True)
            related_name = self._related_name or model_class._meta.name + 's'
            backref.add_to_class(self.rel_model, related_name)

    def get_models(self):
        return [model for _, model in sorted((
            (self._is_backref, self.model_class),
            (not self._is_backref, self.rel_model)))]

    def get_through_model(self):
        if not self._through_model:
            lhs, rhs = self.get_models()
            tables = [model._meta.db_table for model in (lhs, rhs)]

            class Meta:
                database = self.model_class._meta.database
                db_table = '%s_%s_through' % tuple(tables)
                indexes = (
                    ((lhs._meta.name, rhs._meta.name),
                     True),)
                validate_backrefs = False

            attrs = {
                lhs._meta.name: ForeignKeyField(rel_model=lhs),
                rhs._meta.name: ForeignKeyField(rel_model=rhs)}
            attrs['Meta'] = Meta

            self._through_model = type(
                '%s%sThrough' % (lhs.__name__, rhs.__name__),
                (Model,),
                attrs)

        return self._through_model


class ManyToManyFieldDescriptor(FieldDescriptor):
    def __init__(self, field):
        super(ManyToManyFieldDescriptor, self).__init__(field)
        self.model_class = field.model_class
        self.rel_model = field.rel_model
        self.through_model = field.get_through_model()
        self.src_fk = self.through_model._meta.rel_for_model(self.model_class)
        self.dest_fk = self.through_model._meta.rel_for_model(self.rel_model)

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return (ManyToManyQuery(instance, self, self.rel_model)
                    .select()
                    .join(self.through_model)
                    .join(self.model_class)
                    .where(self.src_fk == instance))
        return self.field

    def __set__(self, instance, value):
        query = self.__get__(instance)
        query.add(value, clear_existing=True)


class ManyToManyQuery(SelectQuery):
    def __init__(self, instance, field_descriptor, *args, **kwargs):
        self._instance = instance
        self._field_descriptor = field_descriptor
        super(ManyToManyQuery, self).__init__(*args, **kwargs)

    def clone(self):
        query = type(self)(
            self._instance,
            self._field_descriptor,
            self.model_class)
        query.database = self.database
        return self._clone_attributes(query)

    def _id_list(self, model_or_id_list):
        if isinstance(model_or_id_list[0], Model):
            return [obj.get_id() for obj in model_or_id_list]
        return model_or_id_list

    def add(self, value, clear_existing=False):
        if clear_existing:
            self.clear()

        fd = self._field_descriptor
        if isinstance(value, SelectQuery):
            query = value.select(
                SQL(str(self._instance.get_id())),
                fd.rel_model._meta.primary_key)
            fd.through_model.insert_from(
                fields=[fd.src_fk, fd.dest_fk],
                query=query).execute()
        else:
            if not isinstance(value, (list, tuple)):
                value = [value]
            if not value:
                return
            inserts = [{
                fd.src_fk.name: self._instance.get_id(),
                fd.dest_fk.name: rel_id}
                for rel_id in self._id_list(value)]
            fd.through_model.insert_many(inserts).execute()

    def remove(self, value):
        fd = self._field_descriptor
        if isinstance(value, SelectQuery):
            subquery = value.select(value.model_class._meta.primary_key)
            return (fd.through_model
                    .delete()
                    .where(
                        (fd.dest_fk << subquery) &
                        (fd.src_fk == self._instance.get_id()))
                    .execute())
        else:
            if not isinstance(value, (list, tuple)):
                value = [value]
            if not value:
                return
            return (fd.through_model
                    .delete()
                    .where(
                        (fd.dest_fk << self._id_list(value)) &
                        (fd.src_fk == self._instance.get_id()))
                    .execute())

    def clear(self):
        return (self._field_descriptor.through_model
                .delete()
                .where(self._field_descriptor.src_fk == self._instance)
                .execute())


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

    if PY2:
        def db_value(self, value):
            if value is not None:
                return binary_construct(
                    self.compress(value, self.compression_level))

        def python_value(self, value):
            if value is not None:
                return self.decompress(value)
    else:
        def db_value(self, value):
            if value is not None:
                return self.compress(
                    binary_construct(value), self.compression_level)

        def python_value(self, value):
            if value is not None:
                return self.decompress(value).decode('utf-8')


class PickledField(BlobField):
    def db_value(self, value):
        if value is not None:
            return pickle.dumps(value)

    def python_value(self, value):
        if value is not None:
            if isinstance(value, unicode_type):
                value = value.encode('raw_unicode_escape')
            return pickle.loads(value)


if AES and Random:
    class AESEncryptedField(BlobField):
        def __init__(self, key, *args, **kwargs):
            self.key = key
            super(AESEncryptedField, self).__init__(*args, **kwargs)

        def get_cipher(self, key, iv):
            if len(key) > 32:
                raise ValueError('Key length cannot exceed 32 bytes.')
            key = key + ' ' * (32 - len(key))
            return AES.new(key, AES.MODE_CFB, iv)

        def encrypt(self, value):
            iv = Random.get_random_bytes(AES.block_size)
            cipher = self.get_cipher(self.key, iv)
            return iv + cipher.encrypt(value)

        def decrypt(self, value):
            iv = value[:AES.block_size]
            cipher = self.get_cipher(self.key, iv)
            return cipher.decrypt(value[AES.block_size:])

        if PY2:
            def db_value(self, value):
                if value is not None:
                    return binary_construct(self.encrypt(value))

            def python_value(self, value):
                if value is not None:
                    return self.decrypt(value)
        else:
            def db_value(self, value):
                if value is not None:
                    return self.encrypt(value)

            def python_value(self, value):
                if value is not None:
                    return self.decrypt(value)
