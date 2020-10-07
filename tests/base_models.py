from peewee import *

from .base import TestModel


class Person(TestModel):
    first = CharField()
    last = CharField()
    dob = DateField(index=True)

    class Meta:
        indexes = (
            (('first', 'last'), True),
        )


class Note(TestModel):
    author = ForeignKeyField(Person)
    content = TextField()


class Category(TestModel):
    parent = ForeignKeyField('self', backref='children', null=True)
    name = CharField(max_length=20, primary_key=True)


class Relationship(TestModel):
    from_person = ForeignKeyField(Person, backref='relations')
    to_person = ForeignKeyField(Person, backref='related_to')


class Register(TestModel):
    value = IntegerField()


class User(TestModel):
    username = CharField()

    class Meta:
        table_name = 'users'


class Account(TestModel):
    email = CharField()
    user = ForeignKeyField(User, backref='accounts', null=True)


class Tweet(TestModel):
    user = ForeignKeyField(User, backref='tweets')
    content = TextField()
    timestamp = TimestampField()


class Favorite(TestModel):
    user = ForeignKeyField(User, backref='favorites')
    tweet = ForeignKeyField(Tweet, backref='favorites')


class Sample(TestModel):
    counter = IntegerField()
    value = FloatField(default=1.0)


class SampleMeta(TestModel):
    sample = ForeignKeyField(Sample, backref='metadata')
    value = FloatField(default=0.0)


class A(TestModel):
    a = TextField()
class B(TestModel):
    a = ForeignKeyField(A, backref='bs')
    b = TextField()
class C(TestModel):
    b = ForeignKeyField(B, backref='cs')
    c = TextField()


class Emp(TestModel):
    first = CharField()
    last = CharField()
    empno = CharField(unique=True)

    class Meta:
        indexes = (
            (('first', 'last'), True),
        )


class OCTest(TestModel):
    a = CharField(unique=True)
    b = IntegerField(default=0)
    c = IntegerField(default=0)


class UKVP(TestModel):
    key = TextField()
    value = IntegerField()
    extra = IntegerField()

    class Meta:
        # Partial index, the WHERE clause must be reflected in the conflict
        # target.
        indexes = [
            SQL('CREATE UNIQUE INDEX "ukvp_kve" ON "ukvp" ("key", "value") '
                'WHERE "extra" > 1')]
