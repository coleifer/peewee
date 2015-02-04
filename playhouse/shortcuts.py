import re

from peewee import *
from peewee import Field
from peewee import FieldDescriptor
from peewee import SelectQuery


def case(predicate, expression_tuples, default=None):
    """
    CASE statement builder.

    Example CASE statements:

        SELECT foo,
            CASE
                WHEN foo = 1 THEN "one"
                WHEN foo = 2 THEN "two"
                ELSE "?"
            END -- will be in column named "case" in postgres --
        FROM bar;

        -- equivalent to above --
        SELECT foo,
            CASE foo
                WHEN 1 THEN "one"
                WHEN 2 THEN "two"
                ELSE "?"
            END

    Corresponding peewee:

        # No predicate, use expressions.
        Bar.select(Bar.foo, case(None, (
            (Bar.foo == 1, "one"),
            (Bar.foo == 2, "two")), "?"))

        # Predicate, will test for equality.
        Bar.select(Bar.foo, case(Bar.foo, (
            (1, "one"),
            (2, "two")), "?"))
    """
    clauses = [SQL('CASE')]
    simple_case = predicate is not None
    if simple_case:
        clauses.append(predicate)
    for expr, value in expression_tuples:
        # If this is a simple case, each tuple will contain (value, value) pair
        # since the DB will be performing an equality check automatically.
        # Otherwise, we will have (expression, value) pairs.
        clauses.extend((SQL('WHEN'), expr, SQL('THEN'), value))
    if default is not None:
        clauses.extend((SQL('ELSE'), default))
    clauses.append(SQL('END'))
    return Clause(*clauses)


class ManyToManyField(Field):
    def __init__(self, rel_model, related_name=None, through_model=None,
                 _is_backref=False):
        self.rel_model = rel_model
        self._related_name = related_name
        self._through_model = through_model
        self._is_backref = _is_backref
        self.primary_key = False
        self.verbose_name = None

    def add_to_class(self, model_class, name):
        if isinstance(self._through_model, Proxy):
            def callback(through_model):
                self._through_model = through_model
                self.add_to_class(model_class, name)
            self._through_model.attach_callback(callback)
            return

        self.name = name
        self.model_class = model_class
        if not self.verbose_name:
            self.verbose_name = re.sub('_+', ' ', name).title()
        setattr(model_class, name, ManyToManyFieldDescriptor(self))

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
        query = ManyToManyQuery(
            self._instance,
            self._field_descriptor,
            self.model_class)
        query.database = self.database
        return self._clone_attributes(query)

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
            inserts = [{
                fd.src_fk.name: self._instance.get_id(),
                fd.dest_fk.name: rel_instance.get_id()}
                for rel_instance in value]
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
            primary_keys = [rel_instance.get_id() for rel_instance in value]
            return (fd.through_model
                    .delete()
                    .where(
                        (fd.dest_fk << primary_keys) &
                        (fd.src_fk == self._instance.get_id()))
                    .execute())

    def clear(self):
        return (self._field_descriptor.through_model
                .delete()
                .where(self._field_descriptor.src_fk == self._instance)
                .execute())


def _clone_set(s):
    if s:
        return set(s)
    return set()

def model_to_dict(model, recurse=True, backrefs=False, only=None,
                  exclude=None, seen=None):
    """
    Convert a model instance (and any related objects) to a dictionary.

    :param bool recurse: Whether foreign-keys should be recursed.
    :param bool backrefs: Whether lists of related objects should be recursed.
    :param only: A list (or set) of field instances indicating which fields
        should be included.
    :param exclude: A list (or set) of field instances that should be
        excluded from the dictionary.
    """
    data = {}
    only = _clone_set(only)
    exclude = _clone_set(exclude)
    seen = _clone_set(seen)
    exclude |= seen
    model_class = type(model)

    for field in model._meta.get_fields():
        if field in exclude or (only and (field not in only)):
            continue

        field_data = model._data.get(field.name)
        if isinstance(field, ForeignKeyField) and recurse:
            if field_data:
                seen.add(field)
                rel_obj = getattr(model, field.name)
                field_data = model_to_dict(
                    rel_obj,
                    recurse=recurse,
                    backrefs=backrefs,
                    only=only,
                    exclude=exclude,
                    seen=seen)
            else:
                field_data = {}

        data[field.name] = field_data

    if backrefs:
        for related_name, foreign_key in model._meta.reverse_rel.items():
            descriptor = getattr(model_class, related_name)
            if descriptor in exclude or foreign_key in exclude:
                continue
            if only and (descriptor not in only or foreign_key not in only):
                continue

            accum = []
            exclude.add(foreign_key)
            related_query = getattr(
                model,
                related_name + '_prefetch',
                getattr(model, related_name))

            for rel_obj in related_query:
                accum.append(model_to_dict(
                    rel_obj,
                    recurse=recurse,
                    backrefs=backrefs,
                    only=only,
                    exclude=exclude))

            data[related_name] = accum

    return data


def dict_to_model(model_class, data, ignore_unknown=False):
    instance = model_class()
    meta = model_class._meta
    for key, value in data.items():
        if key in meta.fields:
            field = meta.fields[key]
            is_backref = False
        elif key in model_class._meta.reverse_rel:
            field = meta.reverse_rel[key]
            is_backref = True
        elif ignore_unknown:
            setattr(instance, key, value)
            continue
        else:
            raise AttributeError('Unrecognized attribute "%s" for model '
                                 'class %s.' % (key, model_class))

        is_foreign_key = isinstance(field, ForeignKeyField)

        if not is_backref and is_foreign_key and isinstance(value, dict):
            setattr(
                instance,
                field.name,
                dict_to_model(field.rel_model, value, ignore_unknown))
        elif is_backref and isinstance(value, (list, tuple)):
            instances = [
                dict_to_model(
                    field.model_class,
                    row_data,
                    ignore_unknown)
                for row_data in value]
            for rel_instance in instances:
                setattr(rel_instance, field.name, instance)
            setattr(instance, field.related_name, instances)
        else:
            setattr(instance, field.name, value)

    return instance


class Infix(object):
    def __init__(self, fn):
        self._fn = fn

    def __ror__(self, lhs):
        return Infix(lambda r: self.fn(lhs, r))

    def __or__(self, rhs):
        return self.fn(rhs)
