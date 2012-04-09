# encoding=utf-8

import datetime
import decimal
import logging
import os
import Queue
import threading
import unittest

import peewee
from peewee import (RawQuery, SelectQuery, InsertQuery, UpdateQuery, DeleteQuery,
        Node, Q, database, parseq, SqliteAdapter, PostgresqlAdapter, filter_query,
        annotate_query, F, R)


class QueryLogHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        self.queries = []
        logging.Handler.__init__(self, *args, **kwargs)

    def emit(self, record):
        self.queries.append(record)


BACKEND = os.environ.get('PEEWEE_TEST_BACKEND', 'sqlite')

if BACKEND == 'postgresql':
    database_class = peewee.PostgresqlDatabase
    database_name = 'peewee_test'
elif BACKEND == 'mysql':
    database_class = peewee.MySQLDatabase
    database_name = 'peewee_test'
else:
    database_class = peewee.SqliteDatabase
    database_name = 'tmp.db'

test_db = database_class(database_name)
interpolation = test_db.adapter.interpolation
quote_char = test_db.adapter.quote_char

class TestModel(peewee.Model):
    class Meta:
        database = test_db


# test models
class Blog(TestModel):
    title = peewee.CharField()

    def __unicode__(self):
        return self.title


class Entry(TestModel):
    pk = peewee.PrimaryKeyField()
    title = peewee.CharField(max_length=50, verbose_name='Wacky title')
    content = peewee.TextField()
    pub_date = peewee.DateTimeField(null=True)
    blog = peewee.ForeignKeyField(Blog, cascade=True)

    def __unicode__(self):
        return '%s: %s' % (self.blog.title, self.title)


class EntryTag(TestModel):
    tag = peewee.CharField(max_length=50)
    entry = peewee.ForeignKeyField(Entry)

    def __unicode__(self):
        return self.tag


class EntryTwo(Entry):
    title = peewee.TextField()
    extra_field = peewee.CharField()


class User(TestModel):
    username = peewee.CharField(max_length=50)
    blog = peewee.ForeignKeyField(Blog, null=True)
    active = peewee.BooleanField(db_index=True)

    class Meta:
        db_table = 'users'

    def __unicode__(self):
        return self.username


class Relationship(TestModel):
    from_user = peewee.ForeignKeyField(User, related_name='relationships')
    to_user = peewee.ForeignKeyField(User, related_name='related_to')


class NullModel(TestModel):
    char_field = peewee.CharField(null=True)
    text_field = peewee.TextField(null=True)
    datetime_field = peewee.DateTimeField(null=True)
    int_field = peewee.IntegerField(null=True)
    float_field = peewee.FloatField(null=True)
    decimal_field1 = peewee.DecimalField(null=True)
    decimal_field2 = peewee.DecimalField(decimal_places=2, null=True)
    double_field = peewee.DoubleField(null=True)
    bigint_field = peewee.BigIntegerField(null=True)
    date_field = peewee.DateField(null=True)
    time_field = peewee.TimeField(null=True)

class NumberModel(TestModel):
    num1 = peewee.IntegerField()
    num2 = peewee.IntegerField()

class RelNumberModel(TestModel):
    rel_num = peewee.IntegerField()
    num = peewee.ForeignKeyField(NumberModel)

class Team(TestModel):
    name = peewee.CharField()

class Member(TestModel):
    username = peewee.CharField()

class Membership(TestModel):
    team = peewee.ForeignKeyField(Team)
    member = peewee.ForeignKeyField(Member)

class DefaultVals(TestModel):
    published = peewee.BooleanField(default=True)
    pub_date = peewee.DateTimeField(default=datetime.datetime.now, null=True)

class UniqueModel(TestModel):
    name = peewee.CharField(unique=True)

class OrderedModel(TestModel):
    title = peewee.CharField()
    created = peewee.DateTimeField(default=datetime.datetime.now)

    class Meta:
        ordering = (('created', 'desc'),)

class Category(TestModel):
    parent = peewee.ForeignKeyField('self', related_name='children', null=True)
    name = peewee.CharField()

class SeqModelBase(TestModel):
    class Meta:
        pk_sequence = 'just_testing_seq'

class SeqModelA(SeqModelBase):
    num = peewee.IntegerField()

class SeqModelB(SeqModelBase):
    other_num = peewee.IntegerField()

class LegacyBlog(TestModel):
    name = peewee.CharField(db_column='old_name')

    class Meta:
        ordering = ('id',)

class LegacyEntry(TestModel):
    name = peewee.CharField(db_column='old_name')
    blog = peewee.ForeignKeyField(LegacyBlog, db_column='old_blog')

    class Meta:
        ordering = ('id',)

class ExplicitEntry(TestModel):
    name = peewee.CharField()
    blog = peewee.ForeignKeyField(LegacyBlog, db_column='blog')

class NonIntPK(TestModel):
    id = peewee.PrimaryKeyField(column_class=peewee.VarCharColumn)
    name = peewee.CharField(max_length=10)

class RelNonIntPK(TestModel):
    non_int_pk = peewee.ForeignKeyField(NonIntPK)
    name = peewee.CharField()


class BasePeeweeTestCase(unittest.TestCase):
    def setUp(self):
        self.qh = QueryLogHandler()
        peewee.logger.setLevel(logging.DEBUG)
        peewee.logger.addHandler(self.qh)

    def tearDown(self):
        peewee.logger.removeHandler(self.qh)

    def normalize(self, s):
        if interpolation != '?':
            s = s.replace('?', interpolation)
        if quote_char != "`":
            s = s.replace("`", quote_char)
        return s

    def assertQueriesEqual(self, queries):
        queries = [(self.normalize(q), p) for q,p in queries]
        self.assertEqual(queries, self.queries())

    def assertSQLEqual(self, lhs, rhs):
        self.assertEqual(
            self.normalize(lhs[0]),
            self.normalize(rhs[0])
        )
        self.assertEqual(lhs[1], rhs[1])

    def assertSQL(self, query, expected_clauses):
        computed_joins, clauses, alias_map = query.compile_where()
        clauses = [(self.normalize(x), y) for (x, y) in clauses]
        expected_clauses = [(self.normalize(x), y) for (x, y) in expected_clauses]
        self.assertEqual(sorted(clauses), sorted(expected_clauses))

    def assertNodeEqual(self, lhs, rhs):
        for i, lchild in enumerate(lhs.children):
            rchild = rhs.children[i]
            self.assertEqual(type(lchild), type(rchild))
            if isinstance(lchild, Q):
                self.assertEqual(lchild.query, rchild.query)
            elif isinstance(lchild, Node):
                self.assertNodeEqual(lchild, rchild)
            else:
                raise TypeError("Invalid type passed to assertNodeEqual")

class BaseModelTestCase(BasePeeweeTestCase):
    def setUp(self):
        Membership.drop_table(True)
        Member.drop_table(True)
        Team.drop_table(True)
        Relationship.drop_table(True)
        User.drop_table(True)
        EntryTag.drop_table(True)
        Entry.drop_table(True)
        Blog.drop_table(True)

        Blog.create_table()
        Entry.create_table()
        EntryTag.create_table()
        User.create_table()
        Relationship.create_table()
        Team.create_table()
        Member.create_table()
        Membership.create_table()
        super(BaseModelTestCase, self).setUp()

    def queries(self):
        return [x.msg for x in self.qh.queries]

    def create_blog(self, **kwargs):
        blog = Blog(**kwargs)
        blog.save()
        return blog

    def create_entry(self, **kwargs):
        entry = Entry(**kwargs)
        entry.save()
        return entry

    def create_entry_tag(self, **kwargs):
        entry_tag = EntryTag(**kwargs)
        entry_tag.save()
        return entry_tag


class QueryTests(BasePeeweeTestCase):
    def test_raw(self):
        rq = RawQuery(Blog, 'SELECT id, title FROM blog')
        self.assertSQLEqual(rq.sql(), ('SELECT id, title FROM blog', []))

        rq = RawQuery(Blog, 'SELECT id, title FROM blog WHERE title = ?', 'a')
        self.assertSQLEqual(rq.sql(), ('SELECT id, title FROM blog WHERE title = ?', ['a']))

        rq = RawQuery(Blog, 'SELECT id, title FROM blog WHERE title = ? OR title = ?', 'a', 'b')
        self.assertSQLEqual(rq.sql(), ('SELECT id, title FROM blog WHERE title = ? OR title = ?', ['a', 'b']))

    def test_select(self):
        sq = SelectQuery(Blog, '*')
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog`', []))

        sq = SelectQuery(Blog, '*').where(title='a')
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE `title` = ?', ['a']))

        sq = SelectQuery(Blog, '*').where(title='a', id=1)
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (`id` = ? AND `title` = ?)', [1, 'a']))

        # check that chaining works as expected
        sq = SelectQuery(Blog, '*').where(title='a').where(id=1)
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE `title` = ? AND `id` = ?', ['a', 1]))

        # check that IN query special-case works
        sq = SelectQuery(Blog, '*').where(title__in=['a', 'b'])
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE `title` IN (?,?)', ['a', 'b']))

    def test_select_with_q(self):
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (`title` = ? OR `id` = ?)', ['a', 1]))

        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1) | Q(id=3))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (`title` = ? OR `id` = ? OR `id` = ?)', ['a', 1, 3]))

        # test simple chaining
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where(Q(id=3))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (`title` = ? OR `id` = ?) AND `id` = ?', ['a', 1, 3]))

        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where(id=3)
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (`title` = ? OR `id` = ?) AND `id` = ?', ['a', 1, 3]))

        # test chaining with Q objects
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where((Q(title='c') | Q(id=3)))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (`title` = ? OR `id` = ?) AND (`title` = ? OR `id` = ?)', ['a', 1, 'c', 3]))

        # test mixing it all up
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where((Q(title='c') | Q(id=3)), title='b')
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (`title` = ? OR `id` = ?) AND (`title` = ? OR `id` = ?) AND `title` = ?', ['a', 1, 'c', 3, 'b']))

    def test_select_with_negation(self):
        sq = SelectQuery(Blog, '*').where(~Q(title='a'))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE NOT `title` = ?', ['a']))

        sq = SelectQuery(Blog, '*').where(~Q(title='a') | Q(title='b'))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (NOT `title` = ? OR `title` = ?)', ['a', 'b']))

        sq = SelectQuery(Blog, '*').where(~Q(title='a') | ~Q(title='b'))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (NOT `title` = ? OR NOT `title` = ?)', ['a', 'b']))

        sq = SelectQuery(Blog, '*').where(~(Q(title='a') | Q(title='b')))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (NOT (`title` = ? OR `title` = ?))', ['a', 'b']))

        # chaining?
        sq = SelectQuery(Blog, '*').where(~(Q(title='a') | Q(id=1))).where(Q(id=3))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (NOT (`title` = ? OR `id` = ?)) AND `id` = ?', ['a', 1, 3]))

        # mix n'match?
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where(~(Q(title='c') | Q(id=3)), title='b')
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (`title` = ? OR `id` = ?) AND (NOT (`title` = ? OR `id` = ?)) AND `title` = ?', ['a', 1, 'c', 3, 'b']))

    def test_select_with_models(self):
        sq = SelectQuery(Blog, {Blog: ['*']})
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog`', []))

        sq = SelectQuery(Blog, {Blog: ['title', 'id']})
        self.assertSQLEqual(sq.sql(), ('SELECT `title`, `id` FROM `blog`', []))

        sq = SelectQuery(Blog, {Blog: ['title', 'id']}).join(Entry)
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`title`, t1.`id` FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id`', []))

        sq = SelectQuery(Blog, {Blog: ['title', 'id'], Entry: [peewee.Count('pk')]}).join(Entry)
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`title`, t1.`id`, COUNT(t2.`pk`) AS count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id`', []))

        sq = SelectQuery(Blog, {Blog: ['title', 'id'], Entry: [peewee.Max('pk')]}).join(Entry)
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`title`, t1.`id`, MAX(t2.`pk`) AS max FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id`', []))

        sq = SelectQuery(Blog, {Blog: ['title', 'id']}).join(Entry, alias='e').where(title='foo')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`title`, t1.`id` FROM `blog` AS t1 INNER JOIN `entry` AS e ON t1.`id` = e.`blog_id` WHERE e.`title` = ?', ['foo']))

        sq = SelectQuery(Entry, {Entry: ['pk', 'title'], Blog: ['title']}).join(Blog, alias='b').where(title='foo')
        self.assertSQLEqual(sq.sql(), ('SELECT b.`title`, t1.`pk`, t1.`title` FROM `entry` AS t1 INNER JOIN `blog` AS b ON t1.`blog_id` = b.`id` WHERE b.`title` = ?', ['foo']))

    def test_selecting_across_joins(self):
        sq = SelectQuery(Entry, '*').where(title='a1').join(Blog).where(title='a')

        self.assertEqual(sq._joins, {Entry: [(Blog, None, None)]})
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` WHERE t1.`title` = ? AND t2.`title` = ?', ['a1', 'a']))

        sq = SelectQuery(Blog, '*').join(Entry).where(title='a1')
        self.assertEqual(sq._joins, {Blog: [(Entry, None, None)]})
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`id`, t1.`title` FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` WHERE t2.`title` = ?', ['a1']))

        sq = SelectQuery(EntryTag, '*').join(Entry).join(Blog).where(title='a')
        self.assertEqual(sq._joins, {EntryTag: [(Entry, None, None)], Entry: [(Blog, None, None)]})
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`id`, t1.`tag`, t1.`entry_id` FROM `entrytag` AS t1 INNER JOIN `entry` AS t2 ON t1.`entry_id` = t2.`pk`\nINNER JOIN `blog` AS t3 ON t2.`blog_id` = t3.`id` WHERE t3.`title` = ?', ['a']))

        sq = SelectQuery(Blog, '*').join(Entry).join(EntryTag).where(tag='t2')
        self.assertEqual(sq._joins, {Blog: [(Entry, None, None)], Entry: [(EntryTag, None, None)]})
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`id`, t1.`title` FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id`\nINNER JOIN `entrytag` AS t3 ON t2.`pk` = t3.`entry_id` WHERE t3.`tag` = ?', ['t2']))

    def test_selecting_across_joins_with_q(self):
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).join(Blog).where(title='e')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` WHERE (t1.`title` = ? OR t1.`pk` = ?) AND t2.`title` = ?', ['a', 1, 'e']))

        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1) | Q(title='b')).join(Blog).where(title='e')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` WHERE (t1.`title` = ? OR t1.`pk` = ? OR t1.`title` = ?) AND t2.`title` = ?', ['a', 1, 'b', 'e']))

        # test simple chaining
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).where(Q(title='b')).join(Blog).where(title='e')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` WHERE (t1.`title` = ? OR t1.`pk` = ?) AND t1.`title` = ? AND t2.`title` = ?', ['a', 1, 'b', 'e']))

        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).where(title='b').join(Blog).where(title='e')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` WHERE (t1.`title` = ? OR t1.`pk` = ?) AND t1.`title` = ? AND t2.`title` = ?', ['a', 1, 'b', 'e']))

        # test q on both models
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).join(Blog).where(Q(title='e') | Q(id=2))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` WHERE (t1.`title` = ? OR t1.`pk` = ?) AND (t2.`title` = ? OR t2.`id` = ?)', ['a', 1, 'e', 2]))

        # test q on both with nesting
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).join(Blog).where((Q(title='e') | Q(id=2)) & (Q(title='f') | Q(id=3)))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` WHERE (t1.`title` = ? OR t1.`pk` = ?) AND ((t2.`title` = ? OR t2.`id` = ?) AND (t2.`title` = ? OR t2.`id` = ?))', ['a', 1, 'e', 2, 'f', 3]))

    def test_selecting_with_switching(self):
        sq = SelectQuery(Blog, '*').join(Entry).switch(Blog).where(title='a')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`id`, t1.`title` FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` WHERE t1.`title` = ?', ['a']))

    def test_selecting_with_aggregation(self):
        sq = SelectQuery(Blog, 't1.*, COUNT(t2.pk) AS count').group_by('id').join(Entry)
        self.assertEqual(sq._where, [])
        self.assertEqual(sq._joins, {Blog: [(Entry, None, None)]})
        self.assertSQLEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id`', []))

        sq = sq.having('count > 2')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id` HAVING count > 2', []))

        sq = SelectQuery(Blog, {
            Blog: ['*'],
            Entry: [peewee.Count('pk')]
        }).group_by('id').join(Entry)
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`id`, t1.`title`, COUNT(t2.`pk`) AS count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id`', []))

        sq = sq.having('count > 2')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`id`, t1.`title`, COUNT(t2.`pk`) AS count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id` HAVING count > 2', []))

        sq = sq.order_by(('count', 'desc'))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`id`, t1.`title`, COUNT(t2.`pk`) AS count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id` HAVING count > 2 ORDER BY count desc', []))

    def test_select_with_group_by(self):
        sq = Blog.select().group_by('title')
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` GROUP BY `title`', []))

        sq = Entry.select().join(Blog).group_by(Blog)
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` GROUP BY t2.`id`, t2.`title`', []))

    def test_selecting_with_ordering(self):
        sq = SelectQuery(Blog).order_by('title')
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` ORDER BY `title` ASC', []))

        sq = SelectQuery(Blog).order_by(peewee.desc('title'))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` ORDER BY `title` DESC', []))

        sq = SelectQuery(Blog).order_by((Blog, 'title'))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` ORDER BY `title` ASC', []))

        sq = SelectQuery(Blog).order_by((Blog, 'title', 'desc'))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` ORDER BY `title` desc', []))

    def test_selecting_with_ordering_joins(self):
        sq = SelectQuery(Entry).order_by('title').join(Blog).where(title='a')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` WHERE t2.`title` = ? ORDER BY t1.`title` ASC', ['a']))

        sq = SelectQuery(Entry).order_by(peewee.desc('title')).join(Blog).where(title='a')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` WHERE t2.`title` = ? ORDER BY t1.`title` DESC', ['a']))

        sq = SelectQuery(Entry).join(Blog).where(title='a').order_by((Entry, 'title'))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` WHERE t2.`title` = ? ORDER BY t1.`title` ASC', ['a']))

        sq = SelectQuery(Entry).join(Blog).where(title='a').order_by((Entry, 'title', 'desc'))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` WHERE t2.`title` = ? ORDER BY t1.`title` desc', ['a']))


        sq = SelectQuery(Entry).join(Blog).order_by('title')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` ORDER BY t2.`title` ASC', []))

        sq = SelectQuery(Entry).join(Blog).order_by(peewee.desc('title'))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` ORDER BY t2.`title` DESC', []))

        sq = SelectQuery(Entry).order_by((Blog, 'title')).join(Blog)
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` ORDER BY t2.`title` ASC', []))

        sq = SelectQuery(Entry).order_by((Blog, 'title', 'desc')).join(Blog)
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` ORDER BY t2.`title` desc', []))


        sq = SelectQuery(Entry).join(Blog).order_by(
            (Blog, 'title'),
            (Entry, 'pub_date', 'desc'),
        )
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` ORDER BY t2.`title` ASC, t1.`pub_date` desc', []))

        sq = SelectQuery(Entry).join(Blog).order_by(
            (Entry, 'pub_date', 'desc'),
            (Blog, 'title'),
            'id',
        )
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id` ORDER BY t1.`pub_date` desc, t2.`title` ASC, t2.`id` ASC', []))

        sq = SelectQuery(Entry).order_by((Blog, 'title')).join(Blog).order_by()
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id`', []))

    def test_ordering_on_aggregates(self):
        sq = SelectQuery(
            Blog, 't1.*, COUNT(t2.pk) as count'
        ).join(Entry).order_by(peewee.desc('count'))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) as count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` ORDER BY count DESC', []))

    def test_default_ordering(self):
        sq = OrderedModel.select()
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title`, `created` FROM `orderedmodel` ORDER BY `created` desc', []))

        sq = OrderedModel.select().order_by()
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title`, `created` FROM `orderedmodel`', []))

        class OtherOrderedModel(OrderedModel):
            pass

        sq = OtherOrderedModel.select()
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title`, `created` FROM `otherorderedmodel` ORDER BY `created` desc', []))

        sq = OtherOrderedModel.select().order_by()
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title`, `created` FROM `otherorderedmodel`', []))

        class MoreModel(OrderedModel):
            class Meta:
                ordering = (('created', 'desc'), 'title')

        sq = MoreModel.select()
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title`, `created` FROM `moremodel` ORDER BY `created` desc, `title` ASC', []))

        sq = MoreModel.select().order_by()
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title`, `created` FROM `moremodel`', []))

    def test_insert(self):
        iq = InsertQuery(Blog, title='a')
        self.assertSQLEqual(iq.sql(), ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']))

    def test_update_with_q(self):
        uq = UpdateQuery(Blog, title='A').where(Q(id=1))
        self.assertSQLEqual(uq.sql(), ('UPDATE `blog` SET `title`=? WHERE `id` = ?', ['A', 1]))

        uq = UpdateQuery(Blog, title='A').where(Q(id=1) | Q(id=3))
        self.assertSQLEqual(uq.sql(), ('UPDATE `blog` SET `title`=? WHERE (`id` = ? OR `id` = ?)', ['A', 1, 3]))

    def test_update_with_f(self):
        uq = UpdateQuery(Entry, blog_id=F('blog_id') + 1).where(pk=1)
        self.assertSQLEqual(uq.sql(), ('UPDATE `entry` SET `blog_id`=(`blog_id` + 1) WHERE `pk` = ?', [1]))

        uq = UpdateQuery(Entry, blog_id=F('blog_id') - 10, title='updated').where(pk=2)
        self.assertSQLEqual(uq.sql(), ('UPDATE `entry` SET `blog_id`=(`blog_id` - 10), `title`=? WHERE `pk` = ?', ['updated', 2]))

    def test_delete(self):
        dq = DeleteQuery(Blog).where(title='b')
        self.assertSQLEqual(dq.sql(), ('DELETE FROM `blog` WHERE `title` = ?', ['b']))

        dq = DeleteQuery(Blog).where(Q(title='b') | Q(title='a'))
        self.assertSQLEqual(dq.sql(), ('DELETE FROM `blog` WHERE (`title` = ? OR `title` = ?)', ['b', 'a']))


class ModelTestCase(BaseModelTestCase):
    def test_insert(self):
        iq = InsertQuery(Blog, title='a')
        self.assertSQLEqual(iq.sql(), ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']))
        self.assertEqual(iq.execute(), 1)

        iq = InsertQuery(Blog, title='b')
        self.assertSQLEqual(iq.sql(), ('INSERT INTO `blog` (`title`) VALUES (?)', ['b']))
        self.assertEqual(iq.execute(), 2)

    def test_update(self):
        iq = InsertQuery(Blog, title='a').execute()

        uq = UpdateQuery(Blog, title='A').where(id=1)
        self.assertSQLEqual(uq.sql(), ('UPDATE `blog` SET `title`=? WHERE `id` = ?', ['A', 1]))
        self.assertEqual(uq.execute(), 1)

        iq2 = InsertQuery(Blog, title='b').execute()

        uq = UpdateQuery(Blog, title='B').where(id=2)
        self.assertSQLEqual(uq.sql(), ('UPDATE `blog` SET `title`=? WHERE `id` = ?', ['B', 2]))
        self.assertEqual(uq.execute(), 1)

        sq = SelectQuery(Blog).order_by('id')
        self.assertEqual([x.title for x in sq], ['A', 'B'])

    def test_delete(self):
        InsertQuery(Blog, title='a').execute()
        InsertQuery(Blog, title='b').execute()
        InsertQuery(Blog, title='c').execute()

        dq = DeleteQuery(Blog).where(title='b')
        self.assertSQLEqual(dq.sql(), ('DELETE FROM `blog` WHERE `title` = ?', ['b']))
        self.assertEqual(dq.execute(), 1)

        sq = SelectQuery(Blog).order_by('id')
        self.assertEqual([x.title for x in sq], ['a', 'c'])

        dq = DeleteQuery(Blog)
        self.assertSQLEqual(dq.sql(), ('DELETE FROM `blog`', []))
        self.assertEqual(dq.execute(), 2)

        sq = SelectQuery(Blog).order_by('id')
        self.assertEqual([x.title for x in sq], [])

    def test_count(self):
        for i in xrange(10):
            self.create_blog(title='a%d' % i)

        count = SelectQuery(Blog).count()
        self.assertEqual(count, 10)

        count = Blog.select().count()
        self.assertEqual(count, 10)

        for blog in SelectQuery(Blog):
            for i in xrange(20):
                self.create_entry(title='entry%d' % i, blog=blog)

        count = SelectQuery(Entry).count()
        self.assertEqual(count, 200)

        count = SelectQuery(Entry).join(Blog).where(title="a0").count()
        self.assertEqual(count, 20)

        count = SelectQuery(Entry).where(
            title__icontains="0"
        ).join(Blog).where(
            title="a5"
        ).count()
        self.assertEqual(count, 2)

    def test_count_with_joins_issue27(self):
        b1 = Blog.create(title='b1')
        b2 = Blog.create(title='b2')

        for b in [b1, b2]:
            for i in range(5):
                self.create_entry(title='e-%s-%s' % (b, i), blog=b)

        bc = Blog.select().where(title='b1').join(Entry).count()
        self.assertEqual(bc, 5)

        bc_dist = Blog.select().where(title='b1').join(Entry).distinct().count()
        self.assertEqual(bc_dist, 1)

    def test_pagination(self):
        base_sq = SelectQuery(Blog)

        sq = base_sq.paginate(1, 20)
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` LIMIT 20', []))

        sq = base_sq.paginate(3, 30)
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `title` FROM `blog` LIMIT 30 OFFSET 60', []))

    def test_inner_joins(self):
        sql = SelectQuery(Blog).join(Entry).sql()
        self.assertSQLEqual(sql, ('SELECT t1.`id`, t1.`title` FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id`', []))

        sql = SelectQuery(Entry).join(Blog).sql()
        self.assertSQLEqual(sql, ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id`', []))

    def test_outer_joins(self):
        sql = SelectQuery(User).join(Blog).sql()
        self.assertSQLEqual(sql, ('SELECT t1.`id`, t1.`username`, t1.`blog_id`, t1.`active` FROM `users` AS t1 LEFT OUTER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id`', []))

        sql = SelectQuery(Blog).join(User).sql()
        self.assertSQLEqual(sql, ('SELECT t1.`id`, t1.`title` FROM `blog` AS t1 LEFT OUTER JOIN `users` AS t2 ON t1.`id` = t2.`blog_id`', []))

    def test_cloning(self):
        base_sq = SelectQuery(Blog)

        q1 = base_sq.where(title='a')
        q2 = base_sq.where(title='b')

        q1_sql = ('SELECT `id`, `title` FROM `blog` WHERE `title` = ?', ['a'])
        q2_sql = ('SELECT `id`, `title` FROM `blog` WHERE `title` = ?', ['b'])

        # where causes cloning
        self.assertSQLEqual(base_sq.sql(), ('SELECT `id`, `title` FROM `blog`', []))
        self.assertSQLEqual(q1.sql(), q1_sql)
        self.assertSQLEqual(q2.sql(), q2_sql)

        q3 = q1.join(Entry)
        q3_sql = ('SELECT t1.`id`, t1.`title` FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` WHERE t1.`title` = ?', ['a'])

        # join causes cloning
        self.assertSQLEqual(q3.sql(), q3_sql)
        self.assertSQLEqual(q1.sql(), q1_sql)

        q4 = q1.order_by('title')
        q5 = q3.order_by('title')

        q4_sql = ('SELECT `id`, `title` FROM `blog` WHERE `title` = ? ORDER BY `title` ASC', ['a'])
        q5_sql = ('SELECT t1.`id`, t1.`title` FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` WHERE t1.`title` = ? ORDER BY t2.`title` ASC', ['a'])

        # order_by causes cloning
        self.assertSQLEqual(q3.sql(), q3_sql)
        self.assertSQLEqual(q1.sql(), q1_sql)
        self.assertSQLEqual(q4.sql(), q4_sql)
        self.assertSQLEqual(q5.sql(), q5_sql)

        q6 = q1.paginate(1, 10)
        q7 = q4.paginate(2, 10)

        q6_sql = ('SELECT `id`, `title` FROM `blog` WHERE `title` = ? LIMIT 10', ['a'])
        q7_sql = ('SELECT `id`, `title` FROM `blog` WHERE `title` = ? ORDER BY `title` ASC LIMIT 10 OFFSET 10', ['a'])

        self.assertSQLEqual(q6.sql(), q6_sql)
        self.assertSQLEqual(q7.sql(), q7_sql)

    def test_multi_joins(self):
        sq = Entry.select().join(Blog).where(title='b1').switch(Entry).join(EntryTag).where(tag='t1')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `blog` AS t2 ON t1.`blog_id` = t2.`id`\nINNER JOIN `entrytag` AS t3 ON t1.`pk` = t3.`entry_id` WHERE t2.`title` = ? AND t3.`tag` = ?', ['b1', 't1']))

        sq = Entry.select().join(EntryTag).where(tag='t1').switch(Entry).join(Blog).where(title='b1')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`pk`, t1.`title`, t1.`content`, t1.`pub_date`, t1.`blog_id` FROM `entry` AS t1 INNER JOIN `entrytag` AS t2 ON t1.`pk` = t2.`entry_id`\nINNER JOIN `blog` AS t3 ON t1.`blog_id` = t3.`id` WHERE t2.`tag` = ? AND t3.`title` = ?', ['t1', 'b1']))


class ModelTests(BaseModelTestCase):
    def test_model_save(self):
        a = self.create_blog(title='a')
        self.assertEqual(a.id, 1)

        b = self.create_blog(title='b')
        self.assertEqual(b.id, 2)

        a.save()
        b.save()

        self.assertQueriesEqual([
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']),
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['b']),
            ('UPDATE `blog` SET `title`=? WHERE `id` = ?', ['a', 1]),
            ('UPDATE `blog` SET `title`=? WHERE `id` = ?', ['b', 2]),
        ])

        all_blogs = list(Blog.select().order_by('id'))
        self.assertEqual(all_blogs, [a, b])

    def test_model_get(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')

        b2 = Blog.get(title='b')
        self.assertEqual(b2.id, b.id)

        self.assertQueriesEqual([
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']),
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['b']),
            ('SELECT `id`, `title` FROM `blog` WHERE `title` = ? LIMIT 1', ['b']),
        ])

    def test_select_with_get(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')

        blogs = Blog.filter(title='a')
        blog = blogs.get()
        self.assertEqual(blog, a)

    def test_model_get_with_q(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')

        b2 = Blog.get(Q(title='b') | Q(title='c'))
        self.assertEqual(b2.id, b.id)

        self.assertQueriesEqual([
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']),
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['b']),
            ('SELECT `id`, `title` FROM `blog` WHERE (`title` = ? OR `title` = ?) LIMIT 1', ['b', 'c']),
        ])

    def test_model_raw(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')

        qr = Blog.raw('SELECT id, title FROM blog ORDER BY title ASC')
        self.assertEqual(list(qr), [a, b, c])

        qr = Blog.raw('SELECT id, title FROM blog WHERE title IN (%s, %s) ORDER BY title DESC' % (interpolation, interpolation), 'a', 'c')
        self.assertEqual(list(qr), [c, a])

        # create a couple entires for blog a
        a1 = self.create_entry(title='a1', blog=a)
        a2 = self.create_entry(title='a2', blog=a)

        # create a couple entries for blog c
        c1 = self.create_entry(title='c1', blog=c)
        c2 = self.create_entry(title='c2', blog=c)
        c3 = self.create_entry(title='c3', blog=c)

        qr = Blog.raw("""
            SELECT b.*, COUNT(e.pk) AS count
            FROM blog AS b
            LEFT OUTER JOIN entry AS e
                ON e.blog_id = b.id
            GROUP BY b.id, b.title
            ORDER BY count DESC
        """)
        results = list(qr)

        self.assertEqual(results, [c, a, b])

        self.assertEqual(results[0].count, 3)
        self.assertEqual(results[0].title, 'c')

        self.assertEqual(results[1].count, 2)
        self.assertEqual(results[1].title, 'a')

        self.assertEqual(results[2].count, 0)
        self.assertEqual(results[2].title, 'b')

    def test_model_select(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')

        qr = Blog.select().order_by('title')
        self.assertEqual(list(qr), [a, b, c])

        qr = Blog.select().where(title__in=['a', 'c']).order_by(peewee.desc('title'))
        self.assertEqual(list(qr), [c, a])

        self.assertQueriesEqual([
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']),
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['b']),
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['c']),
            ('SELECT `id`, `title` FROM `blog` ORDER BY `title` ASC', []),
            ('SELECT `id`, `title` FROM `blog` WHERE `title` IN (?,?) ORDER BY `title` DESC', ['a', 'c']),
        ])

    def test_query_cloning(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')

        blog_qr = Blog.select()
        rev_ordered = blog_qr.order_by(peewee.desc('title'))
        ordered = blog_qr.order_by('title')
        rev_filtered = rev_ordered.where(title__in=['a', 'b'])
        filtered = ordered.where(title__in=['b', 'c'])

        self.assertEqual(list(rev_filtered), [b, a])
        self.assertEqual(list(filtered), [b, c])

        more_filtered = filtered.where(title='b')
        self.assertEqual(list(more_filtered), [b])

    def test_model_select_with_q(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')

        qr = Blog.select().where(Q(title='a') | Q(title='b'))
        self.assertEqual(list(qr), [a, b])

        qr = Blog.select().where(Q(title__in=['a']) | Q(title__in=['c', 'd']))
        self.assertEqual(list(qr), [a])

        self.assertQueriesEqual([
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']),
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['b']),
            ('SELECT `id`, `title` FROM `blog` WHERE (`title` = ? OR `title` = ?)', ['a', 'b']),
            ('SELECT `id`, `title` FROM `blog` WHERE (`title` IN (?) OR `title` IN (?,?))', ['a', 'c', 'd']),
        ])

    def test_model_select_with_get(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')

        obj = Blog.select().get(title='a')
        self.assertEqual(obj, a)

        obj = Blog.select().where(title__in=['a', 'b']).get(title='b')
        self.assertEqual(obj, b)

        self.assertRaises(Blog.DoesNotExist, Blog.select().where(title__in=['a', 'b']).get, title='c')

    def test_model_select_with_get_and_joins(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')

        e1 = self.create_entry(blog=a, title='t1')
        e2 = self.create_entry(blog=a, title='t2')
        e3 = self.create_entry(blog=b, title='t3')

        a_entries = Entry.select().join(Blog).where(title='a')
        obj = a_entries.get(title='t1')
        self.assertEqual(obj, e1)
        self.assertEqual(a_entries.query_context, Blog)

        obj = a_entries.get(title='t2')
        self.assertEqual(obj, e2)
        self.assertEqual(a_entries.query_context, Blog)

        self.assertRaises(Entry.DoesNotExist, a_entries.get, title='t3')
        self.assertEqual(a_entries.query_context, Blog)

    def test_exists(self):
        self.assertFalse(Blog.select().exists())

        a = self.create_blog(title='a')
        b = self.create_blog(title='b')

        self.assertTrue(Blog.select().exists())
        self.assertTrue(Blog.select().where(title='a').exists())
        self.assertFalse(Blog.select().where(title='c').exists())

    def test_exists_with_join(self):
        self.assertFalse(Blog.select().join(Entry).exists())

        a = self.create_blog(title='a')
        b = self.create_blog(title='b')

        e1 = self.create_entry(blog=a, title='t1')
        e2 = self.create_entry(blog=a, title='t2')

        a_entries = Entry.select().join(Blog).where(title='a')
        b_entries = Entry.select().join(Blog).where(title='b')

        self.assertTrue(a_entries.exists())
        self.assertFalse(b_entries.exists())

        self.assertTrue(a_entries.switch(Entry).where(title='t1').exists())
        self.assertFalse(a_entries.switch(Entry).where(title='t3').exists())

    def test_query_results_wrapper(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')

        qr = Blog.select().order_by('title').execute()
        self.assertFalse(qr._populated)

        blogs = [b for b in qr]
        self.assertEqual(blogs, [a, b])
        self.assertTrue(qr._populated)

        self.assertQueriesEqual([
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']),
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['b']),
            ('SELECT `id`, `title` FROM `blog` ORDER BY `title` ASC', []),
        ])

        blogs = [b for b in qr]
        self.assertEqual(blogs, [a, b])

        self.assertEqual(len(self.queries()), 3)

        blogs = [b for b in qr]
        self.assertEqual(blogs, [a, b])

        self.assertEqual(len(self.queries()), 3)

    def test_select_caching(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')

        sq = Blog.select().order_by('title')
        blogs = [b for b in sq]
        self.assertEqual(blogs, [a, b])

        self.assertQueriesEqual([
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']),
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['b']),
            ('SELECT `id`, `title` FROM `blog` ORDER BY `title` ASC', []),
        ])

        # iterating again does not cause evaluation
        blogs = [b for b in sq]
        self.assertEqual(blogs, [a, b])

        blogs = [b for b in sq]
        self.assertEqual(blogs, [a, b])

        # still only 3 queries
        self.assertEqual(len(self.queries()), 3)

        # clone the query
        clone = sq.clone()

        # the query will be marked dirty and re-evaluated
        blogs = [b for b in clone]
        self.assertEqual(blogs, [a, b])

        self.assertQueriesEqual([
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']),
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['b']),
            ('SELECT `id`, `title` FROM `blog` ORDER BY `title` ASC', []),
            ('SELECT `id`, `title` FROM `blog` ORDER BY `title` ASC', []),
        ])

        # iterate over the original query - it will use the cached results
        blogs = [b for b in sq]
        self.assertEqual(blogs, [a, b])

        self.assertEqual(len(self.queries()), 4)

    def test_create(self):
        u = User.create(username='a')
        self.assertEqual(u.username, 'a')
        self.assertQueriesEqual([
            ('INSERT INTO `users` (`username`,`blog_id`,`active`) VALUES (?,?,?)', ['a', None, False]),
        ])

        b = Blog.create(title='b blog')
        u2 = User.create(username='b', blog=b)
        self.assertEqual(u2.blog, b)

        self.assertQueriesEqual([
            ('INSERT INTO `users` (`username`,`blog_id`,`active`) VALUES (?,?,?)', ['a', None, False]),
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['b blog']),
            ('INSERT INTO `users` (`username`,`blog_id`,`active`) VALUES (?,?,?)', ['b', b.id, False]),
        ])

    def test_get_raises_does_not_exist(self):
        self.assertRaises(User.DoesNotExist, User.get, username='a')

    def test_get_or_create(self):
        u = User.get_or_create(username='a')
        self.assertEqual(u.username, 'a')
        self.assertQueriesEqual([
            ('SELECT `id`, `username`, `blog_id`, `active` FROM `users` WHERE `username` = ? LIMIT 1', ['a']),
            ('INSERT INTO `users` (`username`,`blog_id`,`active`) VALUES (?,?,?)', ['a', None, False]),
        ])

        other_u = User.get_or_create(username='a')
        self.assertEqual(len(self.queries()), 3)

        self.assertEqual(other_u.id, u.id)
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(len(self.queries()), 4)

        b = Blog.create(title='b blog')
        self.assertEqual(len(self.queries()), 5)

        u2 = User.get_or_create(username='b', blog=b)
        self.assertEqual(u2.blog, b)
        self.assertEqual(len(self.queries()), 7)

        other_u2 = User.get_or_create(username='b', blog=b)
        self.assertEqual(len(self.queries()), 8)

        self.assertEqual(User.select().count(), 2)


class UnicodeFieldTests(BaseModelTestCase):
    def get_common_objects(self):
        a = self.create_blog(title=u'Lýðveldið Ísland')
        e = self.create_entry(title=u'Hergé', content=u'Jökull', blog=a)
        return a, e

    def test_unicode_value(self):
        a, e = self.get_common_objects()
        a.refresh('title')
        e1 = Entry.get(pk=e.pk)
        self.assertEqual(a.title, u'Lýðveldið Ísland')
        self.assertEqual(e1.content, u'Jökull')

    def test_unicode_lookup(self):
        a, e = self.get_common_objects()

        a1 = Blog.get(title=u'Lýðveldið Ísland')
        self.assertEqual(a1.title, a.title)


class NodeTests(BaseModelTestCase):
    def test_simple(self):
        node = Q(a='A') | Q(b='B')
        self.assertEqual(unicode(node), 'a = A OR b = B')

        node = parseq(None, Q(a='A') | Q(b='B'))
        self.assertEqual(unicode(node), '(a = A OR b = B)')

        node = Q(a='A') & Q(b='B')
        self.assertEqual(unicode(node), 'a = A AND b = B')

        node = parseq(None, Q(a='A') & Q(b='B'))
        self.assertEqual(unicode(node), '(a = A AND b = B)')

    def test_kwargs(self):
        node = parseq(None, a='A', b='B')
        self.assertEqual(unicode(node), '(a = A AND b = B)')

    def test_mixed(self):
        node = parseq(None, Q(a='A'), Q(b='B'), c='C', d='D')
        self.assertEqual(unicode(node), 'a = A AND b = B AND (c = C AND d = D)')

        node = parseq(None, (Q(a='A') & Q(b='B')), c='C', d='D')
        self.assertEqual(unicode(node), '(c = C AND d = D) AND (a = A AND b = B)')

        node = parseq(None, (Q(a='A') | Q(b='B')), c='C', d='D')
        self.assertEqual(unicode(node), '(c = C AND d = D) AND (a = A OR b = B)')

    def test_nesting(self):
        node = parseq(None,
            (Q(a='A') | Q(b='B')),
            (Q(c='C') | Q(d='D'))
        )
        self.assertEqual(unicode(node), '(a = A OR b = B) AND (c = C OR d = D)')

        node = parseq(None,
            (Q(a='A') | Q(b='B')) &
            (Q(c='C') | Q(d='D'))
        )
        self.assertEqual(unicode(node), '((a = A OR b = B) AND (c = C OR d = D))')

        node = parseq(None,
            (Q(a='A') | Q(b='B')) |
            (Q(c='C') | Q(d='D'))
        )
        self.assertEqual(unicode(node), '((a = A OR b = B) OR (c = C OR d = D))')

    def test_weird_nesting(self):
        node = parseq(None,
            Q(a='A', b='B'),
            (
                Q(c='C') |
                Q(d='D')
            )
        )
        self.assertEqual(unicode(node), '(a = A AND b = B) AND (c = C OR d = D)')

        node = parseq(None,(
            (
                Q(c='C') |
                Q(d='D')
            ) |
            (
                Q(e='E', f='F')
            )
        ), a='A', b='B')
        self.assertEqual(unicode(node), '(a = A AND b = B) AND (c = C OR d = D OR (e = E AND f = F))')

        node = parseq(None,(
            (
                Q(c='C') |
                Q(d='D')
            ) |
            (
                Q(e='E', f='F') |
                Q(g='G', h='H')
            )
        ), a='A', b='B')
        self.assertEqual(unicode(node), '(a = A AND b = B) AND ((c = C OR d = D) OR ((e = E AND f = F) OR (h = H AND g = G)))')

    def test_node_and_q(self):
        node = parseq(None,
            (Q(a='A') & Q(b='B')) |
            (Q(c='C'))
        )
        self.assertEqual(unicode(node), '(c = C OR (a = A AND b = B))')

        node = parseq(None, Q(c='C') & (Q(a='A') | Q(b='B')))
        self.assertEqual(unicode(node), '((c = C) AND (a = A OR b = B))')


class RelatedFieldTests(BaseModelTestCase):
    def get_common_objects(self):
        a = self.create_blog(title='a')
        a1 = self.create_entry(title='a1', content='a1', blog=a)
        a2 = self.create_entry(title='a2', content='a2', blog=a)

        b = self.create_blog(title='b')
        b1 = self.create_entry(title='b1', content='b1', blog=b)
        b2 = self.create_entry(title='b2', content='b2', blog=b)

        t1 = self.create_entry_tag(tag='t1', entry=a2)
        t2 = self.create_entry_tag(tag='t2', entry=b2)
        return a, a1, a2, b, b1, b2, t1, t2

    def test_fk_caching(self):
        a = self.create_blog(title='a')
        e = self.create_entry(title='e', blog=a)

        self.assertEqual(e.blog, a)
        self.assertEqual(e.blog, a)

        self.assertQueriesEqual([
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']),
            ('INSERT INTO `entry` (`blog_id`,`content`,`pub_date`,`title`) VALUES (?,?,?,?)', [a.id, '', None, 'e']),
        ])

        e2 = Entry.get(pk=e.pk)
        self.assertEqual(e2.blog, a)
        self.assertEqual(e2.blog, a)

        self.assertQueriesEqual([
            ('INSERT INTO `blog` (`title`) VALUES (?)', ['a']),
            ('INSERT INTO `entry` (`blog_id`,`content`,`pub_date`,`title`) VALUES (?,?,?,?)', [a.id, '', None, 'e']),
            ('SELECT `pk`, `title`, `content`, `pub_date`, `blog_id` FROM `entry` WHERE `pk` = ? LIMIT 1', [e.pk]),
            ('SELECT `id`, `title` FROM `blog` WHERE `id` = ? LIMIT 1', [a.id]),
        ])

    def test_fk_exception(self):
        e = Entry(title='e')
        self.assertRaises(Blog.DoesNotExist, getattr, e, 'blog')

    def test_foreign_keys(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()

        self.assertEqual(len(self.queries()), 8)

        self.assertEqual(a1.blog, a)
        self.assertNotEqual(a1.blog, b)

        self.assertEqual(a1.blog_id, a.id)

        self.assertEqual(b1.blog, b)
        self.assertEqual(b1.blog_id, b.id)

        self.assertEqual(t1.entry.blog, a)
        self.assertEqual(t2.entry.blog, b)

        # no queries!
        self.assertEqual(len(self.queries()), 8)

        t = EntryTag.get(id=t1.id)
        self.assertEqual(t.entry.blog, a)
        self.assertEqual(t.entry.blog, a)

        # just 3, tag select, entry select, blog select
        self.assertEqual(len(self.queries()), 11)

        a3 = Entry(title='a3', content='a3')
        a3.blog = a
        self.assertEqual(a3.blog, a)
        self.assertEqual(a3.blog_id, a.id)

        a3.save()
        self.assertEqual(a3.blog, a)
        self.assertEqual(a3.blog_id, a.id)

        a3.blog = b
        self.assertEqual(a3.blog, b)
        self.assertEqual(a3.blog_id, b.id)

        a3.save()
        self.assertEqual(a3.blog, b)
        self.assertEqual(a3.blog_id, b.id)

    def test_reverse_fk(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()

        self.assertEqual(list(a.entry_set), [a1, a2])

        self.assertEqual(list(a.entry_set.where(title='a1')), [a1])

        self.assertEqual(list(a1.entrytag_set), [])
        self.assertEqual(list(a2.entrytag_set), [t1])

    def test_fk_querying(self):
        a_blog = Blog.create(title='a blog')
        a = User.create(username='a', blog=a_blog)
        b = User.create(username='b')

        qr = User.select().where(blog=a_blog)
        self.assertEqual(list(qr), [a])

    def test_querying_across_joins(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()

        sq = Blog.select().join(Entry).join(EntryTag)

        t1_sq = sq.where(tag='t1')
        self.assertEqual(list(t1_sq), [a])

        t2_sq = sq.where(tag='t2')
        self.assertEqual(list(t2_sq), [b])

        joined_sq = Blog.select().join(Entry)

        sq = joined_sq.where(title='a1').join(EntryTag).where(tag='t1')
        self.assertEqual(list(sq), [])

        sq = joined_sq.where(title='a2').join(EntryTag).where(tag='t1')
        self.assertEqual(list(sq), [a])

        et_sq = EntryTag.select().join(Entry).join(Blog)

        sq = et_sq.where(title='a')
        self.assertEqual(list(sq), [t1])

        sq = et_sq.where(title='b')
        self.assertEqual(list(sq), [t2])

        sq = EntryTag.select().join(Entry).where(title='a1').join(Blog).where(title='a')
        self.assertEqual(list(sq), [])

        sq = EntryTag.select().join(Entry).where(title='a2').join(Blog).where(title='a')
        self.assertEqual(list(sq), [t1])

    def test_querying_across_joins_with_q(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()

        sq = Blog.select().join(Entry).join(EntryTag).where(Q(tag='t1') | Q(tag='t2'))
        self.assertEqual(list(sq), [a, b])

        # permutations
        sq = Blog.select().join(Entry).where(Q(title='a2')).join(EntryTag).where(Q(tag='t1') | Q(tag='t2'))
        self.assertEqual(list(sq), [a])

        sq = Blog.select().join(Entry).where(Q(title='b2')).join(EntryTag).where(Q(tag='t1') | Q(tag='t2'))
        self.assertEqual(list(sq), [b])

        sq = Blog.select().join(Entry).where(Q(title='a2') | Q(title='b2')).join(EntryTag).where(Q(tag='t1'))
        self.assertEqual(list(sq), [a])

        sq = Blog.select().join(Entry).where(Q(title='a2') | Q(title='b2')).join(EntryTag).where(Q(tag='t2'))
        self.assertEqual(list(sq), [b])

        # work the other way
        sq = EntryTag.select().join(Entry).join(Blog).where(Q(title='a') | Q(title='b'))
        self.assertEqual(list(sq), [t1, t2])

        sq = EntryTag.select().join(Entry).where(Q(title='a2')).join(Blog).where(Q(title='a') | Q(title='b'))
        self.assertEqual(list(sq), [t1])

        sq = EntryTag.select().join(Entry).where(Q(title='b2')).join(Blog).where(Q(title='a') | Q(title='b'))
        self.assertEqual(list(sq), [t2])

        sq = EntryTag.select().join(Entry).where(Q(title='a2') | Q(title='b2')).join(Blog).where(Q(title='a'))
        self.assertEqual(list(sq), [t1])

        sq = EntryTag.select().join(Entry).where(Q(title='a2') | Q(title='b2')).join(Blog).where(Q(title='b'))
        self.assertEqual(list(sq), [t2])

    def test_querying_joins_mixed_q(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()

        sq = Blog.select().join(Entry).join(EntryTag).where(Q(Blog, title='a') | Q(tag='t2'))
        self.assertSQL(sq, [
            ('(t1.`title` = ? OR t3.`tag` = ?)', ['a', 't2'])
        ])
        self.assertEqual(list(sq), [a, b])

        sq = Blog.select().join(Entry).join(EntryTag).where(Q(Entry, title='a2') | Q(tag='t1') | Q(tag='t2'))
        self.assertSQL(sq, [
            ('(t2.`title` = ? OR t3.`tag` = ? OR t3.`tag` = ?)', ['a2', 't1', 't2'])
        ])

        sq = Blog.select().join(Entry).join(EntryTag).where(
            Q(Blog, title='b') | Q(Entry, title='a2'),
            Q(Entry, pk=1) | Q(EntryTag, tag='t1') | Q(tag='t2'),
        )
        self.assertSQL(sq, [
            ('(t1.`title` = ? OR t2.`title` = ?) AND (t2.`pk` = ? OR t3.`tag` = ? OR t3.`tag` = ?)', ['b', 'a2', 1, 't1', 't2']),
        ])

    def test_filtering_across_joins(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()

        t1_sq = Blog.filter(entry_set__entrytag_set__tag='t1')
        self.assertEqual(list(t1_sq), [a])

        t2_sq = Blog.filter(entry_set__entrytag_set__tag='t2')
        self.assertEqual(list(t2_sq), [b])

        sq = Blog.filter(entry_set__title='a1', entry_set__entrytag_set__tag='t1')
        self.assertEqual(list(sq), [])

        sq = Blog.filter(entry_set__title='a2', entry_set__entrytag_set__tag='t1')
        self.assertEqual(list(sq), [a])

        et_sq = EntryTag.select().join(Entry).join(Blog)

        sq = EntryTag.filter(entry__blog__title='a')
        self.assertEqual(list(sq), [t1])

        sq = EntryTag.filter(entry__blog__title='b')
        self.assertEqual(list(sq), [t2])

        sq = EntryTag.filter(entry__blog__title='a', entry__title='a1')
        self.assertEqual(list(sq), [])

        sq = EntryTag.filter(entry__blog__title='a', entry__title='a2')
        self.assertEqual(list(sq), [t1])

    def test_filtering_across_joins_with_q(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()

        sq = Blog.filter(Q(entry_set__entrytag_set__tag='t1')|Q(entry_set__entrytag_set__tag='t2'))
        self.assertEqual(list(sq), [a, b])

        # permutations
        sq = Blog.filter(Q(entry_set__title='a2'), Q(entry_set__entrytag_set__tag='t1')|Q(entry_set__entrytag_set__tag='t2'))
        self.assertEqual(list(sq), [a])

        sq = Blog.filter(Q(entry_set__title='b2'), Q(entry_set__entrytag_set__tag='t1')|Q(entry_set__entrytag_set__tag='t2'))
        self.assertEqual(list(sq), [b])

        sq = Blog.filter(Q(entry_set__title='a2')|Q(entry_set__title='b2'), Q(entry_set__entrytag_set__tag='t1'))
        self.assertEqual(list(sq), [a])

        sq = Blog.filter(Q(entry_set__title='a2')|Q(entry_set__title='b2'), Q(entry_set__entrytag_set__tag='t2'))
        self.assertEqual(list(sq), [b])

        # work the other way
        sq = EntryTag.filter(Q(entry__blog__title='a')|Q(entry__blog__title='b'))
        self.assertEqual(list(sq), [t1, t2])

        sq = EntryTag.filter(Q(entry__title='a2'), Q(entry__blog__title='a')|Q(entry__blog__title='b'))
        self.assertEqual(list(sq), [t1])

        sq = EntryTag.filter(Q(entry__title='b2'), Q(entry__blog__title='a')|Q(entry__blog__title='b'))
        self.assertEqual(list(sq), [t2])

        sq = EntryTag.filter(Q(entry__title='a2')|Q(entry__title='b2'), Q(entry__blog__title='a'))
        self.assertEqual(list(sq), [t1])

        sq = EntryTag.filter(Q(entry__title='a2')|Q(entry__title='b2'), Q(entry__blog__title='b'))
        self.assertEqual(list(sq), [t2])

    def test_mixing_models_filter_q(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()

        sq = EntryTag.filter(Q(entry__title='a2') | Q(entry__blog__title='b'))
        self.assertSQL(sq, [
            ('(t2.`title` = ? OR t3.`title` = ?)', ['a2', 'b']),
        ])
        self.assertEqual(list(sq), [t1, t2])

        sq = EntryTag.filter(Q(entry__title='a2') | Q(entry__blog__title='b'), tag='t1')
        self.assertSQL(sq, [
            ('(t2.`title` = ? OR t3.`title` = ?)', ['a2', 'b']),
            ('t1.`tag` = ?', ['t1']),
        ])
        self.assertEqual(list(sq), [t1])

        sq = Blog.filter(Q(entry_set__entrytag_set__tag='t1') | Q(entry_set__title='b1'))
        self.assertSQL(sq, [
            ('(t3.`tag` = ? OR t2.`title` = ?)', ['t1', 'b1']),
        ])

        sq = Blog.filter(Q(entry_set__entrytag_set__tag='t1') | Q(entry_set__title='b1'), title='b')
        self.assertSQL(sq, [
            ('(t3.`tag` = ? OR t2.`title` = ?)', ['t1', 'b1']),
            ('t1.`title` = ?', ['b']),
        ])

        sq = Blog.filter(Q(entry_set__entrytag_set__tag='t1') | Q(entry_set__title='b1'), Q(title='b') | Q(entry_set__title='b2'), entry_set__entrytag_set__id=1)
        self.assertSQL(sq, [
            ('(t3.`tag` = ? OR t2.`title` = ?)', ['t1', 'b1']),
            ('(t1.`title` = ? OR t2.`title` = ?)', ['b', 'b2']),
            ('t3.`id` = ?', [1]),
        ])

    def test_multiple_in(self):
        sq = Blog.select().where(title__in=['a', 'b']).join(Entry).where(title__in=['c', 'd'], content='foo')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`id`, t1.`title` FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` WHERE t1.`title` IN (?,?) AND (t2.`content` = ? AND t2.`title` IN (?,?))', ['a', 'b', 'foo', 'c', 'd']))

    def test_ordering_across_joins(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()
        b3 = self.create_entry(title='b3', blog=b)
        c = self.create_blog(title='c')
        c1 = self.create_entry(title='c1', blog=c)

        sq = Blog.select({
            Blog: ['*'],
            Entry: [peewee.Max('title', 'max_title')],
        }).join(Entry).order_by(peewee.desc('max_title')).group_by(Blog)
        results = list(sq)
        self.assertEqual(results, [c, b, a])
        self.assertEqual([r.max_title for r in results], ['c1', 'b3', 'a2'])

        sq = Blog.select({
            Blog: ['*'],
            Entry: [peewee.Max('title', 'max_title')],
        }).where(
            title__in=['a', 'b']
        ).join(Entry).order_by(peewee.desc('max_title')).group_by(Blog)
        results = list(sq)
        self.assertEqual(results, [b, a])
        self.assertEqual([r.max_title for r in results], ['b3', 'a2'])

        sq = Blog.select('t1.*, COUNT(t2.pk) AS count').join(Entry).order_by(peewee.desc('count')).group_by(Blog)
        qr = list(sq)

        self.assertEqual(qr, [b, a, c])
        self.assertEqual(qr[0].count, 3)
        self.assertEqual(qr[1].count, 2)
        self.assertEqual(qr[2].count, 1)

        sq = Blog.select({
            Blog: ['*'],
            Entry: [peewee.Count('pk', 'count')]
        }).join(Entry).group_by(Blog).order_by(peewee.desc('count'))
        qr = list(sq)

        self.assertEqual(qr, [b, a, c])
        self.assertEqual(qr[0].count, 3)
        self.assertEqual(qr[1].count, 2)
        self.assertEqual(qr[2].count, 1)

        # perform a couple checks that break in the postgres backend -- this is
        # due to the way postgresql does aggregation - it wants all the fields
        # used to be included in the DISTINCT query
        if BACKEND != 'postgresql':
            sq = Blog.select().join(Entry).order_by(peewee.desc('title')).distinct()
            self.assertEqual(list(sq), [c, b, a])

            sq = Blog.select().where(title__in=['a', 'b']).join(Entry).order_by(peewee.desc('title')).distinct()
            self.assertEqual(list(sq), [b, a])

    def test_nullable_fks(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')

        user_a = User(username='user_a', blog=a)
        user_a.save()

        user_a2 = User(username='user_a2', blog=a)
        user_a2.save()

        user_b = User(username='user_b', blog=b)
        user_b.save()

        sq = Blog.select({
            Blog: ['*'],
            User: [peewee.Count('id', 'count')]
        }).join(User).group_by(Blog).order_by(peewee.desc('count'))
        qr = list(sq)

        self.assertEqual(qr, [a, b, c])
        self.assertEqual(qr[0].count, 2)
        self.assertEqual(qr[1].count, 1)
        self.assertEqual(qr[2].count, 0)

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

        loose = User.select().join(Relationship, on='to_user').where(from_user=a).sql()
        strict = User.select().join(Relationship, on='to_user_id').where(from_user_id=a.id).sql()
        self.assertEqual(loose, strict)

        following = User.select().join(
            Relationship, on='to_user_id'
        ).where(from_user_id=a.id)
        self.assertEqual(list(following), [b])

        followers = User.select().join(
            Relationship, on='from_user_id'
        ).where(to_user_id=a.id)
        self.assertEqual(list(followers), [])

        following = User.select().join(
            Relationship, on='to_user_id'
        ).where(from_user_id=b.id)
        self.assertEqual(list(following), [c])

        followers = User.select().join(
            Relationship, on='from_user_id'
        ).where(to_user_id=b.id)
        self.assertEqual(list(followers), [a])

        following = User.select().join(
            Relationship, on='to_user_id'
        ).where(from_user_id=c.id)
        self.assertEqual(list(following), [])

        followers = User.select().join(
            Relationship, on='from_user_id'
        ).where(to_user_id=c.id)
        self.assertEqual(list(followers), [b])

    def test_subquery(self):
        a_blog = Blog.create(title='a blog')
        b_blog = Blog.create(title='b blog')
        c_blog = Blog.create(title='c blog')

        a = User.create(username='a', blog=a_blog)
        b = User.create(username='b', blog=b_blog)
        c = User.create(username='c', blog=c_blog)

        some_users = User.select().where(username__in=['a', 'b'])
        blogs = Blog.select().join(User).where(id__in=some_users)

        self.assertEqual(list(blogs), [a_blog, b_blog])

        a_entry = Entry.create(title='a entry', blog=a_blog)
        b_entry = Entry.create(title='b entry', blog=b_blog)
        c_entry = Entry.create(title='c entry', blog=c_blog)

        # this is an inadvisable query but useful for testing!
        some_entries = Entry.select().join(Blog).where(id__in=blogs)
        self.assertEqual(list(some_entries), [a_entry, b_entry])

        # check it without the join and a subquery on the FK
        some_entries2 = Entry.select().where(blog__in=blogs)
        self.assertEqual(list(some_entries2), [a_entry, b_entry])

        # ok, last one
        a_tag = EntryTag.create(tag='a', entry=a_entry)
        b_tag = EntryTag.create(tag='b', entry=b_entry)
        c_tag = EntryTag.create(tag='c', entry=c_entry)

        some_tags = EntryTag.select().join(Entry).where(pk__in=some_entries)
        self.assertEqual(list(some_tags), [a_tag, b_tag])

        # this should work the same
        some_tags = EntryTag.select().where(entry__in=some_entries)
        self.assertEqual(list(some_tags), [a_tag, b_tag])

    def test_complex_subquery(self):
        a_blog = Blog.create(title='a blog')
        b_blog = Blog.create(title='b blog')
        c_blog = Blog.create(title='c blog')

        a = User.create(username='a', blog=a_blog)
        b = User.create(username='b', blog=b_blog)
        c = User.create(username='c', blog=c_blog)

        some_users = User.select().where(username__in=['a', 'b'])

        c_blog_qr = Blog.select().join(User).where(~Q(id__in=some_users))
        self.assertEqual(list(c_blog_qr), [c_blog])

        ac_blog_qr = Blog.select().join(User).where(
            ~Q(id__in=some_users) |
            Q(username='a')
        )
        self.assertEqual(list(ac_blog_qr), [a_blog, c_blog])

    def test_many_to_many(self):
        a_team = Team.create(name='a-team')
        b_team = Team.create(name='b-team')
        x_team = Team.create(name='x-team')

        a_member1 = Member.create(username='a1')
        a_member2 = Member.create(username='a2')

        b_member1 = Member.create(username='b1')
        b_member2 = Member.create(username='b2')

        ab_member = Member.create(username='ab')
        x_member = Member.create(username='x')

        Membership.create(team=a_team, member=a_member1)
        Membership.create(team=a_team, member=a_member2)

        Membership.create(team=b_team, member=b_member1)
        Membership.create(team=b_team, member=b_member2)

        Membership.create(team=a_team, member=ab_member)
        Membership.create(team=b_team, member=ab_member)

        # query the FK in the rel table
        a_team_members = Member.select().join(Membership).where(team=a_team)
        self.assertEqual(list(a_team_members), [a_member1, a_member2, ab_member])

        b_team_members = Member.select().join(Membership).where(team=b_team)
        self.assertEqual(list(b_team_members), [b_member1, b_member2, ab_member])

        a_member_teams = Team.select().join(Membership).where(member=a_member1)
        self.assertEqual(list(a_member_teams), [a_team])

        ab_member_teams = Team.select().join(Membership).where(member=ab_member)
        self.assertEqual(list(ab_member_teams), [a_team, b_team])

        # query across the rel table
        across = Member.select().join(Membership).join(Team).where(name='a-team')
        self.assertEqual(list(across), [a_member1, a_member2, ab_member])

        across = Member.select().join(Membership).join(Team).where(name='b-team')
        self.assertEqual(list(across), [b_member1, b_member2, ab_member])

    def test_updating_fks(self):
        blog = self.create_blog(title='dummy')
        blog2 = self.create_blog(title='dummy2')

        e1 = self.create_entry(title='e1', content='e1', blog=blog)
        e2 = self.create_entry(title='e2', content='e2', blog=blog)
        e3 = self.create_entry(title='e3', content='e3', blog=blog)

        for entry in Entry.select():
            self.assertEqual(entry.blog, blog)

        uq = Entry.update(blog=blog2)
        uq.execute()

        for entry in Entry.select():
            self.assertEqual(entry.blog, blog2)

    def test_non_select_with_list_in_where(self):
        blog = self.create_blog(title='dummy')
        blog2 = self.create_blog(title='dummy2')

        e1 = self.create_entry(title='e1', content='e1', blog=blog)
        e2 = self.create_entry(title='e2', content='e2', blog=blog)
        e3 = self.create_entry(title='e3', content='e3', blog=blog)

        uq = Entry.update(blog=blog2).where(title__in=['e1', 'e3'])
        self.assertEqual(uq.execute(), 2)

        e1_db = Entry.get(pk=e1.pk)
        e2_db = Entry.get(pk=e2.pk)
        e3_db = Entry.get(pk=e3.pk)

        self.assertEqual(list(blog.entry_set), [e2])
        self.assertEqual(list(blog2.entry_set.order_by('title')), [e1, e3])

    def test_delete_instance(self):
        b1 = self.create_blog(title='b1')
        b2 = self.create_blog(title='b2')
        b3 = self.create_blog(title='b3')

        self.assertEqual(list(Blog.select().order_by('title')), [
            b1, b2, b3
        ])

        b1.delete_instance()
        self.assertEqual(list(Blog.select().order_by('title')), [
            b2, b3
        ])

        b3.delete_instance()
        self.assertEqual(list(Blog.select().order_by('title')), [
            b2
        ])

    def test_refresh(self):
        b1 = self.create_blog(title='b1')
        b2 = self.create_blog(title='b2')
        e1 = self.create_entry(title='e1', content='e1', blog=b1)
        e2 = self.create_entry(title='e2', content='e2', blog=b2)

        e1.title = '<edited>'
        e1.content = '<edited>'
        e1.refresh('title')

        self.assertEqual(e1.title, 'e1')
        self.assertEqual(e1.content, '<edited>')

        self.assertSQLEqual(self.queries()[-1], ('SELECT `title` FROM `entry` WHERE `pk` = ? LIMIT 1', [e1.pk]))

        e1.refresh()
        self.assertEqual(e1.content, 'e1')

        e2.title = 'foo'
        e2.content = 'xxx'
        e2.refresh('title')
        self.assertEqual(e2.title, 'e2')
        self.assertEqual(e2.content, 'xxx')

    def test_first_and_iteration(self):
        b1 = Blog.create(title='b1')
        b2 = Blog.create(title='b2')
        b3 = Blog.create(title='b3')

        qc = len(self.queries())

        blog_qr = Blog.select().order_by('id').execute()
        self.assertEqual(blog_qr.first(), b1)
        self.assertEqual(blog_qr.first(), b1)

        all_blogs = list(blog_qr)
        self.assertEqual(all_blogs, [b1, b2, b3])

        self.assertEqual(blog_qr.first(), b1)

        another_iter = [b for b in blog_qr]
        self.assertEqual(another_iter, all_blogs)

        partial_iter = [b for i, b in enumerate(blog_qr) if i < 2]
        self.assertEqual(partial_iter, [b1, b2])

        subsequent_iter = [b for b in blog_qr]
        self.assertEqual(subsequent_iter, all_blogs)

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

    def test_first_with_no_results(self):
        qc = len(self.queries())

        blog_qr = Blog.select().execute()
        self.assertEqual(blog_qr.first(), None)

        self.assertEqual(blog_qr.first(), None)

        all_blogs = list(blog_qr)
        self.assertEqual(all_blogs, [])

        self.assertEqual(blog_qr.first(), None)

        self.assertEqual([b for b in blog_qr], [])

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

    def test_fill_cache(self):
        for i in range(10):
            Blog.create(title='b%d' % i)

        qc = len(self.queries())

        blog_qr = Blog.select().order_by('id').execute()
        first = blog_qr.first()
        self.assertEqual(first.title, 'b0')
        self.assertEqual(len(blog_qr._result_cache), 1)
        self.assertFalse(blog_qr._populated)

        blog_qr.fill_cache()
        self.assertEqual(first.title, 'b0')
        self.assertEqual(len(blog_qr._result_cache), 10)
        self.assertTrue(blog_qr._populated)

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1)

        expected = ['b%d' % i for i in range(10)]
        self.assertEqual([x.title for x in blog_qr], expected)

        qc3 = len(self.queries())
        self.assertEqual(qc3 - qc, 1)

        blog_qr = Blog.select().order_by('id').execute()

        some_blogs = [b for i, b in enumerate(blog_qr) if i < 3]
        self.assertEqual([x.title for x in some_blogs], ['b0', 'b1', 'b2'])

        blog_qr.fill_cache()

        some_blogs = [b for i, b in enumerate(blog_qr) if i < 3]
        self.assertEqual([x.title for x in some_blogs], ['b0', 'b1', 'b2'])

        all_blogs = list(blog_qr)
        self.assertEqual([x.title for x in all_blogs], expected)

        qc4 = len(self.queries())
        self.assertEqual(qc4 - qc3, 1)

    def test_iterator(self):
        expected = ['b%d' % i for i in range(10)]
        for i in range(10):
            Blog.create(title='b%d' % i)

        qc = len(self.queries())

        qr = Blog.select().execute()
        titles = [b.title for b in qr.iterator()]

        self.assertEqual(titles, expected)
        qc1 = len(self.queries())
        self.assertEqual(qc1 - qc, 1)
        self.assertTrue(qr._populated)
        self.assertEqual(qr._result_cache, [])

        # just try to iterate
        again = [b.title for b in qr]
        self.assertEqual(again, [])
        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc1, 0)

        qr = Blog.select().where(title='xxxx').execute()
        titles = [b.title for b in qr.iterator()]
        self.assertEqual(titles, [])
    
    def test_naive_query(self):
        b1 = Blog.create(title='b1')
        b2 = Blog.create(title='b2')
        
        e11 = Entry.create(title='e11', blog=b1)
        e21 = Entry.create(title='e21', blog=b2)
        e22 = Entry.create(title='e22', blog=b2)
        
        # attr assignment works in the simple case
        sq = Blog.select().order_by('id').naive()
        self.assertEqual(dict((b.id, b.title) for b in sq), {
            b1.id: 'b1',
            b2.id: 'b2',
        })
        
        # aggregate assignment works as expected
        sq = Blog.select({
            Blog: ['id', 'title'],
            Entry: [peewee.Count('id', 'count')],
        }).order_by('id').join(Entry).group_by(Blog).naive()
        self.assertEqual(dict((b.id, [b.title, b.count]) for b in sq), {
            b1.id: ['b1', 1],
            b2.id: ['b2', 2],
        })
        
        # select related gets flattened
        sq = Entry.select({
            Entry: ['pk', 'title'],
            Blog: [('title', 'blog_title')],
        }).join(Blog).order_by('id').naive()
        self.assertEqual(dict((e.pk, [e.title, e.blog_title]) for e in sq), {
            e11.pk: ['e11', 'b1'],
            e21.pk: ['e21', 'b2'],
            e22.pk: ['e22', 'b2'],
        })
        
        # check that it works right when you're using a different underlying col
        lb1 = LegacyBlog.create(name='lb1')
        lb2 = LegacyBlog.create(name='lb2')
        sq = LegacyBlog.select(['id', 'name']).where(id__in=[lb1.id, lb2.id]).naive()
        self.assertEqual(dict((lb.id, lb.name) for lb in sq), {
            lb1.id: 'lb1',
            lb2.id: 'lb2',
        })


class RecursiveDeleteTestCase(BaseModelTestCase):
    def setUp(self):
        super(RecursiveDeleteTestCase, self).setUp()
        EntryTwo.drop_table(True)
        Category.drop_table(True)
        EntryTwo.create_table()
        Category.create_table()

    def tearDown(self):
        super(RecursiveDeleteTestCase, self).tearDown()
        EntryTwo.drop_table(True)
        Category.drop_table(True)

    def ro(self, o):
        return type(o).get(**{o._meta.pk_name: o.get_pk()})

    def test_recursive_delete(self):
        b1 = Blog.create(title='b1')
        b2 = Blog.create(title='b2')
        e11 = Entry.create(blog=b1, title='e11')
        e12 = Entry.create(blog=b1, title='e12')
        e21 = Entry.create(blog=b2, title='e21')
        e22 = Entry.create(blog=b2, title='e22')
        et11 = EntryTag.create(entry=e11, tag='et11')
        et12 = EntryTag.create(entry=e12, tag='et12')
        et21 = EntryTag.create(entry=e21, tag='et21')
        et22 = EntryTag.create(entry=e22, tag='et22')
        u1 = User.create(username='u1', blog=b1)
        u2 = User.create(username='u2', blog=b2)
        u3 = User.create(username='u3')
        r1 = Relationship.create(from_user=u1, to_user=u2)
        r2 = Relationship.create(from_user=u2, to_user=u3)
        c1 = Category.create(name='top')
        c2 = Category.create(name='l11', parent=c1)
        c3 = Category.create(name='l12', parent=c1)
        c4 = Category.create(name='l21', parent=c2)

        b1.delete_instance(recursive=True)
        self.assertEqual(Blog.select().count(), 1)
        self.assertEqual(Entry.select().count(), 2)
        self.assertEqual(EntryTag.select().count(), 2)
        self.assertEqual(User.select().count(), 3) # <-- user not affected since nullable
        self.assertEqual(Relationship.select().count(), 2)

        # check that the affected user had their blog set to null
        u1 = self.ro(u1)
        self.assertEqual(u1.blog, None)
        u2 = self.ro(u2)
        self.assertEqual(u2.blog, b2)

        # check that b2's entries are intact
        self.assertEqual(list(b2.entry_set.order_by('pk')), [e21, e22])

        # delete a self-referential FK model, should update to Null
        c2.delete_instance(recursive=True)
        self.assertEqual(list(c1.children.order_by('id')), [c3])
        c4 = self.ro(c4)
        self.assertEqual(c4.parent, None)

        # deleting a user deletes by joining on the proper keys
        u3.delete_instance(recursive=True)
        self.assertEqual(Relationship.select().count(), 1)
        r1 = self.ro(r1)
        self.assertEqual(r1.from_user, u1)
        self.assertEqual(r1.to_user, u2)

        u1.delete_instance(True)
        self.assertEqual(Relationship.select().count(), 0)


class SelectRelatedTestCase(BaseModelTestCase):
    def setUp(self):
        super(SelectRelatedTestCase, self).setUp()
        self.b1 = self.create_blog(title='b1')
        self.b2 = self.create_blog(title='b2')

        for b in [self.b1, self.b2]:
            for i in range(3):
                e = self.create_entry(title='e%d' % i, blog=b)
                t = self.create_entry_tag(tag='e%dt%d' % (i, i), entry=e)

    def test_select_related(self):
        qc1 = len(self.queries())

        sq = Entry.select({
            Entry: ['*'],
            Blog: ['*'],
        }).join(Blog).where(title='b1')

        results = list(sq)
        blog_titles = [r.blog.title for r in results]
        blog_ids = [r.blog.id for r in results]

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc1, 1)

        self.assertEqual(blog_titles, ['b1', 'b1', 'b1'])
        self.assertEqual(blog_ids, [self.b1.id, self.b1.id, self.b1.id])

    def test_select_related_with_missing_pk(self):
        qc1 = len(self.queries())

        sq = Entry.select({
            Entry: ['*'],
            Blog: ['title'],
        }).join(Blog).where(title='b1')

        results = list(sq)
        blog_titles = [r.blog.title for r in results]
        blog_ids = [r.blog.id for r in results]

        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc1, 1)

        self.assertEqual(blog_titles, ['b1', 'b1', 'b1'])
        self.assertEqual(blog_ids, [self.b1.id, self.b1.id, self.b1.id])

    def test_select_related_multiple(self):
        qc1 = len(self.queries())

        sq = EntryTag.select({
            EntryTag: ['*'],
            Entry: ['pk', 'blog_id'],
            Blog: ['title'],
        }).join(Entry).join(Blog).where(title='b1')

        results = list(sq)
        blog_titles = [r.entry.blog.title for r in results]
        blog_ids = [r.entry.blog.id for r in results]

        self.assertEqual(blog_titles, ['b1', 'b1', 'b1'])
        self.assertEqual(blog_ids, [self.b1.id, self.b1.id, self.b1.id])

        qc2 = len(self.queries())

        self.assertEqual(qc2 - qc1, 1)

        # didn't select title/content/pub_date on entries, so make sure they're none
        for r in results:
            self.assertEqual(r.entry.title, None)
            self.assertEqual(r.entry.content, None)
            self.assertEqual(r.entry.pub_date, None)
            self.assertFalse(r.entry.pk == None)


class FilterQueryTests(BaseModelTestCase):
    def test_filter_no_joins(self):
        query = Entry.filter(title='e1')
        self.assertSQL(query, [('`title` = ?', ['e1'])])

        query = Entry.filter(title__in=['e1', 'e2'])
        self.assertSQL(query, [('`title` IN (?,?)', [['e1', 'e2']])])

    def test_filter_missing_field(self):
        self.assertRaises(AttributeError, Entry.filter(missing='missing').sql)
        self.assertRaises(AttributeError, Entry.filter(blog__missing='missing').sql)

    def test_filter_joins(self):
        query = EntryTag.filter(entry__title='e1')
        self.assertSQL(query, [('t2.`title` = ?', ['e1'])])

        query = EntryTag.filter(entry__title__in=['e1', 'e2'])
        self.assertSQL(query, [('t2.`title` IN (?,?)', [['e1', 'e2']])])

        query = EntryTag.filter(entry__blog__title='b1')
        self.assertSQL(query, [('t3.`title` = ?', ['b1'])])

        query = EntryTag.filter(entry__blog__title__in=['b1', 'b2'])
        self.assertSQL(query, [('t3.`title` IN (?,?)', [['b1', 'b2']])])

        query = EntryTag.filter(entry__blog__title__in=['b1', 'b2'], entry__title='e1')
        self.assertSQL(query, [
            ('t3.`title` IN (?,?)', [['b1', 'b2']]),
            ('t2.`title` = ?', ['e1']),
        ])

        query = EntryTag.filter(entry__blog__title__in=['b1', 'b2'], entry__title='e1', tag='t1')
        self.assertSQL(query, [
            ('t3.`title` IN (?,?)', [['b1', 'b2']]),
            ('t2.`title` = ?', ['e1']),
            ('t1.`tag` = ?', ['t1']),
        ])

    def test_filter_reverse_joins(self):
        query = Blog.filter(entry_set__title='e1')
        self.assertSQL(query, [('t2.`title` = ?', ['e1'])])

        query = Blog.filter(entry_set__title__in=['e1', 'e2'])
        self.assertSQL(query, [('t2.`title` IN (?,?)', [['e1', 'e2']])])

        query = Blog.filter(entry_set__entrytag_set__tag='t1')
        self.assertSQL(query, [('t3.`tag` = ?', ['t1'])])

        query = Blog.filter(entry_set__entrytag_set__tag__in=['t1', 't2'])
        self.assertSQL(query, [('t3.`tag` IN (?,?)', [['t1', 't2']])])

        query = Blog.filter(entry_set__entrytag_set__tag__in=['t1', 't2'], entry_set__title='e1')
        self.assertSQL(query, [
            ('t3.`tag` IN (?,?)', [['t1', 't2']]),
            ('t2.`title` = ?', ['e1']),
        ])

        query = Blog.filter(entry_set__entrytag_set__tag__in=['t1', 't2'], entry_set__title='e1', title='b1')
        self.assertSQL(query, [
            ('t3.`tag` IN (?,?)', [['t1', 't2']]),
            ('t2.`title` = ?', ['e1']),
            ('t1.`title` = ?', ['b1']),
        ])

    def test_filter_multiple_lookups(self):
        query = Entry.filter(title='e1', pk=1)
        self.assertSQL(query, [
            ('(`pk` = ? AND `title` = ?)', [1, 'e1']),
        ])

        query = Entry.filter(title='e1', pk=1, blog__title='b1')
        self.assertSQL(query, [
            ('(t1.`pk` = ? AND t1.`title` = ?)', [1, 'e1']),
            ('t2.`title` = ?', ['b1'])
        ])

        query = Entry.filter(blog__id=2, title='e1', pk=1, blog__title='b1')
        self.assertSQL(query, [
            ('(t1.`pk` = ? AND t1.`title` = ?)', [1, 'e1']),
            ('(t2.`id` = ? AND t2.`title` = ?)', [2, 'b1']),
        ])

    def test_filter_with_q(self):
        query = Entry.filter(Q(title='e1') | Q(title='e2'))
        self.assertSQL(query, [
            ('(`title` = ? OR `title` = ?)', ['e1', 'e2'])
        ])

        query = Entry.filter(Q(title='e1') | Q(title='e2') | Q(title='e3'), Q(pk=1) | Q(pk=2))
        self.assertSQL(query, [
            ('(`title` = ? OR `title` = ? OR `title` = ?)', ['e1', 'e2', 'e3']),
            ('(`pk` = ? OR `pk` = ?)', [1, 2])
        ])

        query = Entry.filter(Q(title='e1') | Q(title='e2'), pk=1)
        self.assertSQL(query, [
            ('(`title` = ? OR `title` = ?)', ['e1', 'e2']),
            ('`pk` = ?', [1])
        ])

        # try with joins now
        query = Entry.filter(Q(blog__id=1) | Q(blog__id=2))
        self.assertSQL(query, [
            ('(t2.`id` = ? OR t2.`id` = ?)', [1, 2])
        ])

        query = Entry.filter(Q(blog__id=1) | Q(blog__id=2) | Q(blog__id=3), Q(blog__title='b1') | Q(blog__title='b2'))
        self.assertSQL(query, [
            ('(t2.`id` = ? OR t2.`id` = ? OR t2.`id` = ?)', [1, 2, 3]),
            ('(t2.`title` = ? OR t2.`title` = ?)', ['b1', 'b2'])
        ])

        query = Entry.filter(Q(blog__id=1) | Q(blog__id=2) | Q(blog__id=3), Q(blog__title='b1') | Q(blog__title='b2'), title='foo')
        self.assertSQL(query, [
            ('(t2.`id` = ? OR t2.`id` = ? OR t2.`id` = ?)', [1, 2, 3]),
            ('(t2.`title` = ? OR t2.`title` = ?)', ['b1', 'b2']),
            ('t1.`title` = ?', ['foo']),
        ])

        query = Entry.filter(Q(blog__id=1) | Q(blog__id=2) | Q(blog__id=3), Q(blog__title='b1') | Q(blog__title='b2'), title='foo', blog__title='baz')
        self.assertSQL(query, [
            ('(t2.`id` = ? OR t2.`id` = ? OR t2.`id` = ?)', [1, 2, 3]),
            ('(t2.`title` = ? OR t2.`title` = ?)', ['b1', 'b2']),
            ('t1.`title` = ?', ['foo']),
            ('t2.`title` = ?', ['baz']),
        ])

        query = EntryTag.filter(Q(entry__blog__title='b1') | Q(entry__blog__title='b2'), Q(entry__pk=1) | Q(entry__pk=2), tag='baz', entry__title='e1')
        self.assertSQL(query, [
            ('(t3.`title` = ? OR t3.`title` = ?)', ['b1', 'b2']),
            ('(t2.`pk` = ? OR t2.`pk` = ?)', [1, 2]),
            ('t1.`tag` = ?', ['baz']),
            ('t2.`title` = ?', ['e1']),
        ])

    def test_filter_with_query(self):
        simple_query = User.select().where(active=True)

        query = filter_query(simple_query, username='bamples')
        self.assertSQL(query, [
            ('`active` = ?', [1]),
            ('`username` = ?', ['bamples']),
        ])

        query = filter_query(simple_query, blog__title='b1')
        self.assertSQL(query, [
            ('t1.`active` = ?', [1]),
            ('t2.`title` = ?', ['b1']),
        ])

        join_query = User.select().join(Blog).where(title='b1')

        query = filter_query(join_query, username='bamples')
        self.assertSQL(query, [
            ('t1.`username` = ?', ['bamples']),
            ('t2.`title` = ?', ['b1']),
        ])

        # join should be recycled here
        query = filter_query(join_query, blog__id=1)
        self.assertSQL(query, [
            ('t2.`id` = ?', [1]),
            ('t2.`title` = ?', ['b1']),
        ])

        complex_query = User.select().join(Blog).where(Q(id=1)|Q(id=2))

        query = filter_query(complex_query, username='bamples', blog__title='b1')
        self.assertSQL(query, [
            ('(t2.`id` = ? OR t2.`id` = ?)', [1, 2]),
            ('t1.`username` = ?', ['bamples']),
            ('t2.`title` = ?', ['b1']),
        ])

        query = filter_query(complex_query, Q(blog__title='b1')|Q(blog__title='b2'), username='bamples')
        self.assertSQL(query, [
            ('(t2.`id` = ? OR t2.`id` = ?)', [1, 2]),
            ('t1.`username` = ?', ['bamples']),
            ('(t2.`title` = ? OR t2.`title` = ?)', ['b1', 'b2']),
        ])

        # zomg
        query = filter_query(complex_query, Q(blog__entry_set__title='e1')|Q(blog__entry_set__title='e2'), blog__title='b1', username='bamples')
        self.assertSQL(query, [
            ('(t2.`id` = ? OR t2.`id` = ?)', [1, 2]),
            ('(t3.`title` = ? OR t3.`title` = ?)', ['e1', 'e2']),
            ('t2.`title` = ?', ['b1']),
            ('t1.`username` = ?', ['bamples']),
        ])

    def test_filter_chaining(self):
        simple_filter = Entry.filter(blog__id=1)
        self.assertSQL(simple_filter, [
            ('t2.`id` = ?', [1])
        ])

        f2 = simple_filter.filter(Q(blog__title='b1') | Q(blog__title='b2'), title='e1')
        self.assertSQL(f2, [
            ('t2.`id` = ?', [1]),
            ('(t2.`title` = ? OR t2.`title` = ?)', ['b1', 'b2']),
            ('t1.`title` = ?', ['e1'])
        ])

    def test_filter_both_directions(self):
        f = Entry.filter(blog__title='b1', entrytag_set__tag='t1')
        self.assertSQL(f, [
            ('t2.`title` = ?', ['b1']),
            ('t3.`tag` = ?', ['t1']),
        ])


class AnnotateQueryTests(BaseModelTestCase):
    def get_some_blogs(self):
        blogs = [Blog.create(title='b%d' % i) for i in range(3)]
        entries = []

        for i, b in enumerate(blogs):
            for j in range(3 + i):
                entries.append(Entry.create(blog=b, title='e-%d-%d' % (i,j)))

        users = [
            User.create(username='u1a', blog=blogs[0]),
            User.create(username='u1b', blog=blogs[0]),
            User.create(username='u2', blog=blogs[1]),
            User.create(username='u3'),
        ]

        return blogs, entries, users

    def test_simple_annotation(self):
        blogs, entries, _ = self.get_some_blogs()

        annotated = Blog.select().annotate(Entry).order_by(('count', 'desc'))
        self.assertSQLEqual(annotated.sql(), (
            'SELECT t1.`id`, t1.`title`, COUNT(t2.`pk`) AS count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id`, t1.`title` ORDER BY count desc', []
        ))

        self.assertEqual([(b, b.count) for b in annotated], [
            (blogs[2], 5),
            (blogs[1], 4),
            (blogs[0], 3),
        ])

        Entry.delete().where(blog=blogs[1]).execute()

        self.assertEqual([(b, b.count) for b in annotated.clone()], [
            (blogs[2], 5),
            (blogs[0], 3),
        ])

        alt = Blog.select().join(Entry, 'left outer')
        annotated = alt.annotate(Entry).order_by(('count', 'desc'))
        self.assertSQLEqual(annotated.sql(), (
            'SELECT t1.`id`, t1.`title`, COUNT(t2.`pk`) AS count FROM `blog` AS t1 left outer JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id`, t1.`title` ORDER BY count desc', []
        ))

        self.assertEqual([(b, b.count) for b in annotated], [
            (blogs[2], 5),
            (blogs[0], 3),
            (blogs[1], 0),
        ])

    def test_nullable_annotate(self):
        blogs, entries, users = self.get_some_blogs()

        annotated = Blog.select().annotate(User).order_by(('count', 'desc'))
        self.assertSQLEqual(annotated.sql(), (
            ('SELECT t1.`id`, t1.`title`, COUNT(t2.`id`) AS count FROM `blog` AS t1 LEFT OUTER JOIN `users` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id`, t1.`title` ORDER BY count desc', [])
        ))

        self.assertEqual([(b, b.count) for b in annotated], [
            (blogs[0], 2),
            (blogs[1], 1),
            (blogs[2], 0),
        ])

    def test_limited_annotate(self):
        annotated = Blog.select('id').annotate(Entry)
        self.assertSQLEqual(annotated.sql(), (
            ('SELECT t1.`id`, COUNT(t2.`pk`) AS count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id`', [])
        ))

        annotated = Blog.select(['id', 'title']).annotate(Entry)
        self.assertSQLEqual(annotated.sql(), (
            ('SELECT t1.`id`, t1.`title`, COUNT(t2.`pk`) AS count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id`, t1.`title`', [])
        ))

        annotated = Blog.select({Blog: ['id']}).annotate(Entry)
        self.assertSQLEqual(annotated.sql(), (
            ('SELECT t1.`id`, COUNT(t2.`pk`) AS count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id`', [])
        ))

    def test_annotate_with_where(self):
        blogs, entries, users = self.get_some_blogs()

        annotated = Blog.select().where(title='b2').annotate(Entry)
        self.assertSQLEqual(annotated.sql(), (
            'SELECT t1.`id`, t1.`title`, COUNT(t2.`pk`) AS count FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` WHERE t1.`title` = ? GROUP BY t1.`id`, t1.`title`', ['b2']
        ))

        self.assertEqual([(b, b.count) for b in annotated], [
            (blogs[2], 5),
        ])

        # try with a join
        annotated = Blog.select().join(User).where(username='u2').annotate(Entry)
        self.assertSQLEqual(annotated.sql(), (
            'SELECT t1.`id`, t1.`title`, COUNT(t3.`pk`) AS count FROM `blog` AS t1 INNER JOIN `users` AS t2 ON t1.`id` = t2.`blog_id`\nINNER JOIN `entry` AS t3 ON t1.`id` = t3.`blog_id` WHERE t2.`username` = ? GROUP BY t1.`id`, t1.`title`', ['u2']
        ))

        self.assertEqual([(b, b.count) for b in annotated], [
            (blogs[1], 4),
        ])

    def test_annotate_custom_aggregate(self):
        annotated = Blog.select().annotate(Entry, peewee.Max('pub_date', 'max_pub'))
        self.assertSQLEqual(annotated.sql(), (
            'SELECT t1.`id`, t1.`title`, MAX(t2.`pub_date`) AS max_pub FROM `blog` AS t1 INNER JOIN `entry` AS t2 ON t1.`id` = t2.`blog_id` GROUP BY t1.`id`, t1.`title`', []
        ))

    def test_aggregate(self):
        blergs = [Blog.create(title='b%d' % i) for i in range(10)]

        ct = Blog.select().aggregate(peewee.Count('id'))
        self.assertEqual(ct, 10)

        max_id = Blog.select().aggregate(peewee.Max('id'))
        self.assertEqual(max_id, blergs[-1].id)


class FQueryTestCase(BaseModelTestCase):
    def setUp(self):
        super(FQueryTestCase, self).setUp()

        RelNumberModel.drop_table(True)
        NumberModel.drop_table(True)
        NumberModel.create_table()
        RelNumberModel.create_table()

    def test_f_object_simple(self):
        nm1 = NumberModel.create(num1=1, num2=1)
        nm2 = NumberModel.create(num1=2, num2=2)
        nm12 = NumberModel.create(num1=1, num2=2)
        nm21 = NumberModel.create(num1=2, num2=1)

        sq = NumberModel.select().where(num1=F('num2'))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `num1`, `num2` FROM `numbermodel` WHERE `num1` = `num2`', []))
        self.assertEqual(list(sq.order_by('id')), [nm1, nm2])

        sq = NumberModel.select().where(num1__lt=F('num2'))
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `num1`, `num2` FROM `numbermodel` WHERE `num1` < `num2`', []))
        self.assertEqual(list(sq.order_by('id')), [nm12])

        sq = NumberModel.select().where(num1=F('num2') - 1)
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `num1`, `num2` FROM `numbermodel` WHERE `num1` = (`num2` - 1)', []))
        self.assertEqual(list(sq.order_by('id')), [nm12])

    def test_f_object_joins(self):
        nm1 = NumberModel.create(num1=1, num2=1)
        nm2 = NumberModel.create(num1=2, num2=2)
        nm12 = NumberModel.create(num1=1, num2=2)
        nm21 = NumberModel.create(num1=2, num2=1)

        rnm1 = RelNumberModel.create(rel_num=1, num=nm1)
        rnm2 = RelNumberModel.create(rel_num=1, num=nm2)
        rnm12 = RelNumberModel.create(rel_num=1, num=nm12)
        rnm21 = RelNumberModel.create(rel_num=1, num=nm21)

        sq = RelNumberModel.select().join(NumberModel).where(num1=F('rel_num', RelNumberModel))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`id`, t1.`rel_num`, t1.`num_id` FROM `relnumbermodel` AS t1 INNER JOIN `numbermodel` AS t2 ON t1.`num_id` = t2.`id` WHERE t2.`num1` = t1.`rel_num`', []))
        self.assertEqual(list(sq.order_by('id')), [rnm1, rnm12])

        sq = RelNumberModel.select().join(NumberModel).where(
            Q(num1=F('rel_num', RelNumberModel)) |
            Q(num2=F('rel_num', RelNumberModel))
        )
        self.assertSQLEqual(sq.sql(), ('SELECT t1.`id`, t1.`rel_num`, t1.`num_id` FROM `relnumbermodel` AS t1 INNER JOIN `numbermodel` AS t2 ON t1.`num_id` = t2.`id` WHERE (t2.`num1` = t1.`rel_num` OR t2.`num2` = t1.`rel_num`)', []))
        self.assertEqual(list(sq.order_by('id')), [rnm1, rnm12, rnm21])


class RQueryTestCase(BaseModelTestCase):
    def test_simple(self):
        user_a = User.create(username='user a')
        user_b = User.create(username='user b')
        user_c = User.create(username='user c')

        # test selecting with an alias
        users = User.select(['id', R('UPPER(username)', 'upper_name')]).order_by('id')
        self.assertEqual([u.upper_name for u in users], ['USER A', 'USER B', 'USER C'])

        users = User.select(['id', R('UPPER(username)', 'upper_name'), R('LOWER(username)', 'lower_name')]).order_by('id')
        self.assertEqual([u.upper_name for u in users], ['USER A', 'USER B', 'USER C'])
        self.assertEqual([u.lower_name for u in users], ['user a', 'user b', 'user c'])

        if BACKEND not in ('postgresql', 'mysql'):
            # test selecting with matching where clause as a node
            users = User.select(['id', R('UPPER(username)', 'upper_name')]).where(R('upper_name = %s', 'USER B'))
            self.assertEqual([(u.id, u.upper_name) for u in users], [(user_b.id, 'USER B')])

        # test node multiple clauses
        users = User.select().where(R('username IN (%s, %s)', 'user a', 'user c'))
        self.assertEqual([u for u in users], [user_a, user_c])

        # test selecting with where clause as a keyword
        users = User.select(['id', R('UPPER(username)', 'upper_name')]).where(username=R('LOWER(%s)', 'USER B'))
        self.assertEqual([(u.id, u.upper_name) for u in users], [(user_b.id, 'USER B')])

        # test keyword multiple clauses
        users = User.select().where(username__in=R('LOWER(%s), LOWER(%s)', 'uSer A', 'uSeR c'))
        self.assertEqual([u for u in users], [user_a, user_c])

    def test_subquery(self):
        b1 = self.create_blog(title='b1')
        b2 = self.create_blog(title='b2')

        for i in range(3):
            self.create_entry(blog=b1, title='e%d' % (i+1))
            if i < 2:
                self.create_entry(blog=b2, title='e%d' % (i+1))

        # test subquery in select
        blogs = Blog.select(['id', 'title', R('(SELECT COUNT(*) FROM entry WHERE entry.blog_id=blog.id)', 'ct')]).order_by('ct')
        self.assertEqual([(b.id, b.title, b.ct) for b in blogs], [
            (b2.id, 'b2', 2),
            (b1.id, 'b1', 3),
        ])

        b3 = self.create_blog(title='b3')

        # test subquery in where clause as a node
        blogs = Blog.select().where(R('NOT EXISTS (SELECT * FROM entry WHERE entry.blog_id = blog.id)'))
        self.assertEqual([b.id for b in blogs], [b3.id])

        # test subquery in where clause as a keyword
        blogs = Blog.select().where(id__in=R('SELECT blog_id FROM entry WHERE entry.title = %s', 'e3'))
        self.assertEqual([b.id for b in blogs], [b1.id])

        blogs = Blog.select().where(id__in=R('SELECT blog_id FROM entry WHERE entry.title IN (LOWER(%s), LOWER(%s))', 'E2', 'e3'))
        self.assertEqual([b.id for b in blogs], [b1.id, b2.id])

    def test_combining(self):
        b1 = self.create_blog(title='b1')
        b2 = self.create_blog(title='b2')

        blogs = Blog.select().where(R('title = %s', 'b1') | R('title = %s', 'b2')).order_by('id')
        self.assertSQLEqual(blogs.sql(), ('SELECT `id`, `title` FROM `blog` WHERE (title = ? OR title = ?) ORDER BY `id` ASC', ['b1', 'b2']))

        self.assertEqual(list(blogs), [b1, b2])

        blogs = Blog.select().where(R('title = %s', 'b1') & (R('id = %s', 2) | R('id = %s', 3)))
        self.assertSQLEqual(blogs.sql(), ('SELECT `id`, `title` FROM `blog` WHERE ((title = ?) AND (id = ? OR id = ?))', ['b1', 2, 3]))


class SelfReferentialFKTestCase(BaseModelTestCase):
    def setUp(self):
        super(SelfReferentialFKTestCase, self).setUp()
        Category.drop_table(True)
        Category.create_table()

    def tearDown(self):
        super(SelfReferentialFKTestCase, self).tearDown()
        Category.drop_table(True)

    def test_self_referential_fk(self):
        # let's make a small tree
        python = Category.create(name='python')
        django = Category.create(name='django', parent=python)
        flask = Category.create(name='flask', parent=python)
        flask_peewee = Category.create(name='flask-peewee', parent=flask)

        self.assertEqual(flask_peewee.parent.name, 'flask')
        self.assertEqual(flask_peewee.parent.parent.name, 'python')

        self.assertEqual(list(python.children.order_by('name')), [
            django, flask
        ])

        self.assertEqual(list(flask.children), [flask_peewee])
        self.assertEqual(list(flask_peewee.children), [])


class ExplicitColumnNameTestCase(BasePeeweeTestCase):
    def setUp(self):
        super(ExplicitColumnNameTestCase, self).setUp()
        ExplicitEntry.drop_table(True)
        LegacyEntry.drop_table(True)
        LegacyBlog.drop_table(True)
        LegacyBlog.create_table()
        LegacyEntry.create_table()
        ExplicitEntry.create_table()

    def test_alternate_model_creation(self):
        lb = LegacyBlog.create(name='b1')
        self.assertEqual(lb.name, 'b1')
        self.assertTrue(lb.id >= 1)

        lb_db = LegacyBlog.get(id=lb.id)
        self.assertEqual(lb_db.name, 'b1')

        le = LegacyEntry.create(name='e1', blog=lb)
        self.assertEqual(le.name, 'e1')
        self.assertEqual(le.blog, lb)
        self.assertEqual(le.old_blog, lb.id)

        le_db = LegacyEntry.get(id=le.id)
        self.assertEqual(le_db.name, 'e1')
        self.assertEqual(le_db.blog, lb)
        self.assertEqual(le.old_blog, lb.id)

        ee = ExplicitEntry.create(name='e2', blog=lb)
        self.assertEqual(ee.name, 'e2')
        self.assertEqual(ee.blog, lb)
        self.assertEqual(ee.blog_id, lb.id)

        ee_db = ExplicitEntry.get(id=ee.id)
        self.assertEqual(ee_db.name, 'e2')
        self.assertEqual(ee_db.blog, lb)
        self.assertEqual(ee_db.blog_id, lb.id)

    def test_querying(self):
        lb1 = LegacyBlog.create(name='b1')
        lb2 = LegacyBlog.create(name='b2')
        le11 = LegacyEntry.create(name='e11', blog=lb1)
        le12 = LegacyEntry.create(name='e12', blog=lb1)
        le21 = LegacyEntry.create(name='e21', blog=lb2)
        ee = ExplicitEntry.create(name='ee1', blog=lb1)

        self.assertEqual(list(LegacyBlog.select().join(LegacyEntry).where(name='e11')), [lb1])
        self.assertEqual(list(LegacyEntry.select().join(LegacyBlog).where(name='b1')), [le11, le12])
        self.assertEqual(list(ExplicitEntry.select().join(LegacyBlog).where(name='b1')), [ee])

        self.assertEqual(list(LegacyBlog.filter(legacyentry_set__name='e21')), [lb2])
        self.assertEqual(list(LegacyEntry.filter(blog__name='b2')), [le21])
        self.assertEqual(list(ExplicitEntry.filter(blog__name='b1')), [ee])

        aq = LegacyBlog.select().annotate(LegacyEntry)
        ab1, ab2 = list(aq)
        self.assertEqual(ab1.name, 'b1')
        self.assertEqual(ab1.count, 2)
        self.assertEqual(ab2.name, 'b2')
        self.assertEqual(ab2.count, 1)

        aq2 = LegacyBlog.select().annotate(ExplicitEntry)
        res = list(aq2)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].count, 1)

        blogs = LegacyBlog.select().order_by(('name', 'desc'))
        self.assertEqual(list(blogs), [lb2, lb1])

        entries = LegacyEntry.select().join(LegacyBlog).order_by(('name', 'desc'), (LegacyEntry, 'id', 'asc'))
        self.assertEqual(list(entries), [le21, le11, le12])

        entries = LegacyEntry.select().where(old_blog=lb2.id)
        self.assertEqual(list(entries), [le21])

        entries = ExplicitEntry.select().where(blog=lb1.id)
        self.assertEqual(list(entries), [ee])

        blogs = LegacyBlog.select(['id', 'old_name'])
        b1, b2 = list(blogs)
        self.assertEqual(b1.name, 'b1')
        self.assertEqual(b1.id, lb1.id)
        self.assertEqual(b2.name, 'b2')
        self.assertEqual(b2.id, lb2.id)

        entries = LegacyEntry.select(['id', 'old_blog', 'name']).where(name='e21')
        e, = list(entries)
        self.assertEqual(e.id, le21.id)
        self.assertEqual(e.name, 'e21')
        self.assertEqual(e.blog, lb2)


class FieldTypeTests(BaseModelTestCase):
    def setUp(self):
        super(FieldTypeTests, self).setUp()
        NullModel.drop_table(True)
        DefaultVals.drop_table(True)
        NullModel.create_table()
        DefaultVals.create_table()

    def jd(self, d):
        return datetime.datetime(2010, 1, d)

    def create_common(self):
        b = self.create_blog(title='dummy')
        self.create_entry(title='b1', content='b1', pub_date=self.jd(1), blog=b)
        self.create_entry(title='b2', content='b2', pub_date=self.jd(2), blog=b)
        self.create_entry(title='b3', content='b3', pub_date=self.jd(3), blog=b)

    def assertSQEqual(self, sq, lst):
        self.assertEqual(sorted([x.title for x in sq]), sorted(lst))

    def test_lookups_charfield(self):
        self.create_common()

        self.assertSQEqual(Entry.select().where(title__gt='b1'), ['b2', 'b3'])
        self.assertSQEqual(Entry.select().where(title__gte='b2'), ['b2', 'b3'])

        self.assertSQEqual(Entry.select().where(title__lt='b3'), ['b1', 'b2'])
        self.assertSQEqual(Entry.select().where(title__lte='b2'), ['b1', 'b2'])

        self.assertSQEqual(Entry.select().where(title__icontains='b'), ['b1', 'b2', 'b3'])
        self.assertSQEqual(Entry.select().where(title__icontains='2'), ['b2'])

        self.assertSQEqual(Entry.select().where(title__contains='b'), ['b1', 'b2', 'b3'])

        self.assertSQEqual(Entry.select().where(title__in=['b1', 'b3']), ['b1', 'b3'])
        self.assertSQEqual(Entry.select().where(title__in=[]), [])

    def test_lookups_datefield(self):
        self.create_common()

        self.assertSQEqual(Entry.select().where(pub_date__gt=self.jd(1)), ['b2', 'b3'])
        self.assertSQEqual(Entry.select().where(pub_date__gte=self.jd(2)), ['b2', 'b3'])

        self.assertSQEqual(Entry.select().where(pub_date__lt=self.jd(3)), ['b1', 'b2'])
        self.assertSQEqual(Entry.select().where(pub_date__lte=self.jd(2)), ['b1', 'b2'])

        self.assertSQEqual(Entry.select().where(pub_date__in=[self.jd(1), self.jd(3)]), ['b1', 'b3'])
        self.assertSQEqual(Entry.select().where(pub_date__in=[]), [])

    def test_lookups_boolean_field(self):
        user_a = User.create(username='a', active=True)
        user_b = User.create(username='b')

        active = User.select().where(active=True)
        self.assertEqual(list(active), [user_a])

        inactive = User.select().where(active=False)
        self.assertEqual(list(inactive), [user_b])

        from_db_a = User.get(username='a')
        self.assertTrue(from_db_a.active)

        from_db_b = User.get(username='b')
        self.assertFalse(from_db_b.active)

    def test_null_models_and_lookups(self):
        nm = NullModel.create()
        self.assertEqual(nm.char_field, None)
        self.assertEqual(nm.text_field, None)
        self.assertEqual(nm.datetime_field, None)
        self.assertEqual(nm.int_field, None)
        self.assertEqual(nm.float_field, None)
        self.assertEqual(nm.decimal_field1, None)
        self.assertEqual(nm.decimal_field2, None)

        null_lookup = NullModel.select().where(char_field__is=None)
        self.assertSQLEqual(null_lookup.sql(), ('SELECT `id`, `char_field`, `text_field`, `datetime_field`, `int_field`, `float_field`, `decimal_field1`, `decimal_field2`, `double_field`, `bigint_field`, `date_field`, `time_field` FROM `nullmodel` WHERE `char_field` IS NULL', []))

        self.assertEqual(list(null_lookup), [nm])

        null_lookup = NullModel.select().where(~Q(char_field__is=None))
        self.assertSQLEqual(null_lookup.sql(), ('SELECT `id`, `char_field`, `text_field`, `datetime_field`, `int_field`, `float_field`, `decimal_field1`, `decimal_field2`, `double_field`, `bigint_field`, `date_field`, `time_field` FROM `nullmodel` WHERE NOT `char_field` IS NULL', []))

        non_null_lookup = NullModel.select().where(char_field='')
        self.assertSQLEqual(non_null_lookup.sql(), ('SELECT `id`, `char_field`, `text_field`, `datetime_field`, `int_field`, `float_field`, `decimal_field1`, `decimal_field2`, `double_field`, `bigint_field`, `date_field`, `time_field` FROM `nullmodel` WHERE `char_field` = ?', ['']))

        self.assertEqual(list(non_null_lookup), [])

        isnull_lookup = NullModel.select().where(char_field__isnull=True)
        self.assertSQLEqual(isnull_lookup.sql(), ('SELECT `id`, `char_field`, `text_field`, `datetime_field`, `int_field`, `float_field`, `decimal_field1`, `decimal_field2`, `double_field`, `bigint_field`, `date_field`, `time_field` FROM `nullmodel` WHERE `char_field` IS NULL', []))

        isnull_lookup = NullModel.select().where(char_field__isnull=False)
        self.assertSQLEqual(isnull_lookup.sql(), ('SELECT `id`, `char_field`, `text_field`, `datetime_field`, `int_field`, `float_field`, `decimal_field1`, `decimal_field2`, `double_field`, `bigint_field`, `date_field`, `time_field` FROM `nullmodel` WHERE `char_field` IS NOT NULL', []))

        isnull_lookup = NullModel.select().where(~Q(char_field__isnull=True))
        self.assertSQLEqual(isnull_lookup.sql(), ('SELECT `id`, `char_field`, `text_field`, `datetime_field`, `int_field`, `float_field`, `decimal_field1`, `decimal_field2`, `double_field`, `bigint_field`, `date_field`, `time_field` FROM `nullmodel` WHERE NOT `char_field` IS NULL', []))

        isnull_lookup = NullModel.select().where(~Q(char_field__isnull=False))
        self.assertSQLEqual(isnull_lookup.sql(), ('SELECT `id`, `char_field`, `text_field`, `datetime_field`, `int_field`, `float_field`, `decimal_field1`, `decimal_field2`, `double_field`, `bigint_field`, `date_field`, `time_field` FROM `nullmodel` WHERE NOT `char_field` IS NOT NULL', []))

        nm_from_db = NullModel.get(id=nm.id)
        self.assertEqual(nm_from_db.char_field, None)
        self.assertEqual(nm_from_db.text_field, None)
        self.assertEqual(nm_from_db.datetime_field, None)
        self.assertEqual(nm_from_db.int_field, None)
        self.assertEqual(nm_from_db.float_field, None)
        self.assertEqual(nm_from_db.decimal_field1, None)
        self.assertEqual(nm_from_db.decimal_field2, None)

        nm.char_field = ''
        nm.text_field = ''
        nm.int_field = 0
        nm.float_field = 0.0
        nm.decimal_field1 = 0
        nm.decimal_field2 = decimal.Decimal(0)
        nm.save()

        nm_from_db = NullModel.get(id=nm.id)
        self.assertEqual(nm_from_db.char_field, '')
        self.assertEqual(nm_from_db.text_field, '')
        self.assertEqual(nm_from_db.datetime_field, None)
        self.assertEqual(nm_from_db.int_field, 0)
        self.assertEqual(nm_from_db.float_field, 0.0)
        self.assertEqual(nm_from_db.decimal_field1, decimal.Decimal(0))
        self.assertEqual(nm_from_db.decimal_field2, decimal.Decimal(0))

    def test_decimal_precision(self):
        nm = NullModel()
        nm.decimal_field1 = decimal.Decimal("3.14159265358979323")
        nm.decimal_field2 = decimal.Decimal("100.33")
        nm.save()

        nm_from_db = NullModel.get(id=nm.id)
        # sqlite doesn't enforce these constraints properly
        #self.assertEqual(nm_from_db.decimal_field1, decimal.Decimal("3.14159"))
        self.assertEqual(nm_from_db.decimal_field2, decimal.Decimal("100.33"))

    def test_default_values(self):
        now = datetime.datetime.now() - datetime.timedelta(seconds=1)

        default_model = DefaultVals()

        # defaults are applied at initialization
        self.assertEqual(default_model.published, True)
        self.assertTrue(default_model.pub_date is not None)

        # saving the model will apply the defaults
        default_model.save()
        self.assertTrue(default_model.published)
        self.assertTrue(default_model.pub_date is not None)
        self.assertTrue(default_model.pub_date >= now)

        # overriding the defaults after initial save is fine
        default_model.pub_date = None
        default_model.save()
        self.assertEqual(default_model.pub_date, None)
        self.assertEqual(default_model.published, True)

        # overriding the defaults after initial save is fine
        default_model.published = False
        default_model.save()
        self.assertEqual(default_model.published, False)
        self.assertEqual(default_model.pub_date, None)

        # ensure that the overridden default was propagated to the db
        from_db = DefaultVals.get(id=default_model.id)
        self.assertFalse(default_model.published)
        self.assertEqual(default_model.pub_date, None)

        # test via the create method
        default_model2 = DefaultVals.create()
        self.assertTrue(default_model2.published)
        self.assertTrue(default_model2.pub_date is not None)
        self.assertTrue(default_model2.pub_date >= now)

        # pull it out of the database
        from_db = DefaultVals.get(id=default_model2.id)
        self.assertTrue(from_db.published)
        self.assertTrue(from_db.pub_date is not None)
        self.assertTrue(from_db.pub_date >= now)

        # check that manually specifying a zero but not-none value works
        default_model3 = DefaultVals.create(published=False)
        self.assertFalse(default_model3.published)
        self.assertTrue(default_model3.pub_date >= now)

    def test_naming(self):
        self.assertEqual(Entry._meta.fields['blog'].verbose_name, 'Blog')
        self.assertEqual(Entry._meta.fields['title'].verbose_name, 'Wacky title')

    def test_between_lookup(self):
        nm1 = NullModel.create(int_field=1)
        nm2 = NullModel.create(int_field=2)
        nm3 = NullModel.create(int_field=3)
        nm4 = NullModel.create(int_field=4)

        sq = NullModel.select().where(int_field__between=[2, 3])
        self.assertSQLEqual(sq.sql(), ('SELECT `id`, `char_field`, `text_field`, `datetime_field`, `int_field`, `float_field`, `decimal_field1`, `decimal_field2`, `double_field`, `bigint_field`, `date_field`, `time_field` FROM `nullmodel` WHERE `int_field` BETWEEN ? AND ?', [2, 3]))

        self.assertEqual(list(sq.order_by('id')), [nm2, nm3])

    def test_double_field(self):
        nm1 = NullModel.create(double_field=3.14159265358979)
        from_db = NullModel.get(id=nm1.id)
        self.assertEqual(from_db.double_field, 3.14159265358979)

    def test_bigint_field(self):
        nm1 = NullModel.create(bigint_field=1000000000000)
        from_db = NullModel.get(id=nm1.id)
        self.assertEqual(from_db.bigint_field, 1000000000000)
    
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

class NonIntegerPKTestCase(BasePeeweeTestCase):
    def setUp(self):
        super(NonIntegerPKTestCase, self).setUp()
        RelNonIntPK.drop_table(True)
        NonIntPK.drop_table(True)
        NonIntPK.create_table()
        RelNonIntPK.create_table()

    def test_creation(self):
        # create using the .create() API
        ni1 = NonIntPK.create(id='a1', name='ni1')
        self.assertEqual(ni1.id, 'a1')

        # explicitly use force_insert w/.save()
        ni2 = NonIntPK(id='a2', name='ni2')
        ni2.save(force_insert=True)
        self.assertEqual(ni2.id, 'a2')

        # saving again triggers in update
        ni2.save()
        self.assertEqual(ni2.id, 'a2')

        # check that we only have 2 instances
        self.assertEqual(NonIntPK.select().count(), 2)

        # check that can get from the db
        ni1_db = NonIntPK.get(id='a1')
        self.assertEqual(ni1_db, ni1)

        # check that can iterate them
        self.assertEqual(list(NonIntPK.select().order_by('id')), [
            ni1, ni2,
        ])

    def test_foreign_keys(self):
        ni1 = NonIntPK.create(id='a1', name='ni1')
        ni2 = NonIntPK.create(id='a2', name='ni2')

        rni11 = RelNonIntPK(non_int_pk=ni1, name='rni11')
        rni12 = RelNonIntPK(non_int_pk=ni1, name='rni12')
        rni11.save()
        rni12.save()

        self.assertEqual(list(ni1.relnonintpk_set.order_by('id')), [
            rni11, rni12,
        ])
        self.assertEqual(list(ni2.relnonintpk_set.order_by('id')), [])

        rni21 = RelNonIntPK.create(non_int_pk=ni2, name='rni21')

class ModelIndexTestCase(BaseModelTestCase):
    def setUp(self):
        super(ModelIndexTestCase, self).setUp()
        UniqueModel.drop_table(True)
        UniqueModel.create_table()

    def get_sorted_indexes(self, model):
        return test_db.get_indexes_for_table(model._meta.db_table)

    def check_postgresql_indexes(self, e, u):
        self.assertEqual(e, [
            ('entry_blog_id', False),
            ('entry_pkey', True),
        ])

        self.assertEqual(u, [
            ('users_active', False),
            ('users_blog_id', False),
            ('users_pkey', True),
        ])

    def check_sqlite_indexes(self, e, u):
        # when using an integer not null primary key, sqlite makes
        # the column an alias for the internally-used ``rowid``,
        # which is not visible to applications
        self.assertEqual(e, [
            ('entry_blog_id', False),
            #('entry_pk', True),
        ])

        self.assertEqual(u, [
            ('users_active', False),
            ('users_blog_id', False),
            #('users_id', True),
        ])

    def check_mysql_indexes(self, e, u):
        self.assertEqual(e, [
            ('PRIMARY', True),
            ('entry_blog_id', False),
        ])

        self.assertEqual(u, [
            ('PRIMARY', True),
            ('users_active', False),
            ('users_blog_id', False),
        ])

    def test_primary_key_index(self):
        # this feels pretty dirty to me but until I grok the details of index
        # naming and creation i'm going to check each backend
        if BACKEND == 'postgresql':
            method = self.check_postgresql_indexes
        elif BACKEND == 'mysql':
            method = self.check_mysql_indexes
        else:
            method = self.check_sqlite_indexes

        entry_indexes = self.get_sorted_indexes(Entry)
        user_indexes = self.get_sorted_indexes(User)
        method(entry_indexes, user_indexes)

    def test_unique_index(self):
        uniq1 = UniqueModel.create(name='a')
        uniq2 = UniqueModel.create(name='b')
        self.assertRaises(Exception, UniqueModel.create, name='a')
        test_db.rollback()


class ModelTablesTestCase(BaseModelTestCase):
    def test_tables_created(self):
        tables = test_db.get_tables()

        should_be = [
            'blog',
            'entry',
            'entrytag',
            'member',
            'membership',
            'relationship',
            'team',
            'users'
        ]
        for table in should_be:
            self.assertTrue(table in tables)

    def test_create_and_drop_table(self):
        self.assertTrue(EntryTag._meta.db_table in test_db.get_tables())

        # no exception should be raised here
        EntryTag.create_table(fail_silently=True)

        EntryTag.drop_table()
        self.assertFalse(EntryTag._meta.db_table in test_db.get_tables())

        # no exception should be raised here
        EntryTag.drop_table(fail_silently=True)

        EntryTag.create_table()
        self.assertTrue(EntryTag._meta.db_table in test_db.get_tables())

    def test_cascade_on_delete(self):
        if BACKEND == 'sqlite':
            test_db.execute('pragma foreign_keys = ON;')

        b1 = Blog.create(title='b1')
        b2 = Blog.create(title='b2')

        for b in [b1, b2]:
            for i in range(3):
                Entry.create(blog=b, title='e')

        self.assertEqual(Entry.select().count(), 6)
        b1.delete_instance()

        self.assertEqual(Entry.select().count(), 3)
        self.assertEqual(Entry.filter(blog=b1).count(), 0)
        self.assertEqual(Entry.filter(blog=b2).count(), 3)


class ModelOptionsTest(BaseModelTestCase):
    def test_model_meta(self):
        self.assertEqual(Blog._meta.get_field_names(), ['id', 'title'])
        self.assertEqual(Entry._meta.get_field_names(), ['pk', 'title', 'content', 'pub_date', 'blog'])

        sorted_fields = list(Entry._meta.get_sorted_fields())
        self.assertEqual(sorted_fields, [
            ('pk', Entry._meta.fields['pk']),
            ('title', Entry._meta.fields['title']),
            ('content', Entry._meta.fields['content']),
            ('pub_date', Entry._meta.fields['pub_date']),
            ('blog', Entry._meta.fields['blog']),
        ])

        sorted_fields = list(Blog._meta.get_sorted_fields())
        self.assertEqual(sorted_fields, [
            ('id', Blog._meta.fields['id']),
            ('title', Blog._meta.fields['title']),
        ])

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

    def test_ordering(self):
        self.assertEqual(User._meta.ordering, None)
        self.assertEqual(OrderedModel._meta.ordering, (('created', 'desc'),))

    def test_option_inheritance(self):
        test_db = peewee.Database(SqliteAdapter(), 'testing.db')
        child2_db = peewee.Database(SqliteAdapter(), 'child2.db')

        class FakeUser(peewee.Model):
            pass

        class ParentModel(peewee.Model):
            title = peewee.CharField()
            user = peewee.ForeignKeyField(FakeUser)

            class Meta:
                database = test_db

        class ChildModel(ParentModel):
            pass

        class ChildModel2(ParentModel):
            special_field = peewee.CharField()

            class Meta:
                database = child2_db

        class GrandChildModel(ChildModel):
            pass

        class GrandChildModel2(ChildModel2):
            special_field = peewee.TextField()

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
        self.assertTrue(isinstance(GrandChildModel2._meta.fields['special_field'], peewee.TextField))


class ModelInheritanceTestCase(BaseModelTestCase):
    def setUp(self):
        super(ModelInheritanceTestCase, self).setUp()
        EntryTwo.drop_table(True)
        EntryTwo.create_table()

    def tearDown(self):
        EntryTwo.drop_table(True)

    def test_model_inheritance(self):
        self.assertFalse(EntryTwo._meta.db_table == Entry._meta.db_table)

        b = Blog.create(title='b')

        e = Entry.create(title='e', blog=b)
        e2 = EntryTwo.create(title='e2', extra_field='foo', blog=b)

        self.assertEqual(list(b.entry_set), [e])
        self.assertEqual(list(b.entrytwo_set), [e2])

        self.assertEqual(Entry.select().count(), 1)
        self.assertEqual(EntryTwo.select().count(), 1)

        e_from_db = Entry.get(pk=e.pk)
        e2_from_db = EntryTwo.get(id=e2.id)

        self.assertEqual(e_from_db.blog, b)
        self.assertEqual(e2_from_db.blog, b)
        self.assertEqual(e2_from_db.extra_field, 'foo')


class ConcurrencyTestCase(BaseModelTestCase):
    def setUp(self):
        self._orig_db = test_db
        Blog._meta.database = database_class(database_name, threadlocals=True)
        BaseModelTestCase.setUp(self)

    def tearDown(self):
        Blog._meta.database = self._orig_db
        BaseModelTestCase.tearDown(self)

    def test_multiple_writers(self):
        def create_blog_thread(low, hi):
            for i in range(low, hi):
                Blog.create(title='test-%d' % i)
            Blog._meta.database.close()

        threads = []

        for i in range(5):
            threads.append(threading.Thread(target=create_blog_thread, args=(i*10, i * 10 + 10)))

        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(Blog.select().count(), 50)

    def test_multiple_readers(self):
        data_queue = Queue.Queue()

        def reader_thread(q, num):
            for i in range(num):
                data_queue.put(Blog.select().count())

        threads = []

        for i in range(5):
            threads.append(threading.Thread(target=reader_thread, args=(data_queue, 20)))

        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(data_queue.qsize(), 100)


class TransactionTestCase(BaseModelTestCase):
    def tearDown(self):
        super(TransactionTestCase, self).tearDown()
        test_db.set_autocommit(True)

    def test_autocommit(self):
        test_db.set_autocommit(False)

        b = Blog.create(title='b1')
        b2 = Blog.create(title='b2')

        # open up a new connection to the database, it won't register any blogs
        # as being created
        new_db = database_class(database_name)
        res = new_db.execute('select count(*) from blog;')
        self.assertEqual(res.fetchone()[0], 0)

        # commit our blog inserts
        test_db.commit()

        # now the blogs are query-able from another connection
        res = new_db.execute('select count(*) from blog;')
        self.assertEqual(res.fetchone()[0], 2)

    def test_commit_on_success(self):
        self.assertTrue(test_db.get_autocommit())

        @test_db.commit_on_success
        def will_fail():
            b = Blog.create(title='b1')
            e = Entry.create() # no blog, will raise an error
            return b, e

        self.assertRaises(Exception, will_fail)
        self.assertEqual(Blog.select().count(), 0)
        self.assertEqual(Entry.select().count(), 0)

        @test_db.commit_on_success
        def will_succeed():
            b = Blog.create(title='b1')
            e = Entry.create(title='e1', content='e1', blog=b)
            return b, e

        b, e = will_succeed()
        self.assertEqual(Blog.select().count(), 1)
        self.assertEqual(Entry.select().count(), 1)


if test_db.adapter.for_update_support:
    class ForUpdateTestCase(BaseModelTestCase):
        def tearDown(self):
            test_db.set_autocommit(True)

        def test_for_update(self):
            # create 3 blogs
            b1 = Blog.create(title='b1')
            b2 = Blog.create(title='b2')
            b3 = Blog.create(title='b3')

            test_db.set_autocommit(False)

            # select a blog for update
            blogs = Blog.select().where(title='b1').for_update()
            updated = Blog.update(title='b1_edited').where(title='b1').execute()
            self.assertEqual(updated, 1)

            # open up a new connection to the database
            new_db = database_class(database_name)

            # select the title, it will not register as being updated
            res = new_db.execute('select title from blog where id = %s;' % b1.id)
            blog_title = res.fetchone()[0]
            self.assertEqual(blog_title, 'b1')

            # committing will cause the lock to be released
            test_db.commit()

            # now we get the update
            res = new_db.execute('select title from blog where id = %s;' % b1.id)
            blog_title = res.fetchone()[0]
            self.assertEqual(blog_title, 'b1_edited')

else:
    print 'Skipping for update tests because backend does not support'

if test_db.adapter.sequence_support:
    class SequenceTestCase(BaseModelTestCase):
        def setUp(self):
            super(SequenceTestCase, self).setUp()
            self.safe_drop()
            SeqModelA.create_table()
            SeqModelB.create_table()

        def safe_drop(self):
            SeqModelA.drop_table(True)
            SeqModelB.drop_table(True)

            self.sequence = SeqModelBase._meta.pk_sequence
            if test_db.sequence_exists(self.sequence):
                test_db.drop_sequence(self.sequence)

        def tearDown(self):
            super(SequenceTestCase, self).tearDown()
            self.safe_drop()

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

else:
    print 'Skipping sequence tests because backend does not support'
