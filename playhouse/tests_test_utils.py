import functools
import unittest

from peewee import *
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

class TestTestDatabaseCtxMgr(unittest.TestCase):
    def setUp(self):
        Data.create_table()
        DataItem.create_table()
        a = Data.create(key='a')
        b = Data.create(key='b')
        DataItem.create(data=a, value='a1')
        DataItem.create(data=a, value='a2')
        DataItem.create(data=b, value='b1')

    def tearDown(self):
        # Drop tables from db1.
        DataItem.drop_table()
        Data.drop_table()

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
