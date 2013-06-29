import unittest

from peewee import *
from playhouse.proxy import Proxy


class ProxyTestCase(unittest.TestCase):
    def test_proxy(self):
        class A(object):
            def foo(self):
                return 'foo'

        a = Proxy()
        def raise_error():
            a.foo()
        self.assertRaises(AttributeError, raise_error)

        a.initialize(A())
        self.assertEqual(a.foo(), 'foo')

    def test_proxy_database(self):
        database_proxy = Proxy()

        class DummyModel(Model):
            test_field = CharField()
            class Meta:
                database = database_proxy

        # Un-initialized will raise an AttributeError.
        self.assertRaises(AttributeError, DummyModel.create_table)

        # Initialize the object.
        database_proxy.initialize(SqliteDatabase(':memory:'))

        # Do some queries, verify it is working.
        DummyModel.create_table()
        DummyModel.create(test_field='foo')
        self.assertEqual(DummyModel.get().test_field, 'foo')
        DummyModel.drop_table()

