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
        connection = db.connection

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
