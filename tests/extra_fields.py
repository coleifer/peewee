import enum

from peewee import *
from playhouse.fields import CompressedField
from playhouse.fields import EnumField
from playhouse.fields import IntEnumField
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


class Color(enum.Enum):
    RED = 'red'
    BLUE = 'blue'


class Prio(enum.IntEnum):
    LOW = 1
    HIGH = 9


class Enums(TestModel):
    color = EnumField(Color, null=True)
    prio = IntEnumField(Prio, null=True)


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

    def test_compressed_field_str(self):
        Comp.create(data='caf\xe9 ☃', key='s')
        s_db = Comp.get(Comp.key == 's')
        self.assertEqual(s_db.data.decode('utf8'), 'caf\xe9 ☃')


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


class TestEnumField(ModelTestCase):
    requires = [Enums]

    def test_enum_field(self):
        Enums.create(color=Color.RED, prio=Prio.HIGH)
        Enums.create(color='blue', prio=9)  # Raw values normalize.
        Enums.create()

        e = Enums.get(Enums.color == Color.RED)
        self.assertTrue(e.color is Color.RED)
        self.assertTrue(e.prio is Prio.HIGH)

        # Values are stored, members come back.
        tbl = Table('enums', ('id', 'color', 'prio')).bind(self.database)
        obj = tbl.select().order_by(tbl.id).get()
        self.assertEqual((obj['color'], obj['prio']), ('red', 9))

        self.assertEqual(
            Enums.select().where(Enums.color == Color.BLUE).count(), 1)
        self.assertEqual(Enums.select().where(
            Enums.prio.in_([Prio.LOW, Prio.HIGH])).count(), 2)
        self.assertTrue(Enums.get(Enums.color.is_null()).prio is None)

    def test_enum_field_invalid(self):
        self.assertRaises(ValueError, Enums.create, color='mauve')
        self.assertRaises(ValueError, Enums.create, prio=4)
