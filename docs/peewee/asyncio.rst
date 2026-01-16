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

Example:

.. code-block:: python

    import asyncio
    from peewee import *
    from playhouse.pwasyncio import AsyncSqliteDatabase

    db = AsyncSqliteDatabase('example.db')

    class User(db.Model):
        name = CharField()

    async def main():
        await db.acreate_tables([User])

        async with db.atomic():
            await db.run(User.create, name='Alice')

        users = await db.list(User.select())
        print(users)  # Prints [<User: 1>]

        await db.close_pool()

    asyncio.run(main())

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

API
---

.. py:class:: AsyncDatabaseMixin(database[, pool_size=10[, pool_min_size=1[, acquire_timeout=10[, validate_conn_timeout=2[, **kwargs]]]]])

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

    .. py:method:: run(fn[, *args[, **kwargs]])
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

    .. py:method:: acreate_tables(models[, **options])
        :async:

        Asynchronously create database tables.

    .. py:method:: adrop_tables(models[, **options])
        :async:

        Asynchronously drop database tables.

    .. py:method:: aexecute_sql(sql[, params=None])
        :async:

        :param str sql: SQL query to execute.
        :param tuple params: Optional query parameters.
        :returns: A :py:class:`CursorAdapter` instance.

        Execute a SQL query asynchronously using the underlying async driver.

    .. py:method:: execute_sql(sql[, params=None])

        Synchronous wrapper around :py:meth:`aexecute_sql`.

        This method may only be called from code executing inside
        :py:meth:`~AsyncDatabaseMixin.run`.


.. py:class:: AsyncSqliteDatabase(database[, **kwargs])

    Async SQLite database implementation.

    Uses ``aiosqlite`` and maintains a single shared connection. Pool-related
    configuration options are ignored.

    Inherits from :py:class:`AsyncDatabaseMixin` and
    :py:class:`peewee.SqliteDatabase`.

.. py:class:: AsyncMySQLDatabase(database[, **kwargs])

    Async MySQL / MariaDB database implementation.

    Uses ``aiomysql`` and the driver's native connection pool.

    Inherits from :py:class:`AsyncDatabaseMixin` and
    :py:class:`peewee.MySQLDatabase`.

.. py:class:: AsyncPostgresqlDatabase(database[, **kwargs])

    Async PostgreSQL database implementation.

    Uses ``asyncpg`` and the driver's native connection pool.

    Inherits from :py:class:`AsyncDatabaseMixin` and
    :py:class:`peewee.PostgresqlDatabase`.
