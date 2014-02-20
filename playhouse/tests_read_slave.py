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

class Slave(QueryLogDatabase):
    name = 'slave'

master = Master('tmp.db')
slave = Slave('tmp.db')

class BaseModel(ReadSlaveModel):
    class Meta:
        database = master
        read_slave = slave

class User(BaseModel):
    username = CharField()

class TestMasterSlave(unittest.TestCase):
    def setUp(self):
        User.drop_table(True)
        User.create_table()
        reset()

    def tearDown(self):
        User.drop_table(True)

    def assertQueries(self, databases):
        self.assertEqual([q[0] for q in queries], databases)

    def test_database(self):
        u = User.create(username='charlie')
        User.select().where(User.username == 'charlie').get()
        self.assertQueries(['master', 'slave'])

        User.get(User.username == 'charlie')
        self.assertQueries(['master', 'slave', 'slave'])

        u.username = 'edited'
        u.save()  # Update.
        self.assertQueries(['master', 'slave', 'slave', 'master'])

        u.delete_instance()
        self.assertQueries(['master', 'slave', 'slave', 'master', 'master'])

    def test_raw_queries(self):
        User.raw('insert into user (username) values (?)', 'charlie').execute()
        rq = list(User.raw('select * from user'))
        self.assertEqual(rq[0].username, 'charlie')

        self.assertQueries(['master', 'slave'])
