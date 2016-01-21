"""
Provide a "Generic ForeignKey", similar to Django.  A "GFK" is composed of two
columns: an object ID and an object type identifier.  The object types are
collected in a global registry (all_models), so all you need to do is subclass
``gfk.Model`` and your model will be added to the registry.

Example:

class Tag(Model):
    tag = CharField()
    object_type = CharField(null=True)
    object_id = IntegerField(null=True)
    object = GFKField('object_type', 'object_id')

class Blog(Model):
    tags = ReverseGFK(Tag, 'object_type', 'object_id')

class Photo(Model):
    tags = ReverseGFK(Tag, 'object_type', 'object_id')

tag.object -> a blog or photo
blog.tags -> select query of tags for ``blog`` instance
Blog.tags -> select query of all tags for Blog instances
"""

from peewee import *
from peewee import BaseModel as _BaseModel
from peewee import Model as _Model
from peewee import SelectQuery
from peewee import UpdateQuery
from peewee import with_metaclass


all_models = set()
table_cache = {}


class BaseModel(_BaseModel):
    def __new__(cls, name, bases, attrs):
        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)
        all_models.add(cls)
        return cls

class Model(with_metaclass(BaseModel, _Model)):
    pass

def get_model(tbl_name):
    if tbl_name not in table_cache:
        for model in all_models:
            if model._meta.db_table == tbl_name:
                table_cache[tbl_name] = model
                break
    return table_cache.get(tbl_name)

class BoundGFKField(object):
    __slots__ = ('model_class', 'gfk_field')

    def __init__(self, model_class, gfk_field):
        self.model_class = model_class
        self.gfk_field = gfk_field

    @property
    def unique(self):
        indexes = self.model_class._meta.indexes
        fields = set((self.gfk_field.model_type_field,
                      self.gfk_field.model_id_field))
        for (indexed_columns, is_unique) in indexes:
            if not fields - set(indexed_columns):
                return True
        return False

    @property
    def primary_key(self):
        pk = self.model_class._meta.primary_key
        if isinstance(pk, CompositeKey):
            fields = set((self.gfk_field.model_type_field,
                          self.gfk_field.model_id_field))
            if not fields - set(pk.field_names):
                return True
        return False

    def __eq__(self, other):
        meta = self.model_class._meta
        type_field = meta.fields[self.gfk_field.model_type_field]
        id_field = meta.fields[self.gfk_field.model_id_field]
        return (
            (type_field == other._meta.db_table) &
            (id_field == other._get_pk_value()))

    def __ne__(self, other):
        other_cls = type(other)
        type_field = other._meta.fields[self.gfk_field.model_type_field]
        id_field = other._meta.fields[self.gfk_field.model_id_field]
        return (
            (type_field == other._meta.db_table) &
            (id_field != other._get_pk_value()))


class GFKField(object):
    def __init__(self, model_type_field='object_type',
                 model_id_field='object_id'):
        self.model_type_field = model_type_field
        self.model_id_field = model_id_field
        self.att_name = '.'.join((self.model_type_field, self.model_id_field))

    def get_obj(self, instance):
        data = instance._data
        if data.get(self.model_type_field) and data.get(self.model_id_field):
            tbl_name = data[self.model_type_field]
            model_class = get_model(tbl_name)
            if not model_class:
                raise AttributeError('Model for table "%s" not found in GFK '
                                     'lookup.' % tbl_name)
            query = model_class.select().where(
                model_class._meta.primary_key == data[self.model_id_field])
            return query.get()

    def __get__(self, instance, instance_type=None):
        if instance:
            if self.att_name not in instance._obj_cache:
                rel_obj = self.get_obj(instance)
                if rel_obj:
                    instance._obj_cache[self.att_name] = rel_obj
            return instance._obj_cache.get(self.att_name)
        return BoundGFKField(instance_type, self)

    def __set__(self, instance, value):
        instance._obj_cache[self.att_name] = value
        instance._data[self.model_type_field] = value._meta.db_table
        instance._data[self.model_id_field] = value._get_pk_value()


class ReverseGFK(object):
    def __init__(self, model, model_type_field='object_type',
                 model_id_field='object_id'):
        self.model_class = model
        self.model_type_field = model._meta.fields[model_type_field]
        self.model_id_field = model._meta.fields[model_id_field]

    def __get__(self, instance, instance_type=None):
        if instance:
            return self.model_class.select().where(
                (self.model_type_field == instance._meta.db_table) &
                (self.model_id_field == instance._get_pk_value())
            )
        else:
            return self.model_class.select().where(
                self.model_type_field == instance_type._meta.db_table
            )

    def __set__(self, instance, value):
        mtv = instance._meta.db_table
        miv = instance._get_pk_value()
        if (isinstance(value, SelectQuery) and
                value.model_class == self.model_class):
            UpdateQuery(self.model_class, {
                self.model_type_field: mtv,
                self.model_id_field: miv,
            }).where(value._where).execute()
        elif all(map(lambda i: isinstance(i, self.model_class), value)):
            for obj in value:
                setattr(obj, self.model_type_field.name, mtv)
                setattr(obj, self.model_id_field.name, miv)
                obj.save()
        else:
            raise ValueError('ReverseGFK field unable to handle "%s"' % value)
