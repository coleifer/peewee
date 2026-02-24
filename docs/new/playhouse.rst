.. _playhouse:

The ``playhouse`` package bundles optional extensions that extend Peewee's
core capabilities. All modules live under the ``playhouse`` namespace and are
imported separately so that the core library stays lean.

Extensions are grouped into five areas:

**SQLite extensions**

.. toctree::
   :maxdepth: 1

   sqlite

**PostgreSQL extensions**

.. toctree::
   :maxdepth: 1

   postgres

**MySQL extensions**

.. toctree::
   :maxdepth: 1

   mysql

**Database tooling** - connection management, schema migrations, code
generation, and testing:

.. toctree::
   :maxdepth: 1

   db_tools

**ORM utilities** - higher-level abstractions that work with any database:

.. toctree::
   :maxdepth: 1

   orm_utils

Quick-reference
---------------

The tables below map module paths to the sections that document them.

+---------------------------------------+---------------------------+
| Module                                | Section                   |
+=======================================+===========================+
| playhouse.sqlite_ext                  | :ref:`sqlite-ext`         |
+---------------------------------------+---------------------------+
| playhouse.cysqlite_ext                | :ref:`cysqlite-ext`       |
+---------------------------------------+---------------------------+
| playhouse.sqliteq                     | :ref:`sqliteq`            |
+---------------------------------------+---------------------------+
| playhouse.sqlite_udf                  | :ref:`sqlite-udf`         |
+---------------------------------------+---------------------------+
| playhouse.apsw_ext                    | :ref:`apsw`               |
+---------------------------------------+---------------------------+
| playhouse.sqlcipher_ext               | :ref:`sqlcipher`          |
+---------------------------------------+---------------------------+
| playhouse.postgres_ext                | :ref:`postgres-ext`       |
+---------------------------------------+---------------------------+
| playhouse.cockroachdb                 | :ref:`crdb`               |
+---------------------------------------+---------------------------+
| playhouse.mysql_ext                   | :ref:`mysql-ext`          |
+---------------------------------------+---------------------------+
| playhouse.db_url                      | :ref:`db-url`             |
+---------------------------------------+---------------------------+
| playhouse.pool                        | :ref:`pool`               |
+---------------------------------------+---------------------------+
| playhouse.migrate                     | :ref:`migrate`            |
+---------------------------------------+---------------------------+
| playhouse.reflection                  | :ref:`reflection`         |
+---------------------------------------+---------------------------+
| playhouse.test_utils                  | :ref:`test-utils`         |
+---------------------------------------+---------------------------+
| playhouse.fields                      | :ref:`extra-fields`       |
+---------------------------------------+---------------------------+
| playhouse.shortcuts                   | :ref:`shortcuts`          |
+---------------------------------------+---------------------------+
| playhouse.hybrid                      | :ref:`hybrid`             |
+---------------------------------------+---------------------------+
| playhouse.kv                          | :ref:`kv`                 |
+---------------------------------------+---------------------------+
| playhouse.signals                     | :ref:`signals`            |
+---------------------------------------+---------------------------+
| playhouse.dataset                     | :ref:`dataset`            |
+---------------------------------------+---------------------------+
| playhouse.flask_utils                 | :ref:`flask-utils`        |
+---------------------------------------+---------------------------+
