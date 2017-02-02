from peewee import *
from playhouse.pysqlite_ext import Database
from playhouse.tests.base import ModelTestCase


db = Database(':memory:')

class User(Model):
    username = CharField()

    class Meta:
        database = db


class TestPysqliteDatabase(ModelTestCase):
    requires = [
        User,
    ]

    def tearDown(self):
        super(TestPysqliteDatabase, self).tearDown()
        db.on_commit(None)
        db.on_rollback(None)
        db.on_update(None)

    def test_commit_hook(self):
        state = {}

        @db.on_commit
        def on_commit():
            state.setdefault('commits', 0)
            state['commits'] += 1

        user = User.create(username='u1')
        self.assertEqual(state['commits'], 1)

        user.username = 'u1-e'
        user.save()
        self.assertEqual(state['commits'], 2)

        with db.atomic():
            User.create(username='u2')
            User.create(username='u3')
            User.create(username='u4')
            self.assertEqual(state['commits'], 2)

        self.assertEqual(state['commits'], 3)

        with db.atomic() as txn:
            User.create(username='u5')
            txn.rollback()

        self.assertEqual(state['commits'], 3)
        self.assertEqual(User.select().count(), 4)

    def test_rollback_hook(self):
        state = {}

        @db.on_rollback
        def on_rollback():
            state.setdefault('rollbacks', 0)
            state['rollbacks'] += 1

        user = User.create(username='u1')
        self.assertEqual(state, {'rollbacks': 1})

        with db.atomic() as txn:
            User.create(username='u2')
            txn.rollback()
            self.assertEqual(state['rollbacks'], 2)

        self.assertEqual(state['rollbacks'], 2)

    def test_update_hook(self):
        state = []

        @db.on_update
        def on_update(query, db, table, rowid):
            state.append((query, db, table, rowid))

        u = User.create(username='u1')
        u.username = 'u2'
        u.save()

        self.assertEqual(state, [
            ('INSERT', 'main', 'user', 1),
            ('UPDATE', 'main', 'user', 1),
        ])

        with db.atomic():
            User.create(username='u3')
            User.create(username='u4')
            u.delete_instance()
            self.assertEqual(state, [
                ('INSERT', 'main', 'user', 1),
                ('UPDATE', 'main', 'user', 1),
                ('INSERT', 'main', 'user', 2),
                ('INSERT', 'main', 'user', 3),
                ('DELETE', 'main', 'user', 1),
            ])

        self.assertEqual(len(state), 5)

    def test_udf(self):
        @db.func()
        def backwards(s):
            return s[::-1]

        @db.func()
        def titled(s):
            return s.title()

        query = db.execute_sql('SELECT titled(backwards(?));', ('hello',))
        result, = query.fetchone()
        self.assertEqual(result, 'Olleh')

    def test_properties(self):
        mem_used, mem_high = db.memory_used
        self.assertTrue(mem_high >= mem_used)
        self.assertFalse(mem_high == 0)

        conn = db.connection
        self.assertTrue(conn.cache_used is not None)
