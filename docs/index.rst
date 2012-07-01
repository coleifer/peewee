.. peewee documentation master file, created by
   sphinx-quickstart on Thu Nov 25 21:20:29 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

peewee
======

* a small orm
* written in python
* provides a lightweight querying interface over sql
* uses sql concepts when querying, like joins and where clauses
* support for special extensions like `hstore <http://peewee.readthedocs.org/en/latest/peewee/playhouse.html#postgresql-extensions-hstore-ltree>`_ and `full-text search <http://peewee.readthedocs.org/en/latest/peewee/playhouse.html#full-text-search>`_

For flask integration, including an admin interface and RESTful API, check
out `flask-peewee <https://github.com/coleifer/flask-peewee/>`_.

Contents:
---------

.. toctree::
   :maxdepth: 2
   :glob:

   peewee/overview
   peewee/installation
   peewee/cookbook
   peewee/example
   peewee/models
   peewee/fields
   peewee/querying
   peewee/database
   peewee/playhouse

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
