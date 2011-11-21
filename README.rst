.. image:: http://charlesleifer.com/media/images/peewee-transparent.png

peewee
======

* a small orm
* written in python
* provides a lightweight querying interface over sql
* uses sql concepts when querying, like joins and where clauses
* supports sqlite, mysql and postgresql


Examples::

    # a simple query selecting a user
    User.get(username='charles')
    
    # get the staff and super users
    editors = User.select().where(Q(is_staff=True) | Q(is_superuser=True))
    
    # get tweets by editors
    Tweet.select().where(user__in=editors)
    
    # how many active users are there?
    User.select().where(active=True).count()
    
    # paginate the user table and show me page 3 (users 41-60)
    User.select().order_by(('username', 'asc')).paginate(3, 20)
    
    # order users by number of tweets
    User.select().annotate(Tweet).order_by(('count', 'desc'))
    
    # another way of expressing the same
    User.select({
        User: ['*'],
        Tweet: [Count('id', 'count')]
    }).group_by('id').join(Tweet).order_by(('count', 'desc'))


You can use django-style syntax to create select queries::

    # how many active users are there?
    User.filter(active=True).count()
    
    # get tweets by a specific user
    Tweet.filter(user__username='charlie')
    
    # get tweets by editors
    Tweet.filter(Q(user__is_staff=True) | Q(user__is_superuser=True))


check the `documentation <http://charlesleifer.com/docs/peewee/>`_ for more
examples.

specific question?  come hang out in the #peewee channel on freenode.irc.net,
or post to the mailing list, http://groups.google.com/group/peewee-orm


Why?
----

peewee began when I was working on a small app in flask and found myself writing
lots of queries and wanting a very simple abstraction on top of the sql.  I had
so much fun working on it that I kept adding features.  My goal has always been,
though, to keep the implementation incredibly simple.  I've made a couple dives
into django's orm but have never come away with a deep understanding of its
implementation.  peewee is small enough that its my hope anyone with an interest
in orms will be able to understand the code without too much trouble.


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


querying
--------

queries come in 4 flavors (select/update/insert/delete).

there's the notion of a *query context* which is the model being selected
or joined on::

    User.select().where(active=True).order_by(('username', 'asc'))

since User is the model being selected, the where clause and the order_by will
pertain to attributes on the User model.  User is the current query context
when the .where() and .order_by() are evaluated.

an example using joins::

    Tweet.select().where(deleted=False).order_by(('pub_date', 'desc')).join(
        User
    ).where(active=True)

this will select non-deleted tweets from active users.  the first .where() and
.order_by() occur when Tweet is the current *query context*.  As soon as the
join is evaluated, User becomes the *query context* and so the following
where() pertains to the User model.


now with q objects
------------------

for users familiar with django's orm, I've implemented OR queries and complex
query nesting using similar notation::

    User.select().where(
        Q(is_superuser = True) |
        Q(is_staff = True)
    )

    SomeModel.select().where(
        (Q(a='A') | Q(b='B')) &
        (Q(c='C') | Q(d='D'))
    )

    # generates something like:
    # SELECT * FROM some_obj 
    # WHERE ((a = "A" OR b = "B") AND (c = "C" OR d = "D"))


using sqlite
------------

::

    import peewee

    database = peewee.SqliteDatabase('my.db')

    class BaseModel(peewee.Model):
        class Meta:
            database = database

    class Blog(BaseModel):
        creator = peewee.CharField()
        name = peewee.CharField()
        
    class Entry(BaseModel):
        creator = peewee.CharField()
        name = peewee.CharField()


using postgresql
----------------

you can now use postgresql::

    import peewee

    database = peewee.PostgresqlDatabase('my_db', user='root')

    class BaseModel(peewee.Model):
        class Meta:
            database = database

    # ... same as above sqlite example ...


using mysql
-----------

you can now use MySQL::

    import peewee

    database = peewee.MySQLDatabase('my_db', user='root')

    class BaseModel(peewee.Model):
        class Meta:
            database = database

    # ... same as above sqlite example ...
