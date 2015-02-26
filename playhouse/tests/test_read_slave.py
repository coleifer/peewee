from peewee import *
from peewee import Using
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

# Models to use for testing read slaves.

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

# Regular models to use for testing `Using`.

class BaseMasterOnly(Model):
    class Meta:
        database = master

class A(BaseMasterOnly):
    data = CharField()

class B(BaseMasterOnly):
    data = CharField()


class TestUsing(ModelTestCase):
    requires = [A, B]

    def setUp(self):
        super(TestUsing, self).setUp()
        reset()

    def assertDatabaseVerb(self, expected):
        db_and_verb = [(db, sql.split()[0]) for db, sql in queries]
        self.assertEqual(db_and_verb, expected)
        reset()

    def test_using_context(self):
        models = [A, B]

        with Using(slave1, models, False):
            A.create(data='a1')
            B.create(data='b1')

        self.assertDatabaseVerb([
            ('slave1', 'INSERT'),
            ('slave1', 'INSERT')])

        with Using(slave2, models, False):
            A.create(data='a2')
            B.create(data='b2')
            a_obj = A.select().order_by(A.id).get()
            self.assertEqual(a_obj.data, 'a1')

        self.assertDatabaseVerb([
            ('slave2', 'INSERT'),
            ('slave2', 'INSERT'),
            ('slave2', 'SELECT')])

        with Using(master, models, False):
            query = A.select().order_by(A.data.desc())
            values = [a_obj.data for a_obj in query]

        self.assertEqual(values, ['a2', 'a1'])
        self.assertDatabaseVerb([('master', 'SELECT')])

    def test_using_transactions(self):
        with Using(slave1, [A]) as txn:
            list(B.select())
            A.create(data='a1')

        B.create(data='b1')
        self.assertDatabaseVerb([
            ('slave1', 'BEGIN'),
            ('master', 'SELECT'),
            ('slave1', 'INSERT'),
            ('master', 'INSERT')])

        def fail_with_exc(data):
            with Using(slave2, [A]):
                A.create(data=data)
                raise ValueError('xxx')

        self.assertRaises(ValueError, fail_with_exc, 'a2')
        self.assertDatabaseVerb([
            ('slave2', 'BEGIN'),
            ('slave2', 'INSERT')])

        with Using(slave1, [A, B]):
            a_objs = [a_obj.data for a_obj in A.select()]
            self.assertEqual(a_objs, ['a1'])


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
