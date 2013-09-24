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
    """
    clauses = [R('CASE')]
    simple_case = predicate is not None
    if simple_case:
        clauses.append(predicate)
    for expr, value in expression_tuples:
        # If this is a simple case, each tuple will contain (value, value) pair
        # since the DB will be performing an equality check automatically.
        # Otherwise, we will have (expression, value) pairs.
        clauses.extend((R('WHEN'), expr, R('THEN'), value))
    if default is not None:
        clauses.extend((R('ELSE'), default))
    clauses.append(R('END'))
    return Clause(*clauses)
