.. _crdb:

Cockroach Database
------------------

`CockroachDB <https://www.cockroachlabs.com>`_ (CRDB) is well supported by
peewee.

.. code-block:: python

    from playhouse.cockroachdb import CockroachDatabase

    db = CockroachDatabase('my_app', user='root', host='10.1.0.8')

If you are using `Cockroach Cloud <https://cockroachlabs.cloud/>`_, you may
find it easier to specify the connection parameters using a connection-string:

.. code-block:: python

    db = CockroachDatabase('postgresql://root:secret@host:26257/defaultdb...')

.. note:: CockroachDB requires the ``psycopg2`` (postgres) Python driver.

.. note::
    CockroachDB installation and getting-started guide can be
    found here: https://www.cockroachlabs.com/docs/stable/install-cockroachdb.html


.. _crdb_ssl:

SSL Configuration
^^^^^^^^^^^^^^^^^

SSL certificates are strongly recommended when running a Cockroach cluster.
Psycopg2 supports SSL out-of-the-box, but you may need to specify some
additional options when initializing your database:

.. code-block:: python

    db = CockroachDatabase(
        'my_app',
        user='root',
        host='10.1.0.8',
        sslmode='verify-full',  # Verify the cert common-name.
        sslrootcert='/path/to/root.crt')


    # Or, alternatively, specified as part of a connection-string:
    db = CockroachDatabase('postgresql://root:secret@host:26257/dbname'
                           '?sslmode=verify-full&sslrootcert=/path/to/root.crt'
                           '&options=--cluster=my-cluster-xyz')

More details about client verification can be found on the `libpq docs <https://www.postgresql.org/docs/9.1/libpq-ssl.html>`_.

Cockroach Extension APIs
^^^^^^^^^^^^^^^^^^^^^^^^

The ``playhouse.cockroachdb`` extension module provides the following classes
and helpers:

* :py:class:`CockroachDatabase` - a subclass of :py:class:`PostgresqlDatabase`,
  designed specifically for working with CRDB.
* :py:class:`PooledCockroachDatabase` - like the above, but implements
  connection-pooling.
* :py:meth:`~CockroachDatabase.run_transaction` - runs a function inside a
  transaction and provides automatic client-side retry logic.

Special field-types that may be useful when using CRDB:

* :py:class:`UUIDKeyField` - a primary-key field implementation that uses
  CRDB's ``UUID`` type with a default randomly-generated UUID.
* :py:class:`RowIDField` - a primary-key field implementation that uses CRDB's
  ``INT`` type with a default ``unique_rowid()``.
* :py:class:`JSONField` - same as the Postgres :py:class:`BinaryJSONField`, as
  CRDB treats JSON as JSONB.
* :py:class:`ArrayField` - same as the Postgres extension (but does not support
  multi-dimensional arrays).

CRDB is compatible with Postgres' wire protocol and exposes a very similar
SQL interface, so it is possible (though **not recommended**) to use
:py:class:`PostgresqlDatabase` with CRDB:

1. CRDB does not support nested transactions (savepoints), so the
   :py:meth:`~Database.atomic` method has been implemented to enforce this when
   using :py:class:`CockroachDatabase`. For more info :ref:`crdb-transactions`.
2. CRDB may have subtle differences in field-types, date functions and
   introspection from Postgres.
3. CRDB-specific features are exposed by the :py:class:`CockroachDatabase`,
   such as specifying a transaction priority or the ``AS OF SYSTEM TIME``
   clause.

.. _crdb-transactions:

CRDB Transactions
^^^^^^^^^^^^^^^^^

CRDB does not support nested transactions (savepoints), so the
:py:meth:`~Database.atomic` method on the :py:class:`CockroachDatabase` has
been modified to raise an exception if an invalid nesting is encountered. If
you would like to be able to nest transactional code, you can use the
:py:meth:`~Database.transaction` method, which will ensure that the outer-most
block will manage the transaction (e.g., exiting a nested-block will not cause
an early commit).

Example:

.. code-block:: python

    @db.transaction()
    def create_user(username):
        return User.create(username=username)

    def some_other_function():
        with db.transaction() as txn:
            # do some stuff...

            # This function is wrapped in a transaction, but the nested
            # transaction will be ignored and folded into the outer
            # transaction, as we are already in a wrapped-block (via the
            # context manager).
            create_user('some_user@example.com')

            # do other stuff.

        # At this point we have exited the outer-most block and the transaction
        # will be committed.
        return


CRDB provides client-side transaction retries, which are available using a
special :py:meth:`~CockroachDatabase.run_transaction` helper. This helper
method accepts a callable, which is responsible for executing any transactional
statements that may need to be retried.

Simplest possible example of :py:meth:`~CockroachDatabase.run_transaction`:

.. code-block:: python

    def create_user(email):
        # Callable that accepts a single argument (the database instance) and
        # which is responsible for executing the transactional SQL.
        def callback(db_ref):
            return User.create(email=email)

        return db.run_transaction(callback, max_attempts=10)

    huey = create_user('huey@example.com')

.. note::
    The ``cockroachdb.ExceededMaxAttempts`` exception will be raised if the
    transaction cannot be committed after the given number of attempts. If the
    SQL is mal-formed, violates a constraint, etc., then the function will
    raise the exception to the caller.

Example of using :py:meth:`~CockroachDatabase.run_transaction` to implement
client-side retries for a transaction that transfers an amount from one account
to another:

.. code-block:: python

    from playhouse.cockroachdb import CockroachDatabase

    db = CockroachDatabase('my_app')


    def transfer_funds(from_id, to_id, amt):
        """
        Returns a 3-tuple of (success?, from balance, to balance). If there are
        not sufficient funds, then the original balances are returned.
        """
        def thunk(db_ref):
            src, dest = (Account
                         .select()
                         .where(Account.id.in_([from_id, to_id])))
            if src.id != from_id:
                src, dest = dest, src  # Swap order.

            # Cannot perform transfer, insufficient funds!
            if src.balance < amt:
                return False, src.balance, dest.balance

            # Update each account, returning the new balance.
            src, = (Account
                    .update(balance=Account.balance - amt)
                    .where(Account.id == from_id)
                    .returning(Account.balance)
                    .execute())
            dest, = (Account
                     .update(balance=Account.balance + amt)
                     .where(Account.id == to_id)
                     .returning(Account.balance)
                     .execute())
            return True, src.balance, dest.balance

        # Perform the queries that comprise a logical transaction. In the
        # event the transaction fails due to contention, it will be auto-
        # matically retried (up to 10 times).
        return db.run_transaction(thunk, max_attempts=10)

CRDB APIs
^^^^^^^^^

.. py:class:: CockroachDatabase(database[, **kwargs])

    CockroachDB implementation, based on the :py:class:`PostgresqlDatabase` and
    using the ``psycopg2`` driver.

    Additional keyword arguments are passed to the psycopg2 connection
    constructor, and may be used to specify the database ``user``, ``port``,
    etc.

    Alternatively, the connection details can be specified in URL-form.

    .. py:method:: run_transaction(callback[, max_attempts=None[, system_time=None[, priority=None]]])

        :param callback: callable that accepts a single ``db`` parameter (which
            will be the database instance this method is called from).
        :param int max_attempts: max number of times to try before giving up.
        :param datetime system_time: execute the transaction ``AS OF SYSTEM TIME``
            with respect to the given value.
        :param str priority: either "low", "normal" or "high".
        :return: returns the value returned by the callback.
        :raises: ``ExceededMaxAttempts`` if ``max_attempts`` is exceeded.

        Run SQL in a transaction with automatic client-side retries.

        User-provided ``callback``:

        * **Must** accept one parameter, the ``db`` instance representing the
          connection the transaction is running under.
        * **Must** not attempt to commit, rollback or otherwise manage the
          transaction.
        * **May** be called more than one time.
        * **Should** ideally only contain SQL operations.

        Additionally, the database must not have any open transactions at the
        time this function is called, as CRDB does not support nested
        transactions. Attempting to do so will raise a ``NotImplementedError``.

        Simplest possible example:

        .. code-block:: python

            def create_user(email):
                def callback(db_ref):
                    return User.create(email=email)

                return db.run_transaction(callback, max_attempts=10)

            user = create_user('huey@example.com')

.. py:class:: PooledCockroachDatabase(database[, **kwargs])

    CockroachDB connection-pooling implementation, based on
    :py:class:`PooledPostgresqlDatabase`. Implements the same APIs as
    :py:class:`CockroachDatabase`, but will do client-side connection pooling.

.. py:function:: run_transaction(db, callback[, max_attempts=None[, system_time=None[, priority=None]]])

    Run SQL in a transaction with automatic client-side retries. See
    :py:meth:`CockroachDatabase.run_transaction` for details.

    :param CockroachDatabase db: database instance.
    :param callback: callable that accepts a single ``db`` parameter (which
        will be the same as the value passed above).

    .. note::
        This function is equivalent to the identically-named method on
        the :py:class:`CockroachDatabase` class.

.. py:class:: UUIDKeyField()

    UUID primary-key field that uses the CRDB ``gen_random_uuid()`` function to
    automatically populate the initial value.

.. py:class:: RowIDField()

    Auto-incrementing integer primary-key field that uses the CRDB
    ``unique_rowid()`` function to automatically populate the initial value.

See also:

* :py:class:`BinaryJSONField` from the Postgresql extension (available in the
  ``cockroachdb`` extension module, and aliased to ``JSONField``).
* :py:class:`ArrayField` from the Postgresql extension.
