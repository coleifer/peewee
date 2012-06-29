.. _cookbook:

Extras
======

Peewee comes with numerous extras which I didn't really feel like including in
the main source module, but which might be interesting to implementers or fun
to mess around with.


apsw, an advanced sqlite driver
-------------------------------

The ``apsw_ext`` module contains a database class suitable for use with the
`apsw <http://code.google.com/p/apsw/>`_ sqlite driver.  With apsw, it is possible
to use some of the more advanced features of sqlite.  It also offers better performance
than pysqlite and finer-grained control over query execution.  For more information
on the differences between apsw and pysqlite, check `the apsw docs <http://apidoc.apsw.googlecode.com/hg/pysqlite.html>`_.

.. py:class:: APSWDatabase(database, **connect_kwargs)

    :param string database: filename of sqlite database
    :param connect_kwargs: keyword arguments passed to apsw when opening a connection

    .. py:method:: transaction([lock_type='deferred'])

        Functions just like the :py:meth:`Database.transaction` context manager,
        but accepts an additional parameter specifying the type of lock to use.

        :param string lock_type: type of lock to use when opening a new transaction

.. py:class:: APSWAdapter(timeout)

    :param int timeout: sqlite busy timeout in seconds (`docs <http://apidoc.apsw.googlecode.com/hg/connection.html?highlight=busytimeout#apsw.Connection.setbusytimeout>`_)

    .. py:method:: register_module(mod_name, mod_inst)

        Provides a way of globally registering a module.  For more information,
        see the `documentation on virtual tables <http://apidoc.apsw.googlecode.com/hg/vtable.html>`_.

        :param string mod_name: name to use for module
        :param object mod_inst: an object implementing the `Virtual Table <http://apidoc.apsw.googlecode.com/hg/vtable.html?highlight=virtual%20table#apsw.VTTable>`_ interface

    .. py:method:: unregister_module(mod_name)

        Unregister a module.

        :param string mod_name: name to use for module

.. py:class:: VirtualModel()

    A model subclass suitable for creating virtual tables.

    .. note:: You must specify the name for the extension module you wish to use

    .. py:attribute:: _extension_module

        The name of the extension module to use with this virtual table



pwiz, a model generator
-----------------------

``pwiz`` is a little script that ships with peewee and is capable of introspecting
an existing database and generating model code suitable for interacting with the
underlying data.  If you have a database already, pwiz can give you a nice boost
by generating skeleton code with correct column affinities and foreign keys.

If you install peewee using ``setup.py install``, pwiz will be installed as a "script"
and you can just run:

.. highlight:: console
.. code-block:: console

    pwiz.py -e postgresql -u postgres my_postgres_db > my_models.py

This will print a bunch of models to standard output.  So you can do this:

.. code-block:: console

    pwiz.py -e postgresql my_postgres_db > mymodels.py
    python # <-- fire up an interactive shell


.. highlight:: pycon
.. code-block:: pycon

    >>> from mymodels import Blog, Entry, Tag, Whatever
    >>> print [blog.name for blog in Blog.select()]


======    ========================= ============================================
Option    Meaning                   Example
======    ========================= ============================================
-h        show help
-e        database backend          -e mysql
-H        host to connect to        -H remote.db.server
-p        port to connect on        -p 9001
-u        database user             -u postgres
-P        database password         -P secret
-s        postgres schema           -s public
======    ========================= ============================================

The following are valid parameters for the engine:

* sqlite
* mysql
* postgresql


Signal support
--------------

Models with hooks for signals (a-la django) are provided in ``extras.signals``.
To use the signals, you will need all of your project's models to be a subclass
of ``extras.signals.Model``, which overrides the necessary methods to provide
support for the various signals.

.. highlight:: python
.. code-block:: python

    from extras.signals import Model, connect, post_save


    class MyModel(Model):
        data = IntegerField()

    @connect(post_save, sender=MyModel)
    def on_save_handler(model_class, instance, created):
        put_data_in_cache(instance.data)


The following signals are provided:

``pre_save``
    Called immediately before an object is saved to the database.  Provides an
    additional keyword argument ``created``, indicating whether the model is being
    saved for the first time or updated.
``post_save``
    Called immediately after an object is saved to the database.  Provides an
    additional keyword argument ``created``, indicating whether the model is being
    saved for the first time or updated.
``pre_delete``
    Called immediately before an object is deleted from the database when :py:meth:`Model.delete_instance`
    is used.
``post_delete``
    Called immediately after an object is deleted from the database when :py:meth:`Model.delete_instance`
    is used.
``pre_init``
    Called when a model class is first instantiated
``post_init``
    Called after a model class has been instantiated and the fields have been populated,
    for example when being selected as part of a database query.


Connecting handlers
^^^^^^^^^^^^^^^^^^^

Whenever a signal is dispatched, it will call any handlers that have been registered.
This allows totally separate code to respond to events like model save and delete.

The :py:class:`Signal` class provides a :py:meth:`~Signal.connect` method, which takes
a callback function and two optional parameters for "sender" and "name".  If specified,
the "sender" parameter should be a single model class and allows your callback to only
receive signals from that one model class.  The "name" parameter is used as a convenient alias
in the event you wish to unregister your signal handler.

Example usage:

.. code-block:: python

    from extras.signals import *

    def post_save_handler(sender, instance, created):
        print '%s was just saved' % instance

    # our handler will only be called when we save instances of SomeModel
    post_save.connect(post_save_handler, sender=SomeModel)

All signal handlers accept as their first two arguments ``sender`` and ``instance``,
where ``sender`` is the model class and ``instance`` is the actual model being acted
upon.

If you'd like, you can also use a decorator to connect signal handlers.  This is
functionally equivalent to the above example:

.. code-block:: python

    @connect(post_save, sender=SomeModel)
    def post_save_handler(sender, instance, created):
        print '%s was just saved' % instance


Signal API
^^^^^^^^^^

.. py:class:: Signal()

    Stores a list of receivers (callbacks) and calls them when the "send" method is invoked.

    .. py:method:: connect(receiver[, sender=None[, name=None]])

        Add the receiver to the internal list of receivers, which will be called
        whenever the signal is sent.

        :param callable receiver: a callable that takes at least two parameters,
            a "sender", which is the Model subclass that triggered the signal, and
            an "instance", which is the actual model instance.
        :param Model sender: if specified, only instances of this model class will
            trigger the receiver callback.
        :param string name: a short alias

        .. code-block:: python

            from extras.signals import post_save
            from project.handlers import cache_buster

            post_save.connect(cache_buster, name='project.cache_buster')

    .. py:method:: disconnect([receiver=None[, name=None]])

        Disconnect the given receiver (or the receiver with the given name alias)
        so that it no longer is called.  Either the receiver or the name must be
        provided.

        :param callable receiver: the callback to disconnect
        :param string name: a short alias

        .. code-block:: python

            post_save.disconnect(name='project.cache_buster')

    .. py:method:: send(instance, *args, **kwargs)

        Iterates over the receivers and will call them in the order in which
        they were connected.  If the receiver specified a sender, it will only
        be called if the instance is an instance of the sender.

        :param instance: a model instance


.. py:function:: connect(signal[, sender=None[, name=None]])

    Function decorator that is an alias for a signal's connect method:

    .. code-block:: python

        from extras.signals import connect, post_save

        @connect(post_save, name='project.cache_buster')
        def cache_bust_handler(sender, instance, *args, **kwargs):
            # bust the cache for this instance
            cache.delete(cache_key_for(instance))


Sqlite Extensions
-----------------

The sqlite extensions module provides a number of "sqlite-only" functions, including:

* :ref:`Full-text search support <full-text-search>`
* :ref:`Finer-grained transaction controls <granular-transactions>`
* :ref:`Custom aggregation functions, collations and user-defined functions <custom-shit>`

.. warning:: In order to start using the features described below, you will need to use the
    extension :py:class:`SqliteExtDatabase` class instead of :py:class:`SqliteDatabase`.

The code below will assume you are using the following database and base model:

.. code-block:: python

    from extras.sqlite_ext import *

    ext_db = SqliteExtDatabase('tmp.db')

    class BaseExtModel(Model):
        class Meta:
            database = ext_db


.. _full-text-search:

Full-text search
^^^^^^^^^^^^^^^^

Sqlite ships on most distributions with a full-text search (FTS) extension module.  This
can be used to expose search on your peewee models with very little work.  A complete
overview of sqlite's FTS is beyond the scope of this section, so please `read their documentation <http://www.sqlite.org/fts3.html>`_ for
the details.

To use FTS with your peewee models, you must subclass the ``extras.sqlite_ext.FTSModel``.
You can store data directly in this model or you can create a separate model that
references an existing model.  Since virtual tables do not support column indexes, this decision
will depend on how you intend to query the data stored in the full-text index.

Here is a simple example, showing the use of a separate model for storage (note
that we "mix-in" the :py:class:`FTSModel`):

.. code-block:: python

    class Post(BaseExtModel):
        message = TextField()

    class FTSPost(Post, FTSModel):
        pass

When you create the table, you can specify a number of options for the full-text
module, including a "source" table and a tokenizer:

.. code-block:: python

    Post.create_table()
    FTSPost.create_table(content_model=Post, tokenize='porter')

The above code instructs sqlite to create a virtual table storing our posts that
will be suitable for FTS.

.. code-block:: python

    bulk_import_some_posts()

    # rebuild the search index -- this will load up the contents of the Post table
    # and make it searchable via the FTSPost
    FTSPost.rebuild()

    # you can add/update/delete items from FTSPost just like a normal model
    FTSPost.create(message='this will be searchable as well')

    # perform a search
    FTSPost.select().where(message__match='search phrase')

    # search supports some advanced queries http://www.sqlite.org/fts3.html#section_3_1
    FTSPost.select().where(message__match='cats NOT dogs')

There is also support for ordering search results by rank.  The implementation is
based on the `C implementation <https://gist.github.com/6c94317878b12ef172ab>`_ found
at the bottom of the FTS docs:

.. code-block:: python

    FTSPost.select(['*', Rank('msg_rank')]).where(message__match='python').order_by(('msg_rank', 'desc'))

.. _granular-transactions:

Granular Transactions
^^^^^^^^^^^^^^^^^^^^^

Sqlite uses three different types of locks to control access during transactions.
Details on the three types can be found `in the docs <http://www.sqlite.org/lang_transaction.html>`_,
but here is a quick overview:

``deferred``
    locks are not acquired until the last moment.  multiple processes can continue
    to read the database.

``immediate``
    lock is acquired and no further writes are possible until lock is released, but
    other processes can continue to read.  Additionally, no other immediate or
    exclusive locks can be acquired.

``exclusive``
    lock is acquired and no further reads or writes are possible until lock is released

These various types of transactions can be opened using the special context-manager:

.. code-block:: python

    with ext_db.granular_transaction('exclusive'):
        # no other connections can read or write to the database now
        execute_some_queries()

    # safe for other processes to read and write again
    do_some_other_stuff()

.. _custom-shit:

Custom aggregators, collations and user-defined functions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sqlite allows you to specify custom functions that can stand-in as aggregators,
collations or functions, and then be executed as part of your queries.  If you
read the notes on the full-text search extension, the "sort by rank" is implemented
as a user-defined function.

Python's `sqlite documentation <http://docs.python.org/library/sqlite3.html#module-sqlite3>`_ gives
a good overview of how these types of functions can be used.

* `custom aggregates <http://docs.python.org/library/sqlite3.html#sqlite3.Connection.create_aggregate>`_

  .. code-block:: python

      class WeightedAverage(object):
          def __init__(self):
              self.total_weight = 0.0
              self.total_ct = 0.0

          def step(self, value, wt=None):
              wt = wt or 1.0
              self.total_weight += wt
              self.total_ct += wt * value

          def finalize(self):
              if self.total_weight != 0.0:
                  return self.total_ct / self.total_weight
              return 0.0

      ext_db.adapter.register_aggregate(WeightedAverage, 2, 'weighted_avg')

* `custom collations <http://docs.python.org/library/sqlite3.html#sqlite3.Connection.create_collation>`_

  .. code-block:: python

      def collate_reverse(s1, s2):
          return -cmp(s1, s2)

      ext_db.adapter.register_collation(collate_reverse)

* `custom functions <http://docs.python.org/library/sqlite3.html#sqlite3.Connection.create_function>`_

  .. code-block:: python

      def sha1(s):
          return hashlib.sha1(s).hexdigest()

      ext_db.adapter.register_function(sha1)


Swee'pea, syntactic sugar for peewee
------------------------------------

Calling it syntactic sugar is a bit of a stretch.  I wrote this stuff for fun after
learning about `ISBL <http://en.wikipedia.org/wiki/Relational_algebra>`_ from a coworker.
The `blog post can be found here <http://charlesleifer.com/blog/building-a-simple-query-dsl-with-peewee-orm/>`_.

At any rate, ISBL (Information Systems Base Language) is an old domain-specific
language for querying relational data, developed by IBM in the 60's.  Here are some
example SQL and ISBL queries:

.. code-block:: sql

    -- query the database for all active users
    SELECT id, username, active FROM users WHERE active = True

    -- query for tweets and the username of the sender
    SELECT t.id, t.message, u.username
    FROM tweets AS t
    INNER JOIN users AS u
        ON t.user_id = u.id
    WHERE u.active = True

.. code-block:: sql

    -- tables appear first -- the colon indicates a restriction (our where clause)
    -- and after the modulo is the "projection", or columns we want to select
    users : active = True % (id, username, active)

    (tweets * users) : user.active = True % (tweet.id, tweet.message, user.username)

Pretty cool.  In the above examples:

* multiplication signifies a join, the tables to query (FROM)
* a colon signifies a restriction, the columns to filter (WHERE)
* modulo signifies a projection, the columns to return (SELECT)

I hacked up a small implementation on top of peewee.  Since peewee does not support
the ":" (colon) character as an infix operator, I used the "power" operator to signify
a restriction:

.. code-block:: python

    # active users
    User ** (User.active == True)

    # tweets with the username of sender
    (Tweet * User) ** (User.active == True) % (Tweet.id, Tweet.message, User.username)

To try out swee'pea, simply replace ``from peewee import *`` with ``from extras.sweepea import *``
and start writing wacky queries:

.. code-block:: python

    from extras.sweepea import *

    class User(Model):
        username = CharField()
        active = BooleanField()

    class Tweet(Model):
        user = ForeignKeyField(User)
        message = CharField()

    # have fun!
    (User * Tweet) ** (User.active == True)
