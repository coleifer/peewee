.. image:: http://i.imgur.com/zhcoT.png

peewee
======

* a small, expressive orm
* written in python (2.6+, 3.2+)
* built-in support for sqlite, mysql and postgresql and special extensions like `hstore <http://peewee.readthedocs.org/en/latest/peewee/playhouse.html#postgresql-hstore>`_

.. image:: https://api.travis-ci.org/coleifer/peewee.png?branch=master
  :target: https://travis-ci.org/coleifer/peewee

For flask integration, including an admin interface and RESTful API, check
out `flask-peewee <https://github.com/coleifer/flask-peewee/>`_.

For notes on the upgrade from 1.0 to 2.0, check out `the upgrade docs <http://peewee.readthedocs.org/en/latest/peewee/upgrading.html>`_.

Check out the `quickstart IPython notebook <http://nbviewer.ipython.org/d3faf30bbff67ce5f70c>`_.

Example queries::

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
    tweet_ct = fn.Count(Tweet.id)
    (User
      .select(User, tweet_ct.alias('ct'))
      .join(Tweet)
      .group_by(User)
      .order_by(tweet_ct.desc()))

    # do an atomic update
    Counter.update(count=Counter.count + 1).where(
        Counter.url == request.url
    )


Check out the `quick start <http://peewee.readthedocs.org/en/latest/peewee/quickstart.html>`_ for more!


Learning more
-------------

the official `peewee cookbook <http://peewee.readthedocs.org/en/latest/peewee/cookbook.html>`_
has recipes for common operations and is a good place to get started.

check the `documentation <http://peewee.readthedocs.org/>`_ for more
examples.

specific question?  come hang out in the #peewee channel on freenode.irc.net,
or post to the mailing list, http://groups.google.com/group/peewee-orm

lastly, peewee runs on python 2.6+ or 3.2+.

Still want more info?
---------------------

.. image:: http://media.charlesleifer.com/blog/photos/wat.jpg



Why?
----

peewee began when I was working on a small app in flask and found myself writing
lots of queries and wanting a very simple abstraction on top of the sql.  I had
so much fun working on it that I kept adding features. peewee is small enough that
its my hope anyone with an interest in orms will be able to understand the code
without much trouble.


model definitions and schema creation
-------------------------------------

smells like django::


    from peewee import *

    class Blog(Model):
        title = CharField()

        def __unicode__(self):
            return self.title

    class Entry(Model):
        title = CharField(max_length=50)
        content = TextField()
        pub_date = DateTimeField()
        blog = ForeignKeyField(Blog, related_name='entries')

        def __unicode__(self):
            return '%s: %s' % (self.blog.title, self.title)


open a connection to the database::

    >>> from peewee import database
    >>> database.connect()

create a set of tables from models ::

     >>> from peewee import create_model_tables
     >>> create_model_tables([Blog, Entry]) # will be sorted topologically

create a specific table ::

    >>> Blog.create_table()
    >>> Entry.create_table()

drop a specific table ::

    >>> Blog.drop_table()
    >>> Entry.drop_table()

drop a set of tables from models ::

    >>> from peewee import drop_model_tables
    >>> drop_model_tables([Blog, Entry]) # Drop tables for all given models (in the right order)


foreign keys work like django's
-------------------------------

    >>> b = Blog(title="Peewee's Big Adventure")
    >>> b.save()
    >>> e = Entry(title="Greatest movie ever?", content="YES!", blog=b)
    >>> e.save()
    >>> e.blog
    <Blog: Peewee's Big Adventure>
    >>> for e in b.entries:
    ...     print e.title
    ...
    Greatest movie ever?


querying
--------

queries come in 5 flavors (select/update/insert/delete/"raw").

there's the notion of a *query context* which is the model being selected
or joined on::

    User.select().where(User.active == True).order_by(User.username)

since User is the model being selected, the where clause and the order_by will
pertain to attributes on the User model.  User is the current query context
when the .where() and .order_by() are evaluated.

an example using joins::

    (Tweet
      .select()
      .join(User)
      .where((Tweet.deleted == False) & (User.active == True))
      .order_by(Tweet.pub_date.desc()))

this will select non-deleted tweets from active users.


using sqlite
------------

::

    from peewee import *

    database = SqliteDatabase('my.db')

    class BaseModel(Model):
        class Meta:
            database = database

    class Blog(BaseModel):
        creator = CharField()
        name = CharField()

    class Entry(BaseModel):
        creator = CharField()
        name = CharField()


using postgresql
----------------

you can now use postgresql::

    from peewee import *

    database = PostgresqlDatabase('my_db', user='root')

    class BaseModel(Model):
        class Meta:
            database = database

    # ... same as above sqlite example ...


using mysql
-----------

you can now use MySQL::

    from peewee import *

    database = MySQLDatabase('my_db', user='root')

    class BaseModel(Model):
        class Meta:
            database = database

    # ... same as above sqlite example ...


what now?
---------

Check out the `quick start <http://peewee.readthedocs.org/en/latest/peewee/quickstart.html>`_
