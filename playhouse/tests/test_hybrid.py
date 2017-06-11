from peewee import *
from playhouse.hybrid import hybrid_method
from playhouse.hybrid import hybrid_property
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase


db = database_initializer.get_in_memory_database()

class BaseModel(Model):
    class Meta:
        database = db

class Interval(BaseModel):
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
        return fn.abs(cls.length) / 2


class Person(BaseModel):
    first = CharField()
    last = CharField()

    @hybrid_property
    def full_name(self):
        return self.first + ' ' + self.last


class TestHybrid(ModelTestCase):
    requires = [Interval, Person]

    def setUp(self):
        super(TestHybrid, self).setUp()
        intervals = (
            (1, 5),
            (2, 6),
            (3, 5),
            (2, 5))
        for start, end in intervals:
            Interval.create(start=start, end=end)

    def test_hybrid_property(self):
        query = Interval.select().where(Interval.length == 4)
        sql, params = query.sql()
        self.assertEqual(sql, (
            'SELECT "t1"."id", "t1"."start", "t1"."end" '
            'FROM "interval" AS t1 '
            'WHERE (("t1"."end" - "t1"."start") = ?)'))
        self.assertEqual(params, [4])

        results = sorted(
            (interval.start, interval.end)
            for interval in query)
        self.assertEqual(results, [(1, 5), (2, 6)])

        lengths = [4, 4, 2, 3]
        query = Interval.select().order_by(Interval.id)
        actuals = [interval.length for interval in query]
        self.assertEqual(actuals, lengths)

    def test_hybrid_method(self):
        query = Interval.select().where(Interval.contains(2))
        sql, params = query.sql()
        self.assertEqual(sql, (
            'SELECT "t1"."id", "t1"."start", "t1"."end" '
            'FROM "interval" AS t1 '
            'WHERE (("t1"."start" <= ?) AND ("t1"."end" > ?))'))
        self.assertEqual(params, [2, 2])

        results = sorted(
            (interval.start, interval.end)
            for interval in query)
        self.assertEqual(results, [(1, 5), (2, 5), (2, 6)])

        contains = [True, True, False, True]
        query = Interval.select().order_by(Interval.id)
        actuals = [interval.contains(2) for interval in query]
        self.assertEqual(contains, actuals)

    def test_separate_expr(self):
        query = Interval.select().where(Interval.radius == 2)
        sql, params = query.sql()
        self.assertEqual(sql, (
            'SELECT "t1"."id", "t1"."start", "t1"."end" '
            'FROM "interval" AS t1 '
            'WHERE ((abs("t1"."end" - "t1"."start") / ?) = ?)'))
        self.assertEqual(params, [2, 2])

        results = sorted(
            (interval.start, interval.end)
            for interval in query)
        self.assertEqual(results, [(1, 5), (2, 6)])

        radii = [2, 2, 1, 1]
        query = Interval.select().order_by(Interval.id)
        actuals = [interval.radius for interval in query]
        self.assertEqual(actuals, radii)

    def test_string_fields(self):
        huey = Person.create(first='huey', last='cat')
        zaizee = Person.create(first='zaizee', last='kitty')

        self.assertEqual(huey.full_name, 'huey cat')
        self.assertEqual(zaizee.full_name, 'zaizee kitty')

        query = Person.select().where(Person.full_name == 'zaizee kitty')
        zaizee_db = query.get()
        self.assertEqual(zaizee_db, zaizee)

        query = Person.select().where(Person.full_name.startswith('huey c'))
        huey_db = query.get()
        self.assertEqual(huey_db, huey)
