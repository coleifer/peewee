from datetime import datetime
import unittest

import weez

# test models
class Blog(weez.Model):
    title = weez.CharField()
    
    def __unicode__(self):
        return self.title


class Entry(weez.Model):
    title = weez.CharField(max_length=50)
    content = weez.TextField()
    pub_date = weez.DateTimeField()
    blog = weez.ForeignKeyField(Blog)
    
    def __unicode__(self):
        return '%s: %s' % (self.blog.title, self.title)


class EntryTag(weez.Model):
    tag = weez.CharField(max_length=50)
    entry = weez.ForeignKeyField(Entry)
    
    def __unicode__(self):
        return self.tag


class BaseWeezTestCase(unittest.TestCase):
    def setUp(self):
        weez.database.create_table(Blog)
        weez.database.create_table(Entry)
        weez.database.create_table(EntryTag)
    
    def tearDown(self):
        weez.database.drop_table(EntryTag)
        weez.database.drop_table(Entry)
        weez.database.drop_table(Blog)
    
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


class QueryTests(BaseWeezTestCase):
    def test_select(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')
        
        sq = weez.SelectQuery(Blog, '*')
        self.assertEqual(sorted([o.id for o in sq.execute()]), [1, 2, 3])
        self.assertEqual(sorted([o.title for o in sq.execute()]), ['a', 'b', 'c'])
        
        sq = weez.SelectQuery(Blog, '*').where(title='a')
        self.assertEqual(sorted([o.id for o in sq.execute()]), [1])
        self.assertEqual(sorted([o.title for o in sq.execute()]), ['a'])
        
        sq = weez.SelectQuery(Blog, '*').where(title='a').where(id=1)
        self.assertEqual(sorted([o.id for o in sq.execute()]), [1])
        self.assertEqual(sorted([o.title for o in sq.execute()]), ['a'])
        
        sq = weez.SelectQuery(Blog, '*').where(title__in=['a', 'b'])
        self.assertEqual(sorted([o.id for o in sq.execute()]), [1, 2])
        self.assertEqual(sorted([o.title for o in sq.execute()]), ['a', 'b'])
    
    def test_insert(self):
        iq = weez.InsertQuery(Blog, title='a')
        self.assertEqual(iq.sql(), 'INSERT INTO blog (title) VALUES ("a")')
        self.assertEqual(iq.execute(), 1)
        
        a = Blog._meta.get(id=1)
        self.assertEqual(a.title, 'a')
        
        iq = weez.InsertQuery(Blog, title='b')
        self.assertEqual(iq.execute(), 2)
        
        b = Blog._meta.get(id=2)
        self.assertEqual(b.title, 'b')
    
    def test_update(self):
        iq = weez.InsertQuery(Blog, title='a')
        a_id = iq.execute()
        a = Blog._meta.get(id=a_id)
        self.assertEqual(a.title, 'a')
        
        uq = weez.UpdateQuery(Blog, title='A').where(id=a_id)
        self.assertEqual(uq.sql(), 'UPDATE blog SET title="A" WHERE id = 1')
        
        uq.execute()
        a2 = Blog._meta.get(id=a_id)
        self.assertEqual(a2.title, 'A')
    
    def test_delete(self):
        weez.InsertQuery(Blog, title='a').execute()
        weez.InsertQuery(Blog, title='b').execute()
        weez.InsertQuery(Blog, title='c').execute()
        
        dq = weez.DeleteQuery(Blog).where(title='b')
        self.assertEqual(dq.sql(), 'DELETE FROM blog WHERE title = "b"')
        self.assertEqual(dq.execute(), 1)
        
        sq = weez.SelectQuery(Blog)
        self.assertEqual(sorted([o.title for o in sq.execute()]), ['a', 'c'])
        
        dq = weez.DeleteQuery(Blog).execute()
        self.assertEqual(dq, 2)


class ModelTests(BaseWeezTestCase):
    def test_model_save(self):
        a = self.create_blog(title='a')
        self.assertEqual(a.id, 1)
        
        b = self.create_blog(title='b')
        self.assertEqual(b.id, 2)
        
        a.save()
        b.save()
        
        all_blogs = list(Blog._meta.select())
        self.assertEqual(len(all_blogs), 2)
    
    def test_model_get(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')
        
        b2 = Blog._meta.get(title='b')
        self.assertEqual(b2.id, b.id)
    
    def test_model_select(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')
        
        results = []
        for obj in Blog._meta.select():
            results.append(obj.title)
        
        self.assertEqual(sorted(results), ['a', 'b', 'c'])
        
        results = []
        for obj in Blog._meta.select().where(title__in=['a', 'c']):
            results.append(obj.title)
        
        self.assertEqual(sorted(results), ['a', 'c'])


class RelatedFieldTests(BaseWeezTestCase):
    def test_foreign_keys(self):
        a = self.create_blog(title='a')
        a1 = self.create_entry(title='a1', content='a1', blog=a)
        a2 = self.create_entry(title='a2', content='a2', blog=a)
        
        b = self.create_blog(title='b')
        b1 = self.create_entry(title='b1', content='b1', blog=b)
        b2 = self.create_entry(title='b2', content='b2', blog=b)
        
        self.assertEqual(a1.blog, a)
        self.assertNotEqual(a1.blog, b)
        
        self.assertEqual(a1.blog_id, a.id)
        self.assertEqual(a2.blog_id, a1.blog_id)
        
        self.assertEqual(b1.blog, b)
        self.assertNotEqual(b1.blog, a)
        
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
        a = self.create_blog(title='a')
        a1 = self.create_entry(title='a1', content='a1', blog=a)
        a2 = self.create_entry(title='a2', content='a2', blog=a)
        
        b = self.create_blog(title='b')
        b1 = self.create_entry(title='b1', content='b1', blog=b)
        b2 = self.create_entry(title='b2', content='b2', blog=b)
        
        results = []
        for entry in a.entry_set:
            results.append(entry.title)
        
        self.assertEqual(sorted(results), ['a1', 'a2'])
        
        results = []
        for entry in a.entry_set.where(title='a1'):
            results.append(entry.title)
        
        self.assertEqual(sorted(results), ['a1'])
    
    def test_querying_across_joins(self):
        a = self.create_blog(title='a')
        a1 = self.create_entry(title='a1', content='a1', blog=a)
        a2 = self.create_entry(title='a2', content='a2', blog=a)
        
        a1_tag1 = self.create_entry_tag(tag='a', entry=a1)
        a1_tag2 = self.create_entry_tag(tag='1', entry=a1)
        
        a2_tag1 = self.create_entry_tag(tag='a', entry=a2)
        a2_tag2 = self.create_entry_tag(tag='2', entry=a2)
        
        b = self.create_blog(title='b')
        b1 = self.create_entry(title='b1', content='b1', blog=b)
        b2 = self.create_entry(title='b2', content='b2', blog=b)
        
        b1_tag1 = self.create_entry_tag(tag='b', entry=b1)
        b1_tag2 = self.create_entry_tag(tag='1', entry=b1)
        
        b2_tag1 = self.create_entry_tag(tag='b', entry=b2)
        b2_tag2 = self.create_entry_tag(tag='2', entry=b2)

        sq = Blog._meta.select().where(title='a').join(Entry).where(title='a2')
        
        results = []
        for entry in sq:
            results.append(entry.title)
        
        self.assertEqual(results, ['a'])
        
        sq = Blog._meta.select().join(Entry).where(title='b2')
        
        results = []
        for entry in sq:
            results.append(entry.title)
        
        self.assertEqual(results, ['b'])
