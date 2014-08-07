This section will cover the basic CRUD operations commonly performed on a relational database:

* :py:meth:`Model.create`, for executing *INSERT* queries.
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
    the :ref:`bulk_inserts` recipe section for more information.

.. _bulk_inserts:

Bulk inserts
^^^^^^^^^^^^

There are a couple of ways you can load lots of data quickly. The naive approach is to simply call :py:meth:`Model.create` in a loop:

.. code-block:: python

    data_source = [
        {'field1': 'val1-1', 'field2': 'val1-2'},
        {'field1': 'val2-1', 'field2': 'val2-2'},
        # ...
    ]

    for data_dict in data_source:
        Model.create(**data_dict)

The above approach is slow for a couple of reasons:

1. If you are using autocommit (the default), then each call to :py:meth:`~Model.create` happens in its own transaction. That is going to be really slow!
2. There is a decent amount of Python logic getting in your way, and each :py:class:`InsertQuery` must be generated and parsed into SQL.
3. That's a lot of data (in terms of raw bytes of SQL) you are sending to your database to parse.
4. We are retrieving the *last insert id*, which causes an additional query to be executed in some cases.

You can get a **very significant speedup** by simply wrapping this in a :py:meth:`~Database.transaction`.

.. code-block:: python

    # This is much faster.
    with db.transaction():
        for data_dict in data_source:
            Model.create(**data_dict)

The above code still suffers from points 2, 3 and 4. We can get another big boost by calling :py:meth:`~Model.insert_many`. This method accepts a list of dictionaries to insert.

.. code-block:: python

    # Fastest.
    with db.transaction():
        Model.insert_many(data_source).execute()

Depending on the number of rows in your data source, you may need to break it up into chunks:

.. code-block:: python

    # Insert rows 1000 at a time.
    with db.transaction():
        for idx in range(0, len(data_source), 1000):
            Model.insert_many(data_source[idx:idx+1000]).execute()

If the data you would like to bulk load is stored in another table, you can also create *INSERT* queries whose source is a *SELECT* query. Use the :py:meth:`Model.insert_from` method:

.. code-block:: python

    query = (TweetArchive
             .insert_from(
                 fields=[Tweet.user, Tweet.message],
                 query=Tweet.select(Tweet.user, Tweet.message))
             .execute())


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
    >>> query.execute()  # Returns the number of rows that were updated.
    4

For more information, see the documentation on :py:meth:`Model.update` and :py:class:`UpdateQuery`.

.. note::
    If you would like more information on performing atomic updates (such as
    incrementing the value of a column), check out the :ref:`atomic update <atomic_updates>`
    recipes.

.. _atomic_updates:

Atomic updates
^^^^^^^^^^^^^^

Peewee allows you to perform atomic updates. Let's suppose we need to update some counters. The naive approach would be to write something like this:

.. code-block:: pycon

    >>> for stat in Stat.select().where(Stat.url == request.url):
    ...     stat.counter += 1
    ...     stat.save()

**Do not do this!** Not only is this slow, but it is also vulnerable to race conditions if multiple processes are updating the counter at the same time.

Instead, you can update the counters atomically using :py:meth:`~Model.update`:

.. code-block:: pycon

    >>> query = Stat.update(counter=Stat.counter + 1).where(Stat.url == request.url)
    >>> query.update()

You can make these update statements as complex as you like. Let's give all our employees a bonus equal to their previous bonus plus 10% of their salary:

.. code-block:: pycon

    >>> query = Employee.update(bonus=(Employee.bonus + (Employee.salary * .1)))
    >>> query.execute()  # Give everyone a bonus!

We can even use a subquery to update the value of a column. Suppose we had a denormalized column on the ``User`` model that stored the number of tweets a user had made, and we updated this value periodically. Here is how you might write such a query:

.. code-block:: pycon

    >>> subquery = Tweet.select(fn.COUNT(Tweet.id)).where(Tweet.user == User.id)
    >>> update = User.update(num_tweets=subquery)
    >>> update.execute()

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

Get or create
^^^^^^^^^^^^^

While peewee has a :py:meth:`~Model.get_or_create` method, this should really not be used outside of tests as it is vulnerable to a race condition. The proper way to perform a *get or create* with peewee is to rely on the database to enforce a constraint.

Let's say we wish to implement registering a new user account using the :ref:`example User model <user_and_tweet_models>`. The *User* model has a *unique* constraint on the username field, so we will rely on the database's integrity guarantees to ensure we don't end up with duplicate usernames:

.. code-block:: python

    try:
        with db.transaction():
            user = User.create(username=username)
        return 'Success'
    except peewee.IntegrityError:
        return 'Failure: %s is already in use' % username
