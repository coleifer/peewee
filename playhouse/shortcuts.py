from peewee import *


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
