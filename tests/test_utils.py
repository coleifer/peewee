import functools

from .base import ModelTestCase
from .base import TestModel

from peewee import *
from playhouse.test_utils import assert_query_count
from playhouse.test_utils import count_queries


class Data(TestModel):
    key = CharField()

    class Meta:
        order_by = ('key',)

class DataItem(TestModel):
    data = ForeignKeyField(Data, backref='items')
    value = CharField()

    class Meta:
        order_by = ('value',)


class TestQueryCounter(ModelTestCase):
    requires = [DataItem, Data]

    def test_count(self):
        with count_queries() as count:
            Data.create(key='k1')
            Data.create(key='k2')

        self.assertEqual(count.count, 2)

        with count_queries() as count:
            items = [item.key for item in Data.select().order_by(Data.key)]
            self.assertEqual(items, ['k1', 'k2'])

            Data.get(Data.key == 'k1')
            Data.get(Data.key == 'k2')

        self.assertEqual(count.count, 3)

    def test_only_select(self):
        with count_queries(only_select=True) as count:
            for i in range(10):
                Data.create(key=str(i))

            items = [item.key for item in Data.select()]
            Data.get(Data.key == '0')
            Data.get(Data.key == '9')

            Data.delete().where(
                Data.key << ['1', '3', '5', '7', '9']).execute()

            items = [item.key for item in Data.select().order_by(Data.key)]
            self.assertEqual(items, ['0', '2', '4', '6', '8'])

        self.assertEqual(count.count, 4)

    def test_assert_query_count_decorator(self):
        @assert_query_count(2)
        def will_fail_under():
            Data.create(key='x')

        @assert_query_count(2)
        def will_fail_over():
            for i in range(3):
                Data.create(key=str(i))

        @assert_query_count(4)
        def will_succeed():
            for i in range(4):
                Data.create(key=str(i + 100))

        will_succeed()
        self.assertRaises(AssertionError, will_fail_under)
        self.assertRaises(AssertionError, will_fail_over)

    def test_assert_query_count_ctx_mgr(self):
        with assert_query_count(3):
            for i in range(3):
                Data.create(key=str(i))

        def will_fail():
            with assert_query_count(2):
                Data.create(key='x')

        self.assertRaises(AssertionError, will_fail)

    @assert_query_count(3)
    def test_only_three(self):
        for i in range(3):
            Data.create(key=str(i))
