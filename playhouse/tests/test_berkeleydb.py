import os

from peewee import IntegrityError
from playhouse.berkeleydb import *
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase

database = database_initializer.get_database('berkeleydb')

class BaseModel(Model):
    class Meta:
        database = database

class Person(BaseModel):
    name = CharField(unique=True)

class Message(BaseModel):
    person = ForeignKeyField(Person, related_name='messages')
    body = TextField()


class TestBerkeleyDatabase(ModelTestCase):
    requires = [Person, Message]

    def tearDown(self):
        super(TestBerkeleyDatabase, self).tearDown()
        database.close()

    def test_storage_retrieval(self):
        pc = Person.create(name='charlie')
        ph = Person.create(name='huey')

        for i in range(3):
            Message.create(person=pc, body='message-%s' % i)

        self.assertEqual(Message.select().count(), 3)
        self.assertEqual(Person.select().count(), 2)
        self.assertEqual(
            [msg.body for msg in pc.messages.order_by(Message.body)],
            ['message-0', 'message-1', 'message-2'])
        self.assertEqual(list(ph.messages), [])

    def test_transaction(self):
        with database.transaction():
            Person.create(name='charlie')

        self.assertEqual(Person.select().count(), 1)

        @database.commit_on_success
        def rollback():
            Person.create(name='charlie')

        self.assertRaises(IntegrityError, rollback)
        self.assertEqual(Person.select().count(), 1)
