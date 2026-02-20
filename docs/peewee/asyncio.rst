.. _asyncio:

Asyncio Support
===============

Peewee provides a thin asyncio compatibility layer that allows existing APIs to
be used safely with the asyncio event loop. Unlike other peewee async projects,
this implementation uses ``greenlet`` to execute Peewee's internally synchronous
code while allowing async database operations to run on the event loop.

When database I/O is required, execution is suspended and control is returned
to the event loop. Once the awaitable completes, execution resumes exactly
where it left off.

The Peewee asyncio implementation can be found in ``playhouse.pwasyncio``:

.. code-block:: python

    from playhouse.pwasyncio import AsyncPostgresqlDatabase
    from playhouse.pwasyncio import AsyncMySQLDatabase
    from playhouse.pwasyncio import AsyncSqliteDatabase

The :py:meth:`~AsyncDatabaseMixin.run` method is the primary entry point for
async execution. It accepts a synchronous callable and arbitrary arguments.
When the underlying database driver would block, control is yielded back to the
asyncio event-loop.

.. code-block:: python

    await db.run(User.create, name='Alice')

If you prefer a more ``async``-native approach, a number of helper methods are
available on the async ``Database`` classes:

.. code-block:: python

    import asyncio
    from peewee import *
    from playhouse.pwasyncio import AsyncSqliteDatabase

    db = AsyncSqliteDatabase('example.db')

    class User(db.Model):
        name = TextField()

    async def demo():
        async with db:
            # Asynchronously create table(s).
            await db.acreate_tables([User])

            # Create a new user.
            user = await db.run(User.create, name='Charlie')

            # Retrieve new user from the database.
            user_db = await db.get(User.select().where(User.name == 'Charlie'))
            assert user.name == user_db.name == 'Charlie'

            # Atomicity with async context managers.
            async with db.atomic():
                # Construct a normal Peewee INSERT query.
                iq = (User
                      .insert_many([{'name': 'Alice'}, {'name': 'Bob'}])
                      .returning(User))

                # Execute the query asynchronously, retrieving results.
                users = await db.aexecute(iq)
                print('Added users: %s' % list(users))

            # Retrieve list of users from database.
            for user in await db.list(User.select().order_by(User.name)):
                print(user.name)

        # Close the pool - the connection was released, but it still remains inside
        # the pool, so this ensures we are ready to shutdown completely.
        await db.close_pool()

    asyncio.run(demo())

Here is the same example as above demonstrating how :py:meth:`~AsyncDatabaseMixin.run`
can be used to wrap synchronous ORM operations to be async:

.. code-block:: python

    import asyncio
    from peewee import *
    from playhouse.pwasyncio import AsyncSqliteDatabase

    db = AsyncSqliteDatabase('example.db')

    class User(db.Model):
        name = TextField()

    async def demo():
        async with db:
            # Asynchronously create table(s).
            await db.run(db.create_tables, [User])

            # Create a new user.
            user = await db.run(User.create, name='Charlie')

            # Retrieve new user from the database using a callable.
            def get_user():
                return User.select().where(User.name == 'Charlie').get()

            user_db = await db.run(get_user)
            assert user.name == user_db.name == 'Charlie'

            # Atomicity with a normal context manager.
            def bulk_insert():
                with db.atomic():
                    iq = (User
                          .insert_many([{'name': 'Alice'}, {'name': 'Bob'}])
                          .returning(User))
                    users = iq.execute()
                    print('Added users: %s' % list(users))

            await db.run(bulk_insert)

            # Retrieve list of users from database.
            users = await db.run(list, User.select().order_by(User.name))
            for user in users:
                print(user.name)

        # Close the pool - the connection was released, but it still remains inside
        # the pool, so this ensures we are ready to shutdown completely.
        await db.close_pool()

    asyncio.run(demo())

When running Peewee ORM code, you can choose between the two execution patterns
depending on how explicit you want to be. See :ref:`async-helpers` for details
on the available ``async``-friendly helper methods.

Supported Backends
------------------

================  ============  ===================================
Database          Driver        Database Class
================  ============  ===================================
SQLite            aiosqlite     :py:class:`AsyncSqliteDatabase`
MySQL / MariaDB   aiomysql      :py:class:`AsyncMySQLDatabase`
PostgreSQL        asyncpg       :py:class:`AsyncPostgresqlDatabase`
================  ============  ===================================

Installation
------------

This module requires Python 3.8 or newer and depends on Peewee and greenlet,
along with whatever async-compatible driver you intend to use.

.. code-block:: console

    pip install peewee greenlet
    pip install asyncpg  # Postgresql.
    pip install aiomysql  # MySQL.
    pip install aiosqlite  # Sqlite.

Overview
--------

Async database classes mirror Peewee's standard database classes and can
generally be used as drop-in replacements.

.. code-block:: python

    from playhouse.pwasyncio import AsyncSqliteDatabase

    db = AsyncSqliteDatabase('example.db', pragmas={'journal_mode': 'wal'})


Models are defined as expected:

.. code-block:: python

    class User(db.Model):
        name = CharField()

Executing Queries
^^^^^^^^^^^^^^^^^

Peewee queries must be executed using the database :py:meth:`~AsyncDatabaseMixin.run` method.

.. code-block:: python

    from peewee import *
    from playhouse.pwasyncio import AsyncSqliteDatabase

    db = AsyncSqliteDatabase('example.db')

    class User(db.Model):
        name = CharField()

    async def main():
        await db.acreate_tables([User])

        # Use the db.run() helper with a synchronous callable.
        await db.run(User.create, name='Alice')

        # OR use an awaitable helper method.
        user = await db.get(User.select().where(User.name == 'Alice'))

        def add_users():
            with db.atomic():
                User.create(name='Bob')
                User.create(name='Charlie')

            with db.atomic():
                alice = User.get(User.name == 'Alice')
                alice.name = 'Alyce'  # She spells it fancy now.
                alice.save()

            return list(User.select().order_by(User.name))

        users = await db.run(add_users)
        print([u.name for u in users])

        await db.adrop_tables([User])
        await db.close_pool()

    asyncio.run(main())

The :py:meth:`~AsyncDatabaseMixin.run` method ensures synchronous Peewee code
is executed safely inside the event loop. Any arbitrary code can be wrapped in
a function and sent to the :py:meth:`~AsyncDatabaseMixin.run` method.

.. _async-helpers:

Helper Methods
^^^^^^^^^^^^^^

The :py:class:`AsyncDatabaseMixin` provides a number of async/await-friendly
helpers for common operations.

The most general-purpose helper is the :py:meth:`AsyncDatabaseMixin.run`
method, which accepts a callable and arbitrary arguments, and runs it in an
asynchronous context.

Database connection can be opened and closed asynchronously using the
following helpers:

* :py:meth:`~AsyncDatabaseMixin.aconnect` - acquire a connection from the pool for the current task.
* :py:meth:`~AsyncDatabaseMixin.aclose` - release the connection back to the pool.
* :py:meth:`~AsyncDatabaseMixin.close_pool` - close the connection pool.

Several common query patterns are exposed as async helpers:

* :py:meth:`~AsyncDatabaseMixin.atomic` - can be used as an async context manager for created arbitrarily nested transactions.
* :py:meth:`~AsyncDatabaseMixin.get` - get a single model instance or result.
* :py:meth:`~AsyncDatabaseMixin.list` - get the results of a query (0...many).
* :py:meth:`~AsyncDatabaseMixin.scalar` - get a single, scalar value from a query.
* :py:meth:`~AsyncDatabaseMixin.aexecute` - execute a Query object.
* :py:meth:`~AsyncDatabaseMixin.aexecute_sql` - execute a SQL query.
* :py:meth:`~AsyncDatabaseMixin.acreate_tables` - create one or more tables.
* :py:meth:`~AsyncDatabaseMixin.adrop_tables` - drop one or more tables.

.. code-block:: python

    import asyncio
    from peewee import *
    from playhouse.pwasyncio import AsyncSqliteDatabase

    db = AsyncSqliteDatabase('example.db')

    class User(db.Model):
        name = CharField()

    async def main():
        async with db:
            await db.acreate_tables([User])

            insert = (User
                      .insert_many([(f'user-{i}',) for i in range(10)])
                      .returning(User))
            for new_user in await db.aexecute(insert):
                print(f'Added user {new_user.name}')

            user = await db.get(User.select().where(User.id == 1))

            users = await db.list(User.select())
            print(f'Found {len(users)} users via select')

            async with db.atomic():
                user = await db.run(User.create, name='Charlie')
                print(f'Added new user with id={user.id}')

            count = await db.scalar(User.select(fn.COUNT(User.id)))
            print(f'COUNT returns {count} users')

            await db.adrop_tables([User])

        # Close all connections and exit cleanly.
        await db.close_pool()

    asyncio.run(main())

Connections and Pooling
-----------------------

Like non-async Peewee, which uses a connection-per-thread, each asyncio task
maintains its own connection state. This avoids sharing connections across
concurrent tasks. Internally, we try to use the driver-provided pools where
possible.

Connections can be acquired and released from the pool using the following
helpers:

* :py:meth:`~AsyncDatabaseMixin.aconnect`
* :py:meth:`~AsyncDatabaseMixin.aclose`
* :py:meth:`~AsyncDatabaseMixin.close_pool` - close the pool and exit cleanly.

Alternatively, you can use the database class as a context manager:

.. code-block:: python

    db = AsyncSqliteDatabase('example.db')

    await db.aconnect()
    # Do some database work.
    await db.aclose()

    # Or use the context manager:
    async with db:
        # Do some database work.
        ...

SQLite
^^^^^^

SQLite uses a single shared connection, as the underlying database does not
support concurrent writers.

Generally SQLite is a poor fit for asynchronous workflows where writes may be
coming in at any time, and transactions may be interleaved across multiple
writers. Furthermore, SQLite does not do any network I/O.

The SQLite implementation is provided mostly for testing and local development.

MySQL and PostgreSQL
^^^^^^^^^^^^^^^^^^^^

MySQL and PostgreSQL use the driver's native connection pool.

Pool configuration options include:

* ``pool_size`` – Maximum number of connections
* ``pool_min_size`` – Minimum pool size
* ``acquire_timeout`` – Timeout when acquiring a connection

.. code-block:: python

    db = AsyncPostgresqlDatabase(
        'peewee_test',
        host='localhost',
        user='postgres',
        pool_size=10,
        pool_min_size=1,
        acquire_timeout=10)

Transactions
------------

Transactions and savepoints are managed using async context managers.

.. code-block:: python

    async with db.atomic():
        await db.run(User.create, name='Alice')

        async with db.atomic():
            await db.run(User.create, name='Bob')

Nested atomic blocks behave the same as in synchronous Peewee code.

Implementation Notes
--------------------

Synchronous ORM code runs inside a greenlet, and async I/O is bridged
explicitly by Peewee using two helpers, ``greenlet_spawn()`` and ``await_()``.
The ``greenlet_spawn()`` helper runs synchronous code, but can be suspended and
resumed in order to yield to the asyncio event loop. Yielding is done by the
``await_()`` helper, which suspends the greenlet and passes control to the
asyncio coroutine.

Peewee wraps all this up in a general-purpose :py:meth:`AsyncDatabaseMixin.run`
method, which is the entrypoint for pretty much all async operations:

.. code-block:: python

    from playhouse.pwasyncio import *

    async def demo():
        db = AsyncSqliteDatabase(':memory:')
        def work():
            print(db.execute_sql('select 1').fetchall())
        await db.run(work)

    asyncio.run(demo())  # prints [(1,)]

The basic flow goes something like this:

1. The above code eventually hits the ``db.run()`` method. This method calls
   the ``greenlet_spawn()`` function, creating a resumable coroutine wrapping our synchronous code.
2. The greenlet begins executing the synchronous Peewee code.
3. We call ``db.execute_sql('select 1')``
4. The async database implementation calls our special ``await_()`` helper,
   which switches control back to the event loop.
5. The event-loop awaits the coroutine, e.g. ``await conn.execute(...)``,
   awaiting the results from the cursor before handing them back.
6. The result cursor is sent back to the greenlet, and the greenlet resumes.
7. ``db.execute_sql()`` returns and the rest of the code continues normally.
8. We call ``fetchall()`` on the result cursor, which returns all the rows
   loaded during (5).

If we try to run :py:meth:`~AsyncDatabaseMixin.execute_sql()` outside of the
greenlet helper, Peewee will raise a :py:class:`MissingGreenletBridge` exception:

.. code-block:: python

    async def demo():
        db = AsyncSqliteDatabase(':memory:')
        print(db.execute_sql('select 1').fetchall())

    # MissingGreenletBridge: Attempted query select 1 (None) outside greenlet runner.
    asyncio.run(demo())

Peewee provides a number of async-ready helper methods for common operations,
so the ``run()`` helper can be avoided:

.. code-block:: python

    from playhouse.pwasyncio import *

    async def demo():
        db = AsyncSqliteDatabase(':memory:')
        curs = await db.aexecute_sql('select 1')
        print(curs.fetchall())

    asyncio.run(demo())  # prints [(1,)]

.. note::
    Obtaining the results from the cursor does not happen asynchronously (e.g.
    we do not call ``print(await curs.fetchall())``). Internally Peewee **does**
    await fetching the results from the cursor, but the rows are all loaded
    before the cursor is returned to the caller. This ensures consistency with
    existing behavior, though in future versions we may add support for
    streaming cursor results (via Postgres server-side cursors).

Sharp Corners
-------------

There are limitations to what can be achieved with the approach described above.
The main one I foresee causing problems is lazy foreign-key resolution. Consider this example:

.. code-block:: python

    tweet = await db.get(Tweet.select())
    print(tweet.user.name)  # Fails.
    # MissingGreenletBridge: Attempted query SELECT ...outside greenlet runner.

This fails because the relationship ``tweet.user`` was not explicitly fetched,
so Peewee attempts to issue a ``SELECT`` query to get the related user. This
fails because we are not operating inside the greenlet-bridged environment.

One solution is to resolve foreign keys inside :py:meth:`~AsyncDatabaseMixin.run`:

.. code-block:: python

    print(await db.run(lambda: tweet.user.name))

Even better is to select the related object explicitly:

.. code-block:: python

    query = Tweet.select(Tweet, User).join(User)
    tweet = await db.get(query)
    print(tweet.user.name)  # OK, no extra SELECT required.

In a similar way, iterating the related objects requires a query:

.. code-block:: python

    for tweet in user.tweet_set:
        print(tweet.message)
    # MissingGreenletBridge: Attempted query SELECT ... outside greenlet runner.

Like above, there are a few ways you can accomplish this:

.. code-block:: python

    # Use the db.run() helper:
    tweets = await db.run(list, user.tweet_set)
    for tweet in tweets:
        print(tweet.message)

    # Use the db.list() helper:
    for tweet in await db.list(user.tweet_set):
        print(tweet.message)

    # Use prefetch (not a great fit, but just to demonstrate):
    user_query = User.select().where(User.id == user.id)
    tweet_query = Tweet.select()
    user, = await db.run(prefetch, user_query, tweet_query)
    for tweet in user.tweet_set:
        print(tweet.message)

Overall these are the main issues I see arising, but as things come up I may
expand this section or work to find other solutions to the problems.

API
---

.. py:class:: AsyncDatabaseMixin(database, pool_size=10, pool_min_size=1, acquire_timeout=10, validate_conn_timeout=2, **kwargs)

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

    This mixin provides asyncio execution support for Peewee database classes.
    It is not intended to be used directly, but instead forms the base for the
    concrete ``AsyncDatabase`` implementations.

    Each asyncio task maintains its own connection state. Connections are
    acquired and released back to the pool when the task completes or the
    database context exits.

    .. py:method:: run(fn, *args, **kwargs)
        :async:

        :param fn: A synchronous callable.
        :returns: The return value of ``fn``.

        Execute a synchronous callable inside a greenlet and return the result
        asynchronously.

        This method is the primary entry point for executing Peewee ORM
        operations in an asyncio context.

    .. py:method:: aconnect()
        :async:

        :returns: A wrapped async connection.

        Establish a connection to the database for the currently-running asyncio
        task, if one is not already open.

    .. py:method:: aclose()
        :async:

        Close and release the connection associated with the current asyncio
        task.

    .. py:method:: close_pool()
        :async:

        Close the underlying connection pool and release all active connections.

        This method should be called during application shutdown.

    .. py:method:: __aenter__()
        :async:

        Enter an async database context, acquiring a connection.

    .. py:method:: __aexit__(exc_type, exc, tb)
        :async:

        Exit the async database context, releasing the connection.

    .. py:method:: aexecute(query)
        :async:

        :param Query query: a Select, Insert, Update or Delete query.
        :return: the normal return-value for the query type.

        Execute a query asynchronously.

    .. py:method:: get(query)
        :async:

        :param Query query: a Select query.

        Execute a query and return a single model instance.

    .. py:method:: list(query)
        :async:

        :param Query query: a Select query, or an Insert, Update or Delete
            query that utilizes RETURNING.

        Execute a query and return a list of results.

    .. py:method:: scalar(query)
        :async:

        :param Query query: a Select query.

        Execute a query and return a scalar value.

    .. py:method:: atomic()

        :returns: An :py:class:`async_atomic` instance.

        Return an asyncio-aware atomic transaction context manager.
        Supports use as a synchronous or async context manager.

    .. py:method:: acreate_tables(models, **options)
        :async:

        Asynchronously create database tables.

    .. py:method:: adrop_tables(models, **options)
        :async:

        Asynchronously drop database tables.

    .. py:method:: aexecute_sql(sql, params=None)
        :async:

        :param str sql: SQL query to execute.
        :param tuple params: Optional query parameters.
        :returns: A :py:class:`CursorAdapter` instance.

        Execute a SQL query asynchronously using the underlying async driver.

    .. py:method:: execute_sql(sql, params=None)

        Synchronous wrapper around :py:meth:`aexecute_sql`.

        This method may only be called from code executing inside
        :py:meth:`~AsyncDatabaseMixin.run`.


.. py:class:: AsyncSqliteDatabase(database, **kwargs)

    Async SQLite database implementation.

    Uses ``aiosqlite`` and maintains a single shared connection. Pool-related
    configuration options are ignored.

    Inherits from :py:class:`AsyncDatabaseMixin` and
    :py:class:`peewee.SqliteDatabase`.

.. py:class:: AsyncMySQLDatabase(database, **kwargs)

    Async MySQL / MariaDB database implementation.

    Uses ``aiomysql`` and the driver's native connection pool.

    Inherits from :py:class:`AsyncDatabaseMixin` and
    :py:class:`peewee.MySQLDatabase`.

.. py:class:: AsyncPostgresqlDatabase(database, **kwargs)

    Async PostgreSQL database implementation.

    Uses ``asyncpg`` and the driver's native connection pool.

    Inherits from :py:class:`AsyncDatabaseMixin` and
    :py:class:`peewee.PostgresqlDatabase`.

.. py:class:: MissingGreenletBridge(RuntimeError)

    Exception that is raised when Peewee attempts to run a blocking operation
    like ``execute_sql()`` outside a greenlet-spawn context. Generally
    indicates that you have attempted to execute a query outside of
    ``db.run()`` or without using one of the async helper methods.
