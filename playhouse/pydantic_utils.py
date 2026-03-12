from __future__ import annotations

from typing import Any
from typing import Literal
from typing import Optional

from peewee import AutoField
from peewee import ForeignKeyField
from peewee import Model
from playhouse.reflection import FieldTypeMap

from pydantic import BaseModel
from pydantic import Field
from pydantic import create_model


def choices_to_literal(choices):
    return Literal[tuple(val for val, label in choices)]

def choices_description(choices):
    return ', '.join(['%r = %s' % (value, label) for value, label in choices])

def get_field_type(field):
    if isinstance(field, ForeignKeyField):
        field = field.rel_field
    return FieldTypeMap.get(field.field_type, Any)

def to_pydantic(model_cls, exclude=None, include=None, exclude_autofield=True,
                model_name=None):
    exclude = exclude or set()
    fields = {}
    for field in model_cls._meta.sorted_fields:
        name = field.name
        if name in exclude:
            continue
        elif include is not None and name not in include:
            continue
        elif exclude_autofield and isinstance(field, AutoField):
            continue

        if isinstance(field, ForeignKeyField):
            name = field.column_name

        python_type = get_field_type(field)
        choices = field.choices
        if choices:
            python_type = choices_to_literal(choices)

        parts = []
        if field.help_text:
            parts.append(field.help_text)
        if choices:
            parts.append('Choices: %s' % choices_description(choices))
        description = ' | '.join(parts) or None

        field_kwargs = {}
        if field.verbose_name:
            field_kwargs['title'] = field.verbose_name
        if description:
            field_kwargs['description'] = description

        if field.default is not None:
            if callable(field.default):
                field_kwargs['default_factory'] = field.default
            else:
                field_kwargs['default'] = field.default
            if field.null:
                python_type = Optional[python_type]
        elif field.null:
            python_type = Optional[python_type]
            field_kwargs['default'] = None

        fields[name] = (python_type, Field(**field_kwargs))

    model_name = model_name or ('%sSchema' % model_cls.__name__)

    return create_model(model_name, **fields)
