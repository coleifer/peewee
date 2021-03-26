.. peewee documentation master file, created by
   sphinx-quickstart on Thu Nov 25 21:20:29 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

peewee
======

.. image:: peewee3-logo.png

Peewee is a simple and small ORM. It has few (but expressive) concepts, making
it easy to learn and intuitive to use.

* a small, expressive ORM
* python 2.7+ and 3.4+ (developed with 3.6)
* supports sqlite, mysql, postgresql and cockroachdb
* :ref:`tons of extensions <playhouse>`

.. image:: postgresql.png
    :target: peewee/database.html#using-postgresql
    :alt: postgresql

.. image:: mysql.png
    :target: peewee/database.html#using-mysql
    :alt: mysql

.. image:: sqlite.png
    :target: peewee/database.html#using-sqlite
    :alt: sqlite

.. image:: crdb.png
    :target: peewee/database.html#using-crdb
    :alt: cockroachdb

Peewee's source code hosted on `GitHub <https://github.com/coleifer/peewee>`_.

New to peewee? These may help:

* :ref:`Quickstart <quickstart>`
* :ref:`Example twitter app <example-app>`
* :ref:`Using peewee interactively <interactive>`
* :ref:`Models and fields <models>`
* :ref:`Querying <querying>`
* :ref:`Relationships and joins <relationships>`

Contents:
---------

.. toctree::
   :maxdepth: 2
   :glob:

   peewee/installation
   peewee/quickstart
   peewee/example
   peewee/interactive
   peewee/contributing
   peewee/database
   peewee/models
   peewee/querying
   peewee/query_operators
   peewee/relationships
   peewee/api
   peewee/sqlite_ext
   peewee/playhouse
   peewee/query_examples
   peewee/query_builder
   peewee/hacks
   peewee/changes

Note
----

If you find any bugs, odd behavior, or have an idea for a new feature please don't hesitate to `open an issue <https://github.com/coleifer/peewee/issues?state=open>`_ on GitHub or `contact me <https://charlesleifer.com/contact/>`_.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
