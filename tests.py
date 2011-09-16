import datetime
import logging
import os
import Queue
import threading
import unittest

import peewee
from peewee import (RawQuery, SelectQuery, InsertQuery, UpdateQuery, DeleteQuery,
        Node, Q, database, parseq, SqliteAdapter, PostgresqlAdapter, filter_query,
        annotate_query,)


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
    blog = peewee.ForeignKeyField(Blog)
    
    def __unicode__(self):
        return '%s: %s' % (self.blog.title, self.title)


class EntryTag(TestModel):
    tag = peewee.CharField(max_length=50)
    entry = peewee.ForeignKeyField(Entry)
    
    def __unicode__(self):
        return self.tag


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


class BasePeeweeTestCase(unittest.TestCase):
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
        
        self.qh = QueryLogHandler()
        peewee.logger.setLevel(logging.DEBUG)
        peewee.logger.addHandler(self.qh)
    
    def tearDown(self):
        peewee.logger.removeHandler(self.qh)
    
    def queries(self):
        return [x.msg for x in self.qh.queries]
    
    def assertQueriesEqual(self, queries):
        queries = [(q.replace('?', interpolation),p) for q,p in queries]
        self.assertEqual(queries, self.queries())

    def assertSQLEqual(self, lhs, rhs):
        self.assertEqual(lhs[0].replace('?', interpolation), rhs[0].replace('?', interpolation))
        self.assertEqual(lhs[1], rhs[1])
    
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
        rq = RawQuery(Blog, 'SELECT * FROM blog')
        self.assertSQLEqual(rq.sql(), ('SELECT * FROM blog', []))
        
        rq = RawQuery(Blog, 'SELECT * FROM blog WHERE title = ?', 'a')
        self.assertSQLEqual(rq.sql(), ('SELECT * FROM blog WHERE title = ?', ['a']))
        
        rq = RawQuery(Blog, 'SELECT * FROM blog WHERE title = ? OR title = ?', 'a', 'b')
        self.assertSQLEqual(rq.sql(), ('SELECT * FROM blog WHERE title = ? OR title = ?', ['a', 'b']))
    
    def test_select(self):
        sq = SelectQuery(Blog, '*')
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog', []))

        sq = SelectQuery(Blog, '*').where(title='a')
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE title = ?', ['a']))
        
        sq = SelectQuery(Blog, '*').where(title='a', id=1)
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (id = ? AND title = ?)', [1, 'a']))
        
        # check that chaining works as expected
        sq = SelectQuery(Blog, '*').where(title='a').where(id=1)
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE title = ? AND id = ?', ['a', 1]))
        
        # check that IN query special-case works
        sq = SelectQuery(Blog, '*').where(title__in=['a', 'b'])
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE title IN (?,?)', ['a', 'b']))
    
    def test_select_with_q(self):
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1))
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?)', ['a', 1]))
        
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1) | Q(id=3))
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ? OR id = ?)', ['a', 1, 3]))
        
        # test simple chaining
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where(Q(id=3))
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?) AND id = ?', ['a', 1, 3]))
        
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where(id=3)
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?) AND id = ?', ['a', 1, 3]))
        
        # test chaining with Q objects
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where((Q(title='c') | Q(id=3)))
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?) AND (title = ? OR id = ?)', ['a', 1, 'c', 3]))

        # test mixing it all up
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where((Q(title='c') | Q(id=3)), title='b')
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?) AND (title = ? OR id = ?) AND title = ?', ['a', 1, 'c', 3, 'b']))

    def test_select_with_negation(self):
        sq = SelectQuery(Blog, '*').where(~Q(title='a'))
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE NOT title = ?', ['a']))
        
        sq = SelectQuery(Blog, '*').where(~Q(title='a') | Q(title='b'))
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (NOT title = ? OR title = ?)', ['a', 'b']))
        
        sq = SelectQuery(Blog, '*').where(~Q(title='a') | ~Q(title='b'))
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (NOT title = ? OR NOT title = ?)', ['a', 'b']))
        
        sq = SelectQuery(Blog, '*').where(~(Q(title='a') | Q(title='b')))
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (NOT (title = ? OR title = ?))', ['a', 'b']))
        
        # chaining?
        sq = SelectQuery(Blog, '*').where(~(Q(title='a') | Q(id=1))).where(Q(id=3))
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (NOT (title = ? OR id = ?)) AND id = ?', ['a', 1, 3]))
        
        # mix n'match?
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where(~(Q(title='c') | Q(id=3)), title='b')
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?) AND (NOT (title = ? OR id = ?)) AND title = ?', ['a', 1, 'c', 3, 'b']))

    def test_select_with_models(self):
        sq = SelectQuery(Blog, {Blog: '*'})
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog', []))

        sq = SelectQuery(Blog, {Blog: ['title', 'id']})
        self.assertSQLEqual(sq.sql(), ('SELECT title, id FROM blog', []))
    
        sq = SelectQuery(Blog, {Blog: ['title', 'id']}).join(Entry)
        self.assertSQLEqual(sq.sql(), ('SELECT t1.title, t1.id FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id', []))

        sq = SelectQuery(Blog, {Blog: ['title', 'id'], Entry: [peewee.Count('pk')]}).join(Entry)
        self.assertSQLEqual(sq.sql(), ('SELECT t1.title, t1.id, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id', []))

        sq = SelectQuery(Blog, {Blog: ['title', 'id'], Entry: [peewee.Max('pk')]}).join(Entry)
        self.assertSQLEqual(sq.sql(), ('SELECT t1.title, t1.id, MAX(t2.pk) AS max FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id', []))

    def test_selecting_across_joins(self):
        sq = SelectQuery(Entry, '*').where(title='a1').join(Blog).where(title='a')

        self.assertEqual(sq._joins, {Entry: [(Blog, None, None)]})
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t1.title = ? AND t2.title = ?', ['a1', 'a']))
        
        sq = SelectQuery(Blog, '*').join(Entry).where(title='a1')        
        self.assertEqual(sq._joins, {Blog: [(Entry, None, None)]})
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t2.title = ?', ['a1']))

        sq = SelectQuery(EntryTag, '*').join(Entry).join(Blog).where(title='a')        
        self.assertEqual(sq._joins, {EntryTag: [(Entry, None, None)], Entry: [(Blog, None, None)]})
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entrytag AS t1 INNER JOIN entry AS t2 ON t1.entry_id = t2.pk\nINNER JOIN blog AS t3 ON t2.blog_id = t3.id WHERE t3.title = ?', ['a']))
        
        sq = SelectQuery(Blog, '*').join(Entry).join(EntryTag).where(tag='t2')
        self.assertEqual(sq._joins, {Blog: [(Entry, None, None)], Entry: [(EntryTag, None, None)]})
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id\nINNER JOIN entrytag AS t3 ON t2.pk = t3.entry_id WHERE t3.tag = ?', ['t2']))
    
    def test_selecting_across_joins_with_q(self):
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).join(Blog).where(title='e')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ?) AND t2.title = ?', ['a', 1, 'e']))
        
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1) | Q(title='b')).join(Blog).where(title='e')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ? OR t1.title = ?) AND t2.title = ?', ['a', 1, 'b', 'e']))

        # test simple chaining
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).where(Q(title='b')).join(Blog).where(title='e')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ?) AND t1.title = ? AND t2.title = ?', ['a', 1, 'b', 'e']))
        
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).where(title='b').join(Blog).where(title='e')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ?) AND t1.title = ? AND t2.title = ?', ['a', 1, 'b', 'e']))

        # test q on both models
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).join(Blog).where(Q(title='e') | Q(id=2))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ?) AND (t2.title = ? OR t2.id = ?)', ['a', 1, 'e', 2]))
    
        # test q on both with nesting
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).join(Blog).where((Q(title='e') | Q(id=2)) & (Q(title='f') | Q(id=3)))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ?) AND ((t2.title = ? OR t2.id = ?) AND (t2.title = ? OR t2.id = ?))', ['a', 1, 'e', 2, 'f', 3]))

    def test_selecting_with_switching(self):
        sq = SelectQuery(Blog, '*').join(Entry).switch(Blog).where(title='a')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t1.title = ?', ['a']))
    
    def test_selecting_with_aggregation(self):
        sq = SelectQuery(Blog, 't1.*, COUNT(t2.pk) AS count').group_by('id').join(Entry)
        self.assertEqual(sq._where, {})
        self.assertEqual(sq._joins, {Blog: [(Entry, None, None)]})
        self.assertSQLEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id', []))
        
        sq = sq.having('count > 2')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id HAVING count > 2', []))
        
        sq = SelectQuery(Blog, {
            Blog: ['*'],
            Entry: [peewee.Count('pk')]
        }).group_by('id').join(Entry)
        self.assertSQLEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id', []))
        
        sq = sq.having('count > 2')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id HAVING count > 2', []))
        
        sq = sq.order_by(('count', 'desc'))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id HAVING count > 2 ORDER BY count desc', []))
    
    def test_selecting_with_ordering(self):        
        sq = SelectQuery(Blog).order_by('title')
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog ORDER BY title ASC', []))
        
        sq = SelectQuery(Blog).order_by(peewee.desc('title'))
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog ORDER BY title DESC', []))
        
        sq = SelectQuery(Entry).order_by(peewee.desc('title')).join(Blog).where(title='a')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t2.title = ? ORDER BY t1.title DESC', ['a']))
        
        sq = SelectQuery(Entry).join(Blog).order_by(peewee.desc('title'))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id ORDER BY t2.title DESC', []))

    def test_ordering_on_aggregates(self):
        sq = SelectQuery(
            Blog, 't1.*, COUNT(t2.pk) as count'
        ).join(Entry).order_by(peewee.desc('count'))
        self.assertSQLEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) as count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id ORDER BY count DESC', []))

    def test_insert(self):
        iq = InsertQuery(Blog, title='a')
        self.assertSQLEqual(iq.sql(), ('INSERT INTO blog (title) VALUES (?)', ['a']))
        self.assertEqual(iq.execute(), 1)
        
        iq = InsertQuery(Blog, title='b')
        self.assertSQLEqual(iq.sql(), ('INSERT INTO blog (title) VALUES (?)', ['b']))
        self.assertEqual(iq.execute(), 2)
    
    def test_update(self):
        iq = InsertQuery(Blog, title='a').execute()
        
        uq = UpdateQuery(Blog, title='A').where(id=1)
        self.assertSQLEqual(uq.sql(), ('UPDATE blog SET title=? WHERE id = ?', ['A', 1]))
        self.assertEqual(uq.execute(), 1)
        
        iq2 = InsertQuery(Blog, title='b').execute()
        
        uq = UpdateQuery(Blog, title='B').where(id=2)
        self.assertSQLEqual(uq.sql(), ('UPDATE blog SET title=? WHERE id = ?', ['B', 2]))
        self.assertEqual(uq.execute(), 1)
        
        sq = SelectQuery(Blog).order_by('id')
        self.assertEqual([x.title for x in sq], ['A', 'B'])
    
    def test_update_with_q(self):
        uq = UpdateQuery(Blog, title='A').where(Q(id=1))
        self.assertSQLEqual(uq.sql(), ('UPDATE blog SET title=? WHERE id = ?', ['A', 1]))
        
        uq = UpdateQuery(Blog, title='A').where(Q(id=1) | Q(id=3))
        self.assertSQLEqual(uq.sql(), ('UPDATE blog SET title=? WHERE (id = ? OR id = ?)', ['A', 1, 3]))
    
    def test_delete(self):
        InsertQuery(Blog, title='a').execute()
        InsertQuery(Blog, title='b').execute()
        InsertQuery(Blog, title='c').execute()
        
        dq = DeleteQuery(Blog).where(title='b')
        self.assertSQLEqual(dq.sql(), ('DELETE FROM blog WHERE title = ?', ['b']))
        self.assertEqual(dq.execute(), 1)
        
        sq = SelectQuery(Blog).order_by('id')
        self.assertEqual([x.title for x in sq], ['a', 'c'])
        
        dq = DeleteQuery(Blog)
        self.assertSQLEqual(dq.sql(), ('DELETE FROM blog', []))
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
    
    def test_pagination(self):
        base_sq = SelectQuery(Blog)
        
        sq = base_sq.paginate(1, 20)
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog LIMIT 20 OFFSET 0', []))
        
        sq = base_sq.paginate(3, 30)
        self.assertSQLEqual(sq.sql(), ('SELECT * FROM blog LIMIT 30 OFFSET 60', []))
    
    def test_inner_joins(self):
        sql = SelectQuery(Blog).join(Entry).sql()
        self.assertSQLEqual(sql, ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id', []))
        
        sql = SelectQuery(Entry).join(Blog).sql()
        self.assertSQLEqual(sql, ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id', []))

    def test_outer_joins(self):
        sql = SelectQuery(User).join(Blog).sql()
        self.assertSQLEqual(sql, ('SELECT t1.* FROM users AS t1 LEFT OUTER JOIN blog AS t2 ON t1.blog_id = t2.id', []))
        
        sql = SelectQuery(Blog).join(User).sql()
        self.assertSQLEqual(sql, ('SELECT t1.* FROM blog AS t1 LEFT OUTER JOIN users AS t2 ON t1.id = t2.blog_id', []))
    
    def test_cloning(self):
        base_sq = SelectQuery(Blog)
        
        q1 = base_sq.where(title='a')
        q2 = base_sq.where(title='b')
        
        q1_sql = ('SELECT * FROM blog WHERE title = ?', ['a'])
        q2_sql = ('SELECT * FROM blog WHERE title = ?', ['b'])
        
        # where causes cloning
        self.assertSQLEqual(base_sq.sql(), ('SELECT * FROM blog', []))
        self.assertSQLEqual(q1.sql(), q1_sql)
        self.assertSQLEqual(q2.sql(), q2_sql)
        
        q3 = q1.join(Entry)
        q3_sql = ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t1.title = ?', ['a'])
        
        # join causes cloning
        self.assertSQLEqual(q3.sql(), q3_sql)
        self.assertSQLEqual(q1.sql(), q1_sql)
        
        q4 = q1.order_by('title')
        q5 = q3.order_by('title')
        
        q4_sql = ('SELECT * FROM blog WHERE title = ? ORDER BY title ASC', ['a'])
        q5_sql = ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t1.title = ? ORDER BY t2.title ASC', ['a'])
        
        # order_by causes cloning
        self.assertSQLEqual(q3.sql(), q3_sql)
        self.assertSQLEqual(q1.sql(), q1_sql)
        self.assertSQLEqual(q4.sql(), q4_sql)
        self.assertSQLEqual(q5.sql(), q5_sql)
        
        q6 = q1.paginate(1, 10)
        q7 = q4.paginate(2, 10)
        
        q6_sql = ('SELECT * FROM blog WHERE title = ? LIMIT 10 OFFSET 0', ['a'])
        q7_sql = ('SELECT * FROM blog WHERE title = ? ORDER BY title ASC LIMIT 10 OFFSET 10', ['a'])

        self.assertSQLEqual(q6.sql(), q6_sql)
        self.assertSQLEqual(q7.sql(), q7_sql)
    
    def test_multi_joins(self):
        sq = Entry.select().join(Blog).where(title='b1').switch(Entry).join(EntryTag).where(tag='t1')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id\nINNER JOIN entrytag AS t3 ON t1.pk = t3.entry_id WHERE t2.title = ? AND t3.tag = ?', ['b1', 't1']))
        
        sq = Entry.select().join(EntryTag).where(tag='t1').switch(Entry).join(Blog).where(title='b1')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN entrytag AS t2 ON t1.pk = t2.entry_id\nINNER JOIN blog AS t3 ON t1.blog_id = t3.id WHERE t2.tag = ? AND t3.title = ?', ['t1', 'b1']))


class ModelTests(BasePeeweeTestCase):
    def test_model_save(self):
        a = self.create_blog(title='a')
        self.assertEqual(a.id, 1)
        
        b = self.create_blog(title='b')
        self.assertEqual(b.id, 2)
        
        a.save()
        b.save()
        
        self.assertQueriesEqual([
            ('INSERT INTO blog (title) VALUES (?)', ['a']),
            ('INSERT INTO blog (title) VALUES (?)', ['b']),
            ('UPDATE blog SET title=? WHERE id = ?', ['a', 1]),
            ('UPDATE blog SET title=? WHERE id = ?', ['b', 2]),
        ])

        all_blogs = list(Blog.select().order_by('id'))
        self.assertEqual(all_blogs, [a, b])
    
    def test_model_get(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        
        b2 = Blog.get(title='b')
        self.assertEqual(b2.id, b.id)
        
        self.assertQueriesEqual([
            ('INSERT INTO blog (title) VALUES (?)', ['a']),
            ('INSERT INTO blog (title) VALUES (?)', ['b']),
            ('SELECT * FROM blog WHERE title = ? LIMIT 1 OFFSET 0', ['b']),
        ])
    
    def test_model_get_with_q(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        
        b2 = Blog.get(Q(title='b') | Q(title='c'))
        self.assertEqual(b2.id, b.id)
        
        self.assertQueriesEqual([
            ('INSERT INTO blog (title) VALUES (?)', ['a']),
            ('INSERT INTO blog (title) VALUES (?)', ['b']),
            ('SELECT * FROM blog WHERE (title = ? OR title = ?) LIMIT 1 OFFSET 0', ['b', 'c']),
        ])
    
    def test_model_raw(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')
        
        qr = Blog.raw('SELECT * FROM blog ORDER BY title ASC')
        self.assertEqual(list(qr), [a, b, c])
        
        qr = Blog.raw('SELECT * FROM blog WHERE title IN (%s, %s) ORDER BY title DESC' % (interpolation, interpolation), 'a', 'c')
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
            ('INSERT INTO blog (title) VALUES (?)', ['a']),
            ('INSERT INTO blog (title) VALUES (?)', ['b']),
            ('INSERT INTO blog (title) VALUES (?)', ['c']),
            ('SELECT * FROM blog ORDER BY title ASC', []),
            ('SELECT * FROM blog WHERE title IN (?,?) ORDER BY title DESC', ['a', 'c']),
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
            ('INSERT INTO blog (title) VALUES (?)', ['a']),
            ('INSERT INTO blog (title) VALUES (?)', ['b']),
            ('SELECT * FROM blog WHERE (title = ? OR title = ?)', ['a', 'b']),
            ('SELECT * FROM blog WHERE (title IN (?) OR title IN (?,?))', ['a', 'c', 'd']),
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
            ('INSERT INTO blog (title) VALUES (?)', ['a']),
            ('INSERT INTO blog (title) VALUES (?)', ['b']),
            ('SELECT * FROM blog ORDER BY title ASC', []),
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
            ('INSERT INTO blog (title) VALUES (?)', ['a']),
            ('INSERT INTO blog (title) VALUES (?)', ['b']),
            ('SELECT * FROM blog ORDER BY title ASC', []),
        ])

        # iterating again does not cause evaluation
        blogs = [b for b in sq]
        self.assertEqual(blogs, [a, b])
        self.assertEqual(len(self.queries()), 3)
        
        # clone the query
        clone = sq.clone()
        
        # the query will be marked dirty and re-evaluated
        blogs = [b for b in clone]
        self.assertEqual(blogs, [a, b])
        
        self.assertQueriesEqual([
            ('INSERT INTO blog (title) VALUES (?)', ['a']),
            ('INSERT INTO blog (title) VALUES (?)', ['b']),
            ('SELECT * FROM blog ORDER BY title ASC', []),
            ('SELECT * FROM blog ORDER BY title ASC', []),
        ])
        
        # iterate over the original query - it will use the cached results
        blogs = [b for b in sq]
        self.assertEqual(blogs, [a, b])
        
        self.assertEqual(len(self.queries()), 4)
    
    def test_create(self):
        u = User.create(username='a')
        self.assertEqual(u.username, 'a')
        self.assertQueriesEqual([
            ('INSERT INTO users (username,active,blog_id) VALUES (?,?,?)', ['a', 0, None]),
        ])

        b = Blog.create(title='b blog')
        u2 = User.create(username='b', blog=b)
        self.assertEqual(u2.blog, b)

        self.assertQueriesEqual([
            ('INSERT INTO users (username,active,blog_id) VALUES (?,?,?)', ['a', 0, None]),
            ('INSERT INTO blog (title) VALUES (?)', ['b blog']),
            ('INSERT INTO users (username,active,blog_id) VALUES (?,?,?)', ['b', 0, b.id]),
        ])

    def test_get_raises_does_not_exist(self):
        self.assertRaises(User.DoesNotExist, User.get, username='a')

    def test_get_or_create(self):
        u = User.get_or_create(username='a')
        self.assertEqual(u.username, 'a')
        self.assertQueriesEqual([
            ('SELECT * FROM users WHERE username = ? LIMIT 1 OFFSET 0', ['a']),
            ('INSERT INTO users (username,active,blog_id) VALUES (?,?,?)', ['a', 0, None]),
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


class NodeTests(BasePeeweeTestCase):
    def test_simple(self):
        node = Q(a='A') | Q(b='B')
        self.assertEqual(unicode(node), 'a = A OR b = B')
        
        node = parseq(Q(a='A') | Q(b='B'))
        self.assertEqual(unicode(node), '(a = A OR b = B)')
        
        node = Q(a='A') & Q(b='B')
        self.assertEqual(unicode(node), 'a = A AND b = B')
        
        node = parseq(Q(a='A') & Q(b='B'))
        self.assertEqual(unicode(node), '(a = A AND b = B)')
    
    def test_kwargs(self):
        node = parseq(a='A', b='B')
        self.assertEqual(unicode(node), '(a = A AND b = B)')
    
    def test_mixed(self):
        node = parseq(Q(a='A'), Q(b='B'), c='C', d='D')
        self.assertEqual(unicode(node), 'a = A AND b = B AND (c = C AND d = D)')
        
        node = parseq((Q(a='A') & Q(b='B')), c='C', d='D')
        self.assertEqual(unicode(node), '(c = C AND d = D) AND (a = A AND b = B)')
        
        node = parseq((Q(a='A') | Q(b='B')), c='C', d='D')
        self.assertEqual(unicode(node), '(c = C AND d = D) AND (a = A OR b = B)')
    
    def test_nesting(self):
        node = parseq(
            (Q(a='A') | Q(b='B')),
            (Q(c='C') | Q(d='D'))
        )
        self.assertEqual(unicode(node), '(a = A OR b = B) AND (c = C OR d = D)')
        
        node = parseq(
            (Q(a='A') | Q(b='B')) &
            (Q(c='C') | Q(d='D'))
        )
        self.assertEqual(unicode(node), '((a = A OR b = B) AND (c = C OR d = D))')

        node = parseq(
            (Q(a='A') | Q(b='B')) |
            (Q(c='C') | Q(d='D'))
        )
        self.assertEqual(unicode(node), '((a = A OR b = B) OR (c = C OR d = D))')
    
    def test_weird_nesting(self):
        node = parseq(
            Q(a='A', b='B'),
            (
                Q(c='C') |
                Q(d='D')
            )
        )
        self.assertEqual(unicode(node), '(a = A AND b = B) AND (c = C OR d = D)')
        
        node = parseq((
            (
                Q(c='C') |
                Q(d='D')
            ) |
            (
                Q(e='E', f='F')
            )
        ), a='A', b='B')
        self.assertEqual(unicode(node), '(a = A AND b = B) AND (c = C OR d = D OR (e = E AND f = F))')
        
        node = parseq((
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
        node = parseq(
            (Q(a='A') & Q(b='B')) |
            (Q(c='C'))
        )
        self.assertEqual(unicode(node), '(c = C OR (a = A AND b = B))')
        
        node = parseq(Q(c='C') & (Q(a='A') | Q(b='B')))
        self.assertEqual(unicode(node), '((c = C) AND (a = A OR b = B))')


class RelatedFieldTests(BasePeeweeTestCase):
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
            ('INSERT INTO blog (title) VALUES (?)', ['a']),
            ('INSERT INTO entry (content,blog_id,pub_date,title) VALUES (?,?,?,?)', ['', a.id, None, 'e']),
        ])
        
        e2 = Entry.get(pk=e.pk)
        self.assertEqual(e2.blog, a)
        self.assertEqual(e2.blog, a)
        
        self.assertQueriesEqual([
            ('INSERT INTO blog (title) VALUES (?)', ['a']),
            ('INSERT INTO entry (content,blog_id,pub_date,title) VALUES (?,?,?,?)', ['', a.id, None, 'e']),
            ('SELECT * FROM entry WHERE pk = ? LIMIT 1 OFFSET 0', [e.pk]),
            ('SELECT * FROM blog WHERE id = ?', [a.id]),
        ])
    
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
    
    def test_multiple_in(self):
        sq = Blog.select().where(title__in=['a', 'b']).join(Entry).where(title__in=['c', 'd'], content='foo')
        self.assertSQLEqual(sq.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t1.title IN (?,?) AND (t2.content = ? AND t2.title IN (?,?))', ['a', 'b', 'foo', 'c', 'd']))

    def test_ordering_across_joins(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()
        b3 = self.create_entry(title='b3', blog=b)
        c = self.create_blog(title='c')
        c1 = self.create_entry(title='c1', blog=c)

        sq = Blog.select({
            Blog: ['*'],
            Entry: [peewee.Max('title', 'max_title')],
        }).join(Entry).order_by(peewee.desc('max_title')).group_by(Blog)
        import ipdb; ipdb.set_trace()
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


class FilterQueryTests(BasePeeweeTestCase):
    def test_filter_no_joins(self):
        query = Entry.filter(title='e1')
        self.assertSQLEqual(query.sql(), ('SELECT * FROM entry WHERE title = ?', ['e1']))
        
        query = Entry.filter(title__in=['e1', 'e2'])
        self.assertSQLEqual(query.sql(), ('SELECT * FROM entry WHERE title IN (?,?)', ['e1', 'e2']))
    
    def test_filter_missing_field(self):
        self.assertRaises(AttributeError, Entry.filter(missing='missing').sql)
        self.assertRaises(AttributeError, Entry.filter(blog__missing='missing').sql)
    
    def test_filter_joins(self):
        query = EntryTag.filter(entry__title='e1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entrytag AS t1 INNER JOIN entry AS t2 ON t1.entry_id = t2.pk WHERE t2.title = ?', ['e1']))
        
        query = EntryTag.filter(entry__title__in=['e1', 'e2'])
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entrytag AS t1 INNER JOIN entry AS t2 ON t1.entry_id = t2.pk WHERE t2.title IN (?,?)', ['e1', 'e2']))
        
        query = EntryTag.filter(entry__blog__title='b1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entrytag AS t1 INNER JOIN entry AS t2 ON t1.entry_id = t2.pk\nINNER JOIN blog AS t3 ON t2.blog_id = t3.id WHERE t3.title = ?', ['b1']))
        
        query = EntryTag.filter(entry__blog__title__in=['b1', 'b2'])
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entrytag AS t1 INNER JOIN entry AS t2 ON t1.entry_id = t2.pk\nINNER JOIN blog AS t3 ON t2.blog_id = t3.id WHERE t3.title IN (?,?)', ['b1', 'b2']))

        query = EntryTag.filter(entry__blog__title__in=['b1', 'b2'], entry__title='e1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entrytag AS t1 INNER JOIN entry AS t2 ON t1.entry_id = t2.pk\nINNER JOIN blog AS t3 ON t2.blog_id = t3.id WHERE t2.title = ? AND t3.title IN (?,?)', ['e1', 'b1', 'b2']))
    
        query = EntryTag.filter(entry__blog__title__in=['b1', 'b2'], entry__title='e1', tag='t1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entrytag AS t1 INNER JOIN entry AS t2 ON t1.entry_id = t2.pk\nINNER JOIN blog AS t3 ON t2.blog_id = t3.id WHERE t1.tag = ? AND t2.title = ? AND t3.title IN (?,?)', ['t1', 'e1', 'b1', 'b2']))
    
    def test_filter_reverse_joins(self):
        query = Blog.filter(entry_set__title='e1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t2.title = ?', ['e1']))
        
        query = Blog.filter(entry_set__title__in=['e1', 'e2'])
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t2.title IN (?,?)', ['e1', 'e2']))
        
        query = Blog.filter(entry_set__entrytag_set__tag='t1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id\nINNER JOIN entrytag AS t3 ON t2.pk = t3.entry_id WHERE t3.tag = ?', ['t1']))
        
        query = Blog.filter(entry_set__entrytag_set__tag__in=['t1', 't2'])
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id\nINNER JOIN entrytag AS t3 ON t2.pk = t3.entry_id WHERE t3.tag IN (?,?)', ['t1', 't2']))
        
        query = Blog.filter(entry_set__entrytag_set__tag__in=['t1', 't2'], entry_set__title='e1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id\nINNER JOIN entrytag AS t3 ON t2.pk = t3.entry_id WHERE t2.title = ? AND t3.tag IN (?,?)', ['e1', 't1', 't2']))
        
        query = Blog.filter(entry_set__entrytag_set__tag__in=['t1', 't2'], entry_set__title='e1', title='b1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id\nINNER JOIN entrytag AS t3 ON t2.pk = t3.entry_id WHERE t1.title = ? AND t2.title = ? AND t3.tag IN (?,?)', ['b1', 'e1', 't1', 't2']))
    
    def test_filter_multiple_lookups(self):
        query = Entry.filter(title='e1', pk=1)
        self.assertSQLEqual(query.sql(), ('SELECT * FROM entry WHERE (pk = ? AND title = ?)', [1, 'e1']))
        
        query = Entry.filter(title='e1', pk=1, blog__title='b1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.pk = ? AND t1.title = ?) AND t2.title = ?', [1, 'e1', 'b1']))
        
        query = Entry.filter(blog__id=2, title='e1', pk=1, blog__title='b1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.pk = ? AND t1.title = ?) AND (t2.id = ? AND t2.title = ?)', [1, 'e1', 2, 'b1']))
    
    def test_filter_with_q(self):
        query = Entry.filter(Q(title='e1') | Q(title='e2'))
        self.assertSQLEqual(query.sql(), ('SELECT * FROM entry WHERE (title = ? OR title = ?)', ['e1', 'e2']))
        
        query = Entry.filter(Q(title='e1') | Q(title='e2') | Q(title='e3'), Q(pk=1) | Q(pk=2))
        self.assertSQLEqual(query.sql(), ('SELECT * FROM entry WHERE (title = ? OR title = ? OR title = ?) AND (pk = ? OR pk = ?)', ['e1', 'e2', 'e3', 1, 2]))
        
        query = Entry.filter(Q(title='e1') | Q(title='e2'), pk=1)
        self.assertSQLEqual(query.sql(), ('SELECT * FROM entry WHERE (title = ? OR title = ?) AND pk = ?', ['e1', 'e2', 1]))
        
        # try with joins now
        query = Entry.filter(Q(blog__id=1) | Q(blog__id=2))
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t2.id = ? OR t2.id = ?)', [1, 2]))
        
        query = Entry.filter(Q(blog__id=1) | Q(blog__id=2) | Q(blog__id=3), Q(blog__title='b1') | Q(blog__title='b2'))
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t2.id = ? OR t2.id = ? OR t2.id = ?) AND (t2.title = ? OR t2.title = ?)', [1, 2, 3, 'b1', 'b2']))
        
        query = Entry.filter(Q(blog__id=1) | Q(blog__id=2) | Q(blog__id=3), Q(blog__title='b1') | Q(blog__title='b2'), title='foo')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t1.title = ? AND (t2.id = ? OR t2.id = ? OR t2.id = ?) AND (t2.title = ? OR t2.title = ?)', ['foo', 1, 2, 3, 'b1', 'b2']))
        
        query = Entry.filter(Q(blog__id=1) | Q(blog__id=2) | Q(blog__id=3), Q(blog__title='b1') | Q(blog__title='b2'), title='foo', blog__title='baz')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t1.title = ? AND (t2.id = ? OR t2.id = ? OR t2.id = ?) AND (t2.title = ? OR t2.title = ?) AND t2.title = ?', ['foo', 1, 2, 3, 'b1', 'b2', 'baz']))
        
        query = EntryTag.filter(Q(entry__blog__title='b1') | Q(entry__blog__title='b2'), Q(entry__pk=1) | Q(entry__pk=2), tag='baz', entry__title='e1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM entrytag AS t1 INNER JOIN entry AS t2 ON t1.entry_id = t2.pk\nINNER JOIN blog AS t3 ON t2.blog_id = t3.id WHERE t1.tag = ? AND (t2.pk = ? OR t2.pk = ?) AND t2.title = ? AND (t3.title = ? OR t3.title = ?)', ['baz', 1, 2, 'e1', 'b1', 'b2']))
    
    def test_filter_with_query(self):
        simple_query = User.select().where(active=True)
        
        query = filter_query(simple_query, username='bamples')
        self.assertSQLEqual(query.sql(), ('SELECT * FROM users WHERE active = ? AND username = ?', [1, 'bamples']))
        
        query = filter_query(simple_query, blog__title='b1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM users AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t1.active = ? AND t2.title = ?', [1, 'b1']))
        
        join_query = User.select().join(Blog).where(title='b1')
        
        query = filter_query(join_query, username='bamples')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM users AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t1.username = ? AND t2.title = ?', ['bamples', 'b1']))
        
        # join should be recycled here
        query = filter_query(join_query, blog__id=1)
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM users AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t2.title = ? AND t2.id = ?', ['b1', 1]))
        
        complex_query = User.select().join(Blog).where(Q(id=1)|Q(id=2))
        
        query = filter_query(complex_query, username='bamples', blog__title='b1')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM users AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t1.username = ? AND (t2.id = ? OR t2.id = ?) AND t2.title = ?', ['bamples', 1, 2, 'b1']))
        
        query = filter_query(complex_query, Q(blog__title='b1')|Q(blog__title='b2'), username='bamples')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM users AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t1.username = ? AND (t2.id = ? OR t2.id = ?) AND (t2.title = ? OR t2.title = ?)', ['bamples', 1, 2, 'b1', 'b2']))
        
        # zomg
        query = filter_query(complex_query, Q(blog__entry_set__title='e1')|Q(blog__entry_set__title='e2'), blog__title='b1', username='bamples')
        self.assertSQLEqual(query.sql(), ('SELECT t1.* FROM users AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id\nINNER JOIN entry AS t3 ON t2.id = t3.blog_id WHERE t1.username = ? AND (t2.id = ? OR t2.id = ?) AND t2.title = ? AND (t3.title = ? OR t3.title = ?)', ['bamples', 1, 2, 'b1', 'e1', 'e2']))
    
    def test_filter_chaining(self):
        simple_filter = Entry.filter(blog__id=1)
        self.assertSQLEqual(simple_filter.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t2.id = ?', [1]))
        
        f2 = simple_filter.filter(Q(blog__title='b1') | Q(blog__title='b2'), title='e1')
        self.assertSQLEqual(f2.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t1.title = ? AND t2.id = ? AND (t2.title = ? OR t2.title = ?)', ['e1', 1, 'b1', 'b2']))
    
    def test_filter_both_directions(self):
        f = Entry.filter(blog__title='b1', entrytag_set__tag='t1')
        self.assertSQLEqual(f.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN entrytag AS t2 ON t1.pk = t2.entry_id\nINNER JOIN blog AS t3 ON t1.blog_id = t3.id WHERE t2.tag = ? AND t3.title = ?', ['t1', 'b1']))


class AnnotateQueryTests(BasePeeweeTestCase):
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
            'SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id, t1.title ORDER BY count desc', []
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
            'SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 left outer JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id, t1.title ORDER BY count desc', []
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
            ('SELECT t1.*, COUNT(t2.id) AS count FROM blog AS t1 LEFT OUTER JOIN users AS t2 ON t1.id = t2.blog_id GROUP BY t1.id, t1.title ORDER BY count desc', [])
        ))
        
        self.assertEqual([(b, b.count) for b in annotated], [
            (blogs[0], 2),
            (blogs[1], 1),
            (blogs[2], 0),
        ])
    
    def test_limited_annotate(self):
        annotated = Blog.select('id').annotate(Entry)
        self.assertSQLEqual(annotated.sql(), (
            ('SELECT t1.id, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id', [])
        ))
        
        annotated = Blog.select(['id', 'xxx']).annotate(Entry)
        self.assertSQLEqual(annotated.sql(), (
            ('SELECT t1.id, t1.xxx, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id, t1.xxx', [])
        ))
        
        annotated = Blog.select({Blog: ['id']}).annotate(Entry)
        self.assertSQLEqual(annotated.sql(), (
            'SELECT t1.id, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id', []
        ))
    
    def test_annotate_with_where(self):
        blogs, entries, users = self.get_some_blogs()
        
        annotated = Blog.select().where(title='b2').annotate(Entry)
        self.assertSQLEqual(annotated.sql(), (
            'SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t1.title = ? GROUP BY t1.id, t1.title', ['b2']
        ))
        
        self.assertEqual([(b, b.count) for b in annotated], [
            (blogs[2], 5),
        ])
        
        # try with a join
        annotated = Blog.select().join(User).where(username='u2').annotate(Entry)
        self.assertSQLEqual(annotated.sql(), (
            'SELECT t1.*, COUNT(t3.pk) AS count FROM blog AS t1 INNER JOIN users AS t2 ON t1.id = t2.blog_id\nINNER JOIN entry AS t3 ON t1.id = t3.blog_id WHERE t2.username = ? GROUP BY t1.id, t1.title', ['u2']
        ))
        
        self.assertEqual([(b, b.count) for b in annotated], [
            (blogs[1], 4),
        ])
    
    def test_annotate_custom_aggregate(self):
        annotated = Blog.select().annotate(Entry, peewee.Max('pub_date', 'max_pub'))
        self.assertSQLEqual(annotated.sql(), (
            'SELECT t1.*, MAX(t2.pub_date) AS max_pub FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id, t1.title', []
        ))
        

class FieldTypeTests(BasePeeweeTestCase):
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
        
        null_lookup = NullModel.select().where(char_field__is=None)
        self.assertSQLEqual(null_lookup.sql(), ('SELECT * FROM nullmodel WHERE char_field IS NULL', []))
        
        self.assertEqual(list(null_lookup), [nm])
        
        non_null_lookup = NullModel.select().where(char_field='')
        self.assertSQLEqual(non_null_lookup.sql(), ('SELECT * FROM nullmodel WHERE char_field = ?', ['']))
        
        self.assertEqual(list(non_null_lookup), [])
        
        nm_from_db = NullModel.get(id=nm.id)
        self.assertEqual(nm_from_db.char_field, None)
        self.assertEqual(nm_from_db.text_field, None)
        self.assertEqual(nm_from_db.datetime_field, None)
        self.assertEqual(nm_from_db.int_field, None)
        self.assertEqual(nm_from_db.float_field, None)
        
        nm.char_field = ''
        nm.text_field = ''
        nm.int_field = 0
        nm.float_field = 0.0
        nm.save()
        
        nm_from_db = NullModel.get(id=nm.id)
        self.assertEqual(nm_from_db.char_field, '')
        self.assertEqual(nm_from_db.text_field, '')
        self.assertEqual(nm_from_db.datetime_field, None)
        self.assertEqual(nm_from_db.int_field, 0)
        self.assertEqual(nm_from_db.float_field, 0.0)
    
    def test_default_values(self):
        now = datetime.datetime.now() - datetime.timedelta(seconds=1)
        
        default_model = DefaultVals()
        
        # nothing is set until the model is saved
        self.assertEqual(default_model.published, None)
        self.assertEqual(default_model.pub_date, None)
        
        # saving the model will apply the defaults
        default_model.save()
        self.assertTrue(default_model.published)
        self.assertTrue(default_model.pub_date is not None)
        self.assertTrue(default_model.pub_date >= now)
        
        # overriding the defaults after initial save is fine
        default_model.pub_date = None
        default_model.save()
        self.assertEqual(default_model.pub_date, None)
        
        # ensure that the overridden default was propagated to the db
        from_db = DefaultVals.get(id=default_model.id)
        self.assertTrue(default_model.published)
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
        self.assertEqual(Entry._meta.fields['blog_id'].verbose_name, 'Blog')
        self.assertEqual(Entry._meta.fields['title'].verbose_name, 'Wacky title')

class ModelIndexTestCase(BasePeeweeTestCase):
    def setUp(self):
        super(ModelIndexTestCase, self).setUp()
        UniqueModel.drop_table(True)
        UniqueModel.create_table()
    
    def get_sorted_indexes(self, model):
        return test_db.get_indexes_for_table(model._meta.db_table)
    
    def check_postgresql_indexes(self, e, u):
        self.assertEqual(e, [
            ('entry_blog_id', False),
            ('entry_pk', False),
            ('entry_pkey', True),
        ])
        
        self.assertEqual(u, [
            ('users_active', False),
            ('users_blog_id', False),
            ('users_id', False),
            ('users_pkey', True),
        ])
    
    def check_sqlite_indexes(self, e, u):
        self.assertEqual(e, [
            ('entry_blog_id', False),
            ('entry_pk', True),
        ])
        
        self.assertEqual(u, [
            ('users_active', False),
            ('users_blog_id', False),
            ('users_id', True),
        ])
    
    def check_mysql_indexes(self, e, u):
        self.assertEqual(e, [
            ('PRIMARY', True),
            ('entry_blog_id', False),
            ('entry_pk', True),
        ])
        
        self.assertEqual(u, [
            ('PRIMARY', True),
            ('users_active', False),
            ('users_blog_id', False),
            ('users_id', True),
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


class ModelTablesTestCase(BasePeeweeTestCase):
    tables_might_not_be_there = ['defaultvals', 'nullmodel', 'uniquemodel']
    
    def test_tables_created(self):
        tables = test_db.get_tables()
        
        tables = [t for t in tables if t not in self.tables_might_not_be_there]
        
        self.assertEqual(tables, [
            'blog',
            'entry',
            'entrytag',
            'member',
            'membership',
            'relationship',
            'team',
            'users'
        ])
    
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


class ModelOptionsTest(BasePeeweeTestCase):
    def test_model_meta(self):
        self.assertEqual(Blog._meta.get_field_names(), ['id', 'title'])
        self.assertEqual(Entry._meta.get_field_names(), ['pk', 'title', 'content', 'pub_date', 'blog_id'])

        sorted_fields = list(Entry._meta.get_sorted_fields())
        self.assertEqual(sorted_fields, [
            ('pk', Entry._meta.fields['pk']),
            ('title', Entry._meta.fields['title']),
            ('content', Entry._meta.fields['content']),
            ('pub_date', Entry._meta.fields['pub_date']),
            ('blog_id', Entry._meta.fields['blog_id']),
        ])
        
        sorted_fields = list(Blog._meta.get_sorted_fields())
        self.assertEqual(sorted_fields, [
            ('id', Blog._meta.fields['id']),
            ('title', Blog._meta.fields['title']),
        ])
    
    def test_db_table(self):
        self.assertEqual(User._meta.db_table, 'users')
    
    def test_option_inheritance(self):
        test_db = peewee.Database(SqliteAdapter(), 'testing.db')
        child2_db = peewee.Database(SqliteAdapter(), 'child2.db')

        class ParentModel(peewee.Model):
            title = peewee.CharField()

            class Meta:
                database = test_db

        class ChildModel(ParentModel):
            pass

        class ChildModel2(ParentModel):
            class Meta:
                database = child2_db

        class GrandChildModel(ChildModel):
            pass

        class GrandChildModel2(ChildModel2):
            pass

        self.assertEqual(ParentModel._meta.database.database, 'testing.db')
        self.assertEqual(ParentModel._meta.model_class, ParentModel)

        self.assertEqual(ChildModel._meta.database.database, 'testing.db')
        self.assertEqual(ChildModel._meta.model_class, ChildModel)

        self.assertEqual(ChildModel2._meta.database.database, 'child2.db')
        self.assertEqual(ChildModel2._meta.model_class, ChildModel2)

        self.assertEqual(GrandChildModel._meta.database.database, 'testing.db')
        self.assertEqual(GrandChildModel._meta.model_class, GrandChildModel)

        self.assertEqual(GrandChildModel2._meta.database.database, 'child2.db')
        self.assertEqual(GrandChildModel2._meta.model_class, GrandChildModel2)


class ConcurrencyTestCase(BasePeeweeTestCase):
    def setUp(self):
        self._orig_db = test_db
        Blog._meta.database = database_class(database_name, threadlocals=True)
        BasePeeweeTestCase.setUp(self)
    
    def tearDown(self):
        Blog._meta.database = self._orig_db
        BasePeeweeTestCase.tearDown(self)
        
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
