import os
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
import sys
import unittest

from peewee import *
from pwiz import *


db = SqliteDatabase('tmp.db')

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    username = CharField(primary_key=True)

class Note(BaseModel):
    user = ForeignKeyField(User)
    text = TextField(index=True)

class Category(BaseModel):
    name = CharField(unique=True)
    parent = ForeignKeyField('self', null=True)

class capture_output(object):
    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._buffer = StringIO()
        return self

    def __exit__(self, *args):
        self.data = self._buffer.getvalue()
        sys.stdout = self._stdout

EXPECTED = """
from peewee import *

database = SqliteDatabase('tmp.db', **{})

class UnknownField(object):
    pass

class BaseModel(Model):
    class Meta:
        database = database

class Category(BaseModel):
    name = CharField(unique=True)
    parent = ForeignKeyField(db_column='parent_id', null=True, rel_model='self', to_field='id')

    class Meta:
        db_table = 'category'

class User(BaseModel):
    username = CharField(primary_key=True)

    class Meta:
        db_table = 'user'

class Note(BaseModel):
    text = TextField(index=True)
    user = ForeignKeyField(db_column='user_id', rel_model=User, to_field='username')

    class Meta:
        db_table = 'note'
""".strip()


class TestPwiz(unittest.TestCase):
    def setUp(self):
        if os.path.exists('tmp.db'):
            os.unlink('tmp.db')
        db.connect()
        db.create_tables([User, Note, Category])
        self.introspector = Introspector.from_database(db)

    def tearDown(self):
        db.close()

    def test_print_models(self):
        with capture_output() as output:
            print_models(self.introspector)

        self.assertEqual(output.data.strip(), EXPECTED)
