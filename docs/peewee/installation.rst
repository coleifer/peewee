.. _installation:

Installing and Testing
======================

Most users will want to simply install the latest version, hosted on PyPI:

.. code-block:: console

    pip install peewee

Peewee has optional Sqlite C extensions which are not bundled as part of the
wheel. If you wish to use these, you can install Peewee via source
distribution:

.. code-block:: console

    pip install peewee --no-binary :all:

Installing with git
-------------------

The project is hosted at https://github.com/coleifer/peewee and can be installed
using git:

.. code-block:: console

    git clone https://github.com/coleifer/peewee.git
    cd peewee
    pip install .

If you have the sqlite3 headers installed, then the sqlite C extensions will be
built.

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

* `apsw <https://github.com/rogerbinns/apsw>`_: an optional 3rd-party SQLite
  binding offering greater performance and comprehensive support for SQLite's C
  APIs. Use with :py:class:`APSWDatabase`.
* `gevent <http://www.gevent.org/>`_ is an optional dependency for
  :py:class:`SqliteQueueDatabase` (though it works with ``threading`` just
  fine).
* Lastly, if you use the *Flask* framework, there are helper extension modules
  available.


Note on the SQLite extensions
-----------------------------

Peewee includes two SQLite-specific C extensions which provide additional
functionality and improved performance for SQLite database users. These are not
shipped with the binary wheel, but can be installed by instructing ``pip`` to
install Peewee via source-distribution. In order for the sqlite extensions to
be built, the sqlite shared library and header must be installed.
