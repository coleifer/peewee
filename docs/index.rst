.. peewee documentation master file, created by
   sphinx-quickstart on Thu Nov 25 21:20:29 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

peewee
======

.. image:: peewee-logo.png

Peewee is a simple and small ORM. It has few (but expressive) concepts, making it easy to learn and intuitive to use.

* A small, expressive ORM
* Written in python with support for versions 2.6+ and 3.2+.
* built-in support for sqlite, mysql and postgresql
* :ref:`numerous extensions available <playhouse>` (:ref:`postgres hstore/json/arrays <postgres_ext>`, :ref:`sqlite full-text-search <sqlite_ext>`, :ref:`schema migrations <migrate>`, and much more).

.. image:: postgresql.png
    :target: peewee/database.html#using-postgresql
    :alt: postgresql

.. image:: mysql.png
    :target: peewee/database.html#using-mysql
    :alt: mysql

.. image:: sqlite.png
    :target: peewee/database.html#using-sqlite
    :alt: sqlite

Peewee's source code hosted on `GitHub <https://github.com/coleifer/peewee>`_.

New to peewee? Here is a list of documents you might find most helpful when getting
started:

* :ref:`Quickstart guide <quickstart>` -- this guide covers all the bare essentials. It will take you between 5 and 10 minutes to go through it.
* :ref:`Guide to the various query operators <query-operators>` describes how to construct queries and combine expressions.
* :ref:`Field types table <field_types_table>` lists the various field types peewee supports and the parameters they accept. There is also an :ref:`extension module <playhouse>` that contains :ref:`special/custom field types <extra-fields>`.

Contents:
---------

.. toctree::
   :maxdepth: 2
   :glob:

   peewee/installation
   peewee/quickstart
   peewee/example
   peewee/more-resources
   peewee/contributing
   peewee/database
   peewee/models
   peewee/querying
   peewee/transactions
   peewee/playhouse
   peewee/api
   peewee/hacks

Note
----

If you find any bugs, odd behavior, or have an idea for a new feature please don't hesitate to `open an issue <https://github.com/coleifer/peewee/issues?state=open>`_ on GitHub or `contact me <http://charlesleifer.com/contact/>`_.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
