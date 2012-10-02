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

#
# JUNK TO ALLOW TESTING OF MULTIPLE DATABASE BACKENDS
#

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

#
# TEST-ONLY QUERY COMPILER USED TO CREATE "predictable" QUERIES
#

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

#
# BASE MODEL CLASS
#

class TestModel(Model):
    class Meta:
        database = test_db

#
# MODEL CLASSES USED BY TEST CASES
#

class User(TestModel):
    username = CharField()

    class Meta:
        db_table = 'users'

class Blog(TestModel):
    user = ForeignKeyField(User, related_name='blogs')
    title = CharField(max_length=25)
    content = TextField(default='')
    pub_date = DateTimeField(null=True)
    pk = PrimaryKeyField()

    def __unicode__(self):
        return '%s: %s' % (self.user.username, self.title)

class Comment(TestModel):
    blog = ForeignKeyField(Blog, related_name='comments')
    comment = CharField()

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
        order_by = ('-created',)

class Category(TestModel):
    parent = ForeignKeyField('self', related_name='children', null=True)
    name = CharField()

MODELS = [User, Blog, Comment, Relationship, NullModel, UniqueModel, OrderedModel, Category]

def drop_tables(only=None):
    for model in reversed(MODELS):
        if only is None or model in only:
            model.drop_table(True)

def create_tables(only=None):
    for model in MODELS:
        if only is None or model in only:
            model.create_table()
#
# BASE TEST CASE USED BY ALL TESTS
#

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

    def parse_node(self, query, node):
        am = compiler.calculate_alias_map(query)
        return compiler.parse_query_node(node, am)

    def make_fn(fn_name, attr_name):
        def inner(self, query, expected, expected_params):
            fn = getattr(self, fn_name)
            att = getattr(query, attr_name)
            sql, params = fn(query, att)
            self.assertEqual(sql, expected)
            self.assertEqual(params, expected_params)
        return inner

    assertSelect = make_fn('parse_expr', '_select')
    assertWhere = make_fn('parse_node', '_where')
    assertGroupBy = make_fn('parse_expr', '_group_by')
    assertHaving = make_fn('parse_node', '_having')
    assertOrderBy = make_fn('parse_expr', '_order_by')

    def assertJoins(self, sq, exp_joins):
        am = compiler.calculate_alias_map(sq)
        joins = compiler.parse_joins(sq._joins, sq.model_class, am)
        self.assertEqual(sorted(joins), sorted(exp_joins))

    def assertDict(self, qd, expected, expected_params):
        sets, params = compiler._parse_field_dictionary(qd)
        self.assertEqual(sets, expected)
        self.assertEqual(params, expected_params)

    def assertUpdate(self, uq, expected, expected_params):
        self.assertDict(uq._update, expected, expected_params)

    def assertInsert(self, uq, expected, expected_params):
        self.assertDict(uq._insert, expected, expected_params)

#
# BASIC TESTS OF QUERY TYPES AND INTERNAL DATA STRUCTURES
#

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

    def test_joins(self):
        sq = SelectQuery(User).join(Blog)
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON users."id" = blog."user_id"'])

        sq = SelectQuery(Blog).join(User, JOIN_LEFT_OUTER)
        self.assertJoins(sq, ['LEFT OUTER JOIN "users" AS users ON blog."user_id" = users."id"'])

        sq = SelectQuery(User).join(Relationship)
        self.assertJoins(sq, ['INNER JOIN "relationship" AS relationship ON users."id" = relationship."from_user_id"'])

        sq = SelectQuery(User).join(Relationship, on=Relationship.to_user)
        self.assertJoins(sq, ['INNER JOIN "relationship" AS relationship ON users."id" = relationship."to_user_id"'])

        sq = SelectQuery(User).join(Relationship, JOIN_LEFT_OUTER, Relationship.to_user)
        self.assertJoins(sq, ['LEFT OUTER JOIN "relationship" AS relationship ON users."id" = relationship."to_user_id"'])

    def test_join_self_referential(self):
        sq = SelectQuery(Category).join(Category)
        self.assertJoins(sq, ['INNER JOIN "category" AS category ON category."parent_id" = category."id"'])

    def test_join_both_sides(self):
        sq = SelectQuery(Blog).join(Comment).switch(Blog).join(User)
        self.assertJoins(sq, [
            'INNER JOIN "comment" AS comment ON blog."pk" = comment."blog_id"',
            'INNER JOIN "users" AS users ON blog."user_id" = users."id"',
        ])

        sq = SelectQuery(Blog).join(User).switch(Blog).join(Comment)
        self.assertJoins(sq, [
            'INNER JOIN "users" AS users ON blog."user_id" = users."id"',
            'INNER JOIN "comment" AS comment ON blog."pk" = comment."blog_id"',
        ])

    def test_where(self):
        sq = SelectQuery(User).where(User.id < 5)
        self.assertWhere(sq, 'users."id" < ?', [5])

    def test_where_lists(self):
        sq = SelectQuery(User).where(User.username << ['u1', 'u2'])
        self.assertWhere(sq, 'users."username" IN (?,?)', ['u1', 'u2'])

        sq = SelectQuery(User).where((User.username << ['u1', 'u2']) | (User.username << ['u3', 'u4']))
        self.assertWhere(sq, '(users."username" IN (?,?) OR users."username" IN (?,?))', ['u1', 'u2', 'u3', 'u4'])

    def test_where_joins(self):
        sq = SelectQuery(User).where(
            ((User.id == 1) | (User.id == 2)) &
            ((Blog.pk == 3) | (Blog.pk == 4))
        ).where(User.id == 5).join(Blog)
        self.assertWhere(sq, '(users."id" = ? OR users."id" = ?) AND (blog."pk" = ? OR blog."pk" = ?) AND users."id" = ?', [1, 2, 3, 4, 5])

    def test_where_functions(self):
        sq = SelectQuery(User).where(fn.Lower(fn.Substr(User.username, 0, 1)) == 'a')
        self.assertWhere(sq, 'Lower(Substr(users."username", ?, ?)) = ?', [0, 1, 'a'])

    def test_where_subqueries(self):
        sq = SelectQuery(User).where(User.id << User.select().where(User.username=='u1'))
        self.assertWhere(sq, 'users."id" IN (SELECT users."id" FROM "users" AS users WHERE users."username" = ?)', ['u1'])

        sq = SelectQuery(Blog).where((Blog.pk == 3) | (Blog.user << User.select().where(User.username << ['u1', 'u2'])))
        self.assertWhere(sq, '(blog."pk" = ? OR blog."user_id" IN (SELECT users."id" FROM "users" AS users WHERE users."username" IN (?,?)))', [3, 'u1', 'u2'])

    def test_where_fk(self):
        sq = SelectQuery(Blog).where(Blog.user == User(id=100))
        self.assertWhere(sq, 'blog."user_id" = ?', [100])

        sq = SelectQuery(Blog).where(Blog.user << [User(id=100), User(id=101)])
        self.assertWhere(sq, 'blog."user_id" IN (?,?)', [100, 101])

    def test_where_negation(self):
        sq = SelectQuery(Blog).where(~(Blog.title == 'foo'))
        self.assertWhere(sq, 'NOT blog."title" = ?', ['foo'])

        sq = SelectQuery(Blog).where(~((Blog.title == 'foo') | (Blog.title == 'bar')))
        self.assertWhere(sq, '(NOT (blog."title" = ? OR blog."title" = ?))', ['foo', 'bar'])

        sq = SelectQuery(Blog).where(~((Blog.title == 'foo') & (Blog.title == 'bar')) & (Blog.title == 'baz'))
        self.assertWhere(sq, '(NOT (blog."title" = ? AND blog."title" = ?)) AND blog."title" = ?', ['foo', 'bar', 'baz'])

        sq = SelectQuery(Blog).where(~((Blog.title == 'foo') & (Blog.title == 'bar')) & ((Blog.title == 'baz') & (Blog.title == 'fizz')))
        self.assertWhere(sq, '(NOT (blog."title" = ? AND blog."title" = ?)) AND (blog."title" = ? AND blog."title" = ?)', ['foo', 'bar', 'baz', 'fizz'])

    def test_where_chaining_collapsing(self):
        sq = SelectQuery(User).where(User.id == 1).where(User.id == 2).where(User.id == 3)
        self.assertWhere(sq, 'users."id" = ? AND users."id" = ? AND users."id" = ?', [1, 2, 3])

        sq = SelectQuery(User).where((User.id == 1) & (User.id == 2)).where(User.id == 3)
        self.assertWhere(sq, 'users."id" = ? AND users."id" = ? AND users."id" = ?', [1, 2, 3])

        sq = SelectQuery(User).where((User.id == 1) | (User.id == 2)).where(User.id == 3)
        self.assertWhere(sq, '(users."id" = ? OR users."id" = ?) AND users."id" = ?', [1, 2, 3])

        sq = SelectQuery(User).where(User.id == 1).where((User.id == 2) & (User.id == 3))
        self.assertWhere(sq, 'users."id" = ? AND users."id" = ? AND users."id" = ?', [1, 2, 3])

        sq = SelectQuery(User).where(User.id == 1).where((User.id == 2) | (User.id == 3))
        self.assertWhere(sq, '(users."id" = ?) AND (users."id" = ? OR users."id" = ?)', [1, 2, 3])

        sq = SelectQuery(User).where(~(User.id == 1)).where(User.id == 2).where(~(User.id == 3))
        self.assertWhere(sq, '(users."id" = ? AND users."id" = ?) AND NOT users."id" = ?', [1, 2, 3])

    def test_grouping(self):
        sq = SelectQuery(User).group_by(User.id)
        self.assertGroupBy(sq, 'users."id"', [])

        sq = SelectQuery(User).group_by(User)
        self.assertGroupBy(sq, 'users."id", users."username"', [])

    def test_having(self):
        sq = SelectQuery(User, fn.Count(Blog.pk)).join(Blog).group_by(User).having(
            fn.Count(Blog.pk) > 2
        )
        self.assertHaving(sq, 'Count(blog."pk") > ?', [2])

        sq = SelectQuery(User, fn.Count(Blog.pk)).join(Blog).group_by(User).having(
            (fn.Count(Blog.pk) > 10) | (fn.Count(Blog.pk) < 2)
        )
        self.assertHaving(sq, '(Count(blog."pk") > ? OR Count(blog."pk") < ?)', [10, 2])

    def test_ordering(self):
        sq = SelectQuery(User).join(Blog).order_by(Blog.title)
        self.assertOrderBy(sq, 'blog."title"', [])

        sq = SelectQuery(User).join(Blog).order_by(Blog.title.asc())
        self.assertOrderBy(sq, 'blog."title" ASC', [])

        sq = SelectQuery(User).join(Blog).order_by(Blog.title.desc())
        self.assertOrderBy(sq, 'blog."title" DESC', [])

        sq = SelectQuery(User).join(Blog).order_by(User.username.desc(), Blog.title.asc())
        self.assertOrderBy(sq, 'users."username" DESC, blog."title" ASC', [])

        base_sq = SelectQuery(User, User.username, fn.Count(Blog.pk).set_alias('count')).join(Blog).group_by(User.username)
        sq = base_sq.order_by(fn.Count(Blog.pk).desc())
        self.assertOrderBy(sq, 'Count(blog."pk") DESC', [])

        sq = base_sq.order_by(R('count'))
        self.assertOrderBy(sq, 'count', [])

        sq = OrderedModel.select()
        self.assertOrderBy(sq, 'orderedmodel."created" DESC', [])

        sq = OrderedModel.select().order_by(OrderedModel.id.asc())
        self.assertOrderBy(sq, 'orderedmodel."id" ASC', [])

    def test_paginate(self):
        sq = SelectQuery(User).paginate(1, 20)
        self.assertEqual(sq._limit, 20)
        self.assertEqual(sq._offset, 0)

        sq = SelectQuery(User).paginate(3, 30)
        self.assertEqual(sq._limit, 30)
        self.assertEqual(sq._offset, 60)

class UpdateTestCase(BasePeeweeTestCase):
    def test_update(self):
        uq = UpdateQuery(User, {User.username: 'updated'})
        self.assertUpdate(uq, [('"username"', '?')], ['updated'])

        uq = UpdateQuery(Blog, {Blog.user: User(id=100, username='foo')})
        self.assertUpdate(uq, [('"user_id"', '?')], [100])

        uq = UpdateQuery(User, {User.id: User.id + 5})
        self.assertUpdate(uq, [('"id"', '("id" + ?)')], [5])

    def test_where(self):
        uq = UpdateQuery(User, {User.username: 'updated'}).where(User.id == 2)
        self.assertWhere(uq, 'users."id" = ?', [2])

class InsertTestCase(BasePeeweeTestCase):
    def test_insert(self):
        iq = InsertQuery(User, {User.username: 'inserted'})
        self.assertInsert(iq, [('"username"', '?')], ['inserted'])

class DeleteTestCase(BasePeeweeTestCase):
    def test_where(self):
        dq = DeleteQuery(User).where(User.id == 2)
        self.assertWhere(dq, 'users."id" = ?', [2])

class RawTestCase(BasePeeweeTestCase):
    def test_raw(self):
        q = 'SELECT * FROM "users" WHERE id=?'
        rq = RawQuery(User, q, 100)
        self.assertEqual(rq.sql(compiler), (q, [100]))

class SugarTestCase(BasePeeweeTestCase):
    # test things like filter, annotate, aggregate
    def test_filter(self):
        sq = User.filter(username='u1')
        self.assertJoins(sq, [])
        self.assertWhere(sq, 'users."username" = ?', ['u1'])

        sq = Blog.filter(user__username='u1')
        self.assertJoins(sq, ['INNER JOIN "users" AS users ON blog."user_id" = users."id"'])
        self.assertWhere(sq, 'users."username" = ?', ['u1'])

        sq = Blog.filter(user__username__in=['u1', 'u2'], comments__comment='hurp')
        self.assertJoins(sq, [
            'INNER JOIN "comment" AS comment ON blog."pk" = comment."blog_id"',
            'INNER JOIN "users" AS users ON blog."user_id" = users."id"',
        ])
        self.assertWhere(sq, 'comment."comment" = ? AND users."username" IN (?,?)', ['hurp', 'u1', 'u2'])

        sq = Blog.filter(user__username__in=['u1', 'u2']).filter(comments__comment='hurp')
        self.assertJoins(sq, [
            'INNER JOIN "users" AS users ON blog."user_id" = users."id"',
            'INNER JOIN "comment" AS comment ON blog."pk" = comment."blog_id"',
        ])
        self.assertWhere(sq, 'users."username" IN (?,?) AND comment."comment" = ?', ['u1', 'u2', 'hurp'])

    def test_annotate(self):
        sq = User.select().annotate(Blog)
        self.assertSelect(sq, 'users."id", users."username", Count(blog."pk") AS count', [])
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON users."id" = blog."user_id"'])
        self.assertWhere(sq, '', [])
        self.assertGroupBy(sq, 'users."id", users."username"', [])

        sq = User.select(User.username).annotate(Blog, fn.Sum(Blog.pk).set_alias('sum')).where(User.username == 'foo')
        self.assertSelect(sq, 'users."username", Sum(blog."pk") AS sum', [])
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON users."id" = blog."user_id"'])
        self.assertWhere(sq, 'users."username" = ?', ['foo'])
        self.assertGroupBy(sq, 'users."username"', [])

        sq = User.select(User.username).annotate(Blog).annotate(Blog, fn.Max(Blog.pk).set_alias('mx'))
        self.assertSelect(sq, 'users."username", Count(blog."pk") AS count, Max(blog."pk") AS mx', [])
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON users."id" = blog."user_id"'])
        self.assertWhere(sq, '', [])
        self.assertGroupBy(sq, 'users."username"', [])

        sq = User.select().annotate(Blog).order_by(R('count DESC'))
        self.assertSelect(sq, 'users."id", users."username", Count(blog."pk") AS count', [])
        self.assertOrderBy(sq, 'count DESC', [])

    def test_aggregate(self):
        sq = User.select().where(User.id < 10)._aggregate()
        self.assertSelect(sq, 'Count(users."id")', [])
        self.assertWhere(sq, 'users."id" < ?', [10])


#
# TEST CASE USED TO PROVIDE ACCESS TO DATABASE
# FOR EXECUTION OF "LIVE" QUERIES
#

class ModelTestCase(BasePeeweeTestCase):
    requires = None

    def setUp(self):
        super(ModelTestCase, self).setUp()
        drop_tables(self.requires)
        create_tables(self.requires)

    def create_user(self, username):
        return User.create(username=username)

    def create_users(self, n):
        for i in range(n):
            self.create_user('u%d' % (i + 1))


class QueryResultWrapperTestCase(ModelTestCase):
    requires = [User]

    def test_iteration(self):
        self.create_users(10)
        query_start = len(self.queries())
        sq = User.select()
        qr = sq.execute()

        first_five = []
        for i, u in enumerate(qr):
            first_five.append(u.username)
            if i == 4:
                break
        self.assertEqual(first_five, ['u1', 'u2', 'u3', 'u4', 'u5'])

        another_iter = [u.username for u in qr]
        self.assertEqual(another_iter, ['u%d' % i for i in range(1, 11)])

        another_iter = [u.username for u in qr]
        self.assertEqual(another_iter, ['u%d' % i for i in range(1, 11)])

        # only 1 query for these iterations
        self.assertEqual(len(self.queries()) - query_start, 1)

    def test_iterator(self):
        self.create_users(10)
        qc = len(self.queries())

        qr = User.select().execute()
        usernames = [u.username for u in qr.iterator()]
        self.assertEqual(usernames, ['u%d' % i for i in range(1, 11)])

        qc1 = len(self.queries())
        self.assertEqual(qc1 - qc, 1)

        self.assertTrue(qr._populated)
        self.assertEqual(qr._result_cache, [])

        again = [u.username for u in qr]
        self.assertEqual(again, [])
        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc1, 0)

        qr = User.select().where(User.username == 'xxx').execute()
        usernames = [u.username for u in qr.iterator()]
        self.assertEqual(usernames, [])

class ModelQueryTestCase(ModelTestCase):
    requires = [User, Blog]

    def test_select(self):
        pass
    def test_update(self):
        pass
    def test_insert(self):
        pass
    def test_delete(self):
        pass
    def test_raw(self):
        pass


class ModelAPITestCase(ModelTestCase):
    requires = [User, Blog, Category]

    def test_related_name(self):
        u1 = self.create_user('u1')
        u2 = self.create_user('u2')
        b11 = Blog.create(user=u1, title='b11')
        b12 = Blog.create(user=u1, title='b12')
        b2 = Blog.create(user=u2, title='b2')

        self.assertEqual([b.title for b in u1.blogs], ['b11', 'b12'])
        self.assertEqual([b.title for b in u2.blogs], ['b2'])

    def test_fk_exceptions(self):
        c1 = Category.create(name='c1')
        c2 = Category.create(parent=c1, name='c2')
        self.assertEqual(c1.parent, None)
        self.assertEqual(c2.parent, c1)

        c2_db = Category.get(Category.id == c2.id)
        self.assertEqual(c2_db.parent, c1)

        u = self.create_user('u1')
        b = Blog.create(user=u, title='b')
        b2 = Blog(title='b2')

        self.assertEqual(b.user, u)
        self.assertRaises(User.DoesNotExist, getattr, b2, 'user')

    def test_fk_ints(self):
        c1 = Category.create(name='c1')
        c2 = Category.create(name='c2', parent=c1.id)
        c2_db = Category.get(Category.id == c2.id)
        self.assertEqual(c2_db.parent, c1)

    def test_creation(self):
        self.create_users(10)
        self.assertEqual(User.select().count(), 10)

    def test_saving(self):
        self.assertEqual(User.select().count(), 0)

        u = User(username='u1')
        u.save()
        u.save()

        self.assertEqual(User.select().count(), 1)

    def test_reading(self):
        u1 = self.create_user('u1')
        u2 = self.create_user('u2')

        self.assertEqual(u1, User.get(username='u1'))
        self.assertEqual(u2, User.get(username='u2'))
        self.assertFalse(u1 == u2)

        self.assertEqual(u1, User.get(User.username == 'u1'))
        self.assertEqual(u2, User.get(User.username == 'u2'))

    def test_deleting(self):
        u1 = self.create_user('u1')
        u2 = self.create_user('u2')

        self.assertEqual(User.select().count(), 2)
        u1.delete_instance()
        self.assertEqual(User.select().count(), 1)

        self.assertEqual(u2, User.get(username='u2'))

    def test_counting(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')

        for u in [u1, u2]:
            for i in range(5):
                Blog.create(title='b-%s-%s' % (u.username, i), user=u)

        uc = User.select().where(User.username == 'u1').join(Blog).count()
        self.assertEqual(uc, 5)

        uc = User.select().where(User.username == 'u1').join(Blog).distinct().count()
        self.assertEqual(uc, 1)

    def test_exists(self):
        u1 = User.create(username='u1')
        self.assertTrue(User.select().where(User.username == 'u1').exists())
        self.assertFalse(User.select().where(User.username == 'u2').exists())

    def test_unicode(self):
        ustr = u'Lýðveldið Ísland'
        u = self.create_user(username=ustr)
        u2 = User.get(User.username == ustr)
        self.assertEqual(u2.username, ustr)


class MultipleFKTestCase(ModelTestCase):
    requires = [User, Relationship]

    def test_multiple_fks(self):
        a = User.create(username='a')
        b = User.create(username='b')
        c = User.create(username='c')

        self.assertEqual(list(a.relationships), [])
        self.assertEqual(list(a.related_to), [])

        r_ab = Relationship.create(from_user=a, to_user=b)
        self.assertEqual(list(a.relationships), [r_ab])
        self.assertEqual(list(a.related_to), [])
        self.assertEqual(list(b.relationships), [])
        self.assertEqual(list(b.related_to), [r_ab])

        r_bc = Relationship.create(from_user=b, to_user=c)

        following = User.select().join(
            Relationship, on=Relationship.to_user
        ).where(Relationship.from_user == a)
        self.assertEqual(list(following), [b])

        followers = User.select().join(
            Relationship, on=Relationship.from_user
        ).where(Relationship.to_user == a.id)
        self.assertEqual(list(followers), [])

        following = User.select().join(
            Relationship, on=Relationship.to_user
        ).where(Relationship.from_user == b.id)
        self.assertEqual(list(following), [c])

        followers = User.select().join(
            Relationship, on=Relationship.from_user
        ).where(Relationship.to_user == b.id)
        self.assertEqual(list(followers), [a])

        following = User.select().join(
            Relationship, on=Relationship.to_user
        ).where(Relationship.from_user == c.id)
        self.assertEqual(list(following), [])

        followers = User.select().join(
            Relationship, on=Relationship.from_user
        ).where(Relationship.to_user == c.id)
        self.assertEqual(list(followers), [b])


class DatabaseFeatureTestCase(ModelTestCase):
    requires = [User, Blog]

    def test_count_transaction(self):
        for i in range(10):
            self.create_user(username='u%d' % i)

        with transaction(test_db):
            for user in SelectQuery(User):
                for i in range(20):
                    Blog.create(user=user, title='b-%d-%d' % (user.id, i))

        count = SelectQuery(Blog).count()
        self.assertEqual(count, 200)


class FieldTypeTestCase(ModelTestCase):
    requires = [NullModel]

    pass
