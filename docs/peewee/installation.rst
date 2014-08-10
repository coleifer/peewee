.. _installation:

Installing and Testing
======================

Most users will want to simply install the latest version, hosted on PyPI:

.. code-block:: console

    pip install peewee


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
