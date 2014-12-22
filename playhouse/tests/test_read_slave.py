from peewee import *
from playhouse.read_slave import ReadSlaveModel
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase


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

master = database_initializer.get_database('sqlite', db_class=Master)
slave1 = database_initializer.get_database('sqlite', db_class=Slave1)
slave2 = database_initializer.get_database('sqlite', db_class=Slave2)

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

class TestMasterSlave(ModelTestCase):
    requires = [User, Thing]

    def setUp(self):
        super(TestMasterSlave, self).setUp()
        User.create(username='peewee')
        Thing.create(name='something')
        reset()

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
