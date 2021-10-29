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

You can get a significant speedup by simply wrapping this in a transaction with
:py:meth:`~Database.atomic`.

.. code-block:: python

    # This is much faster.
    with db.atomic():
        for data_dict in data_source:
            MyModel.create(**data_dict)

The above code still suffers from points 2, 3 and 4. We can get another big
boost by using :py:meth:`~Model.insert_many`. This method accepts a list of
tuples or dictionaries, and inserts multiple rows in a single query:

.. code-block:: python

    data_source = [
        {'field1': 'val1-1', 'field2': 'val1-2'},
        {'field1': 'val2-1', 'field2': 'val2-2'},
        # ...
    ]

    # Fastest way to INSERT multiple rows.
    MyModel.insert_many(data_source).execute()

The :py:meth:`~Model.insert_many` method also accepts a list of row-tuples,
provided you also specify the corresponding fields:

.. code-block:: python

    # We can INSERT tuples as well...
    data = [('val1-1', 'val1-2'),
            ('val2-1', 'val2-2'),
            ('val3-1', 'val3-2')]

    # But we need to indicate which fields the values correspond to.
    MyModel.insert_many(data, fields=[MyModel.field1, MyModel.field2]).execute()

It is also a good practice to wrap the bulk insert in a transaction:

.. code-block:: python

    # You can, of course, wrap this in a transaction as well:
    with db.atomic():
        MyModel.insert_many(data, fields=fields).execute()

.. note::
    SQLite users should be aware of some caveats when using bulk inserts.
    Specifically, your SQLite3 version must be 3.7.11.0 or newer to take
    advantage of the bulk insert API. Additionally, by default SQLite limits
    the number of bound variables in a SQL query to ``999`` for SQLite versions
    prior to 3.32.0 (2020-05-22) and 32766 for SQLite versions after 3.32.0.

Inserting rows in batches
^^^^^^^^^^^^^^^^^^^^^^^^^

Depending on the number of rows in your data source, you may need to break it
up into chunks. SQLite in particular typically has a `limit of 999 or 32766 <https://www.sqlite.org/limits.html#max_variable_number>`_
variables-per-query (batch size would then be 999 // row length or 32766 // row length).

You can write a loop to batch your data into chunks (in which case it is
**strongly recommended** you use a transaction):

.. code-block:: python

    # Insert rows 100 at a time.
    with db.atomic():
        for idx in range(0, len(data_source), 100):
            MyModel.insert_many(data_source[idx:idx+100]).execute()

Peewee comes with a :py:func:`chunked` helper function which you can use for
*efficiently* chunking a generic iterable into a series of *batch*-sized
iterables:

.. code-block:: python

    from peewee import chunked

    # Insert rows 100 at a time.
    with db.atomic():
        for batch in chunked(data_source, 100):
            MyModel.insert_many(batch).execute()

Alternatives
^^^^^^^^^^^^

The :py:meth:`Model.bulk_create` method behaves much like
:py:meth:`Model.insert_many`, but instead it accepts a list of unsaved model
instances to insert, and it optionally accepts a batch-size parameter. To use
the :py:meth:`~Model.bulk_create` API:

.. code-block:: python

    # Read list of usernames from a file, for example.
    with open('user_list.txt') as fh:
        # Create a list of unsaved User instances.
        users = [User(username=line.strip()) for line in fh.readlines()]

    # Wrap the operation in a transaction and batch INSERT the users
    # 100 at a time.
    with db.atomic():
        User.bulk_create(users, batch_size=100)

.. note::
    If you are using Postgresql (which supports the ``RETURNING`` clause), then
    the previously-unsaved model instances will have their new primary key
    values automatically populated.

In addition, Peewee also offers :py:meth:`Model.bulk_update`, which can
efficiently update one or more columns on a list of models. For example:

.. code-block:: python

    # First, create 3 users with usernames u1, u2, u3.
    u1, u2, u3 = [User.create(username='u%s' % i) for i in (1, 2, 3)]

    # Now we'll modify the user instances.
    u1.username = 'u1-x'
    u2.username = 'u2-y'
    u3.username = 'u3-z'

    # Update all three users with a single UPDATE query.
    User.bulk_update([u1, u2, u3], fields=[User.username])

.. note::
    For large lists of objects, you should specify a reasonable batch_size and
    wrap the call to :py:meth:`~Model.bulk_update` with
    :py:meth:`Database.atomic`:

    .. code-block:: python

        with database.atomic():
            User.bulk_update(list_of_users, fields=['username'], batch_size=50)

Alternatively, you can use the :py:meth:`Database.batch_commit` helper to
process chunks of rows inside *batch*-sized transactions. This method also
provides a workaround for databases besides Postgresql, when the primary-key of
the newly-created rows must be obtained.

.. code-block:: python

    # List of row data to insert.
    row_data = [{'username': 'u1'}, {'username': 'u2'}, ...]

    # Assume there are 789 items in row_data. The following code will result in
    # 8 total transactions (7x100 rows + 1x89 rows).
    for row in db.batch_commit(row_data, 100):
        User.create(**row)

Bulk-loading from another table
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If the data you would like to bulk load is stored in another table, you can
also create *INSERT* queries whose source is a *SELECT* query. Use the
:py:meth:`Model.insert_from` method:

.. code-block:: python

    res = (TweetArchive
           .insert_from(
               Tweet.select(Tweet.user, Tweet.message),
               fields=[TweetArchive.user, TweetArchive.message])
           .execute())

The above query is equivalent to the following SQL:

.. code-block:: sql

    INSERT INTO "tweet_archive" ("user_id", "message")
    SELECT "user_id", "message" FROM "tweet";


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

For more information, see the documentation on :py:meth:`Model.update`,
:py:class:`Update` and :py:meth:`Model.bulk_update`.

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

**MySQL** supports upsert via the *ON DUPLICATE KEY UPDATE* clause. For
example:

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
                 preserve=[User.last_login],  # Use the value we would have inserted.
                 update={User.login_count: User.login_count + 1})
             .execute())

In the above example, we could safely invoke the upsert query as many times as
we wanted. The login count will be incremented atomically, the last login
column will be updated, and no duplicate rows will be created.

**Postgresql and SQLite** (3.24.0 and newer) provide a different syntax that
allows for more granular control over which constraint violation should trigger
the conflict resolution, and what values should be updated or preserved.

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
                 conflict_target=[User.username],  # Which constraint?
                 preserve=[User.last_login],  # Use the value we would have inserted.
                 update={User.login_count: User.login_count + 1})
             .execute())

In the above example, we could safely invoke the upsert query as many times as
we wanted. The login count will be incremented atomically, the last login
column will be updated, and no duplicate rows will be created.

.. note::
    The main difference between MySQL and Postgresql/SQLite is that Postgresql
    and SQLite require that you specify a ``conflict_target``.

Here is a more advanced (if contrived) example using the :py:class:`EXCLUDED`
namespace. The :py:class:`EXCLUDED` helper allows us to reference values in the
conflicting data. For our example, we'll assume a simple table mapping a unique
key (string) to a value (integer):

.. code-block:: python

    class KV(Model):
        key = CharField(unique=True)
        value = IntegerField()

    # Create one row.
    KV.create(key='k1', value=1)

    # Demonstrate usage of EXCLUDED.
    # Here we will attempt to insert a new value for a given key. If that
    # key already exists, then we will update its value with the *sum* of its
    # original value and the value we attempted to insert -- provided that
    # the new value is larger than the original value.
    query = (KV.insert(key='k1', value=10)
             .on_conflict(conflict_target=[KV.key],
                          update={KV.value: KV.value + EXCLUDED.value},
                          where=(EXCLUDED.value > KV.value)))

    # Executing the above query will result in the following data being
    # present in the "kv" table:
    # (key='k1', value=11)
    query.execute()

    # If we attempted to execute the query *again*, then nothing would be
    # updated, as the new value (10) is now less than the value in the
    # original row (11).

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
* :py:meth:`Model.select`
* :py:meth:`SelectBase.get`
* :py:meth:`SelectBase.first` - return first record of result-set or ``None``.

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
    ...     print(user.username)
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

Iterating over large result-sets
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

By default peewee will cache the rows returned when iterating over a
:py:class:`Select` query. This is an optimization to allow multiple iterations
as well as indexing and slicing without causing additional queries. This
caching can be problematic, however, when you plan to iterate over a large
number of rows.

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

For simple queries you can see further speed improvements by returning rows as
dictionaries, namedtuples or tuples. The following methods can be used on any
:py:class:`Select` query to change the result row type:

* :py:meth:`~BaseQuery.dicts`
* :py:meth:`~BaseQuery.namedtuples`
* :py:meth:`~BaseQuery.tuples`

Don't forget to append the :py:meth:`~BaseQuery.iterator` method call to also
reduce memory consumption. For example, the above code might look like:

.. code-block:: python

    # Let's assume we've got 10 million stat objects to dump to a csv file.
    stats = Stat.select()

    # Our imaginary serializer class
    serializer = CSVSerializer()

    # Loop over all the stats (rendered as tuples, without caching) and serialize.
    for stat_tuple in stats.tuples().iterator():
        serializer.serialize_tuple(stat_tuple)

When iterating over a large number of rows that contain columns from multiple
tables, peewee will reconstruct the model graph for each row returned. This
operation can be slow for complex graphs. For example, if we were selecting a
list of tweets along with the username and avatar of the tweet's author, Peewee
would have to create two objects for each row (a tweet and a user). In addition
to the above row-types, there is a fourth method :py:meth:`~BaseQuery.objects`
which will return the rows as model instances, but will not attempt to resolve
the model graph.

For example:

.. code-block:: python

    query = (Tweet
             .select(Tweet, User)  # Select tweet and user data.
             .join(User))

    # Note that the user columns are stored in a separate User instance
    # accessible at tweet.user:
    for tweet in query:
        print(tweet.user.username, tweet.content)

    # Using ".objects()" will not create the tweet.user object and assigns all
    # user attributes to the tweet instance:
    for tweet in query.objects():
        print(tweet.username, tweet.content)

For maximum performance, you can execute queries and then iterate over the
results using the underlying database cursor. :py:meth:`Database.execute`
accepts a query object, executes the query, and returns a DB-API 2.0 ``Cursor``
object. The cursor will return the raw row-tuples:

.. code-block:: python

    query = Tweet.select(Tweet.content, User.username).join(User)
    cursor = database.execute(query)
    for (content, username) in cursor:
        print(username, '->', content)

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
    Tweet.select().where(Tweet.user.in_(staff_super))

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
    LotteryNumber.select().order_by(fn.Rand()).limit(5)

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

.. _window-functions:

Window functions
----------------

A :py:class:`Window` function refers to an aggregate function that operates on
a sliding window of data that is being processed as part of a ``SELECT`` query.
Window functions make it possible to do things like:

1. Perform aggregations against subsets of a result-set.
2. Calculate a running total.
3. Rank results.
4. Compare a row value to a value in the preceding (or succeeding!) row(s).

peewee comes with support for SQL window functions, which can be created by
calling :py:meth:`Function.over` and passing in your partitioning or ordering
parameters.

For the following examples, we'll use the following model and sample data:

.. code-block:: python

    class Sample(Model):
        counter = IntegerField()
        value = FloatField()

    data = [(1, 10),
            (1, 20),
            (2, 1),
            (2, 3),
            (3, 100)]
    Sample.insert_many(data, fields=[Sample.counter, Sample.value]).execute()

Our sample table now contains:

=== ======== ======
id  counter  value
=== ======== ======
1   1        10.0
2   1        20.0
3   2        1.0
4   2        3.0
5   3        100.0
=== ======== ======

Ordered Windows
^^^^^^^^^^^^^^^

Let's calculate a running sum of the ``value`` field. In order for it to be a
"running" sum, we need it to be ordered, so we'll order with respect to the
Sample's ``id`` field:

.. code-block:: python

    query = Sample.select(
        Sample.counter,
        Sample.value,
        fn.SUM(Sample.value).over(order_by=[Sample.id]).alias('total'))

    for sample in query:
        print(sample.counter, sample.value, sample.total)

    # 1    10.    10.
    # 1    20.    30.
    # 2     1.    31.
    # 2     3.    34.
    # 3   100    134.

For another example, we'll calculate the difference between the current value
and the previous value, when ordered by the ``id``:

.. code-block:: python

    difference = Sample.value - fn.LAG(Sample.value, 1).over(order_by=[Sample.id])
    query = Sample.select(
        Sample.counter,
        Sample.value,
        difference.alias('diff'))

    for sample in query:
        print(sample.counter, sample.value, sample.diff)

    # 1    10.   NULL
    # 1    20.    10.  -- (20 - 10)
    # 2     1.   -19.  -- (1 - 20)
    # 2     3.     2.  -- (3 - 1)
    # 3   100     97.  -- (100 - 3)

Partitioned Windows
^^^^^^^^^^^^^^^^^^^

Let's calculate the average ``value`` for each distinct "counter" value. Notice
that there are three possible values for the ``counter`` field (1, 2, and 3).
We can do this by calculating the ``AVG()`` of the ``value`` column over a
window that is partitioned depending on the ``counter`` field:

.. code-block:: python

    query = Sample.select(
        Sample.counter,
        Sample.value,
        fn.AVG(Sample.value).over(partition_by=[Sample.counter]).alias('cavg'))

    for sample in query:
        print(sample.counter, sample.value, sample.cavg)

    # 1    10.    15.
    # 1    20.    15.
    # 2     1.     2.
    # 2     3.     2.
    # 3   100    100.

We can use ordering within partitions by specifying both the ``order_by`` and
``partition_by`` parameters. For an example, let's rank the samples by value
within each distinct ``counter`` group.

.. code-block:: python

    query = Sample.select(
        Sample.counter,
        Sample.value,
        fn.RANK().over(
            order_by=[Sample.value],
            partition_by=[Sample.counter]).alias('rank'))

    for sample in query:
        print(sample.counter, sample.value, sample.rank)

    # 1    10.    1
    # 1    20.    2
    # 2     1.    1
    # 2     3.    2
    # 3   100     1

Bounded windows
^^^^^^^^^^^^^^^

By default, window functions are evaluated using an *unbounded preceding* start
for the window, and the *current row* as the end. We can change the bounds of
the window our aggregate functions operate on by specifying a ``start`` and/or
``end`` in the call to :py:meth:`Function.over`. Additionally, Peewee comes
with helper-methods on the :py:class:`Window` object for generating the
appropriate boundary references:

* :py:attr:`Window.CURRENT_ROW` - attribute that references the current row.
* :py:meth:`Window.preceding` - specify number of row(s) preceding, or omit
  number to indicate **all** preceding rows.
* :py:meth:`Window.following` - specify number of row(s) following, or omit
  number to indicate **all** following rows.

To examine how boundaries work, we'll calculate a running total of the
``value`` column, ordered with respect to ``id``, **but** we'll only look the
running total of the current row and it's two preceding rows:

.. code-block:: python

    query = Sample.select(
        Sample.counter,
        Sample.value,
        fn.SUM(Sample.value).over(
            order_by=[Sample.id],
            start=Window.preceding(2),
            end=Window.CURRENT_ROW).alias('rsum'))

    for sample in query:
        print(sample.counter, sample.value, sample.rsum)

    # 1    10.    10.
    # 1    20.    30.  -- (20 + 10)
    # 2     1.    31.  -- (1 + 20 + 10)
    # 2     3.    24.  -- (3 + 1 + 20)
    # 3   100    104.  -- (100 + 3 + 1)

.. note::
    Technically we did not need to specify the ``end=Window.CURRENT`` because
    that is the default. It was shown in the example for demonstration.

Let's look at another example. In this example we will calculate the "opposite"
of a running total, in which the total sum of all values is decreased by the
value of the samples, ordered by ``id``. To accomplish this, we'll calculate
the sum from the current row to the last row.

.. code-block:: python

    query = Sample.select(
        Sample.counter,
        Sample.value,
        fn.SUM(Sample.value).over(
            order_by=[Sample.id],
            start=Window.CURRENT_ROW,
            end=Window.following()).alias('rsum'))

    # 1    10.   134.  -- (10 + 20 + 1 + 3 + 100)
    # 1    20.   124.  -- (20 + 1 + 3 + 100)
    # 2     1.   104.  -- (1 + 3 + 100)
    # 2     3.   103.  -- (3 + 100)
    # 3   100    100.  -- (100)

Filtered Aggregates
^^^^^^^^^^^^^^^^^^^

Aggregate functions may also support filter functions (Postgres and Sqlite
3.25+), which get translated into a ``FILTER (WHERE...)`` clause. Filter
expressions are added to an aggregate function with the
:py:meth:`Function.filter` method.

For an example, we will calculate the running sum of the ``value`` field with
respect to the ``id``, but we will filter-out any samples whose ``counter=2``.

.. code-block:: python

    query = Sample.select(
        Sample.counter,
        Sample.value,
        fn.SUM(Sample.value).filter(Sample.counter != 2).over(
            order_by=[Sample.id]).alias('csum'))

    for sample in query:
        print(sample.counter, sample.value, sample.csum)

    # 1    10.    10.
    # 1    20.    30.
    # 2     1.    30.
    # 2     3.    30.
    # 3   100    130.

.. note::
    The call to :py:meth:`~Function.filter` must precede the call to
    :py:meth:`~Function.over`.

Reusing Window Definitions
^^^^^^^^^^^^^^^^^^^^^^^^^^

If you intend to use the same window definition for multiple aggregates, you
can create a :py:class:`Window` object. The :py:class:`Window` object takes the
same parameters as :py:meth:`Function.over`, and can be passed to the
``over()`` method in-place of the individual parameters.

Here we'll declare a single window, ordered with respect to the sample ``id``,
and call several window functions using that window definition:

.. code-block:: python

    win = Window(order_by=[Sample.id])
    query = Sample.select(
        Sample.counter,
        Sample.value,
        fn.LEAD(Sample.value).over(win),
        fn.LAG(Sample.value).over(win),
        fn.SUM(Sample.value).over(win)
    ).window(win)  # Include our window definition in query.

    for row in query.tuples():
        print(row)

    # counter  value  lead()  lag()  sum()
    # 1          10.     20.   NULL    10.
    # 1          20.      1.    10.    30.
    # 2           1.      3.    20.    31.
    # 2           3.    100.     1.    34.
    # 3         100.    NULL     3.   134.

Multiple window definitions
^^^^^^^^^^^^^^^^^^^^^^^^^^^

In the previous example, we saw how to declare a :py:class:`Window` definition
and re-use it for multiple different aggregations. You can include as many
window definitions as you need in your queries, but it is necessary to ensure
each window has a unique alias:

.. code-block:: python

    w1 = Window(order_by=[Sample.id]).alias('w1')
    w2 = Window(partition_by=[Sample.counter]).alias('w2')
    query = Sample.select(
        Sample.counter,
        Sample.value,
        fn.SUM(Sample.value).over(w1).alias('rsum'),  # Running total.
        fn.AVG(Sample.value).over(w2).alias('cavg')   # Avg per category.
    ).window(w1, w2)  # Include our window definitions.

    for sample in query:
        print(sample.counter, sample.value, sample.rsum, sample.cavg)

    # counter  value   rsum     cavg
    # 1          10.     10.     15.
    # 1          20.     30.     15.
    # 2           1.     31.      2.
    # 2           3.     34.      2.
    # 3         100     134.    100.

Similarly, if you have multiple window definitions that share similar
definitions, it is possible to extend a previously-defined window definition.
For example, here we will be partitioning the data-set by the counter value, so
we'll be doing our aggregations with respect to the counter. Then we'll define
a second window that extends this partitioning, and adds an ordering clause:

.. code-block:: python

    w1 = Window(partition_by=[Sample.counter]).alias('w1')

    # By extending w1, this window definition will also be partitioned
    # by "counter".
    w2 = Window(extends=w1, order_by=[Sample.value.desc()]).alias('w2')

    query = (Sample
             .select(Sample.counter, Sample.value,
                     fn.SUM(Sample.value).over(w1).alias('group_sum'),
                     fn.RANK().over(w2).alias('revrank'))
             .window(w1, w2)
             .order_by(Sample.id))

    for sample in query:
        print(sample.counter, sample.value, sample.group_sum, sample.revrank)

    # counter  value   group_sum   revrank
    # 1        10.     30.         2
    # 1        20.     30.         1
    # 2        1.      4.          2
    # 2        3.      4.          1
    # 3        100.    100.        1

.. _window-frame-types:

Frame types: RANGE vs ROWS vs GROUPS
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Depending on the frame type, the database will process ordered groups
differently. Let's create two additional ``Sample`` rows to visualize the
difference:

.. code-block:: pycon

    >>> Sample.create(counter=1, value=20.)
    <Sample 6>
    >>> Sample.create(counter=2, value=1.)
    <Sample 7>

Our table now contains:

=== ======== ======
id  counter  value
=== ======== ======
1   1        10.0
2   1        20.0
3   2        1.0
4   2        3.0
5   3        100.0
6   1        20.0
7   2        1.0
=== ======== ======

Let's examine the difference by calculating a "running sum" of the samples,
ordered with respect to the ``counter`` and ``value`` fields. To specify the
frame type, we can use either:

* :py:attr:`Window.RANGE`
* :py:attr:`Window.ROWS`
* :py:attr:`Window.GROUPS`

The behavior of :py:attr:`~Window.RANGE`, when there are logical duplicates,
may lead to unexpected results:

.. code-block:: python

    query = Sample.select(
        Sample.counter,
        Sample.value,
        fn.SUM(Sample.value).over(
            order_by=[Sample.counter, Sample.value],
            frame_type=Window.RANGE).alias('rsum'))

    for sample in query.order_by(Sample.counter, Sample.value):
        print(sample.counter, sample.value, sample.rsum)

    # counter  value   rsum
    # 1          10.     10.
    # 1          20.     50.
    # 1          20.     50.
    # 2           1.     52.
    # 2           1.     52.
    # 2           3.     55.
    # 3         100     155.

With the inclusion of the new rows we now have some rows that have duplicate
``category`` and ``value`` values. The :py:attr:`~Window.RANGE` frame type
causes these duplicates to be evaluated together rather than separately.

The more expected result can be achieved by using :py:attr:`~Window.ROWS` as
the frame-type:

.. code-block:: python

    query = Sample.select(
        Sample.counter,
        Sample.value,
        fn.SUM(Sample.value).over(
            order_by=[Sample.counter, Sample.value],
            frame_type=Window.ROWS).alias('rsum'))

    for sample in query.order_by(Sample.counter, Sample.value):
        print(sample.counter, sample.value, sample.rsum)

    # counter  value   rsum
    # 1          10.     10.
    # 1          20.     30.
    # 1          20.     50.
    # 2           1.     51.
    # 2           1.     52.
    # 2           3.     55.
    # 3         100     155.

Peewee uses these rules for determining what frame-type to use:

* If the user specifies a ``frame_type``, that frame type will be used.
* If ``start`` and/or ``end`` boundaries are specified Peewee will default to
  using ``ROWS``.
* If the user did not specify frame type or start/end boundaries, Peewee will
  use the database default, which is ``RANGE``.

The :py:attr:`Window.GROUPS` frame type looks at the window range specification
in terms of groups of rows, based on the ordering term(s). Using ``GROUPS``, we
can define the frame so it covers distinct groupings of rows. Let's look at an
example:

.. code-block:: python

    query = (Sample
             .select(Sample.counter, Sample.value,
                     fn.SUM(Sample.value).over(
                        order_by=[Sample.counter, Sample.value],
                        frame_type=Window.GROUPS,
                        start=Window.preceding(1)).alias('gsum'))
             .order_by(Sample.counter, Sample.value))

    for sample in query:
        print(sample.counter, sample.value, sample.gsum)

    #  counter   value    gsum
    #  1         10       10
    #  1         20       50
    #  1         20       50   (10) + (20+0)
    #  2         1        42
    #  2         1        42   (20+20) + (1+1)
    #  2         3        5    (1+1) + 3
    #  3         100      103  (3) + 100

As you can hopefully infer, the window is grouped by its ordering term, which
is ``(counter, value)``. We are looking at a window that extends between one
previous group and the current group.

.. note::
    For information about the window function APIs, see:

    * :py:meth:`Function.over`
    * :py:meth:`Function.filter`
    * :py:class:`Window`

    For general information on window functions, read the postgres `window functions tutorial <https://www.postgresql.org/docs/current/tutorial-window.html>`_

    Additionally, the `postgres docs <https://www.postgresql.org/docs/current/sql-select.html#SQL-WINDOW>`_
    and the `sqlite docs <https://www.sqlite.org/windowfunctions.html>`_
    contain a lot of good information.

.. _rowtypes:

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

By default, the return values upon execution of the different queries are:

* ``INSERT`` - auto-incrementing primary key value of the newly-inserted row.
  When not using an auto-incrementing primary key, Postgres will return the new
  row's primary key, but SQLite and MySQL will not.
* ``UPDATE`` - number of rows modified
* ``DELETE`` - number of rows deleted

When a returning clause is used the return value upon executing a query will be
an iterable cursor object.

Postgresql allows, via the ``RETURNING`` clause, to return data from the rows
inserted or modified by a query.

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
        send_deactivation_email(deactivated_user.email)

The ``RETURNING`` clause is also available on :py:class:`Insert` and
:py:class:`Delete`. When used with ``INSERT``, the newly-created rows will be
returned. When used with ``DELETE``, the deleted rows will be returned.

The only limitation of the ``RETURNING`` clause is that it can only consist of
columns from tables listed in the query's ``FROM`` clause. To select all
columns from a particular table, you can simply pass in the :py:class:`Model`
class.

As another example, let's add a user and set their creation-date to the
server-generated current timestamp. We'll create and retrieve the new user's
ID, Email and the creation timestamp in a single query:

.. code-block:: python

    query = (User
             .insert(email='foo@bar.com', created=fn.now())
             .returning(User))  # Shorthand for all columns on User.

    # When using RETURNING, execute() returns a cursor.
    cursor = query.execute()

    # Get the user object we just inserted and log the data:
    user = cursor[0]
    logger.info('Created user %s (id=%s) at %s', user.email, user.id, user.created)

By default the cursor will return :py:class:`Model` instances, but you can
specify a different row type:

.. code-block:: python

    data = [{'name': 'charlie'}, {'name': 'huey'}, {'name': 'mickey'}]
    query = (User
             .insert_many(data)
             .returning(User.id, User.username)
             .dicts())

    for new_user in query.execute():
        print('Added user "%s", id=%s' % (new_user['username'], new_user['id']))

Just as with :py:class:`Select` queries, you can specify various :ref:`result row types <rowtypes>`.

.. _cte:

Common Table Expressions
------------------------

Peewee supports the inclusion of common table expressions (CTEs) in all types
of queries. CTEs may be useful for:

* Factoring out a common subquery.
* Grouping or filtering by a column derived in the CTE's result set.
* Writing recursive queries.

To declare a :py:class:`Select` query for use as a CTE, use
:py:meth:`~SelectQuery.cte` method, which wraps the query in a :py:class:`CTE`
object. To indicate that a :py:class:`CTE` should be included as part of a
query, use the :py:meth:`Query.with_cte` method, passing a list of CTE objects.

Simple Example
^^^^^^^^^^^^^^

For an example, let's say we have some data points that consist of a key and a
floating-point value. Let's define our model and populate some test data:

.. code-block:: python

    class Sample(Model):
        key = TextField()
        value = FloatField()

    data = (
        ('a', (1.25, 1.5, 1.75)),
        ('b', (2.1, 2.3, 2.5, 2.7, 2.9)),
        ('c', (3.5, 3.5)))

    # Populate data.
    for key, values in data:
        Sample.insert_many([(key, value) for value in values],
                           fields=[Sample.key, Sample.value]).execute()

Let's use a CTE to calculate, for each distinct key, which values were
above-average for that key.

.. code-block:: python

    # First we'll declare the query that will be used as a CTE. This query
    # simply determines the average value for each key.
    cte = (Sample
           .select(Sample.key, fn.AVG(Sample.value).alias('avg_value'))
           .group_by(Sample.key)
           .cte('key_avgs', columns=('key', 'avg_value')))

    # Now we'll query the sample table, using our CTE to find rows whose value
    # exceeds the average for the given key. We'll calculate how far above the
    # average the given sample's value is, as well.
    query = (Sample
             .select(Sample.key, Sample.value)
             .join(cte, on=(Sample.key == cte.c.key))
             .where(Sample.value > cte.c.avg_value)
             .order_by(Sample.value)
             .with_cte(cte))

We can iterate over the samples returned by the query to see which samples had
above-average values for their given group:

.. code-block:: pycon

    >>> for sample in query:
    ...     print(sample.key, sample.value)

    # 'a', 1.75
    # 'b', 2.7
    # 'b', 2.9

Complex Example
^^^^^^^^^^^^^^^

For a more complete example, let's consider the following query which uses
multiple CTEs to find per-product sales totals in only the top sales regions.
Our model looks like this:

.. code-block:: python

    class Order(Model):
        region = TextField()
        amount = FloatField()
        product = TextField()
        quantity = IntegerField()

Here is how the query might be written in SQL. This example can be found in
the `postgresql documentation <https://www.postgresql.org/docs/current/static/queries-with.html>`_.

.. code-block:: sql

    WITH regional_sales AS (
        SELECT region, SUM(amount) AS total_sales
        FROM orders
        GROUP BY region
      ), top_regions AS (
        SELECT region
        FROM regional_sales
        WHERE total_sales > (SELECT SUM(total_sales) / 10 FROM regional_sales)
      )
    SELECT region,
           product,
           SUM(quantity) AS product_units,
           SUM(amount) AS product_sales
    FROM orders
    WHERE region IN (SELECT region FROM top_regions)
    GROUP BY region, product;

With Peewee, we would write:

.. code-block:: python

    reg_sales = (Order
                 .select(Order.region,
                         fn.SUM(Order.amount).alias('total_sales'))
                 .group_by(Order.region)
                 .cte('regional_sales'))

    top_regions = (reg_sales
                   .select(reg_sales.c.region)
                   .where(reg_sales.c.total_sales > (
                       reg_sales.select(fn.SUM(reg_sales.c.total_sales) / 10)))
                   .cte('top_regions'))

    query = (Order
             .select(Order.region,
                     Order.product,
                     fn.SUM(Order.quantity).alias('product_units'),
                     fn.SUM(Order.amount).alias('product_sales'))
             .where(Order.region.in_(top_regions.select(top_regions.c.region)))
             .group_by(Order.region, Order.product)
             .with_cte(regional_sales, top_regions))

Recursive CTEs
^^^^^^^^^^^^^^

Peewee supports recursive CTEs. Recursive CTEs can be useful when, for example,
you have a tree data-structure represented by a parent-link foreign key.
Suppose, for example, that we have a hierarchy of categories for an online
bookstore. We wish to generate a table showing all categories and their
absolute depths, along with the path from the root to the category.

We'll assume the following model definition, in which each category has a
foreign-key to its immediate parent category:

.. code-block:: python

    class Category(Model):
        name = TextField()
        parent = ForeignKeyField('self', backref='children', null=True)

To list all categories along with their depth and parents, we can use a
recursive CTE:

.. code-block:: python

    # Define the base case of our recursive CTE. This will be categories that
    # have a null parent foreign-key.
    Base = Category.alias()
    level = Value(1).alias('level')
    path = Base.name.alias('path')
    base_case = (Base
                 .select(Base.id, Base.name, Base.parent, level, path)
                 .where(Base.parent.is_null())
                 .cte('base', recursive=True))

    # Define the recursive terms.
    RTerm = Category.alias()
    rlevel = (base_case.c.level + 1).alias('level')
    rpath = base_case.c.path.concat('->').concat(RTerm.name).alias('path')
    recursive = (RTerm
                 .select(RTerm.id, RTerm.name, RTerm.parent, rlevel, rpath)
                 .join(base_case, on=(RTerm.parent == base_case.c.id)))

    # The recursive CTE is created by taking the base case and UNION ALL with
    # the recursive term.
    cte = base_case.union_all(recursive)

    # We will now query from the CTE to get the categories, their levels,  and
    # their paths.
    query = (cte
             .select_from(cte.c.name, cte.c.level, cte.c.path)
             .order_by(cte.c.path))

    # We can now iterate over a list of all categories and print their names,
    # absolute levels, and path from root -> category.
    for category in query:
        print(category.name, category.level, category.path)

    # Example output:
    # root, 1, root
    # p1, 2, root->p1
    # c1-1, 3, root->p1->c1-1
    # c1-2, 3, root->p1->c1-2
    # p2, 2, root->p2
    # c2-1, 3, root->p2->c2-1

Foreign Keys and Joins
----------------------

This section has been moved into its own document: :ref:`relationships`.
