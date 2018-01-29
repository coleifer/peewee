import apsw
import datetime

from playhouse.apsw_ext import *
from .base import ModelTestCase
from .base import TestModel


database = APSWDatabase(':memory:')


class User(TestModel):
    username = TextField()


class Message(TestModel):
    user = ForeignKeyField(User)
    message = TextField()
    pub_date = DateTimeField()
    published = BooleanField()


class TestAPSWExtension(ModelTestCase):
    database = database
    requires = [User, Message]

    def test_db_register_function(self):
        @database.func()
        def title(s):
            return s.title()

        curs = self.database.execute_sql('SELECT title(?)', ('heLLo',))
        self.assertEqual(curs.fetchone()[0], 'Hello')

    def test_db_pragmas(self):
        test_db = APSWDatabase(':memory:', pragmas=(
            ('cache_size', '1337'),
        ))
        test_db.connect()

        cs = test_db.execute_sql('PRAGMA cache_size;').fetchone()[0]
        self.assertEqual(cs, 1337)

    def test_select_insert(self):
        for user in ('u1', 'u2', 'u3'):
            User.create(username=user)

        self.assertEqual([x.username for x in User.select()], ['u1', 'u2', 'u3'])

        dt = datetime.datetime(2012, 1, 1, 11, 11, 11)
        Message.create(user=User.get(User.username == 'u1'), message='herps', pub_date=dt, published=True)
        Message.create(user=User.get(User.username == 'u2'), message='derps', pub_date=dt, published=False)

        m1 = Message.get(Message.message == 'herps')
        self.assertEqual(m1.user.username, 'u1')
        self.assertEqual(m1.pub_date, dt)
        self.assertEqual(m1.published, True)

        m2 = Message.get(Message.message == 'derps')
        self.assertEqual(m2.user.username, 'u2')
        self.assertEqual(m2.pub_date, dt)
        self.assertEqual(m2.published, False)

    def test_update_delete(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')

        u1.username = 'u1-modified'
        u1.save()

        self.assertEqual(User.select().count(), 2)
        self.assertEqual(User.get(User.username == 'u1-modified').id, u1.id)

        u1.delete_instance()
        self.assertEqual(User.select().count(), 1)

    def test_transaction_handling(self):
        dt = datetime.datetime(2012, 1, 1, 11, 11, 11)

        def do_ctx_mgr_error():
            with self.database.transaction():
                User.create(username='u1')
                raise ValueError

        self.assertRaises(ValueError, do_ctx_mgr_error)
        self.assertEqual(User.select().count(), 0)

        def do_ctx_mgr_success():
            with self.database.transaction():
                u = User.create(username='test')
                Message.create(message='testing', user=u, pub_date=dt, published=1)

        do_ctx_mgr_success()
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(Message.select().count(), 1)

        def create_error():
            with self.database.atomic():
                u = User.create(username='test')
                Message.create(message='testing', user=u, pub_date=dt,
                               published=1)
                raise ValueError

        self.assertRaises(ValueError, create_error)
        self.assertEqual(User.select().count(), 1)

        def create_success():
            with self.database.atomic():
                u = User.create(username='test')
                Message.create(message='testing', user=u, pub_date=dt,
                               published=1)

        create_success()
        self.assertEqual(User.select().count(), 2)
        self.assertEqual(Message.select().count(), 2)

    def test_exists_regression(self):
        User.create(username='u1')
        self.assertTrue(User.select().where(User.username == 'u1').exists())
        self.assertFalse(User.select().where(User.username == 'ux').exists())
