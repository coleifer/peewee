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

Installing from source
----------------------

.. code-block:: shell

   git clone https://github.com/coleifer/peewee.git
   cd peewee
   pip install .

Running tests
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
| **Sqlite**            | ``sqlite3``            | :py:class:`SqliteDatabase`                 |
+-----------------------+------------------------+--------------------------------------------+
| **Postgres**          | ``psycopg3``           | :py:class:`PostgresqlDatabase`             |
+-----------------------+------------------------+--------------------------------------------+
| **Postgres**          | ``psycopg2``           | :py:class:`PostgresqlDatabase`             |
+-----------------------+------------------------+--------------------------------------------+
| **MySQL**             | ``pymysql``            | :py:class:`MySQLDatabase`                  |
+-----------------------+------------------------+--------------------------------------------+
| Sqlite (async)        | ``aiosqlite``          | :py:class:`AsyncSqliteDatabase`            |
+-----------------------+------------------------+--------------------------------------------+
| Postgres (async)      | ``asyncpg``            | :py:class:`AsyncPostgresqlDatabase`        |
+-----------------------+------------------------+--------------------------------------------+
| MySQL (async)         | ``aiomysql``           | :py:class:`AsyncMySQLDatabase`             |
+-----------------------+------------------------+--------------------------------------------+
| Sqlite (alternate)    | ``cysqlite``           | :py:class:`CySqliteDatabase`               |
+-----------------------+------------------------+--------------------------------------------+
| Sqlite (alternate)    | ``apsw``               | :py:class:`APSWDatabase`                   |
+-----------------------+------------------------+--------------------------------------------+
| SqlCipher             | ``sqlcipher3``         | :py:class:`SqlCipherDatabase`              |
+-----------------------+------------------------+--------------------------------------------+
| MySQL (alternate)     | ``mysql-connector``    | :py:class:`MySQLConnectorDatabase`         |
+-----------------------+------------------------+--------------------------------------------+
| MariaDB (alternate)   | ``mariadb-connector``  | :py:class:`MariaDBConnectorDatabase`       |
+-----------------------+------------------------+--------------------------------------------+

The three bolded rows cover the majority of deployments. All others are
optional; install their drivers when needed.
