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
