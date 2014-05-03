import unittest

from playhouse.sqlcipher_ext import *

DB_FILE = 'test_sqlcipher.db'
PASSPHRASE = 'test1234'
db = SqlCipherDatabase(DB_FILE, passphrase=PASSPHRASE)


class BaseModel(Model):
    class Meta:
        database = db

class Thing(BaseModel):
    name = CharField()

class SqlCipherTestCase(unittest.TestCase):
    def setUp(self):
        Thing.drop_table(True)
        Thing.create_table()

    def test_good_and_bad_passphrases(self):
        things = ('t1', 't2', 't3')
        for thing in things:
            Thing.create(name=thing)

        # Try to open db with wrong passphrase
        secure = False
        bad_db = SqlCipherDatabase(DB_FILE, passphrase=PASSPHRASE + 'x')

        self.assertRaises(DatabaseError, bad_db.get_tables)

        # Assert that we can still access the data with the good passphrase.
        query = Thing.select().order_by(Thing.name)
        self.assertEqual([t.name for t in query], ['t1', 't2', 't3'])

    def test_passphrase_length(self):
        db = SqlCipherDatabase(DB_FILE, passphrase='x')
        self.assertRaises(ImproperlyConfigured, db.connect)

    def test_kdf_iter(self):
        db = SqlCipherDatabase(DB_FILE, passphrase=PASSPHRASE, kdf_iter=9999)
        self.assertRaises(ImproperlyConfigured, db.connect)
