import hashlib
import itertools
import unittest

from playhouse.sqlite_ext import *
from playhouse.sqlite_aggregates import *


db = SqliteExtDatabase(':memory:')

db.register_aggregate(Variance)
db.register_aggregate(StdDev)
db.register_aggregate(CSV)
db.register_aggregate(Mode)
db.register_aggregate(MD5Sum)
db.register_aggregate(SHA1Sum)
db.register_aggregate(First)
db.register_aggregate(Last)

class Point(Model):
    x = IntegerField()
    y = IntegerField()
    data = CharField()

    class Meta:
        database = db

class TestSqliteAggregates(unittest.TestCase):
    test_values = [1, 1, 1, 2, 3, 3, 3, 3, 4]
    test_strings = ['foo', 'bar', 'baz']

    def setUp(self):
        Point.drop_table(True)
        Point.create_table()

        cycle = itertools.cycle(self.test_strings)
        for val, data in zip(self.test_values, cycle):
            Point.create(
                x=val,
                y=val * val,
                data=data)

    def test_variance_stddev(self):
        variance = Point.select(fn.Variance(Point.x)).scalar()
        self.assertEqual(round(variance, 3), 1.111)
        stddev = Point.select(fn.StdDev(Point.x)).scalar()
        self.assertEqual(round(stddev, 3), 1.054)

    def test_csv(self):
        data = Point.select(fn.CSV(Point.data)).scalar()
        self.assertEqual(data, 'foo,bar,baz,foo,bar,baz,foo,bar,baz')

        data = Point.select(fn.CSV(Point.x, Point.y)).scalar()
        self.assertEqual(data, '1,1,1,1,1,1,2,4,3,9,3,9,3,9,3,9,4,16')

    def test_mode(self):
        mode = Point.select(fn.Mode(Point.x)).scalar()
        self.assertEqual(mode, 3)

    def test_checksums(self):
        md5sum = Point.select(fn.MD5Sum(Point.data)).scalar()
        self.assertEqual(md5sum, hashlib.md5('foobarbaz' * 3).hexdigest())

        sha1sum = Point.select(fn.Sha1Sum(Point.data)).scalar()
        self.assertEqual(sha1sum, hashlib.sha1('foobarbaz' * 3).hexdigest())

    def test_first_last(self):
        first, last = (Point
                       .select(
                           fn.First(Point.x),
                           fn.Last(Point.y))
                       .order_by(Point.id)
                       .scalar(as_tuple=True))
        self.assertEqual(first, 1)
        self.assertEqual(last, 16)

    def test_subset_aggregate(self):
        subquery = Point.select(Point.x).order_by(Point.id).limit(3)
        csv = Point.select(fn.CSV(subquery.c.x)).from_(subquery).scalar()
        self.assertEqual(csv, '1,1,1')

        subquery = subquery.order_by(Point.id.desc())
        csv = Point.select(fn.CSV(subquery.c.x)).from_(subquery).scalar()
        self.assertEqual(csv, '4,3,3')
