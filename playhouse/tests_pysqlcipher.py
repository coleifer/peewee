import os
import unittest

from playhouse.sqlcipher_ext import *

db = SqlCipherDatabase('sqlciphertest.db',
    passphrase='thisisthegoodpassphrase')

class BaseModel(Model):
    class Meta:
        database = db

class Thing(BaseModel):
    name = CharField()

class SqlCipherTestCase(unittest.TestCase):
    def setUp(self):
        try:
            os.remove('sqlciphertest.db')
        except OSError:
            pass
    def test_good_and_bad_passphrases(self):
        # This will create the database, because setUp() has deleted
        # the file. This means it should be encrypted with
        # 'thisisthegoodpassphrase'
        Thing.create_table()
        things = ('t1', 't2', 't3')
        for thing in things:
            Thing.create(name=thing)

        # Try to open db with wrong passphrase
        secure = False
        bad_db = SqlCipherDatabase('sqlciphertest.db',
            passphrase='some other passphrase')
        try:
            bad_db.get_tables()
        except DatabaseError as e:
            if e.message=='file is encrypted or is not a database':
                secure = True  # Got the vague "probably bad passphrase" error.
        self.assertTrue(secure)

        # Assert that we can still access the data with the good passphrase.
        self.assertEqual([t.name for t in Thing.select()], ['t1', 't2', 't3'])
