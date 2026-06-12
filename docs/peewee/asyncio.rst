.. _pwasyncio:

Async Support
=============

.. module:: playhouse.pwasyncio

Peewee's async extension provides asyncio-compatible database backends built on
the standard async drivers, ``aiosqlite``, ``asyncpg`` and ``aiomysql``.
Queries are dispatched to the driver as a coroutine and awaited on the asyncio
event loop, while Peewee's query-building and result-processing code runs
unmodified. See :ref:`how-it-works` for the mechanism.

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
           async with db.atomic():
               user = await User.acreate(name='Charlie')

           # Fetch a single row from the database.
           charlie = await User.aget(User.name == 'Charlie')
           assert charlie.id == user.id

           # Update the row.
           charlie.name = 'Charles'
           await charlie.asave()

           # Execute a query and iterate the buffered results.
           for user in await User.select().order_by(User.name).aexecute():
               print(user.name)

           # Or fetch the rows as a plain list:
           users = await db.list(User.select().order_by(User.name))

           # Async lazy result fetching (uses server-side cursors where
           # available).
           query = User.select().order_by(User.name)
           async for user in db.iterate(query):
               print(user.name)

       await db.close_pool()

   asyncio.run(main())

Every query is awaited on the asyncio event loop, in the calling task: the
SQL is handed to the async driver (``aiosqlite``, ``asyncpg`` or
``aiomysql``) and awaited like any other coroutine. No thread executor is
involved and nothing is monkey-patched. Each task acquires its own
connection from the pool, so concurrent tasks never share connection or
transaction state - details under `Connection Management`_ below.

.. _how-it-works:

How it works
------------

Internally the extension uses ``greenlet`` the same way SQLAlchemy's asyncio
support does: purely as a stack-switching mechanism, so that Peewee's
synchronous internals can be suspended mid-call while the async driver
performs I/O. Whenever a query executes, control switches to the event loop and
the I/O coroutine is awaited like any other awaitable. Then the original call
resumes with the result.

.. note::
   This is real asyncio, NOT gevent-style concurrency. Nothing is
   monkey-patched, no sockets are wrapped, and the event loop is the ordinary
   asyncio loop running the rest of your application.

Execution Methods
-----------------

Async Model Methods
^^^^^^^^^^^^^^^^^^^

Models bound to an async database have ``a``-prefixed counterparts of the
:class:`Model` methods that read or write rows:

.. code-block:: python

   user = await User.acreate(name='Huey')

   user.name = 'Huey-zai'
   await user.asave()

   huey = await User.aget(User.name == 'Huey-zai')
   obj, created = await User.aget_or_create(name='Mickey')

   await huey.adelete_instance()

The naming rule: methods that read or write *rows* live on the model and
take an ``a`` prefix (``acreate``, ``aget``, ``aget_or_none``,
``aget_by_id``, ``aget_or_create``, ``aset_by_id``, ``adelete_by_id``,
``abulk_create``, ``abulk_update``, ``asave``, ``adelete_instance``,
``afetch``). Schema operations live on the database
(:meth:`~AsyncDatabaseMixin.acreate_tables`,
:meth:`~AsyncDatabaseMixin.adrop_tables`). Query-builder methods
(``select()``, ``where()``, and the rest) only build SQL - they perform no
I/O and need no async variant. Of the query methods that do perform I/O,
``execute()`` has an async twin, :meth:`~BaseQuery.aexecute`; the others
(``count()``, ``exists()``, ``get()``, iteration) are covered by the
database helpers (``db.count``, ``db.exists``, ``db.get``, ``db.list``,
etc.), which accept any query as an argument.

Classes derived from ``db.Model`` get these methods automatically when
``db`` is an async database. To declare an explicit base class, subclass
:class:`AsyncModel` (or mix :class:`AsyncModelMixin` into your own base):

.. code-block:: python

   from playhouse.pwasyncio import AsyncModel, AsyncSqliteDatabase

   db = AsyncSqliteDatabase('app.db')

   class BaseModel(AsyncModel):
       class Meta:
           database = db

.. note::
   :py:class:`DatabaseProxy` hands out the synchronous base class from its
   ``Model`` property even when later initialized to an async database -
   proxy users should subclass :class:`AsyncModel` with
   ``Meta.database = proxy``.

Related objects follow three rules. Rows selected with a join or with
:meth:`~AsyncDatabaseMixin.aprefetch` expose their relations as plain
attribute access - no await needed. For a one-off lazy load, use
``await obj.afetch(Model.field)``, which runs the query on the event loop
and caches the result on the instance. And if you are calling ``afetch()``
in a loop, you wanted :meth:`~AsyncDatabaseMixin.aprefetch`. Back-references
are not relation attributes but ordinary select queries - execute them like
any query: ``await user.tweets.aexecute()``.

Executing queries: ``aexecute()``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Queries provide :meth:`~BaseQuery.aexecute`, the async counterpart of
:meth:`~BaseQuery.execute`. It executes the query on its bound async
database and returns whatever ``execute()`` returns: a result wrapper for
selects, the new primary key for inserts, the number of modified rows for
updates and deletes. With a ``RETURNING`` clause, writes return rows, like
a select.

.. code-block:: python

   # The async counterpart of execute():
   active = await User.select().where(User.is_active == True).aexecute()
   for user in active:  # Results are buffered; iteration performs no I/O.
       print(user.username)

   # Writes return their usual values:
   pk = await User.insert(username='huey').aexecute()
   n = await User.update(is_active=False).where(User.is_bot).aexecute()

   # DML with RETURNING (Postgres, SQLite 3.35+):
   query = (User
            .delete()
            .where(User.is_spammer)
            .returning(User.username))
   for user in await query.aexecute():
       print('deleted:', user.username)

   # Resolve a backref:
   for tweet in await user.tweets.aexecute():
       print(tweet.content)

For selects, ``await query.aexecute()`` is interchangeable with
``await db.list(query)`` for iteration - ``aexecute()`` returns the
buffered result wrapper while ``list()`` returns a plain list. When in
doubt, prefer ``query.aexecute()``; use ``db.list()`` when you want a
plain list and ``db.iterate()`` when you want streaming.
``aexecute()`` is the only async method on queries; aggregates and other
conveniences remain database helpers (``await db.count(query)``,
``await db.exists(query)``, and so on).

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

   # Equivalent, as a method on the query itself:
   cursor = await query.aexecute()

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

   # Or use the shortcut.
   count = await db.count(User.select())

   # CREATE TABLE / DROP TABLE:
   await db.acreate_tables([User, Tweet])
   await db.adrop_tables([User, Tweet])

   # Raw SQL:
   cursor = await db.aexecute_sql('SELECT 1')
   print(cursor.fetchall())   # [(1,)]

.. note::
   Choosing between buffered and streaming iteration: ``db.list()`` and
   ``query.aexecute()`` buffer the full result set, and it is safe to await
   other queries while looping over the result. ``db.iterate()`` streams
   rows using server-side cursors
   where available - it holds the task's connection while open (an
   interleaved query on the same connection raises ``InterfaceError`` after
   a short grace period), and on Postgres the driver opens a transaction
   for the duration of the cursor.

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
shared between tasks**. Each async task will have its own connection and
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
Conversely, if you don't have that much load, the async wrapper adds complexity
and overhead for no measurable benefit.

To use SQLite in an async environment anyways, it is strongly recommended to
use WAL-mode at a minimum, which allows multiple readers to co-exist with a
single writer:

.. code-block:: python

   db = AsyncSqliteDatabase('app.db', pragmas={'journal_mode': 'wal'})

.. note::
   In-memory databases (``':memory:'``) always use a single connection
   regardless of ``pool_size`` - pooled in-memory connections would each be
   a separate, empty database.


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

Fix with an explicit async fetch, which also caches the related instance so
subsequent plain attribute access is free:

.. code-block:: python

   user = await tweet.afetch(Tweet.user)
   print(user.name)
   print(tweet.user.name)   # OK - cached, no query.

Or by selecting the related model in the original query:

.. code-block:: python

   query = Tweet.select(Tweet, User).join(User)
   tweet = await db.get(query)
   print(tweet.user.name)   # OK - no extra query.

Or by wrapping the access in ``db.run()``:

.. code-block:: python

   name = await db.run(lambda: tweet.user.name)

For strict codebases, disable lazy-loading on the foreign-key field
(``lazy_load=False``) and enforce selecting relations via explicit joins;
attribute access then returns the column value rather than performing a
query, and ``afetch()`` on such a field raises ``ValueError`` rather than
guessing.

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

   # Execute the back-reference query directly:
   for tweet in await user.tweets.aexecute():
       print(tweet.content)

   # Using db.list():
   for tweet in await db.list(user.tweets):
       print(tweet.content)

   # Using db.run() with list():
   tweets = await db.run(list, user.tweets)

   # Use prefetch:
   users = await db.run(
       prefetch,
       User.select().where(User.username.in_(('Charlie', 'Huey', 'Mickey'))),
       Tweet.select())

   for user in users:
       for tweet in user.tweets:  # Prefetched - no extra query.
           print(tweet.content)

Indirect query triggers
^^^^^^^^^^^^^^^^^^^^^^^

Helpers that walk model relations can also trigger lazy queries - e.g.
pydantic validation of an instance (``Schema.model_validate(obj)``) or
``model_to_dict(obj, backrefs=True)``. Run them inside the bridge unless
relations were eagerly loaded:

.. code-block:: python

   data = await db.run(UserSchema.model_validate, user)

Any code that triggers a database query must execute via ``db.run()``,
``query.aexecute()``, or one of the async helper methods.

Sharing one query object across tasks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Select queries cache their result on the query object. Two tasks that
concurrently await the same not-yet-executed select will each execute it -
the cache is only populated after the bridge yields to the event loop -
and the last writer wins the cache. Give each task its own query object,
or ``clone()`` a shared one.

Tasks spawned inside a transaction
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Connections are task-local. A task spawned with ``asyncio.gather()`` or
``asyncio.create_task()`` inside an ``async with db.atomic()`` block
acquires its *own* connection and therefore runs **outside** the
transaction: its writes commit (or fail) independently and are not rolled
back with the parent. This is by design - it is what makes concurrent
tasks safe from interleaving each other's transactions - but it means
transactional work must stay within a single task:

.. code-block:: python

   async with db.atomic():
       await asyncio.gather(
           User.acreate(name='b'),      # Own connection, NOT in the
           User.acreate(name='c'))      # transaction - commits even if the
                                        # parent block rolls back.
       await User.acreate(name='a')     # In the transaction.

Beware of lock interplay on top of the transaction semantics: on a
single-writer database like SQLite, a task that gathers write-tasks *after*
the parent transaction has itself written will deadlock until the busy
timeout - the children block on the parent's write lock while the parent
awaits the children. In-memory SQLite databases are stricter still: they
use a single connection, so any task gathered while the parent holds the
connection will wait for the full ``acquire_timeout`` and then raise. If
concurrent tasks are part of the design, keep transactions short and
prefer Postgres, or structure the work so tasks do not overlap an open
write transaction.

Design note: why not ``await User.select()``?
---------------------------------------------

Queries are deliberately not awaitable. Making every query object awaitable
flips ``inspect.isawaitable(query)`` to ``True`` in every installation,
including purely synchronous ones, and parts of the ecosystem dispatch on
exactly such checks (template engines that auto-await attribute access,
ASGI frameworks that duck-type async iterables) - the blast radius extends
well beyond async users. A forgotten ``await`` on a custom awaitable is
also silent: Python's "coroutine was never awaited" warning applies only to
real coroutines, so an unawaited ``User.insert(...)`` would simply never
execute, without a sound. The ``a``-prefixed methods are ordinary
coroutines - forget the ``await`` and Python itself warns you. The nearest
supported spelling, ``await User.select().aexecute()``, is exactly such a
coroutine. Django's async ORM reached the same conclusion (DEP 0009).

This is a current position, not a permanent one. Adding awaitable queries
later is fully backward-compatible with everything described on this page;
if real-world usage demonstrates the need, the door is open.

API Reference
-------------

.. class:: AsyncDatabaseMixin(database, pool_size=10, pool_min_size=1, acquire_timeout=10, **kwargs)

   :param str database: Database name or filename for SQLite.
   :param int pool_size: Maximum size of the connection pool.
   :param int pool_min_size: Minimum size of the connection pool (ignored
       for SQLite, which always creates ``pool_size`` connections).
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

      Release the current task's connection back to the pool. Like
      synchronous :meth:`~Database.close`, raises ``OperationalError`` if
      called while a transaction is open. Connections reclaimed from tasks
      that exited uncleanly have any open transaction rolled back, so the
      next acquirer always sees a clean connection.

   .. method:: close_pool()
      :async:

      Close the underlying connection pool and release all active connections.

      This method should be called during application shutdown.

      Connections orphaned by tasks that exited without closing them are
      reclaimed as well, with any open transaction rolled back.

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

      :param Query query: any query - select, insert, update, delete,
          raw or compound.
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

      The query is bound to this database before executing. The convenience
      methods (:meth:`get`, :meth:`list`, :meth:`scalar`, :meth:`count` and
      :meth:`exists`) execute the query against whatever database it is
      already bound to. Queries bound to an async database can also be
      executed with :meth:`BaseQuery.aexecute` (``await query.aexecute()``),
      which executes against the bound database without modifying the
      binding.

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

   .. method:: first(query, n=1)
      :async:

      :param Query query: a Select query.
      :param int n: number of rows.

      Execute a SELECT query and return the first row, or ``None`` if the
      result is empty. With ``n > 1``, return up to the first ``n`` rows as
      a list. Like the synchronous :meth:`SelectBase.first`, a LIMIT is
      applied to the query.

   .. method:: list(query)
      :async:

      :param Query query: a Select query, or an Insert, Update or Delete
          query that utilizes RETURNING.

      Execute a SELECT (or INSERT/UPDATE/DELETE with RETURNING) and return
      a list of results.

      Example:

      .. code-block:: python

         query = User.select().order_by(User.username)
         for user in await db.list(query):
             print(user.username)

   .. method:: iterate(query, buffer_size=None)
      :async:

      :param Query query: a Select query to stream results from using an async
         generator.
      :param int buffer_size: Number of rows fetched per round-trip
         (default 100).

      :meth:`~AsyncDatabaseMixin.iterate` method uses server-side cursors
      (MySQL and Postgres) to efficiently stream large result-sets.

      Example:

      .. code-block:: python

         query = User.select().order_by(User.username)
         async for user in db.iterate(query):
             print(user.username)

      .. note::
         While streaming, the iterator holds the task's connection. Another
         query on the same connection - including a second ``iterate()`` -
         waits briefly for an abandoned iterator to finalize (e.g. after
         breaking out of the loop early), then raises
         :class:`InterfaceError`. The grace period is the connection
         wrapper's ``streaming_timeout`` attribute (default 5 seconds). To
         release the connection promptly after a partial iteration,
         ``await`` the generator's ``aclose()`` method.

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

   .. method:: transaction()
               savepoint()

      Like :meth:`atomic`, async-aware wrappers of peewee's transaction and
      savepoint context-managers, supporting both ``async with`` and
      ``with``. Transaction objects additionally provide ``acommit()`` and
      ``arollback()`` coroutines, mirroring peewee's ``commit()`` and
      ``rollback()``.

      .. note::
         On Postgresql, :meth:`atomic`, :meth:`transaction` and
         :meth:`savepoint` all return a transaction manager built directly
         on asyncpg: arguments are forwarded to asyncpg's
         ``Connection.transaction()`` (e.g. ``isolation=``, ``readonly=``),
         and nested blocks are implemented as savepoints by asyncpg's
         transaction nesting.

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

   .. attribute:: Model

      Property which returns a base model class bound to this database,
      including the async model methods (see :class:`AsyncModelMixin`).
      Analogous to :attr:`Database.Model`.

.. method:: BaseQuery.aexecute(database=None)
   :async:

   :param database: an async database; defaults to the query's bound
       database.
   :return: the normal return-value for the query type.

   Async counterpart of :py:meth:`~BaseQuery.execute`, defined on all query
   types (select, insert, update, delete, raw and compound queries). An
   explicit ``database`` is used for that execution only - unlike
   :meth:`AsyncDatabaseMixin.aexecute`, the query's binding is never
   modified. Raises ``InterfaceError`` if the query is not bound to a
   database, and ``AttributeError`` if the bound database is synchronous
   (a query bound to an uninitialized :class:`DatabaseProxy` also raises
   ``AttributeError``).

   .. code-block:: python

      users = await User.select().order_by(User.username).aexecute()


.. class:: AsyncModelMixin()

   Mixin providing ``a``-prefixed coroutine counterparts of the
   :class:`Model` methods that read or write rows. Every method is a thin
   delegation: the synchronous implementation runs inside the greenlet
   bridge, so behaviors like ``only_save_dirty``, composite keys,
   :py:meth:`~Model.get_or_create`'s integrity-error recovery and
   ``playhouse.signals`` hooks all apply unchanged.

   The model must be bound to an async database (e.g.
   :class:`AsyncSqliteDatabase`); calling an async model method on a model
   bound to a synchronous database raises ``InterfaceError``.

   Classmethods: ``acreate``, ``aget``, ``aget_or_none``, ``aget_by_id``,
   ``aget_or_create``, ``aset_by_id``, ``adelete_by_id``, ``abulk_create``,
   ``abulk_update``. Each accepts the same arguments and returns the same
   values as its synchronous counterpart.

   .. method:: asave(force_insert=False, only=None)
      :async:

      Coroutine counterpart of :py:meth:`Model.save`. Returns the number of
      rows modified (or ``False`` for a no-op save when ``only_save_dirty``
      is enabled).

   .. method:: adelete_instance(recursive=False, delete_nullable=False)
      :async:

      Coroutine counterpart of :py:meth:`Model.delete_instance`.

   .. method:: afetch(field)
      :async:

      :param field: a :class:`ForeignKeyField` on this model (or its name).

      Explicitly resolve a lazy foreign-key relation. If the related object
      is already loaded (via a join, :meth:`~AsyncDatabaseMixin.aprefetch`,
      or a prior ``afetch()``), it is returned immediately with no query.
      Otherwise the related row is fetched on the event loop and cached on
      the instance, so subsequent plain attribute access is free.

      Raises ``ValueError`` for non-foreign-key fields, and for fields
      declared with ``lazy_load=False`` (fetch those explicitly, e.g.
      ``await Rel.aget_by_id(obj.rel_id)``). A nullable, unset foreign key
      resolves to ``None``. For fetching relations in bulk, use
      :meth:`~AsyncDatabaseMixin.aprefetch`.

      .. code-block:: python

         tweet = await Tweet.aget_by_id(tweet_id)
         user = await tweet.afetch(Tweet.user)

.. class:: AsyncModel()

   ``Model`` subclass with :class:`AsyncModelMixin` applied - a convenient
   explicit base class:

   .. code-block:: python

      class BaseModel(AsyncModel):
          class Meta:
              database = db

.. class:: AsyncSqliteDatabase(database, **kwargs)

   Async SQLite database implementation.

   Uses ``aiosqlite`` with a simple pool of ``pool_size`` connections
   (``pool_min_size`` is ignored).

   Inherits from :class:`AsyncDatabaseMixin` and :class:`SqliteDatabase`.

.. class:: AsyncPostgresqlDatabase(database, **kwargs)

   Async Postgresql database implementation.

   Uses ``asyncpg`` and the driver's native connection pool. Affected-row
   counts for UPDATE and DELETE are derived from the command status
   reported by the server.

   A connection URL may be given as the ``database`` argument
   (``'postgresql://...'``), and ``isolation_level`` accepts a level name
   (e.g. ``'SERIALIZABLE'``) which is applied to each pooled connection.

   Inherits from :class:`AsyncDatabaseMixin` and :class:`PostgresqlDatabase`.

   .. note::
      :meth:`Model.bulk_update` is not supported with asyncpg: the CASE
      expression's untyped parameters are resolved as ``text`` by the
      server, which fails for non-text columns.

.. class:: AsyncMySQLDatabase(database, **kwargs)

   Async MySQL / MariaDB database implementation.

   Uses ``aiomysql`` and the driver's native connection pool. The server
   version - used, e.g., to distinguish MySQL from MariaDB when generating
   :class:`JSONField` SQL - is detected when the first connection is
   acquired.

   Inherits from :class:`AsyncDatabaseMixin` and :class:`MySQLDatabase`.

.. class:: MissingGreenletBridge(RuntimeError)

   Raised when Peewee attempts to execute a query outside a greenlet context.
   This indicates that a query was triggered outside of ``db.run()`` or an
   async helper call.
