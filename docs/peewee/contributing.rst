.. _contributing:

Contributing
============

To continually improve, Peewee needs the help of developers like you.
Whether it's contributing patches, submitting bug reports, or just asking and
answering questions, you are helping to make Peewee a better library.

In this document I'll describe some of the ways you can help.

.. _running-tests:

Running the tests
-----------------

Peewee comes with a test-runner. By default, tests run against SQLite:

.. code-block:: shell

   git clone https://github.com/coleifer/peewee.git
   cd peewee
   python runtests.py

Tests can also be run against the other supported databases and drivers:

=============== ====================== =======================================
Database        Driver                 Command
=============== ====================== =======================================
SQLite          sqlite3                ``runtests.py``
SQLite          cysqlite               ``runtests.py -e cysqlite``
MySQL/MariaDB   pymysql                ``runtests.py -e mysql``
MySQL           mysql-connector-python ``runtests.py -e mysqlconnector``
MariaDB         mariadb                ``runtests.py -e mariadb``
Postgres        psycopg2               ``runtests.py -e postgres``
Postgres        psycopg (3)            ``runtests.py -e psycopg3``
=============== ====================== =======================================

The asyncio tests need ``greenlet`` along with their respective drivers:

* ``aiosqlite``
* ``aiomysql``
* ``asyncpg``

The ``--help`` test-runner option lists every engine and the connection
options. Postgres honors the ``PGHOST``, ``PGUSER`` and ``PGPASSWORD`` envvars.
MySQL connects to localhost as the current user with no password by default.
Use ``--mysql-user``, ``--mysql-password``, etc to specify connection details.

Peewee will not create a new database in your MariaDB/MySQL/Postgres cluster,
instead it expects to find a database named ``peewee_test``. You can do this
setup once:

.. code-block:: shell

   createdb peewee_test
   psql peewee_test -c "create extension hstore"  # Optional.
   mysql -e 'create database `peewee_test`;'

Tests for optional extensions are skipped when their dependencies are missing.
To run everything, install what CI installs (see ``.github/workflows/tests.yaml``).

To run a subset of the suite, you can specify modules, classes or individual
test methods:

.. code-block:: shell

   python runtests.py models model_sql sql
   python runtests.py models.TestModelAPIs
   python runtests.py models.TestModelAPIs.test_pk_is_fk

Test output verbosity can be configured:

* ``-v2`` lists each test with its skip reason
* ``-v3`` logs every SQL query

If you change the public API in ``peewee.py``, update the type stub in
``peewee-stubs/__init__.pyi``. The ``stubs`` job in the CI workflow shows how
it is checked.

To build the docs:

.. code-block:: shell

   pip install sphinx
   make -C docs html

Patches
-------

Do you have an idea for a new feature, or is there a clunky API you'd like to
improve? Before coding it up and submitting a pull-request, `open a new issue
<https://github.com/coleifer/peewee/issues/new>`_ on GitHub describing your
proposed changes. This doesn't have to be anything formal, just a description
of what you'd like to do and why.

When you're ready, you can submit a pull-request with your changes. Successful
patches will have the following:

* Unit tests.
* Documentation, both prose form and general :ref:`API documentation <api>`.
* Code that conforms stylistically with the rest of the Peewee codebase.

Bugs
----

If you've found a bug, please check to see if it has `already been reported <https://github.com/coleifer/peewee/issues/>`_,
and if not `create an issue on GitHub <https://github.com/coleifer/peewee/issues/new>`_.
The more information you include, the more quickly the bug will get fixed, so
please try to include the following:

* Traceback and the error message (please format your code).
* Relevant portions of your code or code to reproduce the error
* Peewee version: ``python -c "from peewee import __version__; print(__version__)"``
* Which database you're using

If you have found a bug in the code and submit a failing test-case, then hats-off to you, you are a hero!

Questions
---------

If you have questions about how to do something with peewee, then I recommend
either:

* Open a GH issue and clearly mark it as a question. The expectation would be
  that the question pertains to something not easily answered by consulting the
  docs.
* Ask in ``#peewee`` on `libera.chat <https://web.libera.chat/>`_.
* Ask on StackOverflow. I still check SO periodically, but unfortunately since
  early 2026 it's a ghost town. Nonetheless it works and it preserves the Q&A
  for the next person.
