import apsw
import datetime

from playhouse.apsw_ext import *
from .base import ModelTestCase
from .base import TestModel


database = APSWDatabase(':memory:')


class User(TestModel):
    username = TextField()


class Message(TestModel):
    user = ForeignKeyField(User)
    message = TextField()
    pub_date = DateTimeField()
    published = BooleanField()


class TestAPSWExtension(ModelTestCase):
    database = database
    requires = [User, Message]

    def test_db_register_function(self):
        @database.func()
        def title(s):
            return s.title()

        curs = self.database.execute_sql('SELECT title(?)', ('heLLo',))
        self.assertEqual(curs.fetchone()[0], 'Hello')
