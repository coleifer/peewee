import functools
import unittest

from peewee import *
from playhouse.test_utils import assert_query_count
from playhouse.test_utils import count_queries
from playhouse.test_utils import test_database


db1 = SqliteDatabase(':memory:')
db1._flag = 'db1'
db2 = SqliteDatabase(':memory:')
db2._flag = 'db2'

class BaseModel(Model):
    class Meta:
        database = db1

class Data(BaseModel):
    key = CharField()

    class Meta:
        order_by = ('key',)

class DataItem(BaseModel):
    data = ForeignKeyField(Data, related_name='items')
    value = CharField()

    class Meta:
        order_by = ('value',)

class BaseTestCase(unittest.TestCase):
    def setUp(self):
        DataItem.drop_table(True)
        Data.drop_table(True)
        Data.create_table()
        DataItem.create_table()

    def tearDown(self):
        DataItem.drop_table()
        Data.drop_table()

class TestTestDatabaseCtxMgr(BaseTestCase):
    def setUp(self):
        super(TestTestDatabaseCtxMgr, self).setUp()
        a = Data.create(key='a')
        b = Data.create(key='b')
        DataItem.create(data=a, value='a1')
        DataItem.create(data=a, value='a2')
        DataItem.create(data=b, value='b1')

    def tearDown(self):
        super(TestTestDatabaseCtxMgr, self).tearDown()
        # Drop tables from db2.
        db2.execute_sql('drop table if exists dataitem;')
        db2.execute_sql('drop table if exists data;')

    def assertUsing(self, db):
        self.assertEqual(Data._meta.database._flag, db)
        self.assertEqual(DataItem._meta.database._flag, db)

    def case_wrapper(fn):
        @functools.wraps(fn)
        def inner(self):
            self.assertUsing('db1')
            return fn(self)
        return inner

    @case_wrapper
    def test_no_options(self):
        with test_database(db2, (Data, DataItem), create_tables=True):
            self.assertUsing('db2')

            # Tables were created automatically.
            self.assertTrue(Data.table_exists())
            self.assertTrue(DataItem.table_exists())

            # There are no rows in the db.
            self.assertEqual(Data.select().count(), 0)
            self.assertEqual(DataItem.select().count(), 0)

            # Verify we can create items in the db.
            d = Data.create(key='c')
            self.assertEqual(Data.select().count(), 1)

        self.assertUsing('db1')
        # Ensure that no changes were made to db1.
        self.assertEqual([x.key for x in Data.select()], ['a', 'b'])

        # Ensure the tables were dropped.
        res = db2.execute_sql('select * from sqlite_master')
        self.assertEqual(res.fetchall(), [])

    @case_wrapper
    def test_explicit_create_tables(self):
        # Retrieve a reference to a model in db1 and verify that it
        # has the correct items.
        a = Data.get(Data.key == 'a')
        self.assertEqual([x.value for x in a.items], ['a1', 'a2'])

        with test_database(db2, (Data, DataItem), create_tables=False):
            self.assertUsing('db2')

            # Table hasn't been created.
            self.assertFalse(Data.table_exists())
            self.assertFalse(DataItem.table_exists())

        self.assertUsing('db1')

        # We can still fetch the related items for object 'a'.
        self.assertEqual([x.value for x in a.items], ['a1', 'a2'])

    @case_wrapper
    def test_exception_handling(self):
        def raise_exc():
            with test_database(db2, (Data, DataItem)):
                self.assertUsing('db2')
                c = Data.create(key='c')
                # This will raise Data.DoesNotExist.
                Data.get(Data.key == 'a')

        # Ensure the exception is raised by the ctx mgr.
        self.assertRaises(Data.DoesNotExist, raise_exc)
        self.assertUsing('db1')

        # Ensure that the tables in db2 are removed.
        res = db2.execute_sql('select * from sqlite_master')
        self.assertEqual(res.fetchall(), [])

        # Ensure the data in db1 is intact.
        self.assertEqual([x.key for x in Data.select()], ['a', 'b'])

    @case_wrapper
    def test_exception_handling_explicit_cd(self):
        def raise_exc():
            with test_database(db2, (Data, DataItem), create_tables=False):
                self.assertUsing('db2')
                Data.create_table()
                c = Data.create(key='c')
                # This will raise Data.DoesNotExist.
                Data.get(Data.key == 'a')

        self.assertRaises(Data.DoesNotExist, raise_exc)
        self.assertUsing('db1')

        # Ensure that the tables in db2 are still present.
        res = db2.execute_sql('select key from data;')
        self.assertEqual(res.fetchall(), [('c',)])

        # Ensure the data in db1 is intact.
        self.assertEqual([x.key for x in Data.select()], ['a', 'b'])

    @case_wrapper
    def test_mismatch_models(self):
        a = Data.get(Data.key == 'a')
        with test_database(db2, (Data,)):
            d2_id = Data.insert(id=a.id, key='c').execute()
            c = Data.get(Data.id == d2_id)

            # Mismatches work and the queries are handled at the class
            # level, so the Data returned from the DataItems will
            # be from db2.
            self.assertEqual([x.value for x in c.items], ['a1', 'a2'])
            for item in c.items:
                self.assertEqual(item.data.key, 'c')


class TestQueryCounter(BaseTestCase):
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
