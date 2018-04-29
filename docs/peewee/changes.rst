.. _changes:

Changes in 3.0
==============

This document describes changes to be aware of when switching from 2.x to 3.x.

Backwards-incompatible
----------------------

I tried to keep changes backwards-compatible as much as possible. In some
places, APIs that have changed will trigger a ``DeprecationWarning``.

Database
^^^^^^^^

* ``get_conn()`` has changed to :py:meth:`Database.connection`
* ``get_cursor()`` has changed to :py:meth:`Database.cursor`
* ``execution_context()`` is replaced by simply using the database instance as
  a context-manager.
* For a connection context *without* a transaction, use
  :py:meth:`Database.connection_context`.
* :py:meth:`Database.create_tables` and :py:meth:`Database.drop_tables`, as
  well as :py:meth:`Model.create_table` and :py:meth:`Model.drop_table` all
  default to ``safe=True`` (``create_table`` will create if not exists, ``drop_table`` will drop if exists).
* ``connect_kwargs`` attribute has been renamed to ``connect_params``
* initialization parameter for custom field-type definitions has changed
  from ``fields`` to ``field_types``.

Model Meta options
^^^^^^^^^^^^^^^^^^

* ``db_table`` has changed to ``table_name``
* ``db_table_func`` has changed to ``table_function``
* ``order_by`` has been removed (used for specifying a default ordering to be
  applied to SELECT queries).
* ``validate_backrefs`` has been removed. Back-references are no longer
  validated.

Models
^^^^^^

* :py:class:`BaseModel` has been renamed to :py:class:`ModelBase`
* Accessing raw model data is now done using ``__data__`` instead of ``_data``

Fields
^^^^^^

* ``db_column`` has changed to ``column_name``
* ``db_field`` class attribute changed to ``field_type`` (used if you are
  implementing custom field subclasses)
* ``model_class`` attribute has changed to ``model``
* :py:class:`PrimaryKeyField` has been renamed to :py:class:`AutoField`
* :py:class:`ForeignKeyField` constructor has the following changes:

  * ``rel_model`` has changed to ``model``
  * ``to_field`` has changed to ``field``
  * ``related_name`` has changed to ``backref``

* :py:class:`ManyToManyField` is now included in the main ``peewee.py`` module
* Removed the extension fields ``PasswordField``, ``PickledField`` and
  ``AESEncryptedField``.

Querying
^^^^^^^^

The C extension that contained implementations of the query result wrappers has
been removed.

Additionally, :py:meth:`Select.aggregate_rows` has been removed. This helper
was used to de-duplicate left-join queries to give the appearance of efficiency
when iterating a model and its relations. In practice, the complexity of the
code and its somewhat limited usefulness convinced me to scrap it. You can
instead use :py:func:`prefetch` to achieve the same result.

* :py:class:`Select` query attribute ``_select`` has changed to ``_returning``
* The ``naive()`` method is now :py:meth:`~BaseQuery.objects`, which defaults
  to using the model class as the constructor, but accepts any callable to use
  as an alternate constructor.

The :py:func:`Case` helper has moved from the ``playhouse.shortcuts`` module
into the main peewee module.

The :py:meth:`~BaseColumn.cast` method is no longer a function, but instead is
a method on all column-like objects.

The ``InsertQuery.return_id_list()`` method has been replaced by a more general
pattern of using :py:meth:`_WriteQuery.returning`.

When using :py:func:`prefetch`, the collected instances will be stored in the
same attribute as the foreign-key's ``backref``. Previously, you would access
joined instances using ``(backref)_prefetch``.

The :py:class:`SQL` object, used to create a composable a SQL string, now
expects the second parameter to be a list/tuple of parameters.

Removed Extensions
^^^^^^^^^^^^^^^^^^

The following extensions are no longer included in the ``playhouse``:

* ``berkeleydb``
* ``csv_utils``
* ``djpeewee``
* ``gfk``
* ``kv``
* ``pskel``
* ``read_slave``

SQLite Extension
^^^^^^^^^^^^^^^^

The SQLite extension module's :py:class:`VirtualModel` class accepts slightly
different ``Meta`` options:

* ``arguments`` - used to specify arbitrary arguments appended after any
  columns being defined on the virtual table. Should be a list of strings.
* ``extension_module`` (unchanged)
* ``options`` (replaces ``extension_options``) - arbitrary options for the
  virtual table that appear after columns and ``arguments``.
* ``prefix_arguments`` - a list of strings that should appear before any
  arguments or columns in the virtual table declaration.

So, when declaring a model for a virtual table, it will be constructed roughly
like this:

.. code-block:: sql

   CREATE VIRTUAL TABLE "table name" USING extension_module (
       prefix arguments,
       field definitions,
       arguments,
       options)

Signals Extension
^^^^^^^^^^^^^^^^^

The ``post_init`` signal has been removed.

New stuff
---------

The query-builder has been rewritten from the ground-up to be more flexible and
powerful. There is now a generic, :ref:`lower-level API <query-builder>` for
constructing queries.

SQLite
^^^^^^

Many SQLite-specific features have been moved from the ``playhouse.sqlite_ext``
module into ``peewee``, such as:

* User-defined functions, aggregates, collations, and table-functions.
* Loading extensions.
* Specifying pragmas.

See the :ref:`"Using SQLite" section <using_sqlite>` and :ref:`"SQLite extensions" <sqlite_ext>`
documents for more details.

SQLite Extension
^^^^^^^^^^^^^^^^

The virtual-table implementation from `sqlite-vtfunc <https://github.com/coleifer/sqlite-vtfunc>`_
has been folded into the peewee codebase.

* Support for SQLite online backup API.
* Murmurhash implementation has been corrected.
* Couple small quirks in the BM25 ranking code have been addressed.
* Numerous user-defined functions for hashing and ranking are now included.
* :py:class:`BloomFilter` implementation.
* Incremental :py:class:`Blob` I/O support.
* Support for update, commit and rollback hooks.
* :py:class:`LSMTable` implementation to support the lsm1 extension.
