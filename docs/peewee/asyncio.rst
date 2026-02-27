.. _asyncio:

Async Support
=============

Peewee is a synchronous library by design. Its core query execution path uses
blocking DB-API 2.0 calls. The async support described here bridges that
synchronous core to an asyncio event loop using ``greenlet``.

When database I/O occurs inside a greenlet, control is yielded to the event
loop until the driver completes the operation. From the perspective of your
application code, queries look synchronous; from the event loop's perspective,
they yield during I/O.

This means existing Peewee code - queries, transactions, ORM methods - runs
unchanged inside async contexts. No query-by-query API changes are required.

.. note::
   For applications that use Peewee with a purely synchronous framework
   (Flask, Django, Bottle, etc.), no async setup is needed. See
   :ref:`framework-integration` for examples of using Peewee with various sync
   and async frameworks.

Installation
------------

Requires Python 3.8 or newer, plus ``greenlet`` and an async-compatible
database driver:

.. code-block:: shell

   pip install peewee greenlet

   pip install aiosqlite     # SQLite
   pip install asyncpg       # Postgresql
   pip install aiomysql      # MySQL / MariaDB

Supported backends:

================  ============  ====================================
Database          Driver        Peewee class
================  ============  ====================================
SQLite            aiosqlite     :class:`AsyncSqliteDatabase`
Postgresql        asyncpg       :class:`AsyncPostgresqlDatabase`
MySQL / MariaDB   aiomysql      :class:`AsyncMySQLDatabase`
================  ============  ====================================


Basic Usage
-----------

Import from ``playhouse.pwasyncio`` and use the async database class in place
of the standard one. Models are defined identically:

.. code-block:: python

   import asyncio
   from peewee import *
   from playhouse.pwasyncio import AsyncSqliteDatabase

   db = AsyncSqliteDatabase('my_app.db')

   class User(db.Model):
       name = TextField()

All queries must be executed through one of the async execution methods
described below. The database context (``async with db``) acquires a
connection from the pool and releases it on exit:

.. code-block:: python

   async def main():
       async with db:
           await db.acreate_tables([User])

           user = await db.run(User.create, name='Charlie')

           charlie = await db.get(User.select().where(User.name == 'Charlie'))
           assert charlie.name == user.name

           for user in await db.list(User.select().order_by(User.name)):
               print(user.name)

       await db.close_pool()

   asyncio.run(main())

Execution Methods
-----------------

``db.run()`` - general-purpose entry point
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:meth:`~AsyncDatabaseMixin.run` accepts any callable and runs it inside a
greenlet bridge. The callable can contain arbitrary synchronous Peewee code,
including transactions:

.. code-block:: python

   # Single operation:
   user = await db.run(User.create, name='Alice')

   # Multi-step function:
   def register(username, bio):
       with db.atomic():
           user = User.create(name=username)
           Profile.create(user=user, bio=bio)
           return user

   user = await db.run(register, 'alice', 'Python developer')

Use ``db.run()`` when:

* You have existing synchronous code you want to call from async.
* A single operation involves multiple queries (e.g. a transaction).

Async Helper Methods
^^^^^^^^^^^^^^^^^^^^^

For single-query operations, the async helpers are more direct:

.. code-block:: python

   # Execute any query and get its natural return type.
   cursor = await db.aexecute(query)

   # Use a transaction:
   async with db.atomic() as tx:
       await db.run(User.create, name='Bob')

   # SELECT and return one model instance (raises DoesNotExist if none).
   user = await db.get(User.select().where(User.name == 'Alice'))

   # SELECT and return a list.
   users = await db.list(User.select().order_by(User.name))

   # SELECT and return a scalar value.
   count = await db.scalar(User.select(fn.COUNT('*')))

   # CREATE TABLE / DROP TABLE:
   await db.acreate_tables([User, Tweet])
   await db.adrop_tables([User, Tweet])

   # Raw SQL:
   cursor = await db.aexecute_sql('SELECT 1')
   print(cursor.fetchall())   # [(1,)]

Transactions
^^^^^^^^^^^^^

Use ``async with db.atomic()`` for async-aware transactions:

.. code-block:: python

   async with db.atomic():
       await db.run(User.create, name='Alice')
       await db.run(User.create, name='Bob')
   # Both committed when the block exits.

Or wrap transactional code in ``db.run()``:

.. code-block:: python

   def create_users():
       with db.atomic():
           User.create(name='Alice')
           User.create(name='Bob')

   await db.run(create_users)

Both approaches produce the same result. The ``db.run()`` form is often simpler
when the transactional logic involves many inter-dependent queries.


Connection Management
---------------------

The database context manager (``async with db``) is the recommended way to
manage connections. It acquires a connection on entry and releases it on exit:

.. code-block:: python

   async with db:
       # Connection is available here.
       pass
   # Connection released.

Explicit control is also available:

.. code-block:: python

   await db.aconnect()    # Acquire connection for the current task.
   # ... queries ...
   await db.aclose()      # Release connection back to pool.

Each asyncio task gets its own connection from the pool. **Connections are not
shared between tasks**.

To shut down completely (e.g. during application teardown):

.. code-block:: python

   await db.close_pool()

SQLite
^^^^^^

SQLite uses a single shared connection, as the underlying database does not
support concurrent writers.

Generally SQLite is a poor fit for asynchronous workflows where writes may be
coming in at any time, and transactions may be interleaved across multiple
writers. Furthermore, SQLite does not do any network I/O.

The SQLite implementation is provided mostly for testing and local development.

MySQL and Postgresql
^^^^^^^^^^^^^^^^^^^^

MySQL and Postgresql use the driver's native connection pool.

Pool configuration options include:

* ``pool_size`` - Maximum number of connections
* ``pool_min_size`` - Minimum pool size
* ``acquire_timeout`` - Timeout when acquiring a connection

.. code-block:: python

    db = AsyncPostgresqlDatabase(
        'peewee_test',
        host='localhost',
        user='postgres',
        pool_size=10,
        pool_min_size=1,
        acquire_timeout=10)


Sharp Corners
-------------

Lazy foreign key access outside ``db.run()``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Accessing a lazy foreign key attribute triggers a synchronous query. Outside a
greenlet context, this raises ``MissingGreenletBridge``:

.. code-block:: python

   tweet = await db.get(Tweet.select())

   # FAILS: triggers a SELECT outside the greenlet bridge.
   print(tweet.user.name)
   # MissingGreenletBridge: Attempted query outside greenlet runner.

Fix by selecting the related model in the original query:

.. code-block:: python

   query = Tweet.select(Tweet, User).join(User)
   tweet = await db.get(query)
   print(tweet.user.name)   # OK - no extra query.

Or by wrapping the access in ``db.run()``:

.. code-block:: python

   name = await db.run(lambda: tweet.user.name)

To prevent errors from occurring at run-time you can disable lazy-loading on
your foreign-key fields:

.. code-block:: python

   class Tweet(db.Model):
       user = ForeignKeyField(User, backref='tweets', lazy_load=False)
       ...


Iterating back-references outside ``db.run()``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For the same reason, iterating a back-reference outside a greenlet context
also fails:

.. code-block:: python

   # FAILS:
   for tweet in user.tweets:
       print(tweet.content)

Solutions:

.. code-block:: python

   # Using db.list():
   for tweet in await db.list(user.tweets):
       print(tweet.content)

   # Using db.run() with list():
   tweets = await db.run(list, user.tweets)

   # Using prefetch inside db.run():
   def get_user_with_tweets(user_id):
       user_q = User.select().where(User.id == user_id)
       return prefetch(user_q, Tweet.select())[0]

   user = await db.run(get_user_with_tweets, user_id)
   for tweet in user.tweets:   # Prefetched - no extra query.
       print(tweet.content)

The general rule is: any code that triggers a database query must execute
inside a greenlet context, which means inside ``db.run()`` or an async helper
call.


API Reference
-------------

.. class:: AsyncDatabaseMixin(database, pool_size=10, pool_min_size=1, acquire_timeout=10, **kwargs)

   :param str database: Database name or filename for SQLite.
   :param int pool_size: Maximum size of the driver-managed connection pool
       (no-op for SQLite).
   :param int pool_min_size: Minimum size of the driver-managed connection pool
       (no-op for SQLite).
   :param float acquire_timeout: Time (in seconds) to wait for a free
       connection when acquiring from the pool.
   :param kwargs: Arbitrary keyword arguments passed to the underlying database
       driver when creating connections (e.g., ``user``, ``password``,
       ``host``).

   Mixin class providing asyncio execution support. Not used directly -
   instantiate :class:`AsyncSqliteDatabase`,
   :class:`AsyncPostgresqlDatabase`, or :class:`AsyncMySQLDatabase`.

   Each asyncio task maintains its own connection state. Connections are
   acquired and released back to the pool when the task completes or the
   database context exits.

   .. method:: run(fn, *args, **kwargs)
      :async:

      :param fn: A synchronous callable.
      :returns: The return value of ``fn``.

      Execute a synchronous callable inside a greenlet and return the result.
      This is the primary entry point for executing Peewee ORM code in an
      async context.

   .. method:: aconnect()
      :async:

      :return: A wrapped async connection.

      Acquire a connection from the pool for the current task.

   .. method:: aclose()
      :async:

      Release the current task's connection back to the pool.

   .. method:: close_pool()
      :async:

      Close the underlying connection pool and release all active connections.

      This method should be called during application shutdown.

   .. method:: __aenter__()
      :async:

      Enter an async database context, acquiring a connection.

   .. method:: __aexit__(exc_type, exc, tb)
      :async:

      Exit the async database context, releasing the connection.

   .. method:: aexecute(query)
      :async:

      :param Query query: a Select, Insert, Update or Delete query.
      :return: the normal return-value for the query type.

      Execute any Peewee query object and return its natural result.

   .. method:: get(query)
      :async:

      :param Query query: a Select query.

      Execute a SELECT query and return a single model instance.
      Raises :exc:`~Model.DoesNotExist` if no row matches.

   .. method:: list(query)
      :async:

      :param Query query: a Select query, or an Insert, Update or Delete
          query that utilizes RETURNING.

      Execute a SELECT (or INSERT/UPDATE/DELETE with RETURNING) and return
      a list of results.

   .. method:: scalar(query)
      :async:

      :param Query query: a Select query.

      Execute a SELECT and return the first column of the first row.

   .. method:: atomic()

      Return an async-aware atomic context manager. Supports both
      ``async with`` and ``with``.

   .. method:: acreate_tables(models, **options)
      :async:

      Create tables asynchronously.

   .. method:: adrop_tables(models, **options)
      :async:

      Drop tables asynchronously.

   .. method:: aexecute_sql(sql, params=None)
      :async:

      :param str sql: SQL query to execute.
      :param tuple params: Optional query parameters.
      :returns: A :class:`CursorAdapter` instance.

      Execute raw SQL asynchronously. Returns a cursor-like object whose
      rows are already fetched (call ``.fetchall()`` synchronously).


.. class:: AsyncSqliteDatabase(database, **kwargs)

   Async SQLite database implementation.

   Uses ``aiosqlite`` and maintains a single shared connection. Pool-related
   configuration options are ignored.

   Inherits from :class:`AsyncDatabaseMixin` and
   :class:`peewee.SqliteDatabase`.

.. class:: AsyncPostgresqlDatabase(database, **kwargs)

   Async Postgresql database implementation.

   Uses ``asyncpg`` and the driver's native connection pool.

   Inherits from :class:`AsyncDatabaseMixin` and
   :class:`peewee.PostgresqlDatabase`.

.. class:: AsyncMySQLDatabase(database, **kwargs)

   Async MySQL / MariaDB database implementation.

   Uses ``aiomysql`` and the driver's native connection pool.

   Inherits from :class:`AsyncDatabaseMixin` and
   :class:`peewee.MySQLDatabase`.

.. class:: MissingGreenletBridge(RuntimeError)

   Raised when Peewee attempts to execute a query outside a greenlet context.
   This indicates that a query was triggered outside of ``db.run()`` or an
   async helper call.
