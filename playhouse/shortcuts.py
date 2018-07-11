import sys

from peewee import Alias, Field, ForeignKeyField

if sys.version_info[0] == 3:
    from collections import Callable
    callable = lambda c: isinstance(c, Callable)


_clone_set = lambda s: set(s) if s else set()


def model_to_dict(model, recurse=True, backrefs=False, only=None,
                  exclude=None, seen=None, extra_attrs=None,
                  fields_from_query=None, max_depth=None, manytomany=False):
    """
    Convert a model instance (and any related objects) to a dictionary.

    :param bool recurse: Whether foreign-keys should be recursed.
    :param bool backrefs: Whether lists of related objects should be recursed.
    :param only: A list (or set) of field instances indicating which fields
        should be included.
    :param exclude: A list (or set) of field instances that should be
        excluded from the dictionary.
    :param list extra_attrs: Names of model instance attributes or methods
        that should be included.
    :param SelectQuery fields_from_query: Query that was source of model. Take
        fields explicitly selected by the query and serialize them.
    :param int max_depth: Maximum depth to recurse, value <= 0 means no max.
    :param bool manytomany: Process many-to-many fields.
    """
    max_depth = -1 if max_depth is None else max_depth
    if max_depth == 0:
        recurse = False

    only = _clone_set(only)
    extra_attrs = _clone_set(extra_attrs)

    if fields_from_query is not None:
        for item in fields_from_query._returning:
            if isinstance(item, Field):
                only.add(item)
            elif isinstance(item, Alias):
                extra_attrs.add(item._alias)

    data = {}
    exclude = _clone_set(exclude)
    seen = _clone_set(seen)
    exclude |= seen
    model_class = type(model)

    if manytomany:
        for name, m2m in model._meta.manytomany.items():
            if (name in exclude) or (only and (name not in only)):
                continue

            exclude.update((m2m, m2m.rel_model._meta.manytomany[m2m.backref]))
            for fkf in m2m.through_model._meta.refs:
                exclude.add(fkf)

            accum = []
            for rel_obj in getattr(model, name):
                accum.append(model_to_dict(
                    rel_obj,
                    recurse=recurse,
                    backrefs=backrefs,
                    only=only,
                    exclude=exclude,
                    max_depth=max_depth - 1))
            data[name] = accum

    for field in model._meta.sorted_fields:
        if field in exclude or (only and (field not in only)):
            continue

        field_data = model.__data__.get(field.name)
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
                    seen=seen,
                    max_depth=max_depth - 1)
            else:
                field_data = None

        data[field.name] = field_data

    if extra_attrs:
        for attr_name in extra_attrs:
            attr = getattr(model, attr_name)
            if callable(attr):
                data[attr_name] = attr()
            else:
                data[attr_name] = attr

    if backrefs and recurse:
        for foreign_key, rel_model in model._meta.backrefs.items():
            descriptor = getattr(model_class, foreign_key.backref)
            if descriptor in exclude or foreign_key in exclude:
                continue
            if only and (descriptor not in only) and (foreign_key not in only):
                continue

            accum = []
            exclude.add(foreign_key)
            related_query = getattr(model, foreign_key.backref)

            for rel_obj in related_query:
                accum.append(model_to_dict(
                    rel_obj,
                    recurse=recurse,
                    backrefs=backrefs,
                    only=only,
                    exclude=exclude,
                    max_depth=max_depth - 1))

            data[foreign_key.backref] = accum

    return data


def update_model_from_dict(instance, data, ignore_unknown=False):
    meta = instance._meta
    backrefs = dict([(fk.backref, fk) for fk in meta.backrefs])

    for key, value in data.items():
        if key in meta.combined:
            field = meta.combined[key]
            is_backref = False
        elif key in backrefs:
            field = backrefs[key]
            is_backref = True
        elif ignore_unknown:
            setattr(instance, key, value)
            continue
        else:
            raise AttributeError('Unrecognized attribute "%s" for model '
                                 'class %s.' % (key, type(instance)))

        is_foreign_key = isinstance(field, ForeignKeyField)

        if not is_backref and is_foreign_key and isinstance(value, dict):
            try:
                rel_instance = instance.__rel__[field.name]
            except KeyError:
                rel_instance = field.rel_model()
            setattr(
                instance,
                field.name,
                update_model_from_dict(rel_instance, value, ignore_unknown))
        elif is_backref and isinstance(value, (list, tuple)):
            instances = [
                dict_to_model(field.model, row_data, ignore_unknown)
                for row_data in value]
            for rel_instance in instances:
                setattr(rel_instance, field.name, instance)
            setattr(instance, field.backref, instances)
        else:
            setattr(instance, field.name, value)

    return instance


def dict_to_model(model_class, data, ignore_unknown=False):
    return update_model_from_dict(model_class(), data, ignore_unknown)
