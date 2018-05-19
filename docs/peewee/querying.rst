.. _querying:

Querying
========

This section will cover the basic CRUD operations commonly performed on a
relational database:

* :py:meth:`Model.create`, for executing *INSERT* queries.
* :py:meth:`Model.save` and :py:meth:`Model.update`, for executing *UPDATE*
  queries.
* :py:meth:`Model.delete_instance` and :py:meth:`Model.delete`, for executing
  *DELETE* queries.
* :py:meth:`Model.select`, for executing *SELECT* queries.

.. note::
    There is also a large collection of example queries taken from the
    `Postgresql Exercises <https://pgexercises.com/>`_ website. Examples are
    listed on the :ref:`query examples <query_examples>` document.

Creating a new record
---------------------

You can use :py:meth:`Model.create` to create a new model instance. This method
accepts keyword arguments, where the keys correspond to the names of the
model's fields. A new instance is returned and a row is added to the table.

.. code-block:: pycon

    >>> User.create(username='Charlie')
    <__main__.User object at 0x2529350>

This will *INSERT* a new row into the database. The primary key will
automatically be retrieved and stored on the model instance.

Alternatively, you can build up a model instance programmatically and then call
:py:meth:`~Model.save`:

.. code-block:: pycon

    >>> user = User(username='Charlie')
    >>> user.save()  # save() returns the number of rows modified.
    1
    >>> user.id
    1
    >>> huey = User()
    >>> huey.username = 'Huey'
    >>> huey.save()
    1
    >>> huey.id
    2

When a model has a foreign key, you can directly assign a model instance to the
foreign key field when creating a new record.

.. code-block:: pycon

    >>> tweet = Tweet.create(user=huey, message='Hello!')

You can also use the value of the related object's primary key:

.. code-block:: pycon

    >>> tweet = Tweet.create(user=2, message='Hello again!')

If you simply wish to insert data and do not need to create a model instance,
you can use :py:meth:`Model.insert`:

.. code-block:: pycon

    >>> User.insert(username='Mickey').execute()
    3

After executing the insert query, the primary key of the new row is returned.

.. note::
    There are several ways you can speed up bulk insert operations. Check out
    the :ref:`bulk_inserts` recipe section for more information.

.. _bulk_inserts:

Bulk inserts
------------

There are a couple of ways you can load lots of data quickly. The naive
approach is to simply call :py:meth:`Model.create` in a loop:

.. code-block:: python

    data_source = [
        {'field1': 'val1-1', 'field2': 'val1-2'},
        {'field1': 'val2-1', 'field2': 'val2-2'},
        # ...
    ]

    for data_dict in data_source:
        MyModel.create(**data_dict)

The above approach is slow for a couple of reasons:

1. If you are not wrapping the loop in a transaction then each call to
   :py:meth:`~Model.create` happens in its own transaction. That is going to be
   really slow!
2. There is a decent amount of Python logic getting in your way, and each
   :py:class:`InsertQuery` must be generated and parsed into SQL.
3. That's a lot of data (in terms of raw bytes of SQL) you are sending to your
   database to parse.
4. We are retrieving the *last insert id*, which causes an additional query to
   be executed in some cases.

You can get a **very significant speedup** by simply wrapping this in a
:py:meth:`~Database.atomic`.

.. code-block:: python

    # This is much faster.
    with db.atomic():
        for data_dict in data_source:
            MyModel.create(**data_dict)

The above code still suffers from points 2, 3 and 4. We can get another big
boost by calling :py:meth:`~Model.insert_many`. This method accepts a list of
tuples or dictionaries to insert.

.. code-block:: python

    # Fastest.
    MyModel.insert_many(data_source).execute()

    # Fastest using tuples and specifying the fields being inserted.
    fields = [MyModel.field1, MyModel.field2]
    data = [('val1-1', 'val1-2'),
            ('val2-1', 'val2-2'),
            ('val3-1', 'val3-2')]
    MyModel.insert_many(data, fields=fields).execute()

    # You can, of course, wrap this in a transaction as well:
    with db.atomic():
        MyModel.insert_many(data, fields=fields).execute()

Depending on the number of rows in your data source, you may need to break it
up into chunks:

.. code-block:: python

    # Insert rows 100 at a time.
    with db.atomic():
        for idx in range(0, len(data_source), 100):
            MyModel.insert_many(data_source[idx:idx+100]).execute()

If :py:meth:`Model.insert_many` won't work for your use-case, you can also use
the :py:meth:`Database.batch_commit` helper to process chunks of rows inside
transactions:

.. code-block:: python

    # List of row data to insert.
    row_data = [{'username': 'u1'}, {'username': 'u2'}, ...]

    # Assume there are 789 items in row_data. The following code will result in
    # 8 total transactions (7x100 rows + 1x89 rows).
    for row in db.batch_commit(row_data, 100):
        User.create(**row)

.. note::
    SQLite users should be aware of some caveats when using bulk inserts.
    Specifically, your SQLite3 version must be 3.7.11.0 or newer to take
    advantage of the bulk insert API. Additionally, by default SQLite limits
    the number of bound variables in a SQL query to ``999``. This value can be
    modified by setting the ``SQLITE_MAX_VARIABLE_NUMBER`` flag.

If the data you would like to bulk load is stored in another table, you can
also create *INSERT* queries whose source is a *SELECT* query. Use the
:py:meth:`Model.insert_from` method:

.. code-block:: python

    query = (TweetArchive
             .insert_from(
                 Tweet.select(Tweet.user, Tweet.message),
                 fields=[Tweet.user, Tweet.message])
             .execute())

Updating existing records
-------------------------

Once a model instance has a primary key, any subsequent call to
:py:meth:`~Model.save` will result in an *UPDATE* rather than another *INSERT*.
The model's primary key will not change:

.. code-block:: pycon

    >>> user.save()  # save() returns the number of rows modified.
    1
    >>> user.id
    1
    >>> user.save()
    >>> user.id
    1
    >>> huey.save()
    1
    >>> huey.id
    2

If you want to update multiple records, issue an *UPDATE* query. The following
example will update all ``Tweet`` objects, marking them as *published*, if they
were created before today. :py:meth:`Model.update` accepts keyword arguments
where the keys correspond to the model's field names:

.. code-block:: pycon

    >>> today = datetime.today()
    >>> query = Tweet.update(is_published=True).where(Tweet.creation_date < today)
    >>> query.execute()  # Returns the number of rows that were updated.
    4

For more information, see the documentation on :py:meth:`Model.update` and
:py:class:`Update`.

.. note::
    If you would like more information on performing atomic updates (such as
    incrementing the value of a column), check out the :ref:`atomic update <atomic_updates>`
    recipes.

.. _atomic_updates:

Atomic updates
--------------

Peewee allows you to perform atomic updates. Let's suppose we need to update
some counters. The naive approach would be to write something like this:

.. code-block:: pycon

    >>> for stat in Stat.select().where(Stat.url == request.url):
    ...     stat.counter += 1
    ...     stat.save()

**Do not do this!** Not only is this slow, but it is also vulnerable to race
conditions if multiple processes are updating the counter at the same time.

Instead, you can update the counters atomically using :py:meth:`~Model.update`:

.. code-block:: pycon

    >>> query = Stat.update(counter=Stat.counter + 1).where(Stat.url == request.url)
    >>> query.execute()

You can make these update statements as complex as you like. Let's give all our
employees a bonus equal to their previous bonus plus 10% of their salary:

.. code-block:: pycon

    >>> query = Employee.update(bonus=(Employee.bonus + (Employee.salary * .1)))
    >>> query.execute()  # Give everyone a bonus!

We can even use a subquery to update the value of a column. Suppose we had a
denormalized column on the ``User`` model that stored the number of tweets a
user had made, and we updated this value periodically. Here is how you might
write such a query:

.. code-block:: pycon

    >>> subquery = Tweet.select(fn.COUNT(Tweet.id)).where(Tweet.user == User.id)
    >>> update = User.update(num_tweets=subquery)
    >>> update.execute()

Upsert
^^^^^^

Peewee provides support for varying types of upsert functionality. With SQLite
prior to 3.24.0 and MySQL, Peewee offers the :py:meth:`~Model.replace`, which
allows you to insert a record or, in the event of a constraint violation,
replace the existing record.

Example of using :py:meth:`~Model.replace` and :py:meth:`~Insert.on_conflict_replace`:

.. code-block:: python

    class User(Model):
        username = TextField(unique=True)
        last_login = DateTimeField(null=True)

    # Insert or update the user. The "last_login" value will be updated
    # regardless of whether the user existed previously.
    user_id = (User
               .replace(username='the-user', last_login=datetime.now())
               .execute())

    # This query is equivalent:
    user_id = (User
               .insert(username='the-user', last_login=datetime.now())
               .on_conflict_replace()
               .execute())

.. note::
    In addition to *replace*, SQLite, MySQL and Postgresql provide an *ignore*
    action (see: :py:meth:`~Insert.on_conflict_ignore`) if you simply wish to
    insert and ignore any potential constraint violation.

Postgresql and SQLite (3.24.0 and newer) provide a different syntax that allows
for more granular control over which constraint violation should trigger the
conflict resolution, and what values should be updated or preserved.

Example of using :py:meth:`~Insert.on_conflict` to perform a Postgresql-style
upsert (or SQLite 3.24+):

.. code-block:: python

    class User(Model):
        username = TextField(unique=True)
        last_login = DateTimeField(null=True)
        login_count = IntegerField()

    # Insert a new user.
    User.create(username='huey', login_count=0)

    # Simulate the user logging in. The login count and timestamp will be
    # either created or updated correctly.
    now = datetime.now()
    rowid = (User
             .insert(username='huey', last_login=now, login_count=1)
             .on_conflict(
                 conflict_target=(User.username,),  # Which constraint?
                 preserve=(User.last_login,),  # Use the value we would have inserted.
                 update={User.login_count: User.login_count + 1})
             .execute())

In the above example, we could safely invoke the upsert query as many times as
we wanted. The login count will be incremented atomically, the last login
column will be updated, and no duplicate rows will be created.

For more information, see :py:meth:`Insert.on_conflict` and
:py:class:`OnConflict`.

Deleting records
----------------

To delete a single model instance, you can use the
:py:meth:`Model.delete_instance` shortcut. :py:meth:`~Model.delete_instance`
will delete the given model instance and can optionally delete any dependent
objects recursively (by specifying `recursive=True`).

.. code-block:: pycon

    >>> user = User.get(User.id == 1)
    >>> user.delete_instance()  # Returns the number of rows deleted.
    1

    >>> User.get(User.id == 1)
    UserDoesNotExist: instance matching query does not exist:
    SQL: SELECT t1."id", t1."username" FROM "user" AS t1 WHERE t1."id" = ?
    PARAMS: [1]

To delete an arbitrary set of rows, you can issue a *DELETE* query. The
following will delete all ``Tweet`` objects that are over one year old:

.. code-block:: pycon

    >>> query = Tweet.delete().where(Tweet.creation_date < one_year_ago)
    >>> query.execute()  # Returns the number of rows deleted.
    7

For more information, see the documentation on:

* :py:meth:`Model.delete_instance`
* :py:meth:`Model.delete`
* :py:class:`DeleteQuery`

Selecting a single record
-------------------------

You can use the :py:meth:`Model.get` method to retrieve a single instance
matching the given query. For primary-key lookups, you can also use the
shortcut method :py:meth:`Model.get_by_id`.

This method is a shortcut that calls :py:meth:`Model.select` with the given
query, but limits the result set to a single row. Additionally, if no model
matches the given query, a ``DoesNotExist`` exception will be raised.

.. code-block:: pycon

    >>> User.get(User.id == 1)
    <__main__.User object at 0x25294d0>

    >>> User.get_by_id(1)  # Same as above.
    <__main__.User object at 0x252df10>

    >>> User[1]  # Also same as above.
    <__main__.User object at 0x252dd10>

    >>> User.get(User.id == 1).username
    u'Charlie'

    >>> User.get(User.username == 'Charlie')
    <__main__.User object at 0x2529410>

    >>> User.get(User.username == 'nobody')
    UserDoesNotExist: instance matching query does not exist:
    SQL: SELECT t1."id", t1."username" FROM "user" AS t1 WHERE t1."username" = ?
    PARAMS: ['nobody']

For more advanced operations, you can use :py:meth:`SelectBase.get`. The
following query retrieves the latest tweet from the user named *charlie*:

.. code-block:: pycon

    >>> (Tweet
    ...  .select()
    ...  .join(User)
    ...  .where(User.username == 'charlie')
    ...  .order_by(Tweet.created_date.desc())
    ...  .get())
    <__main__.Tweet object at 0x2623410>

For more information, see the documentation on:

* :py:meth:`Model.get`
* :py:meth:`Model.get_by_id`
* :py:meth:`Model.get_or_none` - if no matching row is found, return ``None``.
* :py:meth:`Model.first`
* :py:meth:`Model.select`
* :py:meth:`SelectBase.get`

Create or get
-------------

Peewee has one helper method for performing "get/create" type operations:
:py:meth:`Model.get_or_create`, which first attempts to retrieve the matching
row. Failing that, a new row will be created.

For "create or get" type logic, typically one would rely on a *unique*
constraint or primary key to prevent the creation of duplicate objects. As an
example, let's say we wish to implement registering a new user account using
the :ref:`example User model <blog-models>`. The *User* model has a *unique*
constraint on the username field, so we will rely on the database's integrity
guarantees to ensure we don't end up with duplicate usernames:

.. code-block:: python

    try:
        with db.atomic():
            return User.create(username=username)
    except peewee.IntegrityError:
        # `username` is a unique column, so this username already exists,
        # making it safe to call .get().
        return User.get(User.username == username)

You can easily encapsulate this type of logic as a ``classmethod`` on your own
``Model`` classes.

The above example first attempts at creation, then falls back to retrieval,
relying on the database to enforce a unique constraint. If you prefer to
attempt to retrieve the record first, you can use
:py:meth:`~Model.get_or_create`. This method is implemented along the same
lines as the Django function of the same name. You can use the Django-style
keyword argument filters to specify your ``WHERE`` conditions. The function
returns a 2-tuple containing the instance and a boolean value indicating if the
object was created.

Here is how you might implement user account creation using
:py:meth:`~Model.get_or_create`:

.. code-block:: python

    user, created = User.get_or_create(username=username)

Suppose we have a different model ``Person`` and would like to get or create a
person object. The only conditions we care about when retrieving the ``Person``
are their first and last names, **but** if we end up needing to create a new
record, we will also specify their date-of-birth and favorite color:

.. code-block:: python

    person, created = Person.get_or_create(
        first_name=first_name,
        last_name=last_name,
        defaults={'dob': dob, 'favorite_color': 'green'})

Any keyword argument passed to :py:meth:`~Model.get_or_create` will be used in
the ``get()`` portion of the logic, except for the ``defaults`` dictionary,
which will be used to populate values on newly-created instances.

For more details read the documentation for :py:meth:`Model.get_or_create`.

Selecting multiple records
--------------------------

We can use :py:meth:`Model.select` to retrieve rows from the table. When you
construct a *SELECT* query, the database will return any rows that correspond
to your query. Peewee allows you to iterate over these rows, as well as use
indexing and slicing operations:

.. code-block:: pycon

    >>> query = User.select()
    >>> [user.username for user in query]
    ['Charlie', 'Huey', 'Peewee']

    >>> query[1]
    <__main__.User at 0x7f83e80f5550>

    >>> query[1].username
    'Huey'

    >>> query[:2]
    [<__main__.User at 0x7f83e80f53a8>, <__main__.User at 0x7f83e80f5550>]

:py:class:`Select` queries are smart, in that you can iterate, index and slice
the query multiple times but the query is only executed once.

In the following example, we will simply call :py:meth:`~Model.select` and
iterate over the return value, which is an instance of :py:class:`Select`.
This will return all the rows in the *User* table:

.. code-block:: pycon

    >>> for user in User.select():
    ...     print user.username
    ...
    Charlie
    Huey
    Peewee

.. note::
    Subsequent iterations of the same query will not hit the database as the
    results are cached. To disable this behavior (to reduce memory usage), call
    :py:meth:`Select.iterator` when iterating.

When iterating over a model that contains a foreign key, be careful with the
way you access values on related models. Accidentally resolving a foreign key
or iterating over a back-reference can cause :ref:`N+1 query behavior <nplusone>`.

When you create a foreign key, such as ``Tweet.user``, you can use the
*backref* to create a back-reference (``User.tweets``). Back-references
are exposed as :py:class:`Select` instances:

.. code-block:: pycon

    >>> tweet = Tweet.get()
    >>> tweet.user  # Accessing a foreign key returns the related model.
    <tw.User at 0x7f3ceb017f50>

    >>> user = User.get()
    >>> user.tweets  # Accessing a back-reference returns a query.
    <peewee.ModelSelect at 0x7f73db3bafd0>

You can iterate over the ``user.tweets`` back-reference just like any other
:py:class:`Select`:

.. code-block:: pycon

    >>> for tweet in user.tweets:
    ...     print(tweet.message)
    ...
    hello world
    this is fun
    look at this picture of my food

In addition to returning model instances, :py:class:`Select` queries can return
dictionaries, tuples and namedtuples. Depending on your use-case, you may find
it easier to work with rows as dictionaries, for example:

.. code-block:: pycon

    >>> query = User.select().dicts()
    >>> for row in query:
    ...     print(row)

    {'id': 1, 'username': 'Charlie'}
    {'id': 2, 'username': 'Huey'}
    {'id': 3, 'username': 'Peewee'}

See :py:meth:`~BaseQuery.namedtuples`, :py:meth:`~BaseQuery.tuples`,
:py:meth:`~BaseQuery.dicts` for more information.

Filtering records
-----------------

You can filter for particular records using normal python operators. Peewee
supports a wide variety of :ref:`query operators <query-operators>`.

.. code-block:: pycon

    >>> user = User.get(User.username == 'Charlie')
    >>> for tweet in Tweet.select().where(Tweet.user == user, Tweet.is_published == True):
    ...     print(tweet.user.username, '->', tweet.message)
    ...
    Charlie -> hello world
    Charlie -> this is fun

    >>> for tweet in Tweet.select().where(Tweet.created_date < datetime.datetime(2011, 1, 1)):
    ...     print(tweet.message, tweet.created_date)
    ...
    Really old tweet 2010-01-01 00:00:00

You can also filter across joins:

.. code-block:: pycon

    >>> for tweet in Tweet.select().join(User).where(User.username == 'Charlie'):
    ...     print(tweet.message)
    hello world
    this is fun
    look at this picture of my food

If you want to express a complex query, use parentheses and python's bitwise
*or* and *and* operators:

.. code-block:: pycon

    >>> Tweet.select().join(User).where(
    ...     (User.username == 'Charlie') |
    ...     (User.username == 'Peewee Herman'))

.. note::
    Note that Peewee uses **bitwise** operators (``&`` and ``|``) rather than
    logical operators (``and`` and ``or``). The reason for this is that Python
    coerces the return value of logical operations to a boolean value. This is
    also the reason why "IN" queries must be expressed using ``.in_()`` rather
    than the ``in`` operator.

Check out :ref:`the table of query operations <query-operators>` to see what
types of queries are possible.

.. note::

    A lot of fun things can go in the where clause of a query, such as:

    * A field expression, e.g. ``User.username == 'Charlie'``
    * A function expression, e.g. ``fn.Lower(fn.Substr(User.username, 1, 1)) == 'a'``
    * A comparison of one column to another, e.g. ``Employee.salary < (Employee.tenure * 1000) + 40000``

    You can also nest queries, for example tweets by users whose username
    starts with "a":

    .. code-block:: python

        # get users whose username starts with "a"
        a_users = User.select().where(fn.Lower(fn.Substr(User.username, 1, 1)) == 'a')

        # the ".in_()" method signifies an "IN" query
        a_user_tweets = Tweet.select().where(Tweet.user.in_(a_users))

More query examples
^^^^^^^^^^^^^^^^^^^

.. note::
    For a wide range of example queries, see the :ref:`Query Examples <query_examples>`
    document, which shows how to implements queries from the `PostgreSQL Exercises <https://pgexercises.com/>`_
    website.

Get active users:

.. code-block:: python

    User.select().where(User.active == True)

Get users who are either staff or superusers:

.. code-block:: python

    User.select().where(
        (User.is_staff == True) | (User.is_superuser == True))

Get tweets by user named "charlie":

.. code-block:: python

    Tweet.select().join(User).where(User.username == 'charlie')

Get tweets by staff or superusers (assumes FK relationship):

.. code-block:: python

    Tweet.select().join(User).where(
        (User.is_staff == True) | (User.is_superuser == True))

Get tweets by staff or superusers using a subquery:

.. code-block:: python

    staff_super = User.select(User.id).where(
        (User.is_staff == True) | (User.is_superuser == True))
    Tweet.select().where(Tweet.user << staff_super)

Sorting records
---------------

To return rows in order, use the :py:meth:`~Query.order_by` method:

.. code-block:: pycon

    >>> for t in Tweet.select().order_by(Tweet.created_date):
    ...     print(t.pub_date)
    ...
    2010-01-01 00:00:00
    2011-06-07 14:08:48
    2011-06-07 14:12:57

    >>> for t in Tweet.select().order_by(Tweet.created_date.desc()):
    ...     print(t.pub_date)
    ...
    2011-06-07 14:12:57
    2011-06-07 14:08:48
    2010-01-01 00:00:00

You can also use ``+`` and ``-`` prefix operators to indicate ordering:

.. code-block:: python

    # The following queries are equivalent:
    Tweet.select().order_by(Tweet.created_date.desc())

    Tweet.select().order_by(-Tweet.created_date)  # Note the "-" prefix.

    # Similarly you can use "+" to indicate ascending order, though ascending
    # is the default when no ordering is otherwise specified.
    User.select().order_by(+User.username)

You can also order across joins. Assuming you want to order tweets by the
username of the author, then by created_date:

.. code-block:: pycon

    query = (Tweet
             .select()
             .join(User)
             .order_by(User.username, Tweet.created_date.desc()))

.. code-block:: sql

    SELECT t1."id", t1."user_id", t1."message", t1."is_published", t1."created_date"
    FROM "tweet" AS t1
    INNER JOIN "user" AS t2
      ON t1."user_id" = t2."id"
    ORDER BY t2."username", t1."created_date" DESC

When sorting on a calculated value, you can either include the necessary SQL
expressions, or reference the alias assigned to the value. Here are two
examples illustrating these methods:

.. code-block:: python

    # Let's start with our base query. We want to get all usernames and the number of
    # tweets they've made. We wish to sort this list from users with most tweets to
    # users with fewest tweets.
    query = (User
             .select(User.username, fn.COUNT(Tweet.id).alias('num_tweets'))
             .join(Tweet, JOIN.LEFT_OUTER)
             .group_by(User.username))

You can order using the same COUNT expression used in the ``select`` clause. In
the example below we are ordering by the ``COUNT()`` of tweet ids descending:

.. code-block:: python

    query = (User
             .select(User.username, fn.COUNT(Tweet.id).alias('num_tweets'))
             .join(Tweet, JOIN.LEFT_OUTER)
             .group_by(User.username)
             .order_by(fn.COUNT(Tweet.id).desc()))

Alternatively, you can reference the alias assigned to the calculated value in
the ``select`` clause. This method has the benefit of being a bit easier to
read. Note that we are not referring to the named alias directly, but are
wrapping it using the :py:class:`SQL` helper:

.. code-block:: python

    query = (User
             .select(User.username, fn.COUNT(Tweet.id).alias('num_tweets'))
             .join(Tweet, JOIN.LEFT_OUTER)
             .group_by(User.username)
             .order_by(SQL('num_tweets').desc()))

Or, to do things the "peewee" way:

.. code-block:: python

    ntweets = fn.COUNT(Tweet.id)
    query = (User
             .select(User.username, ntweets.alias('num_tweets'))
             .join(Tweet, JOIN.LEFT_OUTER)
             .group_by(User.username)
             .order_by(ntweets.desc())

Getting random records
----------------------

Occasionally you may want to pull a random record from the database. You can
accomplish this by ordering by the *random* or *rand* function (depending on
your database):

Postgresql and Sqlite use the *Random* function:

.. code-block:: python

    # Pick 5 lucky winners:
    LotteryNumber.select().order_by(fn.Random()).limit(5)

MySQL uses *Rand*:

.. code-block:: python

    # Pick 5 lucky winners:
    LotterNumber.select().order_by(fn.Rand()).limit(5)

Paginating records
------------------

The :py:meth:`~Query.paginate` method makes it easy to grab a *page* or
records. :py:meth:`~Query.paginate` takes two parameters,
``page_number``, and ``items_per_page``.

.. attention::
    Page numbers are 1-based, so the first page of results will be page 1.

.. code-block:: pycon

    >>> for tweet in Tweet.select().order_by(Tweet.id).paginate(2, 10):
    ...     print(tweet.message)
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

If you would like more granular control, you can always use
:py:meth:`~Query.limit` and :py:meth:`~Query.offset`.

Counting records
----------------

You can count the number of rows in any select query:

.. code-block:: python

    >>> Tweet.select().count()
    100
    >>> Tweet.select().where(Tweet.id > 50).count()
    50

Peewee will wrap your query in an outer query that performs a count, which
results in SQL like:

.. code-block:: sql

    SELECT COUNT(1) FROM ( ... your query ... );

Aggregating records
-------------------

Suppose you have some users and want to get a list of them along with the count
of tweets in each.

.. code-block:: python

    query = (User
             .select(User, fn.Count(Tweet.id).alias('count'))
             .join(Tweet, JOIN.LEFT_OUTER)
             .group_by(User))

The resulting query will return *User* objects with all their normal attributes
plus an additional attribute *count* which will contain the count of tweets for
each user. We use a left outer join to include users who have no tweets.

Let's assume you have a tagging application and want to find tags that have a
certain number of related objects. For this example we'll use some different
models in a :ref:`many-to-many <manytomany>` configuration:

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

    query = (Tag
             .select()
             .join(PhotoTag)
             .join(Photo)
             .group_by(Tag)
             .having(fn.Count(Photo.id) > 5))

This query is equivalent to the following SQL:

.. code-block:: sql

    SELECT t1."id", t1."name"
    FROM "tag" AS t1
    INNER JOIN "phototag" AS t2 ON t1."id" = t2."tag_id"
    INNER JOIN "photo" AS t3 ON t2."photo_id" = t3."id"
    GROUP BY t1."id", t1."name"
    HAVING Count(t3."id") > 5

Suppose we want to grab the associated count and store it on the tag:

.. code-block:: python

    query = (Tag
             .select(Tag, fn.Count(Photo.id).alias('count'))
             .join(PhotoTag)
             .join(Photo)
             .group_by(Tag)
             .having(fn.Count(Photo.id) > 5))

Retrieving Scalar Values
------------------------

You can retrieve scalar values by calling :py:meth:`Query.scalar`. For
instance:

.. code-block:: python

    >>> PageView.select(fn.Count(fn.Distinct(PageView.url))).scalar()
    100

You can retrieve multiple scalar values by passing ``as_tuple=True``:

.. code-block:: python

    >>> Employee.select(
    ...     fn.Min(Employee.salary), fn.Max(Employee.salary)
    ... ).scalar(as_tuple=True)
    (30000, 50000)

SQL Functions, Subqueries and "Raw expressions"
-----------------------------------------------

Suppose you need to want to get a list of all users whose username begins with
*a*. There are a couple ways to do this, but one method might be to use some
SQL functions like *LOWER* and *SUBSTR*. To use arbitrary SQL functions, use
the special :py:func:`fn` object to construct queries:

.. code-block:: python

    # Select the user's id, username and the first letter of their username, lower-cased
    first_letter = fn.LOWER(fn.SUBSTR(User.username, 1, 1))
    query = User.select(User, first_letter.alias('first_letter'))

    # Alternatively we could select only users whose username begins with 'a'
    a_users = User.select().where(first_letter == 'a')

    >>> for user in a_users:
    ...    print(user.username)

There are times when you may want to simply pass in some arbitrary sql. You can
do this using the special :py:class:`SQL` class. One use-case is when
referencing an alias:

.. code-block:: python

    # We'll query the user table and annotate it with a count of tweets for
    # the given user
    query = (User
             .select(User, fn.Count(Tweet.id).alias('ct'))
             .join(Tweet)
             .group_by(User))

    # Now we will order by the count, which was aliased to "ct"
    query = query.order_by(SQL('ct'))

    # You could, of course, also write this as:
    query = query.order_by(fn.COUNT(Tweet.id))

There are two ways to execute hand-crafted SQL statements with peewee:

1. :py:meth:`Database.execute_sql` for executing any type of query
2. :py:class:`RawQuery` for executing ``SELECT`` queries and returning model
   instances.

Security and SQL Injection
--------------------------

By default peewee will parameterize queries, so any parameters passed in by the
user will be escaped. The only exception to this rule is if you are writing a
raw SQL query or are passing in a ``SQL`` object which may contain untrusted
data. To mitigate this, ensure that any user-defined data is passed in as a
query parameter and not part of the actual SQL query:

.. code-block:: python

    # Bad! DO NOT DO THIS!
    query = MyModel.raw('SELECT * FROM my_table WHERE data = %s' % (user_data,))

    # Good. `user_data` will be treated as a parameter to the query.
    query = MyModel.raw('SELECT * FROM my_table WHERE data = %s', user_data)

    # Bad! DO NOT DO THIS!
    query = MyModel.select().where(SQL('Some SQL expression %s' % user_data))

    # Good. `user_data` will be treated as a parameter.
    query = MyModel.select().where(SQL('Some SQL expression %s', user_data))

.. note::
    MySQL and Postgresql use ``'%s'`` to denote parameters. SQLite, on the
    other hand, uses ``'?'``. Be sure to use the character appropriate to your
    database. You can also find this parameter by checking
    :py:attr:`Database.param`.

.. _window-functions:

Window functions
----------------

peewee comes with basic support for SQL window functions, which can be created
by calling :py:meth:`Function.over` and passing in your partitioning or
ordering parameters.

.. code-block:: python

    # Get the list of employees and the average salary for their dept.
    query = (Employee
             .select(
                 Employee.name,
                 Employee.department,
                 Employee.salary,
                 fn.Avg(Employee.salary).over(
                     partition_by=[Employee.department]))
             .order_by(Employee.name))

    # Rank employees by salary.
    query = (Employee
             .select(
                 Employee.name,
                 Employee.salary,
                 fn.rank().over(
                     order_by=[Employee.salary])))

For general information on window functions, check out the `postgresql docs <http://www.postgresql.org/docs/9.1/static/tutorial-window.html>`_.

Retrieving row tuples / dictionaries / namedtuples
--------------------------------------------------

Sometimes you do not need the overhead of creating model instances and simply
want to iterate over the row data without needing all the APIs provided
:py:class:`Model`. To do this, use:

* :py:meth:`~BaseQuery.dicts`
* :py:meth:`~BaseQuery.namedtuples`
* :py:meth:`~BaseQuery.tuples`
* :py:meth:`~BaseQuery.objects` -- accepts an arbitrary constructor function
  which is called with the row tuple.

.. code-block:: python

    stats = (Stat
             .select(Stat.url, fn.Count(Stat.url))
             .group_by(Stat.url)
             .tuples())

    # iterate over a list of 2-tuples containing the url and count
    for stat_url, stat_count in stats:
        print(stat_url, stat_count)

Similarly, you can return the rows from the cursor as dictionaries using
:py:meth:`~BaseQuery.dicts`:

.. code-block:: python

    stats = (Stat
             .select(Stat.url, fn.Count(Stat.url).alias('ct'))
             .group_by(Stat.url)
             .dicts())

    # iterate over a list of 2-tuples containing the url and count
    for stat in stats:
        print(stat['url'], stat['ct'])

.. _returning-clause:

Returning Clause
----------------

:py:class:`PostgresqlDatabase` supports a ``RETURNING`` clause on ``UPDATE``,
``INSERT`` and ``DELETE`` queries. Specifying a ``RETURNING`` clause allows you
to iterate over the rows accessed by the query.

For example, let's say you have an :py:class:`Update` that deactivates all
user accounts whose registration has expired. After deactivating them, you want
to send each user an email letting them know their account was deactivated.
Rather than writing two queries, a ``SELECT`` and an ``UPDATE``, you can do
this in a single ``UPDATE`` query with a ``RETURNING`` clause:

.. code-block:: python

    query = (User
             .update(is_active=False)
             .where(User.registration_expired == True)
             .returning(User))

    # Send an email to every user that was deactivated.
    for deactivate_user in query.execute():
        send_deactivation_email(deactivated_user)

The ``RETURNING`` clause is also available on :py:class:`Insert` and
:py:class:`Delete`. When used with ``INSERT``, the newly-created rows will be
returned. When used with ``DELETE``, the deleted rows will be returned.

The only limitation of the ``RETURNING`` clause is that it can only consist of
columns from tables listed in the query's ``FROM`` clause. To select all
columns from a particular table, you can simply pass in the :py:class:`Model`
class.

.. _query-operators:

Query operators
===============

The following types of comparisons are supported by peewee:

================ =======================================
Comparison       Meaning
================ =======================================
``==``           x equals y
``<``            x is less than y
``<=``           x is less than or equal to y
``>``            x is greater than y
``>=``           x is greater than or equal to y
``!=``           x is not equal to y
``<<``           x IN y, where y is a list or query
``>>``           x IS y, where y is None/NULL
``%``            x LIKE y where y may contain wildcards
``**``           x ILIKE y where y may contain wildcards
``^``            x XOR y
``~``            Unary negation (e.g., NOT x)
================ =======================================

Because I ran out of operators to override, there are some additional query
operations available as methods:

======================= ===============================================
Method                  Meaning
======================= ===============================================
``.contains(substr)``   Wild-card search for substring.
``.startswith(prefix)`` Search for values beginning with ``prefix``.
``.endswith(suffix)``   Search for values ending with ``suffix``.
``.between(low, high)`` Search for values between ``low`` and ``high``.
``.regexp(exp)``        Regular expression match (case-sensitive).
``.iregexp(exp)``       Regular expression match (case-insensitive).
``.bin_and(value)``     Binary AND.
``.bin_or(value)``      Binary OR.
``.in_(value)``         IN lookup (identical to ``<<``).
``.not_in(value)``      NOT IN lookup.
``.is_null(is_null)``   IS NULL or IS NOT NULL. Accepts boolean param.
``.concat(other)``      Concatenate two strings or objects using ``||``.
``.distinct()``         Mark column for DISTINCT selection.
======================= ===============================================

To combine clauses using logical operators, use:

================ ==================== ======================================================
Operator         Meaning              Example
================ ==================== ======================================================
``&``            AND                  ``(User.is_active == True) & (User.is_admin == True)``
``|`` (pipe)     OR                   ``(User.is_admin) | (User.is_superuser)``
``~``            NOT (unary negation) ``~(User.username << ['foo', 'bar', 'baz'])``
================ ==================== ======================================================

Here is how you might use some of these query operators:

.. code-block:: python

    # Find the user whose username is "charlie".
    User.select().where(User.username == 'charlie')

    # Find the users whose username is in [charlie, huey, mickey]
    User.select().where(User.username << ['charlie', 'huey', 'mickey'])

    Employee.select().where(Employee.salary.between(50000, 60000))

    Employee.select().where(Employee.name.startswith('C'))

    Blog.select().where(Blog.title.contains(search_string))

Here is how you might combine expressions. Comparisons can be arbitrarily
complex.

.. note::
  Note that the actual comparisons are wrapped in parentheses. Python's operator
  precedence necessitates that comparisons be wrapped in parentheses.

.. code-block:: python

    # Find any users who are active administrations.
    User.select().where(
      (User.is_admin == True) &
      (User.is_active == True))

    # Find any users who are either administrators or super-users.
    User.select().where(
      (User.is_admin == True) |
      (User.is_superuser == True))

    # Find any Tweets by users who are not admins (NOT IN).
    admins = User.select().where(User.is_admin == True)
    non_admin_tweets = Tweet.select().where(~(Tweet.user << admins))

    # Find any users who are not my friends (strangers).
    friends = User.select().where(User.username.in_(['charlie', 'huey', 'mickey']))
    strangers = User.select().where(User.id.not_in(friends))

.. warning::
    Although you may be tempted to use python's ``in``, ``and``, ``or`` and
    ``not`` operators in your query expressions, these **will not work.** The
    return value of an ``in`` expression is always coerced to a boolean value.
    Similarly, ``and``, ``or`` and ``not`` all treat their arguments as boolean
    values and cannot be overloaded.

    So just remember:

    * Use ``.in_()`` and ``.not_in()`` instead of ``in`` and ``not in``
    * Use ``&`` instead of ``and``
    * Use ``|`` instead of ``or``
    * Use ``~`` instead of ``not``
    * Use ``.is_null()`` instead of ``is None`` or ``== None``.
    * **Don't forget to wrap your comparisons in parentheses when using logical operators.**

For more examples, see the :ref:`expressions` section.

.. note::
  **LIKE and ILIKE with SQLite**

  Because SQLite's ``LIKE`` operation is case-insensitive by default,
  peewee will use the SQLite ``GLOB`` operation for case-sensitive searches.
  The glob operation uses asterisks for wildcards as opposed to the usual
  percent-sign. If you are using SQLite and want case-sensitive partial
  string matching, remember to use asterisks for the wildcard.

Three valued logic
------------------

Because of the way SQL handles ``NULL``, there are some special operations
available for expressing:

* ``IS NULL``
* ``IS NOT NULL``
* ``IN``
* ``NOT IN``

While it would be possible to use the ``IS NULL`` and ``IN`` operators with the
negation operator (``~``), sometimes to get the correct semantics you will need
to explicitly use ``IS NOT NULL`` and ``NOT IN``.

The simplest way to use ``IS NULL`` and ``IN`` is to use the operator
overloads:

.. code-block:: python

    # Get all User objects whose last login is NULL.
    User.select().where(User.last_login >> None)

    # Get users whose username is in the given list.
    usernames = ['charlie', 'huey', 'mickey']
    User.select().where(User.username << usernames)

If you don't like operator overloads, you can call the Field methods instead:

.. code-block:: python

    # Get all User objects whose last login is NULL.
    User.select().where(User.last_login.is_null(True))

    # Get users whose username is in the given list.
    usernames = ['charlie', 'huey', 'mickey']
    User.select().where(User.username.in_(usernames))

To negate the above queries, you can use unary negation, but for the correct
semantics you may need to use the special ``IS NOT`` and ``NOT IN`` operators:

.. code-block:: python

    # Get all User objects whose last login is *NOT* NULL.
    User.select().where(User.last_login.is_null(False))

    # Using unary negation instead.
    User.select().where(~(User.last_login >> None))

    # Get users whose username is *NOT* in the given list.
    usernames = ['charlie', 'huey', 'mickey']
    User.select().where(User.username.not_in(usernames))

    # Using unary negation instead.
    usernames = ['charlie', 'huey', 'mickey']
    User.select().where(~(User.username << usernames))

.. _custom-operators:

Adding user-defined operators
-----------------------------

Because I ran out of python operators to overload, there are some missing
operators in peewee, for instance ``modulo``. If you find that you need to
support an operator that is not in the table above, it is very easy to add your
own.

Here is how you might add support for ``modulo`` in SQLite:

.. code-block:: python

    from peewee import *
    from peewee import Expression # the building block for expressions

    def mod(lhs, rhs):
        return Expression(lhs, '%', rhs)

Now you can use these custom operators to build richer queries:

.. code-block:: python

    # Users with even ids.
    User.select().where(mod(User.id, 2) == 0)

For more examples check out the source to the ``playhouse.postgresql_ext``
module, as it contains numerous operators specific to postgresql's hstore.

.. _expressions:

Expressions
-----------

Peewee is designed to provide a simple, expressive, and pythonic way of
constructing SQL queries. This section will provide a quick overview of some
common types of expressions.

There are two primary types of objects that can be composed to create
expressions:

* :py:class:`Field` instances
* SQL aggregations and functions using :py:class:`fn`

We will assume a simple "User" model with fields for username and other things.
It looks like this:

.. code-block:: python

    class User(Model):
        username = CharField()
        is_admin = BooleanField()
        is_active = BooleanField()
        last_login = DateTimeField()
        login_count = IntegerField()
        failed_logins = IntegerField()

Comparisons use the :ref:`query-operators`:

.. code-block:: python

    # username is equal to 'charlie'
    User.username == 'charlie'

    # user has logged in less than 5 times
    User.login_count < 5

Comparisons can be combined using bitwise *and* and *or*.  Operator precedence
is controlled by python and comparisons can be nested to an arbitrary depth:

.. code-block:: python

    # User is both and admin and has logged in today
    (User.is_admin == True) & (User.last_login >= today)

    # User's username is either charlie or charles
    (User.username == 'charlie') | (User.username == 'charles')

Comparisons can be used with functions as well:

.. code-block:: python

    # user's username starts with a 'g' or a 'G':
    fn.Lower(fn.Substr(User.username, 1, 1)) == 'g'

We can do some fairly interesting things, as expressions can be compared
against other expressions. Expressions also support arithmetic operations:

.. code-block:: python

    # users who entered the incorrect more than half the time and have logged
    # in at least 10 times
    (User.failed_logins > (User.login_count * .5)) & (User.login_count > 10)

Expressions allow us to do atomic updates:

.. code-block:: python

    # when a user logs in we want to increment their login count:
    User.update(login_count=User.login_count + 1).where(User.id == user_id)

Expressions can be used in all parts of a query, so experiment!

Foreign Keys
============

Foreign keys are created using a special field class
:py:class:`ForeignKeyField`. Each foreign key also creates a back-reference on
the related model using the specified *backref*.

.. note::
    In SQLite, foreign keys are not enabled by default. Most things, including
    the Peewee foreign-key API, will work fine, but ON DELETE behaviour will be
    ignored, even if you explicitly specify on_delete to your ForeignKeyField.
    In conjunction with the default PrimaryKeyField behaviour (where deleted
    record IDs can be reused), this can lead to surprising (and almost
    certainly unwanted) behaviour where if you delete a record in table A
    referenced by a foreign key in table B, and then create a new, unrelated,
    record in table A, the new record will end up mis-attached to the undeleted
    record in table B. To avoid the mis-attachment, you can use
    :py:class:`AutoIncrementField`, but it may be better overall to
    ensure that foreign keys are enabled with
    ``pragmas=(('foreign_keys', 'on'),)`` when you
    instantiate :py:class:`SqliteDatabase`.


Traversing foreign keys
-----------------------

Referring back to the :ref:`User and Tweet models <blog-models>`, note that
there is a :py:class:`ForeignKeyField` from *Tweet* to *User*. The foreign key
can be traversed, allowing you access to the associated user instance:

.. code-block:: pycon

    >>> tweet.user.username
    'charlie'

.. note::
    Unless the *User* model was explicitly selected when retrieving the
    *Tweet*, an additional query will be required to load the *User* data. To
    learn how to avoid the extra query, see the :ref:`N+1 query documentation
    <nplusone>`.

The reverse is also true, and we can iterate over the tweets associated with a
given *User* instance:

.. code-block:: python

    >>> for tweet in user.tweets:
    ...     print(tweet.message)
    ...
    http://www.youtube.com/watch?v=xdhLQCYQ-nQ

Under the hood, the *tweets* attribute is just a :py:class:`Select` with the
*WHERE* clause pre-populated to point to the given *User* instance:

.. code-block:: python

    >>> user.tweets
    <peewee.ModelSelect at 0x7f73db3bafd0>

    >>> user.tweets.sql()
    ('SELECT "t1"."id", "t1"."user_id", "t1"."content", "t1"."timestamp" FROM "tweet" AS "t1" WHERE ("t1"."user_id" = ?)',
     [1])

Joining tables
--------------

Use the :py:meth:`~ModelSelect.join` method to *JOIN* additional tables. When a
foreign key exists between the source model and the join model, you do not need
to specify any additional parameters:

.. code-block:: pycon

    >>> my_tweets = Tweet.select().join(User).where(User.username == 'charlie')

By default peewee will use an *INNER* join, but you can use *LEFT OUTER*,
*RIGHT OUTER*, *FULL*, or *CROSS* joins as well:

.. code-block:: python

    users = (User
             .select(User, fn.Count(Tweet.id).alias('num_tweets'))
             .join(Tweet, JOIN.LEFT_OUTER)
             .group_by(User)
             .order_by(fn.Count(Tweet.id).desc()))
    for user in users:
        print(user.username, 'has created', user.num_tweets, 'tweet(s).')

Selecting from multiple models
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

SQL makes it easy to select columns from multiple tables and return it all at
once. Peewee makes this possible, too, but since Peewee models form a graph
(via foreign-keys), the selected data is returned as a graph of model
instances. To see what I mean, consider this query:

.. code-block:: sql

    SELECT tweet.content, tweet.timestamp, user.username
    FROM tweet
    INNER JOIN user ON tweet.user_id = user.id
    ORDER BY tweet.timestamp DESC;

    -- Returns rows like
    -- "Meow I'm a tweet" | 2017-01-17 13:37:00 | huey
    -- "Woof woof" | 2017-01-17 11:59:00 | mickey
    -- "Purr" | 2017-01-17 10:00:00 | huey

With Peewee we would write this query:

.. code-block:: python

    query = (Tweet
             .select(Tweet.content, Tweet.timestamp, User.username)
             .join(User)
             .order_by(Tweet.timestamp.desc()))

The question is: where is the "username" attribute to be found? The answer is
that Peewee, because there is a foreign-key relationship between Tweet and
User, will return each row as a Tweet model *with* the associated User model,
which has it's username attribute set:

.. code-block:: python

    for tweet in query:
        print(tweet.content, tweet.timestamp, tweet.user.username)

When doing complicated joins, joins where no foreign-key exists (for example
joining on a subquery), etc., it is necessary to tell Peewee where to place the
joined attributes. This is done by putting an *alias* on the join predicate
expression.

For example, let's say that in the above query we want to put the joined user
data in the *Tweet.foo* attribute:

.. code-block:: python

    query = (Tweet
             .select(Tweet.content, Tweet.timestamp, User.username)
             .join(User, on=(Tweet.user == User.id).alias('foo'))
             .order_by(Tweet.timestamp.desc()))

    for tweet in query:
        # Joined user data is stored in "tweet.foo":
        print(tweet.content, tweet.timestamp, tweet.foo.username)

For queries with complex joins and selections from several models, constructing
this graph can be expensive. If you wish, instead, to have *all* columns as
attributes on a single model, you can use :py:meth:`~ModelSelect.objects`
method:

.. code-block:: python

    for tweet in query.objects():
        # Now "username" is on the Tweet model itself:
        print(tweet.content, tweet.timestamp, tweet.username)

For additional performance gains, consider using :py:meth:`~BaseQuery.dicts`,
:py:meth:`~BaseQuery.tuples` or :py:meth:`~BaseQuery.namedtuples` when
iterating large and/or complex result-sets.

Multiple Foreign Keys to the Same Model
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When there are multiple foreign keys to the same model, it is good practice to
explicitly specify which field you are joining on.

Referring back to the :ref:`example app's models <example-app-models>`,
consider the *Relationship* model, which is used to denote when one user
follows another. Here is the model definition:

.. code-block:: python

    class Relationship(BaseModel):
        from_user = ForeignKeyField(User, backref='relationships')
        to_user = ForeignKeyField(User, backref='related_to')

        class Meta:
            indexes = (
                # Specify a unique multi-column index on from/to-user.
                (('from_user', 'to_user'), True),
            )

Since there are two foreign keys to *User*, we should always specify which
field we are using in a join.

For example, to determine which users I am following, I would write:

.. code-block:: python

    (User
     .select()
     .join(Relationship, on=Relationship.to_user)
     .where(Relationship.from_user == charlie))

On the other hand, if I wanted to determine which users are following me, I
would instead join on the *from_user* column and filter on the relationship's
*to_user*:

.. code-block:: python

    (User
     .select()
     .join(Relationship, on=Relationship.from_user)
     .where(Relationship.to_user == charlie))

Joining on arbitrary fields
^^^^^^^^^^^^^^^^^^^^^^^^^^^

If a foreign key does not exist between two tables you can still perform a
join, but you must manually specify the join predicate.

In the following example, there is no explicit foreign-key between *User* and
*ActivityLog*, but there is an implied relationship between the
*ActivityLog.object_id* field and *User.id*. Rather than joining on a specific
:py:class:`Field`, we will join using an :py:class:`Expression`.

.. code-block:: python

    user_log = (User
                .select(User, ActivityLog)
                .join(
                    ActivityLog,
                    on=(User.id == ActivityLog.object_id).alias('log'))
                .where(
                    (ActivityLog.activity_type == 'user_activity') &
                    (User.username == 'charlie')))

    for user in user_log:
        print(user.username, user.log.description)

    #### Print something like ####
    charlie logged in
    charlie posted a tweet
    charlie retweeted
    charlie posted a tweet
    charlie logged out

.. note::
    By specifying an alias on the join condition, you can control the attribute
    peewee will assign the joined instance to. In the previous example, we used
    the following *join*:

    .. code-block:: python

        (User.id == ActivityLog.object_id).alias('log')

    Then when iterating over the query, we were able to directly access the
    joined *ActivityLog* without incurring an additional query:

    .. code-block:: python

        for user in user_log:
            print(user.username, user.log.description)

Joining on Multiple Tables
^^^^^^^^^^^^^^^^^^^^^^^^^^

When calling :py:meth:`~ModelSelect.join`, peewee will use the *last joined table*
as the source table. For example:

.. code-block:: python

    User.select().join(Tweet).join(Comment)

This query will result in a join from *User* to *Tweet*, and another join from
*Tweet* to *Comment*.

If you would like to join the same table twice, use the :py:meth:`~ModelSelect.switch` method:

.. code-block:: python

    # Join the Artist table on both `Album` and `Genre`.
    Artist.select().join(Album).switch(Artist).join(Genre)

.. _manytomany:

Implementing Many to Many
-------------------------

Peewee provides a field for representing many-to-many relationships, much like
Django does. This feature was added due to many requests from users, but I
strongly advocate against using it, since it conflates the idea of a field with
a junction table and hidden joins. It's just a nasty hack to provide convenient
accessors.

To implement many-to-many **correctly** with peewee, you will therefore create
the intermediary table yourself and query through it:

.. code-block:: python

    class Student(Model):
        name = CharField()

    class Course(Model):
        name = CharField()

    class StudentCourse(Model):
        student = ForeignKeyField(Student)
        course = ForeignKeyField(Course)

To query, let's say we want to find students who are enrolled in math class:

.. code-block:: python

    query = (Student
             .select()
             .join(StudentCourse)
             .join(Course)
             .where(Course.name == 'math'))
    for student in query:
        print(student.name)

To query what classes a given student is enrolled in:

.. code-block:: python

    courses = (Course
               .select()
               .join(StudentCourse)
               .join(Student)
               .where(Student.name == 'da vinci'))

    for course in courses:
        print(course.name)

To efficiently iterate over a many-to-many relation, i.e., list all students
and their respective courses, we will query the *through* model
``StudentCourse`` and *precompute* the Student and Course:

.. code-block:: python

    query = (StudentCourse
             .select(StudentCourse, Student, Course)
             .join(Course)
             .switch(StudentCourse)
             .join(Student)
             .order_by(Student.name))

To print a list of students and their courses you might do the following:

.. code-block:: python

    for student_course in query:
        print(student_course.student.name, '->', student_course.course.name)

Since we selected all fields from ``Student`` and ``Course`` in the *select*
clause of the query, these foreign key traversals are "free" and we've done the
whole iteration with just 1 query.

ManyToManyField
^^^^^^^^^^^^^^^

The :py:class:`ManyToManyField` provides a *field-like* API over many-to-many
fields. For all but the simplest many-to-many situations, you're better off
using the standard peewee APIs. But, if your models are very simple and your
querying needs are not very complex, you can get a big boost by using
:py:class:`ManyToManyField`. Check out the :ref:`extra-fields` extension module
for details.

Modeling students and courses using :py:class:`ManyToManyField`:

.. code-block:: python

    from peewee import *
    from playhouse.fields import ManyToManyField

    db = SqliteDatabase('school.db')

    class BaseModel(Model):
        class Meta:
            database = db

    class Student(BaseModel):
        name = CharField()

    class Course(BaseModel):
        name = CharField()
        students = ManyToManyField(Student, backref='courses')

    StudentCourse = Course.students.get_through_model()

    db.create_tables([
        Student,
        Course,
        StudentCourse])

    # Get all classes that "huey" is enrolled in:
    huey = Student.get(Student.name == 'Huey')
    for course in huey.courses.order_by(Course.name):
        print(course.name)

    # Get all students in "English 101":
    engl_101 = Course.get(Course.name == 'English 101')
    for student in engl_101.students:
        print(student.name)

    # When adding objects to a many-to-many relationship, we can pass
    # in either a single model instance, a list of models, or even a
    # query of models:
    huey.courses.add(Course.select().where(Course.name.contains('English')))

    engl_101.students.add(Student.get(Student.name == 'Mickey'))
    engl_101.students.add([
        Student.get(Student.name == 'Charlie'),
        Student.get(Student.name == 'Zaizee')])

    # The same rules apply for removing items from a many-to-many:
    huey.courses.remove(Course.select().where(Course.name.startswith('CS')))

    engl_101.students.remove(huey)

    # Calling .clear() will remove all associated objects:
    cs_150.students.clear()

For more examples, see:

* :py:meth:`ManyToManyField.add`
* :py:meth:`ManyToManyField.remove`
* :py:meth:`ManyToManyField.clear`
* :py:meth:`ManyToManyField.get_through_model`

Self-joins
----------

Peewee supports constructing queries containing a self-join.

Using model aliases
^^^^^^^^^^^^^^^^^^^

To join on the same model (table) twice, it is necessary to create a model
alias to represent the second instance of the table in a query. Consider the
following model:

.. code-block:: python

    class Category(Model):
        name = CharField()
        parent = ForeignKeyField('self', backref='children')

What if we wanted to query all categories whose parent category is
*Electronics*. One way would be to perform a self-join:

.. code-block:: python

    Parent = Category.alias()
    query = (Category
             .select()
             .join(Parent, on=(Category.parent == Parent.id))
             .where(Parent.name == 'Electronics'))

When performing a join that uses a :py:class:`ModelAlias`, it is necessary to
specify the join condition using the ``on`` keyword argument. In this case we
are joining the category with its parent category.

Using subqueries
^^^^^^^^^^^^^^^^

Another less common approach involves the use of subqueries. Here is another
way we might construct a query to get all the categories whose parent category
is *Electronics* using a subquery:

.. code-block:: python

    Parent = Category.alias()
    join_query = Parent.select().where(Parent.name == 'Electronics')

    # Subqueries used as JOINs need to have an alias.
    join_query = join_query.alias('jq')

    query = (Category
             .select()
             .join(join_query, on=(Category.parent == join_query.c.id)))

This will generate the following SQL query:

.. code-block:: sql

    SELECT t1."id", t1."name", t1."parent_id"
    FROM "category" AS t1
    INNER JOIN (
      SELECT t2."id"
      FROM "category" AS t2
      WHERE (t2."name" = ?)) AS jq ON (t1."parent_id" = "jq"."id")

To access the ``id`` value from the subquery, we use the ``.c`` magic lookup
which will generate the appropriate SQL expression:

.. code-block:: python

    Category.parent == join_query.c.id
    # Becomes: (t1."parent_id" = "jq"."id")

Performance Techniques
======================

This section outlines some techniques for improving performance when using
peewee.

.. _nplusone:

Avoiding N+1 queries
--------------------

The term *N+1 queries* refers to a situation where an application performs a
query, then for each row of the result set, the application performs at least
one other query (another way to conceptualize this is as a nested loop). In
many cases, these *n* queries can be avoided through the use of a SQL join or
subquery. The database itself may do a nested loop, but it will usually be more
performant than doing *n* queries in your application code, which involves
latency communicating with the database and may not take advantage of indices
or other optimizations employed by the database when joining or executing a
subquery.

Peewee provides several APIs for mitigating *N+1* query behavior. Recollecting
the models used throughout this document, *User* and *Tweet*, this section will
try to outline some common *N+1* scenarios, and how peewee can help you avoid
them.

.. note::
    In some cases, N+1 queries will not result in a significant or measurable
    performance hit. It all depends on the data you are querying, the database
    you are using, and the latency involved in executing queries and retrieving
    results. As always when making optimizations, profile before and after to
    ensure the changes do what you expect them to.

List recent tweets
^^^^^^^^^^^^^^^^^^

The twitter timeline displays a list of tweets from multiple users. In addition
to the tweet's content, the username of the tweet's author is also displayed.
The N+1 scenario here would be:

1. Fetch the 10 most recent tweets.
2. For each tweet, select the author (10 queries).

By selecting both tables and using a *join*, peewee makes it possible to
accomplish this in a single query:

.. code-block:: python

    query = (Tweet
             .select(Tweet, User)  # Note that we are selecting both models.
             .join(User)  # Use an INNER join because every tweet has an author.
             .order_by(Tweet.id.desc())  # Get the most recent tweets.
             .limit(10))

    for tweet in query:
        print(tweet.user.username, '-', tweet.message)

Without the join, accessing ``tweet.user.username`` would trigger a query to
resolve the foreign key ``tweet.user`` and retrieve the associated user. But
since we have selected and joined on ``User``, peewee will automatically
resolve the foreign-key for us.

List users and all their tweets
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let's say you want to build a page that shows several users and all of their
tweets. The N+1 scenario would be:

1. Fetch some users.
2. For each user, fetch their tweets.

This situation is similar to the previous example, but there is one important
difference: when we selected tweets, they only have a single associated user,
so we could directly assign the foreign key. The reverse is not true, however,
as one user may have any number of tweets (or none at all).

Peewee provides an approach to avoiding *O(n)* queries in this situation. Fetch
users first, then fetch all the tweets associated with those users.  Once
peewee has the big list of tweets, it will assign them out, matching them with
the appropriate user. This method is usually faster but will involve a query
for each table being selected.

.. _prefetch:

Using prefetch
^^^^^^^^^^^^^^

peewee supports pre-fetching related data using sub-queries. This method
requires the use of a special API, :py:func:`prefetch`. Pre-fetch, as its name
indicates, will eagerly load the appropriate tweets for the given users using
subqueries. This means instead of *O(n)* queries for *n* rows, we will do
*O(k)* queries for *k* tables.

Here is an example of how we might fetch several users and any tweets they
created within the past week.

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
        print(user.username)
        for tweet in user.tweets:
            print('  ', tweet.message)

.. note::
    Note that neither the ``User`` query, nor the ``Tweet`` query contained a
    JOIN clause. When using :py:func:`prefetch` you do not need to specify the
    join.

:py:func:`prefetch` can be used to query an arbitrary number of tables. Check
the API documentation for more examples.

Some things to consider when using :py:func:`prefetch`:

* Foreign keys must exist between the models being prefetched.
* `LIMIT` works as you'd expect on the outer-most query, but may be difficult
  to implement correctly if trying to limit the size of the sub-selects.

Iterating over lots of rows
---------------------------

By default peewee will cache the rows returned when iterating of a
:py:class:`Select`. This is an optimization to allow multiple iterations as
well as indexing and slicing without causing additional queries. This caching
can be problematic, however, when you plan to iterate over a large number of
rows.

To reduce the amount of memory used by peewee when iterating over a query, use
the :py:meth:`~BaseQuery.iterator` method. This method allows you to iterate
without caching each model returned, using much less memory when iterating over
large result sets.

.. code-block:: python

    # Let's assume we've got 10 million stat objects to dump to a csv file.
    stats = Stat.select()

    # Our imaginary serializer class
    serializer = CSVSerializer()

    # Loop over all the stats and serialize.
    for stat in stats.iterator():
        serializer.serialize_object(stat)

For simple queries you can see further speed improvements by using:

* :py:meth:`~BaseQuery.dicts`
* :py:meth:`~BaseQuery.namedtuples`
* :py:meth:`~BaseQuery.objects`
* :py:meth:`~BaseQuery.tuples`

When iterating over a large number of rows that contain columns from multiple
tables, peewee will reconstruct the model graph for each row returned. This
operation can be slow for complex graphs.

Ordinarily, when a query contains joins, peewee will reconstruct the graph of
joined data returned by cursor. Using the above helpers returns a simpler
data-structure which can be much more efficient when iterating over large or
very-complex queries.

.. note::
    If no constructor is passed to :py:meth:`~BaseQuery.objects`, then peewee
    will return model instances. However, instead of attempting to reconstruct
    a graph of any joined data, all columns will be returned as attributes of
    the model.

    For example:

    .. code-block:: python

        query = (Tweet
                 .select(Tweet, User)
                 .join(User))

        # Note that the user columns are stored in a separate User instance
        # accessible at row.user:
        for tweet in query:
            print(tweet.user.username, tweet.content)

        # Using ".objects()" will put all attributes on the model we are
        # querying.
        for tweet in query.objects():
            print(tweet.username, tweet.content)

.. code-block:: python

    for stat in stats.objects().iterator():
        serializer.serialize_object(stat)

Speeding up Bulk Inserts
------------------------

See the :ref:`bulk_inserts` section for details on speeding up bulk insert
operations.
