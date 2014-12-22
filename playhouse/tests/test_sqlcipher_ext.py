from playhouse.sqlcipher_ext import *
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase


db = database_initializer.get_database('sqlcipher')


class BaseModel(Model):
    class Meta:
        database = db

class Thing(BaseModel):
    name = CharField()

class SqlCipherTestCase(ModelTestCase):
    requires = [Thing]

    def test_good_and_bad_passphrases(self):
        things = ('t1', 't2', 't3')
        for thing in things:
            Thing.create(name=thing)

        # Try to open db with wrong passphrase
        secure = False
        bad_db = database_initializer.get_database(
            'sqlcipher',
            passphrase='wrong passphrase')

        self.assertRaises(DatabaseError, bad_db.get_tables)

        # Assert that we can still access the data with the good passphrase.
        query = Thing.select().order_by(Thing.name)
        self.assertEqual([t.name for t in query], ['t1', 't2', 't3'])

    def test_passphrase_length(self):
        db = database_initializer.get_database('sqlcipher', passphrase='x')
        self.assertRaises(ImproperlyConfigured, db.connect)

    def test_kdf_iter(self):
        db = database_initializer.get_database('sqlcipher', kdf_iter=9999)
        self.assertRaises(ImproperlyConfigured, db.connect)
