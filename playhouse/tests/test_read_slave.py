import unittest

from peewee import *
from playhouse.read_slave import ReadSlaveModel


queries = []

def reset():
    global queries
    queries = []

class QueryLogDatabase(SqliteDatabase):
    name = ''

    def execute_sql(self, query, *args, **kwargs):
        queries.append((self.name, query))
        return super(QueryLogDatabase, self).execute_sql(
            query, *args, **kwargs)

class Master(QueryLogDatabase):
    name = 'master'

class Slave1(QueryLogDatabase):
    name = 'slave1'

class Slave2(QueryLogDatabase):
    name = 'slave2'

master = Master('tmp.db')
slave1 = Slave1('tmp.db')
slave2 = Slave2('tmp.db')

class BaseModel(ReadSlaveModel):
    class Meta:
        database = master
        read_slaves = [slave1, slave2]

class User(BaseModel):
    username = CharField()

class Thing(BaseModel):
    name = CharField()

    class Meta:
        read_slaves = [slave2]

class TestMasterSlave(unittest.TestCase):
    def setUp(self):
        User.drop_table(True)
        User.create_table()
        Thing.drop_table(True)
        Thing.create_table()
        User.create(username='peewee')
        Thing.create(name='something')
        reset()

    def tearDown(self):
        User.drop_table(True)
        Thing.drop_table(True)

    def assertQueries(self, databases):
        self.assertEqual([q[0] for q in queries], databases)

    def test_balance_pair(self):
        for i in range(6):
            User.get()
        self.assertQueries([
            'slave1',
            'slave2',
            'slave1',
            'slave2',
            'slave1',
            'slave2'])

    def test_balance_single(self):
        for i in range(3):
            Thing.get()
        self.assertQueries(['slave2', 'slave2', 'slave2'])

    def test_query_types(self):
        u = User.create(username='charlie')
        User.select().where(User.username == 'charlie').get()
        self.assertQueries(['master', 'slave1'])

        User.get(User.username == 'charlie')
        self.assertQueries(['master', 'slave1', 'slave2'])

        u.username = 'edited'
        u.save()  # Update.
        self.assertQueries(['master', 'slave1', 'slave2', 'master'])

        u.delete_instance()
        self.assertQueries(['master', 'slave1', 'slave2', 'master', 'master'])

    def test_raw_queries(self):
        User.raw('insert into user (username) values (?)', 'charlie').execute()
        rq = list(User.raw('select * from user where username = ?', 'charlie'))
        self.assertEqual(rq[0].username, 'charlie')

        self.assertQueries(['master', 'slave1'])
