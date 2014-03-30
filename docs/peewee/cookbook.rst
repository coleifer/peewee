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
    # if your Postgres template doesn't use UTF8, you can set the connection encoding like so:
    psql_db.get_conn().set_client_encoding('UTF8')


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

With the above peewee stores connection state in a thread local; each thread gets its
own separate connection.

Alternatively, Python sqlite3 module can share a connection across different threads,
but you have to disable runtime checks to reuse the single connection:

.. code-block:: python

    concurrent_db = SqliteDatabase('stats.db', check_same_thread=False)


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

.. _dynamic_db:

Dynamically defining a database
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For even more control over how your database is defined/initialized, you can
use the :py:class:`Proxy` helper, which is included as part of peewee.  You
can use the proxy as a "placeholder", and then at run-time swap it out for a
different object.  In the example below, we will swap out the database depending
on how the app is configured:

.. code-block:: python

    database_proxy = Proxy()  # Create a proxy for our db.

    class BaseModel(Model):
        class Meta:
            database = database_proxy  # Use proxy for our DB.

    class User(BaseModel):
        username = CharField()

    # Based on configuration, use a different database.
    if app.config['DEBUG']:
        database = SqliteDatabase('local.db')
    elif app.config['TESTING']:
        database = SqliteDatabase(':memory:')
    else:
        database = PostgresqlDatabase('mega_production_db')

    # Configure our proxy to use the db we specified in config.
    database_proxy.initialize(database)


Logging queries
^^^^^^^^^^^^^^^

All queries are logged to the ``peewee`` namespace using the standard library
logging module. Queries are logged using the ``DEBUG`` level.  If you're
interested in doing something with the queries, you can simply register a
handler.

.. code-block:: python

    # Print all queries to stderr.
    import logging
    logger = logging.getLogger('peewee')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())


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

If you want to express a complex query, use parentheses and python's bitwise "or" and "and"
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


Getting random records
^^^^^^^^^^^^^^^^^^^^^^

Occasionally you may want to pull a random record from the database.  You can accomplish
this by ordering by the ``random`` or ``rand`` function:

Postgresql and Sqlite:

.. code-block:: python

    LotteryNumber.select().order_by(fn.Random()).limit(5) # pick 5 lucky winners

MySQL:

.. code-block:: python

    LotterNumber.select().order_by(fn.Rand()).limit(5) # pick 5 lucky winners


Paginating records
^^^^^^^^^^^^^^^^^^

The paginate method makes it easy to grab a "page" or records -- it takes two
parameters, `page_number`, and `items_per_page`. `page_number` is 1-based, so page 1 is the first page:

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

    >>> Stat.update(counter=Stat.counter + 1).where(Stat.url == request.url).execute()


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


Retrieving Scalar Values
^^^^^^^^^^^^^^^^^^^^^^^^

You can retrieve scalar values by calling :py:meth:`Query.scalar`.  For instance:

.. code-block:: python

    >>> PageView.select(fn.Count(fn.Distinct(PageView.url))).scalar()
    100 # <-- there are 100 distinct URLs in the PageView table

You can retrieve multiple scalar values by passing ``as_tuple=True``:

.. code-block:: python

    >>> Employee.select(
    ...     fn.Min(Employee.salary), fn.Max(Employee.salary)
    ... ).scalar(as_tuple=True)
    (30000, 50000)


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
this using the special :py:class:`SQL` class.  One use-case is when referencing an
alias:

.. code-block:: python

    # we'll query the user table and annotate it with a count of tweets for
    # the given user
    query = User.select(User, fn.Count(Tweet.id).alias('ct')).join(Tweet).group_by(User)

    # now we will order by the count, which was aliased to "ct"
    query = query.order_by(SQL('ct'))

To execute custom SQL, please refer to :ref:`using_sql`.


Retrieving raw tuples / dictionaries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes you do not need the overhead of creating model instances and simply want
to iterate over the row tuples.  To do this, call :py:meth:`SelectQuery.tuples` or
:py:meth:`RawQuery.tuples`:

.. code-block:: python

    stats = Stat.select(Stat.url, fn.Count(Stat.url)).group_by(Stat.url).tuples()

    # iterate over a list of 2-tuples containing the url and count
    for stat_url, stat_count in stats:
        print stat_url, stat_count

Similarly, you can return the rows from the cursor as dictionaries using :py:meth:`SelectQuery.dicts`
or :py:meth:`RawQuery.dicts`:

.. code-block:: python

    stats = Stat.select(Stat.url, fn.Count(Stat.url).alias('ct')).group_by(Stat.url).dicts()

    # iterate over a list of 2-tuples containing the url and count
    for stat in stats:
        print stat['url'], stat['ct']

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
        try:
            db.commit()
        except:
            db.rollback()
            raise
    finally:
        db.set_autocommit(True)


If you would like to manually control *every* transaction, simply turn autocommit
off when instantiating your database:

.. code-block:: python

    db = SqliteDatabase(':memory:', autocommit=False)

    User.create(username='somebody')
    db.commit()


.. _non_integer_primary_keys:

Non-integer Primary Keys, Composite Keys and other Tricks
---------------------------------------------------------

Non-integer primary keys
^^^^^^^^^^^^^^^^^^^^^^^^

If you would like use a non-integer primary key (which I generally don't recommend),
you can specify ``primary_key=True``.

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


Composite primary keys
^^^^^^^^^^^^^^^^^^^^^^

Peewee has very basic support for composite keys.  In order to use a composite
key, you must set the ``primary_key`` attribute of the model options to a
:py:class:`CompositeKey` instance:

.. code-block:: python

    class BlogToTag(Model):
        """A simple "through" table for many-to-many relationship."""
        blog = ForeignKeyField(Blog)
        tag = ForeignKeyField(Tag)

        class Meta:
            primary_key = CompositeKey('blog', 'tag')


Bulk inserts
^^^^^^^^^^^^

There are a couple of ways you can load lots of data quickly. Let's look at the
various options:

The naive approach is to simply call :py:meth:`Model.create`:

.. code-block:: python

    for data_dict in data_source:
        Model.create(**data_dict)

The above approach is slow for a couple of reasons:

1. If you are using autocommit (the default), then each call to ``create``
   happens in its own transaction. That is going to be slow!
2. There is a decent amount of Python logic getting in your way, and each
   :py:class:`InsertQuery` must be generated and parsed into SQL.
3. That's a lot of data (in terms of raw bytes) you are sending to your database
   to parse.
4. We are retrieving the "last insert ID", which causes an additional query to
   be executed in some cases.

You can get a *very significant* speedup by simply wrapping this in a transaction.

.. code-block:: python

    # This is much faster.
    with db.transaction():
        for data_dict in data_source:
            Model.create(**data_dict)

The above code still suffers from points 2, 3 and 4. We can get another big
boost by calling :py:meth:`Model.insert_many`. This method accepts a list of
dictionaries to insert.

.. code-block:: python

    # Fastest.
    with db.transaction():
        Model.insert_many(data_source).execute()

Depending on the number of rows in your data source, you may need to break it
up into chunks:

.. code-block:: python

    # Insert rows 1000 at a time.
    with db.transaction():
        for idx in range(0, len(data_source), 1000):
            Model.insert_many(data_source[i:i+1000]).execute()


Manually specifying primary keys
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

Self-referential foreign keys
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When creating a heirarchical structure it is necessary to create a self-referential
foreign key which links a child object to its parent.  Because the model class is not
defined at the time you instantiate the self-referential foreign key, use the special
string ``'self'`` to indicate a self-referential foreign key:

.. code-block:: python

    class Category(Model):
        name = CharField()
        parent = ForeignKeyField('self', null=True, related_name='children')

As you can see, the foreign key points "upward" to the parent object and the
back-reference is named "children".

.. note:: Self-referential foreign-keys should always be ``null=True``.


Circular foreign key dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes it happens that you will create a circular dependency between two
tables.

.. note::
  My personal opinion is that circular foreign keys are a code smell and should
  be refactored (by adding an intermediary table, for instance).

Adding circular foreign keys with peewee is a bit tricky because at the time you
are defining either foreign key, the model it points to will not have been defined
yet, causing a ``NameError``.

By using :py:class:`Proxy` we can get around the problem, though:

.. code-block:: python

    # Create a proxy object to stand in for our as-yet-undefined Tweet model.
    TweetProxy = Proxy()

    class User(Model):
        username = CharField()
        # Tweet has not been defined yet so use the proxy.
        favorite_tweet = ForeignKeyField(TweetProxy, null=True)

    class Tweet(Model):
        message = TextField()
        user = ForeignKeyField(User, related_name='tweets')

    # Now that Tweet is defined, we can initialize the proxy object.
    TweetProxy.initialize(Tweet)

After initializing the proxy the foreign key fields are now correctly set up.
There is one more quirk to watch out for, though.  When you call :py:class:`~Model.create_table`
we will again encounter the same issue.  For this reason peewee will not automatically
create a foreign key constraint for any "deferred" foreign keys.

Here is how to create the tables:

.. code-block:: python

    # Foreign key constraint from User -> Tweet will NOT be created because the
    # Tweet table does not exist yet. `favorite_tweet` will just be a regular
    # integer field:
    User.create_table()

    # Foreign key constraint from Tweet -> User will be created normally.
    Tweet.create_table()

    # Now that both tables exist, we can create the foreign key from User -> Tweet:
    db.create_foreign_key(User, User.favorite_tweet)


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

.. note::
    pwiz is **not** a fully-automatic model generator. You may need to go
    back through, add indexes, fix unknown column types, and resolve any
    circular references.


Schema migrations
-----------------

Currently peewee does not have support for automatic schema migrations.
