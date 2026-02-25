.. _quickstart:

Quickstart
==========

This guide walks through defining a schema, writing rows, and reading them
back. It takes about ten minutes. Every concept introduced here is covered in
depth in the following documents.

.. tip::
   Follow along in an interactive Python session.

Model Definition
-----------------

A Peewee application starts with a :class:`Database` object and one or more
:class:`Model` classes. The database object manages connections; model
classes map to tables.

.. code-block:: python

   import datetime
   from peewee import *

   # An in-memory SQLite database. Or use PostgresqlDatabase or MySQLDatabase.
   db = SqliteDatabase(':memory:')

   class BaseModel(Model):
       """All models inherit this to share the database connection."""
       class Meta:
           database = db

   class User(BaseModel):
       username = TextField(unique=True)

   class Tweet(BaseModel):
       user = ForeignKeyField(User, backref='tweets')
       content = TextField()
       timestamp = DateTimeField(
           default=datetime.datetime.now,
           index=True)

Three things to notice:

* ``BaseModel`` exists only to carry the ``database`` setting. Every subclass
  inherits it automatically.
* Peewee adds an auto-incrementing integer ``id`` primary key to any model
  that does not declare its own.
* ``ForeignKeyField`` links ``Tweet`` to ``User``. The ``backref='tweets'``
  parameter means every ``User`` instance gains a ``tweets`` attribute.

Create the Tables
-----------------

.. code-block:: python

   db.connect()
   db.create_tables([User, Tweet])

:meth:`~Database.create_tables` generates ``CREATE TABLE`` statements for
each model. By default ``create_table()`` specifies ``safe=True``, which uses
``CREATE TABLE IF NOT EXISTS``, making it safe to call on every startup.

Writing Data
------------

Create a row with :meth:`~Model.create` (one step) or instantiate a model
and call :meth:`~Model.save` (two steps):

.. code-block:: python

   # One-step creation - returns the saved instance.
   charlie = User.create(username='charlie')
   huey = User.create(username='huey')

   # Two-step creation.
   t = Tweet(user=charlie, content='Hello, world!')
   t.save()

   Tweet.create(user=charlie, content='My second tweet.')
   Tweet.create(user=huey, content='meow')

To update an existing row, modify attributes and call ``save()`` again:

.. code-block:: python

   charlie.username = 'charlie_admin'
   charlie.save()

To delete a row:

.. code-block:: python

   stale_tweet = Tweet.get(Tweet.content == 'My second tweet.')
   stale_tweet.delete_instance()

Reading Data
------------

Retrieve a single row with :meth:`~Model.get`. It raises :exc:`~Model.DoesNotExist`
if no match is found:

.. code-block:: python

   user = User.get(User.username == 'charlie_admin')
   print(user.id, user.username)

Retrieve multiple rows with :meth:`~Model.select`. The result is a lazy
query - rows are fetched only when you iterate:

.. code-block:: python

   for tweet in Tweet.select():
       print(tweet.content)

Filter with :meth:`~Query.where`:

.. code-block:: python

   for tweet in Tweet.select().where(Tweet.user == charlie):
       print(tweet.content)

   for tweet in Tweet.select().where(Tweet.timestamp.year == 2026):
       print(tweet.content)

Sort with :meth:`~Query.order_by`:

.. code-block:: python

   for tweet in Tweet.select().order_by(Tweet.timestamp.desc()):
       print(tweet.timestamp, tweet.content)

Join to combine data from related tables in a single query:

.. code-block:: python

   # Fetch each tweet alongside its author's username.
   # Without the join, accessing tweet.user.username would issue
   # an extra query per tweet - see the N+1 section in Relationships.
   query = (Tweet
            .select(Tweet, User)
            .join(User)
            .order_by(Tweet.timestamp.desc()))

   for tweet in query:
       print(tweet.user.username, '->', tweet.content)

Simple Aggregates
-----------------

How many tweets are in the database:

.. code-block:: python

   Tweet.select().count()

When the most-recent tweet was added:

.. code-block:: python

   Tweet.select(fn.MAX(Tweet.timestamp)).scalar()

Close the Connection
--------------------

When done using the database, close the connection:

.. code-block:: python

   db.close()

In a web application you would open the connection when a request arrives and
close it when the response is sent. See :ref:`framework-integration` for
framework-specific patterns.

Working with Existing databases
-------------------------------

If you have an existing database, peewee can generate models using :ref:`pwiz`.
For example to generate models for a Postgres database named ``blog_db``:

.. code-block:: shell

   python -m pwiz -e postgresql blog > blog_models.py

What Next
---------

Each concept introduced above is covered in full detail in the following
documents:

* :ref:`database` - connection options, multiple backends, run-time
  configuration, connection pooling.
* :ref:`models` - field types, field parameters, model Meta options, indexes,
  primary keys.
* :ref:`relationships` - how foreign keys work at runtime, joins, the N+1
  problem, many-to-many relationships.
* :ref:`querying` - the full SELECT API: filtering, sorting, aggregates,
  window functions, CTEs.
* :ref:`writing` - INSERT, UPDATE, DELETE, bulk operations, upsert.
* :ref:`transactions` - atomic blocks, nesting, savepoints.

For a complete worked example building a small web application, see
:ref:`example`.
