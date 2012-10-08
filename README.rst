.. image:: http://i.imgur.com/zhcoT.png

peewee
======

* a small orm
* written in python
* provides a lightweight querying interface over sql
* uses sql concepts when querying, like joins and where clauses
* supports sqlite, mysql and postgresql
* support for special extensions like `hstore <http://peewee.readthedocs.org/en/latest/peewee/playhouse.html#postgresql-extensions-hstore-ltree>`_ and `full-text search <http://peewee.readthedocs.org/en/latest/peewee/playhouse.html#full-text-search>`_

For flask integration, including an admin interface and RESTful API, check
out `flask-peewee <https://github.com/coleifer/flask-peewee/>`_.

For notes on the upgrade from 1.0 to 2.0, check out `the upgrade docs <http://peewee.readthedocs.org/en/latest/peewee/upgrading.html>`_.

Examples::

    # a simple query selecting a user
    User.get(User.username == 'charles')

    # get the staff and super users
    editors = User.select().where(
        (User.is_staff == True) |
        (User.is_superuser == True)
    )

    # get tweets by editors ("<<" maps to IN)
    Tweet.select().where(Tweet.user << editors)

    # how many active users are there?
    User.select().where(User.active == True).count()

    # paginate the user table and show me page 3 (users 41-60)
    User.select().order_by(User.username).paginate(3, 20)

    # order users by number of tweets
    User.select().annotate(Tweet).order_by(
        fn.Count(Tweet.id).desc()
    )

    # a similar way of expressing the same
    User.select(
        User, fn.Count(Tweet.id).alias('ct')
    ).join(Tweet).group_by(User).order_by(R('ct desc'))

    # do an atomic update
    Counter.update(count=Counter.count + 1).where(
        Counter.url == request.url
    )


Learning more
-------------

the official `peewee cookbook <http://peewee.readthedocs.org/en/latest/peewee/cookbook.html>`_
has recipes for common operations and is a good place to get started.

check the `documentation <http://peewee.readthedocs.org/>`_ for more
examples.

specific question?  come hang out in the #peewee channel on freenode.irc.net,
or post to the mailing list, http://groups.google.com/group/peewee-orm

lastly, peewee runs on python 2.5 or greater, though there is currently no
support for python3

Still want more info?
---------------------

.. image:: http://media.charlesleifer.com/blog/photos/wat.jpg



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

    User.select().where(User.active == True).order_by(User.username)

since User is the model being selected, the where clause and the order_by will
pertain to attributes on the User model.  User is the current query context
when the .where() and .order_by() are evaluated.

an example using joins::

    Tweet.select().join(User).where(
        (Tweet.deleted == False) & (User.active == True)
    ).order_by(Tweet.pub_date.desc())

this will select non-deleted tweets from active users.


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
