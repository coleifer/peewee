# encoding=utf-8

import datetime
import decimal
import itertools
import logging
import operator
import os
import threading
import unittest
import sys
try:
    from Queue import Queue
except ImportError:
    from queue import Queue
from functools import wraps

from peewee import *
from peewee import AliasMap
from peewee import DeleteQuery
from peewee import InsertQuery
from peewee import logger
from peewee import ModelQueryResultWrapper
from peewee import NaiveQueryResultWrapper
from peewee import prefetch_add_subquery
from peewee import print_
from peewee import QueryCompiler
from peewee import R
from peewee import RawQuery
from peewee import SelectQuery
from peewee import sort_models_topologically
from peewee import transaction
from peewee import UpdateQuery

class QueryLogHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        self.queries = []
        logging.Handler.__init__(self, *args, **kwargs)

    def emit(self, record):
        self.queries.append(record)

if sys.version_info[0] < 3:
    import codecs
    ulit = lambda s: codecs.unicode_escape_decode(s)[0]
    binary_construct = buffer
    binary_types = buffer
else:
    ulit = lambda s: s
    binary_construct = lambda s: bytes(s.encode('raw_unicode_escape'))
    binary_types = (bytes, memoryview)

#
# JUNK TO ALLOW TESTING OF MULTIPLE DATABASE BACKENDS
#

BACKEND = os.environ.get('PEEWEE_TEST_BACKEND', 'sqlite')
TEST_VERBOSITY = int(os.environ.get('PEEWEE_TEST_VERBOSITY') or 1)

if TEST_VERBOSITY > 1:
    handler = logging.StreamHandler()
    handler.setLevel(logging.ERROR)
    logger.addHandler(handler)

database_params = {}

print_('TESTING USING PYTHON %s' % sys.version)

BerkeleyDatabase = None
if BACKEND in ('postgresql', 'postgres', 'pg'):
    database_class = PostgresqlDatabase
    database_name = 'peewee_test'
    import psycopg2
elif BACKEND == 'mysql':
    database_class = MySQLDatabase
    database_name = 'peewee_test'
    try:
        import MySQLdb as mysql
    except ImportError:
        import pymysql as mysql
elif BACKEND == 'apsw':
    from playhouse.apsw_ext import *
    database_class = APSWDatabase
    database_name = 'tmp.db'
    database_params['timeout'] = 1000
elif BACKEND in ('berkeleydb', 'berkeley', 'bdb'):
    from playhouse.berkeleydb import *
    database_class = BerkeleyDatabase
    database_name = 'tmp.bdb.db'
    database_params['timeout'] = 1000
elif BACKEND == 'sqlcipher':
    from playhouse.sqlcipher_ext import *
    database_class = SqlCipherDatabase
    database_name = 'tmp-snakeoilpassphrase.db'
    database_params['passphrase'] = 'snakeoilpassphrase'
    from pysqlcipher import dbapi2 as sqlcipher
    print_('PYSQLCIPHER VERSION: %s' % sqlcipher.version)
else:
    database_class = SqliteDatabase
    database_name = 'tmp.db'
    import sqlite3
    print_('SQLITE VERSION: %s' % sqlite3.version)

#
# TEST-ONLY QUERY COMPILER USED TO CREATE "predictable" QUERIES
#

class TestAliasMap(AliasMap):
    def add(self, obj, alias=None):
        self._alias_map[obj] = obj._meta.db_table

class TestQueryCompiler(QueryCompiler):
    alias_map_class = TestAliasMap

class TestDatabase(database_class):
    compiler_class = TestQueryCompiler
    field_overrides = {}
    interpolation = '?'
    op_overrides = {}
    quote_char = '"'

    def sql_error_handler(self, exception, sql, params, require_commit):
        self.last_error = (sql, params)
        return super(TestDatabase, self).sql_error_handler(
            exception, sql, params, require_commit)

test_db = database_class(database_name, **database_params)
query_db = TestDatabase(database_name, **database_params)
compiler = query_db.compiler()

# create a compiler we can use to test that will generate increasing aliases
# this is used to test self-referential joins
normal_compiler = QueryCompiler('"', '?', {}, {})

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

    def prepared(self):
        self.foo = self.username

class Blog(TestModel):
    user = ForeignKeyField(User)
    title = CharField(max_length=25)
    content = TextField(default='')
    pub_date = DateTimeField(null=True)
    pk = PrimaryKeyField()

    def __unicode__(self):
        return '%s: %s' % (self.user.username, self.title)

    def prepared(self):
        self.foo = self.title

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

class BlogTwo(Blog):
    title = TextField()
    extra_field = CharField()


class Parent(TestModel):
    data = CharField()

class Child(TestModel):
    parent = ForeignKeyField(Parent)
    data = CharField(default='')

class Orphan(TestModel):
    parent = ForeignKeyField(Parent, null=True)
    data = CharField(default='')

class ChildPet(TestModel):
    child = ForeignKeyField(Child)
    data = CharField(default='')

class OrphanPet(TestModel):
    orphan = ForeignKeyField(Orphan)
    data = CharField(default='')

class CSVField(TextField):
    def db_value(self, value):
        if value:
            return ','.join(value)
        return value or ''

    def python_value(self, value):
        return value.split(',') if value else []

class CSVRow(TestModel):
    data = CSVField()

class BlobModel(TestModel):
    data = BlobField()

class Job(TestModel):
    """A job that can be queued for later execution."""
    name = CharField()

class JobExecutionRecord(TestModel):
    """Record of a job having been executed."""
    # the foreign key is also the primary key to enforce the
    # constraint that a job can be executed once and only once
    job = ForeignKeyField(Job, primary_key=True)
    status = CharField()

class TestModelA(TestModel):
    field = CharField(primary_key=True)
    data = CharField()

class TestModelB(TestModel):
    field = CharField(primary_key=True)
    data = CharField()

class TestModelC(TestModel):
    field = CharField(primary_key=True)
    data = CharField()

class Post(TestModel):
    title = CharField()

class Tag(TestModel):
    tag = CharField()

class TagPostThrough(TestModel):
    tag = ForeignKeyField(Tag, related_name='posts')
    post = ForeignKeyField(Post, related_name='tags')

    class Meta:
        primary_key = CompositeKey('tag', 'post')

class Manufacturer(TestModel):
    name = CharField()

class CompositeKeyModel(TestModel):
    f1 = CharField()
    f2 = IntegerField()
    f3 = FloatField()

    class Meta:
        primary_key = CompositeKey('f1', 'f2')

class UserThing(TestModel):
    thing = CharField()
    user = ForeignKeyField(User, related_name='things')

    class Meta:
        primary_key = CompositeKey('thing', 'user')

class Component(TestModel):
    name = CharField()
    manufacturer = ForeignKeyField(Manufacturer, null=True)

class Computer(TestModel):
    hard_drive = ForeignKeyField(Component, related_name='c1')
    memory = ForeignKeyField(Component, related_name='c2')
    processor = ForeignKeyField(Component, related_name='c3')

class CheckModel(TestModel):
    value = IntegerField(constraints=[Check('value > 0')])

# Deferred foreign keys.
SnippetProxy = Proxy()

class Language(TestModel):
    name = CharField()
    selected_snippet = ForeignKeyField(SnippetProxy, null=True)

class Snippet(TestModel):
    code = TextField()
    language = ForeignKeyField(Language, related_name='snippets')

SnippetProxy.initialize(Snippet)

class _UpperField(CharField):
    def python_value(self, value):
        return value.upper() if value else value

class UpperUser(TestModel):
    username = _UpperField()
    class Meta:
        db_table = User._meta.db_table

class Package(TestModel):
    barcode = CharField(unique=True)

class PackageItem(TestModel):
    title = CharField()
    package = ForeignKeyField(
        Package,
        related_name='items',
        to_field=Package.barcode)


MODELS = [
    User,
    Blog,
    Comment,
    Relationship,
    NullModel,
    UniqueModel,
    OrderedModel,
    Category,
    UserCategory,
    NonIntModel,
    NonIntRelModel,
    DBUser,
    DBBlog,
    SeqModelA,
    SeqModelB,
    MultiIndexModel,
    BlogTwo,
    Parent,
    Child,
    Orphan,
    ChildPet,
    OrphanPet,
    BlobModel,
    Job,
    JobExecutionRecord,
    TestModelA,
    TestModelB,
    TestModelC,
    Tag,
    Post,
    TagPostThrough,
    Language,
    Snippet,
    Manufacturer,
    CompositeKeyModel,
    UserThing,
    Component,
    Computer,
    CheckModel,
    Package,
    PackageItem,
]
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

    def parse_node(self, query, expr_list, compiler=compiler):
        am = compiler.calculate_alias_map(query)
        return compiler.parse_node_list(expr_list, am)

    def parse_query(self, query, node, compiler=compiler):
        am = compiler.calculate_alias_map(query)
        if node is not None:
            return compiler.parse_node(node, am)
        return '', []

    def make_fn(fn_name, attr_name):
        def inner(self, query, expected, expected_params, compiler=compiler):
            fn = getattr(self, fn_name)
            att = getattr(query, attr_name)
            sql, params = fn(query, att, compiler=compiler)
            self.assertEqual(sql, expected)
            self.assertEqual(params, expected_params)
        return inner

    assertSelect = make_fn('parse_node', '_select')
    assertWhere = make_fn('parse_query', '_where')
    assertGroupBy = make_fn('parse_node', '_group_by')
    assertHaving = make_fn('parse_query', '_having')
    assertOrderBy = make_fn('parse_node', '_order_by')

    def assertJoins(self, sq, exp_joins, compiler=compiler):
        am = compiler.calculate_alias_map(sq)
        clauses = compiler.generate_joins(sq._joins, sq.model_class, am)
        joins = [compiler.parse_node(clause, am)[0] for clause in clauses]
        self.assertEqual(sorted(joins), sorted(exp_joins))

#
# BASIC TESTS OF QUERY TYPES AND INTERNAL DATA STRUCTURES
#

class SelectTestCase(BasePeeweeTestCase):
    def test_selection(self):
        sq = SelectQuery(User)
        self.assertSelect(sq, 'users."id", users."username"', [])

        sq = SelectQuery(Blog, Blog.pk, Blog.title, Blog.user, User.username).join(User)
        self.assertSelect(sq, 'blog."pk", blog."title", blog."user_id", users."username"', [])

        sq = SelectQuery(User, fn.Lower(fn.Substr(User.username, 0, 1)).alias('lu'), fn.Count(Blog.pk)).join(Blog)
        self.assertSelect(sq, 'Lower(Substr(users."username", ?, ?)) AS lu, Count(blog."pk")', [0, 1])

        sq = SelectQuery(User, User.username, fn.Count(Blog.select().where(Blog.user == User.id)))
        self.assertSelect(sq, 'users."username", Count(SELECT blog."pk" FROM "blog" AS blog WHERE (blog."user_id" = users."id"))', [])

        sq = SelectQuery(Package, Package, fn.Count(PackageItem.id)).join(PackageItem)
        self.assertSelect(sq, 'package."id", package."barcode", Count(packageitem."id")', [])

    def test_select_distinct(self):
        sq = SelectQuery(User).distinct()
        self.assertEqual(
            compiler.generate_select(sq),
            ('SELECT DISTINCT users."id", users."username" '
             'FROM "users" AS users', []))

        sq = sq.distinct(False)
        self.assertEqual(
            compiler.generate_select(sq),
            ('SELECT users."id", users."username" FROM "users" AS users', []))

        sq = SelectQuery(User).distinct([User.username])
        self.assertEqual(
            compiler.generate_select(sq),
            ('SELECT DISTINCT ON (users."username") users."id", '
             'users."username" '
             'FROM "users" AS users', []))

    def test_reselect(self):
        sq = SelectQuery(User, User.username)
        self.assertSelect(sq, 'users."username"', [])

        sq2 = sq.select()
        self.assertSelect(sq2, 'users."id", users."username"', [])
        self.assertTrue(id(sq) != id(sq2))

        sq3 = sq2.select(User.id)
        self.assertSelect(sq3, 'users."id"', [])
        self.assertTrue(id(sq2) != id(sq3))

    def test_select_subquery(self):
        subquery = SelectQuery(Child, fn.Count(Child.id)).where(Child.parent == Parent.id).group_by(Child.parent)
        sq = SelectQuery(Parent, Parent, subquery.alias('count'))

        sql = compiler.generate_select(sq)
        self.assertEqual(sql, (
            'SELECT parent."id", parent."data", ' + \
            '(SELECT Count(child."id") FROM "child" AS child ' + \
            'WHERE (child."parent_id" = parent."id") GROUP BY child."parent_id") ' + \
            'AS count FROM "parent" AS parent', []
        ))

    def test_select_subquery_ordering(self):
        sq = Comment.select().join(Blog).where(Blog.pk == 1)
        sq1 = Comment.select().where(
            (Comment.id << sq) |
            (Comment.comment == '*')
        )
        sq2 = Comment.select().where(
            (Comment.comment == '*') |
            (Comment.id << sq)
        )

        sql1, params1 = normal_compiler.generate_select(sq1)
        self.assertEqual(sql1, (
            'SELECT t1."id", t1."blog_id", t1."comment" FROM "comment" AS t1 '
            'WHERE ((t1."id" IN ('
            'SELECT t2."id" FROM "comment" AS t2 '
            'INNER JOIN "blog" AS t3 ON (t2."blog_id" = t3."pk") '
            'WHERE (t3."pk" = ?))) OR (t1."comment" = ?))'))
        self.assertEqual(params1, [1, '*'])

        sql2, params2 = normal_compiler.generate_select(sq2)
        self.assertEqual(sql2, (
            'SELECT t1."id", t1."blog_id", t1."comment" FROM "comment" AS t1 '
            'WHERE ((t1."comment" = ?) OR (t1."id" IN ('
            'SELECT t2."id" FROM "comment" AS t2 '
            'INNER JOIN "blog" AS t3 ON (t2."blog_id" = t3."pk") '
            'WHERE (t3."pk" = ?))))'))
        self.assertEqual(params2, ['*', 1])

    def test_multiple_subquery(self):
        sq2 = Comment.select().where(Comment.comment == '2').join(Blog)
        sq1 = Comment.select().where(
            (Comment.comment == '1') &
            (Comment.id << sq2)
        ).join(Blog)
        sq = Comment.select().where(
            Comment.id << sq1
        )
        sql, params = normal_compiler.generate_select(sq)
        self.assertEqual(sql, (
            'SELECT t1."id", t1."blog_id", t1."comment" '
            'FROM "comment" AS t1 '
            'WHERE (t1."id" IN ('
            'SELECT t2."id" FROM "comment" AS t2 '
            'INNER JOIN "blog" AS t3 ON (t2."blog_id" = t3."pk") '
            'WHERE ((t2."comment" = ?) AND (t2."id" IN ('
            'SELECT t4."id" FROM "comment" AS t4 '
            'INNER JOIN "blog" AS t5 ON (t4."blog_id" = t5."pk") '
            'WHERE (t4."comment" = ?)'
            ')))))'))
        self.assertEqual(params, ['1', '2'])

    def test_select_cloning(self):
        ct = fn.Count(Blog.pk)
        sq = SelectQuery(User, User, User.id.alias('extra_id'), ct.alias('blog_ct')).join(
            Blog, JOIN_LEFT_OUTER).group_by(User).order_by(ct.desc())
        sql = compiler.generate_select(sq)
        self.assertEqual(sql, (
            'SELECT users."id", users."username", users."id" AS extra_id, Count(blog."pk") AS blog_ct ' + \
            'FROM "users" AS users LEFT OUTER JOIN "blog" AS blog ON (users."id" = blog."user_id") ' + \
            'GROUP BY users."id", users."username" ' + \
            'ORDER BY Count(blog."pk") DESC', []
        ))
        self.assertEqual(User.id._alias, None)

    def test_joins(self):
        sq = SelectQuery(User).join(Blog)
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON (users."id" = blog."user_id")'])

        sq = SelectQuery(Blog).join(User, JOIN_LEFT_OUTER)
        self.assertJoins(sq, ['LEFT OUTER JOIN "users" AS users ON (blog."user_id" = users."id")'])

        sq = SelectQuery(User).join(Relationship)
        self.assertJoins(sq, ['INNER JOIN "relationship" AS relationship ON (users."id" = relationship."from_user_id")'])

        sq = SelectQuery(User).join(Relationship, on=Relationship.to_user)
        self.assertJoins(sq, ['INNER JOIN "relationship" AS relationship ON (users."id" = relationship."to_user_id")'])

        sq = SelectQuery(User).join(Relationship, JOIN_LEFT_OUTER, Relationship.to_user)
        self.assertJoins(sq, ['LEFT OUTER JOIN "relationship" AS relationship ON (users."id" = relationship."to_user_id")'])

        sq = SelectQuery(Package).join(PackageItem)
        self.assertJoins(sq, ['INNER JOIN "packageitem" AS packageitem ON (package."barcode" = packageitem."package_id")'])

        sq = SelectQuery(PackageItem).join(Package)
        self.assertJoins(sq, ['INNER JOIN "package" AS package ON (packageitem."package_id" = package."barcode")'])

    def test_join_self_referential(self):
        sq = SelectQuery(Category).join(Category)
        self.assertJoins(sq, ['INNER JOIN "category" AS category ON (category."parent_id" = category."id")'])

    def test_join_self_referential_alias(self):
        Parent = Category.alias()
        sq = SelectQuery(Category, Category, Parent).join(Parent, on=(Category.parent == Parent.id)).where(
            Parent.name == 'parent name'
        ).order_by(Parent.name)
        self.assertSelect(sq, 't1."id", t1."parent_id", t1."name", t2."id", t2."parent_id", t2."name"', [], normal_compiler)
        self.assertJoins(sq, [
            'INNER JOIN "category" AS t2 ON (t1."parent_id" = t2."id")',
        ], normal_compiler)
        self.assertWhere(sq, '(t2."name" = ?)', ['parent name'], normal_compiler)
        self.assertOrderBy(sq, 't2."name"', [], normal_compiler)

        Grandparent = Category.alias()
        sq = SelectQuery(Category, Category, Parent, Grandparent).join(
            Parent, on=(Category.parent == Parent.id)
        ).join(
            Grandparent, on=(Parent.parent == Grandparent.id)
        ).where(Grandparent.name == 'g1')
        self.assertSelect(sq, 't1."id", t1."parent_id", t1."name", t2."id", t2."parent_id", t2."name", t3."id", t3."parent_id", t3."name"', [], normal_compiler)
        self.assertJoins(sq, [
            'INNER JOIN "category" AS t2 ON (t1."parent_id" = t2."id")',
            'INNER JOIN "category" AS t3 ON (t2."parent_id" = t3."id")',
        ], normal_compiler)
        self.assertWhere(sq, '(t3."name" = ?)', ['g1'], normal_compiler)

    def test_join_both_sides(self):
        sq = SelectQuery(Blog).join(Comment).switch(Blog).join(User)
        self.assertJoins(sq, [
            'INNER JOIN "comment" AS comment ON (blog."pk" = comment."blog_id")',
            'INNER JOIN "users" AS users ON (blog."user_id" = users."id")',
        ])

        sq = SelectQuery(Blog).join(User).switch(Blog).join(Comment)
        self.assertJoins(sq, [
            'INNER JOIN "users" AS users ON (blog."user_id" = users."id")',
            'INNER JOIN "comment" AS comment ON (blog."pk" = comment."blog_id")',
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
            'INNER JOIN "artist" AS artist ON (track."artist_id" = artist."id")',
            'INNER JOIN "genre" AS genre ON (trackgenre."genre_id" = genre."id")',
            'INNER JOIN "release" AS release ON (releasetrack."release_id" = release."id")',
            'INNER JOIN "releasetrack" AS releasetrack ON (track."id" = releasetrack."track_id")',
            'INNER JOIN "trackgenre" AS trackgenre ON (track."id" = trackgenre."track_id")',
        ])

        single_first = Track.select().join(Artist).switch(Track).join(ReleaseTrack).join(Release).switch(Track).join(TrackGenre).join(Genre)
        self.assertSelect(single_first, 'track."id", track."artist_id"', [])
        self.assertJoins(single_first, [
            'INNER JOIN "artist" AS artist ON (track."artist_id" = artist."id")',
            'INNER JOIN "genre" AS genre ON (trackgenre."genre_id" = genre."id")',
            'INNER JOIN "release" AS release ON (releasetrack."release_id" = release."id")',
            'INNER JOIN "releasetrack" AS releasetrack ON (track."id" = releasetrack."track_id")',
            'INNER JOIN "trackgenre" AS trackgenre ON (track."id" = trackgenre."track_id")',
        ])

    def test_joining_expr(self):
        class A(TestModel):
            uniq_a = CharField(primary_key=True)
        class B(TestModel):
            uniq_ab = CharField(primary_key=True)
            uniq_b = CharField()
        class C(TestModel):
            uniq_bc = CharField(primary_key=True)
        sq = A.select(A, B, C).join(
            B, on=(A.uniq_a == B.uniq_ab)
        ).join(
            C, on=(B.uniq_b == C.uniq_bc)
        )
        self.assertSelect(sq, 'a."uniq_a", b."uniq_ab", b."uniq_b", c."uniq_bc"', [])
        self.assertJoins(sq, [
            'INNER JOIN "b" AS b ON (a."uniq_a" = b."uniq_ab")',
            'INNER JOIN "c" AS c ON (b."uniq_b" = c."uniq_bc")',
        ])

    def test_where(self):
        sq = SelectQuery(User).where(User.id < 5)
        self.assertWhere(sq, '(users."id" < ?)', [5])

        sq = SelectQuery(Blog).where(Blog.user << sq)
        self.assertWhere(sq, '(blog."user_id" IN (SELECT users."id" FROM "users" AS users WHERE (users."id" < ?)))', [5])

        p = SelectQuery(Package).where(Package.id == 2)
        sq = SelectQuery(PackageItem).where(PackageItem.package << p)
        self.assertWhere(sq, '(packageitem."package_id" IN (SELECT package."barcode" FROM "package" AS package WHERE (package."id" = ?)))', [2])

    def test_orwhere(self):
        sq = SelectQuery(User).orwhere(User.id < 5)
        self.assertWhere(sq, '(users."id" < ?)', [5])

        sq = sq.orwhere(User.id > 10)
        self.assertWhere(sq, '((users."id" < ?) OR (users."id" > ?))', [5, 10])

    def test_fix_null(self):
        sq = SelectQuery(Blog).where(Blog.user == None)
        self.assertWhere(sq, '(blog."user_id" IS ?)', [None])

        sq = SelectQuery(Blog).where(Blog.user != None)
        self.assertWhere(sq, 'NOT (blog."user_id" IS ?)', [None])

    def test_where_coercion(self):
        sq = SelectQuery(User).where(User.id < '5')
        self.assertWhere(sq, '(users."id" < ?)', [5])

        sq = SelectQuery(User).where(User.id < (User.id - '5'))
        self.assertWhere(sq, '(users."id" < (users."id" - ?))', [5])

    def test_where_lists(self):
        sq = SelectQuery(User).where(User.username << ['u1', 'u2'])
        self.assertWhere(sq, '(users."username" IN (?, ?))', ['u1', 'u2'])

        sq = SelectQuery(User).where((User.username << ['u1', 'u2']) | (User.username << ['u3', 'u4']))
        self.assertWhere(sq, '((users."username" IN (?, ?)) OR (users."username" IN (?, ?)))', ['u1', 'u2', 'u3', 'u4'])

    def test_where_joins(self):
        sq = SelectQuery(User).where(
            ((User.id == 1) | (User.id == 2)) &
            ((Blog.pk == 3) | (Blog.pk == 4))
        ).where(User.id == 5).join(Blog)
        self.assertWhere(sq, '((((users."id" = ?) OR (users."id" = ?)) AND ((blog."pk" = ?) OR (blog."pk" = ?))) AND (users."id" = ?))', [1, 2, 3, 4, 5])

    def test_where_join_non_pk_fk(self):
        sq = (SelectQuery(Package)
              .join(PackageItem)
              .where(PackageItem.title == 'p1'))
        self.assertWhere(sq, '(packageitem."title" = ?)', ['p1'])

        sq = (SelectQuery(PackageItem)
              .join(Package)
              .where(Package.barcode == 'b1'))
        self.assertWhere(sq, '(package."barcode" = ?)', ['b1'])

    def test_where_functions(self):
        sq = SelectQuery(User).where(fn.Lower(fn.Substr(User.username, 0, 1)) == 'a')
        self.assertWhere(sq, '(Lower(Substr(users."username", ?, ?)) = ?)', [0, 1, 'a'])

    def test_where_conversion(self):
        sq = SelectQuery(CSVRow).where(CSVRow.data == Param(['foo', 'bar']))
        self.assertWhere(sq, '(csvrow."data" = ?)', ['foo,bar'])

        sq = SelectQuery(CSVRow).where(
            CSVRow.data == fn.FOO(Param(['foo', 'bar'])))
        self.assertWhere(sq, '(csvrow."data" = FOO(?))', ['foo,bar'])

        sq = SelectQuery(CSVRow).where(
            CSVRow.data == fn.FOO(Param(['foo', 'bar'])).coerce(False))
        self.assertWhere(sq, '(csvrow."data" = FOO(?))', [['foo', 'bar']])

    def test_where_clauses(self):
        sq = SelectQuery(Blog).where(
            Blog.pub_date < (fn.NOW() - SQL('INTERVAL 1 HOUR')))
        self.assertWhere(sq, '(blog."pub_date" < (NOW() - INTERVAL 1 HOUR))', [])

    def test_where_r(self):
        sq = SelectQuery(Blog).where(Blog.pub_date < R('NOW() - INTERVAL 1 HOUR'))
        self.assertWhere(sq, '(blog."pub_date" < NOW() - INTERVAL 1 HOUR)', [])

        sq = SelectQuery(Blog).where(Blog.pub_date < (fn.Now() - R('INTERVAL 1 HOUR')))
        self.assertWhere(sq, '(blog."pub_date" < (Now() - INTERVAL 1 HOUR))', [])

    def test_where_subqueries(self):
        sq = SelectQuery(User).where(User.id << User.select().where(User.username=='u1'))
        self.assertWhere(sq, '(users."id" IN (SELECT users."id" FROM "users" AS users WHERE (users."username" = ?)))', ['u1'])

        sq = SelectQuery(User).where(User.username << User.select(User.username).where(User.username=='u1'))
        self.assertWhere(sq, '(users."username" IN (SELECT users."username" FROM "users" AS users WHERE (users."username" = ?)))', ['u1'])

        sq = SelectQuery(Blog).where((Blog.pk == 3) | (Blog.user << User.select().where(User.username << ['u1', 'u2'])))
        self.assertWhere(sq, '((blog."pk" = ?) OR (blog."user_id" IN (SELECT users."id" FROM "users" AS users WHERE (users."username" IN (?, ?)))))', [3, 'u1', 'u2'])

    def test_where_fk(self):
        sq = SelectQuery(Blog).where(Blog.user == User(id=100))
        self.assertWhere(sq, '(blog."user_id" = ?)', [100])

        sq = SelectQuery(Blog).where(Blog.user << [User(id=100), User(id=101)])
        self.assertWhere(sq, '(blog."user_id" IN (?, ?))', [100, 101])

        sq = SelectQuery(PackageItem).where(PackageItem.package == Package(barcode='b1'))
        self.assertWhere(sq, '(packageitem."package_id" = ?)', ['b1'])

    def test_where_negation(self):
        sq = SelectQuery(Blog).where(~(Blog.title == 'foo'))
        self.assertWhere(sq, 'NOT (blog."title" = ?)', ['foo'])

        sq = SelectQuery(Blog).where(~((Blog.title == 'foo') | (Blog.title == 'bar')))
        self.assertWhere(sq, 'NOT ((blog."title" = ?) OR (blog."title" = ?))', ['foo', 'bar'])

        sq = SelectQuery(Blog).where(~((Blog.title == 'foo') & (Blog.title == 'bar')) & (Blog.title == 'baz'))
        self.assertWhere(sq, '(NOT ((blog."title" = ?) AND (blog."title" = ?)) AND (blog."title" = ?))', ['foo', 'bar', 'baz'])

        sq = SelectQuery(Blog).where(~((Blog.title == 'foo') & (Blog.title == 'bar')) & ((Blog.title == 'baz') & (Blog.title == 'fizz')))
        self.assertWhere(sq, '(NOT ((blog."title" = ?) AND (blog."title" = ?)) AND ((blog."title" = ?) AND (blog."title" = ?)))', ['foo', 'bar', 'baz', 'fizz'])

    def test_where_chaining_collapsing(self):
        sq = SelectQuery(User).where(User.id == 1).where(User.id == 2).where(User.id == 3)
        self.assertWhere(sq, '(((users."id" = ?) AND (users."id" = ?)) AND (users."id" = ?))', [1, 2, 3])

        sq = SelectQuery(User).where((User.id == 1) & (User.id == 2)).where(User.id == 3)
        self.assertWhere(sq, '(((users."id" = ?) AND (users."id" = ?)) AND (users."id" = ?))', [1, 2, 3])

        sq = SelectQuery(User).where((User.id == 1) | (User.id == 2)).where(User.id == 3)
        self.assertWhere(sq, '(((users."id" = ?) OR (users."id" = ?)) AND (users."id" = ?))', [1, 2, 3])

        sq = SelectQuery(User).where(User.id == 1).where((User.id == 2) & (User.id == 3))
        self.assertWhere(sq, '((users."id" = ?) AND ((users."id" = ?) AND (users."id" = ?)))', [1, 2, 3])

        sq = SelectQuery(User).where(User.id == 1).where((User.id == 2) | (User.id == 3))
        self.assertWhere(sq, '((users."id" = ?) AND ((users."id" = ?) OR (users."id" = ?)))', [1, 2, 3])

        sq = SelectQuery(User).where(~(User.id == 1)).where(User.id == 2).where(~(User.id == 3))
        self.assertWhere(sq, '((NOT (users."id" = ?) AND (users."id" = ?)) AND NOT (users."id" = ?))', [1, 2, 3])

    def test_grouping(self):
        sq = SelectQuery(User).group_by(User.id)
        self.assertGroupBy(sq, 'users."id"', [])

        sq = SelectQuery(User).group_by(User)
        self.assertGroupBy(sq, 'users."id", users."username"', [])

    def test_having(self):
        sq = SelectQuery(User, fn.Count(Blog.pk)).join(Blog).group_by(User).having(
            fn.Count(Blog.pk) > 2
        )
        self.assertHaving(sq, '(Count(blog."pk") > ?)', [2])

        sq = SelectQuery(User, fn.Count(Blog.pk)).join(Blog).group_by(User).having(
            (fn.Count(Blog.pk) > 10) | (fn.Count(Blog.pk) < 2)
        )
        self.assertHaving(sq, '((Count(blog."pk") > ?) OR (Count(blog."pk") < ?))', [10, 2])

    def test_ordering(self):
        sq = SelectQuery(User).join(Blog).order_by(Blog.title)
        self.assertOrderBy(sq, 'blog."title"', [])

        sq = SelectQuery(User).join(Blog).order_by(Blog.title.asc())
        self.assertOrderBy(sq, 'blog."title" ASC', [])

        sq = SelectQuery(User).join(Blog).order_by(Blog.title.desc())
        self.assertOrderBy(sq, 'blog."title" DESC', [])

        sq = SelectQuery(User).join(Blog).order_by(User.username.desc(), Blog.title.asc())
        self.assertOrderBy(sq, 'users."username" DESC, blog."title" ASC', [])

        base_sq = SelectQuery(User, User.username, fn.Count(Blog.pk).alias('count')).join(Blog).group_by(User.username)
        sq = base_sq.order_by(fn.Count(Blog.pk).desc())
        self.assertOrderBy(sq, 'Count(blog."pk") DESC', [])

        sq = base_sq.order_by(R('count'))
        self.assertOrderBy(sq, 'count', [])

        sq = OrderedModel.select()
        self.assertOrderBy(sq, 'orderedmodel."created" DESC', [])

        sq = OrderedModel.select().order_by(OrderedModel.id.asc())
        self.assertOrderBy(sq, 'orderedmodel."id" ASC', [])

        sq = User.select().order_by(User.id * 5)
        self.assertOrderBy(sq, '(users."id" * ?)', [5])
        sql = compiler.generate_select(sq)
        self.assertEqual(sql, (
            'SELECT users."id", users."username" '
            'FROM "users" AS users ORDER BY (users."id" * ?)',
            [5]))

    def test_from_subquery(self):
        # e.g. annotate the number of blogs per user, then annotate the number
        # of users with that number of blogs.
        inner = (Blog
                 .select(fn.COUNT(Blog.pk).alias('blog_ct'))
                 .group_by(Blog.user))
        blog_ct = SQL('blog_ct')
        outer = (Blog
                 .select(blog_ct, fn.COUNT(blog_ct).alias('blog_ct_n'))
                 .from_(inner)
                 .group_by(blog_ct))
        sql, params = compiler.generate_select(outer)
        self.assertEqual(sql, (
            'SELECT blog_ct, COUNT(blog_ct) AS blog_ct_n '
            'FROM ('
            'SELECT COUNT(blog."pk") AS blog_ct FROM "blog" AS blog '
            'GROUP BY blog."user_id") '
            'GROUP BY blog_ct'))

    def test_from_multiple(self):
        q = (User
             .select()
             .from_(User, Blog)
             .where(Blog.user == User.id))

        sql, params = compiler.generate_select(q)
        self.assertEqual(sql, (
            'SELECT users."id", users."username" '
            'FROM "users" AS users, "blog" AS blog '
            'WHERE (blog."user_id" = users."id")'))

        q = (User
             .select()
             .from_(User, Blog, Comment)
             .where(
                 (Blog.user == User.id) &
                 (Comment.blog == Blog.pk)))

        sql, params = compiler.generate_select(q)
        self.assertEqual(sql, (
            'SELECT users."id", users."username" '
            'FROM "users" AS users, "blog" AS blog, "comment" AS comment '
            'WHERE ((blog."user_id" = users."id") AND '
            '(comment."blog_id" = blog."pk"))'))

    def test_paginate(self):
        sq = SelectQuery(User).paginate(1, 20)
        self.assertEqual(sq._limit, 20)
        self.assertEqual(sq._offset, 0)

        sq = SelectQuery(User).paginate(3, 30)
        self.assertEqual(sq._limit, 30)
        self.assertEqual(sq._offset, 60)

    def test_prefetch_subquery(self):
        sq = SelectQuery(User).where(User.username == 'foo')
        sq2 = SelectQuery(Blog).where(Blog.title == 'bar')
        sq3 = SelectQuery(Comment).where(Comment.comment == 'baz')
        fixed = prefetch_add_subquery(sq, (sq2, sq3))
        fixed_sql = [
            ('SELECT t1."id", t1."username" FROM "users" AS t1 WHERE (t1."username" = ?)', ['foo']),
            ('SELECT t1."pk", t1."user_id", t1."title", t1."content", t1."pub_date" FROM "blog" AS t1 WHERE ((t1."title" = ?) AND (t1."user_id" IN (SELECT t2."id" FROM "users" AS t2 WHERE (t2."username" = ?))))', ['bar', 'foo']),
            ('SELECT t1."id", t1."blog_id", t1."comment" FROM "comment" AS t1 WHERE ((t1."comment" = ?) AND (t1."blog_id" IN (SELECT t2."pk" FROM "blog" AS t2 WHERE ((t2."title" = ?) AND (t2."user_id" IN (SELECT t3."id" FROM "users" AS t3 WHERE (t3."username" = ?)))))))', ['baz', 'bar', 'foo']),
        ]
        for (query, fkf), expected in zip(fixed, fixed_sql):
            self.assertEqual(normal_compiler.generate_select(query), expected)

        fixed = prefetch_add_subquery(sq, (Blog,))
        fixed_sql = [
            ('SELECT t1."id", t1."username" FROM "users" AS t1 WHERE (t1."username" = ?)', ['foo']),
            ('SELECT t1."pk", t1."user_id", t1."title", t1."content", t1."pub_date" FROM "blog" AS t1 WHERE (t1."user_id" IN (SELECT t2."id" FROM "users" AS t2 WHERE (t2."username" = ?)))', ['foo']),
        ]
        for (query, fkf), expected in zip(fixed, fixed_sql):
            self.assertEqual(normal_compiler.generate_select(query), expected)

    def test_prefetch_non_pk_fk(self):
        sq = SelectQuery(Package).where(Package.barcode % 'b%')
        sq2 = SelectQuery(PackageItem).where(PackageItem.title % 'n%')
        fixed = prefetch_add_subquery(sq, (sq2,))
        fixed_sq = (
            'SELECT t1."id", t1."barcode" FROM "package" AS t1 '
            'WHERE (t1."barcode" LIKE ?)',
            ['b%'])
        fixed_sq2 = (
            'SELECT t1."id", t1."title", t1."package_id" '
            'FROM "packageitem" AS t1 '
            'WHERE ('
            '(t1."title" LIKE ?) AND '
            '(t1."package_id" IN ('
            'SELECT t2."barcode" FROM "package" AS t2 '
            'WHERE (t2."barcode" LIKE ?))))',
            ['n%', 'b%'])
        fixed_sql = [fixed_sq, fixed_sq2]

        for (query, fkf), expected in zip(fixed, fixed_sql):
            self.assertEqual(normal_compiler.generate_select(query), expected)

    def test_prefetch_subquery_same_depth(self):
        sq = Parent.select()
        sq2 = Child.select()
        sq3 = Orphan.select()
        sq4 = ChildPet.select()
        sq5 = OrphanPet.select()
        fixed = prefetch_add_subquery(sq, (sq2, sq3, sq4, sq5))
        fixed_sql = [
            ('SELECT t1."id", t1."data" FROM "parent" AS t1', []),
            ('SELECT t1."id", t1."parent_id", t1."data" FROM "child" AS t1 WHERE (t1."parent_id" IN (SELECT t2."id" FROM "parent" AS t2))', []),
            ('SELECT t1."id", t1."parent_id", t1."data" FROM "orphan" AS t1 WHERE (t1."parent_id" IN (SELECT t2."id" FROM "parent" AS t2))', []),
            ('SELECT t1."id", t1."child_id", t1."data" FROM "childpet" AS t1 WHERE (t1."child_id" IN (SELECT t2."id" FROM "child" AS t2 WHERE (t2."parent_id" IN (SELECT t3."id" FROM "parent" AS t3))))', []),
            ('SELECT t1."id", t1."orphan_id", t1."data" FROM "orphanpet" AS t1 WHERE (t1."orphan_id" IN (SELECT t2."id" FROM "orphan" AS t2 WHERE (t2."parent_id" IN (SELECT t3."id" FROM "parent" AS t3))))', []),
        ]
        for (query, fkf), expected in zip(fixed, fixed_sql):
            self.assertEqual(normal_compiler.generate_select(query), expected)

    def test_outer_inner_alias(self):
        expected = ('SELECT t1."id", t1."username", '
                    '(SELECT Sum(t2."id") FROM "users" AS t2 '
                    'WHERE (t2."id" = t1."id")) AS xxx FROM "users" AS t1')
        UA = User.alias()
        inner = SelectQuery(UA, fn.Sum(UA.id)).where(UA.id == User.id)
        query = User.select(User, inner.alias('xxx'))
        sql, _ = normal_compiler.generate_select(query)
        self.assertEqual(sql, expected)

        # Ensure that ModelAlias.select() does the right thing.
        inner = UA.select(fn.Sum(UA.id)).where(UA.id == User.id)
        query = User.select(User, inner.alias('xxx'))
        sql, _ = normal_compiler.generate_select(query)
        self.assertEqual(sql, expected)

    def test_parentheses_cleaning(self):
        query = (User
                 .select(
                     User.username,
                     fn.Count(
                         Blog
                         .select(Blog.pk)
                         .where(Blog.user == User.id)).alias('blog_ct')))
        sql, params = query.sql()
        self.assertEqual(sql, (
            'SELECT t1."username", '
            'Count('
            'SELECT t2."pk" FROM "blog" AS t2 '
            'WHERE (t2."user_id" = t1."id")) AS blog_ct FROM "users" AS t1'))

        query = (User
                 .select(User.username)
                 .where(fn.Exists(fn.Exists(User.select(User.id)))))
        self.assertEqual(query.sql()[0], (
            'SELECT t1."username" FROM "users" AS t1 '
            'WHERE Exists(Exists('
            'SELECT t2."id" FROM "users" AS t2))'))

class UpdateTestCase(BasePeeweeTestCase):
    def test_update(self):
        uq = UpdateQuery(User, {User.username: 'updated'})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "users" SET "username" = ?',
            ['updated']))

        uq = UpdateQuery(Blog, {Blog.user: User(id=100, username='foo')})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "blog" SET "user_id" = ?',
            [100]))

        uq = UpdateQuery(User, {User.id: User.id + 5})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "users" SET "id" = (users."id" + ?)',
            [5]))

        uq = UpdateQuery(User, {User.id: 5 * (3 + User.id)})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "users" SET "id" = (? * (? + users."id"))',
            [5, 3]))

        # set username to the maximum id of all users -- silly, yes, but lets see what happens
        uq = UpdateQuery(User, {User.username: User.select(fn.Max(User.id).alias('maxid'))})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "users" SET "username" = (SELECT Max(users."id") AS maxid '
            'FROM "users" AS users)',
            []))

        uq = UpdateQuery(Blog, {Blog.title: 'foo', Blog.content: 'bar'})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "blog" SET "title" = ?, "content" = ?',
            ['foo', 'bar']))

        pub_date = datetime.datetime(2014, 1, 2, 3, 4)
        uq = UpdateQuery(Blog, {
            Blog.title: 'foo',
            Blog.pub_date: pub_date,
            Blog.user: User(id=15),
            Blog.content: 'bar'})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "blog" SET '
            '"user_id" = ?, "title" = ?, "content" = ?, "pub_date" = ?',
            [15, 'foo', 'bar', pub_date]))

    def test_update_special(self):
        uq = UpdateQuery(CSVRow, {CSVRow.data: ['foo', 'bar', 'baz']})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "csvrow" SET "data" = ?',
            ['foo,bar,baz']))

        uq = UpdateQuery(CSVRow, {CSVRow.data: []})
        self.assertEqual(compiler.generate_update(uq), (
            'UPDATE "csvrow" SET "data" = ?',
            ['']))

    def test_where(self):
        uq = UpdateQuery(User, {User.username: 'updated'}).where(User.id == 2)
        self.assertWhere(uq, '(users."id" = ?)', [2])

        uq = (UpdateQuery(User, {User.username: 'updated'})
              .where(User.id == 2)
              .where(User.username == 'old'))
        self.assertWhere(uq, '((users."id" = ?) AND (users."username" = ?))', [2, 'old'])

class InsertTestCase(BasePeeweeTestCase):
    def test_insert(self):
        iq = InsertQuery(User, {User.username: 'inserted'})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "users" ("username") VALUES (?)',
            ['inserted']))

        iq = InsertQuery(User, {'username': 'inserted'})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "users" ("username") VALUES (?)',
            ['inserted']))

        pub_date = datetime.datetime(2014, 1, 2, 3, 4)
        iq = InsertQuery(Blog, {
            Blog.title: 'foo',
            Blog.content: 'bar',
            Blog.pub_date: pub_date,
            Blog.user: User(id=10)})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "blog" ("user_id", "title", "content", "pub_date") '
            'VALUES (?, ?, ?, ?)',
            [10, 'foo', 'bar', pub_date]))

        subquery = Blog.select(Blog.title)
        iq = InsertQuery(User, fields=[User.username], query=subquery)
        sql, params = normal_compiler.generate_insert(iq)
        self.assertEqual(sql, (
            'INSERT INTO "users" ("username") '
            'SELECT t2."title" FROM "blog" AS t2'))

        subquery = Blog.select(Blog.pk, Blog.title)
        iq = InsertQuery(User, query=subquery)
        sql, params = normal_compiler.generate_insert(iq)
        self.assertEqual(sql, (
            'INSERT INTO "users" '
            'SELECT t2."pk", t2."title" FROM "blog" AS t2'))

    def test_insert_default_vals(self):
        class DM(TestModel):
            name = CharField(default='peewee')
            value = IntegerField(default=1, null=True)
            other = FloatField()

        iq = InsertQuery(DM)
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("name", "value") VALUES (?, ?)',
            ['peewee', 1]))

        iq = InsertQuery(DM, {'name': 'herman'})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("name", "value") VALUES (?, ?)',
            ['herman', 1]))

        iq = InsertQuery(DM, {'value': None})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("name", "value") VALUES (?, ?)',
            ['peewee', None]))

        iq = InsertQuery(DM, {DM.name: 'huey', 'other': 2.0})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "dm" ("name", "value", "other") VALUES (?, ?, ?)',
            ['huey', 1, 2.0]))

    def test_insert_many(self):
        iq = InsertQuery(User, rows=[
            {'username': 'u1'},
            {User.username: 'u2'},
            {'username': 'u3'},
        ])
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "users" ("username") VALUES (?), (?), (?)',
            ['u1', 'u2', 'u3']))

        iq = InsertQuery(User, rows=[{'username': 'u1'}])
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "users" ("username") VALUES (?)',
            ['u1']))

        iq = InsertQuery(User, rows=[])
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "users"', []))

    def test_insert_many_gen(self):
        def row_generator():
            for i in range(3):
                yield {'username': 'u%s' % i}

        iq = InsertQuery(User, rows=row_generator())
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "users" ("username") VALUES (?), (?), (?)',
            ['u0', 'u1', 'u2']))

    def test_insert_special(self):
        iq = InsertQuery(CSVRow, {CSVRow.data: ['foo', 'bar', 'baz']})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "csvrow" ("data") VALUES (?)',
            ['foo,bar,baz']))

        iq = InsertQuery(CSVRow, {CSVRow.data: []})
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "csvrow" ("data") VALUES (?)',
            ['']))

        iq = InsertQuery(CSVRow, rows=[
            {CSVRow.data: ['foo', 'bar', 'baz']},
            {CSVRow.data: ['a', 'b']},
            {CSVRow.data: ['b']},
            {CSVRow.data: []}])
        self.assertEqual(compiler.generate_insert(iq), (
            'INSERT INTO "csvrow" ("data") VALUES (?), (?), (?), (?)',
            ['foo,bar,baz', 'a,b', 'b', '']))

    def test_empty_insert(self):
        class EmptyModel(TestModel):
            pass
        iq = InsertQuery(EmptyModel, {})
        sql, params = compiler.generate_insert(iq)
        self.assertEqual(sql, 'INSERT INTO "emptymodel"')

class DeleteTestCase(BasePeeweeTestCase):
    def test_where(self):
        dq = DeleteQuery(User).where(User.id == 2)
        self.assertWhere(dq, '(users."id" = ?)', [2])

        dq = (DeleteQuery(User)
              .where(User.id == 2)
              .where(User.username == 'old'))
        self.assertWhere(dq, '((users."id" = ?) AND (users."username" = ?))', [2, 'old'])

class RawTestCase(BasePeeweeTestCase):
    def test_raw(self):
        q = 'SELECT * FROM "users" WHERE id=?'
        rq = RawQuery(User, q, 100)
        self.assertEqual(rq.sql(), (q, [100]))

class SugarTestCase(BasePeeweeTestCase):
    # test things like filter, annotate, aggregate
    def test_filter(self):
        sq = User.filter(username='u1')
        self.assertJoins(sq, [])
        self.assertWhere(sq, '(users."username" = ?)', ['u1'])

        sq = Blog.filter(user__username='u1')
        self.assertJoins(sq, ['INNER JOIN "users" AS users ON (blog."user_id" = users."id")'])
        self.assertWhere(sq, '(users."username" = ?)', ['u1'])

        sq = Blog.filter(user__username__in=['u1', 'u2'], comments__comment='hurp')
        self.assertJoins(sq, [
            'INNER JOIN "comment" AS comment ON (blog."pk" = comment."blog_id")',
            'INNER JOIN "users" AS users ON (blog."user_id" = users."id")',
        ])
        self.assertWhere(sq, '((comment."comment" = ?) AND (users."username" IN (?, ?)))', ['hurp', 'u1', 'u2'])

        sq = Blog.filter(user__username__in=['u1', 'u2']).filter(comments__comment='hurp')
        self.assertJoins(sq, [
            'INNER JOIN "users" AS users ON (blog."user_id" = users."id")',
            'INNER JOIN "comment" AS comment ON (blog."pk" = comment."blog_id")',
        ])
        self.assertWhere(sq, '((users."username" IN (?, ?)) AND (comment."comment" = ?))', ['u1', 'u2', 'hurp'])

    def test_filter_dq(self):
        sq = User.filter(DQ(username='u1') | DQ(username='u2'))
        self.assertJoins(sq, [])
        self.assertWhere(sq, '((users."username" = ?) OR (users."username" = ?))', ['u1', 'u2'])

        sq = Comment.filter(DQ(blog__user__username='u1') | DQ(blog__title='b1'), DQ(comment='c1'))
        self.assertJoins(sq, [
            'INNER JOIN "blog" AS blog ON (comment."blog_id" = blog."pk")',
            'INNER JOIN "users" AS users ON (blog."user_id" = users."id")',
        ])
        self.assertWhere(sq, '(((users."username" = ?) OR (blog."title" = ?)) AND (comment."comment" = ?))', ['u1', 'b1', 'c1'])

        sq = Blog.filter(DQ(user__username='u1') | DQ(comments__comment='c1'))
        self.assertJoins(sq, [
            'INNER JOIN "comment" AS comment ON (blog."pk" = comment."blog_id")',
            'INNER JOIN "users" AS users ON (blog."user_id" = users."id")',
        ])
        self.assertWhere(sq, '((users."username" = ?) OR (comment."comment" = ?))', ['u1', 'c1'])

        sq = Blog.filter(~DQ(user__username='u1') | DQ(user__username='b2'))
        self.assertJoins(sq, [
            'INNER JOIN "users" AS users ON (blog."user_id" = users."id")',
        ])
        self.assertWhere(sq, '(NOT (users."username" = ?) OR (users."username" = ?))', ['u1', 'b2'])

        sq = Blog.filter(~(
            DQ(user__username='u1') |
            ~DQ(title='b1', pk=3)))
        self.assertJoins(sq, [
            'INNER JOIN "users" AS users ON (blog."user_id" = users."id")',
        ])
        self.assertWhere(sq, 'NOT ((users."username" = ?) OR NOT ((blog."pk" = ?) AND (blog."title" = ?)))', ['u1', 3, 'b1'])

    def test_annotate(self):
        sq = User.select().annotate(Blog)
        self.assertSelect(sq, 'users."id", users."username", Count(blog."pk") AS count', [])
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON (users."id" = blog."user_id")'])
        self.assertWhere(sq, '', [])
        self.assertGroupBy(sq, 'users."id", users."username"', [])

        sq = User.select(User.username).annotate(Blog, fn.Sum(Blog.pk).alias('sum')).where(User.username == 'foo')
        self.assertSelect(sq, 'users."username", Sum(blog."pk") AS sum', [])
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON (users."id" = blog."user_id")'])
        self.assertWhere(sq, '(users."username" = ?)', ['foo'])
        self.assertGroupBy(sq, 'users."username"', [])

        sq = User.select(User.username).annotate(Blog).annotate(Blog, fn.Max(Blog.pk).alias('mx'))
        self.assertSelect(sq, 'users."username", Count(blog."pk") AS count, Max(blog."pk") AS mx', [])
        self.assertJoins(sq, ['INNER JOIN "blog" AS blog ON (users."id" = blog."user_id")'])
        self.assertWhere(sq, '', [])
        self.assertGroupBy(sq, 'users."username"', [])

        sq = User.select().annotate(Blog).order_by(R('count DESC'))
        self.assertSelect(sq, 'users."id", users."username", Count(blog."pk") AS count', [])
        self.assertOrderBy(sq, 'count DESC', [])

        sq = User.select().join(Blog, JOIN_LEFT_OUTER).switch(User).annotate(Blog)
        self.assertSelect(sq, 'users."id", users."username", Count(blog."pk") AS count', [])
        self.assertJoins(sq, ['LEFT OUTER JOIN "blog" AS blog ON (users."id" = blog."user_id")'])
        self.assertWhere(sq, '', [])
        self.assertGroupBy(sq, 'users."id", users."username"', [])

    def test_aggregate(self):
        sq = User.select().where(User.id < 10)._aggregate()
        self.assertSelect(sq, 'Count(*)', [])
        self.assertWhere(sq, '(users."id" < ?)', [10])

        sq = User.select()._aggregate(fn.Sum(User.id).alias('baz'))
        self.assertSelect(sq, 'Sum(users."id") AS baz', [])


class CompilerTestCase(BasePeeweeTestCase):
    def test_clause(self):
        expr = fn.extract(Clause('year', R('FROM'), Blog.pub_date))
        sql, params = compiler.parse_node(expr)
        self.assertEqual(sql, 'extract(? FROM "pub_date")')
        self.assertEqual(params, ['year'])

    def test_custom_alias(self):
        class Person(TestModel):
            name = CharField()

            class Meta:
                table_alias = 'person_tbl'

        class Pet(TestModel):
            name = CharField()
            owner = ForeignKeyField(Person)

            class Meta:
                table_alias = 'pet_tbl'

        sq = Person.select().where(Person.name == 'peewee')
        sql = normal_compiler.generate_select(sq)
        self.assertEqual(
            sql[0],
            'SELECT person_tbl."id", person_tbl."name" FROM "person" AS '
            'person_tbl WHERE (person_tbl."name" = ?)')

        sq = Pet.select(Pet, Person.name).join(Person)
        sql = normal_compiler.generate_select(sq)
        self.assertEqual(
            sql[0],
            'SELECT pet_tbl."id", pet_tbl."name", pet_tbl."owner_id", '
            'person_tbl."name" '
            'FROM "pet" AS pet_tbl '
            'INNER JOIN "person" AS person_tbl '
            'ON (pet_tbl."owner_id" = person_tbl."id")')

    def test_alias_map(self):
        class A(TestModel):
            a = CharField()
            class Meta:
                table_alias = 'a_tbl'
        class B(TestModel):
            b = CharField()
            a_link = ForeignKeyField(A)
        class C(TestModel):
            c = CharField()
            b_link = ForeignKeyField(B)
        class D(TestModel):
            d = CharField()
            c_link = ForeignKeyField(C)
            class Meta:
                table_alias = 'd_tbl'

        sq = (D
              .select(D.d, C.c)
              .join(C)
              .where(C.b_link << (
                  B.select(B.id).join(A).where(A.a == 'a'))))
        sql, params = normal_compiler.generate_select(sq)
        self.assertEqual(sql, (
            'SELECT d_tbl."d", t2."c" '
            'FROM "d" AS d_tbl '
            'INNER JOIN "c" AS t2 ON (d_tbl."c_link_id" = t2."id") '
            'WHERE (t2."b_link_id" IN ('
            'SELECT t3."id" FROM "b" AS t3 '
            'INNER JOIN "a" AS a_tbl ON (t3."a_link_id" = a_tbl."id") '
            'WHERE (a_tbl."a" = ?)))'))

    def test_fn_no_coerce(self):
        class A(TestModel):
            i = IntegerField()
            d = DateTimeField()

        query = A.select(A.id).where(A.d == '2013-01-02')
        sql, params = compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT a."id" FROM "a" AS a WHERE (a."d" = ?)'))
        self.assertEqual(params, ['2013-01-02'])

        query = A.select(A.id).where(A.i == fn.Foo('test'))
        self.assertRaises(ValueError, query.sql)

        query = A.select(A.id).where(A.i == fn.Foo('test').coerce(False))
        sql, params = compiler.generate_select(query)
        self.assertEqual(sql, (
            'SELECT a."id" FROM "a" AS a WHERE (a."i" = Foo(?))'))
        self.assertEqual(params, ['test'])

    def test_strip_parentheses(self):
        tests = (
            ('x = 1', 'x = 1'),
            ('(x = 1)', 'x = 1'),
            ('(((((x = 1)))))', 'x = 1'),
            ('(((((x = (1))))))', 'x = (1)'),
            ('(((((x) = 1))))', '(x) = 1'),
            ('(x = (y = 2))', 'x = (y = 2)'),
            ('(((x = 1)', '((x = 1'),
            ('(x = 1)))', 'x = 1))'),
            ('x = 1))', 'x = 1))'),
            ('((x = 1', '((x = 1'),
            ('(((()))', '('),
            ('((())))', ')'),
            ('', ''),
            ('(((())))', ''))
        for s, expected in tests:
            self.assertEqual(compiler._clean_extra_parens(s), expected)


class ValidationTestCase(BasePeeweeTestCase):
    def test_foreign_key_validation(self):
        def declare_bad(val):
            class Bad(TestModel):
                name = ForeignKeyField(val)

        vals_to_try = [
            ForeignKeyField(User),
            'Self',
            object,
            object()]

        for val in vals_to_try:
            self.assertRaises(TypeError, declare_bad, val)


class ProxyTestCase(BasePeeweeTestCase):
    def test_proxy(self):
        class A(object):
            def foo(self):
                return 'foo'

        a = Proxy()
        def raise_error():
            a.foo()
        self.assertRaises(AttributeError, raise_error)

        a.initialize(A())
        self.assertEqual(a.foo(), 'foo')

    def test_proxy_database(self):
        database_proxy = Proxy()

        class DummyModel(TestModel):
            test_field = CharField()
            class Meta:
                database = database_proxy

        # Un-initialized will raise an AttributeError.
        self.assertRaises(AttributeError, DummyModel.create_table)

        # Initialize the object.
        database_proxy.initialize(SqliteDatabase(':memory:'))

        # Do some queries, verify it is working.
        DummyModel.create_table()
        DummyModel.create(test_field='foo')
        self.assertEqual(DummyModel.get().test_field, 'foo')
        DummyModel.drop_table()

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

    def test_iterator_query_method(self):
        self.create_users(10)
        qc = len(self.queries())

        qr = User.select()
        usernames = [u.username for u in qr.iterator()]
        self.assertEqual(usernames, ['u%d' % i for i in range(1, 11)])

        qc1 = len(self.queries())
        self.assertEqual(qc1 - qc, 1)

        again = [u.username for u in qr]
        self.assertEqual(again, [])
        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc1, 0)

    def test_iterator_extended(self):
        self.create_users(10)
        for i in range(1, 4):
            for j in range(i):
                Blog.create(
                    title='blog-%s-%s' % (i, j),
                    user=User.get(User.username == 'u%s' % i))

        qc = len(self.queries())

        qr = (User
              .select(
                  User.username,
                  fn.Count(Blog.pk).alias('ct'))
              .join(Blog)
              .where(User.username << ['u1', 'u2', 'u3'])
              .group_by(User)
              .order_by(User.id)
              .naive())

        accum = []
        for user in qr.iterator():
            accum.append((user.username, user.ct))

        self.assertEqual(accum, [
            ('u1', 1),
            ('u2', 2),
            ('u3', 3)])

        qr = (User
              .select(fn.Count(User.id).alias('ct'))
              .group_by(User.username << ['u1', 'u2', 'u3'])
              .order_by(fn.Count(User.id).desc()))
        accum = []
        for ct, in qr.tuples().iterator():
            accum.append(ct)
        self.assertEqual(accum, [7, 3])

    def test_fill_cache(self):
        def assertUsernames(qr, n):
            self.assertEqual([u.username for u in qr._result_cache], ['u%d' % i for i in range(1, n+1)])

        self.create_users(20)
        qc = len(self.queries())

        qr = User.select().execute()

        qr.fill_cache(5)
        self.assertFalse(qr._populated)
        assertUsernames(qr, 5)

        # a subsequent call will not "over-fill"
        qr.fill_cache(5)
        self.assertFalse(qr._populated)
        assertUsernames(qr, 5)

        # ask for one more and ye shall receive
        qr.fill_cache(6)
        self.assertFalse(qr._populated)
        assertUsernames(qr, 6)

        qr.fill_cache(21)
        self.assertTrue(qr._populated)
        assertUsernames(qr, 20)

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

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

        self.assertTrue(isinstance(comments._qr, ModelQueryResultWrapper))

        qc = len(self.queries())
        comments = Comment.select().join(Blog).join(User).where(User.username == 'u1').order_by(Comment.id)
        self.assertEqual([c.blog.user.username for c in comments], ['u1', 'u1'])
        self.assertEqual(len(self.queries()) - qc, 5)

        self.assertTrue(isinstance(comments._qr, NaiveQueryResultWrapper))

    def test_naive(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        b1 = Blog.create(user=u1, title='b1')
        b2 = Blog.create(user=u2, title='b2')

        users = User.select().naive()
        self.assertEqual([u.username for u in users], ['u1', 'u2'])
        self.assertTrue(isinstance(users._qr, NaiveQueryResultWrapper))

        users = User.select(User, Blog).join(Blog).naive()
        self.assertEqual([u.username for u in users], ['u1', 'u2'])
        self.assertEqual([u.title for u in users], ['b1', 'b2'])

        query = Blog.select(Blog, User).join(User).order_by(Blog.title).naive()
        self.assertEqual(query.get().user, User.get(User.username == 'u1'))

    def test_tuples_dicts(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        b1 = Blog.create(user=u1, title='b1')
        b2 = Blog.create(user=u2, title='b2')
        users = User.select().tuples().order_by(User.id)
        self.assertEqual([r for r in users], [
            (u1.id, 'u1'),
            (u2.id, 'u2'),
        ])

        users = User.select().dicts()
        self.assertEqual([r for r in users], [
            {'id': u1.id, 'username': 'u1'},
            {'id': u2.id, 'username': 'u2'},
        ])

        users = User.select(User, Blog).join(Blog).order_by(User.id).tuples()
        self.assertEqual([r for r in users], [
            (u1.id, 'u1', b1.pk, u1.id, 'b1', '', None),
            (u2.id, 'u2', b2.pk, u2.id, 'b2', '', None),
        ])

        users = User.select(User, Blog).join(Blog).order_by(User.id).dicts()
        self.assertEqual([r for r in users], [
            {'id': u1.id, 'username': 'u1', 'pk': b1.pk, 'user': u1.id, 'title': 'b1', 'content': '', 'pub_date': None},
            {'id': u2.id, 'username': 'u2', 'pk': b2.pk, 'user': u2.id, 'title': 'b2', 'content': '', 'pub_date': None},
        ])

    def test_slicing_dicing(self):
        def assertUsernames(users, nums):
            self.assertEqual([u.username for u in users], ['u%d' % i for i in nums])

        self.create_users(10)
        qc = len(self.queries())

        uq = User.select().order_by(User.id)

        for i in range(2):
            res = uq[0]
            self.assertEqual(res.username, 'u1')

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

        for i in range(2):
            res = uq[1]
            self.assertEqual(res.username, 'u2')

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

        for i in range(2):
            res = uq[:3]
            assertUsernames(res, [1, 2, 3])

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

        for i in range(2):
            res = uq[2:5]
            assertUsernames(res, [3, 4, 5])

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

        for i in range(2):
            res = uq[5:]
            assertUsernames(res, [6, 7, 8, 9, 10])

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

        self.assertRaises(IndexError, uq.__getitem__, 10)
        self.assertRaises(ValueError, uq.__getitem__, -1)

        res = uq[10:]
        self.assertEqual(res, [])

    def test_indexing_fill_cache(self):
        def assertUser(query_or_qr, idx):
            self.assertEqual(query_or_qr[idx].username, 'u%d' % (idx + 1))

        self.create_users(10)
        uq = User.select().order_by(User.id)
        qc = len(self.queries())

        # Ensure we can grab the first 5 users and that it only costs 1 query.
        for i in range(5):
            assertUser(uq, i)
        self.assertEqual(len(self.queries()) - qc, 1)

        # Iterate in reverse and ensure only costs 1 query.
        uq = User.select().order_by(User.id)
        for i in reversed(range(10)):
            assertUser(uq, i)
        self.assertEqual(len(self.queries()) - qc, 2)

        # Execute the query and get reference to result wrapper.
        query = User.select().order_by(User.id)
        query.execute()
        qr = query._qr

        # Getting the first user will populate the result cache with 1 obj.
        assertUser(query, 0)
        self.assertEqual(len(qr._result_cache), 1)

        # Getting the last user will fill the cache.
        assertUser(query, 9)
        self.assertEqual(len(qr._result_cache), 10)

    def test_prepared(self):
        for i in range(2):
            u = User.create(username='u%d' % i)
            for j in range(2):
                Blog.create(title='b%d-%d' % (i, j), user=u, content='')

        for u in User.select():
            # check prepared was called
            self.assertEqual(u.foo, u.username)

        for b in Blog.select(Blog, User).join(User):
            # prepared is called for select-related instances
            self.assertEqual(b.foo, b.title)
            self.assertEqual(b.user.foo, b.user.username)


class QueryResultCoerceTestCase(ModelTestCase):
    requires = [User]

    def setUp(self):
        super(QueryResultCoerceTestCase, self).setUp()
        for i in range(3):
            User.create(username='u%d' % i)

    def assertNames(self, query, expected, attr='username'):
        id_field = query.model_class.id
        self.assertEqual(
            [getattr(item, attr) for item in query.order_by(id_field)],
            expected)

    def test_simple_select(self):
        query = UpperUser.select()
        self.assertNames(query, ['U0', 'U1', 'U2'])

        query = User.select()
        self.assertNames(query, ['u0', 'u1', 'u2'])

    def test_with_alias(self):
        # Even when aliased to a different attr, the column is coerced.
        query = UpperUser.select(UpperUser.username.alias('foo'))
        self.assertNames(query, ['U0', 'U1', 'U2'], 'foo')

    def test_scalar(self):
        max_username = (UpperUser
                        .select(fn.Max(UpperUser.username))
                        .scalar(convert=True))
        self.assertEqual(max_username, 'U2')

        max_username = (UpperUser
                        .select(fn.Max(UpperUser.username))
                        .scalar())
        self.assertEqual(max_username, 'u2')

    def test_function(self):
        substr = fn.SubStr(UpperUser.username, 1, 3)

        # Being the first parameter of the function, it meets the special-case
        # criteria.
        query = UpperUser.select(substr.alias('foo'))
        self.assertNames(query, ['U0', 'U1', 'U2'], 'foo')

        query = UpperUser.select(substr.coerce(False).alias('foo'))
        self.assertNames(query, ['u0', 'u1', 'u2'], 'foo')

        query = UpperUser.select(substr.coerce(False).alias('username'))
        self.assertNames(query, ['u0', 'u1', 'u2'])

        query = UpperUser.select(fn.Lower(UpperUser.username).alias('username'))
        self.assertNames(query, ['U0', 'U1', 'U2'])

        query = UpperUser.select(
            fn.Lower(UpperUser.username).alias('username').coerce(False))
        self.assertNames(query, ['u0', 'u1', 'u2'])

        # Since it is aliased to an existing column, we will use that column's
        # coerce.
        query = UpperUser.select(
            fn.SubStr(fn.Lower(UpperUser.username), 1, 3).alias('username'))
        self.assertNames(query, ['U0', 'U1', 'U2'])

        query = UpperUser.select(
            fn.SubStr(fn.Lower(UpperUser.username), 1, 3).alias('foo'))
        self.assertNames(query, ['u0', 'u1', 'u2'], 'foo')

class ModelQueryResultWrapperTestCase(ModelTestCase):
    requires = [TestModelA, TestModelB, TestModelC, User, Blog]

    data = (
        (TestModelA, (
            ('pk1', 'a1'),
            ('pk2', 'a2'),
            ('pk3', 'a3'))),
        (TestModelB, (
            ('pk1', 'b1'),
            ('pk2', 'b2'),
            ('pk3', 'b3'))),
        (TestModelC, (
            ('pk1', 'c1'),
            ('pk2', 'c2'))),
    )

    def setUp(self):
        super(ModelQueryResultWrapperTestCase, self).setUp()
        for model_class, model_data in self.data:
            for pk, data in model_data:
                model_class.create(field=pk, data=data)

    def test_join_expr(self):
        def get_query(join_type=JOIN_INNER):
            sq = (TestModelA
                  .select(TestModelA, TestModelB, TestModelC)
                  .join(
                      TestModelB,
                      on=(TestModelA.field == TestModelB.field).alias('rel_b'))
                  .join(
                      TestModelC,
                      join_type=join_type,
                      on=(TestModelB.field == TestModelC.field))
                  .order_by(TestModelA.field))
            return sq

        sq = get_query()
        self.assertEqual(sq.count(), 2)

        results = list(sq)
        expected = (('b1', 'c1'), ('b2', 'c2'))
        for i, (b_data, c_data) in enumerate(expected):
            self.assertEqual(results[i].rel_b.data, b_data)
            self.assertEqual(results[i].rel_b.field.data, c_data)

        sq = get_query(JOIN_LEFT_OUTER)
        self.assertEqual(sq.count(), 3)

        results = list(sq)
        expected = (('b1', 'c1'), ('b2', 'c2'), ('b3', None))
        for i, (b_data, c_data) in enumerate(expected):
            self.assertEqual(results[i].rel_b.data, b_data)
            self.assertEqual(results[i].rel_b.field.data, c_data)

    def test_backward_join(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        for user in (u1, u2):
            Blog.create(title='b-%s' % user.username, user=user)

        # Create an additional blog for user 2.
        Blog.create(title='b-u2-2', user=u2)

        res = (User
               .select(User.username, Blog.title)
               .join(Blog)
               .order_by(User.username.asc(), Blog.title.asc()))
        self.assertEqual([(u.username, u.blog.title) for u in res], [
            ('u1', 'b-u1'),
            ('u2', 'b-u2'),
            ('u2', 'b-u2-2')])

class SelectRelatedNonPKFKTestCase(ModelTestCase):
    requires = [Package, PackageItem]

    def test_select_related(self):
        p1 = Package.create(barcode='101')
        p2 = Package.create(barcode='102')
        pi11 = PackageItem.create(title='p11', package='101')
        pi12 = PackageItem.create(title='p12', package='101')
        pi21 = PackageItem.create(title='p21', package='102')
        pi22 = PackageItem.create(title='p22', package='102')

        # missing PackageItem.package_id.
        qc = len(self.queries())
        items = (PackageItem
                 .select(PackageItem.id, PackageItem.title, Package.barcode)
                 .join(Package)
                 .where(Package.barcode == '101')
                 .order_by(PackageItem.id))
        self.assertEqual([i.package.barcode for i in items], ['101', '101'])
        self.assertEqual(len(self.queries()) - qc, 1)

        qc = len(self.queries())
        items = (PackageItem
                 .select(PackageItem.id, PackageItem.title, PackageItem.package, Package.id)
                 .join(Package)
                 .where(Package.barcode == '101')
                 .order_by(PackageItem.id))
        self.assertEqual([i.package.id for i in items], [p1.id, p1.id])
        self.assertEqual(len(self.queries()) - qc, 1)

class NonPKFKBasicTestCase(ModelTestCase):
    requires = [Package, PackageItem]

    def setUp(self):
        super(NonPKFKBasicTestCase, self).setUp()

        for barcode in ['101', '102']:
            Package.create(barcode=barcode)
            for i in range(2):
                PackageItem.create(
                    package=barcode,
                    title='%s-%s' % (barcode, i))

    def test_fk_resolution(self):
        pi = PackageItem.get(PackageItem.title == '101-0')
        self.assertEqual(pi._data['package'], '101')
        self.assertEqual(pi.package, Package.get(Package.barcode == '101'))

    def test_select_generation(self):
        p = Package.get(Package.barcode == '101')
        self.assertEqual(
            [item.title for item in p.items.order_by(PackageItem.id)],
            ['101-0', '101-1'])

class ModelQueryTestCase(ModelTestCase):
    requires = [User, Blog]

    def setUp(self):
        super(ModelQueryTestCase, self).setUp()
        self._orig_db_insert_many = test_db.insert_many

    def tearDown(self):
        super(ModelQueryTestCase, self).tearDown()
        test_db.insert_many = self._orig_db_insert_many

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

    def test_select_all(self):
        self.create_users_blogs(2, 2)
        all_cols = SQL('*')
        query = Blog.select(all_cols)
        blogs = [blog for blog in query.order_by(Blog.pk)]
        self.assertEqual(
            [b.title for b in blogs],
            ['b-0-0', 'b-0-1', 'b-1-0', 'b-1-1'])
        self.assertEqual(
            [b.user.username for b in blogs],
            ['u0', 'u0', 'u1', 'u1'])

    def test_select_subquery(self):
        # 10 users, 5 blogs each
        self.create_users_blogs(5, 3)

        # delete user 2's 2nd blog
        Blog.delete().where(Blog.title == 'b-2-2').execute()

        subquery = Blog.select(fn.Count(Blog.pk)).where(Blog.user == User.id).group_by(Blog.user)
        users = User.select(User, subquery.alias('ct')).order_by(R('ct'), User.id)

        self.assertEqual([(x.username, x.ct) for x in users], [
            ('u2', 2),
            ('u0', 3),
            ('u1', 3),
            ('u3', 3),
            ('u4', 3),
        ])

    def test_scalar(self):
        self.create_users(5)

        users = User.select(fn.Count(User.id)).scalar()
        self.assertEqual(users, 5)

        users = User.select(fn.Count(User.id)).where(User.username << ['u1', 'u2'])
        self.assertEqual(users.scalar(), 2)
        self.assertEqual(users.scalar(True), (2,))

        users = User.select(fn.Count(User.id)).where(User.username == 'not-here')
        self.assertEqual(users.scalar(), 0)
        self.assertEqual(users.scalar(True), (0,))

        users = User.select(fn.Count(User.id), fn.Count(User.username))
        self.assertEqual(users.scalar(), 5)
        self.assertEqual(users.scalar(True), (5, 5))

        User.create(username='u1')
        User.create(username='u2')
        User.create(username='u3')
        User.create(username='u99')
        users = User.select(fn.Count(fn.Distinct(User.username))).scalar()
        self.assertEqual(users, 6)

    def test_update(self):
        self.create_users(5)
        uq = User.update(username='u-edited').where(User.username << ['u1', 'u2', 'u3'])
        self.assertEqual([u.username for u in User.select().order_by(User.id)], ['u1', 'u2', 'u3', 'u4', 'u5'])

        uq.execute()
        self.assertEqual([u.username for u in User.select().order_by(User.id)], ['u-edited', 'u-edited', 'u-edited', 'u4', 'u5'])

        self.assertRaises(KeyError, User.update, doesnotexist='invalid')

    def test_update_subquery(self):
        self.create_users(3)
        u1, u2, u3 = [user for user in User.select().order_by(User.id)]
        for i in range(4):
            Blog.create(title='b%s' % i, user=u1)
        for i in range(2):
            Blog.create(title='b%s' % i, user=u3)

        subquery = Blog.select(fn.COUNT(Blog.pk)).where(Blog.user == User.id)
        query = User.update(username=subquery)
        sql, params = normal_compiler.generate_update(query)
        self.assertEqual(sql, (
            'UPDATE "users" SET "username" = ('
            'SELECT COUNT(t2."pk") FROM "blog" AS t2 '
            'WHERE (t2."user_id" = users."id"))'))
        self.assertEqual(query.execute(), 3)

        usernames = [u.username for u in User.select().order_by(User.id)]
        self.assertEqual(usernames, ['4', '0', '2'])

    def test_insert(self):
        iq = User.insert(username='u1')
        self.assertEqual(User.select().count(), 0)
        uid = iq.execute()
        self.assertTrue(uid > 0)
        self.assertEqual(User.select().count(), 1)
        u = User.get(User.id==uid)
        self.assertEqual(u.username, 'u1')

        iq = User.insert(doesnotexist='invalid')
        self.assertRaises(KeyError, iq.execute)

    def test_insert_from(self):
        u0, u1, u2 = [User.create(username='U%s' % i) for i in range(3)]

        subquery = (User
                    .select(fn.LOWER(User.username))
                    .where(User.username << ['U0', 'U2']))
        iq = User.insert_from([User.username], subquery)
        sql, params = normal_compiler.generate_insert(iq)
        self.assertEqual(sql, (
            'INSERT INTO "users" ("username") '
            'SELECT LOWER(t2."username") FROM "users" AS t2 '
            'WHERE (t2."username" IN (?, ?))'))
        self.assertEqual(params, ['U0', 'U2'])

        iq.execute()
        usernames = sorted([u.username for u in User.select()])
        self.assertEqual(usernames, ['U0', 'U1', 'U2', 'u0', 'u2'])

    def test_insert_many(self):
        qc = len(self.queries())
        iq = User.insert_many([
            {'username': 'u1'},
            {'username': 'u2'},
            {'username': 'u3'},
            {'username': 'u4'}])
        self.assertTrue(iq.execute())

        qc2 = len(self.queries())
        if test_db.insert_many:
            self.assertEqual(qc2 - qc, 1)
        else:
            self.assertEqual(qc2 - qc, 4)
        self.assertEqual(User.select().count(), 4)

        sq = User.select(User.username).order_by(User.username)
        self.assertEqual([u.username for u in sq], ['u1', 'u2', 'u3', 'u4'])

        iq = User.insert_many([{'username': 'u5'}])
        self.assertTrue(iq.execute())
        self.assertEqual(User.select().count(), 5)

        iq = User.insert_many([
            {User.username: 'u6'},
            {User.username: 'u7'},
            {'username': 'u8'}]).execute()

        sq = User.select(User.username).order_by(User.username)
        self.assertEqual([u.username for u in sq],
                         ['u1', 'u2', 'u3', 'u4', 'u5', 'u6', 'u7', 'u8'])

    def test_insert_many_fallback(self):
        # Simulate database not supporting multiple insert (older versions of
        # sqlite).
        test_db.insert_many = False
        qc = len(self.queries())
        iq = User.insert_many([
            {'username': 'u1'},
            {'username': 'u2'},
            {'username': 'u3'},
            {'username': 'u4'}])
        self.assertTrue(iq.execute())
        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 4)
        self.assertEqual(User.select().count(), 4)

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

        rq = User.raw('select count(id) from users')
        self.assertEqual(rq.scalar(), 3)

        rq = User.raw('select username from users').tuples()
        self.assertEqual([r for r in rq], [
            ('u1',), ('u2',), ('u3',),
        ])

    def test_limits_offsets(self):
        for i in range(10):
            self.create_user(username='u%d' % i)
        sq = User.select().order_by(User.id)

        offset_no_lim = sq.offset(3)
        self.assertEqual(
            [u.username for u in offset_no_lim],
            ['u%d' % i for i in range(3, 10)]
        )

        offset_with_lim = sq.offset(5).limit(3)
        self.assertEqual(
            [u.username for u in offset_with_lim],
            ['u%d' % i for i in range(5, 8)]
        )

    def test_raw_fn(self):
        self.create_users_blogs(3, 2)  # 3 users, 2 blogs each.
        query = User.raw('select count(1) as ct from blog group by user_id')
        results = [x.ct for x in query]
        self.assertEqual(results, [2, 2, 2])


class ModelAPITestCase(ModelTestCase):
    requires = [User, Blog, Category, UserCategory]

    def test_related_name(self):
        u1 = self.create_user('u1')
        u2 = self.create_user('u2')
        b11 = Blog.create(user=u1, title='b11')
        b12 = Blog.create(user=u1, title='b12')
        b2 = Blog.create(user=u2, title='b2')

        self.assertEqual([b.title for b in u1.blog_set], ['b11', 'b12'])
        self.assertEqual([b.title for b in u2.blog_set], ['b2'])

    def test_related_name_collision(self):
        class Foo(TestModel):
            f1 = CharField()

        def make_klass():
            class FooRel(TestModel):
                foo = ForeignKeyField(Foo, related_name='f1')

        self.assertRaises(AttributeError, make_klass)

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

    def test_fk_cache_invalidated(self):
        u1 = self.create_user('u1')
        u2 = self.create_user('u2')
        b = Blog.create(user=u1, title='b')

        blog = Blog.get(Blog.pk == b)
        qc = len(self.queries())
        self.assertEqual(blog.user.id, u1.id)
        self.assertEqual(len(self.queries()), qc + 1)

        blog.user = u2.id
        self.assertEqual(blog.user.id, u2.id)
        self.assertEqual(len(self.queries()), qc + 2)

        # No additional query.
        blog.user = u2.id
        self.assertEqual(blog.user.id, u2.id)
        self.assertEqual(len(self.queries()), qc + 2)

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

    def test_category_select_related_alias(self):
        g1 = Category.create(name='g1')
        g2 = Category.create(name='g2')

        p1 = Category.create(name='p1', parent=g1)
        p2 = Category.create(name='p2', parent=g2)

        c1 = Category.create(name='c1', parent=p1)
        c11 = Category.create(name='c11', parent=p1)
        c2 = Category.create(name='c2', parent=p2)

        qc = len(self.queries())

        Grandparent = Category.alias()
        Parent = Category.alias()
        sq = Category.select(Category, Parent, Grandparent).join(
            Parent, on=(Category.parent == Parent.id)
        ).join(
            Grandparent, on=(Parent.parent == Grandparent.id)
        ).where(
            Grandparent.name == 'g1'
        ).order_by(Category.name)

        self.assertEqual([(c.name, c.parent.name, c.parent.parent.name) for c in sq], [
            ('c1', 'p1', 'g1'),
            ('c11', 'p1', 'g1'),
        ])

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

    def test_creation(self):
        self.create_users(10)
        self.assertEqual(User.select().count(), 10)

    def test_saving(self):
        self.assertEqual(User.select().count(), 0)

        u = User(username='u1')
        self.assertEqual(u.save(), 1)
        u.username = 'u2'
        self.assertEqual(u.save(), 1)

        self.assertEqual(User.select().count(), 1)

        self.assertEqual(u.delete_instance(), 1)
        self.assertEqual(u.save(), 0)

    def test_modify_model_cause_it_dirty(self):
        u = User(username='u1')
        u.save()
        self.assertFalse(u.is_dirty())

        u.username = 'u2'
        self.assertTrue(u.is_dirty())
        self.assertEqual(u.dirty_fields, [User.username])

        u.save()
        self.assertFalse(u.is_dirty())

        b = Blog.create(user=u, title='b1')
        self.assertFalse(b.is_dirty())

        b.user = u
        self.assertTrue(b.is_dirty())
        self.assertEqual(b.dirty_fields, [Blog.user])

    def test_save_only(self):
        u = User.create(username='u')
        b = Blog.create(user=u, title='b1', content='ct')
        b.title = 'b1-edit'
        b.content = 'ct-edit'

        b.save(only=[Blog.title])

        b_db = Blog.get(Blog.pk == b.pk)
        self.assertEqual(b_db.title, 'b1-edit')
        self.assertEqual(b_db.content, 'ct')

        b = Blog(user=u, title='b2', content='foo')
        b.save(only=[Blog.user, Blog.title])

        b_db = Blog.get(Blog.pk == b.pk)

        self.assertEqual(b_db.title, 'b2')
        self.assertEqual(b_db.content, '')

    def test_zero_id(self):
        if isinstance(test_db, MySQLDatabase):
            # Need to explicitly tell MySQL it's OK to use zero.
            test_db.execute_sql("SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'")
        query = 'insert into users (id, username) values (%s, %s)' % (
            test_db.interpolation, test_db.interpolation)
        test_db.execute_sql(query, (0, 'foo'))
        Blog.insert(title='foo2', user=0).execute()

        u = User.get(User.id == 0)
        b = Blog.get(Blog.user == u)

        self.assertTrue(u == u)
        self.assertTrue(u == b.user)

    def test_saving_via_create_gh111(self):
        u = User.create(username='u')
        b = Blog.create(title='foo', user=u)
        last_sql, _ = self.queries()[-1]
        self.assertFalse('pub_date' in last_sql)
        self.assertEqual(b.pub_date, None)

        b2 = Blog(title='foo2', user=u)
        b2.save()
        last_sql, _ = self.queries()[-1]
        self.assertFalse('pub_date' in last_sql)
        self.assertEqual(b2.pub_date, None)

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

    def test_first(self):
        users = self.create_users(5)
        qc = len(self.queries())

        sq = User.select().order_by(User.username)
        qr = sq.execute()

        # call it once
        first = sq.first()
        self.assertEqual(first.username, 'u1')

        # check the result cache
        self.assertEqual(len(qr._result_cache), 1)

        # call it again and we get the same result, but not an
        # extra query
        self.assertEqual(sq.first().username, 'u1')

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

        usernames = [u.username for u in sq]
        self.assertEqual(usernames, ['u1', 'u2', 'u3', 'u4', 'u5'])

        qc3 = len(self.queries())
        self.assertEqual(qc3, qc2)

        # call after iterating
        self.assertEqual(sq.first().username, 'u1')

        usernames = [u.username for u in sq]
        self.assertEqual(usernames, ['u1', 'u2', 'u3', 'u4', 'u5'])

        qc3 = len(self.queries())
        self.assertEqual(qc3, qc2)

        # call it with an empty result
        sq = User.select().where(User.username == 'not-here')
        self.assertEqual(sq.first(), None)

    def test_deleting(self):
        u1 = self.create_user('u1')
        u2 = self.create_user('u2')

        self.assertEqual(User.select().count(), 2)
        u1.delete_instance()
        self.assertEqual(User.select().count(), 1)

        self.assertEqual(u2, User.get(User.username=='u2'))

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

        self.assertEqual(Blog.select().limit(4).offset(3).count(), 4)
        self.assertEqual(Blog.select().limit(4).offset(3).count(True), 10)

        # Calling `distinct()` will result in a call to wrapped_count().
        uc = User.select().join(Blog).distinct().count()
        self.assertEqual(uc, 2)

        # Test with clear limit = True.
        self.assertEqual(User.select().limit(1).count(clear_limit=True), 2)
        self.assertEqual(
            User.select().limit(1).wrapped_count(clear_limit=True), 2)

        # Test with clear limit = False.
        self.assertEqual(User.select().limit(1).count(clear_limit=False), 1)
        self.assertEqual(
            User.select().limit(1).wrapped_count(clear_limit=False), 1)

    def test_ordering(self):
        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        u3 = User.create(username='u2')
        users = User.select().order_by(User.username.desc(), User.id.desc())
        self.assertEqual([u.get_id() for u in users], [u3.id, u2.id, u1.id])

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
        # create a unicode literal
        ustr = ulit('Lýðveldið Ísland')
        u = self.create_user(username=ustr)

        # query using the unicode literal
        u_db = User.get(User.username == ustr)

        # the db returns a unicode literal
        self.assertEqual(u_db.username, ustr)

        # delete the user
        self.assertEqual(u.delete_instance(), 1)

        # convert the unicode to a utf8 string
        utf8_str = ustr.encode('utf-8')

        # create using the utf8 string
        u2 = self.create_user(username=utf8_str)

        # query using unicode literal
        u2_db = User.get(User.username == ustr)

        # we get unicode back
        self.assertEqual(u2_db.username, ustr)

    def test_unicode_issue202(self):
        ustr = ulit('M\u00f6rk')
        user = User.create(username=ustr)
        self.assertEqual(user.username, ustr)


class TestMultipleForeignKey(ModelTestCase):
    requires = [Manufacturer, Component, Computer]
    test_values = [
        ['3TB', '16GB', 'i7'],
        ['128GB', '1GB', 'ARM'],
    ]

    def setUp(self):
        super(TestMultipleForeignKey, self).setUp()
        intel = Manufacturer.create(name='Intel')
        amd = Manufacturer.create(name='AMD')
        kingston = Manufacturer.create(name='Kingston')
        for hard_drive, memory, processor in self.test_values:
            c = Computer.create(
                hard_drive=Component.create(name=hard_drive),
                memory=Component.create(name=memory, manufacturer=kingston),
                processor=Component.create(name=processor, manufacturer=intel))

        # The 2nd computer has an AMD processor.
        c.processor.manufacturer = amd
        c.processor.save()

    def test_multi_join(self):
        query_start = len(self.queries())
        HDD = Component.alias()
        HDDMf = Manufacturer.alias()
        Memory = Component.alias()
        MemoryMf = Manufacturer.alias()
        Processor = Component.alias()
        ProcessorMf = Manufacturer.alias()
        query = (Computer
                 .select(
                     Computer,
                     HDD,
                     Memory,
                     Processor,
                     HDDMf,
                     MemoryMf,
                     ProcessorMf)
                 .join(HDD, on=(Computer.hard_drive == HDD.id))
                 .join(
                     HDDMf,
                     JOIN_LEFT_OUTER,
                     on=(HDD.manufacturer == HDDMf.id))
                 .switch(Computer)
                 .join(Memory, on=(Computer.memory == Memory.id))
                 .join(
                     MemoryMf,
                     JOIN_LEFT_OUTER,
                     on=(Memory.manufacturer == MemoryMf.id))
                 .switch(Computer)
                 .join(Processor, on=(Computer.processor == Processor.id))
                 .join(
                     ProcessorMf,
                     JOIN_LEFT_OUTER,
                     on=(Processor.manufacturer == ProcessorMf.id))
                 .order_by(Computer.id))

        vals = []
        manufacturers = []
        for computer in query:
            components = [
                computer.hard_drive,
                computer.memory,
                computer.processor]
            vals.append([component.name for component in components])
            for component in components:
                if component.manufacturer:
                    manufacturers.append(component.manufacturer.name)
                else:
                    manufacturers.append(None)

        self.assertEqual(vals, self.test_values)
        self.assertEqual(manufacturers, [
            None, 'Kingston', 'Intel',
            None, 'Kingston', 'AMD',
        ])
        self.assertEqual(len(self.queries()), query_start + 1)


class ModelAggregateTestCase(ModelTestCase):
    requires = [OrderedModel, User, Blog]

    def create_ordered_models(self):
        return [
            OrderedModel.create(
                title=i, created=datetime.datetime(2013, 1, i + 1))
            for i in range(3)]

    def create_user_blogs(self):
        users = []
        ct = 0
        for i in range(2):
            user = User.create(username='u-%d' % i)
            for j in range(2):
                ct += 1
                Blog.create(
                    user=user,
                    title='b-%d-%d' % (i, j),
                    pub_date=datetime.datetime(2013, 1, ct))
            users.append(user)
        return users

    def test_annotate_int(self):
        users = self.create_user_blogs()
        annotated = User.select().annotate(Blog, fn.Count(Blog.pk).alias('ct'))
        for i, user in enumerate(annotated):
            self.assertEqual(user.ct, 2)
            self.assertEqual(user.username, 'u-%d' % i)

    def test_annotate_datetime(self):
        users = self.create_user_blogs()
        annotated = (User
                     .select()
                     .annotate(Blog, fn.Max(Blog.pub_date).alias('max_pub')))
        user_0, user_1 = annotated
        self.assertEqual(user_0.max_pub, datetime.datetime(2013, 1, 2))
        self.assertEqual(user_1.max_pub, datetime.datetime(2013, 1, 4))

    def test_aggregate_int(self):
        models = self.create_ordered_models()
        max_id = OrderedModel.select().aggregate(fn.Max(OrderedModel.id))
        self.assertEqual(max_id, models[-1].id)

    def test_aggregate_datetime(self):
        models = self.create_ordered_models()
        max_created = (OrderedModel
                       .select()
                       .aggregate(fn.Max(OrderedModel.created)))
        self.assertEqual(max_created, models[-1].created)


class FromMultiTableTestCase(ModelTestCase):
    requires = [Blog, Comment, User]

    def setUp(self):
        super(FromMultiTableTestCase, self).setUp()

        for u in range(2):
            user = User.create(username='u%s' % u)
            for i in range(3):
                b = Blog.create(user=user, title='b%s-%s' % (u, i))
                for j in range(i):
                    Comment.create(blog=b, comment='c%s-%s' % (i, j))

    def test_from_multi_table(self):
        q = (Blog
             .select(Blog, User)
             .from_(Blog, User)
             .where(
                 (Blog.user == User.id) &
                 (User.username == 'u0'))
             .order_by(Blog.pk)
             .naive())

        qc = len(self.queries())
        blogs = [b.title for b in q]
        self.assertEqual(blogs, ['b0-0', 'b0-1', 'b0-2'])

        usernames = [b.username for b in q]
        self.assertEqual(usernames, ['u0', 'u0', 'u0'])
        self.assertEqual(len(self.queries()) - qc, 1)

    def test_subselect(self):
        inner = User.select(User.username)
        self.assertEqual(
            [u.username for u in inner.order_by(User.username)], ['u0', 'u1'])

        # Have to manually specify the alias as "t1" because the outer query
        # will expect that.
        outer = (User
                 .select(User.username)
                 .from_(inner.alias('t1')))
        sql, params = compiler.generate_select(outer)
        self.assertEqual(sql, (
            'SELECT users."username" FROM '
            '(SELECT users."username" FROM "users" AS users) AS t1'))

        self.assertEqual(
            [u.username for u in outer.order_by(User.username)], ['u0', 'u1'])

    def test_subselect_with_column(self):
        inner = User.select(User.username.alias('name')).alias('t1')
        outer = (User
                 .select(inner.c.name)
                 .from_(inner))
        sql, params = compiler.generate_select(outer)
        self.assertEqual(sql, (
            'SELECT "t1"."name" FROM '
            '(SELECT users."username" AS name FROM "users" AS users) AS t1'))

        query = outer.order_by(inner.c.name.desc())
        self.assertEqual([u[0] for u in query.tuples()], ['u1', 'u0'])

    def test_subselect_with_join(self):
        inner = User.select(User.id, User.username).alias('q1')
        outer = (Blog
                 .select(inner.c.id, inner.c.username)
                 .from_(inner)
                 .join(Comment, on=(inner.c.id == Comment.id)))
        sql, params = compiler.generate_select(outer)
        self.assertEqual(sql, (
            'SELECT "q1"."id", "q1"."username" FROM ('
            'SELECT users."id", users."username" FROM "users" AS users) AS q1 '
            'INNER JOIN "comment" AS comment ON ("q1"."id" = comment."id")'))


class PrefetchTestCase(ModelTestCase):
    requires = [User, Blog, Comment, Parent, Child, Orphan, ChildPet, OrphanPet, Category]
    user_data = [
        ('u1', (('b1', ('b1-c1', 'b1-c2')), ('b2', ('b2-c1',)))),
        ('u2', ()),
        ('u3', (('b3', ('b3-c1', 'b3-c2')), ('b4', ()))),
        ('u4', (('b5', ('b5-c1', 'b5-c2')), ('b6', ('b6-c1',)))),
    ]
    parent_data = [
        ('p1', (
            # children
            (
                ('c1', ('c1-p1', 'c1-p2')),
                ('c2', ('c2-p1',)),
                ('c3', ('c3-p1',)),
                ('c4', ()),
            ),
            # orphans
            (
                ('o1', ('o1-p1', 'o1-p2')),
                ('o2', ('o2-p1',)),
                ('o3', ('o3-p1',)),
                ('o4', ()),
            ),
        )),
        ('p2', ((), ())),
        ('p3', (
            # children
            (
                ('c6', ()),
                ('c7', ('c7-p1',)),
            ),
            # orphans
            (
                ('o6', ('o6-p1', 'o6-p2')),
                ('o7', ('o7-p1',)),
            ),
        )),
    ]

    def setUp(self):
        super(PrefetchTestCase, self).setUp()
        for parent, (children, orphans) in self.parent_data:
            p = Parent.create(data=parent)
            for child_pets in children:
                child, pets = child_pets
                c = Child.create(parent=p, data=child)
                for pet in pets:
                    ChildPet.create(child=c, data=pet)
            for orphan_pets in orphans:
                orphan, pets = orphan_pets
                o = Orphan.create(parent=p, data=orphan)
                for pet in pets:
                    OrphanPet.create(orphan=o, data=pet)

        for user, blog_comments in self.user_data:
            u = User.create(username=user)
            for blog, comments in blog_comments:
                b = Blog.create(user=u, title=blog, content='')
                for c in comments:
                    Comment.create(blog=b, comment=c)

    def test_prefetch_simple(self):
        sq = User.select().where(User.username != 'u3')
        sq2 = Blog.select().where(Blog.title != 'b2')
        sq3 = Comment.select()
        qc = len(self.queries())

        prefetch_sq = prefetch(sq, sq2, sq3)
        results = []
        for user in prefetch_sq:
            results.append(user.username)
            for blog in user.blog_set_prefetch:
                results.append(blog.title)
                for comment in blog.comments_prefetch:
                    results.append(comment.comment)

        self.assertEqual(results, [
            'u1', 'b1', 'b1-c1', 'b1-c2',
            'u2',
            'u4', 'b5', 'b5-c1', 'b5-c2', 'b6', 'b6-c1',
        ])
        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 3)

        results = []
        for user in prefetch_sq:
            for blog in user.blog_set_prefetch:
                results.append(blog.user.username)
                for comment in blog.comments_prefetch:
                    results.append(comment.blog.title)
        self.assertEqual(results, [
            'u1', 'b1', 'b1', 'u4', 'b5', 'b5', 'u4', 'b6',
        ])
        qc3 = len(self.queries())
        self.assertEqual(qc3, qc2)

    def test_prefetch_multi_depth(self):
        sq = Parent.select()
        sq2 = Child.select()
        sq3 = Orphan.select()
        sq4 = ChildPet.select()
        sq5 = OrphanPet.select()
        qc = len(self.queries())

        prefetch_sq = prefetch(sq, sq2, sq3, sq4, sq5)
        results = []
        for parent in prefetch_sq:
            results.append(parent.data)
            for child in parent.child_set_prefetch:
                results.append(child.data)
                for pet in child.childpet_set_prefetch:
                    results.append(pet.data)

            for orphan in parent.orphan_set_prefetch:
                results.append(orphan.data)
                for pet in orphan.orphanpet_set_prefetch:
                    results.append(pet.data)

        self.assertEqual(results, [
            'p1', 'c1', 'c1-p1', 'c1-p2', 'c2', 'c2-p1', 'c3', 'c3-p1', 'c4',
                  'o1', 'o1-p1', 'o1-p2', 'o2', 'o2-p1', 'o3', 'o3-p1', 'o4',
            'p2',
            'p3', 'c6', 'c7', 'c7-p1', 'o6', 'o6-p1', 'o6-p2', 'o7', 'o7-p1',
        ])
        self.assertEqual(len(self.queries()) - qc, 5)

    def test_prefetch_no_aggregate(self):
        qc = len(self.queries())
        query = (User
                 .select(User, Blog)
                 .join(Blog, JOIN_LEFT_OUTER)
                 .order_by(User.username, Blog.title))
        results = []
        for user in query:
            results.append((
                user.username,
                user.blog.title))

        self.assertEqual(results, [
            ('u1', 'b1'),
            ('u1', 'b2'),
            ('u2', None),
            ('u3', 'b3'),
            ('u3', 'b4'),
            ('u4', 'b5'),
            ('u4', 'b6'),
        ])
        self.assertEqual(len(self.queries()) - qc, 1)

    def test_aggregate_users(self):
        qc = len(self.queries())
        query = (User
                 .select(User, Blog, Comment)
                 .join(Blog, JOIN_LEFT_OUTER)
                 .join(Comment, JOIN_LEFT_OUTER)
                 .order_by(User.username, Blog.title, Comment.id)
                 .aggregate_rows())

        results = []
        for user in query:
            results.append((
                user.username,
                [(blog.title, [comment.comment for comment in blog.comments])
                 for blog in user.blog_set]))

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

        self.assertEqual(results, [
            ('u1', [
                ('b1', ['b1-c1', 'b1-c2']),
                ('b2', ['b2-c1'])]),
            ('u2', []),
            ('u3', [
                ('b3', ['b3-c1', 'b3-c2']),
                ('b4', [])]),
            ('u4', [
                ('b5', ['b5-c1', 'b5-c2']),
                ('b6', ['b6-c1'])]),
        ])

    def test_aggregate_blogs(self):
        qc = len(self.queries())
        query = (Blog
                 .select(Blog, User, Comment)
                 .join(User)
                 .switch(Blog)
                 .join(Comment, JOIN_LEFT_OUTER)
                 .order_by(Blog.title, User.username, Comment.id)
                 .aggregate_rows())

        results = []
        for blog in query:
            results.append((
                blog.user.username,
                blog.title,
                [comment.comment for comment in blog.comments]))

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

        self.assertEqual(results, [
            ('u1', 'b1', ['b1-c1', 'b1-c2']),
            ('u1', 'b2', ['b2-c1']),
            ('u3', 'b3', ['b3-c1', 'b3-c2']),
            ('u3', 'b4', []),
            ('u4', 'b5', ['b5-c1', 'b5-c2']),
            ('u4', 'b6', ['b6-c1']),
        ])

    def test_aggregate_parent_child(self):
        qc = len(self.queries())
        query = (Parent
                 .select(Parent, Child, Orphan, ChildPet, OrphanPet)
                 .join(Child, JOIN_LEFT_OUTER)
                 .join(ChildPet, JOIN_LEFT_OUTER)
                 .switch(Parent)
                 .join(Orphan, JOIN_LEFT_OUTER)
                 .join(OrphanPet, JOIN_LEFT_OUTER)
                 .order_by(
                     Parent.data,
                     Child.data,
                     ChildPet.id,
                     Orphan.data,
                     OrphanPet.id)
                 .aggregate_rows())

        results = []
        for parent in query:
            results.append((
                parent.data,
                [(child.data, [pet.data for pet in child.childpet_set])
                 for child in parent.child_set],
                [(orphan.data, [pet.data for pet in orphan.orphanpet_set])
                 for orphan in parent.orphan_set]
            ))

        # Without the `.aggregate_rows()` call, this would be 289!!
        self.assertEqual(len(self.queries()) - qc, 1)
        self.assertEqual(results, [
            ('p1',
             [('c1', ['c1-p1', 'c1-p2']),
              ('c2', ['c2-p1']),
              ('c3', ['c3-p1']),
              ('c4', [])],
             [('o1', ['o1-p1', 'o1-p2']),
              ('o2', ['o2-p1']),
              ('o3', ['o3-p1']),
              ('o4', [])],
            ),
            ('p2', [], []),
            ('p3',
             [('c6', []),
              ('c7', ['c7-p1'])],
             [('o6', ['o6-p1', 'o6-p2']),
              ('o7', ['o7-p1'])],)
        ])


class TestPrefetchNonPKFK(ModelTestCase):
    requires = [Package, PackageItem]
    data = {
        '101': ['a', 'b'],
        '102': ['c'],
        '103': [],
        '104': ['a', 'b', 'c', 'd', 'e'],
    }

    def setUp(self):
        super(TestPrefetchNonPKFK, self).setUp()
        for barcode, titles in self.data.items():
            Package.create(barcode=barcode)
            for title in titles:
                PackageItem.create(package=barcode, title=title)

    def test_prefetch(self):
        packages = Package.select().order_by(Package.barcode)
        items = PackageItem.select().order_by(PackageItem.id)
        query = prefetch(packages, items)

        for package, (barcode, titles) in zip(query, sorted(self.data.items())):
            self.assertEqual(package.barcode, barcode)
            self.assertEqual(
                [item.title for item in package.items_prefetch],
                titles)

        packages = (Package
                    .select()
                    .where(Package.barcode << ['101', '104'])
                    .order_by(Package.id))
        items = items.where(PackageItem.title << ['a', 'c', 'e'])
        query = prefetch(packages, items)
        accum = {}
        for package in query:
            accum[package.barcode] = [
                item.title for item in package.items_prefetch]

        self.assertEqual(accum, {
            '101': ['a'],
            '104': ['a', 'c','e'],
        })

class RecursiveDeleteTestCase(ModelTestCase):
    requires = [
        Parent, Child, Orphan, ChildPet, OrphanPet, Package, PackageItem]

    def setUp(self):
        super(RecursiveDeleteTestCase, self).setUp()
        p1 = Parent.create(data='p1')
        p2 = Parent.create(data='p2')
        c11 = Child.create(parent=p1)
        c12 = Child.create(parent=p1)
        c21 = Child.create(parent=p2)
        c22 = Child.create(parent=p2)
        o11 = Orphan.create(parent=p1)
        o12 = Orphan.create(parent=p1)
        o21 = Orphan.create(parent=p2)
        o22 = Orphan.create(parent=p2)
        ChildPet.create(child=c11)
        ChildPet.create(child=c12)
        ChildPet.create(child=c21)
        ChildPet.create(child=c22)
        OrphanPet.create(orphan=o11)
        OrphanPet.create(orphan=o12)
        OrphanPet.create(orphan=o21)
        OrphanPet.create(orphan=o22)
        self.p1 = p1
        self.p2 = p2

    def test_recursive_update(self):
        self.p1.delete_instance(recursive=True)
        counts = (
            #query,fk,p1,p2,tot
            (Child.select(), Child.parent, 0, 2, 2),
            (Orphan.select(), Orphan.parent, 0, 2, 4),
            (ChildPet.select().join(Child), Child.parent, 0, 2, 2),
            (OrphanPet.select().join(Orphan), Orphan.parent, 0, 2, 4),
        )

        for query, fk, p1_ct, p2_ct, tot in counts:
            self.assertEqual(query.where(fk == self.p1).count(), p1_ct)
            self.assertEqual(query.where(fk == self.p2).count(), p2_ct)
            self.assertEqual(query.count(), tot)

    def test_recursive_delete(self):
        self.p1.delete_instance(recursive=True, delete_nullable=True)
        counts = (
            #query,fk,p1,p2,tot
            (Child.select(), Child.parent, 0, 2, 2),
            (Orphan.select(), Orphan.parent, 0, 2, 2),
            (ChildPet.select().join(Child), Child.parent, 0, 2, 2),
            (OrphanPet.select().join(Orphan), Orphan.parent, 0, 2, 2),
        )

        for query, fk, p1_ct, p2_ct, tot in counts:
            self.assertEqual(query.where(fk == self.p1).count(), p1_ct)
            self.assertEqual(query.where(fk == self.p2).count(), p2_ct)
            self.assertEqual(query.count(), tot)

    def test_recursive_non_pk_fk(self):
        for i in range(3):
            Package.create(barcode=str(i))
            for j in range(4):
                PackageItem.create(package=str(i), title='%s-%s' % (i, j))

        self.assertEqual(Package.select().count(), 3)
        self.assertEqual(PackageItem.select().count(), 12)

        Package.get(Package.barcode == '1').delete_instance(recursive=True)

        self.assertEqual(Package.select().count(), 2)
        self.assertEqual(PackageItem.select().count(), 8)

        items = (PackageItem
                 .select(PackageItem.title)
                 .order_by(PackageItem.id)
                 .tuples())
        self.assertEqual([i[0] for i in items], [
            '0-0', '0-1', '0-2', '0-3',
            '2-0', '2-1', '2-2', '2-3',
        ])


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


class CompositeKeyTestCase(ModelTestCase):
    requires = [Tag, Post, TagPostThrough, CompositeKeyModel, User, UserThing]

    def setUp(self):
        super(CompositeKeyTestCase, self).setUp()
        tags = [Tag.create(tag='t%d' % i) for i in range(1, 4)]
        posts = [Post.create(title='p%d' % i) for i in range(1, 4)]
        p12 = Post.create(title='p12')
        for t, p in zip(tags, posts):
            TagPostThrough.create(tag=t, post=p)
        TagPostThrough.create(tag=tags[0], post=p12)
        TagPostThrough.create(tag=tags[1], post=p12)

    def test_create_table_query(self):
        query, params = compiler.create_table(TagPostThrough)
        self.assertEqual(
            query,
            'CREATE TABLE "tagpostthrough" '
            '("tag_id" INTEGER NOT NULL, '
            '"post_id" INTEGER NOT NULL, '
            'PRIMARY KEY ("tag_id", "post_id"), '
            'FOREIGN KEY ("tag_id") REFERENCES "tag" ("id"), '
            'FOREIGN KEY ("post_id") REFERENCES "post" ("id")'
            ')')

    def test_get_set_id(self):
        tpt = (TagPostThrough
               .select()
               .join(Tag)
               .switch(TagPostThrough)
               .join(Post)
               .order_by(Tag.tag, Post.title)).get()
        # Sanity check.
        self.assertEqual(tpt.tag.tag, 't1')
        self.assertEqual(tpt.post.title, 'p1')

        tag = Tag.select().where(Tag.tag == 't1').get()
        post = Post.select().where(Post.title == 'p1').get()
        self.assertEqual(tpt.get_id(), [tag, post])

        # set_id is a no-op.
        tpt.set_id(None)
        self.assertEqual(tpt.get_id(), [tag, post])

    def test_querying(self):
        posts = (Post.select()
                 .join(TagPostThrough)
                 .join(Tag)
                 .where(Tag.tag == 't1')
                 .order_by(Post.title))
        self.assertEqual([p.title for p in posts], ['p1', 'p12'])

        tags = (Tag.select()
                .join(TagPostThrough)
                .join(Post)
                .where(Post.title == 'p12')
                .order_by(Tag.tag))
        self.assertEqual([t.tag for t in tags], ['t1', 't2'])

    def test_composite_key_model(self):
        CKM = CompositeKeyModel
        values = [
            ('a', 1, 1.0),
            ('a', 2, 2.0),
            ('b', 1, 1.0),
            ('b', 2, 2.0)]
        c1, c2, c3, c4 = [
            CKM.create(f1=f1, f2=f2, f3=f3) for f1, f2, f3 in values]

        # Update a single row, giving it a new value for `f3`.
        CKM.update(f3=3.0).where((CKM.f1 == 'a') & (CKM.f2 == 2)).execute()

        c = CKM.get((CKM.f1 == 'a') & (CKM.f2 == 2))
        self.assertEqual(c.f3, 3.0)

        # Update the `f3` value and call `save()`, triggering an update.
        c3.f3 = 4.0
        c3.save()

        c = CKM.get((CKM.f1 == 'b') & (CKM.f2 == 1))
        self.assertEqual(c.f3, 4.0)

        # Only 1 row updated.
        query = CKM.select().where(CKM.f3 == 4.0)
        self.assertEqual(query.wrapped_count(), 1)

        # Unfortunately this does not work since the original value of the
        # PK is lost (and hence cannot be used to update).
        c4.f1 = 'c'
        c4.save()
        self.assertRaises(
            CKM.DoesNotExist, CKM.get, (CKM.f1 == 'c') & (CKM.f2 == 2))

    def test_count_composite_key(self):
        CKM = CompositeKeyModel
        values = [
            ('a', 1, 1.0),
            ('a', 2, 2.0),
            ('b', 1, 1.0),
            ('b', 2, 1.0)]
        for f1, f2, f3 in values:
            CKM.create(f1=f1, f2=f2, f3=f3)

        self.assertEqual(CKM.select().wrapped_count(), 4)
        self.assertEqual(CKM.select().count(), 4)
        self.assertTrue(CKM.select().where(
            (CKM.f1 == 'a') &
            (CKM.f2 == 1)).exists())
        self.assertFalse(CKM.select().where(
            (CKM.f1 == 'a') &
            (CKM.f2 == 3)).exists())

    def test_delete_instance(self):
        u1, u2 = [User.create(username='u%s' % i) for i in range(2)]
        ut1 = UserThing.create(thing='t1', user=u1)
        ut2 = UserThing.create(thing='t2', user=u1)
        ut3 = UserThing.create(thing='t1', user=u2)
        ut4 = UserThing.create(thing='t3', user=u2)

        res = ut1.delete_instance()
        self.assertEqual(res, 1)
        self.assertEqual(
            [x.thing for x in UserThing.select().order_by(UserThing.thing)],
            ['t1', 't2', 't3'])


class ManyToManyTestCase(ModelTestCase):
    requires = [User, Category, UserCategory]

    def setUp(self):
        super(ManyToManyTestCase, self).setUp()
        users = ['u1', 'u2', 'u3']
        categories = ['c1', 'c2', 'c3', 'c12', 'c23']
        user_to_cat = {
            'u1': ['c1', 'c12'],
            'u2': ['c2', 'c12', 'c23'],
        }
        for u in users:
            User.create(username=u)
        for c in categories:
            Category.create(name=c)
        for user, categories in user_to_cat.items():
            user = User.get(User.username == user)
            for category in categories:
                UserCategory.create(
                    user=user,
                    category=Category.get(Category.name == category))

    def test_m2m(self):
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

    def test_many_to_many_prefetch(self):
        categories = Category.select()
        users = User.select()
        # Unfortunately this is not working.
        self.assertRaises(
            AttributeError,
            prefetch,
            categories,
            UserCategory,
            users)


class FieldTypeTestCase(ModelTestCase):
    requires = [NullModel, BlobModel]

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

    def test_null_query(self):
        NullModel.delete().execute()
        nm1 = NullModel.create(char_field='nm1')
        nm2 = NullModel.create(char_field='nm2', int_field=1)
        nm3 = NullModel.create(char_field='nm3', int_field=2, float_field=3.0)

        q = ~(NullModel.int_field >> None)
        self.assertNM(q, ['nm2', 'nm3'])

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
        NM = NullModel
        nm = NM.create(char_field=4)
        nm_db = NM.get(NM.id==nm.id)
        self.assertEqual(nm_db.char_field, '4')

        nm_alpha = NM.create(char_field='Alpha')
        nm_bravo = NM.create(char_field='Bravo')

        if isinstance(test_db, SqliteDatabase):
            # Sqlite's sql-dialect uses "*" as case-sensitive lookup wildcard,
            # and pysqlcipher is simply a wrapper around sqlite's engine.
            like_wildcard = '*'
        else:
            like_wildcard = '%'
        like_str = '%sA%s' % (like_wildcard, like_wildcard)
        ilike_str = '%A%'

        case_sens = NM.select(NM.char_field).where(NM.char_field % like_str)
        self.assertEqual([x[0] for x in case_sens.tuples()], ['Alpha'])

        case_insens = NM.select(NM.char_field).where(NM.char_field ** ilike_str)
        self.assertEqual([x[0] for x in case_insens.tuples()], ['Alpha', 'Bravo'])

    def test_intfield(self):
        nm = NullModel.create(int_field='4')
        nm_db = NullModel.get(NullModel.id==nm.id)
        self.assertEqual(nm_db.int_field, 4)

    def test_floatfield(self):
        nm = NullModel.create(float_field='4.2')
        nm_db = NullModel.get(NullModel.id==nm.id)
        self.assertEqual(nm_db.float_field, 4.2)

    def test_decimalfield(self):
        D = decimal.Decimal
        nm = NullModel()
        nm.decimal_field1 = D("3.14159265358979323")
        nm.decimal_field2 = D("100.33")
        nm.save()

        nm_from_db = NullModel.get(NullModel.id==nm.id)
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

    def _time_to_delta(self, t):
        micro = t.microsecond / 1000000.
        return datetime.timedelta(
            seconds=(3600 * t.hour) + (60 * t.minute) + t.second + micro)

    def test_date_and_time_fields(self):
        dt1 = datetime.datetime(2011, 1, 2, 11, 12, 13, 54321)
        dt2 = datetime.datetime(2011, 1, 2, 11, 12, 13)
        d1 = datetime.date(2011, 1, 3)
        t1 = datetime.time(11, 12, 13, 54321)
        t2 = datetime.time(11, 12, 13)
        td1 = self._time_to_delta(t1)
        td2 = self._time_to_delta(t2)

        nm1 = NullModel.create(datetime_field=dt1, date_field=d1, time_field=t1)
        nm2 = NullModel.create(datetime_field=dt2, time_field=t2)

        nmf1 = NullModel.get(NullModel.id==nm1.id)
        self.assertEqual(nmf1.date_field, d1)
        if isinstance(test_db, MySQLDatabase):
            # mysql doesn't store microseconds
            self.assertEqual(nmf1.datetime_field, dt2)
            self.assertEqual(nmf1.time_field, td2)
        else:
            self.assertEqual(nmf1.datetime_field, dt1)
            self.assertEqual(nmf1.time_field, t1)

        nmf2 = NullModel.get(NullModel.id==nm2.id)
        self.assertEqual(nmf2.datetime_field, dt2)
        if isinstance(test_db, MySQLDatabase):
            self.assertEqual(nmf2.time_field, td2)
        else:
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

    def test_blob_field(self):
        byte_count = 256
        data = ''.join(chr(i) for i in range(256))
        blob = BlobModel.create(data=data)

        # pull from db and check binary data
        res = BlobModel.get(BlobModel.id == blob.id)
        self.assertTrue(isinstance(res.data, binary_types))

        self.assertEqual(len(res.data), byte_count)
        db_data = res.data
        binary_data = binary_construct(data)

        if db_data != binary_data and sys.version_info[:3] >= (3, 3, 3):
            db_data = db_data.tobytes()

        self.assertEqual(db_data, binary_data)

        # try querying the blob field
        binary_data = res.data

        # use the string representation
        res = BlobModel.get(BlobModel.data == data)
        self.assertEqual(res.id, blob.id)

        # use the binary representation
        res = BlobModel.get(BlobModel.data == binary_data)
        self.assertEqual(res.id, blob.id)

    def test_between(self):
        field = NullModel.int_field
        self.assertNM(field.between(1, 2), ['c1', 'c2'])
        self.assertNM(field.between(2, 3), ['c2', 'c3'])
        self.assertNM(field.between(5, 300), [])

    def test_in_(self):
        self.assertNM(NullModel.int_field.in_(1, 3), ['c1', 'c3'])
        self.assertNM(NullModel.int_field.in_(2, 5), ['c2'])

    def test_contains(self):
        self.assertNM(NullModel.char_field.contains('c2'), ['c2'])
        self.assertNM(NullModel.char_field.contains('c'), ['c1', 'c2', 'c3'])
        self.assertNM(NullModel.char_field.contains('1'), ['c1'])

    def test_startswith(self):
        NullModel.create(char_field='ch1')
        self.assertNM(NullModel.char_field.startswith('c'), ['c1', 'c2', 'c3', 'ch1'])
        self.assertNM(NullModel.char_field.startswith('ch'), ['ch1'])
        self.assertNM(NullModel.char_field.startswith('a'), [])

    def test_endswith(self):
        NullModel.create(char_field='ch1')
        self.assertNM(NullModel.char_field.endswith('1'), ['c1', 'ch1'])
        self.assertNM(NullModel.char_field.endswith('4'), [])

    def test_regexp(self):
        values = [
            'abcdefg',
            'abcd',
            'defg',
            'gij',
            'xx',
        ]
        for value in values:
            NullModel.create(char_field=value)

        def assertValues(regexp, *expected):
            query = NullModel.select().where(
                NullModel.char_field.regexp(regexp)).order_by(NullModel.id)
            values = [nm.char_field for nm in query]
            self.assertEqual(values, list(expected))

        assertValues('^ab', 'abcdefg', 'abcd')
        assertValues('d', 'abcdefg', 'abcd', 'defg')
        assertValues('efg$', 'abcdefg', 'defg')
        assertValues('a.+d', 'abcdefg', 'abcd')

    def test_concat(self):
        if database_class is MySQLDatabase:
            if TEST_VERBOSITY > 0:
                print_('Skipping `concat` for mysql.')
            return

        NullModel.create(char_field='foo')
        NullModel.create(char_field='bar')

        values = (NullModel
                  .select(
                      NullModel.char_field.concat('-nuggets').alias('nugs'))
                  .order_by(NullModel.id)
                  .dicts())
        self.assertEqual(list(values), [
            {'nugs': 'c1-nuggets'},
            {'nugs': 'c2-nuggets'},
            {'nugs': 'c3-nuggets'},
            {'nugs': 'foo-nuggets'},
            {'nugs': 'bar-nuggets'}])

class DateTimeExtractTestCase(ModelTestCase):
    requires = [NullModel]

    test_datetimes = [
        datetime.datetime(2001, 1, 2, 3, 4, 5),
        datetime.datetime(2002, 2, 3, 4, 5, 6),
        # overlap on year and hour with previous
        datetime.datetime(2002, 3, 4, 4, 6, 7),
    ]
    datetime_parts = ['year', 'month', 'day', 'hour', 'minute', 'second']
    date_parts = datetime_parts[:3]
    time_parts = datetime_parts[3:]

    def setUp(self):
        super(DateTimeExtractTestCase, self).setUp()

        self.nms = []
        for dt in self.test_datetimes:
            self.nms.append(NullModel.create(
                datetime_field=dt,
                date_field=dt.date(),
                time_field=dt.time()))

    def assertDates(self, sq, expected):
        sq = sq.tuples().order_by(NullModel.id)
        self.assertEqual(list(sq), [(e,) for e in expected])

    def assertPKs(self, sq, idxs):
        sq = sq.tuples().order_by(NullModel.id)
        self.assertEqual(list(sq), [(self.nms[i].id,) for i in idxs])

    def test_extract_datetime(self):
        self.test_extract_date(NullModel.datetime_field)
        self.test_extract_time(NullModel.datetime_field)

    def test_extract_date(self, f=None):
        if f is None:
            f = NullModel.date_field

        self.assertDates(NullModel.select(f.year), [2001, 2002, 2002])
        self.assertDates(NullModel.select(f.month), [1, 2, 3])
        self.assertDates(NullModel.select(f.day), [2, 3, 4])

    def test_extract_time(self, f=None):
        if f is None:
            f = NullModel.time_field

        self.assertDates(NullModel.select(f.hour), [3, 4, 4])
        self.assertDates(NullModel.select(f.minute), [4, 5, 6])
        self.assertDates(NullModel.select(f.second), [5, 6, 7])

    def test_extract_datetime_where(self):
        f = NullModel.datetime_field
        self.test_extract_date_where(f)
        self.test_extract_time_where(f)

        sq = NullModel.select(NullModel.id)
        self.assertPKs(sq.where((f.year == 2002) & (f.month == 2)), [1])
        self.assertPKs(sq.where((f.year == 2002) & (f.hour == 4)), [1, 2])
        self.assertPKs(sq.where((f.year == 2002) & (f.minute == 5)), [1])

    def test_extract_date_where(self, f=None):
        if f is None:
            f = NullModel.date_field

        sq = NullModel.select(NullModel.id)
        self.assertPKs(sq.where(f.year == 2001), [0])
        self.assertPKs(sq.where(f.year == 2002), [1, 2])
        self.assertPKs(sq.where(f.year == 2003), [])

        self.assertPKs(sq.where(f.month == 1), [0])
        self.assertPKs(sq.where(f.month > 1), [1, 2])
        self.assertPKs(sq.where(f.month == 4), [])

        self.assertPKs(sq.where(f.day == 2), [0])
        self.assertPKs(sq.where(f.day > 2), [1, 2])
        self.assertPKs(sq.where(f.day == 5), [])

    def test_extract_time_where(self, f=None):
        if f is None:
            f = NullModel.time_field

        sq = NullModel.select(NullModel.id)
        self.assertPKs(sq.where(f.hour == 3), [0])
        self.assertPKs(sq.where(f.hour == 4), [1, 2])
        self.assertPKs(sq.where(f.hour == 5), [])

        self.assertPKs(sq.where(f.minute == 4), [0])
        self.assertPKs(sq.where(f.minute > 4), [1, 2])
        self.assertPKs(sq.where(f.minute == 7), [])

        self.assertPKs(sq.where(f.second == 5), [0])
        self.assertPKs(sq.where(f.second > 5), [1, 2])
        self.assertPKs(sq.where(f.second == 8), [])


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

        ni1_db = NonIntModel.get(NonIntModel.pk=='a1')
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


class PrimaryForeignKeyTestCase(ModelTestCase):
    requires = [Job, JobExecutionRecord]

    def test_primary_foreign_key(self):
        # we have one job, unexecuted, and therefore no executed jobs
        job = Job.create(name='Job One')
        executed_jobs = Job.select().join(JobExecutionRecord)
        self.assertEqual([], list(executed_jobs))

        # after execution, we must have one executed job
        exec_record = JobExecutionRecord.create(job=job, status='success')
        executed_jobs = Job.select().join(JobExecutionRecord)
        self.assertEqual([job], list(executed_jobs))

        # we must not be able to create another execution record for the job
        self.assertRaises(Exception, JobExecutionRecord.create, job=job, status='success')
        test_db.rollback()


class NonPKFKCreateTableTestCase(BasePeeweeTestCase):
    def test_create_table(self):
        class A(TestModel):
            cf = CharField(max_length=100, unique=True)
            df = DecimalField(
                max_digits=4,
                decimal_places=2,
                auto_round=True,
                unique=True)

        class CF(TestModel):
            a = ForeignKeyField(A, to_field='cf')

        class DF(TestModel):
            a = ForeignKeyField(A, to_field='df')

        cf_create, _ = compiler.create_table(CF)
        self.assertEqual(
            cf_create,
            'CREATE TABLE "cf" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"a_id" VARCHAR(100) NOT NULL, '
            'FOREIGN KEY ("a_id") REFERENCES "a" ("cf"))')

        df_create, _ = compiler.create_table(DF)
        self.assertEqual(
            df_create,
            'CREATE TABLE "df" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"a_id" DECIMAL(4, 2) NOT NULL, '
            'FOREIGN KEY ("a_id") REFERENCES "a" ("df"))')

class DeferredForeignKeyTestCase(ModelTestCase):
    requires = [Snippet, Language]

    def test_field_definitions(self):
        self.assertEqual(Snippet._meta.fields['language'].rel_model, Language)
        self.assertEqual(Language._meta.fields['selected_snippet'].rel_model,
                         Snippet)

    def test_create_table_query(self):
        query, params = compiler.create_table(Snippet)
        self.assertEqual(
            query,
            'CREATE TABLE "snippet" '
            '("id" INTEGER NOT NULL PRIMARY KEY, '
            '"code" TEXT NOT NULL, '
            '"language_id" INTEGER NOT NULL, '
            'FOREIGN KEY ("language_id") REFERENCES "language" ("id")'
            ')')

        query, params = compiler.create_table(Language)
        self.assertEqual(
            query,
            'CREATE TABLE "language" '
            '("id" INTEGER NOT NULL PRIMARY KEY, '
            '"name" VARCHAR(255) NOT NULL, '
            '"selected_snippet_id" INTEGER)')

    def test_storage_retrieval(self):
        python = Language.create(name='python')
        javascript = Language.create(name='javascript')
        p1 = Snippet.create(code="print 'Hello world'", language=python)
        p2 = Snippet.create(code="print 'Goodbye world'", language=python)
        j1 = Snippet.create(code="alert('Hello world')", language=javascript)

        self.assertEqual(Snippet.get(Snippet.id == p1.id).language, python)
        self.assertEqual(Snippet.get(Snippet.id == j1.id).language, javascript)

        python.selected_snippet = p2
        python.save()

        self.assertEqual(
            Language.get(Language.id == python.id).selected_snippet, p2)
        self.assertEqual(
            Language.get(Language.id == javascript.id).selected_snippet, None)


class DBColumnTestCase(ModelTestCase):
    requires = [DBUser, DBBlog]

    def test_select(self):
        sq = DBUser.select().where(DBUser.username == 'u1')
        self.assertSelect(sq, 'dbuser."db_user_id", dbuser."db_username"', [])
        self.assertWhere(sq, '(dbuser."db_username" = ?)', ['u1'])

        sq = DBUser.select(DBUser.user_id).join(DBBlog).where(DBBlog.title == 'b1')
        self.assertSelect(sq, 'dbuser."db_user_id"', [])
        self.assertJoins(sq, ['INNER JOIN "dbblog" AS dbblog ON (dbuser."db_user_id" = dbblog."db_user")'])
        self.assertWhere(sq, '(dbblog."db_title" = ?)', ['b1'])

    def test_db_column(self):
        u1 = DBUser.create(username='u1')
        u2 = DBUser.create(username='u2')
        u2_db = DBUser.get(DBUser.user_id==u2.get_id())
        self.assertEqual(u2_db.username, 'u2')

        b1 = DBBlog.create(user=u1, title='b1')
        b2 = DBBlog.create(user=u2, title='b2')
        b2_db = DBBlog.get(DBBlog.blog_id==b2.get_id())
        self.assertEqual(b2_db.user.user_id, u2.user_id)
        self.assertEqual(b2_db.title, 'b2')

        self.assertEqual([b.title for b in u2.dbblog_set], ['b2'])


class TransactionTestCase(ModelTestCase):
    requires = [User, Blog]

    def tearDown(self):
        super(TransactionTestCase, self).tearDown()
        test_db.set_autocommit(True)

    def test_autocommit(self):
        if database_class is BerkeleyDatabase:
            if TEST_VERBOSITY > 0:
                print_('Skipping `test_autocommit` for berkeleydb.')
            return

        test_db.set_autocommit(False)

        u1 = User.create(username='u1')
        u2 = User.create(username='u2')

        # open up a new connection to the database, it won't register any blogs
        # as being created
        new_db = database_class(database_name, **database_params)
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
            User.create(username='u1')
            Blog.create() # no blog, will raise an error

        self.assertRaises(IntegrityError, will_fail)
        self.assertEqual(User.select().count(), 0)
        self.assertEqual(Blog.select().count(), 0)

        @test_db.commit_on_success
        def will_succeed():
            u = User.create(username='u1')
            Blog.create(title='b1', user=u)

        will_succeed()
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(Blog.select().count(), 1)

    def test_context_mgr(self):
        def do_will_fail():
            with test_db.transaction():
                User.create(username='u1')
                Blog.create() # no blog, will raise an error

        self.assertRaises(IntegrityError, do_will_fail)
        self.assertEqual(Blog.select().count(), 0)

        def do_will_succeed():
            with transaction(test_db):
                u = User.create(username='u1')
                Blog.create(title='b1', user=u)

        do_will_succeed()
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(Blog.select().count(), 1)

        def do_manual_rollback():
            with test_db.transaction() as txn:
                User.create(username='u2')
                txn.rollback()

        do_manual_rollback()
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(Blog.select().count(), 1)

    def test_nesting_transactions(self):
        @test_db.commit_on_success
        def outer(should_fail=False):
            self.assertEqual(test_db.transaction_depth(), 1)
            User.create(username='outer')
            inner(should_fail)
            self.assertEqual(test_db.transaction_depth(), 1)

        @test_db.commit_on_success
        def inner(should_fail):
            self.assertEqual(test_db.transaction_depth(), 2)
            User.create(username='inner')
            if should_fail:
                raise ValueError('failing')

        self.assertRaises(ValueError, outer, should_fail=True)
        self.assertEqual(User.select().count(), 0)
        self.assertEqual(test_db.transaction_depth(), 0)

        outer(should_fail=False)
        self.assertEqual(User.select().count(), 2)
        self.assertEqual(test_db.transaction_depth(), 0)


class ConcurrencyTestCase(ModelTestCase):
    requires = [User]
    threads = 4

    def setUp(self):
        self._orig_db = test_db
        kwargs = {'threadlocals': True}
        try:  # Some engines need the extra kwargs.
            kwargs.update(test_db.connect_kwargs)
        except:
            pass
        if isinstance(test_db, SqliteDatabase):
            # Put a very large timeout in place to avoid `database is locked`
            # when using SQLite (default is 5).
            kwargs['timeout'] = 30

        User._meta.database = database_class(database_name, **kwargs)
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

        for i in range(self.threads):
            threads.append(threading.Thread(target=create_user_thread, args=(i*10, i * 10 + 10)))

        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(User.select().count(), self.threads * 10)

    def test_multiple_readers(self):
        data_queue = Queue()

        def reader_thread(q, num):
            for i in range(num):
                data_queue.put(User.select().count())

        threads = []

        for i in range(self.threads):
            threads.append(threading.Thread(target=reader_thread, args=(data_queue, 20)))

        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(data_queue.qsize(), self.threads * 20)


class CompoundSelectTestCase(ModelTestCase):
    requires = [User, UniqueModel, OrderedModel]
    # User -> username, UniqueModel -> name, OrderedModel -> title
    test_values = {
        User.username: ['a', 'b', 'c', 'd'],
        UniqueModel.name: ['b', 'd', 'e'],
        OrderedModel.title: ['a', 'c', 'e'],
    }

    def setUp(self):
        super(CompoundSelectTestCase, self).setUp()
        for field, values in self.test_values.items():
            for value in values:
                field.model_class.create(**{field.name: value})

    def requires_op(op):
        def decorator(fn):
            @wraps(fn)
            def inner(self):
                if op in test_db.compound_operations:
                    return fn(self)
                elif TEST_VERBOSITY > 0:
                    print_('"%s" not supported, skipping %s' %
                           (op, fn.__name__))
            return inner
        return decorator

    def assertValues(self, query, expected):
        self.assertEqual(sorted(query.tuples()),
                         [(x,) for x in sorted(expected)])

    def assertPermutations(self, op, expected):
        fields = {
            User: User.username,
            UniqueModel: UniqueModel.name,
            OrderedModel: OrderedModel.title,
        }
        for key in itertools.permutations(fields.keys(), 2):
            if key in expected:
                left, right = key
                query = op(left.select(fields[left]).order_by(),
                           right.select(fields[right]).order_by())
                # Ensure the sorted tuples returned from the query are equal
                # to the sorted values we expected for this combination.
                self.assertValues(query, expected[key])

    @requires_op('UNION')
    def test_union(self):
        all_letters = ['a', 'b', 'c', 'd', 'e']
        self.assertPermutations(operator.or_, {
            (User, UniqueModel): all_letters,
            (User, OrderedModel): all_letters,
            (UniqueModel, User): all_letters,
            (UniqueModel, OrderedModel): all_letters,
            (OrderedModel, User): all_letters,
            (OrderedModel, UniqueModel): all_letters,
        })

    @requires_op('UNION')
    def test_union_count(self):
        a = User.select().where(User.username == 'a')
        c_and_d = User.select().where(User.username << ['c', 'd'])
        self.assertEqual(a.count(), 1)
        self.assertEqual(c_and_d.count(), 2)

        union = a | c_and_d
        self.assertEqual(union.wrapped_count(), 3)

        overlapping = User.select() | c_and_d
        self.assertEqual(overlapping.wrapped_count(), 4)

    @requires_op('INTERSECT')
    def test_intersect(self):
        self.assertPermutations(operator.and_, {
            (User, UniqueModel): ['b', 'd'],
            (User, OrderedModel): ['a', 'c'],
            (UniqueModel, User): ['b', 'd'],
            (UniqueModel, OrderedModel): ['e'],
            (OrderedModel, User): ['a', 'c'],
            (OrderedModel, UniqueModel): ['e'],
        })

    @requires_op('EXCEPT')
    def test_except(self):
        self.assertPermutations(operator.sub, {
            (User, UniqueModel): ['a', 'c'],
            (User, OrderedModel): ['b', 'd'],
            (UniqueModel, User): ['e'],
            (UniqueModel, OrderedModel): ['b', 'd'],
            (OrderedModel, User): ['e'],
            (OrderedModel, UniqueModel): ['a', 'c'],
        })

    @requires_op('INTERSECT')
    @requires_op('EXCEPT')
    def test_symmetric_difference(self):
        self.assertPermutations(operator.xor, {
            (User, UniqueModel): ['a', 'c', 'e'],
            (User, OrderedModel): ['b', 'd', 'e'],
            (UniqueModel, User): ['a', 'c', 'e'],
            (UniqueModel, OrderedModel): ['a', 'b', 'c', 'd'],
            (OrderedModel, User): ['b', 'd', 'e'],
            (OrderedModel, UniqueModel): ['a', 'b', 'c', 'd'],
        })

    def test_model_instances(self):
        union = (User.select(User.username) |
                 UniqueModel.select(UniqueModel.name))
        query = union.order_by(SQL('username').desc()).limit(3)
        self.assertEqual([user.username for user in query],
                         ['e', 'd', 'c'])

    @requires_op('UNION')
    @requires_op('INTERSECT')
    def test_complex(self):
        left = User.select(User.username).where(User.username << ['a', 'b'])
        right = UniqueModel.select(UniqueModel.name).where(
            UniqueModel.name << ['b', 'd', 'e'])

        query = (left & right).order_by(SQL('1'))
        self.assertEqual(list(query.dicts()), [{'username': 'b'}])

        query = (left | right).order_by(SQL('1'))
        self.assertEqual(list(query.dicts()), [
            {'username': 'a'},
            {'username': 'b'},
            {'username': 'd'},
            {'username': 'e'}])

class ModelOptionInheritanceTestCase(BasePeeweeTestCase):
    def test_db_table(self):
        self.assertEqual(User._meta.db_table, 'users')

        class Foo(TestModel):
            pass
        self.assertEqual(Foo._meta.db_table, 'foo')

        class Foo2(TestModel):
            pass
        self.assertEqual(Foo2._meta.db_table, 'foo2')

        class Foo_3(TestModel):
            pass
        self.assertEqual(Foo_3._meta.db_table, 'foo_3')

    def test_custom_options(self):
        class A(Model):
            class Meta:
                a = 'a'

        class B1(A):
            class Meta:
                b = 1

        class B2(A):
            class Meta:
                b = 2

        self.assertEqual(A._meta.a, 'a')
        self.assertEqual(B1._meta.a, 'a')
        self.assertEqual(B2._meta.a, 'a')
        self.assertEqual(B1._meta.b, 1)
        self.assertEqual(B2._meta.b, 2)

    def test_option_inheritance(self):
        x_test_db = SqliteDatabase('testing.db')
        child2_db = SqliteDatabase('child2.db')

        class FakeUser(Model):
            pass

        class ParentModel(Model):
            title = CharField()
            user = ForeignKeyField(FakeUser)

            class Meta:
                database = x_test_db

        class ChildModel(ParentModel):
            pass

        class ChildModel2(ParentModel):
            special_field = CharField()

            class Meta:
                database = child2_db

        class GrandChildModel(ChildModel):
            pass

        class GrandChildModel2(ChildModel2):
            special_field = TextField()

        self.assertEqual(ParentModel._meta.database.database, 'testing.db')
        self.assertEqual(ParentModel._meta.model_class, ParentModel)

        self.assertEqual(ChildModel._meta.database.database, 'testing.db')
        self.assertEqual(ChildModel._meta.model_class, ChildModel)
        self.assertEqual(sorted(ChildModel._meta.fields.keys()), [
            'id', 'title', 'user'
        ])

        self.assertEqual(ChildModel2._meta.database.database, 'child2.db')
        self.assertEqual(ChildModel2._meta.model_class, ChildModel2)
        self.assertEqual(sorted(ChildModel2._meta.fields.keys()), [
            'id', 'special_field', 'title', 'user'
        ])

        self.assertEqual(GrandChildModel._meta.database.database, 'testing.db')
        self.assertEqual(GrandChildModel._meta.model_class, GrandChildModel)
        self.assertEqual(sorted(GrandChildModel._meta.fields.keys()), [
            'id', 'title', 'user'
        ])

        self.assertEqual(GrandChildModel2._meta.database.database, 'child2.db')
        self.assertEqual(GrandChildModel2._meta.model_class, GrandChildModel2)
        self.assertEqual(sorted(GrandChildModel2._meta.fields.keys()), [
            'id', 'special_field', 'title', 'user'
        ])
        self.assertTrue(isinstance(GrandChildModel2._meta.fields['special_field'], TextField))

    def test_order_by_inheritance(self):
        class Base(TestModel):
            created = DateTimeField()

            class Meta:
                order_by = ('-created',)

        class Foo(Base):
            data = CharField()

        class Bar(Base):
            val = IntegerField()
            class Meta:
                order_by = ('-val',)

        foo_order_by = Foo._meta.order_by[0]
        self.assertTrue(isinstance(foo_order_by, Field))
        self.assertTrue(foo_order_by.model_class is Foo)
        self.assertEqual(foo_order_by.name, 'created')

        bar_order_by = Bar._meta.order_by[0]
        self.assertTrue(isinstance(bar_order_by, Field))
        self.assertTrue(bar_order_by.model_class is Bar)
        self.assertEqual(bar_order_by.name, 'val')


class ModelInheritanceTestCase(ModelTestCase):
    requires = [Blog, BlogTwo, User]

    def test_model_inheritance_attrs(self):
        self.assertEqual(Blog._meta.get_field_names(), ['pk', 'user', 'title', 'content', 'pub_date'])
        self.assertEqual(BlogTwo._meta.get_field_names(), ['pk', 'user', 'content', 'pub_date', 'title', 'extra_field'])

        self.assertEqual(Blog._meta.primary_key.name, 'pk')
        self.assertEqual(BlogTwo._meta.primary_key.name, 'pk')

        self.assertEqual(Blog.user.related_name, 'blog_set')
        self.assertEqual(BlogTwo.user.related_name, 'blogtwo_set')

        self.assertEqual(User.blog_set.rel_model, Blog)
        self.assertEqual(User.blogtwo_set.rel_model, BlogTwo)

        self.assertFalse(BlogTwo._meta.db_table == Blog._meta.db_table)

    def test_model_inheritance_flow(self):
        u = User.create(username='u')

        b = Blog.create(title='b', user=u)
        b2 = BlogTwo.create(title='b2', extra_field='foo', user=u)

        self.assertEqual(list(u.blog_set), [b])
        self.assertEqual(list(u.blogtwo_set), [b2])

        self.assertEqual(Blog.select().count(), 1)
        self.assertEqual(BlogTwo.select().count(), 1)

        b_from_db = Blog.get(Blog.pk==b.pk)
        b2_from_db = BlogTwo.get(BlogTwo.pk==b2.pk)

        self.assertEqual(b_from_db.user, u)
        self.assertEqual(b2_from_db.user, u)
        self.assertEqual(b2_from_db.extra_field, 'foo')


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

    def test_sql_error(self):
        bad_sql = 'select asdf from -1;'
        self.assertRaises(Exception, query_db.execute_sql, bad_sql)
        self.assertEqual(query_db.last_error, (bad_sql, None))

class _SqliteDateTestHelper(BasePeeweeTestCase):
    datetimes = [
        datetime.datetime(2000, 1, 2, 3, 4, 5),
        datetime.datetime(2000, 2, 3, 4, 5, 6),
    ]

    def create_date_model(self, date_fn):
        dp_db = SqliteDatabase(':memory:')
        class SqDp(Model):
            datetime_field = DateTimeField()
            date_field = DateField()
            time_field = TimeField()

            class Meta:
                database = dp_db

            @classmethod
            def date_query(cls, field, part):
                return (SqDp
                        .select(date_fn(field, part))
                        .tuples()
                        .order_by(SqDp.id))

        SqDp.create_table()

        for d in self.datetimes:
            SqDp.create(datetime_field=d, date_field=d.date(),
                        time_field=d.time())

        return SqDp

class SqliteDatePartTestCase(_SqliteDateTestHelper):
    def test_sqlite_date_part(self):
        date_fn = lambda field, part: fn.date_part(part, field)
        SqDp = self.create_date_model(date_fn)

        for part in ('year', 'month', 'day', 'hour', 'minute', 'second'):
            for i, dp in enumerate(SqDp.date_query(SqDp.datetime_field, part)):
                self.assertEqual(dp[0], getattr(self.datetimes[i], part))

        for part in ('year', 'month', 'day'):
            for i, dp in enumerate(SqDp.date_query(SqDp.date_field, part)):
                self.assertEqual(dp[0], getattr(self.datetimes[i], part))

        for part in ('hour', 'minute', 'second'):
            for i, dp in enumerate(SqDp.date_query(SqDp.time_field, part)):
                self.assertEqual(dp[0], getattr(self.datetimes[i], part))

        # ensure that the where clause works
        query = SqDp.select().where(fn.date_part('year', SqDp.datetime_field) == 2000)
        self.assertEqual(query.count(), 2)

        query = SqDp.select().where(fn.date_part('month', SqDp.datetime_field) == 1)
        self.assertEqual(query.count(), 1)
        query = SqDp.select().where(fn.date_part('month', SqDp.datetime_field) == 3)
        self.assertEqual(query.count(), 0)


class SqliteDateTruncTestCase(_SqliteDateTestHelper):
    def test_sqlite_date_trunc(self):
        date_fn = lambda field, part: fn.date_trunc(part, field)
        SqDp = self.create_date_model(date_fn)

        def assertQuery(field, part, expected):
            values = SqDp.date_query(field, part)
            self.assertEqual([r[0] for r in values], expected)

        assertQuery(SqDp.datetime_field, 'year', ['2000', '2000'])
        assertQuery(SqDp.datetime_field, 'month', ['2000-01', '2000-02'])
        assertQuery(SqDp.datetime_field, 'day', ['2000-01-02', '2000-02-03'])
        assertQuery(SqDp.datetime_field, 'hour', [
            '2000-01-02 03', '2000-02-03 04'])
        assertQuery(SqDp.datetime_field, 'minute', [
            '2000-01-02 03:04', '2000-02-03 04:05'])
        assertQuery(SqDp.datetime_field, 'second', [
            '2000-01-02 03:04:05', '2000-02-03 04:05:06'])


class AutoRollbackTestCase(ModelTestCase):
    requires = [User, Blog]

    def setUp(self):
        test_db.autorollback = True
        super(AutoRollbackTestCase, self).setUp()

    def tearDown(self):
        test_db.autorollback = False
        test_db.set_autocommit(True)
        super(AutoRollbackTestCase, self).tearDown()

    def test_auto_rollback(self):
        # Exceptions are still raised.
        self.assertRaises(IntegrityError, Blog.create)

        # The transaction should have been automatically rolled-back, allowing
        # us to create new objects (in a new transaction).
        u = User.create(username='u')
        self.assertTrue(u.id)

        # No-op, the previous INSERT was already committed.
        test_db.rollback()

        # Ensure we can get our user back.
        u_db = User.get(User.username == 'u')
        self.assertEqual(u.id, u_db.id)

    def test_transaction_ctx_mgr(self):
        'Only auto-rollback when autocommit is enabled.'
        def create_error():
            self.assertRaises(IntegrityError, Blog.create)

        # autocommit is disabled in a transaction ctx manager.
        with test_db.transaction():
            # Error occurs, but exception is caught, leaving the current txn
            # in a bad state.
            create_error()

            try:
                create_error()
            except Exception as exc:
                # Subsequent call will raise an InternalError with postgres.
                self.assertTrue(isinstance(exc, InternalError))
            else:
                self.assertFalse(database_class is PostgresqlDatabase)

        # New transactions are not affected.
        self.test_auto_rollback()

    def test_manual(self):
        test_db.set_autocommit(False)

        # Will not be rolled back.
        self.assertRaises(IntegrityError, Blog.create)

        if database_class is PostgresqlDatabase:
            self.assertRaises(InternalError, User.create, username='u')

        test_db.rollback()
        u = User.create(username='u')
        test_db.commit()
        u_db = User.get(User.username == 'u')
        self.assertEqual(u.id, u_db.id)


class CheckConstraintTestCase(ModelTestCase):
    requires = [CheckModel]

    def test_check_constraint(self):
        CheckModel.create(value=1)
        if isinstance(test_db, MySQLDatabase):
            # MySQL silently ignores all check constraints.
            CheckModel.create(value=0)
        else:
            with test_db.transaction() as txn:
                self.assertRaises(IntegrityError, CheckModel.create, value=0)
                txn.rollback()


class SQLAllTestCase(BasePeeweeTestCase):
    def setUp(self):
        super(SQLAllTestCase, self).setUp()
        fake_db = SqliteDatabase(':memory:')
        UniqueModel._meta.database = fake_db
        SeqModelA._meta.database = fake_db
        MultiIndexModel._meta.database = fake_db

    def tearDown(self):
        super(SQLAllTestCase, self).tearDown()
        UniqueModel._meta.database = test_db
        SeqModelA._meta.database = test_db
        MultiIndexModel._meta.database = test_db

    def test_sqlall(self):
        sql = UniqueModel.sqlall()
        self.assertEqual(sql, [
            ('CREATE TABLE "uniquemodel" ("id" INTEGER NOT NULL PRIMARY KEY, '
             '"name" VARCHAR(255) NOT NULL)'),
            'CREATE UNIQUE INDEX "uniquemodel_name" ON "uniquemodel" ("name")',
        ])

        sql = MultiIndexModel.sqlall()
        self.assertEqual(sql, [
            ('CREATE TABLE "multiindexmodel" ("id" INTEGER NOT NULL PRIMARY '
             'KEY, "f1" VARCHAR(255) NOT NULL, "f2" VARCHAR(255) NOT NULL, '
             '"f3" VARCHAR(255) NOT NULL)'),
            ('CREATE UNIQUE INDEX "multiindexmodel_f1_f2" ON "multiindexmodel"'
             ' ("f1", "f2")'),
            ('CREATE INDEX "multiindexmodel_f2_f3" ON "multiindexmodel" '
             '("f2", "f3")'),
        ])

        sql = SeqModelA.sqlall()
        self.assertEqual(sql, [
            ('CREATE TABLE "seqmodela" ("id" INTEGER NOT NULL PRIMARY KEY '
             'DEFAULT NEXTVAL(\'just_testing_seq\'), "num" INTEGER NOT NULL)'),
        ])


class LongIndexTestCase(BasePeeweeTestCase):
    def test_long_index(self):
        class LongIndexModel(TestModel):
            a123456789012345678901234567890 = CharField()
            b123456789012345678901234567890 = CharField()
            c123456789012345678901234567890 = CharField()

        fields = LongIndexModel._meta.get_fields()[1:]
        self.assertEqual(len(fields), 3)

        sql, params = compiler.create_index(LongIndexModel, fields, False)
        self.assertEqual(sql, (
            'CREATE INDEX "longindexmodel_85c2f7db5319d3c0c124a1594087a1cb" '
            'ON "longindexmodel" ('
            '"a123456789012345678901234567890", '
            '"b123456789012345678901234567890", '
            '"c123456789012345678901234567890")'
        ))


class ConnectionStateTestCase(BasePeeweeTestCase):
    def test_connection_state(self):
        conn = test_db.get_conn()
        self.assertFalse(test_db.is_closed())
        test_db.close()
        self.assertTrue(test_db.is_closed())
        conn = test_db.get_conn()
        self.assertFalse(test_db.is_closed())


class TopologicalSortTestCase(unittest.TestCase):
    def test_topological_sort_fundamentals(self):
        FKF = ForeignKeyField
        # we will be topo-sorting the following models
        class A(Model): pass
        class B(Model): a = FKF(A)              # must follow A
        class C(Model): a, b = FKF(A), FKF(B)   # must follow A and B
        class D(Model): c = FKF(C)              # must follow A and B and C
        class E(Model): e = FKF('self')
        # but excluding this model, which is a child of E
        class Excluded(Model): e = FKF(E)

        # property 1: output ordering must not depend upon input order
        repeatable_ordering = None
        for input_ordering in permutations([A, B, C, D, E]):
            output_ordering = sort_models_topologically(input_ordering)
            repeatable_ordering = repeatable_ordering or output_ordering
            self.assertEqual(repeatable_ordering, output_ordering)

        # property 2: output ordering must have same models as input
        self.assertEqual(len(output_ordering), 5)
        self.assertFalse(Excluded in output_ordering)

        # property 3: parents must precede children
        def assert_precedes(X, Y):
            lhs, rhs = map(output_ordering.index, [X, Y])
            self.assertTrue(lhs < rhs)
        assert_precedes(A, B)
        assert_precedes(B, C)  # if true, C follows A by transitivity
        assert_precedes(C, D)  # if true, D follows A and B by transitivity

        # property 4: independent model hierarchies must be in name order
        assert_precedes(A, E)

def permutations(xs):
    if not xs:
        yield []
    else:
        for y, ys in selections(xs):
            for pys in permutations(ys):
                yield [y] + pys

def selections(xs):
    for i in range(len(xs)):
        yield (xs[i], xs[:i] + xs[i + 1:])


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
            new_db = database_class(database_name, **database_params)

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
    print_('Skipping "for update" tests')

if test_db.for_update_nowait:
    class ForUpdateNoWaitTestCase(ModelTestCase):
        requires = [User]

        def tearDown(self):
            test_db.set_autocommit(True)

        def test_for_update_exc(self):
            u1 = self.create_user('u1')
            test_db.set_autocommit(False)

            user = (User
                    .select()
                    .where(User.username == 'u1')
                    .for_update(nowait=True)
                    .execute())

            # Open up a second conn.
            new_db = database_class(database_name, **database_params)

            class User2(User):
                class Meta:
                    database = new_db
                    db_table = User._meta.db_table

            # Select the username -- it will raise an error.
            def try_lock():
                user2 = (User2
                         .select()
                         .where(User2.username == 'u1')
                         .for_update(nowait=True)
                         .execute())
            self.assertRaises(OperationalError, try_lock)
            test_db.rollback()


elif TEST_VERBOSITY > 0:
    print_('Skipping "for update + nowait" tests')

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
    print_('Skipping "sequence" tests')

if database_class is PostgresqlDatabase:
    class TestUnicodeConversion(ModelTestCase):
        requires = [User]

        def setUp(self):
            super(TestUnicodeConversion, self).setUp()

            # Create a user object with UTF-8 encoded username.
            ustr = ulit('Ísland')
            self.user = User.create(username=ustr)

        def tearDown(self):
            super(TestUnicodeConversion, self).tearDown()
            test_db.register_unicode = True
            test_db.close()

        def reset_encoding(self, encoding):
            test_db.close()
            conn = test_db.get_conn()
            conn.set_client_encoding(encoding)

        def test_unicode_conversion(self):
            # Per psycopg2's documentation, in Python2, strings are returned as
            # 8-bit str objects encoded in the client encoding. In python3,
            # the strings are automatically decoded in the connection encoding.

            # Turn off unicode conversion on a per-connection basis.
            test_db.register_unicode = False
            self.reset_encoding('LATIN1')

            u = User.get(User.id == self.user.id)
            if sys.version_info[0] < 3:
                self.assertFalse(u.username == self.user.username)
            else:
                self.assertTrue(u.username == self.user.username)

            test_db.register_unicode = True
            self.reset_encoding('LATIN1')

            u = User.get(User.id == self.user.id)
            self.assertEqual(u.username, self.user.username)

if test_db.savepoints:
    class TestSavepoints(ModelTestCase):
        requires = [User]

        def _outer(self, fail_outer=False, fail_inner=False):
            with test_db.savepoint():
                User.create(username='outer')
                try:
                    self._inner(fail_inner)
                except ValueError:
                    pass
                if fail_outer:
                    raise ValueError

        def _inner(self, fail_inner):
            with test_db.savepoint():
                User.create(username='inner')
                if fail_inner:
                    raise ValueError('failing')

        def assertNames(self, expected):
            query = User.select().order_by(User.username)
            self.assertEqual([u.username for u in query], expected)

        def test_success(self):
            with test_db.transaction():
                self._outer()
                self.assertEqual(User.select().count(), 2)
            self.assertNames(['inner', 'outer'])

        def test_inner_failure(self):
            with test_db.transaction():
                self._outer(fail_inner=True)
                self.assertEqual(User.select().count(), 1)
            self.assertNames(['outer'])

        def test_outer_failure(self):
            # Because the outer savepoint is rolled back, we'll lose the
            # inner savepoint as well.
            with test_db.transaction():
                self.assertRaises(ValueError, self._outer, fail_outer=True)
                self.assertEqual(User.select().count(), 0)

        def test_failure(self):
            with test_db.transaction():
                self.assertRaises(
                    ValueError, self._outer, fail_outer=True, fail_inner=True)
                self.assertEqual(User.select().count(), 0)


elif TEST_VERBOSITY > 0:
    print_('Skipping "savepoint" tests')

if test_db.foreign_keys:
    class ForeignKeyConstraintTestCase(ModelTestCase):
        requires = [User, Blog]

        def test_constraint_exists(self):
            # IntegrityError is raised when we specify a non-existent user_id.
            max_id = User.select(fn.Max(User.id)).scalar() or 0

            def will_fail():
                with test_db.transaction() as txn:
                    Blog.create(user=max_id + 1, title='testing')

            self.assertRaises(IntegrityError, will_fail)

        def test_constraint_creation(self):
            class FKC_a(TestModel):
                name = CharField()

            fkc_proxy = Proxy()

            class FKC_b(TestModel):
                fkc_a = ForeignKeyField(fkc_proxy)

            fkc_proxy.initialize(FKC_a)

            with test_db.transaction() as txn:
                FKC_b.drop_table(True)
                FKC_a.drop_table(True)
                FKC_a.create_table()
                FKC_b.create_table()

                # Foreign key constraint is not enforced.
                fb = FKC_b.create(fkc_a=-1000)
                fb.delete_instance()

                # Add constraint.
                test_db.create_foreign_key(FKC_b, FKC_b.fkc_a)

                def _trigger_exc():
                    with test_db.savepoint() as s1:
                        fb = FKC_b.create(fkc_a=-1000)

                self.assertRaises(IntegrityError, _trigger_exc)

                fa = FKC_a.create(name='fa')
                fb = FKC_b.create(fkc_a=fa)
                txn.rollback()


elif TEST_VERBOSITY > 0:
    print_('Skipping "foreign key" tests')

if test_db.drop_cascade:
    class DropCascadeTestCase(ModelTestCase):
        requires = [User, Blog]

        def test_drop_cascade(self):
            u1 = User.create(username='u1')
            b1 = Blog.create(user=u1, title='b1')

            User.drop_table(cascade=True)
            self.assertFalse(User.table_exists())

            # The constraint is dropped, we can create a blog for a non-
            # existant user.
            Blog.create(user=-1, title='b2')


elif TEST_VERBOSITY > 0:
    print_('Skipping "drop/cascade" tests')


if test_db.window_functions:
    class WindowFunctionTestCase(ModelTestCase):
        """Use int_field & float_field to test window queries."""
        requires = [NullModel]
        data = (
            # int / float -- we'll use int for grouping.
            (1, 10),
            (1, 20),
            (2, 1),
            (2, 3),
            (3, 100),
        )

        def setUp(self):
            super(WindowFunctionTestCase, self).setUp()
            for int_v, float_v in self.data:
                NullModel.create(int_field=int_v, float_field=float_v)

        def test_partition_unordered(self):
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.Avg(NullModel.float_field).over(
                             partition_by=[NullModel.int_field]))
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 15.0),
                (1, 20.0, 15.0),
                (2, 1.0, 2.0),
                (2, 3.0, 2.0),
                (3, 100.0, 100.0),
            ])

        def test_named_window(self):
            window = Window(partition_by=[NullModel.int_field])
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.Avg(NullModel.float_field).over(window))
                     .window(window)
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 15.0),
                (1, 20.0, 15.0),
                (2, 1.0, 2.0),
                (2, 3.0, 2.0),
                (3, 100.0, 100.0),
            ])

            window = Window(
                partition_by=[NullModel.int_field],
                order_by=[NullModel.float_field.desc()])
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.rank().over(window=window))
                     .window(window)
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 2),
                (1, 20.0, 1),
                (2, 1.0, 2),
                (2, 3.0, 1),
                (3, 100.0, 1),
            ])

        def test_multi_window(self):
            w1 = Window(partition_by=[NullModel.int_field]).alias('w1')
            w2 = Window(order_by=[NullModel.int_field]).alias('w2')
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.Avg(NullModel.float_field).over(window=w1),
                         fn.Rank().over(window=w2))
                     .window(w1, w2)
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 15.0, 1),
                (1, 20.0, 15.0, 1),
                (2, 1.0, 2.0, 3),
                (2, 3.0, 2.0, 3),
                (3, 100.0, 100.0, 5),
            ])

        def test_ordered_unpartitioned(self):
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.rank().over(
                             order_by=[NullModel.float_field]))
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 3),
                (1, 20.0, 4),
                (2, 1.0, 1),
                (2, 3.0, 2),
                (3, 100.0, 5),
            ])

        def test_ordered_partitioned(self):
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.rank().over(
                             partition_by=[NullModel.int_field],
                             order_by=[NullModel.float_field.desc()]))
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, 2),
                (1, 20.0, 1),
                (2, 1.0, 2),
                (2, 3.0, 1),
                (3, 100.0, 1),
            ])

        def test_empty_over(self):
            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.float_field,
                         fn.lag(NullModel.int_field, 1).over())
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (1, 10.0, None),
                (1, 20.0, 1),
                (2, 1.0, 1),
                (2, 3.0, 2),
                (3, 100.0, 2),
            ])

        def test_docs_example(self):
            NullModel.delete().execute()  # Clear out the table.

            curr_dt = datetime.datetime(2014, 1, 1)
            one_day = datetime.timedelta(days=1)
            for i in range(3):
                for j in range(i + 1):
                    NullModel.create(int_field=i, datetime_field=curr_dt)
                curr_dt += one_day

            query = (NullModel
                     .select(
                         NullModel.int_field,
                         NullModel.datetime_field,
                         fn.Count(NullModel.id).over(
                             partition_by=[fn.date_trunc(
                                 'day', NullModel.datetime_field)]))
                     .order_by(NullModel.id))

            self.assertEqual(list(query.tuples()), [
                (0, datetime.datetime(2014, 1, 1), 1),
                (1, datetime.datetime(2014, 1, 2), 2),
                (1, datetime.datetime(2014, 1, 2), 2),
                (2, datetime.datetime(2014, 1, 3), 3),
                (2, datetime.datetime(2014, 1, 3), 3),
                (2, datetime.datetime(2014, 1, 3), 3),
            ])


elif TEST_VERBOSITY > 0:
    print_('Skipping "window function" tests')

if test_db.distinct_on:
    class DistinctOnTestCase(ModelTestCase):
        requires = [User, Blog]

        def test_distinct_on(self):
            for i in range(1, 4):
                u = User.create(username='u%s' % i)
                for j in range(i):
                    Blog.create(user=u, title='b-%s-%s' % (i, j))

            query = (Blog
                     .select(User.username, Blog.title)
                     .join(User)
                     .order_by(User.username, Blog.title)
                     .distinct([User.username])
                     .tuples())
            self.assertEqual(list(query), [
                ('u1', 'b-1-0'),
                ('u2', 'b-2-0'),
                ('u3', 'b-3-0')])

            query = (Blog
                     .select(
                         fn.Distinct(User.username),
                         User.username,
                         Blog.title)
                     .join(User)
                     .order_by(Blog.title)
                     .tuples())
            self.assertEqual(list(query), [
                ('u1', 'u1', 'b-1-0'),
                ('u2', 'u2', 'b-2-0'),
                ('u2', 'u2', 'b-2-1'),
                ('u3', 'u3', 'b-3-0'),
                ('u3', 'u3', 'b-3-1'),
                ('u3', 'u3', 'b-3-2'),
            ])

elif TEST_VERBOSITY > 0:
    print_('Skipping "distinct on" tests')


if __name__ == '__main__':
    unittest.main(argv=sys.argv)
