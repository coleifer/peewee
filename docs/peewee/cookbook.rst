.. _cookbook:

Peewee Cookbook
===============

Below are outlined some of the ways to perform typical database-related tasks
with peewee.

Examples will use the following models:

.. code-block:: python

    from peewee import *

    class User(Model):
        username = CharField()

    class Tweet(Model):
        user = ForeignKeyField(User, related_name='tweets')
        message = TextField()
        created_date = DateTimeField(default=datetime.datetime.now)
        is_published = BooleanField(default=True)


Database and Connection Recipes
-------------------------------

Creating a database connection and tables
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

While it is not necessary to explicitly connect to the database before using it,
managing connections explicitly is a good practice.  This way if the connection
fails, the exception can be caught during the "connect" step, rather than some
arbitrary time later when a query is executed.

.. code-block:: python

    >>> database = SqliteDatabase('stats.db')
    >>> database.connect()


To use this database with your models, specify it in an inner "Meta" class:

.. code-block:: python

    class MyModel(Model):
        some_field = CharField()

        class Meta:
            database = database


It is possible to use multiple databases (provided that you don't try and mix
models from each):

.. code-block:: python

    >>> custom_db = SqliteDatabase('custom.db')

    >>> class CustomModel(Model):
    ...     whatev = CharField()
    ...
    ...     class Meta:
    ...         database = custom_db
    ...

    >>> custom_db.connect()
    >>> CustomModel.create_table()


**Best practice:** define a base model class that points at the database object
you wish to use, and then all your models will extend it:

.. code-block:: python

    custom_db = SqliteDatabase('custom.db')

    class CustomModel(Model):
        class Meta:
            database = custom_db

    class User(CustomModel):
        username = CharField()

    class Tweet(CustomModel):
        # etc, etc

.. note:: Remember to specify a database in a model class (or its parent class),
    otherwise peewee will fall back to a default sqlite database named "peewee.db".


.. _postgresql:

Using with Postgresql
^^^^^^^^^^^^^^^^^^^^^

Point models at an instance of :py:class:`PostgresqlDatabase`.

.. code-block:: python

    psql_db = PostgresqlDatabase('my_database', user='code')


    class PostgresqlModel(Model):
        """A base model that will use our Postgresql database"""
        class Meta:
            database = psql_db

    class User(PostgresqlModel):
        username = CharField()
        # etc, etc


.. _mysql:

Using with MySQL
^^^^^^^^^^^^^^^^

Point models at an instance of :py:class:`MySQLDatabase`.

.. code-block:: python

    mysql_db = MySQLDatabase('my_database', user='code')


    class MySQLModel(Model):
        """A base model that will use our MySQL database"""
        class Meta:
            database = mysql_db

    class User(MySQLModel):
        username = CharField()
        # etc, etc


    # when you're ready to start querying, remember to connect
    mysql_db.connect()


.. _sqlite:

Using with SQLite
^^^^^^^^^^^^^^^^^

Point models at an instance of :py:class:`SqliteDatabase`.  See also :ref:`Alternate Python SQLite Driver <apsw>`,
it's really neat.


.. code-block:: python

    sqlite_db = SqliteDatabase('sq.db')


    class SqliteModel(Model):
        """A base model that will use our Sqlite database"""
        class Meta:
            database = sqlite_db

    class User(SqliteModel):
        username = CharField()
        # etc, etc


    # when you're ready to start querying, remember to connect
    sqlite_db.connect()


Multi-threaded applications
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Some database engines may not allow a connection to be shared across threads, notably
sqlite.  If you would like peewee to maintain a single connection per-thread,
instantiate your database with ``threadlocals=True`` (*recommended*):

.. code-block:: python

    concurrent_db = SqliteDatabase('stats.db', threadlocals=True)

The above implementation stores connection state in a thread local and will only
use that connection for a given thread.  Pysqlite can share a connection across
threads, so if you would prefer to reuse a connection in multiple threads:

.. code-block:: python

    native_concurrent_db = SqliteDatabase('stats.db', check_same_thread=False)


.. _deferring_initialization:

Deferring initialization
^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes the database information is not known until run-time, when it might
be loaded from a configuration file/etc.  In this case, you can "defer" the initialization
of the database by passing in ``None`` as the database_name.

.. code-block:: python

    deferred_db = SqliteDatabase(None)

    class SomeModel(Model):
        class Meta:
            database = deferred_db

If you try to connect or issue any queries while your database is uninitialized
you will get an exception:

.. code-block:: python

    >>> deferred_db.connect()
    Exception: Error, database not properly initialized before opening connection

To initialize your database, you simply call the ``init`` method with the database_name
and any additional kwargs:

.. code-block:: python

    database_name = raw_input('What is the name of the db? ')
    deferred_db.init(database_name)


Creating, Reading, Updating and Deleting
----------------------------------------

Creating a new record
^^^^^^^^^^^^^^^^^^^^^

You can use the :py:meth:`Model.create` method on the model:

.. code-block:: pycon

    >>> User.create(username='Charlie')
    <__main__.User object at 0x2529350>

This will ``INSERT`` a new row into the database.  The primary key will automatically
be retrieved and stored on the model instance.

Alternatively, you can build up a model instance programmatically and then
save it:

.. code-block:: pycon

    >>> user = User()
    >>> user.username = 'Charlie'
    >>> user.save()
    >>> user.id
    1

See also :py:meth:`Model.save`, :py:meth:`Model.insert` and :py:class:`InsertQuery`


Updating existing records
^^^^^^^^^^^^^^^^^^^^^^^^^

Once a model instance has a primary key, any attempt to re-save it will result
in an ``UPDATE`` rather than another ``INSERT``:

.. code-block:: pycon

    >>> user.save()
    >>> user.id
    1
    >>> user.save()
    >>> user.id
    1

If you want to update multiple records, issue an ``UPDATE`` query.  The following
example will update all ``Entry`` objects, marking them as "published", if their
pub_date is less than today's date.

.. code-block:: pycon

    >>> today = datetime.today()
    >>> update_query = Tweet.update(is_published=True).where(Tweet.creation_date < today)
    >>> update_query.execute()
    4 # <--- number of rows updated

For more information, see the documentation on :py:class:`UpdateQuery`.


Deleting a record
^^^^^^^^^^^^^^^^^

To delete a single model instance, you can use the :py:meth:`Model.delete_instance`
shortcut:

.. code-block:: pycon

    >>> user = User.get(User.id == 1)
    >>> user.delete_instance()
    1 # <--- number of rows deleted

    >>> User.get(User.id == 1)
    UserDoesNotExist: instance matching query does not exist:
    SQL: SELECT t1."id", t1."username" FROM "user" AS t1 WHERE t1."id" = ?
    PARAMS: [1]

To delete an arbitrary group of records, you can issue a ``DELETE`` query.  The
following will delete all ``Tweet`` objects that are a year old.

.. code-block:: pycon

    >>> delete_query = Tweet.delete().where(Tweet.pub_date < one_year_ago)
    >>> delete_query.execute()
    7 # <--- number of rows deleted

For more information, see the documentation on :py:class:`DeleteQuery`.


Selecting a single record
^^^^^^^^^^^^^^^^^^^^^^^^^

You can use the :py:meth:`Model.get` method to retrieve a single instance matching
the given query.

This method is a shortcut that calls :py:meth:`Model.select` with the given query,
but limits the result set to 1.  Additionally, if no model matches the given query,
a ``DoesNotExist`` exception will be raised.

.. code-block:: pycon

    >>> User.get(User.id == 1)
    <__main__.Blog object at 0x25294d0>

    >>> User.get(User.id == 1).username
    u'Charlie'

    >>> User.get(User.username == 'Charlie')
    <__main__.Blog object at 0x2529410>

    >>> User.get(User.username == 'nobody')
    UserDoesNotExist: instance matching query does not exist:
    SQL: SELECT t1."id", t1."username" FROM "user" AS t1 WHERE t1."username" = ?
    PARAMS: ['nobody']

For more information see notes on :py:class:`SelectQuery` and :ref:`querying` in general.


Selecting multiple records
^^^^^^^^^^^^^^^^^^^^^^^^^^

To simply get all instances in a table, call the :py:meth:`Model.select` method:

.. code-block:: pycon

    >>> for user in User.select():
    ...     print user.username
    ...
    Charlie
    Peewee Herman

When you iterate over a :py:class:`SelectQuery`, it will automatically execute
it and start returning results from the database cursor.  Subsequent iterations
of the same query will not hit the database as the results are cached.

Another useful note is that you can retrieve instances related by :py:class:`ForeignKeyField`
by iterating.  To get all the related instances for an object, you can query the related name.
Looking at the example models, we have Users and Tweets.  Tweet has a foreign key to User,
meaning that any given user may have 0..n tweets.  A user's related tweets are exposed
using a :py:class:`SelectQuery`, and can be iterated the same as any other SelectQuery:

.. code-block:: pycon

    >>> for tweet in user.tweets:
    ...     print tweet.message
    ...
    hello world
    this is fun
    look at this picture of my food

The ``tweets`` attribute is just another select query and any methods available
to :py:class:`SelectQuery` are available:

.. code-block:: pycon

    >>> for tweet in user.tweets.order_by(Tweet.created_date.desc()):
    ...     print tweet.message
    ...
    look at this picture of my food
    this is fun
    hello world


Filtering records
^^^^^^^^^^^^^^^^^

You can filter for particular records using normal python operators.

.. code-block:: pycon

    >>> user = User.get(User.username == 'Charlie')
    >>> for tweet in Tweet.select().where(Tweet.user == user, Tweet.is_published == True):
    ...     print '%s: %s (%s)' % (tweet.user.username, tweet.message)
    ...
    Charlie: hello world
    Charlie: this is fun

    >>> for tweet in Tweet.select().where(Tweet.created_date < datetime.datetime(2011, 1, 1)):
    ...     print tweet.message, tweet.created_date
    ...
    Really old tweet 2010-01-01 00:00:00

You can also filter across joins:

.. code-block:: pycon

    >>> for tweet in Tweet.select().join(User).where(User.username == 'Charlie'):
    ...     print tweet.message
    hello world
    this is fun
    look at this picture of my food

If you want to express a complex query, use parentheses and python's "or" and "and"
operators:

.. code-block:: pycon

    >>> Tweet.select().join(User).where(
    ...     (User.username == 'Charlie') |
    ...     (User.username == 'Peewee Herman')
    ... )

Check out :ref:`the table of query operations <column-lookups>` to see what types of
queries are possible.

.. note::

    A lot of fun things can go in the where clause of a query, such as:

    * a field expression, e.g. ``User.username == 'Charlie'``
    * a function expression, e.g. ``fn.Lower(fn.Substr(User.username, 1, 1)) == 'a'``
    * a comparison of one column to another, e.g. ``Employee.salary < (Employee.tenure * 1000) + 40000``

    You can also nest queries, for example tweets by users whose username starts with "a":

    .. code-block:: python

        # get users whose username starts with "a"
        a_users = User.select().where(fn.Lower(fn.Substr(User.username, 1, 1)) == 'a')

        # the "<<" operator signifies an "IN" query
        a_user_tweets = Tweet.select().where(Tweet.user << a_users)

Check :ref:`the docs <query_compare>` for some more example queries.


Sorting records
^^^^^^^^^^^^^^^

.. code-block:: pycon

    >>> for t in Tweet.select().order_by(Tweet.created_date):
    ...     print t.pub_date
    ...
    2010-01-01 00:00:00
    2011-06-07 14:08:48
    2011-06-07 14:12:57

    >>> for t in Tweet.select().order_by(Tweet.created_date.desc()):
    ...     print t.pub_date
    ...
    2011-06-07 14:12:57
    2011-06-07 14:08:48
    2010-01-01 00:00:00

You can also order across joins.  Assuming you want
to order tweets by the username of the author, then by created_date:

.. code-block:: pycon

    >>> qry = Tweet.select().join(User).order_by(User.username, Tweet.created_date.desc())

.. code-block:: sql

    -- generates --
    SELECT t1."id", t1."user_id", t1."message", t1."is_published", t1."created_date"
    FROM "tweet" AS t1 INNER JOIN "user" AS t2 ON t1."user_id" = t2."id"
    ORDER BY t2."username", t1."created_date" DESC


Paginating records
^^^^^^^^^^^^^^^^^^

The paginate method makes it easy to grab a "page" or records -- it takes two
parameters, `page_number`, and `items_per_page`:

.. code-block:: pycon

    >>> for tweet in Tweet.select().order_by(Tweet.id).paginate(2, 10):
    ...     print tweet.message
    ...
    tweet 10
    tweet 11
    tweet 12
    tweet 13
    tweet 14
    tweet 15
    tweet 16
    tweet 17
    tweet 18
    tweet 19


Counting records
^^^^^^^^^^^^^^^^

You can count the number of rows in any select query:

.. code-block:: python

    >>> Tweet.select().count()
    100
    >>> Tweet.select().where(Tweet.id > 50).count()
    50


Iterating over lots of rows
^^^^^^^^^^^^^^^^^^^^^^^^^^^

To limit the amount of memory used by peewee when iterating over a lot of rows (i.e.
you may be dumping data to csv), use the ``iterator()`` method on the :py:class:`QueryResultWrapper`.
This method allows you to iterate without caching each model returned, using much less
memory when iterating over large result sets:

.. code-block:: python

    # let's assume we've got 1M stat objects to dump to csv
    stats_qr = Stat.select().execute()

    # our imaginary serializer class
    serializer = CSVSerializer()

    # loop over all the stats and serialize
    for stat in stats_qr.iterator():
        serializer.serialize_object(stat)


For simple queries you can see further speed improvements by using the :py:meth:`SelectQuery.naive`
query method.  See the documentation for details on this optimization.

.. code-block:: python

    stats_query = Stat.select().naive() # note we are calling "naive()"
    stats_qr = stats_query.execute()

    for stat in stats_qr.iterator():
        serializer.serialize_object(stat)


Performing atomic updates
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    >>> Stat.update(counter=Stat.counter + 1).where(Stat.url == request.url)


Aggregating records
^^^^^^^^^^^^^^^^^^^

Suppose you have some users and want to get a list of them along with the count
of tweets in each.  First I will show you the shortcut:

.. code-block:: python

    query = User.select().annotate(Tweet)

This is equivalent to the following:

.. code-block:: python

    query = User.select(
        User, fn.Count(Tweet.id).alias('count')
    ).join(Tweet).group_by(User)


The resulting query will return User objects with all their normal attributes
plus an additional attribute 'count' which will contain the number of tweets.
By default it uses an inner join if the foreign key is not nullable, which means
blogs without entries won't appear in the list.  To remedy this, manually specify
the type of join to include users with 0 tweets:

.. code-block:: python

    query = User.select().join(Tweet, JOIN_LEFT_OUTER).annotate(Tweet)

You can also specify a custom aggregator:

.. code-block:: python

    query = User.select().annotate(Tweet, fn.Max(Tweet.created_date).alias('latest'))

Let's assume you have a tagging application and want to find tags that have a
certain number of related objects.  For this example we'll use some different
models in a Many-To-Many configuration:

.. code-block:: python

    class Photo(Model):
        image = CharField()

    class Tag(Model):
        name = CharField()

    class PhotoTag(Model):
        photo = ForeignKeyField(Photo)
        tag = ForeignKeyField(Tag)

Now say we want to find tags that have at least 5 photos associated with them:

.. code-block:: python

    >>> Tag.select().join(PhotoTag).join(Photo).group_by(Tag).having(fn.Count(Photo.id) > 5)

Yields the following:

.. code-block:: sql

    SELECT t1."id", t1."name"
    FROM "tag" AS t1
    INNER JOIN "phototag" AS t2 ON t1."id" = t2."tag_id"
    INNER JOIN "photo" AS t3 ON t2."photo_id" = t3."id"
    GROUP BY t1."id", t1."name"
    HAVING Count(t3."id") > 5

Suppose we want to grab the associated count and store it on the tag:

.. code-block:: python

    >>> Tag.select(
    ...     Tag, fn.Count(Photo.id).alias('count')
    ... ).join(PhotoTag).join(Photo).group_by(Tag).having(fn.Count(Photo.id) > 5)


SQL Functions, Subqueries and "Raw expressions"
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Suppose you need to want to get a list of all users whose username begins with "a".
There are a couple ways to do this, but one method might be to use some SQL functions
like ``LOWER`` and ``SUBSTR``.  To use arbitrary SQL functions, use the special :py:func:`fn`
function to construct queries:

.. code-block:: python

    # select the users' id, username and the first letter of their username, lower-cased
    query = User.select(User, fn.Lower(fn.Substr(User.username, 1, 1)).alias('first_letter'))

    # alternatively we could select only users whose username begins with 'a'
    a_users = User.select().where(fn.Lower(fn.Substr(User.username, 1, 1)) == 'a')

    >>> for user in a_users:
    ...    print user.username

There are times when you may want to simply pass in some arbitrary sql.  You can do
this using the special :py:class:`R` class.  One use-case is when referencing an
alias:

.. code-block:: python

    # we'll query the user table and annotate it with a count of tweets for
    # the given user
    query = User.select(User, fn.Count(Tweet.id).alias('ct')).join(Tweet).group_by(User)

    # now we will order by the count, which was aliased to "ct"
    query = query.order_by(R('ct'))


.. _working_with_transactions:

Working with transactions
-------------------------

Context manager
^^^^^^^^^^^^^^^

You can execute queries within a transaction using the ``transaction`` context manager,
which will issue a commit if all goes well, or a rollback if an exception is raised:

.. code-block:: python

    db = SqliteDatabase(':memory:')

    with db.transaction():
        user.delete_instance(recursive=True) # delete user and associated tweets


Decorator
^^^^^^^^^

Similar to the context manager, you can decorate functions with the ``commit_on_success``
decorator:

.. code-block:: python

    db = SqliteDatabase(':memory:')

    @db.commit_on_success
    def delete_user(user):
        user.delete_instance(recursive=True)


Changing autocommit behavior
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

By default, databases are initialized with ``autocommit=True``, you can turn this
on and off at runtime if you like.  The behavior below is roughly the same as the
context manager and decorator:

.. code-block:: python

    db.set_autocommit(False)
    try:
        user.delete_instance(recursive=True)
    except:
        db.rollback()
        raise
    else:
        db.commit()
    finally:
        db.set_autocommit(True)


If you would like to manually control *every* transaction, simply turn autocommit
off when instantiating your database:

.. code-block:: python

    db = SqliteDatabase(':memory:', autocommit=False)

    User.create(username='somebody')
    db.commit()


.. _non_integer_primary_keys:

Non-integer Primary Keys and other Tricks
-----------------------------------------

Non-integer primary keys
^^^^^^^^^^^^^^^^^^^^^^^^

If you would like use a non-integer primary key (which I generally don't recommend),
you can override the default ``column_class`` of the :py:class:`PrimaryKeyField`:

.. code-block:: python

    from peewee import *

    class UUIDModel(Model):
        id = CharField(primary_key=True)


    inst = UUIDModel(id=str(uuid.uuid4()))
    inst.save() # <-- WRONG!!  this will try to do an update

    inst.save(force_insert=True) # <-- CORRECT

    # to update the instance after it has been saved once
    inst.save()

.. note::
    Any foreign keys to a model with a non-integer primary key will have the
    ``ForeignKeyField`` use the same underlying storage type as the primary key
    they are related to.

See full documentation on :ref:`non-integer primary keys <non_int_pks>`.


Bulk loading data or manually specifying primary keys
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes you do not want the database to automatically generate a primary key,
for instance when bulk loading relational data.  To handle this on a "one-off"
basis, you can simply tell peewee to turn off ``auto_increment`` during the
import:

.. code-block:: python

    data = load_user_csv() # load up a bunch of data

    User._meta.auto_increment = False # turn off auto incrementing IDs
    with db.transaction():
        for row in data:
            u = User(id=row[0], username=row[1])
            u.save(force_insert=True) # <-- force peewee to insert row

    User._meta.auto_increment = True

If you *always* want to have control over the primary key, simply do not use
the ``PrimaryKeyField`` type:

.. code-block:: python

    class User(BaseModel):
        id = IntegerField(primary_key=True)
        username = CharField()

    >>> u = User.create(id=999, username='somebody')
    >>> u.id
    999
    >>> User.get(User.username == 'somebody').id
    999


Introspecting databases
-----------------------

If you'd like to generate some models for an existing database, you can try
out the database introspection tool "pwiz" that comes with peewee.

Usage:

.. code-block:: console

    python pwiz.py my_postgresql_database

It works with postgresql, mysql and sqlite:

.. code-block:: console

    python pwiz.py test.db --engine=sqlite

pwiz will generate code for:

* database connection object
* a base model class to use this connection
* models that were introspected from the database tables

The generated code is written to stdout.


Schema migrations
-----------------

Currently peewee does not have support for automatic schema migrations.
