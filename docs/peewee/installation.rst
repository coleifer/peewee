.. _installation:

Installing and Testing
======================

Most users will want to simply install the latest version, hosted on PyPI:

.. code-block:: shell
   :emphasize-lines: 1

   pip install peewee

Peewee has an optional Sqlite C extension which is not bundled as part of the
wheel. If you wish to use this, you can install Peewee via source distribution:

.. code-block:: shell

   pip install peewee --no-binary :all:

Installing with git
-------------------

The project is hosted at https://github.com/coleifer/peewee and can be installed
using git:

.. code-block:: shell

   git clone https://github.com/coleifer/peewee.git
   cd peewee
   pip install .

Running tests
-------------

You can test your installation by running the test suite.

.. code-block:: shell

   python runtests.py

You can test specific features or specific database drivers using the
``runtests.py`` script. To view the available test runner options, use:

.. code-block:: shell

   python runtests.py --help

.. note::
   To run tests against Postgres or MySQL you need to create a database named
   "peewee_test". To test the Postgres extension module, you will also want to
   install the HStore extension in the postgres test database:

   .. code-block:: sql

      -- install the hstore extension on the peewee_test postgres db.
      CREATE EXTENSION hstore;

Driver support
--------------

+-----------------------+------------------------+--------------------------------------------+
| Database              | Driver                 | Implementation                             |
+=======================+========================+============================================+
| **Sqlite**            | ``sqlite3``            | :class:`SqliteDatabase`                 |
+-----------------------+------------------------+--------------------------------------------+
| **Postgres**          | ``psycopg2``           | :class:`PostgresqlDatabase`             |
+-----------------------+------------------------+--------------------------------------------+
| **Postgres**          | ``psycopg3``           | :class:`PostgresqlDatabase`             |
+-----------------------+------------------------+--------------------------------------------+
| **MySQL**             | ``pymysql``            | :class:`MySQLDatabase`                  |
+-----------------------+------------------------+--------------------------------------------+
| Sqlite (async)        | ``aiosqlite``          | :class:`AsyncSqliteDatabase`            |
+-----------------------+------------------------+--------------------------------------------+
| Postgres (async)      | ``asyncpg``            | :class:`AsyncPostgresqlDatabase`        |
+-----------------------+------------------------+--------------------------------------------+
| MySQL (async)         | ``aiomysql``           | :class:`AsyncMySQLDatabase`             |
+-----------------------+------------------------+--------------------------------------------+
| Sqlite (alternate)    | ``cysqlite``           | :class:`CySqliteDatabase`               |
+-----------------------+------------------------+--------------------------------------------+
| Sqlite (alternate)    | ``apsw``               | :class:`APSWDatabase`                   |
+-----------------------+------------------------+--------------------------------------------+
| SqlCipher             | ``sqlcipher3``         | :class:`SqlCipherDatabase`              |
+-----------------------+------------------------+--------------------------------------------+
| MySQL (alternate)     | ``mysql-connector``    | :class:`MySQLConnectorDatabase`         |
+-----------------------+------------------------+--------------------------------------------+
| MariaDB (alternate)   | ``mariadb-connector``  | :class:`MariaDBConnectorDatabase`       |
+-----------------------+------------------------+--------------------------------------------+
