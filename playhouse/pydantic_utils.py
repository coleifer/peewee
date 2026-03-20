from __future__ import annotations

from typing import Any
from typing import Literal
from typing import Optional
from typing import get_origin

from peewee import AutoField
from peewee import ForeignKeyField
from peewee import Model
from playhouse.reflection import FieldTypeMap

from pydantic import BaseModel
from pydantic import ConfigDict
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
                model_name=None, relationships=None, base_model=None):
    exclude = exclude or set()
    relationships = relationships or {}
    fields = {}

    rel_fields = {}
    backref_fields = {}
    for field, schema in relationships.items():
        if isinstance(field, ForeignKeyField):
            rel_fields[field.name] = schema
        else:
            backref_fields[field.field.backref] = schema

    for field in model_cls._meta.sorted_fields:
        name = field.name
        if name in exclude:
            continue
        elif include is not None and name not in include:
            continue
        elif exclude_autofield and isinstance(field, AutoField):
            continue

        if isinstance(field, ForeignKeyField):
            if name in rel_fields:
                schema = rel_fields[name]
                field_kwargs = {}
                if field.verbose_name:
                    field_kwargs['title'] = field.verbose_name
                if field.help_text:
                    field_kwargs['description'] = field.help_text
                if field.null:
                    schema = Optional[schema]
                    field_kwargs['default'] = None
                fields[name] = (schema, Field(**field_kwargs))
                continue

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

    for name, schema in backref_fields.items():
        origin = get_origin(schema)
        if origin is not list:
            raise ValueError('back-references must use a List type')
        fields[name] = (schema, Field(default_factory=list))

    model_name = model_name or ('%sSchema' % model_cls.__name__)

    kwargs = {}
    kwargs.update(fields)

    if base_model is not None:
        class Base(base_model, from_attributes=True):
            pass
        kwargs['__base__'] = Base
    else:
        kwargs['__config__'] = ConfigDict(from_attributes=True)

    return create_model(model_name, **kwargs)
