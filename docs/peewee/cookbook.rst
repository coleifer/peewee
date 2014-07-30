.. _cookbook:

Peewee Cookbook
===============

Below are outlined some of the ways to perform typical database-related tasks
with peewee.

Examples will use the following models:

.. include:: includes/user_tweet.rst

Database and Connection Recipes
-------------------------------

This section describes ways to configure and connect to various databases.

.. include:: includes/databases.rst

Generating Models from Existing Databases
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you'd like to generate peewee model definitions for an existing database, you can try out the database introspection tool :ref:`pwiz` that comes with peewee. *pwiz* is capable of introspecting Postgresql, MySQL and SQLite databases.

Introspecting a Postgresql database:

.. code-block:: console

    pwiz.py --engine=postgresql my_postgresql_database

Introspecting a SQLite database:

.. code-block:: console

    pwiz.py --engine=sqlite test.db

pwiz will generate:

* Database connection object
* A *BaseModel* class to use with the database
* *Model* classes for each table in the database.

The generated code is written to stdout, and can easily be redirected to a file:

.. code-block:: console

    pwiz.py -e postgresql my_postgresql_db > models.py

.. note::
    pwiz generally works quite well with even large and complex database
    schemas, but in some cases it will not be able to introspect a column.
    You may need to go through the generated code to add indexes, fix unrecognized
    column types, and resolve any circular references that were found.

Logging queries
^^^^^^^^^^^^^^^

All queries are logged to the *peewee* namespace using the standard library ``logging`` module. Queries are logged using the *DEBUG* level.  If you're interested in doing something with the queries, you can simply register a handler.

.. code-block:: python

    # Print all queries to stderr.
    import logging
    logger = logging.getLogger('peewee')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())


Basic CRUD operations
---------------------

This section will cover the basic CRUD operations commonly performed on a relational database:

* :py:meth`Model.create`, for executing *INSERT* queries.
* :py:meth:`Model.save` and :py:meth:`Model.update`, for executing *UPDATE* queries.
* :py:meth:`Model.delete_instance` and :py:meth:`Model.delete`, for executing *DELETE* queries.
* :py:meth:`Model.select`, for executing *SELECT* queries.

Creating a new record
^^^^^^^^^^^^^^^^^^^^^

You can use :py:meth:`Model.create` to create a new model instance. This method accepts keyword arguments, where the keys correspond to the names of the model's fields. A new instance is returned and a row is added to the table.

.. code-block:: pycon

    >>> User.create(username='Charlie')
    <__main__.User object at 0x2529350>

This will *INSERT* a new row into the database. The primary key will automatically be retrieved and stored on the model instance.

Alternatively, you can build up a model instance programmatically and then call :py:meth:`~Model.save`:

.. code-block:: pycon

    >>> user = User(username='Charlie')
    >>> user.save()  # save() returns the number of rows modified.
    1
    >>> user.id
    1
    >>> peewee = User()
    >>> peewee.username = 'Peewee'
    >>> peewee.save()
    1
    >>> peewee.id
    2

When a model has a foreign key, you can directly assign a model instance to the foreign key field when creating a new record.

.. code-block:: pycon

    >>> tweet = Tweet.create(user=peewee, message='Hello!')

You can also use the value of the related object's primary key:

.. code-block:: pycon

    >>> tweet = Tweet.create(user=2, message='Hello again!')

If you simply wish to insert data and do not need to create a model instance, you can use :py:meth:`Model.insert`:

.. code-block:: pycon

    >>> User.insert(username='Huey').execute()
    3

After executing the insert query, the primary key of the new row is returned.

.. note::
    There are several ways you can speed up bulk insert operations. Check out
    the :ref:`bulk_insert` recipe section for more information.

Updating existing records
^^^^^^^^^^^^^^^^^^^^^^^^^

Once a model instance has a primary key, any subsequent call to :py:meth:`~Model.save` will result in an *UPDATE* rather than another *INSERT*. The model's primary key will not change:

.. code-block:: pycon

    >>> user.save()  # save() returns the number of rows modified.
    1
    >>> user.id
    1
    >>> user.save()
    >>> user.id
    1
    >>> peewee.save()
    1
    >>> peewee.id
    2

If you want to update multiple records, issue an *UPDATE* query. The following example will update all ``Tweet`` objects, marking them as *published*, if they were created before today. :py:meth:`Model.update` accepts keyword arguments where the keys correspond to the model's field names:

.. code-block:: pycon

    >>> today = datetime.today()
    >>> query = Tweet.update(is_published=True).where(Tweet.creation_date < today)
    >>> query.execute()
    4 # <--- number of rows updated

For more information, see the documentation on :py:meth:`Model.update` and :py:class:`UpdateQuery`.

.. note::
    If you would like more information on performing atomic updates (such as
    incrementing the value of a column), check out the :ref:`atomic update <atomic_updates>`
    recipes.

Deleting a record
^^^^^^^^^^^^^^^^^

To delete a single model instance, you can use the :py:meth:`Model.delete_instance` shortcut. :py:meth:`~Model.delete_instance` will delete the given model instance and can optionally delete any dependent objects recursively (by specifying `recursive=True`).

.. code-block:: pycon

    >>> user = User.get(User.id == 1)
    >>> user.delete_instance()  # Returns the number of rows deleted.
    1

    >>> User.get(User.id == 1)
    UserDoesNotExist: instance matching query does not exist:
    SQL: SELECT t1."id", t1."username" FROM "user" AS t1 WHERE t1."id" = ?
    PARAMS: [1]

To delete an arbitrary set of rows, you can issue a *DELETE* query. The following will delete all ``Tweet`` objects that are over one year old:

.. code-block:: pycon

    >>> query = Tweet.delete().where(Tweet.creation_date < one_year_ago)
    >>> query.execute()  # Returns the number of rows deleted.
    7

For more information, see the documentation on:

* :py:meth:`Model.delete_instance`
* :py:meth:`Model.delete`
* :py:class:`DeleteQuery`

Selecting a single record
^^^^^^^^^^^^^^^^^^^^^^^^^

You can use the :py:meth:`Model.get` method to retrieve a single instance matching the given query.

This method is a shortcut that calls :py:meth:`Model.select` with the given query, but limits the result set to a single row. Additionally, if no model matches the given query, a ``DoesNotExist`` exception will be raised.

.. code-block:: pycon

    >>> User.get(User.id == 1)
    <__main__.User object at 0x25294d0>

    >>> User.get(User.id == 1).username
    u'Charlie'

    >>> User.get(User.username == 'Charlie')
    <__main__.User object at 0x2529410>

    >>> User.get(User.username == 'nobody')
    UserDoesNotExist: instance matching query does not exist:
    SQL: SELECT t1."id", t1."username" FROM "user" AS t1 WHERE t1."username" = ?
    PARAMS: ['nobody']

For more advanced operations, you can use :py:meth:`SelectQuery.get`. The following query retrieves the latest tweet from the user named *charlie*:

.. code-block:: pycon

    >>> (Tweet
    ...  .select()
    ...  .join(User)
    ...  .where(User.username == 'charlie')
    ...  .order_by(Tweet.created_date.desc())
    ...  .get())
    <__main__.Tweet object at 0x2623410>

For more information, see the documentation on:

* :ref:`querying`
* :py:meth:`Model.get`
* :py:meth:`Model.select`
* :py:meth:`SelectQuery.get`

Selecting multiple records
^^^^^^^^^^^^^^^^^^^^^^^^^^

As we saw in the previous section, we can use :py:meth:`Model.select` to retrieve rows from the table. When you construct a *SELECT* query, the database will return any rows that correspond to your query. Peewee allows you to iterate over these rows, as well as use indexing and slicing operations.

In the following example, we will simply call :py:meth:`~Model.select` and iterate over the return value, which is an instance of :py:class:`SelectQuery`. This will return all the rows in the *User* table:

.. code-block:: pycon

    >>> for user in User.select():
    ...     print user.username
    ...
    Charlie
    Huey
    Peewee

.. note::
    Subsequent iterations of the same query will not hit the database as
    the results are cached. To disable this behavior (to reduce memory), call
    :py:meth:`SelectQuery.iterator` when iterating.

When iterating over a model that contains a foreign key, be careful with the way you access values on related models. Accidentally resolving a foreign key or iterating over a back-reference can cause :ref:`N+1 query behavior <nplusone>`.

When you create a foreign key, such as ``Tweet.user``, you can use the
*related_name* to create a back-reference (``User.tweets``). Back-references
are exposed as :py:class:`SelectQuery` instances:

.. code-block:: pycon

    >>> tweet = Tweet.get()
    >>> tweet.user  # Accessing a foreign key returns the related model.
    <tw.User at 0x7f3ceb017f50>

    >>> user = User.get()
    >>> user.tweets  # Accessing a back-reference returns a query.
    <SelectQuery> SELECT t1."id", t1."user_id", t1."message", t1."created_date", t1."is_published" FROM "tweet" AS t1 WHERE (t1."user_id" = ?) [1]

You can iterate over the ``user.tweets`` back-reference just like any other :py:class:`SelectQuery`:

.. code-block:: pycon

    >>> for tweet in user.tweets:
    ...     print tweet.message
    ...
    hello world
    this is fun
    look at this picture of my food

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

.. _atomic_updates:

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


.. _nplusone:

Avoiding N+1 queries
--------------------

Peewee provides several APIs for mitigating the dreaded N+1 query behavior. Recollecting
the models at the top of this document (``User`` and ``Tweet``), this section will try to outline
some common N+1 scenarios, and how you can avoid them with peewee.

List recent tweets
^^^^^^^^^^^^^^^^^^

The twitter timeline displays a list of tweets from multiple users. In addition
to the tweet's content, the author of the tweet is also displayed. The N+1 scenario
here would be:

1. Fetch the 10 most recent tweets.
2. For each tweet, select the author (10 queries).

Simply by selecting both tables and using a ``JOIN``, peewee makes it possible to
accomplish this in a single query:

.. code-block:: python

    query = (Tweet
             .select(Tweet, User)  # Note that we are selecting both models.
             .join(User)
             .order_by(Tweet.id.desc())  # Get the most recent tweets.
             .limit(10))

    for tweet in query:
        print tweet.user.username, '-', tweet.message

Without the ``JOIN``, accessing ``tweet.user.username`` would trigger a query to
resolve the foreign key (``tweet.user_id``) and retrieve the associated user. But
since we have selected and joined on ``User``, peewee will automatically resolve the
foreign-key for us.

List users and all their tweets
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let's say you want to build a page that shows several users and all of their tweets.
The N+1 scenario would be:

1. Fetch some users.
2. For each user, fetch their tweets.

This situation is similar to the previous example, but there is one important
difference: when we selected tweets, they only have a single associated user, so
we could directly assign the foreign key. The reverse is not true, however, as one
user may have any number of tweets (or none at all).

Peewee provides two approaches to avoiding O(n) queries in this situation. We can
either:

* Fetch both users and tweets in a single query. User data will be duplicated, so
  we will manually de-dupe it and aggregate the tweets as we go.
* Fetch users first, then fetch all the tweets associated with those users. Once
  we have the big list of tweets, we will assign them out, matching them with the
  appropriate user.

Each solution has its place and, depending on the size and shape of the data you
are querying, one may be more performant than the other.

Let's look at the first approach, since it is more general and can work with
arbitrarily complex queries. We will use a special flag, :py:meth:`SelectQuery.aggregate_rows`,
when creating our query. This method tells peewee to de-duplicate any rows that,
due to the structure of the JOINs, may be duplicated.

.. code-block:: python

    query = (User
             .select(User, Tweet)  # As in the previous example, we select both tables.
             .join(Tweet, JOIN_LEFT_OUTER)
             .order_by(User.username)  # We need to specify an ordering here.
             .aggregate_rows())
    for user in query:
        print user.username
        for tweet in user.tweets:
            print '  ', tweet.message

Ordinarily, ``user.tweets`` would be a :py:class:`SelectQuery` and iterating over it
would trigger an additional query. By using :py:meth:`~SelectQuery.aggregate_rows`,
though, ``user.tweets`` is a Python ``list`` and no additional query occurs.

.. note::
    We used a ``LEFT OUTER`` join to ensure that users with zero tweets would
    also be included in the result set.

The second approach requires the use of a special API, :py:func:`prefetch`. Pre-fetch,
as its name indicates, will eagerly load the appropriate tweets for the given users.
This means instead of O(n) queries for ``n`` rows, we will do O(k) queries for ``k``
tables.

Here is an example of how we might fetch several users and any tweets they created
within the past week.

.. code-block:: python

    week_ago = datetime.date.today() - datetime.timedelta(days=7)
    users = User.select()
    tweets = (Tweet
              .select()
              .where(
                  (Tweet.is_published == True) &
                  (Tweet.created_date >= week_ago)))

    # This will perform two queries.
    users_with_tweets = prefetch(users, tweets)

    for user in users_with_tweets:
        print user.username
        for tweet in user.tweets_prefetch:
            print '  ', tweet.message

.. note::
    Note that neither the ``User`` query, nor the ``Tweet`` query contained a
    JOIN clause. When using :py:func:`prefetch` you do not need to specify the
    join.

As with :py:meth:`~SelectQuery.aggregate_rows`, you can use :py:func:`prefetch`
to query an arbitrary number of tables. Check the API documentation for more
examples.

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

.. _bulk_inserts:

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
            Model.insert_many(data_source[idx:idx+1000]).execute()


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

Schema migrations
-----------------

Currently peewee does not have support for *automatic* schema migrations, but
you can use the :ref:`migrate` module to create simple migration scripts. The
schema migrations module works with SQLite, MySQL and Postgres, and will even
allow you to do things like drop or rename columns in SQLite!

Here is an example of how you might write a migration script:

.. code-block:: python

    from playhouse.migrate import *

    my_db = SqliteDatabase('my_database.db')
    migrator = SqliteMigrator(my_db)

    title_field = CharField(default='')
    status_field = IntegerField(null=True)

    with my_db.transaction():
        migrate(
            migrator.add_column('some_table', 'title', title_field),
            migrator.add_column('some_table', 'status', status_field),
            migrator.drop_column('some_table', 'old_column'),
        )

Check the :ref:`migrate` documentation for more details.
