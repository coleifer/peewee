from peewee import *
from playhouse.fields import CompressedField
from playhouse.fields import PickleField

from .base import db
from .base import ModelTestCase
from .base import TestModel


class Comp(TestModel):
    key = TextField()
    data = CompressedField()


class Pickled(TestModel):
    key = TextField()
    data = PickleField()


class TestCompressedField(ModelTestCase):
    requires = [Comp]

    def test_compressed_field(self):
        a = b'a' * 1024
        b = b'b' * 1024
        Comp.create(data=a, key='a')
        Comp.create(data=b, key='b')

        a_db = Comp.get(Comp.key == 'a')
        self.assertEqual(a_db.data, a)

        b_db = Comp.get(Comp.key == 'b')
        self.assertEqual(b_db.data, b)

        # Get at the underlying data.
        CompTbl = Table('comp', ('id', 'data', 'key')).bind(self.database)
        obj = CompTbl.select().where(CompTbl.key == 'a').get()
        self.assertEqual(obj['key'], 'a')

        # Ensure that the data actually was compressed.
        self.assertTrue(len(obj['data']) < 1024)


class TestPickleField(ModelTestCase):
    requires = [Pickled]

    def test_pickle_field(self):
        a = {'k1': 'v1', 'k2': [0, 1, 2], 'k3': None}
        b = 'just a string'
        Pickled.create(data=a, key='a')
        Pickled.create(data=b, key='b')

        a_db = Pickled.get(Pickled.key == 'a')
        self.assertEqual(a_db.data, a)

        b_db = Pickled.get(Pickled.key == 'b')
        self.assertEqual(b_db.data, b)
