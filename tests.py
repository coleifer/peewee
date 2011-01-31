import datetime
import logging
import unittest

import peewee
from peewee import (SelectQuery, InsertQuery, UpdateQuery, DeleteQuery, Node, 
        Q, database, parseq, SqliteAdapter)


class QueryLogHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        self.queries = []
        logging.Handler.__init__(self, *args, **kwargs)
        
    def emit(self, record):
        self.queries.append(record)


# test models
class Blog(peewee.Model):
    title = peewee.CharField()
    
    def __unicode__(self):
        return self.title


class Entry(peewee.Model):
    pk = peewee.PrimaryKeyField()
    title = peewee.CharField(max_length=50)
    content = peewee.TextField()
    pub_date = peewee.DateTimeField(null=True)
    blog = peewee.ForeignKeyField(Blog)
    
    def __unicode__(self):
        return '%s: %s' % (self.blog.title, self.title)


class EntryTag(peewee.Model):
    tag = peewee.CharField(max_length=50)
    entry = peewee.ForeignKeyField(Entry)
    
    def __unicode__(self):
        return self.tag


class User(peewee.Model):
    username = peewee.CharField(max_length=50)
    blog = peewee.ForeignKeyField(Blog, null=True)
    active = peewee.BooleanField(db_index=True)

    def __unicode__(self):
        return self.username


class Relationship(peewee.Model):
    from_user = peewee.ForeignKeyField(User, related_name='relationships')
    to_user = peewee.ForeignKeyField(User, related_name='related_to')


class NullModel(peewee.Model):
    char_field = peewee.CharField(null=True)
    text_field = peewee.TextField(null=True)
    datetime_field = peewee.DateTimeField(null=True)
    int_field = peewee.IntegerField(null=True)
    float_field = peewee.FloatField(null=True)

class Team(peewee.Model):
    name = peewee.CharField()

class Member(peewee.Model):
    username = peewee.CharField()

class Membership(peewee.Model):
    team = peewee.ForeignKeyField(Team)
    member = peewee.ForeignKeyField(Member)


class BasePeeweeTestCase(unittest.TestCase):
    def setUp(self):
        database.connect()
        Blog.create_table()
        Entry.create_table()
        EntryTag.create_table()
        User.create_table()
        Relationship.create_table()
        NullModel.create_table()
        Team.create_table()
        Member.create_table()
        Membership.create_table()
        
        self.qh = QueryLogHandler()
        peewee.logger.setLevel(logging.DEBUG)
        peewee.logger.addHandler(self.qh)
    
    def tearDown(self):
        peewee.logger.removeHandler(self.qh)
        
        Membership.drop_table()
        Member.drop_table()
        Team.drop_table()
        NullModel.drop_table()
        Relationship.drop_table()
        User.drop_table()
        EntryTag.drop_table()
        Entry.drop_table()
        Blog.drop_table()
        database.close()
    
    def queries(self):
        return [x.msg for x in self.qh.queries]
    
    def assertQueriesEqual(self, queries):
        self.assertEqual(queries, self.queries())
    
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
    def test_select(self):
        sq = SelectQuery(Blog, '*')
        self.assertEqual(sq.sql(), ('SELECT * FROM blog', []))

        sq = SelectQuery(Blog, '*').where(title='a')
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE title = ?', ['a']))
        
        sq = SelectQuery(Blog, '*').where(title='a', id=1)
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (id = ? AND title = ?)', [1, 'a']))
        
        # check that chaining works as expected
        sq = SelectQuery(Blog, '*').where(title='a').where(id=1)
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE title = ? AND id = ?', ['a', 1]))
        
        # check that IN query special-case works
        sq = SelectQuery(Blog, '*').where(title__in=['a', 'b'])
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE title IN (?,?)', ['a', 'b']))
    
    def test_select_with_q(self):
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1))
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?)', ['a', 1]))
        
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1) | Q(id=3))
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ? OR id = ?)', ['a', 1, 3]))
        
        # test simple chaining
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where(Q(id=3))
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?) AND id = ?', ['a', 1, 3]))
        
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where(id=3)
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?) AND id = ?', ['a', 1, 3]))
        
        # test chaining with Q objects
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where((Q(title='c') | Q(id=3)))
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?) AND (title = ? OR id = ?)', ['a', 1, 'c', 3]))

        # test mixing it all up
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where((Q(title='c') | Q(id=3)), title='b')
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?) AND (title = ? OR id = ?) AND title = ?', ['a', 1, 'c', 3, 'b']))

    def test_select_with_negation(self):
        sq = SelectQuery(Blog, '*').where(~Q(title='a'))
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE NOT title = ?', ['a']))
        
        sq = SelectQuery(Blog, '*').where(~Q(title='a') | Q(title='b'))
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (NOT title = ? OR title = ?)', ['a', 'b']))
        
        sq = SelectQuery(Blog, '*').where(~Q(title='a') | ~Q(title='b'))
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (NOT title = ? OR NOT title = ?)', ['a', 'b']))
        
        sq = SelectQuery(Blog, '*').where(~(Q(title='a') | Q(title='b')))
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (NOT (title = ? OR title = ?))', ['a', 'b']))
        
        # chaining?
        sq = SelectQuery(Blog, '*').where(~(Q(title='a') | Q(id=1))).where(Q(id=3))
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (NOT (title = ? OR id = ?)) AND id = ?', ['a', 1, 3]))
        
        # mix n'match?
        sq = SelectQuery(Blog, '*').where(Q(title='a') | Q(id=1)).where(~(Q(title='c') | Q(id=3)), title='b')
        self.assertEqual(sq.sql(), ('SELECT * FROM blog WHERE (title = ? OR id = ?) AND (NOT (title = ? OR id = ?)) AND title = ?', ['a', 1, 'c', 3, 'b']))

    def test_select_with_models(self):
        sq = SelectQuery(Blog, {Blog: '*'})
        self.assertEqual(sq.sql(), ('SELECT * FROM blog', []))

        sq = SelectQuery(Blog, {Blog: ['title', 'id']})
        self.assertEqual(sq.sql(), ('SELECT title, id FROM blog', []))
    
        sq = SelectQuery(Blog, {Blog: ['title', 'id']}).join(Entry)
        self.assertEqual(sq.sql(), ('SELECT t1.title, t1.id FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id', []))

        sq = SelectQuery(Blog, {Blog: ['title', 'id'], Entry: [peewee.Count('pk')]}).join(Entry)
        self.assertEqual(sq.sql(), ('SELECT t1.title, t1.id, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id', []))

        sq = SelectQuery(Blog, {Blog: ['title', 'id'], Entry: [peewee.Max('pk')]}).join(Entry)
        self.assertEqual(sq.sql(), ('SELECT t1.title, t1.id, MAX(t2.pk) AS max FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id', []))

    def test_selecting_across_joins(self):
        sq = SelectQuery(Entry, '*').where(title='a1').join(Blog).where(title='a')
        self.assertEqual(sq._joins, [(Blog, None, None)])
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t1.title = ? AND t2.title = ?', ['a1', 'a']))
        
        sq = SelectQuery(Blog, '*').join(Entry).where(title='a1')        
        self.assertEqual(sq._joins, [(Entry, None, None)])
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t2.title = ?', ['a1']))

        sq = SelectQuery(EntryTag, '*').join(Entry).join(Blog).where(title='a')        
        self.assertEqual(sq._joins, [(Entry, None, None), (Blog, None, None)])
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM entrytag AS t1 INNER JOIN entry AS t2 ON t1.entry_id = t2.pk\nINNER JOIN blog AS t3 ON t2.blog_id = t3.id WHERE t3.title = ?', ['a']))
        
        sq = SelectQuery(Blog, '*').join(Entry).join(EntryTag).where(tag='t2')
        self.assertEqual(sq._joins, [(Entry, None, None), (EntryTag, None, None)])
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id\nINNER JOIN entrytag AS t3 ON t2.pk = t3.entry_id WHERE t3.tag = ?', ['t2']))
    
    def test_selecting_across_joins_with_q(self):
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).join(Blog).where(title='e')
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ?) AND t2.title = ?', ['a', 1, 'e']))
        
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1) | Q(title='b')).join(Blog).where(title='e')
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ? OR t1.title = ?) AND t2.title = ?', ['a', 1, 'b', 'e']))

        # test simple chaining
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).where(Q(title='b')).join(Blog).where(title='e')
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ?) AND t1.title = ? AND t2.title = ?', ['a', 1, 'b', 'e']))
        
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).where(title='b').join(Blog).where(title='e')
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ?) AND t1.title = ? AND t2.title = ?', ['a', 1, 'b', 'e']))

        # test q on both models
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).join(Blog).where(Q(title='e') | Q(id=2))
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ?) AND (t2.title = ? OR t2.id = ?)', ['a', 1, 'e', 2]))
    
        # test q on both with nesting
        sq = SelectQuery(Entry, '*').where(Q(title='a') | Q(pk=1)).join(Blog).where((Q(title='e') | Q(id=2)) & (Q(title='f') | Q(id=3)))
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE (t1.title = ? OR t1.pk = ?) AND ((t2.title = ? OR t2.id = ?) AND (t2.title = ? OR t2.id = ?))', ['a', 1, 'e', 2, 'f', 3]))

    def test_selecting_with_switching(self):
        sq = SelectQuery(Blog, '*').join(Entry).switch(Blog).where(title='a')
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t1.title = ?', ['a']))
    
    def test_selecting_with_aggregation(self):
        sq = SelectQuery(Blog, 't1.*, COUNT(t2.pk) AS count').group_by('id').join(Entry)
        self.assertEqual(sq._where, {})
        self.assertEqual(sq._joins, [(Entry, None, None)])
        self.assertEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id', []))
        
        sq = sq.having('count > 2')
        self.assertEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id HAVING count > 2', []))
        
        sq = SelectQuery(Blog, {
            Blog: ['*'],
            Entry: [peewee.Count('pk')]
        }).group_by('id').join(Entry)
        self.assertEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id', []))
        
        sq = sq.having('count > 2')
        self.assertEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id HAVING count > 2', []))
        
        sq = sq.order_by(('count', 'desc'))
        self.assertEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id HAVING count > 2 ORDER BY count desc', []))
    
    def test_selecting_with_ordering(self):        
        sq = SelectQuery(Blog).order_by('title')
        self.assertEqual(sq.sql(), ('SELECT * FROM blog ORDER BY title ASC', []))
        
        sq = SelectQuery(Blog).order_by(peewee.desc('title'))
        self.assertEqual(sq.sql(), ('SELECT * FROM blog ORDER BY title DESC', []))
        
        sq = SelectQuery(Entry).order_by(peewee.desc('title')).join(Blog).where(title='a')
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t2.title = ? ORDER BY t1.title DESC', ['a']))
        
        sq = SelectQuery(Entry).join(Blog).order_by(peewee.desc('title'))
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id ORDER BY t2.title DESC', []))

    def test_ordering_on_aggregates(self):
        sq = SelectQuery(
            Blog, 't1.*, COUNT(t2.pk) as count'
        ).join(Entry).order_by(peewee.desc('count'))
        self.assertEqual(sq.sql(), ('SELECT t1.*, COUNT(t2.pk) as count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id ORDER BY count DESC', []))

    def test_insert(self):
        iq = InsertQuery(Blog, title='a')
        self.assertEqual(iq.sql(), ('INSERT INTO blog (title) VALUES (?)', ['a']))
        self.assertEqual(iq.execute(), 1)
        
        iq = InsertQuery(Blog, title='b')
        self.assertEqual(iq.sql(), ('INSERT INTO blog (title) VALUES (?)', ['b']))
        self.assertEqual(iq.execute(), 2)
    
    def test_update(self):
        iq = InsertQuery(Blog, title='a').execute()
        
        uq = UpdateQuery(Blog, title='A').where(id=1)
        self.assertEqual(uq.sql(), ('UPDATE blog SET title=? WHERE id = ?', ['A', 1]))
        self.assertEqual(uq.execute(), 1)
        
        iq2 = InsertQuery(Blog, title='b').execute()
        
        uq = UpdateQuery(Blog, title='B').where(id=2)
        self.assertEqual(uq.sql(), ('UPDATE blog SET title=? WHERE id = ?', ['B', 2]))
        self.assertEqual(uq.execute(), 1)
        
        sq = SelectQuery(Blog).order_by('id')
        self.assertEqual([x.title for x in sq], ['A', 'B'])
    
    def test_update_with_q(self):
        uq = UpdateQuery(Blog, title='A').where(Q(id=1))
        self.assertEqual(uq.sql(), ('UPDATE blog SET title=? WHERE id = ?', ['A', 1]))
        
        uq = UpdateQuery(Blog, title='A').where(Q(id=1) | Q(id=3))
        self.assertEqual(uq.sql(), ('UPDATE blog SET title=? WHERE (id = ? OR id = ?)', ['A', 1, 3]))
    
    def test_delete(self):
        InsertQuery(Blog, title='a').execute()
        InsertQuery(Blog, title='b').execute()
        InsertQuery(Blog, title='c').execute()
        
        dq = DeleteQuery(Blog).where(title='b')
        self.assertEqual(dq.sql(), ('DELETE FROM blog WHERE title = ?', ['b']))
        self.assertEqual(dq.execute(), 1)
        
        sq = SelectQuery(Blog).order_by('id')
        self.assertEqual([x.title for x in sq], ['a', 'c'])
        
        dq = DeleteQuery(Blog)
        self.assertEqual(dq.sql(), ('DELETE FROM blog', []))
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
        sq = SelectQuery(Blog).paginate(1, 20)
        self.assertEqual(sq.sql(), ('SELECT * FROM blog LIMIT 20 OFFSET 0', []))
        
        sq = SelectQuery(Blog).paginate(3, 30)
        self.assertEqual(sq.sql(), ('SELECT * FROM blog LIMIT 30 OFFSET 60', []))
    
    def test_inner_joins(self):
        sql = SelectQuery(Blog).join(Entry).sql()
        self.assertEqual(sql, ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id', []))
        
        sql = SelectQuery(Entry).join(Blog).sql()
        self.assertEqual(sql, ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id', []))

    def test_outer_joins(self):
        sql = SelectQuery(User).join(Blog).sql()
        self.assertEqual(sql, ('SELECT t1.* FROM user AS t1 LEFT OUTER JOIN blog AS t2 ON t1.blog_id = t2.id', []))
        
        sql = SelectQuery(Blog).join(User).sql()
        self.assertEqual(sql, ('SELECT t1.* FROM blog AS t1 LEFT OUTER JOIN user AS t2 ON t1.id = t2.blog_id', []))


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
        
        self.assertFalse(sq._dirty)

        blogs = [b for b in sq]
        self.assertEqual(blogs, [a, b])
        self.assertEqual(len(self.queries()), 3)
        
        # mark dirty
        sq = sq.where(title='a')
        self.assertTrue(sq._dirty)
        
        blogs = [b for b in sq]
        self.assertEqual(blogs, [a])
        
        self.assertQueriesEqual([
            ('INSERT INTO blog (title) VALUES (?)', ['a']),
            ('INSERT INTO blog (title) VALUES (?)', ['b']),
            ('SELECT * FROM blog ORDER BY title ASC', []),
            ('SELECT * FROM blog WHERE title = ? ORDER BY title ASC', ['a']),
        ])
        
        blogs = [b for b in sq]
        self.assertEqual(blogs, [a])
        
        self.assertEqual(len(self.queries()), 4)
    
    def test_create(self):
        u = User.create(username='a')
        self.assertEqual(u.username, 'a')
        self.assertQueriesEqual([
            ('INSERT INTO user (username,active,blog_id) VALUES (?,?,?)', ['a', 0, None]),
        ])

        b = Blog.create(title='b blog')
        u2 = User.create(username='b', blog=b)
        self.assertEqual(u2.blog, b)

        self.assertQueriesEqual([
            ('INSERT INTO user (username,active,blog_id) VALUES (?,?,?)', ['a', 0, None]),
            ('INSERT INTO blog (title) VALUES (?)', ['b blog']),
            ('INSERT INTO user (username,active,blog_id) VALUES (?,?,?)', ['b', 0, b.id]),
        ])

    def test_get_or_create(self):
        u = User.get_or_create(username='a')
        self.assertEqual(u.username, 'a')
        self.assertQueriesEqual([
            ('SELECT * FROM user WHERE username = ? LIMIT 1 OFFSET 0', ['a']),
            ('INSERT INTO user (username,active,blog_id) VALUES (?,?,?)', ['a', 0, None]),
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
        
        sq = Blog.select().join(Entry).join(EntryTag).where(tag='t1')
        self.assertEqual(list(sq), [a])
        
        sq = Blog.select().join(Entry).join(EntryTag).where(tag='t2')
        self.assertEqual(list(sq), [b])
        
        sq = Blog.select().join(Entry).where(title='a1').join(EntryTag).where(tag='t1')
        self.assertEqual(list(sq), [])
        
        sq = Blog.select().join(Entry).where(title='a2').join(EntryTag).where(tag='t1')
        self.assertEqual(list(sq), [a])
        
        sq = EntryTag.select().join(Entry).join(Blog).where(title='a')
        self.assertEqual(list(sq), [t1])
        
        sq = EntryTag.select().join(Entry).join(Blog).where(title='b')
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
    
    def test_multiple_in(self):
        sq = Blog.select().where(title__in=['a', 'b']).join(Entry).where(title__in=['c', 'd'], content='foo')
        self.assertEqual(sq.sql(), ('SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t1.title IN (?,?) AND (t2.content = ? AND t2.title IN (?,?))', ['a', 'b', 'foo', 'c', 'd']))

    def test_ordering_across_joins(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()
        b3 = self.create_entry(title='b3', blog=b)
        c = self.create_blog(title='c')
        c1 = self.create_entry(title='c1', blog=c)

        sq = Blog.select().join(Entry).order_by(peewee.desc('title')).group_by('blog_id')
        self.assertEqual(list(sq), [c, b, a])
        
        sq = Blog.select().join(Entry).order_by(peewee.desc('title')).distinct()
        self.assertEqual(list(sq), [c, b, a])

        sq = Blog.select().where(title__in=['a', 'b']).join(Entry).order_by(peewee.desc('title')).group_by('blog_id')
        self.assertEqual(list(sq), [b, a])
        
        sq = Blog.select().where(title__in=['a', 'b']).join(Entry).order_by(peewee.desc('title')).distinct()
        self.assertEqual(list(sq), [b, a])

        sq = Blog.select('t1.*, COUNT(t2.pk) AS count').join(Entry).order_by(peewee.desc('count')).group_by('blog_id')
        qr = list(sq)

        self.assertEqual(qr, [b, a, c])
        self.assertEqual(qr[0].count, 3)
        self.assertEqual(qr[1].count, 2)
        self.assertEqual(qr[2].count, 1)
        
        sq = Blog.select({
            Blog: ['*'],
            Entry: [peewee.Count('pk', 'count')]
        }).join(Entry).group_by('blog_id').order_by(peewee.desc('count'))
        qr = list(sq)
        
        self.assertEqual(qr, [b, a, c])
        self.assertEqual(qr[0].count, 3)
        self.assertEqual(qr[1].count, 2)
        self.assertEqual(qr[2].count, 1)
    
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
        }).join(User).group_by('blog_id').order_by(peewee.desc('count'))
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
        
        a_member1 = Member.create(username='a1')
        a_member2 = Member.create(username='a2')
        
        b_member1 = Member.create(username='b1')
        b_member2 = Member.create(username='b2')
        
        ab_member = Member.create(username='ab')
        
        Membership.create(team=a_team, member=a_member1)
        Membership.create(team=a_team, member=a_member2)
        
        Membership.create(team=b_team, member=b_member1)
        Membership.create(team=b_team, member=b_member2)
        
        Membership.create(team=a_team, member=ab_member)
        Membership.create(team=b_team, member=ab_member)
        
        a_team_members = Member.select().join(Membership).where(team=a_team)
        self.assertEqual(list(a_team_members), [a_member1, a_member2, ab_member])
        
        b_team_members = Member.select().join(Membership).where(team=b_team)
        self.assertEqual(list(b_team_members), [b_member1, b_member2, ab_member])
        
        a_member_teams = Team.select().join(Membership).where(member=a_member1)
        self.assertEqual(list(a_member_teams), [a_team])
        
        ab_member_teams = Team.select().join(Membership).where(member=ab_member)
        self.assertEqual(list(ab_member_teams), [a_team, b_team])


class FieldTypeTests(BasePeeweeTestCase):
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
        self.assertEqual(null_lookup.sql(), ('SELECT * FROM nullmodel WHERE char_field IS NULL', []))
        
        self.assertEqual(list(null_lookup), [nm])
        
        non_null_lookup = NullModel.select().where(char_field='')
        self.assertEqual(non_null_lookup.sql(), ('SELECT * FROM nullmodel WHERE char_field = ?', ['']))
        
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
    
    def get_sorted_indexes(self, model):
        res = database.execute('PRAGMA index_list(%s);' % model._meta.db_table)
        rows = sorted([r[1:] for r in res.fetchall()])
        return rows
    
    def test_primary_key_index(self):
        entry_indexes = self.get_sorted_indexes(Entry)
        self.assertEqual(entry_indexes, [
            ('entry_blog_id', 0),
            ('entry_pk', 1),
        ])
        
        user_indexes = self.get_sorted_indexes(User)
        self.assertEqual(user_indexes, [
            ('user_active', 0),
            ('user_blog_id', 0),
            ('user_id', 1),
        ])


class ModelOptionsTest(BasePeeweeTestCase):
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
