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


class WeezModelTests(unittest.TestCase):
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
        
        dq = weez.DeleteQuery(Blog).where(title='b').execute()
        self.assertEqual(dq, 1)
        
        sq = weez.SelectQuery(Blog)
        self.assertEqual(sorted([o.title for o in sq.execute()]), ['a', 'c'])
        
        dq = weez.DeleteQuery(Blog).execute()
        self.assertEqual(dq, 2)
    
    def test_persistence(self):
        a = Blog(title='a')
        a.save()
        self.assertEqual(a.id, 1)
        
        b = Blog(title='b')
        b.save()
        self.assertEqual(b.id, 2)
        
        a.save()
        b.save()
        
        all_blogs = list(Blog._meta.select())
        self.assertEqual(len(all_blogs), 2)
