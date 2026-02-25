.. _installation:

Installing and Testing
======================

Install the latest release from PyPI:

.. code-block:: shell

   pip install peewee

Peewee has an optional Sqlite C extension which is not bundled in the default
wheel. It provides user-defined ranking functions for use with Sqlite FTS4 and
functions for fuzzy string matching. To build from source:

.. code-block:: shell

   pip install peewee --no-binary :all:

Installing from Source
----------------------

.. code-block:: shell

   git clone https://github.com/coleifer/peewee.git
   cd peewee
   pip install .

Running Tests
-------------

.. code-block:: shell

   python runtests.py
   python runtests.py --help  # Show options.

To run tests against Postgres or MySQL create a database named ``peewee_test``.
For the Postgres extension tests, enable hstore:

.. code-block:: sql

   CREATE EXTENSION hstore;

Supported Drivers
-----------------

Peewee works with any database for which a DB-API 2.0 driver exists. The
following drivers are supported out of the box:

+-----------------------+------------------------+--------------------------------------------+
| Database              | Driver                 | Implementation                             |
+=======================+========================+============================================+
| **Sqlite**            | ``sqlite3``            | :class:`SqliteDatabase`                    |
+-----------------------+------------------------+--------------------------------------------+
| **Postgres**          | ``psycopg3``           | :class:`PostgresqlDatabase`                |
+-----------------------+------------------------+--------------------------------------------+
| **Postgres**          | ``psycopg2``           | :class:`PostgresqlDatabase`                |
+-----------------------+------------------------+--------------------------------------------+
| **MySQL**             | ``pymysql``            | :class:`MySQLDatabase`                     |
+-----------------------+------------------------+--------------------------------------------+
| Sqlite (async)        | ``aiosqlite``          | :class:`AsyncSqliteDatabase`               |
+-----------------------+------------------------+--------------------------------------------+
| Postgres (async)      | ``asyncpg``            | :class:`AsyncPostgresqlDatabase`           |
+-----------------------+------------------------+--------------------------------------------+
| MySQL (async)         | ``aiomysql``           | :class:`AsyncMySQLDatabase`                |
+-----------------------+------------------------+--------------------------------------------+
| Sqlite (alternate)    | ``cysqlite``           | :class:`CySqliteDatabase`                  |
+-----------------------+------------------------+--------------------------------------------+
| Sqlite (alternate)    | ``apsw``               | :class:`APSWDatabase`                      |
+-----------------------+------------------------+--------------------------------------------+
| SqlCipher             | ``sqlcipher3``         | :class:`SqlCipherDatabase`                 |
+-----------------------+------------------------+--------------------------------------------+
| MySQL (alternate)     | ``mysql-connector``    | :class:`MySQLConnectorDatabase`            |
+-----------------------+------------------------+--------------------------------------------+
| MariaDB (alternate)   | ``mariadb-connector``  | :class:`MariaDBConnectorDatabase`          |
+-----------------------+------------------------+--------------------------------------------+
| CockroachDB           | ``psycopg`` (2 or 3)   | :class:`CockroachDatabase`                 |
+-----------------------+------------------------+--------------------------------------------+

The three bolded rows cover the majority of deployments. All others are
optional; install their drivers when needed.
