.. _pwasyncio:

Async Support
=============

.. module:: playhouse.pwasyncio

Peewee's async extension bridges blocking query execution to the asyncio event
loop using ``greenlet``. When database I/O occurs inside a greenlet, control is
transparently yielded to the event loop until the driver completes the
operation. This allows synchronous Peewee code to run unmodified within an
async context.

Example
-------

``playhouse.pwasyncio`` contains the async database implementations. Typically
this is the only thing you will need in order to use Peewee with asyncio:

.. code-block:: python

   import asyncio
   from peewee import *
   from playhouse.pwasyncio import AsyncSqliteDatabase

   db = AsyncSqliteDatabase('my_app.db')

   class User(db.Model):
       name = TextField()

Queries must be executed through an async execution method. This ensures that
when blocking would occur, control is properly yielded to the event loop. The
database context (``async with db``) acquires a connection from the pool and
releases it on exit:

.. code-block:: python

   async def main():
       async with db:
           await db.acreate_tables([User])

           # Create a new user in a transaction.
           async with db.atomic() as txn:
               user = await db.run(User.create, name='Charlie')

           # Fetch a single row from the database.
           charlie = await db.get(User.select().where(User.name == 'Charlie'))
           assert charlie.name == user.name

           # Execute a query and iterate results.
           for user in await db.list(User.select().order_by(User.name)):
               print(user.name)

           # Async lazy result fetching (uses server-side cursors where
           # available).
           query = User.select().order_by(User.name)
           async for user in db.iterate(query):
               print(user.name)

       await db.close_pool()

   asyncio.run(main())

Installation
------------

Requires Python 3.8 or newer, ``greenlet`` and an async database driver:

.. code-block:: shell

   pip install peewee greenlet

   pip install aiosqlite  # SQLite
   pip install asyncpg  # Postgresql
   pip install aiomysql  # MySQL / MariaDB

Supported backends:

================  ============  ====================================
Database          Driver        Peewee class
================  ============  ====================================
SQLite            aiosqlite     :class:`AsyncSqliteDatabase`
Postgresql        asyncpg       :class:`AsyncPostgresqlDatabase`
MySQL / MariaDB   aiomysql      :class:`AsyncMySQLDatabase`
================  ============  ====================================

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

   # SELECT and stream results from the database asynchronously.
   users = [user async for user in db.iterate(User.select())]

   # SELECT and return a scalar value.
   count = await db.scalar(User.select(fn.COUNT(User.id)))

   # Or user shortcut.
   count = await db.count(User.select())

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

       # Nesting and explicit commit/rollback work.
       async with db.atomic() as nested:
           await db.aexecute(User.delete().where(User.name == 'Bob'))
           await nested.arollback()  # Un-delete Bob.

   # Both Alice and Bob are in the database.

Or wrap transactional code in ``db.run()``:

.. code-block:: python

   def create_users():
       with db.atomic():
           User.create(name='Alice')
           User.create(name='Bob')

           with db.atomic() as nested:
               User.delete().where(User.name == 'Bob').execute()
               nested.rollback()  # Un-delete Bob.

   await db.run(create_users)

   # Both Alice and Bob are in the database.

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
shared between tasks**. Each async task will have it's own connection and
transaction state - this prevents bugs that may occur when connections are
shared and transactions end up interleaved across several running tasks.

To shut down completely (e.g. during application teardown):

.. code-block:: python

   await db.close_pool()

MySQL and Postgresql
^^^^^^^^^^^^^^^^^^^^

MySQL and Postgresql use the driver's native connection pool.

Pool configuration options include:

* ``pool_size``: Maximum number of connections
* ``pool_min_size``: Minimum pool size
* ``acquire_timeout``: Timeout when acquiring a connection

.. code-block:: python

   db = AsyncPostgresqlDatabase(
       'peewee_test',
       host='localhost',
       user='postgres',
       pool_size=10,
       pool_min_size=1,
       acquire_timeout=10)

SQLite
^^^^^^

Peewee provides a simple connection-pooling implementation for SQLite
connections.

Pool configuration options include:

* ``pool_size``: Maximum number of connections
* ``acquire_timeout``: Timeout when acquiring a connection

SQLite operates on local disk storage, so queries typically execute extremely
quickly. The cost of dispatching to a background thread and wrapping in
coroutines increases the latency per query. For every query executed, a closure
must be created, a future allocated, a queue written-to, a loop
``call_soon_threadsafe()`` issued, and two context switches made. This is the
case with `aiosqlite <https://github.com/omnilib/aiosqlite/blob/main/aiosqlite/core.py>`__.

Additionally, SQLite only allows one writer at a time, so while using an async
wrapper may keep things responsive while waiting to obtain the write lock,
writes will not occur "faster", the bottleneck has merely been moved.
Conversely, if you don’t have that much load, the async wrapper adds complexity
and overhead for no measurable benefit.

To use SQLite in an async environment anyways, it is strongly recommended to
use WAL-mode at a minimum, which allows multiple readers to co-exist with a
single writer:

.. code-block:: python

   db = AsyncSqliteDatabase('app.db', pragmas={'journal_mode': 'wal'})


Sharp Corners
-------------

Lazy foreign key access outside ``db.run()``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Accessing a lazy foreign key attribute triggers a synchronous query if the
object has not been populated. Outside a greenlet context, this raises ``MissingGreenletBridge``:

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

The safest approach is to disable lazy-loading on your foreign-key fields and
enforce selecting relations via explicit joins.

.. code-block:: python

   class Tweet(db.Model):
       user = ForeignKeyField(User, backref='tweets', lazy_load=False)
       ...


Iterating back-references outside ``db.run()``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Iterating a back-reference outside a greenlet context also fails for the same
reason as above.

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

   # Use prefetch:
   users = await db.run(
       prefetch,
       User.select().where(User.username.in_(('Charlie', 'Huey', 'Mickey')))
       Tweet.select())

   for user in users:
       for tweet in user.tweets:  # Prefetched - no extra query.
           print(tweet.content)

Any code that triggers a database query must execute via either ``db.run()`` or
one of the async helper methods.

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

   Mixin class providing asyncio execution support. Use a driver-specific
   subclass in application code:

   * :class:`AsyncSqliteDatabase`
   * :class:`AsyncPostgresqlDatabase`
   * :class:`AsyncMySQLDatabase`

   Each asyncio task maintains its own connection state and transaction stack.
   Connections are acquired and released back to the pool when the task
   completes or the database context exits.

   .. method:: run(fn, *args, **kwargs)
      :async:

      :param fn: A synchronous callable.
      :returns: The return value of ``fn(*args, **kwargs)``.

      Execute a synchronous callable inside a greenlet and return the result.
      This is the primary entry point for executing Peewee ORM code in an
      async context.

      When database I/O or blocking would occur, control is yielded to the
      event-loop automatically.

      Example:

      .. code-block:: python

         db = AsyncSqliteDatabase(':memory:')

         class User(db.Model):
             username = TextField()

         def setup_app():
             # Ensure table exists and admin user is present at startup.
             with db:
                 db.create_tables([User])

                 # Create admin user if does not exist.
                 try:
                     with db.atomic():
                         User.create(username='admin')
                 except IntegrityError:
                     pass

         async def main():
             await db.run(setup_app)

             # We can pass arguments to the synchronous callable and get
             # return values as well.
             admin_user = await db.run(User.get, User.username == 'admin')

   .. method:: aconnect()
      :async:

      :return: A wrapped async connection.

      Acquire a connection from the pool for the current task. Typically the
      connection is not used directly, since the connection will be bound to
      the task using a task-local.

      Example:

      .. code-block:: python

         # Acquire a connection from the pool which will be used for the
         # current asyncio task.
         await db.aconnect()

         # Run some queries.
         users = await db.list(User.select().order_by(User.username))
         for user in users:
             print(user.username)

         # Close connection, which releases it back to the pool.
         await db.aclose()

      Typically applications should prefer to use the async context-manager for
      connection management, e.g.:

      .. code-block:: python

         db = AsyncSqliteDatabase(':memory:')

         async with db:
             # Connection is obtained from the pool and used for this task.
             await db.acreate_tables([User, Tweet])

         # Context block exits, connection is released back to pool.

   .. method:: aclose()
      :async:

      Release the current task's connection back to the pool.

   .. method:: close_pool()
      :async:

      Close the underlying connection pool and release all active connections.

      This method should be called during application shutdown.

   .. method:: __aenter__()
               __aexit__(exc_type, exc, tb)
      :async:

      Async database context, acquiring a connection for the current task for
      the duration of the wrapped block.

      .. code-block:: python

         db = AsyncSqliteDatabase(':memory:')

         async with db:
             # Connection is obtained from the pool and used for this task.
             await db.acreate_tables([User, Tweet])

         # Context block exits, connection is released back to pool.

   .. method:: aexecute(query)
      :async:

      :param Query query: a Select, Insert, Update or Delete query.
      :return: the normal return-value for the query type.

      Execute any Peewee query object and return its result.

      Example:

      .. code-block:: python

         insert = User.insert(username='Huey')
         pk = await db.aexecute(insert)

         update = (Tweet
                   .update(is_published=True)
                   .where(Tweet.timestamp <= datetime.now()))
         nrows = await db.aexecute(update)

         spammers = (User
                     .delete()
                     .where(User.username.contains('billing'))
                     .returning(User.username))
         for u in await db.aexecute(spammers):
             print(f'Deleted: {u.username}')

   .. method:: get(query)
      :async:

      :param Query query: a Select query.

      Execute a SELECT query and return a single model instance.
      Raises :exc:`~Model.DoesNotExist` if no row matches.

      Example:

      .. code-block:: python

         huey = await db.get(User.select().where(User.username == 'Huey'))

         # Fetch a model and a relation in single query.
         query = Tweet.select(Tweet, User).join(User).where(Tweet.id == 123)
         tweet = await db.get(query)
         print(tweet.user.username, '->', tweet.content)

   .. method:: list(query)
      :async:

      :param Query query: a Select query, or an Insert, Update or Delete
          query that utilizes RETURNING.

      Execute a SELECT (or INSERT/UPDATE/DELETE with RETURNING) and return
      a list of results.

      Example:

      .. code-block:: python

         query = User.select().order_by(User.username)
         async for user in db.list(query):
             print(user.username)

   .. method:: iterate(query)
      :async:

      :param Query query: a Select query to stream results from using an async
         generator.

      :meth:`~AsyncDatabaseMixin.iterate` method uses server-side cursors
      (MySQL and Postgres) to efficiently stream large result-sets.

      Example:

      .. code-block:: python

         query = User.select().order_by(User.username)
         async for user in db.iterate(query):
             print(user.username)

   .. method:: scalar(query)
      :async:

      :param Query query: a Select query.

      Execute a SELECT and return the first column of the first row.

      Example:

      .. code-block:: python

         max_id = await db.scalar(User.select(fn.MAX(User.id)))

   .. method:: count(query)
      :async:

      :param Query query: a Select query.

      Wrap the query in a SELECT COUNT(...) and return the count of rows.

      Example:

      .. code-block:: python

         tweets = await db.count(Tweet.select().where(Tweet.is_published))

   .. method:: exists(query)
      :async:

      :param Query query: a Select query.

      Return boolean whether the query contains any results.

   .. method:: aprefetch(query, *subqueries)
      :async:

      :param Query query: Query to use as starting-point.
      :param subqueries: One or more models or :class:`ModelSelect` queries
          to eagerly fetch.
      :return: a list of models with selected relations prefetched.

      Eagerly fetch related objects, allowing efficient querying of multiple
      tables when a 1-to-many relationship exists.

      .. code-block:: python

         users = User.select().order_by(User.username)
         tweets = Tweet.select().order_by(Tweet.timestamp)

         for user in await db.aprefetch(users, tweets):
             print(user.username)
             for tweet in user.tweets:
                 print('    ', tweet.content)

   .. method:: atomic()

      Return an async-aware atomic context manager. Supports both
      ``async with`` and ``with``.

      Example of async usage:

      .. code-block:: python

         async def transfer_funds(src, dest, amount):
             async with db.atomic() as txn:
                 await db.aexecute(
                     Account
                     .update(balance=Account.balance - amount)
                     .where(Account.id == src.id))

                 await db.aexecute(
                     Account
                     .update(balance=Account.balance + amount)
                     .where(Account.id == dest.id))

         async def main():
             await transfer_funds(user1, user2, 100.)

      Example of sync usage:

      .. code-block:: python

         def transfer_funds(src, dest, amount):
             with db.atomic() as txn:
                 (Account
                  .update(balance=Account.balance - amount)
                  .where(Account.id == src.id)
                  .execute())

                 (Account
                  .update(balance=Account.balance + amount)
                  .where(Account.id == dest.id)
                  .execute())

         async def main():
             await db.run(transfer_funds, user1, user2, 100.)

   .. method:: acreate_tables(models, **options)
      :async:

      :param list models: A list of :class:`Model` classes.
      :param options: Options to specify when calling
          :meth:`Model.create_table`.

      Create tables, indexes and associated constraints for the given list of
      models.

      Dependencies are resolved so that tables are created in the appropriate
      order.

      Example:

      .. code-block:: python

         class User(db.Model):
             ...

         class Tweet(db.Model):
             ...

         async def setup_hook():
             async with db:
                 await db.acreate_tables([User, Tweet])

   .. method:: adrop_tables(models, **options)
      :async:

      :param list models: A list of :class:`Model` classes.
      :param kwargs: Options to specify when calling
          :meth:`Model.drop_table`.

      Drop tables, indexes and constraints for the given list of models.

   .. method:: aexecute_sql(sql, params=None)
      :async:

      :param str sql: SQL query to execute.
      :param tuple params: Optional query parameters.
      :returns: A :class:`CursorAdapter` instance.

      Execute SQL asynchronously. Returns a cursor-like object whose rows are
      already fetched (call ``.fetchall()`` synchronously). For result
      streaming, see :meth:`~AsyncDatabaseMixin.iterate`.


.. class:: AsyncSqliteDatabase(database, **kwargs)

   Async SQLite database implementation.

   Uses ``aiosqlite`` and maintains a single shared connection. Pool-related
   configuration options are ignored.

   Inherits from :class:`AsyncDatabaseMixin` and :class:`SqliteDatabase`.

.. class:: AsyncPostgresqlDatabase(database, **kwargs)

   Async Postgresql database implementation.

   Uses ``asyncpg`` and the driver's native connection pool.

   Inherits from :class:`AsyncDatabaseMixin` and :class:`PostgresqlDatabase`.

.. class:: AsyncMySQLDatabase(database, **kwargs)

   Async MySQL / MariaDB database implementation.

   Uses ``aiomysql`` and the driver's native connection pool.

   Inherits from :class:`AsyncDatabaseMixin` and :class:`MySQLDatabase`.

.. class:: MissingGreenletBridge(RuntimeError)

   Raised when Peewee attempts to execute a query outside a greenlet context.
   This indicates that a query was triggered outside of ``db.run()`` or an
   async helper call.
