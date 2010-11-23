peewee
======

a small orm

written to provide a lightweight querying interface over sql

uses sql concepts when querying, like joins, group by, having, etc.

pagination is handled for you automatically

Examples::

    # a simple query selecting a user
    User.select().where(username='charles')
    
    # get the tweets by a user named charles and order the newest to oldest
    Tweet.select().order_by(('pub_date', 'desc')).join(User).where(username='charles')
    
    # how many active users are there?
    User.select().where(active=True).count()
    
    # paginate the user table and show me page 3 (users 41-60)
    User.select().order_by(('username', 'asc')).paginate(3, 20)
    
    # order users by number of tweets
    User.select({
        User: ['*'],
        Tweet: [Count('id', 'num_tweets')]
    }).group_by('id').join(Tweet).order_by(('num_tweets', 'desc'))


what it doesn't do (yet?)
-------------------------

subqueries


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
