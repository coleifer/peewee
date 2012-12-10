.. _databases:

Databases
=========

Below the :py:class:`Model` level, peewee uses an abstraction for representing the database.  The
:py:class:`Database` is responsible for establishing and closing connections, making queries,
and gathering information from the database.  The :py:class:`Database` encapsulates functionality
specific to a given db driver.  For example difference in column types across database engines,
or support for certain features like sequences.  The database is responsible for smoothing out
the quirks of each backend driver to provide a consistent interface.

The :py:class:`Database` also uses a subclass of :py:class:`QueryCompiler` to generate
valid SQL.  The QueryCompiler maps the internal data structures used by peewee to
SQL statements.

For a high-level overview of working with transactions, check out the :ref:`transactions cookbook <working_with_transactions>`.

For notes on deferring instantiation of database, for example if loading configuration
at run-time, see the notes on :ref:`deferring initialization <deferring_initialization>`.

.. note::
    The internals of the :py:class:`Database` and :py:class:`QueryCompiler` will be
    of interest to anyone interested in adding support for another database driver.


Writing a database driver
-------------------------

Peewee currently supports Sqlite, MySQL and Postgresql.  These databases are very
popular and run the gamut from fast, embeddable databases to heavyweight servers
suitable for large-scale deployments.  That being said, there are a ton of cool
databases out there and adding support for your database-of-choice should be really
easy, provided the driver supports the `DB-API 2.0 spec <http://www.python.org/dev/peps/pep-0249/>`_.

The db-api 2.0 spec should be familiar to you if you've used the standard library
sqlite3 driver, psycopg2 or the like.  Peewee currently relies on a handful of parts:

* `Connection.commit`
* `Connection.execute`
* `Connection.rollback`
* `Cursor.description`
* `Cursor.fetchone`

These methods are generally wrapped up in higher-level abstractions and exposed
by the :py:class:`Database`, so even if your driver doesn't
do these exactly you can still get a lot of mileage out of peewee.  An example
is the `apsw sqlite driver <http://code.google.com/p/apsw/>`_ in the "playhouse"
module.


Starting out
^^^^^^^^^^^^

The first thing is to provide a subclass of :py:class:`Database` that will open
a connection.

.. code-block:: python

    from peewee import Database
    import foodb # our fictional driver


    class FooDatabase(Database):
        def _connect(self, database, **kwargs):
            return foodb.connect(database, **kwargs)


Essential methods to override
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :py:class:`Database` provides a higher-level API and is responsible for executing queries,
creating tables and indexes, and introspecting the database to get lists of tables. The above
implementation is the absolute minimum needed, though some features will not work -- for best
results you will want to additionally add a method for extracting a list of tables
and indexes for a table from the database.  We'll pretend that ``FooDB`` is a lot like
MySQL and has special "SHOW" statements:

.. code-block:: python

    class FooDatabase(Database):
        def _connect(self, database, **kwargs):
            return foodb.connect(database, **kwargs)

        def get_tables(self):
            res = self.execute('SHOW TABLES;')
            return [r[0] for r in res.fetchall()]

        def get_indexes_for_table(self, table):
            res = self.execute('SHOW INDEXES IN %s;' % self.quote_name(table))
            rows = sorted([(r[2], r[1] == 0) for r in res.fetchall()])
            return rows


Other things the database handles that are not covered here include:

* :py:meth:`~Database.last_insert_id` and :py:meth:`~Database.rows_affected`
* :py:attr:`~Database.interpolation` and :py:attr:`~Database.quote_char`
* :py:attr:`~Database.op_overrides` for mapping operations such as "LIKE/ILIKE" to their database equivalent

Refer to the :py:class:`Database` API reference or the `source code <https://github.com/coleifer/peewee/blob/master/peewee.py>`_. for details.

.. note:: If your driver conforms to the db-api 2.0 spec, there shouldn't be
    much work needed to get up and running.


Using our new database
^^^^^^^^^^^^^^^^^^^^^^

Our new database can be used just like any of the other database subclasses:

.. code-block:: python

    from peewee import *
    from foodb_ext import FooDatabase

    db = FooDatabase('my_database', user='foo', password='secret')

    class BaseModel(Model):
        class Meta:
            database = db

    class Blog(BaseModel):
        title = CharField()
        contents = TextField()
        pub_date = DateTimeField()
