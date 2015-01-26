import datetime
from hashlib import sha1

from peewee import DatabaseError
from playhouse.sqlcipher_ext import *
from playhouse.sqlite_ext import *
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase


db = database_initializer.get_database('sqlcipher')
ext_db = database_initializer.get_database(
    'sqlcipher_ext',
    passphrase='testing sqlcipher')


class BaseModel(Model):
    class Meta:
        database = db

class Thing(BaseModel):
    name = CharField()

@ext_db.func('shazam')
def shazam(s):
    return sha1(s or '').hexdigest()[:5]

class ExtModel(Model):
    class Meta:
        database = ext_db

class FTSNote(FTSModel):
    content = TextField()

    class Meta:
        database = ext_db

class Note(ExtModel):
    content = TextField()
    timestamp = DateTimeField(default=datetime.datetime.now)


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


class SqlCipherExtTestCase(ModelTestCase):
    requires = [Note]

    def setUp(self):
        super(SqlCipherExtTestCase, self).setUp()
        FTSNote.drop_table(True)
        FTSNote.create_table(tokenize='porter', content=Note.content)

    def tearDown(self):
        super(SqlCipherExtTestCase, self).tearDown()
        FTSNote.drop_table(True)

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
            'SELECT * FROM "%s"' % (FTSNote._meta.db_table))

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
