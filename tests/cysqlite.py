import os

from peewee import *
from playhouse.sqlite_ext import CYTHON_SQLITE_EXTENSIONS
from playhouse.sqlite_ext import *
from playhouse._sqlite_ext import BloomFilter

from .base import BaseTestCase
from .base import DatabaseTestCase


database = CSqliteExtDatabase('peewee_test.db', timeout=100,
                              hash_functions=1)


class CyDatabaseTestCase(DatabaseTestCase):
    database = database

    def tearDown(self):
        super(CyDatabaseTestCase, self).tearDown()
        if os.path.exists(self.database.database):
            os.unlink(self.database.database)

    def execute(self, sql, *params):
        return self.database.execute_sql(sql, params, commit=False)


class TestCySqliteHelpers(CyDatabaseTestCase):
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


HUser = Table('users', ('id', 'username'))


class TestHashFunctions(CyDatabaseTestCase):
    database = database

    def setUp(self):
        super(TestHashFunctions, self).setUp()
        self.database.execute_sql(
            'create table users (id integer not null primary key, '
            'username text not null)')

    def test_md5(self):
        for username in ('charlie', 'huey', 'zaizee'):
            HUser.insert({HUser.username: username}).execute(self.database)

        query = (HUser
                 .select(HUser.username,
                         fn.SUBSTR(fn.SHA1(HUser.username), 1, 6).alias('sha'))
                 .order_by(HUser.username)
                 .tuples()
                 .execute(self.database))

        self.assertEqual(query[:], [
            ('charlie', 'd8cd10'),
            ('huey', '89b31a'),
            ('zaizee', 'b4dcf9')])


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
        other_db = CSqliteExtDatabase(':memory:')
        self.database.backup(other_db)
        cursor = other_db.execute_sql('SELECT value FROM register ORDER BY '
                                      'value;')
        self.assertEqual([val for val, in cursor.fetchall()], list(range(100)))
        other_db.close()

    def test_backup_preserve_pagesize(self):
        db1 = CSqliteExtDatabase('test_backup1.db')
        with db1.connection_context():
            db1.page_size = 8192
            self._populate_test_data(db=db1)

        db1.connect()
        self.assertEqual(db1.page_size, 8192)

        db2 = CSqliteExtDatabase('test_backup2.db')
        db1.backup(db2)
        self.assertEqual(db2.page_size, 8192)
        nrows, = db2.execute_sql('select count(*) from register;').fetchone()
        self.assertEqual(nrows, 100)

    def test_backup_to_file(self):
        self._populate_test_data()

        self.database.backup_to_file('test_backup.db')
        backup_db = CSqliteExtDatabase('test_backup.db')
        cursor = backup_db.execute_sql('SELECT value FROM register ORDER BY '
                                       'value;')
        self.assertEqual([val for val, in cursor.fetchall()], list(range(100)))
        backup_db.close()

    def test_backup_progress(self):
        self._populate_test_data()

        accum = []
        def progress(remaining, total, is_done):
            accum.append((remaining, total, is_done))

        other_db = CSqliteExtDatabase(':memory:')
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

        other_db = CSqliteExtDatabase(':memory:')
        self.assertRaises(ValueError, self.database.backup, other_db,
                          progress=broken_progress)
        other_db.close()


class TestBlob(CyDatabaseTestCase):
    def setUp(self):
        super(TestBlob, self).setUp()
        self.Register = Table('register', ('id', 'data'))
        self.execute('CREATE TABLE register (id INTEGER NOT NULL PRIMARY KEY, '
                     'data BLOB NOT NULL)')

    def create_blob_row(self, nbytes):
        Register = self.Register.bind(self.database)
        Register.insert({Register.data: ZeroBlob(nbytes)}).execute()
        return self.database.last_insert_rowid

    def test_blob(self):
        rowid1024 = self.create_blob_row(1024)
        rowid16 = self.create_blob_row(16)

        blob = Blob(self.database, 'register', 'data', rowid1024)
        self.assertEqual(len(blob), 1024)

        blob.write(b'x' * 1022)
        blob.write(b'zz')
        blob.seek(1020)
        self.assertEqual(blob.tell(), 1020)

        data = blob.read(3)
        self.assertEqual(data, b'xxz')
        self.assertEqual(blob.read(), b'z')
        self.assertEqual(blob.read(), b'')

        blob.seek(-10, 2)
        self.assertEqual(blob.tell(), 1014)
        self.assertEqual(blob.read(), b'xxxxxxxxzz')

        blob.reopen(rowid16)
        self.assertEqual(blob.tell(), 0)
        self.assertEqual(len(blob), 16)

        blob.write(b'x' * 15)
        self.assertEqual(blob.tell(), 15)

    def test_blob_exceed_size(self):
        rowid = self.create_blob_row(16)

        blob = self.database.blob_open('register', 'data', rowid)
        with self.assertRaisesCtx(ValueError):
            blob.seek(17, 0)

        with self.assertRaisesCtx(ValueError):
            blob.write(b'x' * 17)

        blob.write(b'x' * 16)
        self.assertEqual(blob.tell(), 16)
        blob.seek(0)
        data = blob.read(17)  # Attempting to read more data is OK.
        self.assertEqual(data, b'x' * 16)
        blob.close()

    def test_blob_errors_opening(self):
        rowid = self.create_blob_row(4)

        with self.assertRaisesCtx(OperationalError):
            blob = self.database.blob_open('register', 'data', rowid + 1)

        with self.assertRaisesCtx(OperationalError):
            blob = self.database.blob_open('register', 'missing', rowid)

        with self.assertRaisesCtx(OperationalError):
            blob = self.database.blob_open('missing', 'data', rowid)

    def test_blob_operating_on_closed(self):
        rowid = self.create_blob_row(4)
        blob = self.database.blob_open('register', 'data', rowid)
        self.assertEqual(len(blob), 4)
        blob.close()

        with self.assertRaisesCtx(InterfaceError):
            len(blob)

        self.assertRaises(InterfaceError, blob.read)
        self.assertRaises(InterfaceError, blob.write, b'foo')
        self.assertRaises(InterfaceError, blob.seek, 0, 0)
        self.assertRaises(InterfaceError, blob.tell)
        self.assertRaises(InterfaceError, blob.reopen, rowid)

    def test_blob_readonly(self):
        rowid = self.create_blob_row(4)
        blob = self.database.blob_open('register', 'data', rowid)
        blob.write(b'huey')
        blob.seek(0)
        self.assertEqual(blob.read(), b'huey')
        blob.close()

        blob = self.database.blob_open('register', 'data', rowid, True)
        self.assertEqual(blob.read(), b'huey')
        blob.seek(0)
        with self.assertRaisesCtx(OperationalError):
            blob.write(b'meow')

        # BLOB is read-only.
        self.assertEqual(blob.read(), b'huey')


class TestBloomFilterIntegration(CyDatabaseTestCase):
    database = CSqliteExtDatabase(':memory:', bloomfilter=True)

    def setUp(self):
        super(TestBloomFilterIntegration, self).setUp()
        self.execute('create table register (data TEXT);')

    def populate(self):
        accum = []
        with self.database.atomic():
            for i in 'abcdefghijklmnopqrstuvwxyz':
                keys = [i * j for j in range(1, 10)]
                accum.extend(keys)
                self.execute('insert into register (data) values %s' %
                             ', '.join(['(?)'] * len(keys)),
                             *keys)

        curs = self.execute('select * from register '
                            'order by data limit 5 offset 6')
        self.assertEqual([key for key, in curs.fetchall()],
                         ['aaaaaaa', 'aaaaaaaa', 'aaaaaaaaa', 'b', 'bb'])
        return accum

    def test_bloomfilter(self):
        all_keys = self.populate()

        curs = self.execute('select bloomfilter(data, ?) from register',
                            1024 * 16)
        buf, = curs.fetchone()
        self.assertEqual(len(buf), 1024 * 16)
        for key in all_keys:
            curs = self.execute('select bloomfilter_contains(?, ?)',
                                key, buf)
            self.assertEqual(curs.fetchone()[0], 1)

        for key in all_keys:
            key += '-test'
            curs = self.execute('select bloomfilter_contains(?, ?)',
                                key, buf)
            self.assertEqual(curs.fetchone()[0], 0)


class TestBloomFilter(BaseTestCase):
    def setUp(self):
        super(TestBloomFilter, self).setUp()
        self.bf = BloomFilter(1024)

    def test_bloomfilter(self):
        keys = ('charlie', 'huey', 'mickey', 'zaizee', 'nuggie', 'foo', 'bar',
                'baz')
        self.bf.add(*keys)
        for key in keys:
            self.assertTrue(key in self.bf)

        for key in keys:
            self.assertFalse(key + '-x' in self.bf)
            self.assertFalse(key + '-y' in self.bf)
            self.assertFalse(key + ' ' in self.bf)
