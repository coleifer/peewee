from __future__ import annotations

import datetime
import decimal
import uuid
from typing import List

from peewee import *
from playhouse.pydantic_utils import to_pydantic
from pydantic import BaseModel

from .base import ModelDatabaseTestCase
from .base import get_in_memory_db
from .base import requires_models
from .base import TestModel


class User(TestModel):
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
            ('deleted', 'Deleted')])
    created = DateTimeField(default=datetime.datetime.now)


class Tweet(TestModel):
    user = ForeignKeyField(User, backref='tweets')
    content = TextField()
    created = DateTimeField(default=datetime.datetime.now)


class NullableFK(TestModel):
    user = ForeignKeyField(User, null=True, backref='nullable_things')
    label = CharField()


class AllTypes(TestModel):
    f_text = TextField()
    f_blob = BlobField()
    f_bool = BooleanField()
    f_date = DateField()
    f_datetime = DateTimeField()
    f_decimal = DecimalField()
    f_double = DoubleField()
    f_float = FloatField()
    f_int = IntegerField()
    f_smallint = SmallIntegerField()
    f_time = TimeField()
    f_uuid = UUIDField()
    f_char = CharField()


class BasePydanticTestCase(ModelDatabaseTestCase):
    database = get_in_memory_db()


class TestPydanticConversion(BasePydanticTestCase):
    def test_conversion(self):
        Schema = to_pydantic(User)
        self.assertTrue(issubclass(Schema, BaseModel))
        self.assertEqual(Schema.__name__, 'UserSchema')
        self.assertEqual(set(Schema.model_fields), {
            'name', 'age', 'active', 'bio', 'score', 'status', 'created'})

    def test_base_model(self):
        class TestBase(BaseModel):
            x: int = 123

        Schema = to_pydantic(User, base_model=TestBase)
        self.assertEqual(set(Schema.model_fields), {
            'name', 'age', 'active', 'bio', 'score', 'status', 'created',
            'x'})

        obj = Schema(name='Huey', age=14, status='active')
        ts = obj.created
        self.assertEqual(obj.dict(), {
            'name': 'Huey',
            'age': 14,
            'active': True,
            'bio': None,
            'score': 0.0,
            'status': 'active',
            'created': ts,
            'x': 123})

        huey = User(name='Huey', age=14, status='active', x=12)
        validated = Schema.model_validate(huey)
        self.assertEqual(validated.name, 'Huey')
        self.assertEqual(validated.x, 12)

    def test_application(self):
        Schema = to_pydantic(User)
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

    def test_autofield(self):
        Schema = to_pydantic(User)
        self.assertNotIn('id', Schema.model_fields)

        Schema = to_pydantic(User, exclude_autofield=False)
        self.assertIn('id', Schema.model_fields)

    def test_nullable(self):
        Schema = to_pydantic(User)
        self.assertTrue(Schema.model_fields['name'].is_required())
        self.assertTrue(Schema.model_fields['age'].is_required())
        self.assertFalse(Schema.model_fields['bio'].is_required())
        self.assertFalse(Schema.model_fields['score'].is_required())

        self.assertIsNone(Schema.model_fields['bio'].default)
        self.assertEqual(Schema.model_fields['score'].default, 0.0)

    def test_defaults(self):
        Schema = to_pydantic(User)
        obj = Schema(name='Huey', age=14, status='active')
        self.assertTrue(obj.active)
        self.assertEqual(obj.score, 0.0)
        self.assertIsNone(obj.bio)
        self.assertTrue(isinstance(obj.created, datetime.datetime))

    def test_choices(self):
        Schema = to_pydantic(User, include='status')

        for choice in ('active', 'archived', 'deleted'):
            instance = Schema(status=choice)
            self.assertEqual(instance.status, choice)

        with self.assertRaises(ValueError):
            instance = Schema(status='invalid')

    def test_metadata(self):
        Schema = to_pydantic(User)
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
                         {'user_id', 'content', 'created'})

        obj = Schema(user_id=1337, content='Test')
        self.assertEqual(obj.user_id, 1337)
        self.assertEqual(obj.content, 'Test')

        with self.assertRaises(ValueError):
            Schema(user_id='not_an_int', content='test')

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
            'f_time': datetime.time(12, 14),
            'f_uuid': uuid.uuid4(),
        }
        instance = Schema(**valid_data)
        for key, val in valid_data.items():
            self.assertEqual(getattr(instance, key), val)

    def test_include_exclude(self):
        Schema = to_pydantic(User, exclude={'age', 'bio'})
        self.assertNotIn('age', Schema.model_fields)
        self.assertNotIn('bio', Schema.model_fields)
        self.assertIn('name', Schema.model_fields)

        Schema = to_pydantic(User, include={'name', 'status'})
        self.assertEqual(set(Schema.model_fields), {'name', 'status'})

        Schema = to_pydantic(User, include={'name', 'age'}, exclude={'age'})
        self.assertEqual(set(Schema.model_fields), {'name'})

    def test_nullable_fields(self):
        Schema = to_pydantic(User)
        self.assertTrue(Schema.model_fields['name'].is_required())
        self.assertTrue(Schema.model_fields['age'].is_required())

        self.assertEqual(Schema.model_fields['bio'].default, None)
        self.assertFalse(Schema.model_fields['bio'].is_required())

        instance = Schema(name='a', age=1, status='active')
        self.assertEqual(instance.score, 0.0)
        self.assertIsNone(instance.bio)
        self.assertEqual(instance.active, True)
        self.assertIsInstance(instance.created, datetime.datetime)

    def test_schema_generation(self):
        for model in (User, Tweet, AllTypes):
            with self.subTest(model=model.__name__):
                Schema = to_pydantic(model)
                schema = Schema.model_json_schema()
                self.assertIn('properties', schema)

        Schema = to_pydantic(User)
        schema = Schema.model_json_schema()
        bio_schema = schema['properties']['bio']
        any_of_types = [s.get('type') for s in bio_schema.get('anyOf', [])]
        self.assertIn('null', any_of_types)

    @requires_models(User)
    def test_validate_model(self):
        Schema = to_pydantic(User)

        u = User.create(name='Huey', age=14, status='active')
        validated = Schema.model_validate(u)
        self.assertEqual(validated.dict(), {
            'name': 'Huey',
            'age': 14,
            'active': True,
            'bio': None,
            'score': 0.0,
            'status': 'active',
            'created': u.created})

        us = User(**validated.dict())
        self.assertEqual(us.name, 'Huey')
        self.assertEqual(us.age, 14)
        self.assertTrue(us.active)
        self.assertIsNone(us.bio)
        self.assertEqual(us.score, 0.0)
        self.assertEqual(us.status, 'active')
        self.assertEqual(us.created, u.created)
        self.assertIsNone(us.id)

        v2 = Schema.model_validate(validated.dict())
        self.assertEqual(validated, v2)

    @requires_models(User, Tweet)
    def test_validate_model_foreign_key(self):
        Schema = to_pydantic(Tweet)

        user = User.create(name='Huey', age=14, status='active')
        tweet = Tweet.create(user=user, content='hello')

        validated = Schema.model_validate(tweet)
        self.assertEqual(validated.dict(), {
            'content': 'hello',
            'created': tweet.created,
            'user_id': user.id})

        ts = Tweet(**validated.dict())
        self.assertEqual(ts.content, 'hello')
        self.assertEqual(ts.user_id, user.id)
        self.assertEqual(ts.user.name, 'Huey')  # Triggers query.
        self.assertIsNone(ts.id)

        v2 = Schema.model_validate(validated.dict())
        self.assertEqual(validated, v2)


class TestRelationships(BasePydanticTestCase):
    def test_nested_schema(self):
        UserSchema = to_pydantic(User, exclude_autofield=False)
        TweetResponse = to_pydantic(
            Tweet,
            exclude_autofield=False,
            relationships={Tweet.user: UserSchema})

        self.assertEqual(set(TweetResponse.model_fields),
                         {'id', 'user', 'content', 'created'})

        instance = TweetResponse(
            id=1,
            user={'id': 1, 'name': 'Huey', 'age': 14, 'status': 'active'},
            content='hello')
        self.assertEqual(instance.user.name, 'Huey')
        self.assertEqual(instance.content, 'hello')

        with self.assertRaises(ValueError):
            TweetResponse(id=1, user=42, content='hello')

        OtherSchema = to_pydantic(Tweet, relationships={})
        self.assertIn('user_id', OtherSchema.model_fields)

    def test_nested_relationship_in_json_schema(self):
        UserSchema = to_pydantic(User, exclude_autofield=False)
        TweetResponse = to_pydantic(
            Tweet, exclude_autofield=False,
            relationships={Tweet.user: UserSchema})

        schema = TweetResponse.model_json_schema()
        self.assertIn('user', schema['properties'])

    def test_nullable_fk_relationship(self):
        UserSchema = to_pydantic(User, exclude_autofield=False)
        Schema = to_pydantic(
            NullableFK,
            exclude_autofield=False,
            relationships={NullableFK.user: UserSchema})

        instance = Schema(id=1, user=None, label='test')
        self.assertIsNone(instance.user)

        instance = Schema(id=1, label='test', user={
            'id': 1,
            'name': 'Huey',
            'age': 14,
            'status': 'active'})
        self.assertEqual(instance.user.name, 'Huey')

    def test_metadata_preserved_on_nested_field(self):
        UserSchema = to_pydantic(User, exclude_autofield=False)
        Schema = to_pydantic(
            NullableFK, exclude_autofield=False,
            relationships={NullableFK.user: UserSchema})

        field_info = Schema.model_fields['user']
        self.assertFalse(field_info.is_required())

    def test_backref(self):
        TweetFlat = to_pydantic(Tweet, exclude_autofield=False)
        UserDetail = to_pydantic(
            User, exclude_autofield=False,
            relationships={User.tweets: List[TweetFlat]})

        self.assertEqual(set(UserDetail.model_fields), {
            'id', 'name', 'age', 'active', 'bio', 'score', 'status',
            'created', 'tweets'})

        instance = UserDetail(id=1, name='Huey', age=14, status='active')
        self.assertEqual(instance.tweets, [])

        instance = UserDetail(
            id=1, name='Huey', age=14, status='active',
            tweets=[
                {'id': 1, 'user_id': 1, 'content': 'hello'},
                {'id': 2, 'user_id': 1, 'content': 'world'},
            ])
        self.assertEqual(len(instance.tweets), 2)
        self.assertEqual(instance.tweets[0].content, 'hello')

        with self.assertRaises(ValueError):
            UserDetail(id=1, name='Huey', age=14, status='active',
                       tweets=[{'bad': 'data'}])

    @requires_models(User, Tweet)
    def test_validate_fk(self):
        UserSchema = to_pydantic(User, exclude_autofield=False)
        TweetResponse = to_pydantic(
            Tweet, exclude_autofield=False,
            relationships={Tweet.user: UserSchema})

        user = User.create(name='Huey', age=14, status='active')
        Tweet.create(user=user, content='hello')

        # Re-fetch so rel is not populated.
        tweet = Tweet.select().get()

        with self.assertQueryCount(1):
            result = TweetResponse.model_validate(tweet)
            self.assertEqual(result.content, 'hello')
            self.assertEqual(result.user.name, 'Huey')
            self.assertEqual(result.user.age, 14)

        tweet = (Tweet
                 .select(Tweet, User)
                 .join(User)
                 .get())

        with self.assertQueryCount(0):
            result = TweetResponse.model_validate(tweet)
            self.assertEqual(result.content, 'hello')
            self.assertEqual(result.user.name, 'Huey')
            self.assertEqual(result.user.age, 14)

    @requires_models(User, Tweet)
    def test_validate_backref(self):
        TweetFlat = to_pydantic(Tweet, exclude_autofield=False,
                                exclude={'user'})
        UserDetail = to_pydantic(
            User, exclude_autofield=False,
            relationships={User.tweets: List[TweetFlat]})

        user = User.create(name='Huey', age=14, status='active')
        Tweet.create(user=user, content=f't0')
        Tweet.create(user=user, content=f't1')

        # Will evaluate user.tweets on demand.
        with self.assertQueryCount(1):
            result = UserDetail.model_validate(user)
            self.assertEqual(result.name, 'Huey')
            self.assertEqual(sorted([t.content for t in result.tweets]),
                             ['t0', 't1'])

        # Will use prefetched tweets.
        user = User.select().prefetch(Tweet.select().order_by(Tweet.id))[0]
        with self.assertQueryCount(0):
            result = UserDetail.model_validate(user)
            self.assertEqual(result.name, 'Huey')
            self.assertEqual([t.content for t in result.tweets], ['t0', 't1'])
