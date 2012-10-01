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


class TestQueryCompiler(QueryCompiler):
    def _max_alias(self, am):
        return 0

    def calculate_alias_map(self, query, start=1):
        alias_map = {query.model_class: query.model_class._meta.db_table}
        for model, joins in query._joins.items():
            if model not in alias_map:
                alias_map[model] = model._meta.db_table
            for join in joins:
                if join.model_class not in alias_map:
                    alias_map[join.model_class] = join.model_class._meta.db_table
        return alias_map

class TestDatabase(database_class):
    compiler_class = TestQueryCompiler
    field_overrides = {}
    interpolation = '?'
    op_overrides = {}
    quote_char = '"'

test_db = database_class(database_name, **database_params)
query_db = TestDatabase(database_name, **database_params)
compiler = query_db.get_compiler()


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

    def parse_expr(self, query, expr_list):
        am = compiler.calculate_alias_map(query)
        return compiler.parse_expr_list(expr_list, am)

    def assertSelect(self, sq, exp_sel, exp_params):
        exp, p = self.parse_expr(sq, sq._select)
        self.assertEqual(exp, exp_sel)
        self.assertEqual(p, exp_params)


class SelectTestCase(BasePeeweeTestCase):
    def test_selection(self):
        sq = SelectQuery(User)
        self.assertSelect(sq, 'users."id", users."username"', [])

        sq = SelectQuery(Blog, Blog.pk, Blog.title, Blog.user, User.username).join(User)
        self.assertSelect(sq, 'blog."pk", blog."title", blog."user_id", users."username"', [])

        sq = SelectQuery(User, fn.Lower(fn.Substr(User.username, 0, 1)).set_alias('lu'), fn.Count(Blog.pk)).join(Blog)
        self.assertSelect(sq, 'Lower(Substr(users."username", ?, ?)) AS lu, Count(blog."pk")', [0, 1])

        sq = SelectQuery(User, User.username, fn.Count(Blog.select().where(Blog.user == User.id)))
        self.assertSelect(sq, 'users."username", Count((SELECT blog."pk" FROM "blog" AS blog WHERE blog."user_id" = users."id"))', [])


class ModelTestCase(BasePeeweeTestCase):
    def setUp(self):
        super(ModelTestCase, self).setUp()
        drop_tables()
        create_tables()
