import sys

from peewee import *
from peewee import Node

if sys.version_info[0] == 3:
    from collections import Callable
    callable = lambda c: isinstance(c, Callable)


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


def cast(node, as_type):
    return fn.CAST(Clause(node, SQL('AS %s' % as_type)))


def _clone_set(s):
    if s:
        return set(s)
    return set()

def model_to_dict(model, recurse=True, backrefs=False, only=None,
                  exclude=None, seen=None, extra_attrs=None,
                  fields_from_query=None, max_depth=None):
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
    """
    max_depth = -1 if max_depth is None else max_depth
    if max_depth == 0:
        recurse = False

    only = _clone_set(only)
    extra_attrs = _clone_set(extra_attrs)

    if fields_from_query is not None:
        for item in fields_from_query._select:
            if isinstance(item, Field):
                only.add(item)
            elif isinstance(item, Node) and item._alias:
                extra_attrs.add(item._alias)

    data = {}
    exclude = _clone_set(exclude)
    seen = _clone_set(seen)
    exclude |= seen
    model_class = type(model)

    for field in model._meta.declared_fields:
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
                    seen=seen,
                    max_depth=max_depth - 1)
            else:
                field_data = {}

        data[field.name] = field_data

    if extra_attrs:
        for attr_name in extra_attrs:
            attr = getattr(model, attr_name)
            if callable(attr):
                data[attr_name] = attr()
            else:
                data[attr_name] = attr

    if backrefs and recurse:
        for related_name, foreign_key in model._meta.reverse_rel.items():
            descriptor = getattr(model_class, related_name)
            if descriptor in exclude or foreign_key in exclude:
                continue
            if only and (descriptor not in only) and (foreign_key not in only):
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
                    exclude=exclude,
                    max_depth=max_depth - 1))

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


class RetryOperationalError(object):
    def execute_sql(self, sql, params=None, require_commit=True):
        try:
            cursor = super(RetryOperationalError, self).execute_sql(
                sql, params, require_commit)
        except OperationalError:
            if not self.is_closed():
                self.close()
            with self.exception_wrapper():
                cursor = self.get_cursor()
                cursor.execute(sql, params or ())
                if require_commit and self.get_autocommit():
                    self.commit()
        return cursor
