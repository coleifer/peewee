.. image:: http://i.imgur.com/zhcoT.png

peewee
======

* A small, expressive ORM
* Written in python with support for versions 2.6+ and 3.2+.
* built-in support for sqlite, mysql and postgresql
* tons of extensions available in the `playhouse <http://docs.peewee-orm.com/en/latest/peewee/playhouse.html>`_ (postgres hstore/json/arrays, sqlite full-text-search, schema migrations, and much more).

.. image:: https://api.travis-ci.org/coleifer/peewee.png?branch=master
  :target: https://travis-ci.org/coleifer/peewee

For flask integration, check out `flask-peewee <http://flask-peewee.readthedocs.org/>`_, which includes and admin interface, RESTful APIs, authentication, and more. You can also use peewee with the popular extension `flask-admin <http://flask-admin.readthedocs.org/en/latest/>`_.

Defining models is similar to Django or SQLAlchemy::

    from peewee import *

    db = SqliteDatabase('my_database.db', threadlocals=True)

    class BaseModel(Model):
        class Meta:
            database = db

    class User(BaseModel):
        username = CharField(unique=True)

    class Tweet(BaseModel):
        user = ForeignKeyField(User, related_name='tweets')
        message = TextField()
        created_date = DateTimeField(default=datetime.datetime.now)
        is_published = BooleanField(default=True)

Connect to the database and create tables::

    db.connect()
    db.create_tables([User, Tweet])

Create a few rows::

    charlie = User.create(username='charlie')
    huey = User(username='huey')
    huey.save()

    # No need to set `is_published` or `created_date` since they
    # will just use the default values we specified.
    Tweet.create(user=charlie, message='My first tweet')

Queries are expressive and composable::

    # A simple query selecting a user.
    User.get(User.username == 'charles')

    # Get tweets created by one of several users. The "<<" operator
    # corresponds to the SQL "IN" operator.
    usernames = ['charlie', 'huey', 'mickey']
    users = User.select().where(User.username << usernames)
    tweets = Tweet.select().where(Tweet.user << users)

    # We could accomplish the same using a JOIN:
    tweets = (Tweet
              .select()
              .join(User)
              .where(User.username << usernames))

    # How many tweets were published today?
    tweets_today = (Tweet
                    .select()
                    .where(
                        (Tweet.created_date >= datetime.date.today()) &
                        (Tweet.is_published == True))
                    .count())

    # Paginate the user table and show me page 3 (users 41-60).
    User.select().order_by(User.username).paginate(3, 20)

    # Order users by the number of tweets they've created:
    tweet_ct = fn.Count(Tweet.id)
    users = (User
             .select(User, tweet_ct.alias('ct'))
             .join(Tweet, JOIN_LEFT_OUTER)
             .group_by(User)
             .order_by(tweet_ct.desc()))

    # Do an atomic update
    Counter.update(count=Counter.count + 1).where(
        Counter.url == request.url)

Check out the `example app <http://docs.peewee-orm.com/en/latest/peewee/example.html>`_ for a working Twitter-clone website written with Flask.

Learning more
-------------

Check the `documentation <http://docs.peewee-orm.com/>`_ for more examples.

Specific question? Come hang out in the #peewee channel on freenode.irc.net, or post to the mailing list, http://groups.google.com/group/peewee-orm . If you would like to report a bug, `create a new issue <https://github.com/coleifer/peewee/issues/new>`_ on GitHub.

Still want more info?
---------------------

.. image:: http://media.charlesleifer.com/blog/photos/wat.jpg

Why does peewee exist?
----------------------

peewee began when I was working on a small app in flask and found myself writing lots of queries and wanting a very simple abstraction on top of the sql.  I had so much fun working on it that I kept adding features. peewee is small enough that its my hope anyone with an interest in orms will be able to understand the code without much trouble.

I hope you enjoy using peewee as much as I've enjoyed working on it!

.. image:: http://media.charlesleifer.com/playground/notes/img/im-97f3e42c02.jpg
