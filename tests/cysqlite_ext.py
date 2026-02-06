import glob
import os

import cysqlite

from peewee import *
from playhouse.cysqlite_ext import *

from .base import BaseTestCase
from .base import DatabaseTestCase
from .base import TestModel
from .base import db_loader
from .base import skip_unless


database = CySqliteDatabase('peewee_test.db', timeout=100)


class CyDatabaseTestCase(DatabaseTestCase):
    database = database

    def tearDown(self):
        super(CyDatabaseTestCase, self).tearDown()
        for filename in glob.glob(self.database.database + '*'):
            os.unlink(filename)

    def execute(self, sql, *params):
        return self.database.execute_sql(sql, params)


class TestCSqliteHelpers(CyDatabaseTestCase):
    def test_autocommit(self):
        self.assertTrue(self.database.autocommit)
        self.database.begin()
        self.assertFalse(self.database.autocommit)
        self.database.rollback()
        self.assertTrue(self.database.autocommit)

    def test_commit_hook(self):
        state = {}

        @self.database.on_commit
        def on_commit():
            state.setdefault('commits', 0)
            state['commits'] += 1

        self.execute('create table register (value text)')
        self.assertEqual(state['commits'], 1)

        # Check hook is preserved.
        self.database.close()
        self.database.connect()

        self.execute('insert into register (value) values (?), (?)',
                     'foo', 'bar')
        self.assertEqual(state['commits'], 2)

        curs = self.execute('select * from register order by value;')
        results = curs.fetchall()
        self.assertEqual([tuple(r) for r in results], [('bar',), ('foo',)])

        self.assertEqual(state['commits'], 2)

    def test_rollback_hook(self):
        state = {}

        @self.database.on_rollback
        def on_rollback():
            state.setdefault('rollbacks', 0)
            state['rollbacks'] += 1

        self.execute('create table register (value text);')
        self.assertEqual(state, {})

        # Check hook is preserved.
        self.database.close()
        self.database.connect()

        self.database.begin()
        self.execute('insert into register (value) values (?)', 'test')
        self.database.rollback()
        self.assertEqual(state, {'rollbacks': 1})

        curs = self.execute('select * from register;')
        self.assertEqual(curs.fetchall(), [])

    def test_update_hook(self):
        state = []

        @self.database.on_update
        def on_update(query, db, table, rowid):
            state.append((query, db, table, rowid))

        self.execute('create table register (value text)')
        self.execute('insert into register (value) values (?), (?)',
                     'foo', 'bar')

        self.assertEqual(state, [
            ('INSERT', 'main', 'register', 1),
            ('INSERT', 'main', 'register', 2)])

        # Check hook is preserved.
        self.database.close()
        self.database.connect()

        self.execute('update register set value = ? where rowid = ?', 'baz', 1)
        self.assertEqual(state, [
            ('INSERT', 'main', 'register', 1),
            ('INSERT', 'main', 'register', 2),
            ('UPDATE', 'main', 'register', 1)])

        self.execute('delete from register where rowid=?;', 2)
        self.assertEqual(state, [
            ('INSERT', 'main', 'register', 1),
            ('INSERT', 'main', 'register', 2),
            ('UPDATE', 'main', 'register', 1),
            ('DELETE', 'main', 'register', 2)])

    def test_properties(self):
        self.assertTrue(self.database.cache_used is not None)


class TestBackup(CyDatabaseTestCase):
    backup_filenames = set(('test_backup.db', 'test_backup1.db',
                            'test_backup2.db'))

    def tearDown(self):
        super(TestBackup, self).tearDown()
        for backup_filename in self.backup_filenames:
            if os.path.exists(backup_filename):
                os.unlink(backup_filename)

    def _populate_test_data(self, nrows=100, db=None):
        db = self.database if db is None else db
        db.execute_sql('CREATE TABLE register (id INTEGER NOT NULL PRIMARY KEY'
                       ', value INTEGER NOT NULL)')
        with db.atomic():
            for i in range(nrows):
                db.execute_sql('INSERT INTO register (value) VALUES (?)', (i,))

    def test_backup(self):
        self._populate_test_data()

        # Back-up to an in-memory database and verify contents.
        other_db = CySqliteDatabase(':memory:')
        self.database.backup(other_db)
        cursor = other_db.execute_sql('SELECT value FROM register ORDER BY '
                                      'value;')
        self.assertEqual([val for val, in cursor.fetchall()], list(range(100)))
        other_db.close()

    def test_backup_preserve_pagesize(self):
        db1 = CySqliteDatabase('test_backup1.db')
        with db1.connection_context():
            db1.page_size = 8192
            self._populate_test_data(db=db1)

        db1.connect()
        self.assertEqual(db1.page_size, 8192)

        db2 = CySqliteDatabase('test_backup2.db')
        db1.backup(db2)
        self.assertEqual(db2.page_size, 8192)
        nrows, = db2.execute_sql('select count(*) from register;').fetchone()
        self.assertEqual(nrows, 100)

    def test_backup_to_file(self):
        self._populate_test_data()

        self.database.backup_to_file('test_backup.db')
        backup_db = CySqliteDatabase('test_backup.db')
        cursor = backup_db.execute_sql('SELECT value FROM register ORDER BY '
                                       'value;')
        self.assertEqual([val for val, in cursor.fetchall()], list(range(100)))
        backup_db.close()

    def test_backup_progress(self):
        self._populate_test_data()

        accum = []
        def progress(remaining, total, is_done):
            accum.append((remaining, total, is_done))

        other_db = CySqliteDatabase(':memory:')
        self.database.backup(other_db, pages=1, progress=progress)
        self.assertTrue(len(accum) > 0)

        sql = 'select value from register order by value;'
        self.assertEqual([r for r, in other_db.execute_sql(sql)],
                         list(range(100)))
        other_db.close()

    def test_backup_progress_error(self):
        self._populate_test_data()

        def broken_progress(remaining, total, is_done):
            raise ValueError('broken')

        other_db = CySqliteDatabase(':memory:')
        self.assertRaises(ValueError, self.database.backup, other_db,
                          progress=broken_progress)
        other_db.close()


class DataTypes(cysqlite.TableFunction):
    columns = ('key', 'value')
    params = ()
    name = 'data_types'

    def initialize(self):
        self.values = (
            None,
            1,
            2.,
            u'unicode str',
            b'byte str',
            False,
            True)
        self.idx = 0
        self.n = len(self.values)

    def iterate(self, idx):
        if idx < self.n:
            return ('k%s' % idx, self.values[idx])
        raise StopIteration


@skip_unless(cysqlite.sqlite_version_info >= (3, 9), 'requires sqlite >= 3.9')
class TestDataTypesTableFunction(CyDatabaseTestCase):
    database = db_loader('cysqlite')

    def test_data_types_table_function(self):
        self.database.register_table_function(DataTypes)
        for _ in range(2):
            cursor = self.database.execute_sql('SELECT key, value FROM '
                                               'data_types() ORDER BY key')
            self.assertEqual(cursor.fetchall(), [
                ('k0', None),
                ('k1', 1),
                ('k2', 2.),
                ('k3', u'unicode str'),
                ('k4', b'byte str'),
                ('k5', 0),
                ('k6', 1),
            ])

            # Ensure table re-registered after close.
            self.database.close()
            self.database.connect()
