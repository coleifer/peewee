.. _transactions:

Transactions
============

Peewee provides several interfaces for working with transactions.

Context manager
---------------

You can execute queries within a transaction using the :py:meth:`Database.transaction` context manager, which will issue a commit if all goes well, or a rollback if an exception is raised:

.. code-block:: python

    db = SqliteDatabase(':memory:')

    with db.transaction():
        # Delete the user and their associated tweets.
        user.delete_instance(recursive=True)

Transactions can be explicitly committed or rolled-back within the wrapped block, in which case a new transaction will be opened.

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

You can use the transaction to perform *get or create* operations as well:

.. code-block:: python

    try:
        with db.transaction():
            user = User.create(username=username)
        return 'Success'
    except peewee.IntegrityError:
        return 'Failure: %s is already in use' % username

Decorator
---------

Similar to the context manager, you can decorate functions with the :py:meth:`~Database.commit_on_success` decorator. This decorator will commit if the function returns normally, otherwise the transaction will be rolled back and the exception re-raised.

.. code-block:: python

    db = SqliteDatabase(':memory:')

    @db.commit_on_success
    def delete_user(user):
        user.delete_instance(recursive=True)

Autocommit Mode
---------------

By default, databases are initialized with ``autocommit=True``, you can turn this on and off at runtime if you like. The behavior below is roughly the same as the context manager and decorator:

.. code-block:: python

    db.set_autocommit(False)
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

    User.create(username='somebody')
    db.commit()

Nesting Transactions
--------------------

For transparent nesting of transactions, you can use the :py:meth:`~Database.atomic` context manager. When using :py:meth:`~Database.atomic`, the outer-most call will be wrapped in a transaction, and any nested calls will use savepoints.

.. code-block:: python

    with db.atomic() as txn:
        perform_operation()

        with db.atomic() as nested_txn:
            perform_another_operation()

Peewee supports nested transactions through the use of savepoints (for more information, see :py:meth:`~Database.savepoint`).

If you attempt to nest transactions with peewee using the :py:meth:`~Database.transaction` context manager, only the outer-most transaction will be used. However if an exception occurs in a nested block, this can lead to unpredictable behavior, so it is strongly recommended that you use :py:meth:`~Database.atomic`.
