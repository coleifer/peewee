import datetime
import unittest

import peewee

# test models
class Blog(peewee.Model):
    title = peewee.CharField()
    
    def __unicode__(self):
        return self.title


class Entry(peewee.Model):
    title = peewee.CharField(max_length=50)
    content = peewee.TextField()
    pub_date = peewee.DateTimeField()
    blog = peewee.ForeignKeyField(Blog)
    
    def __unicode__(self):
        return '%s: %s' % (self.blog.title, self.title)


class EntryTag(peewee.Model):
    tag = peewee.CharField(max_length=50)
    entry = peewee.ForeignKeyField(Entry)
    
    def __unicode__(self):
        return self.tag


class BasePeeweeTestCase(unittest.TestCase):
    def setUp(self):
        peewee.database.create_table(Blog)
        peewee.database.create_table(Entry)
        peewee.database.create_table(EntryTag)
    
    def tearDown(self):
        peewee.database.drop_table(EntryTag)
        peewee.database.drop_table(Entry)
        peewee.database.drop_table(Blog)
    
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
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')
        
        sq = peewee.database.select(Blog, '*')
        self.assertEqual(sorted([o.id for o in sq.execute()]), [1, 2, 3])
        self.assertEqual(sorted([o.title for o in sq.execute()]), ['a', 'b', 'c'])
        
        sq = peewee.database.select(Blog, '*').where(title='a')
        self.assertEqual(sorted([o.id for o in sq.execute()]), [1])
        self.assertEqual(sorted([o.title for o in sq.execute()]), ['a'])
        
        sq = peewee.database.select(Blog, '*').where(title='a').where(id=1)
        self.assertEqual(sorted([o.id for o in sq.execute()]), [1])
        self.assertEqual(sorted([o.title for o in sq.execute()]), ['a'])
        
        sq = peewee.database.select(Blog, '*').where(title__in=['a', 'b'])
        self.assertEqual(sorted([o.id for o in sq.execute()]), [1, 2])
        self.assertEqual(sorted([o.title for o in sq.execute()]), ['a', 'b'])
    
    def test_selecting_across_joins(self):
        a = self.create_blog(title='a')
        a1 = self.create_entry(title='a1', content='a1', blog=a)
        a2 = self.create_entry(title='a2', content='a2', blog=a)
        
        b = self.create_blog(title='b')
        b1 = self.create_entry(title='b1', content='b1', blog=b)
        b2 = self.create_entry(title='b2', content='b2', blog=b)
        
        sq = peewee.database.select(Entry, '*').where(title='a1').join(Blog).where(title='a')
        
        self.assertEqual(sq._where, {
            Entry: {'title': '= "a1"'},
            Blog: {'title': '= "a"'}
        })
        self.assertEqual(sq._joins, [Blog])
        self.assertEqual(sq.sql(), 'SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t1.title = "a1" AND t2.title = "a"')
        
        self.assertEqual(list(sq), [a1])
        
        sq = peewee.database.select(Blog, '*').join(Entry).where(title='a1')
        
        self.assertEqual(sq._where, {
            Entry: {'title': '= "a1"'}
        })
        self.assertEqual(sq._joins, [Entry])
        
        self.assertEqual(list(sq), [a])
        
        t1 = self.create_entry_tag(tag='t1', entry=a2)
        t2 = self.create_entry_tag(tag='t2', entry=b2)
        
        sq = peewee.database.select(EntryTag, '*').join(Entry).join(Blog).where(title='a')
        
        self.assertEqual(sq._where, {
            Blog: {'title': '= "a"'}
        })
        self.assertEqual(sq._joins, [Entry, Blog])
        self.assertEqual(list(sq), [t1])
        
        sq = peewee.database.select(Blog, '*').join(Entry).join(EntryTag).where(tag='t2')
        self.assertEqual(list(sq), [b])
    
    def test_selecting_with_aggregation(self):
        a_id = peewee.database.insert(Blog, title='a').execute()
        b_id = peewee.database.insert(Blog, title='b').execute()
        
        peewee.database.insert(Entry, title='a1', blog_id=a_id).execute()
        peewee.database.insert(Entry, title='a2', blog_id=a_id).execute()
        peewee.database.insert(Entry, title='a3', blog_id=a_id).execute()
        peewee.database.insert(Entry, title='b1', blog_id=b_id).execute()

        sq = peewee.database.select(Blog, 't1.*, COUNT(t2.id) AS count').join(Entry).group_by('t1.id')
        a, b = list(sq)
        self.assertEqual(a.count, 3)
        self.assertEqual(b.count, 1)
        
        sq = sq.having('count > 2')
        self.assertEqual(list(sq), [a])
    
    def test_selecting_with_ordering(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')
        
        a1 = self.create_entry(title='a1', blog=a)
        a2 = self.create_entry(title='a2', blog=a)
        b1 = self.create_entry(title='b1', blog=b)
        b2 = self.create_entry(title='b2', blog=b)
        c1 = self.create_entry(title='c1', blog=c)
        
        sq = peewee.database.select(Blog).order_by('title')
        self.assertEqual(list(sq), [a, b, c])
        
        sq = peewee.database.select(Blog).order_by(peewee.desc('title'))
        self.assertEqual(list(sq), [c, b, a])
        
        sq = peewee.database.select(Entry).order_by(peewee.desc('title')).join(Blog).where(title='a')
        self.assertEqual(list(sq), [a2, a1])
        
        sq = peewee.database.select(Entry).order_by(peewee.desc('title')).join(Blog).order_by('title')
        self.assertEqual(list(sq), [c1, b2, b1, a2, a1])
    
    def test_insert(self):
        iq = peewee.database.insert(Blog, title='a')
        self.assertEqual(iq.sql(), 'INSERT INTO blog (title) VALUES ("a")')
        self.assertEqual(iq.execute(), 1)
        
        a = Blog.get(id=1)
        self.assertEqual(a.title, 'a')
        
        iq = peewee.database.insert(Blog, title='b')
        self.assertEqual(iq.execute(), 2)
        
        b = Blog.get(id=2)
        self.assertEqual(b.title, 'b')
    
    def test_update(self):
        iq = peewee.database.insert(Blog, title='a')
        a_id = iq.execute()
        a = Blog.get(id=a_id)
        self.assertEqual(a.title, 'a')
        
        uq = peewee.database.update(Blog, title='A').where(id=a_id)
        self.assertEqual(uq.sql(), 'UPDATE blog SET title="A" WHERE id = 1')
        
        uq.execute()
        a2 = Blog.get(id=a_id)
        self.assertEqual(a2.title, 'A')
    
    def test_delete(self):
        peewee.database.insert(Blog, title='a').execute()
        peewee.database.insert(Blog, title='b').execute()
        peewee.database.insert(Blog, title='c').execute()
        
        dq = peewee.database.delete(Blog).where(title='b')
        self.assertEqual(dq.sql(), 'DELETE FROM blog WHERE title = "b"')
        self.assertEqual(dq.execute(), 1)
        
        sq = peewee.database.select(Blog)
        self.assertEqual(sorted([o.title for o in sq.execute()]), ['a', 'c'])
        
        dq = peewee.database.delete(Blog).execute()
        self.assertEqual(dq, 2)
    
    def test_count(self):
        for i in xrange(10):
            self.create_blog(title='a%d' % i)
        
        count = peewee.database.select(Blog).count()
        self.assertEqual(count, 10)
        
        count = Blog.select().count()
        self.assertEqual(count, 10)
        
        for blog in peewee.database.select(Blog):
            for i in xrange(20):
                self.create_entry(title='entry%d' % i, blog=blog)
        
        count = peewee.database.select(Entry).count()
        self.assertEqual(count, 200)
        
        count = peewee.database.select(Entry).join(Blog).where(title="a0").count()
        self.assertEqual(count, 20)
        
        count = peewee.database.select(Entry).where(
            title__icontains="0"
        ).join(Blog).where(
            title="a5"
        ).count()
        self.assertEqual(count, 2)
    
    def test_pagination(self):
        for i in xrange(100):
            self.create_blog(title='%s' % i)
        
        first_page = peewee.database.select(Blog).paginate(1, 20)
        titles = [blog.title for blog in first_page]
        self.assertEqual(titles, map(str, range(20)))
        
        second_page = peewee.database.select(Blog).paginate(3, 30)
        titles = [blog.title for blog in second_page]
        self.assertEqual(titles, map(str, range(60, 90)))


class ModelTests(BasePeeweeTestCase):
    def test_model_save(self):
        a = self.create_blog(title='a')
        self.assertEqual(a.id, 1)
        
        b = self.create_blog(title='b')
        self.assertEqual(b.id, 2)
        
        a.save()
        b.save()
        
        all_blogs = list(Blog.select())
        self.assertEqual(len(all_blogs), 2)
    
    def test_model_get(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')
        
        b2 = Blog.get(title='b')
        self.assertEqual(b2.id, b.id)
    
    def test_model_select(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')
        
        results = []
        for obj in Blog.select():
            results.append(obj.title)
        
        self.assertEqual(sorted(results), ['a', 'b', 'c'])
        
        results = []
        for obj in Blog.select().where(title__in=['a', 'c']):
            results.append(obj.title)
        
        self.assertEqual(sorted(results), ['a', 'c'])


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
    
    def test_foreign_keys(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()
        
        self.assertEqual(a1.blog, a)
        self.assertNotEqual(a1.blog, b)
        
        self.assertEqual(a1.blog_id, a.id)
        self.assertEqual(a2.blog_id, a1.blog_id)
        
        self.assertEqual(b1.blog, b)
        self.assertNotEqual(b1.blog, a)
        
        self.assertEqual(t1.entry.blog, a)
        self.assertEqual(t2.entry.blog, b)
        
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
