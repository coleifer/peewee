import apsw
import datetime

from playhouse.apsw_ext import *
from playhouse.tests.base import ModelTestCase


db = APSWDatabase(':memory:')

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    username = CharField()

class Message(BaseModel):
    user = ForeignKeyField(User)
    message = TextField()
    pub_date = DateTimeField()
    published = BooleanField()


class APSWTestCase(ModelTestCase):
    requires = [Message, User]

    def test_db_register_functions(self):
        result = db.execute_sql('SELECT date_part(?, ?)', (
            'day', '2015-01-02 03:04:05')).fetchone()[0]
        self.assertEqual(result, 2)

        result = db.execute_sql('SELECT date_trunc(?, ?)', (
            'day', '2015-01-02 03:04:05')).fetchone()[0]
        self.assertEqual(result, '2015-01-02')

    def test_db_pragmas(self):
        test_db = APSWDatabase(':memory:', pragmas=(
            ('cache_size', '1337'),
        ))
        test_db.connect()

        cs = test_db.execute_sql('PRAGMA cache_size;').fetchone()[0]
        self.assertEqual(cs, 1337)

    def test_select_insert(self):
        users = ('u1', 'u2', 'u3')
        for user in users:
            User.create(username=user)

        self.assertEqual([x.username for x in User.select()], ['u1', 'u2', 'u3'])
        self.assertEqual([x.username for x in User.select().filter(username='x')], [])
        self.assertEqual([x.username for x in User.select().filter(username__in=['u1', 'u3'])], ['u1', 'u3'])

        dt = datetime.datetime(2012, 1, 1, 11, 11, 11)
        Message.create(user=User.get(username='u1'), message='herps', pub_date=dt, published=True)
        Message.create(user=User.get(username='u2'), message='derps', pub_date=dt, published=False)

        m1 = Message.get(message='herps')
        self.assertEqual(m1.user.username, 'u1')
        self.assertEqual(m1.pub_date, dt)
        self.assertEqual(m1.published, True)

        m2 = Message.get(message='derps')
        self.assertEqual(m2.user.username, 'u2')
        self.assertEqual(m2.pub_date, dt)
        self.assertEqual(m2.published, False)

    def test_update_delete(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')

        u1.username = 'u1-modified'
        u1.save()

        self.assertEqual(User.select().count(), 2)
        self.assertEqual(User.get(username='u1-modified').id, u1.id)

        u1.delete_instance()
        self.assertEqual(User.select().count(), 1)

    def test_transaction_handling(self):
        dt = datetime.datetime(2012, 1, 1, 11, 11, 11)

        def do_ctx_mgr_error():
            with db.transaction():
                User.create(username='u1')
                raise ValueError

        self.assertRaises(ValueError, do_ctx_mgr_error)
        self.assertEqual(User.select().count(), 0)

        def do_ctx_mgr_success():
            with db.transaction():
                u = User.create(username='test')
                Message.create(message='testing', user=u, pub_date=dt, published=1)

        do_ctx_mgr_success()
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(Message.select().count(), 1)

        @db.commit_on_success
        def create_error():
            u = User.create(username='test')
            Message.create(message='testing', user=u, pub_date=dt, published=1)
            raise ValueError

        self.assertRaises(ValueError, create_error)
        self.assertEqual(User.select().count(), 1)

        @db.commit_on_success
        def create_success():
            u = User.create(username='test')
            Message.create(message='testing', user=u, pub_date=dt, published=1)

        create_success()
        self.assertEqual(User.select().count(), 2)
        self.assertEqual(Message.select().count(), 2)

    def test_exists_regression(self):
        User.create(username='u1')
        self.assertTrue(User.select().where(User.username == 'u1').exists())
        self.assertFalse(User.select().where(User.username == 'ux').exists())
