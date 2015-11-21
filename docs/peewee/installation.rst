.. _installation:

Installing and Testing
======================

Most users will want to simply install the latest version, hosted on PyPI:

.. code-block:: console

    pip install peewee

Peewee comes with two C extensions that can optionally be compiled:

* Speedups, which includes miscellaneous functions re-implemented with Cython. This module will be built automatically if Cython is installed.
* Sqlite extensions, which includes Cython implementations of the SQLite date manipulation functions, the REGEXP operator, and full-text search result ranking algorithms. This module should be built using the ``build_sqlite_ext`` command.

.. note::
    If you have Cython installed, then the ``speedups`` module will automatically be built. If you wish to also build the SQLite Cython extension, you must manually run:

    .. code-block:: console

        python setup.py build_sqlite_ext
        python setup.py install


Installing with git
-------------------

The project is hosted at https://github.com/coleifer/peewee and can be installed
using git:

.. code-block:: console

    git clone https://github.com/coleifer/peewee.git
    cd peewee
    python setup.py install

If you would like to build the SQLite extension in a git checkout, you can run:

.. code-block:: console

    # Build the sqlite extension and place the shared library alongside the other modules.
    python setup.py build_sqlite_ext -i

.. note::
    On some systems you may need to use ``sudo python setup.py install`` to install peewee system-wide.

Running tests
-------------

You can test your installation by running the test suite.

.. code-block:: console

    python setup.py test

    # Or use the test runner:
    python runtests.py

You can test specific features or specific database drivers using the ``runtests.py``
script. By default the test suite is run using SQLite and the ``playhouse``
extension tests are not run. To view the available test runner options, use:

.. code-block:: console

    python runtests.py --help
