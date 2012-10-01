# encoding=utf-8

from __future__ import with_statement
import datetime
import logging
import os
import unittest
from decimal import Decimal

from peewee import *
from peewee import logger


class QueryLogHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        self.queries = []
        logging.Handler.__init__(self, *args, **kwargs)

    def emit(self, record):
        self.queries.append(record)


BACKEND = os.environ.get('PEEWEE_TEST_BACKEND', 'sqlite')
TEST_VERBOSITY = int(os.environ.get('PEEWEE_TEST_VERBOSITY') or 1)

database_params = {}

if BACKEND == 'postgresql':
    database_class = PostgresqlDatabase
    database_name = 'peewee_test'
elif BACKEND == 'mysql':
    database_class = MySQLDatabase
    database_name = 'peewee_test'
elif BACKEND == 'apsw':
    from extras.apsw_ext import *
    database_class = APSWDatabase
    database_name = 'tmp.db'
    database_params['timeout'] = 1000
else:
    database_class = SqliteDatabase
    database_name = 'tmp.db'
    import sqlite3
    print 'SQLITE VERSION: %s' % sqlite3.version


test_db = database_class(database_name, **database_params)


class TestModel(Model):
    class Meta:
        database = test_db

class User(TestModel):
    username = CharField()

    class Meta:
        db_table = 'users'

class Blog(TestModel):
    user = ForeignKeyField(User)
    title = CharField(max_length=25)
    content = TextField(default='')
    pub_date = DateTimeField(null=True)
    pk = PrimaryKeyField()

    def __unicode__(self):
        return '%s: %s' % (self.user.username, self.title)

class Relationship(TestModel):
    from_user = ForeignKeyField(User, related_name='relationships')
    to_user = ForeignKeyField(User, related_name='related_to')

class NullModel(TestModel):
    char_field = CharField(null=True)
    text_field = TextField(null=True)
    datetime_field = DateTimeField(null=True)
    int_field = IntegerField(null=True)
    float_field = FloatField(null=True)
    decimal_field1 = DecimalField(null=True)
    decimal_field2 = DecimalField(decimal_places=2, null=True)
    double_field = DoubleField(null=True)
    bigint_field = BigIntegerField(null=True)
    date_field = DateField(null=True)
    time_field = TimeField(null=True)
    boolean_field = BooleanField(null=True)

class UniqueModel(TestModel):
    name = CharField(unique=True)

class OrderedModel(TestModel):
    title = CharField()
    created = DateTimeField(default=datetime.datetime.now)

    class Meta:
        ordering = (('created', 'desc'),)

class Category(TestModel):
    parent = ForeignKeyField('self', related_name='children', null=True)
    name = CharField()

def drop_tables():
    Category.drop_table(True)
    OrderedModel.drop_table(True)
    UniqueModel.drop_table(True)
    NullModel.drop_table(True)
    Relationship.drop_table(True)
    Blog.drop_table(True)
    User.drop_table(True)
    
def create_tables():
    User.create_table()
    Blog.create_table()
    Relationship.create_table()
    NullModel.create_table()
    UniqueModel.create_table()
    OrderedModel.create_table()
    Category.create_table()


class BasePeeweeTestCase(unittest.TestCase):
    def setUp(self):
        self.qh = QueryLogHandler()
        logger.setLevel(logging.DEBUG)
        logger.addHandler(self.qh)

    def tearDown(self):
        logger.removeHandler(self.qh)

    def queries(self):
        return [x.msg for x in self.qh.queries]


class ModelTestCase(BasePeeweeTestCase):
    def setUp(self):
        super(ModelTestCase, self).setUp()
        drop_tables()
        create_tables()


class ModelAPITestCase(ModelTestCase):
    def create_user(self, n):
        return User.create(username=n)

    def test_creation(self):
        self.create_user('u1')
        self.create_user('u2')
        res = test_db.execute_sql('select username from users order by username;')
        self.assertEqual([r[0] for r in res.fetchall()], ['u1', 'u2'])

    def test_select(self):
        self.create_user('u1')
        self.create_user('u2')
        self.assertEqual([u.username for u in User.select().order_by(User.username.asc())], ['u1', 'u2'])
        self.assertEqual([u.username for u in User.select().order_by(User.username.desc())], ['u2', 'u1'])
