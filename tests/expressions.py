from peewee import *

from .base import IS_SQLITE
from .base import ModelTestCase
from .base import TestModel
from .base import get_in_memory_db
from .base import skip_if


class Person(TestModel):
    name = CharField()


class BaseNamesTest(ModelTestCase):
    requires = [Person]

    def assertNames(self, exp, x):
        query = Person.select().where(exp).order_by(Person.name)
        self.assertEqual([p.name for p in query], x)



class TestRegexp(BaseNamesTest):
    @skip_if(IS_SQLITE)
    def test_regexp_iregexp(self):
        people = [Person.create(name=name) for name in ('n1', 'n2', 'n3')]

        self.assertNames(Person.name.regexp('n[1,3]'), ['n1', 'n3'])
        self.assertNames(Person.name.regexp('N[1,3]'), [])
        self.assertNames(Person.name.iregexp('n[1,3]'), ['n1', 'n3'])
        self.assertNames(Person.name.iregexp('N[1,3]'), ['n1', 'n3'])


class TestContains(BaseNamesTest):
    def test_contains_startswith_endswith(self):
        people = [Person.create(name=n) for n in ('huey', 'mickey', 'zaizee')]

        self.assertNames(Person.name.contains('ey'), ['huey', 'mickey'])
        self.assertNames(Person.name.contains('EY'), ['huey', 'mickey'])

        self.assertNames(Person.name.startswith('m'), ['mickey'])
        self.assertNames(Person.name.startswith('M'), ['mickey'])

        self.assertNames(Person.name.endswith('ey'), ['huey', 'mickey'])
        self.assertNames(Person.name.endswith('EY'), ['huey', 'mickey'])


class UpperField(TextField):
    def db_value(self, value):
        return fn.UPPER(value)


class UpperModel(TestModel):
    name = UpperField()


class TestValueConversion(ModelTestCase):
    database = get_in_memory_db()
    requires = [UpperModel]

    def test_value_conversion(self):
        # Ensure value is converted on INSERT.
        insert = UpperModel.insert({UpperModel.name: 'huey'})
        self.assertSQL(insert, (
            'INSERT INTO "uppermodel" ("name") VALUES (UPPER(?))'), ['huey'])
        uid = insert.execute()

        obj = UpperModel.get(UpperModel.id == uid)
        self.assertEqual(obj.name, 'HUEY')

        # Ensure value is converted on UPDATE.
        update = (UpperModel
                  .update({UpperModel.name: 'zaizee'})
                  .where(UpperModel.id == uid))
        self.assertSQL(update, (
            'UPDATE "uppermodel" SET "name" = UPPER(?) WHERE ("id" = ?)'),
            ['zaizee', uid])
        update.execute()

        # Ensure it works with SELECT (or more generally, WHERE expressions).
        select = UpperModel.select().where(UpperModel.name == 'zaizee')
        self.assertSQL(select, (
            'SELECT "t1"."id", "t1"."name" FROM "uppermodel" AS "t1" '
            'WHERE ("t1"."name" = UPPER(?))'), ['zaizee'])
        obj = select.get()
        self.assertEqual(obj.name, 'ZAIZEE')

        # Ensure it works with DELETE.
        delete = UpperModel.delete().where(UpperModel.name == 'zaizee')
        self.assertSQL(delete, (
            'DELETE FROM "uppermodel" WHERE ("name" = UPPER(?))'), ['zaizee'])
        self.assertEqual(delete.execute(), 1)

    def test_value_conversion_mixed(self):
        um = UpperModel.create(name='huey')

        # If we apply a function to the field, the conversion is not applied.
        sq = UpperModel.select().where(fn.SUBSTR(UpperModel.name, 1, 1) == 'h')
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "uppermodel" AS "t1" '
            'WHERE (SUBSTR("t1"."name", ?, ?) = ?)'), [1, 1, 'h'])
        self.assertRaises(UpperModel.DoesNotExist, sq.get)

        # If we encapsulate the object as a value, the conversion is applied.
        sq = UpperModel.select().where(UpperModel.name == Value('huey'))
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "uppermodel" AS "t1" '
            'WHERE ("t1"."name" = UPPER(?))'), ['huey'])
        self.assertEqual(sq.get().id, um.id)

        # Unless we explicitly pass converter=False.
        sq = UpperModel.select().where(UpperModel.name == Value('huey', False))
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "uppermodel" AS "t1" '
            'WHERE ("t1"."name" = ?)'), ['huey'])
        self.assertRaises(UpperModel.DoesNotExist, sq.get)

        # If we specify explicit SQL on the rhs, the conversion is not applied.
        sq = UpperModel.select().where(UpperModel.name == SQL('?', ['huey']))
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "uppermodel" AS "t1" '
            'WHERE ("t1"."name" = ?)'), ['huey'])
        self.assertRaises(UpperModel.DoesNotExist, sq.get)
