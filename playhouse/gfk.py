"""
class Tag(Model):
    tag = CharField()
    object_type = CharField(null=True)
    object_id = IntegerField(null=True)
    object = GFKField('object_type', 'object_id')

class Blog(Model):
    tags = ReverseGFK(Tag, 'object_type', 'object_id')

tag.object -> should be a blog
blog.tags -> select query of tags for ``blog`` instance
Blog.tags -> select query of all tags for Blog instances
"""
from peewee import *
from peewee import FieldDescriptor, SelectQuery, UpdateQuery, Model as _Model, BaseModel as _BaseModel


all_models = set()
table_cache = {}


class BaseModel(_BaseModel):
    def __new__(cls, name, bases, attrs):
        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)
        all_models.add(cls)
        return cls

class Model(_Model):
    __metaclass__ = BaseModel

def get_model(tbl_name):
    if tbl_name not in table_cache:
        for model in all_models:
            if model._meta.db_table == tbl_name:
                table_cache[tbl_name] = model
                break
    return table_cache.get(tbl_name)

class GFKField(object):
    def __init__(self, model_type_field='object_type', model_id_field='object_id'):
        self.model_type_field = model_type_field
        self.model_id_field = model_id_field
        self.att_name = '.'.join((self.model_type_field, self.model_id_field))

    def __get__(self, instance, instance_type=None):
        if instance:
            if self.att_name not in instance._obj_cache:
                inst_data = instance._data
                if inst_data.get(self.model_type_field) and inst_data.get(self.model_id_field):
                    tbl_name = instance._data[self.model_type_field]
                    model_class = get_model(tbl_name)
                    if not model_class:
                        raise AttributeError('Model for table "%s" not found in GFK lookup' % tbl_name)

                    instance._obj_cache[self.att_name] = model_class.select().where(
                        model_class._meta.primary_key == instance._data[self.model_id_field]
                    ).get()
            return instance._obj_cache.get(self.att_name)
        return self.field

    def __set__(self, instance, value):
        instance._obj_cache[self.att_name] = value
        instance._data[self.model_type_field] = value._meta.db_table
        instance._data[self.model_id_field] = value.get_id()

class ReverseGFK(object):
    def __init__(self, model, model_type_field='object_type', model_id_field='object_id'):
        self.model_class = model
        self.model_type_field = model._meta.fields[model_type_field]
        self.model_id_field = model._meta.fields[model_id_field]

    def __get__(self, instance, instance_type=None):
        if instance:
            return self.model_class.select().where(
                (self.model_type_field == instance._meta.db_table) &
                (self.model_id_field == instance.get_id())
            )
        else:
            return self.model_class.select().where(
                self.model_type_field == instance_type._meta.db_table
            )

    def __set__(self, instance, value):
        mtv = instance._meta.db_table
        miv = instance.get_id()
        if isinstance(value, SelectQuery) and value.model_class == self.model_class:
            uq = UpdateQuery(self.model_class, {
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
