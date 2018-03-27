.. _installation:

Installing and Testing
======================

Most users will want to simply install the latest version, hosted on PyPI:

.. code-block:: console

    pip install peewee

Peewee comes with a couple C extensions that will be built if Cython is
available.

* Speedups, which includes miscellaneous functions re-implemented with Cython.
* Sqlite extensions, which includes Cython implementations of the SQLite date
  manipulation functions, the REGEXP operator, and full-text search result
  ranking algorithms.


Installing with git
-------------------

The project is hosted at https://github.com/coleifer/peewee and can be installed
using git:

.. code-block:: console

    git clone https://github.com/coleifer/peewee.git
    cd peewee
    python setup.py install

.. note::
    On some systems you may need to use ``sudo python setup.py install`` to
    install peewee system-wide.

If you would like to build the SQLite extension in a git checkout, you can run:

.. code-block:: console

    # Build the C extension and place shared libraries alongside other modules.
    python setup.py build_ext -i


Running tests
-------------

You can test your installation by running the test suite.

.. code-block:: console

    python runtests.py

You can test specific features or specific database drivers using the
``runtests.py`` script. To view the available test runner options, use:

.. code-block:: console

    python runtests.py --help

.. note::
    To run tests against Postgres or MySQL you need to create a database named
    "peewee_test". To test the Postgres extension module, you will also want to
    install the HStore extension in the postgres test database:

    .. code-block:: sql

        -- install the hstore extension on the peewee_test postgres db.
        CREATE EXTENSION hstore;


Optional dependencies
---------------------

.. note::
    To use Peewee, you typically won't need anything outside the standard
    library, since most Python distributions are compiled with SQLite support.
    You can test by running ``import sqlite3`` in the Python console. If you
    wish to use another database, there are many DB-API 2.0-compatible drivers
    out there, such as ``pymysql`` or ``psycopg2`` for MySQL and Postgres
    respectively.

* `Cython <http://cython.org/>`_: used for various speedups. Can give a big
  boost to certain operations, particularly if you use SQLite.
* `apsw <https://github.com/rogerbinns/apsw>`_: an optional 3rd-party SQLite
  binding offering greater performance and much, much saner semantics than the
  standard library ``pysqlite``. Use with :py:class:`APSWDatabase`.
* `gevent <http://www.gevent.org/>`_ is an optional dependency for
  :py:class:`SqliteQueueDatabase` (though it works with ``threading`` just
  fine).
* `BerkeleyDB <http://www.oracle.com/technetwork/database/database-technologies/berkeleydb/downloads/index.html>`_ can
  be compiled with a SQLite frontend, which works with Peewee. Compiling can be
  tricky so `here are instructions <http://charlesleifer.com/blog/updated-instructions-for-compiling-berkeleydb-with-sqlite-for-use-with-python/>`_.
* Lastly, if you use the *Flask* framework, there are helper extension modules
  available.


Skip Compilation of SQLite Extensions
-------------------------------------

I've received reports from Windows users that they have some trouble installing
Peewee due to missing a SQLite shared library. If you would like to simply skip
compilation of the SQLite-specific C extensions, you can set the ``NO_SQLITE``
environment variable:

.. code-block:: console

    $ NO_SQLITE=1 python setup.py build
