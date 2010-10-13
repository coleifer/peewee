peewee
======

fiddling around with an orm


model definitions and schema creation
-------------------------------------

smells like django::


    import peewee
    
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


gotta connect::

    >>> from peewee import database
    >>> database.connect()

create some tables::

    >>> Blog.create_table()
    >>> Entry.create_table()


foreign keys work like django's
-------------------------------

    >>> b = Blog(title="Peewee's Big Adventure")
    >>> b.save()
    >>> e = Entry(title="Greatest movie ever?", content="YES!", blog=b)
    >>> e.save()
    >>> e.blog
    <Blog: Peewee's Big Adventure>
    >>> for e in b.entry_set:
    ...     print e.title
    ... 
    Greatest movie ever?


bizarre querying
----------------

queries come in 4 flavors (select/update/insert/delete)::

    >>> for i in xrange(50):
    ...     b = Blog(title='blog-%d' % i)
    ...     b.save()
    ...     for j in xrange(i):
    ...         e = Entry(title='entry-%d' % j, blog=b)
    ...         e.save()
    ... 
    >>> [obj.title for obj in Blog.select().where(title__contains='0')]
    [u'blog-0', u'blog-10', u'blog-20', u'blog-30', u'blog-40']
    
    >>> [obj.title for obj in Blog.select().paginate(3, 10)]
    [u'blog-20', u'blog-21', u'blog-22', u'blog-23', u'blog-24',
     u'blog-25', u'blog-26', u'blog-27', u'blog-28', u'blog-29']
    
    >>> [obj.title for obj in Blog.select().join(Entry).where(title__contains='entry-45')]
    [u'blog-46', u'blog-47', u'blog-48', u'blog-49']
    
    >>> Blog.select().join(Entry).where(title__contains='entry-29').count()
    20

there's the notion of a *query context* which is the model being selected
or, if there is a join, the model being joined on.
