.. image:: http://media.charlesleifer.com/blog/photos/peewee3-logo.png

peewee
======

Peewee is a simple and small ORM. It has few (but expressive) concepts, making it easy to learn and intuitive to use.

* A small, expressive ORM
* Written in python with support for versions 2.7+ and 3.4+ (developed with 3.6)
* built-in support for sqlite, mysql and postgresql
* tons of extensions available in the `playhouse <http://docs.peewee-orm.com/en/latest/peewee/playhouse.html>`_

  * `Postgresql HStore, JSON, arrays and more <http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#postgres-ext>`_
  * `SQLite full-text search, user-defined functions, virtual tables and more <http://docs.peewee-orm.com/en/latest/peewee/sqlite_ext.html>`_
  * `Schema migrations <http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#migrate>`_ and `model code generator <http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#pwiz>`_
  * `Connection pool <http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#pool>`_
  * `Encryption <http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#sqlcipher-ext>`_
  * `and much, much more... <http://docs.peewee-orm.com/en/latest/peewee/playhouse.html>`_

.. image:: https://travis-ci.org/coleifer/peewee.svg?branch=master
  :target: https://travis-ci.org/coleifer/peewee

New to peewee? Here is a list of documents you might find most helpful when getting
started:

* `Quickstart guide <http://docs.peewee-orm.com/en/latest/peewee/quickstart.html#quickstart>`_ -- this guide covers all the essentials. It will take you between 5 and 10 minutes to go through it.
* `Example queries <http://docs.peewee-orm.com/en/latest/peewee/query_examples.html>`_ taken from the `PostgreSQL Exercises website <https://pgexercises.com/>`_.
* `Guide to the various query operators <http://docs.peewee-orm.com/en/latest/peewee/querying.html#query-operators>`_ describes how to construct queries and combine expressions.
* `Field types table <http://docs.peewee-orm.com/en/latest/peewee/models.html#field-types-table>`_ lists the various field types peewee supports and the parameters they accept.

For flask helpers, check out the `flask_utils extension module <http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#flask-utils>`_. You can also use peewee with the popular extension `flask-admin <https://flask-admin.readthedocs.io/en/latest/>`_ to provide a Django-like admin interface for managing peewee models.

Examples
--------

Defining models is similar to Django or SQLAlchemy:

.. code-block:: python

    from peewee import *
    import datetime


    db = SqliteDatabase('my_database.db')

    class BaseModel(Model):
        class Meta:
            database = db

    class User(BaseModel):
        username = CharField(unique=True)

    class Tweet(BaseModel):
        user = ForeignKeyField(User, backref='tweets')
        message = TextField()
        created_date = DateTimeField(default=datetime.datetime.now)
        is_published = BooleanField(default=True)

Connect to the database and create tables:

.. code-block:: python

    db.connect()
    db.create_tables([User, Tweet])

Create a few rows:

.. code-block:: python

    charlie = User.create(username='charlie')
    huey = User(username='huey')
    huey.save()

    # No need to set `is_published` or `created_date` since they
    # will just use the default values we specified.
    Tweet.create(user=charlie, message='My first tweet')

Queries are expressive and composable:

.. code-block:: python

    # A simple query selecting a user.
    User.get(User.username == 'charlie')

    # Get tweets created by one of several users.
    usernames = ['charlie', 'huey', 'mickey']
    users = User.select().where(User.username.in_(usernames))
    tweets = Tweet.select().where(Tweet.user.in_(users))

    # We could accomplish the same using a JOIN:
    tweets = (Tweet
              .select()
              .join(User)
              .where(User.username.in_(usernames)))

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
             .join(Tweet, JOIN.LEFT_OUTER)
             .group_by(User)
             .order_by(tweet_ct.desc()))

    # Do an atomic update
    Counter.update(count=Counter.count + 1).where(Counter.url == request.url)

Check out the `example app <http://docs.peewee-orm.com/en/latest/peewee/example.html>`_ for a working Twitter-clone website written with Flask.

Learning more
-------------

Check the `documentation <http://docs.peewee-orm.com/>`_ for more examples.

Specific question? Come hang out in the #peewee channel on irc.freenode.net, or post to the mailing list, http://groups.google.com/group/peewee-orm . If you would like to report a bug, `create a new issue <https://github.com/coleifer/peewee/issues/new>`_ on GitHub.

Still want more info?
---------------------

.. image:: http://media.charlesleifer.com/blog/photos/wat.jpg

I've written a number of blog posts about building applications and web-services with peewee (and usually Flask). If you'd like to see some real-life applications that use peewee, the following resources may be useful:

* `Building a note-taking app with Flask and Peewee <http://charlesleifer.com/blog/saturday-morning-hack-a-little-note-taking-app-with-flask/>`_ as well as `Part 2 <http://charlesleifer.com/blog/saturday-morning-hacks-revisiting-the-notes-app/>`_ and `Part 3 <http://charlesleifer.com/blog/saturday-morning-hacks-adding-full-text-search-to-the-flask-note-taking-app/>`_.
* `Analytics web service built with Flask and Peewee <http://charlesleifer.com/blog/saturday-morning-hacks-building-an-analytics-app-with-flask/>`_.
* `Personalized news digest (with a boolean query parser!) <http://charlesleifer.com/blog/saturday-morning-hack-personalized-news-digest-with-boolean-query-parser/>`_.
* `Structuring Flask apps with Peewee <http://charlesleifer.com/blog/structuring-flask-apps-a-how-to-for-those-coming-from-django/>`_.
* `Creating a lastpass clone with Flask and Peewee <http://charlesleifer.com/blog/creating-a-personal-password-manager/>`_.
* `Creating a bookmarking web-service that takes screenshots of your bookmarks <http://charlesleifer.com/blog/building-bookmarking-service-python-and-phantomjs/>`_.
* `Building a pastebin, wiki and a bookmarking service using Flask and Peewee <http://charlesleifer.com/blog/dont-sweat-small-stuff-use-flask-blueprints/>`_.
* `Encrypted databases with Python and SQLCipher <http://charlesleifer.com/blog/encrypted-sqlite-databases-with-python-and-sqlcipher/>`_.
* `Dear Diary: An Encrypted, Command-Line Diary with Peewee <http://charlesleifer.com/blog/dear-diary-an-encrypted-command-line-diary-with-python/>`_.
* `Query Tree Structures in SQLite using Peewee and the Transitive Closure Extension <http://charlesleifer.com/blog/querying-tree-structures-in-sqlite-using-python-and-the-transitive-closure-extension/>`_.
