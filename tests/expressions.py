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
    """
    Test the conversion of field values using a field's db_value() function.

    It is possible that a field's `db_value()` function may returns a Node
    subclass (e.g. a SQL function). These tests verify and document how such
    conversions are applied in various parts of the query.
    """
    database = get_in_memory_db()
    requires = [UpperModel]

    def test_value_conversion(self):
        # Ensure value is converted on INSERT.
        insert = UpperModel.insert({UpperModel.name: 'huey'})
        self.assertSQL(insert, (
            'INSERT INTO "upper_model" ("name") VALUES (UPPER(?))'), ['huey'])
        uid = insert.execute()

        obj = UpperModel.get(UpperModel.id == uid)
        self.assertEqual(obj.name, 'HUEY')

        # Ensure value is converted on UPDATE.
        update = (UpperModel
                  .update({UpperModel.name: 'zaizee'})
                  .where(UpperModel.id == uid))
        self.assertSQL(update, (
            'UPDATE "upper_model" SET "name" = UPPER(?) WHERE ("id" = ?)'),
            ['zaizee', uid])
        update.execute()

        # Ensure it works with SELECT (or more generally, WHERE expressions).
        select = UpperModel.select().where(UpperModel.name == 'zaizee')
        self.assertSQL(select, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE ("t1"."name" = UPPER(?))'), ['zaizee'])
        obj = select.get()
        self.assertEqual(obj.name, 'ZAIZEE')

        # Ensure it works with DELETE.
        delete = UpperModel.delete().where(UpperModel.name == 'zaizee')
        self.assertSQL(delete, (
            'DELETE FROM "upper_model" WHERE ("name" = UPPER(?))'), ['zaizee'])
        self.assertEqual(delete.execute(), 1)

    def test_value_conversion_mixed(self):
        um = UpperModel.create(name='huey')

        # If we apply a function to the field, the conversion is not applied.
        sq = UpperModel.select().where(fn.SUBSTR(UpperModel.name, 1, 1) == 'h')
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE (SUBSTR("t1"."name", ?, ?) = ?)'), [1, 1, 'h'])
        self.assertRaises(UpperModel.DoesNotExist, sq.get)

        # If we encapsulate the object as a value, the conversion is applied.
        sq = UpperModel.select().where(UpperModel.name == Value('huey'))
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE ("t1"."name" = UPPER(?))'), ['huey'])
        self.assertEqual(sq.get().id, um.id)

        # Unless we explicitly pass converter=False.
        sq = UpperModel.select().where(UpperModel.name == Value('huey', False))
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE ("t1"."name" = ?)'), ['huey'])
        self.assertRaises(UpperModel.DoesNotExist, sq.get)

        # If we specify explicit SQL on the rhs, the conversion is not applied.
        sq = UpperModel.select().where(UpperModel.name == SQL('?', ['huey']))
        self.assertSQL(sq, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE ("t1"."name" = ?)'), ['huey'])
        self.assertRaises(UpperModel.DoesNotExist, sq.get)

    def test_value_conversion_query(self):
        um = UpperModel.create(name='huey')
        UM = UpperModel.alias()
        subq = UM.select(UM.name).where(UM.name == 'huey')

        # Select from WHERE ... IN <subquery>.
        query = UpperModel.select().where(UpperModel.name.in_(subq))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'WHERE ("t1"."name" IN ('
            'SELECT "t2"."name" FROM "upper_model" AS "t2" '
            'WHERE ("t2"."name" = UPPER(?))))'), ['huey'])
        self.assertEqual(query.get().id, um.id)

        # Join on sub-query.
        query = (UpperModel
                 .select()
                 .join(subq, on=(UpperModel.name == subq.c.name)))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name" FROM "upper_model" AS "t1" '
            'INNER JOIN (SELECT "t2"."name" FROM "upper_model" AS "t2" '
            'WHERE ("t2"."name" = UPPER(?))) AS "t3" '
            'ON ("t1"."name" = "t3"."name")'), ['huey'])
        row = query.tuples().get()
        self.assertEqual(row, (um.id, 'HUEY'))

    def test_having_clause(self):
        query = (UpperModel
                 .select(UpperModel.name, fn.COUNT(UpperModel.id).alias('ct'))
                 .group_by(UpperModel.name)
                 .having(UpperModel.name == 'huey'))
        self.assertSQL(query, (
            'SELECT "t1"."name", COUNT("t1"."id") AS "ct" '
            'FROM "upper_model" AS "t1" '
            'GROUP BY "t1"."name" '
            'HAVING ("t1"."name" = UPPER(?))'), ['huey'])
