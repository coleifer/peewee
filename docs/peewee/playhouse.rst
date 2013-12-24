.. _playhouse:

Playhouse, a collection of addons
=================================

Peewee comes with numerous extras which I didn't really feel like including in
the main source module, but which might be interesting to implementers or fun
to mess around with.

The playhouse includes modules for different database drivers or database
specific functionality:

* :ref:`apsw`
* :ref:`postgres_ext`
* :ref:`sqlite_ext`

Modules which expose higher-level python constructs:

* :ref:`djpeewee`
* :ref:`gfk`
* :ref:`kv`
* :ref:`shortcuts`
* :ref:`signals`

As well as tools for working with databases:

* :ref:`pwiz`
* :ref:`migrate`
* :ref:`csv_loader`
* :ref:`test_utils`


.. _apsw:

apsw, an advanced sqlite driver
-------------------------------

The ``apsw_ext`` module contains a database class suitable for use with
the apsw sqlite driver.

APSW Project page: https://code.google.com/p/apsw/

APSW is a really neat library that provides a thin wrapper on top of SQLite's
C interface, making it possible to use all of SQLite's advanced features.

Here are just a few reasons to use APSW, taken from the documentation:

* APSW gives all functionality of SQLite, including virtual tables, virtual
  file system, blob i/o, backups and file control.
* Connections can be shared across threads without any additional locking.
* Transactions are managed explicitly by your code.
* APSW can handle nested transactions.
* Unicode is handled correctly.
* APSW is faster.

For more information on the differences between apsw and pysqlite,
check `the apsw docs <http://apidoc.apsw.googlecode.com/hg/pysqlite.html>`_.

How to use the APSWDatabase
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from apsw_ext import *

    db = APSWDatabase(':memory:')

    class BaseModel(Model):
        class Meta:
            database = db

    class SomeModel(BaseModel):
        col1 = CharField()
        col2 = DateTimeField()


apsw_ext API notes
^^^^^^^^^^^^^^^^^^

.. py:class:: APSWDatabase(database, **connect_kwargs)

    :param string database: filename of sqlite database
    :param connect_kwargs: keyword arguments passed to apsw when opening a connection

    .. py:method:: transaction([lock_type='deferred'])

        Functions just like the :py:meth:`Database.transaction` context manager,
        but accepts an additional parameter specifying the type of lock to use.

        :param string lock_type: type of lock to use when opening a new transaction

    .. py:method:: register_module(mod_name, mod_inst)

        Provides a way of globally registering a module.  For more information,
        see the `documentation on virtual tables <http://apidoc.apsw.googlecode.com/hg/vtable.html>`_.

        :param string mod_name: name to use for module
        :param object mod_inst: an object implementing the `Virtual Table <http://apidoc.apsw.googlecode.com/hg/vtable.html?highlight=virtual%20table#apsw.VTTable>`_ interface

    .. py:method:: unregister_module(mod_name)

        Unregister a module.

        :param string mod_name: name to use for module

.. note::
    Be sure to use the ``Field`` subclasses defined in the ``apsw_ext``
    module, as they will properly handle adapting the data types for storage.


.. _postgres_ext:

Postgresql Extensions
---------------------

The postgresql extensions module provides a number of "postgres-only" functions,
currently:

* :ref:`hstore support <hstore>`
* :ref:`server-side cursors <server_side_cursors>`
* :py:class:`ArrayField` field type, for storing arrays.
* :py:class:`UUIDField` field type, for storing UUID objects.
* :py:class:`DateTimeTZ` field type, a timezone-aware datetime field.

In the future I would like to add support for more of postgresql's features.
If there is a particular feature you would like to see added, please
`open a Github issue <https://github.com/coleifer/peewee/issues>`_.

.. warning:: In order to start using the features described below, you will need to use the
    extension :py:class:`PostgresqlExtDatabase` class instead of :py:class:`PostgresqlDatabase`.

The code below will assume you are using the following database and base model:

.. code-block:: python

    from playhouse.postgres_ext import *

    ext_db = PostgresqlExtDatabase('peewee_test', user='postgres')

    class BaseExtModel(Model):
        class Meta:
            database = ext_db

.. _hstore:

hstore support
^^^^^^^^^^^^^^

`Postgresql hstore <http://www.postgresql.org/docs/current/static/hstore.html>`_ is
an embedded key/value store.  With hstore, you can store arbitrary key/value pairs
in your database alongside structured relational data.

Currently the ``postgres_ext`` module supports the following operations:

* Store and retrieve arbitrary dictionaries
* Filter by key(s) or partial dictionary
* Update/add one or more keys to an existing dictionary
* Delete one or more keys from an existing dictionary
* Select keys, values, or zip keys and values
* Retrieve a slice of keys/values
* Test for the existence of a key
* Test that a key has a non-NULL value


Using hstore
^^^^^^^^^^^^

To start with, you will need to import the custom database class and the hstore
functions from ``playhouse.postgres_ext`` (see above code snippet).  Then, it is
as simple as adding a :py:class:`HStoreField` to your model:

.. code-block:: python

    class House(BaseExtModel):
        address = CharField()
        features = HStoreField()


You can now store arbitrary key/value pairs on ``House`` instances:

.. code-block:: pycon

    >>> h = House.create(address='123 Main St', features={'garage': '2 cars', 'bath': '2 bath'})
    >>> h_from_db = House.get(House.id == h.id)
    >>> h_from_db.features
    {'bath': '2 bath', 'garage': '2 cars'}


You can filter by keys or partial dictionary:

.. code-block:: pycon

    >>> f = House.features
    >>> House.select().where(f.contains('garage')) # <-- all houses w/garage key
    >>> House.select().where(f.contains(['garage', 'bath'])) # <-- all houses w/garage & bath
    >>> House.select().where(f.contains({'garage': '2 cars'})) # <-- houses w/2-car garage

Suppose you want to do an atomic update to the house:

.. code-block:: pycon

    >>> f = House.features
    >>> new_features = House.features.update({'bath': '2.5 bath', 'sqft': '1100'})
    >>> query = House.update(features=new_features)
    >>> query.where(House.id == h.id).execute()
    1
    >>> h = House.get(House.id == h.id)
    >>> h.features
    {'bath': '2.5 bath', 'garage': '2 cars', 'sqft': '1100'}


Or, alternatively an atomic delete:

.. code-block:: pycon

    >>> query = House.update(features=f.delete('bath'))
    >>> query.where(House.id == h.id).execute()
    1
    >>> h = House.get(House.id == h.id)
    >>> h.features
    {'garage': '2 cars', 'sqft': '1100'}


Multiple keys can be deleted at the same time:

.. code-block:: pycon

    >>> query = House.update(features=f.delete('garage', 'sqft'))

You can select just keys, just values, or zip the two:

.. code-block:: pycon

    >>> f = House.features
    >>> for h in House.select(House.address, f.keys().alias('keys')):
    ...     print h.address, h.keys

    123 Main St [u'bath', u'garage']

    >>> for h in House.select(House.address, f.values().alias('vals')):
    ...     print h.address, h.vals

    123 Main St [u'2 bath', u'2 cars']

    >>> for h in House.select(House.address, f.items().alias('mtx')):
    ...     print h.address, h.mtx

    123 Main St [[u'bath', u'2 bath'], [u'garage', u'2 cars']]

You can retrieve a slice of data, for example, all the garage data:

.. code-block:: pycon

    >>> f = House.features
    >>> for h in House.select(House.address, f.slice('garage').alias('garage_data')):
    ...     print h.address, h.garage_data

    123 Main St {'garage': '2 cars'}

You can check for the existence of a key and filter rows accordingly:

.. code-block:: pycon

    >>> for h in House.select(House.address, f.exists('garage').alias('has_garage')):
    ...     print h.address, h.has_garage

    123 Main St True

    >>> for h in House.select().where(f.exists('garage')):
    ...     print h.address, h.features['garage'] # <-- just houses w/garage data

    123 Main St 2 cars

.. _server_side_cursors:

Server-side cursors
^^^^^^^^^^^^^^^^^^^

When psycopg2 executes a query, normally all results are fetched and returned to
the client by the backend.  This can cause your application to use a lot of memory
when making large queries.  Using server-side cursors, results are returned a
little at a time (by default 2000 records).  For the definitive reference, please see the `psycopg2 documentation <http://initd.org/psycopg/docs/usage.html#server-side-cursors>`_.

.. note:: To use server-side (or named) cursors, you must be using :py:class:`PostgresqlExtDatabase`.

To execute a query using a server-side cursor, simply wrap your select query
using the :py:func:`ServerSide` helper:

.. code-block:: python

    large_query = PageView.select()  # Build query normally.

    # Iterate over large query inside a transaction.
    for page_view in ServerSide(large_query):
        # do some interesting analysis here.
        pass

    # Server-side resources are released.

If you would like all ``SELECT`` queries to automatically use a server-side
cursor, you can specify this when creating your :py:class:`PostgresqlExtDatabase`:

.. code-block:: python

    from postgres_ext import PostgresqlExtDatabase

    ss_db = PostgresqlExtDatabase('my_db', server_side_cursors=True)

.. note::
    Server-side cursors live only as long as the transaction, so for this reason
    peewee will not automatically call ``commit()`` after executing a ``SELECT``
    query.  If you do not ``commit`` after you are done iterating, you will not
    release the server-side resources until the connection is closed (or the
    transaction is committed later).  Furthermore, since peewee will by default
    cache rows returned by the cursor, you should always call ``.iterator()``
    when iterating over a large query.

    If you are using the :py:func:`ServerSide` helper, the transaction and
    call to ``iterator()`` will be handled transparently.


postgres_ext API notes
^^^^^^^^^^^^^^^^^^^^^^

.. py:class:: PostgresqlExtDatabase(database[, server_side_cursors=False[,...]])

    Identical to :py:class:`PostgresqlDatabase` but required in order to support:

    * :ref:`server_side_cursors`
    * :py:class:`ArrayField`
    * :py:class:`DateTimeTZField`
    * :py:class:`HStoreField`
    * :py:class:`UUIDField`

    :param str database: Name of database to connect to.
    :param bool server_side_cursors: Whether ``SELECT`` queries should utilize
        server-side cursors.

    If using ``server_side_cursors``, also be sure to wrap your queries with
    :py:func:`ServerSide`.

.. py:function:: ServerSide(select_query)

    Wrap the given select query in a transaction, and call it's :py:meth:`~SelectQuery.iterator`
    method to avoid caching row instances.  In order for the server-side resources
    to be released, be sure to exhaust the generator (iterate over all the rows).

    :param select_query: a :py:class:`SelectQuery` instance.
    :rtype: ``generator``

    Usage:

    .. code-block:: python

        large_query = PageView.select()
        for page_view in ServerSide(large_query):
            # Do something interesting.
            pass

        # At this point server side resources are released.

.. py:class:: ArrayField([field_class=IntegerField[, dimensions=1]])

    Field capable of storing arrays of the provided `field_class`.

    :param field_class: a subclass of :py:class:`Field`, e.g. :py:class:`IntegerField`.
    :param int dimensions: dimensions of array.

    You can store and retrieve lists (or lists-of-lists):

    .. code-block:: python

        class BlogPost(BaseModel):
            content = TextField()
            tags = ArrayField(CharField)


        post = BlogPost(content='awesome', tags=['foo', 'bar', 'baz'])

    Additionally, you can use the ``__getitem__`` API to query values or slices
    in the database:

    .. code-block:: python

        # Get the first tag on a given blog post.
        first_tag = (BlogPost
                     .select(BlogPost.tags[0].alias('first_tag'))
                     .where(BlogPost.id == 1)
                     .dicts()
                     .get())

        # first_tag = {'first_tag': 'foo'}

    Get a slice of values:

    .. code-block:: python

        # Get the first two tags.
        two_tags = (BlogPost
                    .select(BlogPost.tags[:2].alias('two'))
                    .dicts()
                    .get())
        # two_tags = {'two': ['foo', 'bar']}

.. py:class:: DateTimeTZField(*args, **kwargs)

    A timezone-aware subclass of :py:class:`DateTimeField`.

.. py:class:: HStoreField(*args, **kwargs)

    A field for storing and retrieving arbitrary key/value pairs.  For details
    on usage, see :ref:`hstore`.

    .. py:method:: keys()

        Returns the keys for a given row.

        .. code-block:: pycon

            >>> f = House.features
            >>> for h in House.select(House.address, f.keys().alias('keys')):
            ...     print h.address, h.keys

            123 Main St [u'bath', u'garage']

    .. py:method:: values()

        Return the values for a given row.

        .. code-block:: pycon

            >>> for h in House.select(House.address, f.values().alias('vals')):
            ...     print h.address, h.vals

            123 Main St [u'2 bath', u'2 cars']

    .. py:method:: items()

        Like python's ``dict``, return the keys and values in a list-of-lists:

        .. code-block:: pycon

            >>> for h in House.select(House.address, f.items().alias('mtx')):
            ...     print h.address, h.mtx

            123 Main St [[u'bath', u'2 bath'], [u'garage', u'2 cars']]

    .. py:method:: slice(*args)

        Return a slice of data given a list of keys.

        .. code-block:: pycon

            >>> f = House.features
            >>> for h in House.select(House.address, f.slice('garage').alias('garage_data')):
            ...     print h.address, h.garage_data

            123 Main St {'garage': '2 cars'}

    .. py:method:: exists(key)

        Query for whether the given key exists.

        .. code-block:: pycon

            >>> for h in House.select(House.address, f.exists('garage').alias('has_garage')):
            ...     print h.address, h.has_garage

            123 Main St True

            >>> for h in House.select().where(f.exists('garage')):
            ...     print h.address, h.features['garage'] # <-- just houses w/garage data

            123 Main St 2 cars

    .. py:method:: defined(key)

        Query for whether the given key has a value associated with it.

    .. py:method:: update(**data)

        Perform an atomic update to the keys/values for a given row or rows.

        .. code-block:: pycon

            >>> query = House.update(features=House.features.update(
            ...     sqft=2000,
            ...     year_built=2012))
            >>> query.where(House.id == 1).execute()

    .. py:method:: delete(*keys)

        Delete the provided keys for a given row or rows.

        .. note:: We will use an ``UPDATE`` query.

        .. code-block:: pycon

        >>> query = House.update(features=House.features.delete(
        ...     'sqft', 'year_built'))
        >>> query.where(House.id == 1).execute()

    .. py:method:: contains(value)

        :param value: Either a ``dict``, a ``list`` of keys, or a single key.

        Query rows for the existence of either:

        * a partial dictionary.
        * a list of keys.
        * a single key.

        .. code-block:: pycon

            >>> f = House.features
            >>> House.select().where(f.contains('garage')) # <-- all houses w/garage key
            >>> House.select().where(f.contains(['garage', 'bath'])) # <-- all houses w/garage & bath
            >>> House.select().where(f.contains({'garage': '2 cars'})) # <-- houses w/2-car garage

    .. py:method:: contains_any(*keys)

        :param keys: One or more keys to search for.

        Query rows for the existince of *any* key.


.. py:class:: UUIDField(*args, **kwargs)

    A field for storing and retrieving ``UUID`` objects.

.. _sqlite_ext:

Sqlite Extensions
-----------------

The SQLite extensions module provides support for some interesting sqlite-only
features:

* Define custom aggregates, collations and functions.
* Basic support for virtual tables.
* Basic support for FTS3/4 (sqlite full-text search).
* Specify isolation level in transactions.


sqlite_ext API notes
^^^^^^^^^^^^^^^^^^^^

.. py:class:: SqliteExtDatabase(database, **kwargs)

    Subclass of the :py:class:`SqliteDatabase` that provides some advanced
    features only offered by Sqlite.

    * Register custom aggregates, collations and functions
    * Specify a row factory
    * Advanced transactions (specify isolation level)

    .. py:method:: aggregate(num_params[, name])

        Class-decorator for registering custom aggregation functions.

        :param num_params: integer representing number of parameters the
            aggregate function accepts.
        :param name: string name for the aggregate, defaults to the name of
            the class.

        .. code-block:: python

            @db.aggregate(1, 'product')
            class Product(object):
                """Like sum, except calculate the product of a series of numbers."""
                def __init__(self):
                    self.product = 1

                def step(self, value):
                    self.product *= value

                def finalize(self):
                    return self.product

            # To use this aggregate:
            product = (Score
                       .select(fn.product(Score.value))
                       .scalar())

    .. py:method:: collation([name])

        Function decorator for registering a custom collation.

        :param name: string name to use for this collation.

        .. code-block:: python

            @db.collation()
            def collate_reverse(s1, s2):
                return -cmp(s1, s2)

            # To use this collation:
            Book.select().order_by(collate_reverse.collation(Book.title))

        As you might have noticed, the original ``collate_reverse`` function
        has a special attribute called ``collation`` attached to it.  This extra
        attribute provides a shorthand way to generate the SQL necessary to use
        our custom collation.

    .. py:method:: func([name[, num_params]])

        Function decorator for registering user-defined functions.

        :param name: name to use for this function.
        :param num_params: number of parameters this function accepts.  If not
            provided, peewee will introspect the function for you.

        .. code-block:: python

            @db.func()
            def title_case(s):
                return s.title()

            # Use in the select clause...
            titled_books = Book.select(fn.title_case(Book.title))

            @db.func()
            def sha1(s):
                return hashlib.sha1(s).hexdigest()

            # Use in the where clause...
            user = User.select().where(
                (User.username == username) &
                (fn.sha1(User.password) == password_hash)).get()

    .. py:method:: granular_transaction([lock_type='deferred'])

        With the ``granular_transaction`` helper, you can specify the isolation level
        for an individual transaction.  The valid options are:

        * ``exclusive``
        * ``immediate``
        * ``deferred``

        Example usage:

        .. code-block:: python

            with db.granular_transaction('exclusive'):
                # no other readers or writers!
                (Account
                 .update(Account.balance=Account.balance - 100)
                 .where(Account.id == from_acct)
                 .execute())

                (Account
                 .update(Account.balance=Account.balance + 100)
                 .where(Account.id == to_acct)
                 .execute())


.. py:class:: VirtualModel

    Subclass of :py:class:`Model` that signifies the model operates using a
    virtual table provided by a sqlite extension.

    .. py:attribute:: _extension = 'name of sqlite extension'


.. py:class:: FTSModel

    Model class that provides support for Sqlite's full-text search extension.
    Models should be defined normally, however there are a couple caveats:

    * Indexes are ignored completely
    * Sqlite will treat all column types as :py:class:`TextField` (although you
      can store other data types, Sqlite will treat them as text).

    Therefore it usually makes sense to index the content you intend to search
    and a single link back to the original document, since all SQL queries
    *except* full-text searches and ``rowid`` lookups will be slow.

    Example:

    .. code-block:: python

        class Document(FTSModel):
            title = TextField()  # type affinities are ignored by FTS, so use TextField
            content = TextField()

        Document.create_table(tokenize='porter')  # use the porter stemmer.

        # populate documents using normal operations.
        for doc in list_of_docs_to_index:
            Document.create(title=doc['title'], content=doc['content'])

        # use the "match" operation for FTS queries.
        matching_docs = Document.select().where(match(Document.title, 'some query'))

        # to sort by best match, use the custom "rank" function.
        best = (Document
                .select(Document, Document.rank('score'))
                .where(match(Document.title, 'some query'))
                .order_by(SQL('score').desc()))

        # or use the shortcut method:
        best = Document.match('some phrase')

    If you have an existing table and would like to add search for a column
    on that table, you can specify it using the ``content`` option:

    .. code-block:: python

        class Blog(Model):
            title = CharField()
            pub_date = DateTimeField()
            content = TextField()  # we want to search this.

        class FTSBlog(FTSModel):
            content = TextField()

        Blog.create_table()
        FTSBlog.create_table(content=Blog.content)

        # Now, we can manage content in the FTSBlog.  To populate it with
        # content:
        FTSBlog.rebuild()

        # Optimize the index.
        FTSBlog.optimize()

    The ``content`` option accepts either a single :py:class:`Field` or a :py:class:`Model`
    and can reduce the amount of storage used.  However, content will need to be
    manually moved to/from the associated ``FTSModel``.

    .. py:classmethod:: create_table([fail_silently=False[, **options]])

        :param boolean fail_silently: do not re-create if table already exists.
        :param options: options passed along when creating the table, e.g. ``content``.

    .. py:classmethod:: rebuild()

        Rebuild the search index -- this only works when the ``content`` option
        was specified during table creation.

    .. py:classmethod:: optimize()

        Optimize the search index.

    .. py:classmethod:: match(search_phrase)

        Shorthand way of performing a search for a given phrase.  Example:

        .. code-block:: python

            for doc in Document.match('search phrase'):
                print 'match: ', doc.title

    .. py:classmethod:: rank([alias])

        Shorthand way of sorting search results by the quality of their match.

        .. code-block:: python

            docs = (Document
                    .select(Document, Document.rank().alias('score'))
                    .where(match(Document, search))
                    .order_by(SQL('score').desc()))

        The above code is exactly what the :py:meth:`match` function
        provides.

.. _djpeewee:

Django Integration
------------------

The Django ORM provides a very high-level abstraction over SQL and as a consequence is in some ways
`limited in terms of flexibility or expressiveness <http://charlesleifer.com/blog/shortcomings-in-the-django-orm-and-a-look-at-peewee-a-lightweight-alternative/>`_. I
wrote a `blog post <http://charlesleifer.com/blog/the-search-for-the-missing-link-what-lies-between-sql-and-django-s-orm-/>`_
describing my search for a "missing link" between Django's ORM and the SQL it
generates, concluding that no such layer exists.  The ``djpeewee`` module attempts
to provide an easy-to-use, structured layer for generating SQL queries for use
with Django's ORM.

A couple use-cases might be:

* Joining on fields that are not related by foreign key (for example UUID fields).
* Performing aggregate queries on calculated values.
* Features that Django does not support such as ``CASE`` statements.
* Utilizing SQL functions that Django does not support, such as ``SUBSTR``.
* Replacing nearly-identical SQL queries with reusable, composable data-structures.

Below is an example of how you might use this:

.. code-block:: python

    # Django model.
    class Event(models.Model):
        start_time = models.DateTimeField()
        end_time = models.DateTimeField()
        title = models.CharField(max_length=255)

    # Suppose we want to find all events that are longer than an hour.  Django
    # does not support this, but we can use peewee.
    from playhouse.djpeewee import translate
    P = translate(Event)
    query = (P.Event
             .select()
             .where(
                 (P.Event.end_time - P.Event.start_time) > timedelta(hours=1)))

    # Now feed our peewee query into Django's `raw()` method:
    sql, params = query.sql()
    Event.objects.raw(sql, params)

Foreign keys and Many-to-many relationships
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :py:func:`translate` function will recursively traverse the graph of models
and return a dictionary populated with everything it finds.  Back-references are
not searched by default, but can be included by specifying ``backrefs=True``.

Example:

.. code-block:: pycon

    >>> from django.contrib.auth.models import User, Group
    >>> from playhouse.djpeewee import translate
    >>> translate(User, Group)
    {'ContentType': peewee.ContentType,
     'Group': peewee.Group,
     'Group_permissions': peewee.Group_permissions,
     'Permission': peewee.Permission,
     'User': peewee.User,
     'User_groups': peewee.User_groups,
     'User_user_permissions': peewee.User_user_permissions}

As you can see in the example above, although only `User` and `Group` were passed
in to :py:func:`translate`, several other models which are related by foreign key
were also created. Additionally, the many-to-many "through" tables were created
as separate models since peewee does not abstract away these types of relationships.

Using the above models it is possible to construct joins.  The following example
will get all users who belong to a group that starts with the letter "A":

.. code-block:: pycon

    >>> P = translate(User, Group)
    >>> query = P.User.select().join(P.User_groups).join(P.Group).where(
    ...     fn.Lower(fn.Substr(P.Group.name, 1, 1)) == 'a')
    >>> sql, params = query.sql()
    >>> print sql  # formatted for legibility
    SELECT t1."id", t1."password", ...
    FROM "auth_user" AS t1
    INNER JOIN "auth_user_groups" AS t2 ON (t1."id" = t2."user_id")
    INNER JOIN "auth_group" AS t3 ON (t2."group_id" = t3."id")
    WHERE (Lower(Substr(t3."name", %s, %s)) = %s)

djpeewee API
^^^^^^^^^^^^

.. py:function:: translate(*models, **options)

    Translate the given Django models into roughly equivalent peewee models
    suitable for use constructing queries. Foreign keys and many-to-many relationships
    will be followed and models generated, although back references are not traversed.

    :param models: One or more Django model classes.
    :param options: A dictionary of options, see note below.
    :returns: A dict-like object containing the generated models, but which supports
        dotted-name style lookups.

    The following are valid options:

    * ``recurse``: Follow foreign keys and many to many (default: ``True``).
    * ``max_depth``: Maximum depth to recurse (default: ``None``, unlimited).
    * ``backrefs``: Follow backrefs (default: ``False``).
    * ``exclude``: A list of models to exclude.


.. _gfk:

Generic foreign keys
--------------------

The ``gfk`` module provides a Generic ForeignKey (GFK), similar to Django.  A GFK
is composed of two columns: an object ID and an object type identifier.  The
object types are collected in a global registry (``all_models``).

How a :py:class:`GFKField` is resolved:

1. Look up the object type in the global registry (returns a model class)
2. Look up the model instance by object ID

.. note:: In order to use Generic ForeignKeys, your application's models *must*
    subclass ``playhouse.gfk.Model``.  This ensures that the model class will
    be added to the global registry.

.. note:: GFKs themselves are not actually a field and will not add a column
    to your table.

Like regular ForeignKeys, GFKs support a "back-reference" via the :py:class:`ReverseGFK`
descriptor.

How to use GFKs
^^^^^^^^^^^^^^^

1. Be sure your model subclasses ``playhouse.gfk.Model``
2. Add a :py:class:`CharField` to store the ``object_type``
3. Add a field to store the ``object_id`` (usually a :py:class:`IntegerField`)
4. Add a :py:class:`GFKField` and instantiate it with the names of the ``object_type``
   and ``object_id`` fields.
5. (optional) On any other models, add a :py:class:`ReverseGFK` descriptor

Example:

.. code-block:: python

    from playhouse.gfk import *

    class Tag(Model):
        tag = CharField()
        object_type = CharField(null=True)
        object_id = IntegerField(null=True)
        object = GFKField('object_type', 'object_id')

    class Blog(Model):
        tags = ReverseGFK(Tag, 'object_type', 'object_id')

    class Photo(Model):
        tags = ReverseGFK(Tag, 'object_type', 'object_id')

How you use these is pretty straightforward hopefully:

.. code-block:: pycon

    >>> b = Blog.create(name='awesome post')
    >>> Tag.create(tag='awesome', object=b)
    >>> b2 = Blog.create(name='whiny post')
    >>> Tag.create(tag='whiny', object=b2)

    >>> b.tags # <-- a select query
    <class '__main__.Tag'> SELECT t1."id", t1."tag", t1."object_type", t1."object_id" FROM "tag" AS t1 WHERE ((t1."object_type" = ?) AND (t1."object_id" = ?)) [u'blog', 1]

    >>> [x.tag for x in b.tags]
    [u'awesome']

    >>> [x.tag for x in b2.tags]
    [u'whiny']

    >>> p = Photo.create(name='picture of cat')
    >>> Tag.create(object=p, tag='kitties')
    >>> Tag.create(object=p, tag='cats')

    >>> [x.tag for x in p.tags]
    [u'kitties', u'cats']

    >>> [x.tag for x in Blog.tags]
    [u'awesome', u'whiny']

    >>> t = Tag.get(Tag.tag == 'awesome')
    >>> t.object
    <__main__.Blog at 0x268f450>

    >>> t.object.name
    u'awesome post'

GFK API
^^^^^^^

.. py:class:: GFKField([model_type_field='object_type'[, model_id_field='object_id']])

    Provide a clean API for storing "generic" foreign keys.  Generic foreign keys
    are comprised of an object type, which maps to a model class, and an object id,
    which maps to the primary key of the related model class.

    Setting the GFKField on a model will automatically populate the ``model_type_field``
    and ``model_id_field``.  Similarly, getting the GFKField on a model instance
    will "resolve" the two fields, first looking up the model class, then looking
    up the instance by ID.

.. py:class:: ReverseGFK(model, [model_type_field='object_type'[, model_id_field='object_id']])

    Back-reference support for :py:class:`GFKField`.

.. _kv:

Key/Value Store
---------------

Provides a simple key/value store, using a dictionary API.  By default the
the :py:class:`KeyStore` will use an in-memory sqlite database, but any database
will work.

To start using the key-store, create an instance and pass it a field to use
for the values.

.. code-block:: python

    >>> kv = KeyStore(TextField())
    >>> kv['a'] = 'A'
    >>> kv['a']
    'A'

.. note::
  To store arbitrary python objects, use the :py:class:`PickledKeyStore`, which
  stores values in a pickled :py:class:`BlobField`.

Using the :py:class:`KeyStore` it is possible to use "expressions" to retrieve
values from the dictionary.  For instance, imagine you want to get all keys
which contain a certain substring:

.. code-block:: python

    >>> keys_matching_substr = kv[kv.key % '%substr%']
    >>> keys_start_with_a = kv[fn.Lower(fn.Substr(kv.key, 1, 1)) == 'a']

KeyStore API
^^^^^^^^^^^^

.. py:class:: KeyStore(value_field[, ordered=False[, database=None]])

    Lightweight dictionary interface to a model containing a key and value.
    Implements common dictionary methods, such as ``__getitem__``, ``__setitem__``,
    ``get``, ``pop``, ``items``, ``keys``, and ``values``.

    :param Field value_field: Field instance to use as value field, e.g. an
        instance of :py:class:`TextField`.
    :param boolean ordered: Whether the keys should be returned in sorted order
    :param Database database: :py:class:`Database` class to use for the storage
        backend.  If none is supplied, an in-memory Sqlite DB will be used.

    Example:

    .. code-block:: pycon

        >>> from playhouse.kv import KeyStore
        >>> kv = KeyStore(TextField())
        >>> kv['a'] = 'foo'
        >>> for k, v in kv:
        ...     print k, v
        a foo

        >>> 'a' in kv
        True
        >>> 'b' in kv
        False

.. py:class:: PickledKeyStore([ordered=False[, database=None]])

    Identical to the :py:class:`KeyStore` except *anything* can be stored as
    a value in the dictionary.  The storage for the value will be a pickled
    :py:class:`BlobField`.

    Example:

    .. code-block:: pycon

        >>> from playhouse.kv import PickledKeyStore
        >>> pkv = PickledKeyStore()
        >>> pkv['a'] = 'A'
        >>> pkv['b'] = 1.0
        >>> list(pkv.items())
        [(u'a', 'A'), (u'b', 1.0)]

.. _shortcuts:

Shortcuts
---------

This module contains helper functions for expressing things that would otherwise
be somewhat verbose or cumbersome using peewee's APIs.

.. py:function:: case(predicate, expression_tuples, default=None)

    :param predicate: A SQL expression or can be ``None``.
    :param expression_tuples: An iterable containing one or more 2-tuples
      comprised of an expression and return value.
    :param default: default if none of the cases match.

    Example SQL case statements:

    .. code-block:: sql

        -- case with predicate --
        SELECT "username",
          CASE "user_id"
            WHEN 1 THEN "one"
            WHEN 2 THEN "two"
            ELSE "?"
          END
        FROM "users";

        -- case with no predicate (inline expressions) --
        SELECT "username",
          CASE
            WHEN "user_id" = 1 THEN "one"
            WHEN "user_id" = 2 THEN "two"
            ELSE "?"
          END
        FROM "users";

    Equivalent function invocations:

    .. code-block:: python

        User.select(User.username, case(User.user_id, (
          (1, "one"),
          (2, "two")), "?"))

        User.select(User.username, case(None, (
          (User.user_id == 1, "one"),  # note the double equals
          (User.user_id == 2, "two")), "?"))

    You can specify a value for the CASE expression using the ``alias()``
    method:

    .. code-block:: python

        User.select(User.username, case(User.user_id, (
          (1, "one"),
          (2, "two")), "?").alias("id_string"))


.. _signals:

Signal support
--------------

Models with hooks for signals (a-la django) are provided in ``playhouse.signals``.
To use the signals, you will need all of your project's models to be a subclass
of ``playhouse.signals.Model``, which overrides the necessary methods to provide
support for the various signals.

.. highlight:: python
.. code-block:: python

    from playhouse.signals import Model, post_save


    class MyModel(Model):
        data = IntegerField()

    @post_save(sender=MyModel)
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

    from playhouse.signals import *

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

    @post_save(sender=SomeModel)
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

            from playhouse.signals import post_save
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


    .. py:method __call__([sender=None[, name=None]])

        Function decorator that is an alias for a signal's connect method:

        .. code-block:: python

            from playhouse.signals import connect, post_save

            @post_save(name='project.cache_buster')
            def cache_bust_handler(sender, instance, *args, **kwargs):
                # bust the cache for this instance
                cache.delete(cache_key_for(instance))

.. _pwiz:

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

    pwiz.py -e postgresql -u postgres my_postgres_db

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

.. _migrate:

Basic Schema Migrations
-----------------------

.. note:: This module is still pretty experimental, but it provides a light
    API for doing schema migrations with postgresql.

Instantiate a migrator:

.. code-block:: python

    my_db = PostgresqlDatabase(...)
    migrator = Migrator(my_db)

Adding a field to a model:

.. code-block:: python

    # declare a field instance
    new_pubdate_field = DateTimeField(null=True)

    # in a transaction, add the column to your model
    with my_db.transaction():
        migrator.add_column(Story, new_pubdate_field, 'pub_date')

Renaming a field:

.. code-block:: python

    # specify the original name of the field and its new name
    with my_db.transaction():
        migrator.rename_column(Story, 'pub_date', 'publish_date')

Dropping a field:

.. code-block:: python

   # specify the field name to drop
   with my_db.transaction():
       migrator.drop_column(Story, 'some_old_field')

Setting nullable / not nullable

.. code-block:: python

    with my_db.transaction():
        # make pubdate not nullable
        migrator.set_nullable(Story, Story.pub_date, False)

Renaming a table

.. code-block:: python

    with my_db.transaction():
        migrator.rename_table(Story, 'stories')


.. _csv_loader:

CSV Loader
----------

This module contains helpers for loading CSV data into a database.  CSV files can
be introspected to generate an appropriate model class for working with the data.
This makes it really easy to explore the data in a CSV file using Peewee and SQL.

Here is how you would load a CSV file into an in-memory SQLite database.  The
call to :py:func:`load_csv` returns a :py:class:`Model` instance suitable for
working with the CSV data:

.. code-block:: python

    from peewee import *
    from playhouse.csv_loader import load_csv
    db = SqliteDatabase(':memory:')
    ZipToTZ = load_csv(db, 'zip_to_tz.csv')

Now we can run queries using the new model.

.. code-block:: pycon

    # Get the timezone for a zipcode.
    >>> ZipToTZ.get(ZipToTZ.zip == 66047).timezone
    'US/Central'

    # Get all the zipcodes for my town.
    >>> [row.zip for row in ZipToTZ.select().where(
    ...     (ZipToTZ.city == 'Lawrence') && (ZipToTZ.state == 'KS'))]
    [66044, 66045, 66046, 66047, 66049]

For more information and examples check out this `blog post <http://charlesleifer.com/blog/using-peewee-to-explore-csv-files/>`_.


CSV Loader API
^^^^^^^^^^^^^^

.. py:function:: load_csv(db_or_model, filename[, fields=None[, field_names=None[, has_header=True[, sample_size=10[, converter=None[, db_table=None[, **reader_kwargs]]]]]]])

    Load a CSV file into the provided database or model class, returning a
    :py:class:`Model` suitable for working with the CSV data.

    :param db_or_model: Either a :py:class:`Database` instance or a :py:class:`Model` class.  If a model is not provided, one will be automatically generated for you.
    :param str filename: Path of CSV file to load.
    :param list fields: A list of :py:class:`Field` instances mapping to each column in the CSV.  This allows you to manually specify the column types.  If not provided, and a model is not provided, the field types will be determined automatically.
    :param list field_names: A list of strings to use as field names for each column in the CSV.  If not provided, and a model is not provided, the field names will be determined by looking at the header row of the file.  If no header exists, then the fields will be given generic names.
    :param bool has_header: Whether the first row is a header.
    :param int sample_size: Number of rows to look at when introspecting data types.  If set to ``0``, then a generic field type will be used for all fields.
    :param RowConverter converter: a :py:class:`RowConverter` instance to use for introspecting the CSV.  If not provided, one will be created.
    :param str db_table: The name of the database table to load data into.  If this value is not provided, it will be determined using the filename of the CSV file.  If a model is provided, this value is ignored.
    :param reader_kwargs: Arbitrary keyword arguments to pass to the ``csv.reader`` object, such as the dialect, separator, etc.
    :rtype: A :py:class:`Model` suitable for querying the CSV data.

    Basic example -- field names and types will be introspected:

    .. code-block:: python

        from peewee import *
        from playhouse.csv_loader import *
        db = SqliteDatabase(':memory:')
        User = load_csv(db, 'users.csv')

    Using a pre-defined model:

    .. code-block:: python

        class ZipToTZ(Model):
            zip = IntegerField()
            timezone = CharField()

        load_csv(ZipToTZ, 'zip_to_tz.csv')

    Specifying fields:

    .. code-block:: python

        fields = [DecimalField(), IntegerField(), IntegerField(), DateField()]
        field_names = ['amount', 'from_acct', 'to_acct', 'timestamp']
        Payments = load_csv(db, 'payments.csv', fields=fields, field_names=field_names, has_header=False)


.. _test_utils:

Test Utils
----------

Contains utilities helpful when testing peewee projects.

.. py:class:: test_database(db, models[, create_tables=True[, fail_silently=False]])

    Context manager that lets you use a different database with a set of
    models.  Models can also be automatically created and dropped.

    This context manager helps make it possible to test your peewee models
    using a "test-only" database.

    :param Database db: Database to use with the given models
    :param models: a ``list`` of :py:class:`Model` classes to use with the ``db``
    :param boolean create_tables: Whether tables should be automatically created
        and dropped.
    :param boolean fail_silently: Whether the table create / drop should fail
        silently.

    Example:

    .. code-block:: python

        from unittest import TestCase
        from playhouse.test_utils import test_database
        from peewee import *

        from my_app.models import User, Tweet

        test_db = SqliteDatabase(':memory:')

        class TestUsersTweets(TestCase):
            def create_test_data(self):
                # ... create a bunch of users and tweets
                for i in range(10):
                    User.create(username='user-%d' % i)

            def test_timeline(self):
                with test_database(test_db, (User, Tweet)):
                    # This data will be created in `test_db`
                    self.create_test_data()

                    # Perform assertions on test data inside ctx manager.
                    self.assertEqual(Tweet.timeline('user-0') [...])

                # once we exit the context manager, we're back to using the normal database
