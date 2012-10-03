# encoding=utf-8

from __future__ import with_statement
import datetime
import logging
import os
import Queue
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

class UserCategory(TestModel):
    user = ForeignKeyField(User)
    category = ForeignKeyField(Category)

class NonIntModel(TestModel):
    pk = CharField(primary_key=True)
    data = CharField()

class NonIntRelModel(TestModel):
    non_int_model = ForeignKeyField(NonIntModel, related_name='nr')

class DBUser(TestModel):
    user_id = PrimaryKeyField(db_column='db_user_id')
    username = CharField(db_column='db_username')

class DBBlog(TestModel):
    blog_id = PrimaryKeyField(db_column='db_blog_id')
    title = CharField(db_column='db_title')
    user = ForeignKeyField(DBUser, db_column='db_user')

class SeqModelA(TestModel):
    id = IntegerField(primary_key=True, sequence='just_testing_seq')
    num = IntegerField()

class SeqModelB(TestModel):
    id = IntegerField(primary_key=True, sequence='just_testing_seq')
    other_num = IntegerField()

class MultiIndexModel(TestModel):
    f1 = CharField()
    f2 = CharField()
    f3 = CharField()

    class Meta:
        indexes = (
            (('f1', 'f2'), True),
            (('f2', 'f3'), False),
        )


MODELS = [User, Blog, Comment, Relationship, NullModel, UniqueModel, OrderedModel, Category, UserCategory,
          NonIntModel, NonIntRelModel, DBUser, DBBlog, SeqModelA, SeqModelB, MultiIndexModel]
INT = test_db.interpolation

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

    def test_join_switching(self):
        class Artist(TestModel):
            pass

        class Track(TestModel):
            artist = ForeignKeyField(Artist)

        class Release(TestModel):
            artist = ForeignKeyField(Artist)

        class ReleaseTrack(TestModel):
            track = ForeignKeyField(Track)
            release = ForeignKeyField(Release)

        class Genre(TestModel):
            pass

        class TrackGenre(TestModel):
            genre = ForeignKeyField(Genre)
            track = ForeignKeyField(Track)

        multiple_first = Track.select().join(ReleaseTrack).join(Release).switch(Track).join(Artist).switch(Track).join(TrackGenre).join(Genre)
        self.assertSelect(multiple_first, 'track."id", track."artist_id"', [])
        self.assertJoins(multiple_first, [
            'INNER JOIN "artist" AS artist ON track."artist_id" = artist."id"',
            'INNER JOIN "genre" AS genre ON trackgenre."genre_id" = genre."id"',
            'INNER JOIN "release" AS release ON releasetrack."release_id" = release."id"',
            'INNER JOIN "releasetrack" AS releasetrack ON track."id" = releasetrack."track_id"',
            'INNER JOIN "trackgenre" AS trackgenre ON track."id" = trackgenre."track_id"',
        ])

        single_first = Track.select().join(Artist).switch(Track).join(ReleaseTrack).join(Release).switch(Track).join(TrackGenre).join(Genre)
        self.assertSelect(single_first, 'track."id", track."artist_id"', [])
        self.assertJoins(single_first, [
            'INNER JOIN "artist" AS artist ON track."artist_id" = artist."id"',
            'INNER JOIN "genre" AS genre ON trackgenre."genre_id" = genre."id"',
            'INNER JOIN "release" AS release ON releasetrack."release_id" = release."id"',
            'INNER JOIN "releasetrack" AS releasetrack ON track."id" = releasetrack."track_id"',
            'INNER JOIN "trackgenre" AS trackgenre ON track."id" = trackgenre."track_id"',
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

    def tearDown(self):
        drop_tables(self.requires)

    def create_user(self, username):
        return User.create(username=username)

    def create_users(self, n):
        for i in range(n):
            self.create_user('u%d' % (i + 1))


class QueryResultWrapperTestCase(ModelTestCase):
    requires = [User, Blog, Comment]

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

    def test_select_related(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        b1 = Blog.create(user=u1, title='b1')
        b2 = Blog.create(user=u2, title='b2')
        c11 = Comment.create(blog=b1, comment='c11')
        c12 = Comment.create(blog=b1, comment='c12')
        c21 = Comment.create(blog=b2, comment='c21')
        c22 = Comment.create(blog=b2, comment='c22')

        # missing comment.blog_id
        qc = len(self.queries())
        comments = Comment.select(Comment.id, Comment.comment, Blog.pk, Blog.title).join(Blog).where(Blog.title == 'b1').order_by(Comment.id)
        self.assertEqual([c.blog.title for c in comments], ['b1', 'b1'])
        self.assertEqual(len(self.queries()) - qc, 1)

        # missing blog.pk
        qc = len(self.queries())
        comments = Comment.select(Comment.id, Comment.comment, Comment.blog, Blog.title).join(Blog).where(Blog.title == 'b2').order_by(Comment.id)
        self.assertEqual([c.blog.title for c in comments], ['b2', 'b2'])
        self.assertEqual(len(self.queries()) - qc, 1)

        # both but going up 2 levels
        qc = len(self.queries())
        comments = Comment.select(Comment, Blog, User).join(Blog).join(User).where(User.username == 'u1').order_by(Comment.id)
        self.assertEqual([c.comment for c in comments], ['c11', 'c12'])
        self.assertEqual([c.blog.title for c in comments], ['b1', 'b1'])
        self.assertEqual([c.blog.user.username for c in comments], ['u1', 'u1'])
        self.assertEqual(len(self.queries()) - qc, 1)

        qc = len(self.queries())
        comments = Comment.select().join(Blog).join(User).where(User.username == 'u1').order_by(Comment.id)
        self.assertEqual([c.blog.user.username for c in comments], ['u1', 'u1'])
        self.assertEqual(len(self.queries()) - qc, 5)

    def test_naive(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        b1 = Blog.create(user=u1, title='b1')
        b2 = Blog.create(user=u2, title='b2')

        users = User.select().naive()
        self.assertEqual([u.username for u in users], ['u1', 'u2'])

        users = User.select(User, Blog).join(Blog).naive()
        self.assertEqual([u.username for u in users], ['u1', 'u2'])
        self.assertEqual([u.title for u in users], ['b1', 'b2'])


class ModelQueryTestCase(ModelTestCase):
    requires = [User, Blog]

    def create_users_blogs(self, n=10, nb=5):
        for i in range(n):
            u = User.create(username='u%d' % i)
            for j in range(nb):
                b = Blog.create(title='b-%d-%d' % (i, j), content=str(j), user=u)

    def test_select(self):
        self.create_users_blogs()

        users = User.select().where(User.username << ['u0', 'u5']).order_by(User.username)
        self.assertEqual([u.username for u in users], ['u0', 'u5'])

        blogs = Blog.select().join(User).where(
            (User.username << ['u0', 'u3']) &
            (Blog.content == '4')
        ).order_by(Blog.title)
        self.assertEqual([b.title for b in blogs], ['b-0-4', 'b-3-4'])

        users = User.select().paginate(2, 3)
        self.assertEqual([u.username for u in users], ['u3', 'u4', 'u5'])

    def test_update(self):
        self.create_users(5)
        uq = User.update(username='u-edited').where(User.username << ['u1', 'u2', 'u3'])
        self.assertEqual([u.username for u in User.select().order_by(User.id)], ['u1', 'u2', 'u3', 'u4', 'u5'])

        uq.execute()
        self.assertEqual([u.username for u in User.select().order_by(User.id)], ['u-edited', 'u-edited', 'u-edited', 'u4', 'u5'])

    def test_insert(self):
        iq = User.insert(username='u1')
        self.assertEqual(User.select().count(), 0)
        uid = iq.execute()
        self.assertTrue(uid > 0)
        self.assertEqual(User.select().count(), 1)
        u = User.get(id=uid)
        self.assertEqual(u.username, 'u1')

    def test_delete(self):
        self.create_users(5)
        dq = User.delete().where(User.username << ['u1', 'u2', 'u3'])
        self.assertEqual(User.select().count(), 5)
        nr = dq.execute()
        self.assertEqual(nr, 3)
        self.assertEqual([u.username for u in User.select()], ['u4', 'u5'])

    def test_raw(self):
        self.create_users(3)

        qc = len(self.queries())
        rq = User.raw('select * from users where username IN (%s,%s)' % (INT,INT), 'u1', 'u3')
        self.assertEqual([u.username for u in rq], ['u1', 'u3'])

        # iterate again
        self.assertEqual([u.username for u in rq], ['u1', 'u3'])
        self.assertEqual(len(self.queries()) - qc, 1)

        rq = User.raw('select id, username, %s as secret from users where username = %s' % (INT,INT), 'sh', 'u2')
        self.assertEqual([u.secret for u in rq], ['sh'])
        self.assertEqual([u.username for u in rq], ['u2'])


class ModelAPITestCase(ModelTestCase):
    requires = [User, Blog, Category, UserCategory]

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

    def test_fk_caching(self):
        c1 = Category.create(name='c1')
        c2 = Category.create(name='c2', parent=c1)
        c2_db = Category.get(Category.id == c2.id)
        qc = len(self.queries())

        parent = c2_db.parent
        self.assertEqual(parent, c1)

        parent = c2_db.parent
        self.assertEqual(len(self.queries()) - qc, 1)

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

    def test_get_or_create(self):
        u1 = User.get_or_create(username='u1')
        u1_x = User.get_or_create(username='u1')
        self.assertEqual(u1.id, u1_x.id)
        self.assertEqual(User.select().count(), 1)

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

    def test_count_transaction(self):
        for i in range(10):
            self.create_user(username='u%d' % i)

        with transaction(test_db):
            for user in SelectQuery(User):
                for i in range(20):
                    Blog.create(user=user, title='b-%d-%d' % (user.id, i))

        count = SelectQuery(Blog).count()
        self.assertEqual(count, 200)

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


class ManyToManyTestCase(ModelTestCase):
    requires = [User, Category, UserCategory]

    def test_m2m(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        u3 = User.create(username='u3')

        c1 = Category.create(name='c1')
        c2 = Category.create(name='c2')
        c3 = Category.create(name='c3')

        # extras
        c12 = Category.create(name='c12')
        c23 = Category.create(name='c23')

        umap = (
            (u1, c1),
            (u2, c2),
            (u1, c12),
            (u2, c12),
            (u2, c23),
        )

        for u, c in umap:
            UserCategory.create(user=u, category=c)

        def aU(q, exp):
            self.assertEqual([u.username for u in q.order_by(User.username)], exp)
        def aC(q, exp):
            self.assertEqual([c.name for c in q.order_by(Category.name)], exp)

        users = User.select().join(UserCategory).join(Category).where(Category.name == 'c1')
        aU(users, ['u1'])

        users = User.select().join(UserCategory).join(Category).where(Category.name == 'c3')
        aU(users, [])

        cats = Category.select().join(UserCategory).join(User).where(User.username == 'u1')
        aC(cats, ['c1', 'c12'])

        cats = Category.select().join(UserCategory).join(User).where(User.username == 'u2')
        aC(cats, ['c12', 'c2', 'c23'])

        cats = Category.select().join(UserCategory).join(User).where(User.username == 'u3')
        aC(cats, [])

        cats = Category.select().join(UserCategory).join(User).where(
            Category.name << ['c1', 'c2', 'c3']
        )
        aC(cats, ['c1', 'c2'])

        cats = Category.select().join(UserCategory, JOIN_LEFT_OUTER).join(User, JOIN_LEFT_OUTER).where(
            Category.name << ['c1', 'c2', 'c3']
        )
        aC(cats, ['c1', 'c2', 'c3'])


class FieldTypeTestCase(ModelTestCase):
    requires = [NullModel]

    _dt = datetime.datetime
    _d = datetime.date
    _t = datetime.time

    _data = (
        ('char_field', 'text_field', 'int_field', 'float_field', 'decimal_field1', 'datetime_field', 'date_field', 'time_field'),
        ('c1',         't1',         1,           1.0,           "1.0",            _dt(2010, 1, 1),  _d(2010, 1, 1), _t(1, 0)),
        ('c2',         't2',         2,           2.0,           "2.0",            _dt(2010, 1, 2),  _d(2010, 1, 2), _t(2, 0)),
        ('c3',         't3',         3,           3.0,           "3.0",            _dt(2010, 1, 3),  _d(2010, 1, 3), _t(3, 0)),
    )

    def setUp(self):
        super(FieldTypeTestCase, self).setUp()
        self.field_data = {}

        headers = self._data[0]
        for row in self._data[1:]:
            nm = NullModel()
            for i, col in enumerate(row):
                attr = headers[i]
                self.field_data.setdefault(attr, [])
                self.field_data[attr].append(col)
                setattr(nm, attr, col)
            nm.save()

    def assertNM(self, q, exp):
        query = NullModel.select().where(q).order_by(NullModel.id)
        self.assertEqual([nm.char_field for nm in query], exp)

    def test_field_types(self):
        for field, values in self.field_data.items():
            field_obj = getattr(NullModel, field)
            self.assertNM(field_obj < values[2], ['c1', 'c2'])
            self.assertNM(field_obj <= values[1], ['c1', 'c2'])
            self.assertNM(field_obj > values[0], ['c2', 'c3'])
            self.assertNM(field_obj >= values[1], ['c2', 'c3'])
            self.assertNM(field_obj == values[1], ['c2'])
            self.assertNM(field_obj != values[1], ['c1', 'c3'])
            self.assertNM(field_obj << [values[0], values[2]], ['c1', 'c3'])
            self.assertNM(field_obj << [values[1]], ['c2'])

    def test_charfield(self):
        nm = NullModel.create(char_field=4)
        nm_db = NullModel.get(id=nm.id)
        self.assertEqual(nm_db.char_field, '4')

    def test_intfield(self):
        nm = NullModel.create(int_field='4')
        nm_db = NullModel.get(id=nm.id)
        self.assertEqual(nm_db.int_field, 4)

    def test_floatfield(self):
        nm = NullModel.create(float_field='4.2')
        nm_db = NullModel.get(id=nm.id)
        self.assertEqual(nm_db.float_field, 4.2)

    def test_decimalfield(self):
        D = Decimal
        nm = NullModel()
        nm.decimal_field1 = D("3.14159265358979323")
        nm.decimal_field2 = D("100.33")
        nm.save()

        nm_from_db = NullModel.get(id=nm.id)
        # sqlite doesn't enforce these constraints properly
        #self.assertEqual(nm_from_db.decimal_field1, decimal.Decimal("3.14159"))
        self.assertEqual(nm_from_db.decimal_field2, D("100.33"))

        class TestDecimalModel(TestModel):
            df1 = DecimalField(decimal_places=2, auto_round=True)
            df2 = DecimalField(decimal_places=2, auto_round=True, rounding=decimal.ROUND_UP)

        f1 = TestDecimalModel.df1.db_value
        f2 = TestDecimalModel.df2.db_value

        self.assertEqual(f1(D('1.2345')), D('1.23'))
        self.assertEqual(f2(D('1.2345')), D('1.24'))

    def test_boolfield(self):
        NullModel.delete().execute()

        nmt = NullModel.create(boolean_field=True, char_field='t')
        nmf = NullModel.create(boolean_field=False, char_field='f')
        nmn = NullModel.create(boolean_field=None, char_field='n')

        self.assertNM(NullModel.boolean_field == True, ['t'])
        self.assertNM(NullModel.boolean_field == False, ['f'])
        self.assertNM(NullModel.boolean_field >> None, ['n'])

    def test_date_and_time_fields(self):
        dt1 = datetime.datetime(2011, 1, 2, 11, 12, 13, 54321)
        dt2 = datetime.datetime(2011, 1, 2, 11, 12, 13)
        d1 = datetime.date(2011, 1, 3)
        t1 = datetime.time(11, 12, 13, 54321)
        t2 = datetime.time(11, 12, 13)

        nm1 = NullModel.create(datetime_field=dt1, date_field=d1, time_field=t1)
        nm2 = NullModel.create(datetime_field=dt2, time_field=t2)

        nmf1 = NullModel.get(id=nm1.id)
        self.assertEqual(nmf1.date_field, d1)
        if BACKEND == 'mysql':
            # mysql doesn't store microseconds
            self.assertEqual(nmf1.datetime_field, dt2)
            self.assertEqual(nmf1.time_field, t2)
        else:
            self.assertEqual(nmf1.datetime_field, dt1)
            self.assertEqual(nmf1.time_field, t1)

        nmf2 = NullModel.get(id=nm2.id)
        self.assertEqual(nmf2.datetime_field, dt2)
        self.assertEqual(nmf2.time_field, t2)

    def test_various_formats(self):
        class FormatModel(Model):
            dtf = DateTimeField()
            df = DateField()
            tf = TimeField()

        dtf = FormatModel._meta.fields['dtf']
        df = FormatModel._meta.fields['df']
        tf = FormatModel._meta.fields['tf']

        d = datetime.datetime
        self.assertEqual(dtf.python_value('2012-01-01 11:11:11.123456'), d(
            2012, 1, 1, 11, 11, 11, 123456
        ))
        self.assertEqual(dtf.python_value('2012-01-01 11:11:11'), d(
            2012, 1, 1, 11, 11, 11
        ))
        self.assertEqual(dtf.python_value('2012-01-01'), d(
            2012, 1, 1,
        ))
        self.assertEqual(dtf.python_value('2012 01 01'), '2012 01 01')

        d = datetime.date
        self.assertEqual(df.python_value('2012-01-01 11:11:11.123456'), d(
            2012, 1, 1,
        ))
        self.assertEqual(df.python_value('2012-01-01 11:11:11'), d(
            2012, 1, 1,
        ))
        self.assertEqual(df.python_value('2012-01-01'), d(
            2012, 1, 1,
        ))
        self.assertEqual(df.python_value('2012 01 01'), '2012 01 01')

        t = datetime.time
        self.assertEqual(tf.python_value('2012-01-01 11:11:11.123456'), t(
            11, 11, 11, 123456
        ))
        self.assertEqual(tf.python_value('2012-01-01 11:11:11'), t(
            11, 11, 11
        ))
        self.assertEqual(tf.python_value('11:11:11.123456'), t(
            11, 11, 11, 123456
        ))
        self.assertEqual(tf.python_value('11:11:11'), t(
            11, 11, 11
        ))
        self.assertEqual(tf.python_value('11:11'), t(
            11, 11,
        ))
        self.assertEqual(tf.python_value('11:11 AM'), '11:11 AM')

        class CustomFormatsModel(Model):
            dtf = DateTimeField(formats=['%b %d, %Y %I:%M:%S %p'])
            df = DateField(formats=['%b %d, %Y'])
            tf = TimeField(formats=['%I:%M %p'])

        dtf = CustomFormatsModel._meta.fields['dtf']
        df = CustomFormatsModel._meta.fields['df']
        tf = CustomFormatsModel._meta.fields['tf']

        d = datetime.datetime
        self.assertEqual(dtf.python_value('2012-01-01 11:11:11.123456'), '2012-01-01 11:11:11.123456')
        self.assertEqual(dtf.python_value('Jan 1, 2012 11:11:11 PM'), d(
            2012, 1, 1, 23, 11, 11,
        ))

        d = datetime.date
        self.assertEqual(df.python_value('2012-01-01'), '2012-01-01')
        self.assertEqual(df.python_value('Jan 1, 2012'), d(
            2012, 1, 1,
        ))

        t = datetime.time
        self.assertEqual(tf.python_value('11:11:11'), '11:11:11')
        self.assertEqual(tf.python_value('11:11 PM'), t(
            23, 11
        ))


class UniqueTestCase(ModelTestCase):
    requires = [UniqueModel, MultiIndexModel]

    def test_unique(self):
        uniq1 = UniqueModel.create(name='a')
        uniq2 = UniqueModel.create(name='b')
        self.assertRaises(Exception, UniqueModel.create, name='a')
        test_db.rollback()

    def test_multi_index(self):
        mi1 = MultiIndexModel.create(f1='a', f2='a', f3='a')
        mi2 = MultiIndexModel.create(f1='b', f2='b', f3='b')
        self.assertRaises(Exception, MultiIndexModel.create, f1='a', f2='a', f3='b')
        test_db.rollback()
        self.assertRaises(Exception, MultiIndexModel.create, f1='b', f2='b', f3='a')
        test_db.rollback()

        mi3 = MultiIndexModel.create(f1='a', f2='b', f3='b')


class NonIntPKTestCase(ModelTestCase):
    requires = [NonIntModel, NonIntRelModel]

    def test_non_int_pk(self):
        ni1 = NonIntModel.create(pk='a1', data='ni1')
        self.assertEqual(ni1.pk, 'a1')

        ni2 = NonIntModel(pk='a2', data='ni2')
        ni2.save(force_insert=True)
        self.assertEqual(ni2.pk, 'a2')

        ni2.save()
        self.assertEqual(ni2.pk, 'a2')

        self.assertEqual(NonIntModel.select().count(), 2)

        ni1_db = NonIntModel.get(pk='a1')
        self.assertEqual(ni1_db.data, ni1.data)

        self.assertEqual([(x.pk, x.data) for x in NonIntModel.select().order_by(NonIntModel.pk)], [
            ('a1', 'ni1'), ('a2', 'ni2'),
        ])

    def test_non_int_fk(self):
        ni1 = NonIntModel.create(pk='a1', data='ni1')
        ni2 = NonIntModel.create(pk='a2', data='ni2')

        rni11 = NonIntRelModel(non_int_model=ni1)
        rni12 = NonIntRelModel(non_int_model=ni1)
        rni11.save()
        rni12.save()

        self.assertEqual([r.id for r in ni1.nr.order_by(NonIntRelModel.id)], [rni11.id, rni12.id])
        self.assertEqual([r.id for r in ni2.nr.order_by(NonIntRelModel.id)], [])

        rni21 = NonIntRelModel.create(non_int_model=ni2)
        self.assertEqual([r.id for r in ni2.nr.order_by(NonIntRelModel.id)], [rni21.id])

        sq = NonIntRelModel.select().join(NonIntModel).where(NonIntModel.data == 'ni2')
        self.assertEqual([r.id for r in sq], [rni21.id])


class DBColumnTestCase(ModelTestCase):
    requires = [DBUser, DBBlog]

    def test_select(self):
        sq = DBUser.select().where(DBUser.username == 'u1')
        self.assertSelect(sq, 'dbuser."db_user_id", dbuser."db_username"', [])
        self.assertWhere(sq, 'dbuser."db_username" = ?', ['u1'])

        sq = DBUser.select(DBUser.user_id).join(DBBlog).where(DBBlog.title == 'b1')
        self.assertSelect(sq, 'dbuser."db_user_id"', [])
        self.assertJoins(sq, ['INNER JOIN "dbblog" AS dbblog ON dbuser."db_user_id" = dbblog."db_user"'])
        self.assertWhere(sq, 'dbblog."db_title" = ?', ['b1'])

    def test_db_column(self):
        u1 = DBUser.create(username='u1')
        u2 = DBUser.create(username='u2')
        u2_db = DBUser.get(user_id=u2.get_id())
        self.assertEqual(u2_db.username, 'u2')

        b1 = DBBlog.create(user=u1, title='b1')
        b2 = DBBlog.create(user=u2, title='b2')
        b2_db = DBBlog.get(blog_id=b2.get_id())
        self.assertEqual(b2_db.user.user_id, u2.user_id)
        self.assertEqual(b2_db.title, 'b2')
        
        self.assertEqual([b.title for b in u2.dbblog_set], ['b2'])


class TransactionTestCase(ModelTestCase):
    requires = [User, Blog]

    def tearDown(self):
        super(TransactionTestCase, self).tearDown()
        test_db.set_autocommit(True)

    def test_autocommit(self):
        test_db.set_autocommit(False)

        u1 = User.create(username='u1')
        u2 = User.create(username='u2')

        # open up a new connection to the database, it won't register any blogs
        # as being created
        new_db = database_class(database_name)
        res = new_db.execute_sql('select count(*) from users;')
        self.assertEqual(res.fetchone()[0], 0)

        # commit our blog inserts
        test_db.commit()

        # now the blogs are query-able from another connection
        res = new_db.execute_sql('select count(*) from users;')
        self.assertEqual(res.fetchone()[0], 2)

    def test_commit_on_success(self):
        self.assertTrue(test_db.get_autocommit())

        @test_db.commit_on_success
        def will_fail():
            u = User.create(username='u1')
            b = Blog.create() # no blog, will raise an error
            return u, b

        self.assertRaises(Exception, will_fail)
        self.assertEqual(User.select().count(), 0)
        self.assertEqual(Blog.select().count(), 0)

        @test_db.commit_on_success
        def will_succeed():
            u = User.create(username='u1')
            b = Blog.create(title='b1', user=u)
            return u, b

        u, b = will_succeed()
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(Blog.select().count(), 1)

    def test_context_mgr(self):
        def will_fail():
            u = User.create(username='u1')
            b = Blog.create() # no blog, will raise an error
            return u, b

        def do_will_fail():
            with transaction(test_db):
                will_fail()

        def do_will_fail2():
            with test_db.transaction():
                will_fail()

        self.assertRaises(Exception, do_will_fail)
        self.assertEqual(Blog.select().count(), 0)

        self.assertRaises(Exception, do_will_fail2)
        self.assertEqual(Blog.select().count(), 0)

        def will_succeed():
            u = User.create(username='u1')
            b = Blog.create(title='b1', user=u)
            return u, b

        def do_will_succeed():
            with transaction(test_db):
                will_succeed()

        def do_will_succeed2():
            with test_db.transaction():
                will_succeed()

        do_will_succeed()
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(Blog.select().count(), 1)

        do_will_succeed2()
        self.assertEqual(User.select().count(), 2)
        self.assertEqual(Blog.select().count(), 2)


class ConcurrencyTestCase(ModelTestCase):
    requires = [User]

    def setUp(self):
        self._orig_db = test_db
        User._meta.database = database_class(database_name, threadlocals=True)
        super(ConcurrencyTestCase, self).setUp()

    def tearDown(self):
        User._meta.database = self._orig_db
        super(ConcurrencyTestCase, self).tearDown()

    def test_multiple_writers(self):
        def create_user_thread(low, hi):
            for i in range(low, hi):
                User.create(username='u%d' % i)
            User._meta.database.close()

        threads = []

        for i in range(5):
            threads.append(threading.Thread(target=create_user_thread, args=(i*10, i * 10 + 10)))

        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(User.select().count(), 50)

    def test_multiple_readers(self):
        data_queue = Queue.Queue()

        def reader_thread(q, num):
            for i in range(num):
                data_queue.put(User.select().count())

        threads = []

        for i in range(5):
            threads.append(threading.Thread(target=reader_thread, args=(data_queue, 20)))

        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(data_queue.qsize(), 100)


class ModelInheritanceTestCase(BasePeeweeTestCase):
    # TODO
    pass


class DatabaseTestCase(BasePeeweeTestCase):
    def test_deferred_database(self):
        deferred_db = SqliteDatabase(None)
        self.assertTrue(deferred_db.deferred)

        class DeferredModel(Model):
            class Meta:
                database = deferred_db

        self.assertRaises(Exception, deferred_db.connect)
        sq = DeferredModel.select()
        self.assertRaises(Exception, sq.execute)

        deferred_db.init(':memory:')
        self.assertFalse(deferred_db.deferred)

        # connecting works
        conn = deferred_db.connect()
        DeferredModel.create_table()
        sq = DeferredModel.select()
        self.assertEqual(list(sq), [])

        deferred_db.init(None)
        self.assertTrue(deferred_db.deferred)


class ConnectionStateTestCase(BasePeeweeTestCase):
    def test_connection_state(self):
        conn = test_db.get_conn()
        self.assertFalse(test_db.is_closed())
        test_db.close()
        self.assertTrue(test_db.is_closed())
        conn = test_db.get_conn()
        self.assertFalse(test_db.is_closed())


if test_db.for_update:
    class ForUpdateTestCase(ModelTestCase):
        requires = [User]

        def tearDown(self):
            test_db.set_autocommit(True)

        def test_for_update(self):
            u1 = self.create_user('u1')
            u2 = self.create_user('u2')
            u3 = self.create_user('u3')

            test_db.set_autocommit(False)

            # select a user for update
            users = User.select().where(User.username == 'u1').for_update()
            updated = User.update(username='u1_edited').where(User.username == 'u1').execute()
            self.assertEqual(updated, 1)

            # open up a new connection to the database
            new_db = database_class(database_name)

            # select the username, it will not register as being updated
            res = new_db.execute_sql('select username from users where id = %s;' % u1.id)
            username = res.fetchone()[0]
            self.assertEqual(username, 'u1')

            # committing will cause the lock to be released
            test_db.commit()

            # now we get the update
            res = new_db.execute_sql('select username from users where id = %s;' % u1.id)
            username = res.fetchone()[0]
            self.assertEqual(username, 'u1_edited')

elif TEST_VERBOSITY > 0:
    print 'Skipping "for update" tests'

if test_db.sequences:
    class SequenceTestCase(ModelTestCase):
        requires = [SeqModelA, SeqModelB]

        def test_sequence_shared(self):
            a1 = SeqModelA.create(num=1)
            a2 = SeqModelA.create(num=2)
            b1 = SeqModelB.create(other_num=101)
            b2 = SeqModelB.create(other_num=102)
            a3 = SeqModelA.create(num=3)

            self.assertEqual(a1.id, a2.id - 1)
            self.assertEqual(a2.id, b1.id - 1)
            self.assertEqual(b1.id, b2.id - 1)
            self.assertEqual(b2.id, a3.id - 1)

elif TEST_VERBOSITY > 0:
    print 'Skipping "sequence" tests'
