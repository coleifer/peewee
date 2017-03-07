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
