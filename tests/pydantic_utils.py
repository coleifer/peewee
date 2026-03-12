from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Optional

from peewee import *
from playhouse.pydantic_utils import to_pydantic
from pydantic import BaseModel

from .base import BaseTestCase
from .base import get_in_memory_db


db = get_in_memory_db()

class Person(db.Model):
    name = CharField(verbose_name='Full Name', help_text='Display name')
    age = IntegerField()
    active = BooleanField(default=True)
    bio = TextField(null=True)
    score = FloatField(null=True, default=0.0)
    status = CharField(
        verbose_name='Status',
        help_text='Record status',
        choices=[
            ('active', 'Active'),
            ('archived', 'Archived'),
            ('deleted', 'Deleted'),
        ])
    created = DateTimeField(default=datetime.datetime.now)

class User(db.Model):
    name = CharField()

class Tweet(db.Model):
    user = ForeignKeyField(User)
    content = TextField()
    timestamp = TimestampField(default=datetime.datetime.now)

class AllTypes(db.Model):
    f_blob = BlobField()
    f_bool = BooleanField()
    f_char = CharField()
    f_date = DateField()
    f_datetime = DateTimeField()
    f_decimal = DecimalField()
    f_double = DoubleField()
    f_float = FloatField()
    f_int = IntegerField()
    f_smallint = SmallIntegerField()
    f_text = TextField()
    f_time = TimeField()
    f_uuid = UUIDField()


class TestPydanticConversion(BaseTestCase):
    def test_conversion(self):
        Schema = to_pydantic(Person)
        self.assertTrue(issubclass(Schema, BaseModel))
        self.assertEqual(Schema.__name__, 'PersonSchema')
        self.assertEqual(set(Schema.model_fields), {
            'name', 'age', 'active', 'bio', 'score', 'status', 'created'})

    def test_application(self):
        Schema = to_pydantic(Person)
        obj = Schema(name='Huey', age=14, status='active')
        ts = obj.created
        self.assertEqual(obj.dict(), {
            'name': 'Huey',
            'age': 14,
            'active': True,
            'bio': None,
            'score': 0.0,
            'status': 'active',
            'created': ts})

        with self.assertRaises(ValueError) as ctx:
            obj = Schema()

        self.assertTrue('3 validation errors' in str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            obj = Schema(name='Huey', age=14)

        self.assertTrue('1 validation error' in str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            obj = Schema(name='Huey', age=14, status='invalid')

        self.assertTrue('Input should be' in str(ctx.exception))

    def test_include_exclude(self):
        Schema = to_pydantic(Person, exclude=('age', 'bio'))
        self.assertEqual(set(Schema.model_fields), {
            'name', 'active', 'score', 'status', 'created'})

        Schema = to_pydantic(Person, include=('name', 'status'))
        self.assertEqual(set(Schema.model_fields), {'name', 'status'})

    def test_nullable(self):
        Schema = to_pydantic(Person)
        self.assertTrue(Schema.model_fields['name'].is_required())
        self.assertTrue(Schema.model_fields['age'].is_required())
        self.assertFalse(Schema.model_fields['bio'].is_required())
        self.assertFalse(Schema.model_fields['score'].is_required())

        self.assertIsNone(Schema.model_fields['bio'].default)
        self.assertEqual(Schema.model_fields['score'].default, 0.0)

    def test_defaults(self):
        Schema = to_pydantic(Person)
        obj = Schema(name='Huey', age=14, status='active')
        self.assertTrue(obj.active)
        self.assertEqual(obj.score, 0.0)
        self.assertIsNone(obj.bio)
        self.assertTrue(isinstance(obj.created, datetime.datetime))

    def test_choices(self):
        Schema = to_pydantic(Person, include='status')

        for choice in ('active', 'archived', 'deleted'):
            instance = Schema(status=choice)
            self.assertEqual(instance.status, choice)

        with self.assertRaises(ValueError):
            instance = Schema(status='invalid')

    def test_metadata(self):
        Schema = to_pydantic(Person)
        self.assertEqual(Schema.model_fields['name'].title, 'Full Name')
        self.assertEqual(Schema.model_fields['status'].title, 'Status')
        self.assertIsNone(Schema.model_fields['age'].title)

        self.assertIn('Display name', Schema.model_fields['name'].description)
        self.assertIsNone(Schema.model_fields['age'].description)

        desc = Schema.model_fields['status'].description
        self.assertIn('Record status', desc)
        self.assertIn("'active' = Active", desc)
        self.assertIn("'deleted' = Deleted", desc)

        jschema = Schema.model_json_schema()
        self.assertEqual(jschema['properties']['name']['title'], 'Full Name')

    def test_foreign_key(self):
        Schema = to_pydantic(Tweet)
        self.assertEqual(set(Schema.model_fields),
                         {'user_id', 'content', 'timestamp'})

        obj = Schema(user_id=1337, content='Test')
        self.assertEqual(obj.user_id, 1337)
        self.assertEqual(obj.content, 'Test')

    def test_type_mapping(self):
        Schema = to_pydantic(AllTypes)
        valid_data = {
            'f_blob': b'\x00\x01',
            'f_bool': True,
            'f_char': 'world',
            'f_date': datetime.date.today(),
            'f_datetime': datetime.datetime.now(),
            'f_decimal': decimal.Decimal('3.14'),
            'f_double': 2.718,
            'f_float': 1.5,
            'f_int': 42,
            'f_smallint': 7,
            'f_text': 'hello',
            'f_time': datetime.time(12, 30),
            'f_uuid': uuid.uuid4(),
        }
        instance = Schema(**valid_data)
        for key, val in valid_data.items():
            self.assertEqual(getattr(instance, key), val)
