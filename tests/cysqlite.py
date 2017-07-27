from collections import OrderedDict
import os

from peewee import *
from peewee import sqlite3
from playhouse._cysqlite_ext import *
from playhouse._sqlite_ext import TableFunction

from .base import BaseTestCase
from .base import DatabaseTestCase
from .base import ModelTestCase
from .base import TestModel
from .base import skip_case_unless


database = CySqliteExtDatabase('peewee_test.db', timeout=0.1, hash_functions=1)


class Series(TableFunction):
    columns = ['value']
    params = ['start', 'stop', 'step']
    name = 'series'

    def initialize(self, start=0, stop=None, step=1):
        self.start = start
        self.stop = stop or float('inf')
        self.step = step
        self.curr = self.start

    def iterate(self, idx):
        if self.curr > self.stop:
            raise StopIteration

        ret = self.curr
        self.curr += self.step
        return (ret,)


class RegexSearch(TableFunction):
    columns = ['match']
    params = ['regex', 'search_string']
    name = 'regex_search'

    def initialize(self, regex=None, search_string=None):
        if regex and search_string:
            self._iter = re.finditer(regex, search_string)
        else:
            self._iter = None

    def iterate(self, idx):
        # We do not need `idx`, so just ignore it.
        if self._iter is None:
            raise StopIteration
        else:
            return (next(self._iter).group(0),)


class Split(TableFunction):
    params = ['data']
    columns = ['part']
    name = 'str_split'

    def initialize(self, data=None):
        self._parts = data.split()
        self._idx = 0

    def iterate(self, idx):
        if self._idx < len(self._parts):
            result = (self._parts[self._idx],)
            self._idx += 1
            return result
        raise StopIteration


class TestTableFunction(BaseTestCase):
    def setUp(self):
        super(TestTableFunction, self).setUp()
        self.conn = sqlite3.connect(':memory:')

    def tearDown(self):
        super(TestTableFunction, self).tearDown()
        self.conn.close()

    def test_split(self):
        Split.register(self.conn)
        curs = self.conn.execute('select part from str_split(?) order by part '
                                 'limit 3', ('well hello huey and zaizee',))
        self.assertEqual([row for row, in curs.fetchall()],
                         ['and', 'hello', 'huey'])

    def test_split_tbl(self):
        Split.register(self.conn)
        self.conn.execute('create table post (content TEXT);')
        self.conn.execute('insert into post (content) values (?), (?), (?)',
                          ('huey secret post',
                           'mickey message',
                           'zaizee diary'))
        curs = self.conn.execute('SELECT * FROM post, str_split(post.content)')
        results = curs.fetchall()
        self.assertEqual(results, [
            ('huey secret post', 'huey'),
            ('huey secret post', 'secret'),
            ('huey secret post', 'post'),
            ('mickey message', 'mickey'),
            ('mickey message', 'message'),
            ('zaizee diary', 'zaizee'),
            ('zaizee diary', 'diary'),
        ])

    def test_series(self):
        Series.register(self.conn)

        def assertSeries(params, values, extra_sql=''):
            param_sql = ', '.join('?' * len(params))
            sql = 'SELECT * FROM series(%s)' % param_sql
            if extra_sql:
                sql = ' '.join((sql, extra_sql))
            curs = self.conn.execute(sql, params)
            self.assertEqual([row for row, in curs.fetchall()], values)

        assertSeries((0, 10, 2), [0, 2, 4, 6, 8, 10])
        assertSeries((5, None, 20), [5, 25, 45, 65, 85], 'LIMIT 5')
        assertSeries((4, 0, -1), [4, 3, 2], 'LIMIT 3')
        assertSeries((3, 5, 3), [3])
        assertSeries((3, 3, 1), [3])

    def test_series_tbl(self):
        Series.register(self.conn)
        self.conn.execute('CREATE TABLE nums (id INTEGER PRIMARY KEY)')
        self.conn.execute('INSERT INTO nums DEFAULT VALUES;')
        self.conn.execute('INSERT INTO nums DEFAULT VALUES;')
        curs = self.conn.execute(
            'SELECT * FROM nums, series(nums.id, nums.id + 2)')
        results = curs.fetchall()
        self.assertEqual(results, [
            (1, 1), (1, 2), (1, 3),
            (2, 2), (2, 3), (2, 4)])

        curs = self.conn.execute(
            'SELECT * FROM nums, series(nums.id) LIMIT 3')
        results = curs.fetchall()
        self.assertEqual(results, [(1, 1), (1, 2), (1, 3)])

    def test_regex(self):
        RegexSearch.register(self.conn)

        def assertResults(regex, search_string, values):
            sql = 'SELECT * FROM regex_search(?, ?)'
            curs = self.conn.execute(sql, (regex, search_string))
            self.assertEqual([row for row, in curs.fetchall()], values)

        assertResults(
            '[0-9]+',
            'foo 123 45 bar 678 nuggie 9.0',
            ['123', '45', '678', '9', '0'])
        assertResults(
            '[\w]+@[\w]+\.[\w]{2,3}',
            ('Dear charlie@example.com, this is nug@baz.com. I am writing on '
             'behalf of zaizee@foo.io. He dislikes your blog.'),
            ['charlie@example.com', 'nug@baz.com', 'zaizee@foo.io'])
        assertResults(
            '[a-z]+',
            '123.pDDFeewXee',
            ['p', 'eew', 'ee'])
        assertResults(
            '[0-9]+',
            'hello',
            [])

    def test_regex_tbl(self):
        messages = (
            'hello foo@example.fap, this is nuggie@example.fap. How are you?',
            'baz@example.com wishes to let charlie@crappyblog.com know that '
            'huey@example.com hates his blog',
            'testing no emails.',
            '')
        RegexSearch.register(self.conn)

        self.conn.execute('create table posts (id integer primary key, msg)')
        self.conn.execute('insert into posts (msg) values (?), (?), (?), (?)',
                          messages)
        cur = self.conn.execute('select posts.id, regex_search.rowid, regex_search.match '
                                'FROM posts, regex_search(?, posts.msg)',
                                ('[\w]+@[\w]+\.\w{2,3}',))
        results = cur.fetchall()
        self.assertEqual(results, [
            (1, 1, 'foo@example.fap'),
            (1, 2, 'nuggie@example.fap'),
            (2, 3, 'baz@example.com'),
            (2, 4, 'charlie@crappyblog.com'),
            (2, 5, 'huey@example.com'),
        ])


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
        mem_used, mem_high = self.database.memory_used
        self.assertTrue(mem_high >= mem_used)
        self.assertFalse(mem_high == 0)

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
    backup_filename = 'test_backup.db'

    def tearDown(self):
        super(TestBackup, self).tearDown()
        if os.path.exists(self.backup_filename):
            os.unlink(self.backup_filename)

    def test_backup_to_file(self):
        # Populate the database with some test data.
        self.execute('CREATE TABLE register (id INTEGER NOT NULL PRIMARY KEY, '
                     'value INTEGER NOT NULL)')
        with self.database.atomic():
            for i in range(100):
                self.execute('INSERT INTO register (value) VALUES (?)', i)

        self.database.backup_to_file(self.backup_filename)
        backup_db = CySqliteExtDatabase(self.backup_filename)
        cursor = backup_db.execute_sql('SELECT value FROM register ORDER BY '
                                       'value;')
        self.assertEqual([val for val, in cursor.fetchall()], range(100))
        backup_db.close()


class TestBlob(CyDatabaseTestCase):
    def setUp(self):
        super(TestBlob, self).setUp()
        self.Register = Table('register', ('id', 'data'))
        self.execute('CREATE TABLE register (id INTEGER NOT NULL PRIMARY KEY, '
                     'data BLOB NOT NULL)')

    def test_blob(self):
        Register = self.Register.bind(self.database)

        Register.insert({Register.data: ZeroBlob(1024)}).execute()
        rowid1024 = self.database.last_insert_rowid
        Register.insert({Register.data: ZeroBlob(16)}).execute()
        rowid16 = self.database.last_insert_rowid

        blob = Blob(self.database, 'register', 'data', rowid1024)
        self.assertEqual(len(blob), 1024)

        blob.write('x' * 1022)
        blob.write('zz')
        blob.seek(1020)
        self.assertEqual(blob.tell(), 1020)

        data = blob.read(3)
        self.assertEqual(data, 'xxz')
        self.assertEqual(blob.read(), 'z')
        self.assertEqual(blob.read(), '')

        blob.seek(-10, 2)
        self.assertEqual(blob.tell(), 1014)
        self.assertEqual(blob.read(), 'xxxxxxxxzz')

        blob.reopen(rowid16)
        self.assertEqual(blob.tell(), 0)
        self.assertEqual(len(blob), 16)

        blob.write('x' * 15)
        self.assertEqual(blob.tell(), 15)

    def test_blob_errors(self):
        Register = self.Register.bind(self.database)
        Register.insert(data=ZeroBlob(16)).execute()
        rowid = self.database.last_insert_rowid

        blob = self.database.blob_open('register', 'data', rowid)
        with self.assertRaisesCtx(ValueError):
            blob.seek(17, 0)

        with self.assertRaisesCtx(ValueError):
            blob.write('x' * 17)

        blob.write('x' * 16)
        self.assertEqual(blob.tell(), 16)
        blob.seek(0)
        data = blob.read(17)  # Attempting to read more data is OK.
        self.assertEqual(data, 'x' * 16)
        blob.close()