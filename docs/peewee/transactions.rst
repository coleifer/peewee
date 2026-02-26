.. _transactions:

Transactions
============

A *transaction* groups one or more SQL statements into a single unit of work.
Either all of the statements succeed and are committed to the database, or none
of them are - the database rolls back to the state it was in before the
transaction began.

Peewee operates in *autocommit mode*: every statement that runs outside an
explicit transaction runs in its own implicit transaction. To group statements,
use the tools described in this document.

db.atomic
---------

:meth:`Database.atomic` is the recommended transaction API. :meth:`~Database.atomic`
can be used as a context manager or a decorator, and it handles nesting
automatically.

If an unhandled exception occurs in a wrapped block, the current block will be
rolled back. Otherwise the statements will be committed at the end of the block.

As a context manager:

.. code-block:: python

   with db.atomic() as txn:
       user = User.create(username='charlie')
       tweet = Tweet.create(user=user, content='Hello')

   # Both rows are committed when block exits normally.

As a decorator:

.. code-block:: python

   @db.atomic()
   def create_user_with_tweet(username, content):
       user = User.create(username=username)
       Tweet.create(user=user, content=content)
       return user

If an unhandled exception propagates out of the block, the transaction (or
savepoint - see below) is rolled back and the exception continues to propagate:

.. code-block:: python

   with db.atomic() as txn:
       User.create(username='huey')
       # User has been INSERTed into the database but the transaction is not
       # yet committed because we haven't left the scope of the "with" block.

       raise ValueError('something went wrong')
       # This exception is unhandled - the transaction will be rolled-back and
       # the ValueError will be raised.

   # User('huey') was NOT committed, the transaction rolled-back.
   # The ValueError is raised here.

Manual Commit / Rollback
------------------------

You can commit or roll-back explicitly inside an :meth:`~Database.atomic`
block. After calling :meth:`~Transaction.commit` or :meth:`~Transaction.rollback`
a new transaction (or savepoint) begins automatically:

.. code-block:: python

   with db.atomic() as txn:
       try:
           save_objects()
       except SaveError:
           txn.rollback()  # Roll back, new transaction starts automatically.
           log_error()

       finalize()  # Runs in a new transaction.

   # finalize()'s changes are committed here.

Nesting Transactions
--------------------

The outermost :meth:`~Database.atomic` block creates a transaction. Any nested
``atomic()`` blocks create *savepoints* instead. A savepoint is a named point
within a transaction to which you can roll back without affecting the rest of
the transaction.

.. code-block:: python

   with db.atomic():                        # Transaction begins.
       User.create(username='charlie')

       with db.atomic() as sp:              # Savepoint begins.
           User.create(username='huey')
           sp.rollback()                    # Rolls back huey only.
           User.create(username='alice')    # New savepoint begins here.

       User.create(username='mickey')
   # Committed: charlie, alice, mickey. huey was rolled back.

Savepoints can be nested arbitrarily deep:

.. code-block:: python

   with db.atomic():
       with db.atomic():
           with db.atomic() as inner:
               do_something_risky()
               inner.rollback()   # Only the innermost work is lost.
           do_something_safe()

.. note::
   ``atomic()`` tracks the nesting depth internally. You do not need to
   manage savepoint names or transaction state manually.

Explicit Transaction
--------------------

:meth:`Database.transaction` opens an explicit transaction that does not
nest. Any ``transaction()`` call inside an outer ``transaction()`` block is
ignored - only the outermost transaction is active.

Use this only when you explicitly need a flat, non-nesting transaction. For
most cases, ``atomic()`` is the better choice.

If an exception occurs in a wrapped block, the transaction will be rolled back.
Otherwise the statements will be committed at the end of the wrapped block.

.. code-block:: python

   with db.transaction() as txn:
       User.create(username='mickey')
       txn.commit()         # Commit now; a new transaction begins.
       User.create(username='huey')
       txn.rollback()       # Roll back huey; a new transaction begins.
       User.create(username='zaizee')
   # zaizee is committed when the block exits.

.. warning::
   If you attempt to nest transactions with peewee using the
   :meth:`~Database.transaction` context manager, only the outer-most
   transaction will be used.

   As this may lead to unpredictable behavior, it is recommended that
   you use :meth:`~Database.atomic`.

Explicit Savepoints
-------------------

:meth:`Database.savepoint` creates a savepoint within an active transaction.
Savepoints must occur within a transaction, but can be nested arbitrarily deep.

.. code-block:: python

   with db.transaction() as txn:
       with db.savepoint() as sp:
           User.create(username='mickey')

       with db.savepoint() as sp2:
           User.create(username='zaizee')
           sp2.rollback()  # "zaizee" is not saved.
           User.create(username='huey')

   # mickey and huey were created.

.. note::
   If you manually commit or roll back a savepoint, a new savepoint will
   automatically begin.

Autocommit Mode
---------------

Peewee requires the underlying driver to run in autocommit mode and manages
transaction boundaries itself. This differs from the DB-API 2.0 default, which
starts a transaction implicitly and requires you to commit manually. As a
result, Peewee puts all DB-API drivers into *autocommit* mode.

In rare cases where you need to take direct control of ``BEGIN``/``COMMIT``/
``ROLLBACK`` - bypassing Peewee's transaction management entirely - use
:meth:`~Database.manual_commit`:

.. code-block:: python

   with db.manual_commit():
       db.begin()  # Begin transaction explicitly.
       try:
           user.delete_instance(recursive=True)
       except:
           db.rollback()  # Rollback! An error occurred.
           raise
       else:
           try:
               db.commit()  # Commit changes.
           except:
               db.rollback()
               raise

``manual_commit`` suspends Peewee's transaction management for the duration
of the block. ``atomic()`` and ``transaction()`` have no effect inside it.
This should rarely be needed in application code.

.. _sqlite-locking:

SQLite Transaction Locking Modes
----------------------------------

SQLite supports three locking modes for transactions. Use these when precise
control over read-write locking is required:

.. code-block:: python

   with db.atomic('EXCLUSIVE'):
       # No other connection can read or write until this commits.
       do_something()

   @db.atomic('IMMEDIATE')
   def load_data():
       # No other writer is allowed, but readers can proceed.
       insert_records()

The three modes:

* **DEFERRED** (default) - acquires the minimum necessary lock as reads and
  writes occur. Another writer can intervene between BEGIN and your first write.
* **IMMEDIATE** - acquires a write reservation lock at BEGIN. Other writers are
  blocked; readers can proceed.
* **EXCLUSIVE** - acquires an exclusive lock at BEGIN. No other connection can
  read or write until the transaction completes.

.. seealso::
   `SQLite locking documentation
   <https://sqlite.org/lockingv3.html>`_.

.. _postgres-isolation:

Postgresql Isolation Notes
--------------------------

Postgresql supports configurable isolation levels per-transaction, from least
to most strict:

* READ UNCOMMITTED
* READ COMMITTED (default in most deployments)
* REPEATABLE READ
* SERIALIZABLE

See the `Postgresql transaction isolation docs <https://www.postgresql.org/docs/current/transaction-iso.html>`__
for discussion.

The default isolation level is specified when initializing :class:`PostgresqlDatabase`:

.. code-block:: python

   db = PostgresqlDatabase(
       'my_app',
       user='postgres',
       host='10.8.0.1',
       port=5432,
       isolation_level='SERIALIZABLE')

   # Or use the constants provided by the driver.

   from psycopg2.extensions import ISOLATION_LEVEL_SERIALIZABLE
   db = PostgresqlDatabase(
       ...
       isolation_level=ISOLATION_LEVEL_SERIALIZABLE)


   from psycopg import IsolationLevel
   db = PostgresqlDatabase(
       ...
       isolation_level=IsolationLevel.SERIALIZABLE)

To control the isolation-level for a transaction, you can pass the desired
setting to the outer-most ``atomic()`` block:

.. code-block:: python

   with db.atomic('SERIALIZABLE') as txn:
       ...

.. note::
   Isolation level cannot be specified for nested ``atomic()`` blocks.
