.. _changes:

Changes in 3.0
==============

This document describes changes to be aware of when switching from 2.x to 3.x.

Backwards-incompatible
----------------------

I tried to keep changes backwards-compatible as much as possible. In some
places, APIs that have changed will trigger a ``DeprecationWarning``.

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

* Accessing raw model data is now done using ``__data__`` instead of ``_data``

Fields
^^^^^^

* ``db_column`` has changed to ``column_name``
* ``model_class`` attribute has changed to ``model``
* :py:class:`PrimaryKeyField` has been renamed to :py:class:`AutoField`
* :py:class:`ForeignKeyField` constructor has the following changes:
  * ``rel_model`` has changed to ``model``
  * ``to_field`` has changed to ``field``
  * ``related_name`` has changed to ``backref``
* :py:class:`ManyToManyField` is now included in the main ``peewee.py`` module

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

New stuff
---------

The query-builder has been rewritten from the ground-up to be more flexible and
powerful. There is now a generic, lower-level API for constructing queries.
