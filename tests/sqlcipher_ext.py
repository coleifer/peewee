import datetime
import os
from hashlib import sha1

from peewee import DatabaseError
from playhouse.sqlcipher_ext import *
from playhouse.sqlite_ext import *

from .base import ModelTestCase
from .base import TestModel


PASSPHRASE = 'testing sqlcipher'
PRAGMAS = {'kdf_iter': 10}  # Much faster for testing. Totally unsafe.
db = SqlCipherDatabase('peewee_test.dbc', passphrase=PASSPHRASE,
                       pragmas=PRAGMAS)
ext_db = SqlCipherExtDatabase('peewee_test.dbx', passphrase=PASSPHRASE,
                              pragmas=PRAGMAS)


@ext_db.func('shazam')
def shazam(s):
    return sha1((s or '').encode('utf-8')).hexdigest()[:5]


class Thing(TestModel):
    name = CharField()


class FTSNote(FTSModel, TestModel):
    content = TextField()


class Note(TestModel):
    content = TextField()
    timestamp = DateTimeField(default=datetime.datetime.now)


class CleanUpModelTestCase(ModelTestCase):
    def tearDown(self):
        super(CleanUpModelTestCase, self).tearDown()
        if os.path.exists(self.database.database):
            os.unlink(self.database.database)


class SqlCipherTestCase(CleanUpModelTestCase):
    database = db
    requires = [Thing]

    def test_good_and_bad_passphrases(self):
        things = ('t1', 't2', 't3')
        for thing in things:
            Thing.create(name=thing)

        # Try to open db with wrong passphrase
        bad_db = SqlCipherDatabase(db.database, passphrase='wrong passphrase')
        self.assertRaises(DatabaseError, bad_db.get_tables)

        # Assert that we can still access the data with the good passphrase.
        query = Thing.select().order_by(Thing.name)
        self.assertEqual([t.name for t in query], ['t1', 't2', 't3'])

    def test_rekey(self):
        things = ('t1', 't2', 't3')
        for thing in things:
            Thing.create(name=thing)

        self.database.rekey('a new passphrase')

        db2 = SqlCipherDatabase(db.database, passphrase='a new passphrase',
                                pragmas=PRAGMAS)
        cursor = db2.execute_sql('select name from thing order by name;')
        self.assertEqual([name for name, in cursor], ['t1', 't2', 't3'])

        query = Thing.select().order_by(Thing.name)
        self.assertEqual([t.name for t in query], ['t1', 't2', 't3'])

        self.database.close()
        self.database.connect()

        query = Thing.select().order_by(Thing.name)
        self.assertEqual([t.name for t in query], ['t1', 't2', 't3'])

        # Re-set to the original passphrase.
        self.database.rekey(PASSPHRASE)

    def test_empty_passphrase(self):
        db = SqlCipherDatabase(':memory:')

        class CM(TestModel):
            data = TextField()
            class Meta:
                database = db

        db.connect()
        db.create_tables([CM])
        cm = CM.create(data='foo')
        cm_db = CM.get(CM.data == 'foo')
        self.assertEqual(cm_db.id, cm.id)
        self.assertEqual(cm_db.data, 'foo')


config_db = SqlCipherDatabase('peewee_test.dbc', pragmas={
    'kdf_iter': 1234,
    'cipher_page_size': 8192}, passphrase=PASSPHRASE)

class TestSqlCipherConfiguration(CleanUpModelTestCase):
    database = config_db

    def test_configuration_via_pragma(self):
        # Write some data so the database file is created.
        self.database.execute_sql('create table foo (data TEXT)')
        self.database.close()

        self.database.connect()
        self.assertEqual(int(self.database.pragma('kdf_iter')), 1234)
        self.assertEqual(int(self.database.pragma('cipher_page_size')), 8192)
        self.assertTrue('foo' in self.database.get_tables())


class SqlCipherExtTestCase(CleanUpModelTestCase):
    database = ext_db
    requires = [Note]

    def setUp(self):
        super(SqlCipherExtTestCase, self).setUp()
        FTSNote._meta.database = ext_db
        FTSNote.drop_table(True)
        FTSNote.create_table(tokenize='porter', content=Note.content)

    def tearDown(self):
        FTSNote.drop_table(True)
        super(SqlCipherExtTestCase, self).tearDown()

    def test_fts(self):
        strings = [
            'python and peewee for working with databases',
            'relational databases are the best',
            'sqlite is the best relational database',
            'sqlcipher is a cool database extension']
        for s in strings:
            Note.create(content=s)
        FTSNote.rebuild()

        query = (FTSNote
                 .select(FTSNote, FTSNote.rank().alias('score'))
                 .where(FTSNote.match('relational databases'))
                 .order_by(SQL('score').desc()))
        notes = [note.content for note in query]
        self.assertEqual(notes, [
            'relational databases are the best',
            'sqlite is the best relational database'])

        alt_conn = SqliteDatabase(ext_db.database)
        self.assertRaises(
            DatabaseError,
            alt_conn.execute_sql,
            'SELECT * FROM "%s"' % (FTSNote._meta.table_name))

    def test_func(self):
        Note.create(content='hello')
        Note.create(content='baz')
        Note.create(content='nug')

        query = (Note
                 .select(Note.content, fn.shazam(Note.content).alias('shz'))
                 .order_by(Note.id)
                 .dicts())
        results = list(query)
        self.assertEqual(results, [
            {'content': 'hello', 'shz': 'aaf4c'},
            {'content': 'baz', 'shz': 'bbe96'},
            {'content': 'nug', 'shz': '52616'},
        ])
