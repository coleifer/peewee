import operator
import os
import unittest

from peewee import *
from playhouse.dataset import DataSet
from playhouse.dataset import Table


db = SqliteDatabase('tmp.db')

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    username = CharField(primary_key=True)

class Note(BaseModel):
    user = ForeignKeyField(User)
    content = TextField()
    timestamp = DateTimeField()

class Category(BaseModel):
    name = CharField()
    parent = ForeignKeyField('self', null=True)


class TestDataSet(unittest.TestCase):
    def setUp(self):
        if os.path.exists('tmp.db'):
            os.unlink('tmp.db')
        db.connect()
        db.create_tables([User, Note, Category])

        self.dataset = DataSet('sqlite:///tmp.db')

    def tearDown(self):
        self.dataset.close()
        db.close()

    def test_introspect(self):
        tables = sorted(self.dataset.tables)
        self.assertEqual(tables, ['category', 'note', 'user'])

        user = self.dataset['user']
        columns = sorted(user.columns)
        self.assertEqual(columns, ['username'])

        note = self.dataset['note']
        columns = sorted(note.columns)
        self.assertEqual(columns, ['content', 'id', 'timestamp', 'user'])

        category = self.dataset['category']
        columns = sorted(category.columns)
        self.assertEqual(columns, ['id', 'name', 'parent'])

    def assertQuery(self, query, expected, sort_key='id'):
        key = operator.itemgetter(sort_key)
        self.assertEqual(
            sorted(list(query), key=key),
            sorted(expected, key=key))

    def test_insert(self):
        user = self.dataset['user']
        for username in ['charlie', 'huey']:
            user.insert(username=username)

        expected = [
            {'username': 'charlie'},
            {'username': 'huey'}]
        self.assertQuery(user.all(), expected, 'username')

        user.insert(username='mickey', age=5)
        expected = [
            {'username': 'charlie', 'age': None},
            {'username': 'huey', 'age': None},
            {'username': 'mickey', 'age': 5}]
        self.assertQuery(user.all(), expected, 'username')

        query = user.find(username='charlie')
        expected = [{'username': 'charlie', 'age': None}]
        self.assertQuery(query, expected, 'username')

        self.assertEqual(
            user.find_one(username='mickey'),
            {'username': 'mickey', 'age': 5})

        self.assertIsNone(user.find_one(username='xx'))

    def test_update(self):
        user = self.dataset['user']
        user.insert(username='charlie')
        user.insert(username='huey')

        self.assertEqual(user.update(favorite_color='green'), 2)
        expected = [
            {'username': 'charlie', 'favorite_color': 'green'},
            {'username': 'huey', 'favorite_color': 'green'}]
        self.assertQuery(user.all(), expected, 'username')

        res = user.update(
            favorite_color='blue',
            username='huey',
            columns=['username'])
        self.assertEqual(res, 1)
        expected[1]['favorite_color'] = 'blue'
        self.assertQuery(user.all(), expected, 'username')
