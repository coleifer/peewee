from peewee import *
from playhouse.hybrid import *

from .base import ModelTestCase
from .base import TestModel
from .base import get_in_memory_db


class Interval(TestModel):
    start = IntegerField()
    end = IntegerField()

    @hybrid_property
    def length(self):
        return self.end - self.start

    @hybrid_method
    def contains(self, point):
        return (self.start <= point) & (point < self.end)

    @hybrid_property
    def radius(self):
        return int(abs(self.length) / 2)

    @radius.expression
    def radius(cls):
        return fn.ABS(cls.length) / 2


class Person(TestModel):
    first = TextField()
    last = TextField()

    @hybrid_property
    def full_name(self):
        return self.first + ' ' + self.last


class TestHybridProperties(ModelTestCase):
    database = get_in_memory_db()
    requires = [Interval, Person]

    def setUp(self):
        super(TestHybridProperties, self).setUp()
        intervals = (
            (1, 5),
            (2, 6),
            (3, 5),
            (2, 5))
        for start, end in intervals:
            Interval.create(start=start, end=end)

    def test_hybrid_property(self):
        query = Interval.select().where(Interval.length == 4)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."start", "t1"."end" '
            'FROM "interval" AS "t1" '
            'WHERE (("t1"."end" - "t1"."start") = ?)'), [4])

        results = sorted((i.start, i.end) for i in query)
        self.assertEqual(results, [(1, 5), (2, 6)])

        query = Interval.select().order_by(Interval.id)
        self.assertEqual([i.length for i in query], [4, 4, 2, 3])

    def test_hybrid_method(self):
        query = Interval.select().where(Interval.contains(2))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."start", "t1"."end" '
            'FROM "interval" AS "t1" '
            'WHERE (("t1"."start" <= ?) AND ("t1"."end" > ?))'), [2, 2])

        results = sorted((i.start, i.end) for i in query)
        self.assertEqual(results, [(1, 5), (2, 5), (2, 6)])

        query = Interval.select().order_by(Interval.id)
        self.assertEqual([i.contains(2) for i in query], [1, 1, 0, 1])

    def test_expression(self):
        query = Interval.select().where(Interval.radius == 2)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."start", "t1"."end" '
            'FROM "interval" AS "t1" '
            'WHERE ((ABS("t1"."end" - "t1"."start") / ?) = ?)'), [2, 2])

        self.assertEqual(sorted((i.start, i.end) for i in query),
                         [(1, 5), (2, 6)])

        query = Interval.select().order_by(Interval.id)
        self.assertEqual([i.radius for i in query], [2, 2, 1, 1])

    def test_string_fields(self):
        huey = Person.create(first='huey', last='cat')
        zaizee = Person.create(first='zaizee', last='kitten')

        self.assertEqual(huey.full_name, 'huey cat')
        self.assertEqual(zaizee.full_name, 'zaizee kitten')

        query = Person.select().where(Person.full_name.startswith('huey c'))
        huey_db = query.get()
        self.assertEqual(huey_db.id, huey.id)
