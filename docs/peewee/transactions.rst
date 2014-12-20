.. _transactions:

Transactions
============

Peewee provides several interfaces for working with transactions. The most general is the :py:meth:`Database.atomic` method, which also supports nested transactions. :py:meth:`~Database.atomic` blocks will be run in a transaction or savepoint, depending on the level of nesting.

If an exception occurs in a wrapped block, the current transaction/savepoint will be rolled back. Otherwise the statements will be committed at the end of the wrapped block.

:py:meth:`~Database.atomic` can be used as either a **context manager** or a **decorator**.

Context manager
---------------

Using ``atomic`` as context manager:

.. code-block:: python

    db = SqliteDatabase(':memory:')

    with db.atomic() as txn:
        # This is the outer-most level, so this block corresponds to
        # a transaction.
        User.create(username='charlie')

        with db.atomic() as nested_txn:
            # This block corresponds to a savepoint.
            User.create(username='huey')

            # This will roll back the above create() query.
            nested_txn.rollback()

        User.create(username='mickey')

    # When the block ends, the transaction is committed (assuming no error
    # occurs). At that point there will be two users, "charlie" and "mickey".

You can use the ``atomic`` method to perform *get or create* operations as well:

.. code-block:: python

    try:
        with db.atomic():
            user = User.create(username=username)
        return 'Success'
    except peewee.IntegrityError:
        return 'Failure: %s is already in use.' % username

Decorator
---------

Using ``atomic`` as a decorator:

.. code-block:: python

    @db.atomic()
    def create_user(username):
        # This statement will run in a transaction. If the caller is already
        # running in an `atomic` block, then a savepoint will be used instead.
        return User.create(username=username)

    create_user('charlie')

Nesting Transactions
--------------------

:py:meth:`~Database.atomic` provides transparent nesting of transactions. When using :py:meth:`~Database.atomic`, the outer-most call will be wrapped in a transaction, and any nested calls will use savepoints.

.. code-block:: python

    with db.atomic() as txn:
        perform_operation()

        with db.atomic() as nested_txn:
            perform_another_operation()

Peewee supports nested transactions through the use of savepoints (for more information, see :py:meth:`~Database.savepoint`).

Explicit transaction
--------------------

If you wish to explicitly run code in a transaction, you can use :py:meth:`~Database.transaction`. Like :py:meth:`~Database.atomic`, :py:meth:`~Database.transaction` can be used as a context manager or as a decorator.

If an exception occurs in a wrapped block, the transaction will be rolled back. Otherwise the statements will be committed at the end of the wrapped block.

.. code-block:: python

    db = SqliteDatabase(':memory:')

    with db.transaction():
        # Delete the user and their associated tweets.
        user.delete_instance(recursive=True)

Transactions can be explicitly committed or rolled-back within the wrapped block. When this happens, a new transaction will be started.

.. code-block:: python

    with db.transaction() as txn:
        User.create(username='mickey')
        txn.commit()  # Changes are saved and a new transaction begins.
        User.create(username='huey')

        # Roll back. "huey" will not be saved, but since "mickey" was already
        # committed, that row will remain in the database.
        txn.rollback()

    with db.transaction() as txn:
        User.create(username='whiskers')
        # Roll back changes, which removes "whiskers".
        txn.rollback()

        # Create a new row for "mr. whiskers" which will be implicitly committed
        # at the end of the `with` block.
        User.create(username='mr. whiskers')

.. note:: If you attempt to nest transactions with peewee using the :py:meth:`~Database.transaction` context manager, only the outer-most transaction will be used. However if an exception occurs in a nested block, this can lead to unpredictable behavior, so it is strongly recommended that you use :py:meth:`~Database.atomic`.

Explicit Savepoints
^^^^^^^^^^^^^^^^^^^

Just as you can explicitly create transactions, you can also explicitly create savepoints using the :py:meth:`~Database.savepoint` method. Savepoints must occur within a transaction, but can be nested arbitrarily deep.

.. code-block:: python

    with db.transaction() as txn:
        with db.savepoint() as sp:
            User.create(username='mickey')

        with db.savepoint() as sp2:
            User.create(username='zaizee')
            sp2.rollback()  # "zaizee" will not be saved, but "mickey" will be.

.. note:: If you manually commit or roll back a savepoint, a new savepoint **will not** automatically be created. This differs from the behavior of :py:class:`transaction`, which will automatically open a new transaction after manual commit/rollback.

Autocommit Mode
---------------

By default, databases are initialized with ``autocommit=True``, you can turn this on and off at runtime if you like. If you choose to disable autocommit, then you must explicitly call :py:meth:`Database.begin` to begin a transaction, and commit or roll back.

The behavior below is roughly the same as the context manager and decorator:

.. code-block:: python

    db.set_autocommit(False)
    db.begin()
    try:
        user.delete_instance(recursive=True)
    except:
        db.rollback()
        raise
    else:
        try:
            db.commit()
        except:
            db.rollback()
            raise
    finally:
        db.set_autocommit(True)

If you would like to manually control *every* transaction, simply turn autocommit off when instantiating your database:

.. code-block:: python

    db = SqliteDatabase(':memory:', autocommit=False)

    db.begin()
    User.create(username='somebody')
    db.commit()
