from peewee import *
from playhouse.postgres_ext import *

from .base import ModelTestCase
from .base import TestModel


db = PostgresqlExtDatabase('peewee_test')


class HStoreModel(TestModel):
    name = CharField()
    data = HStoreField()


class TestHStoreField(ModelTestCase):
    database = db
    requires = [HStoreModel]

    def setUp(self):
        super(TestHStoreField, self).setUp()
        self.t1 = None
        self.t2 = None

    def create(self):
        self.t1 = HStoreModel.create(name='t1', data={'k1': 'v1', 'k2': 'v2'})
        self.t2 = HStoreModel.create(name='t2', data={'k2': 'v2', 'k3': 'v3'})

    def by_name(self, name):
        return HStoreModel.get(HStoreModel.name == name).data

    def test_hstore_storage(self):
        self.create()
        self.assertEqual(self.by_name('t1'), {'k1': 'v1', 'k2': 'v2'})
        self.assertEqual(self.by_name('t2'), {'k2': 'v2', 'k3': 'v3'})

        self.t1.data = {'k4': 'v4'}
        self.t1.save()
        self.assertEqual(self.by_name('t1'), {'k4': 'v4'})

        HStoreModel.create(name='t3', data={})
        self.assertEqual(self.by_name('t3'), {})
