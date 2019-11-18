.. _crdb:

Cockroach Database
------------------

`CockroachDB <https://www.cockroachlabs.com>` (CRDB) is well supported by
peewee. The ``playhouse.cockroach`` extension module provides the following
classes and helpers:

* :py:class:`CockroachDatabase` - a subclass of :py:class:`PostgresqlDatabase`,
  designed specifically for working with CRDB.
* :py:class:`PooledCockroachDatabase` - like the above, but implements
  connection-pooling.
* :py:func:`run_transaction` - runs a function inside a transaction and
  provides automatic client-side retry logic.
* :py:class:`UUIDKeyField` - a primary-key field implementation that uses
  CRDB's ``UUID`` type with a default randomly-generated UUID.
* :py:class:`RowIDField` - a primary-key field implementation that uses CRDB's
  ``INT`` type with a default ``unique_rowid()``.

CRDB is compatible with Postgres' wire protocol and exposes a very similar
SQL interface, so it is possible (though not recommended) to use
:py:class:`PostgresqlDatabase` with CRDB. There are a number of reasons for
this:

1. CRDB does not support nested transactions, so the
   :py:meth:`~Database.atomic` method has been implemented to enforce this
