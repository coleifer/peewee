.. _writing:

Writing Data
============

This document covers INSERT, UPDATE, and DELETE queries. Reading data is
covered in :ref:`querying`.

All examples use the canonical schema from :ref:`models`:

.. code-block:: python

   import datetime
   from peewee import *

   db = SqliteDatabase(':memory:')

   class BaseModel(Model):
       class Meta:
           database = db

   class User(BaseModel):
       username = TextField(unique=True)

   class Tweet(BaseModel):
       user = ForeignKeyField(User, backref='tweets')
       content = TextField()
       timestamp = DateTimeField(default=datetime.datetime.now)
       is_published = BooleanField(default=True)

Methods which will be discussed:

+-----------------+-----------------------------------------------------------+
| Query           | Methods                                                   |
+=================+===========================================================+
| INSERT          | * :meth:`Model.create`                                    |
|                 | * :meth:`Model.insert`                                    |
|                 | * :meth:`Model.insert_many`                               |
|                 | * :meth:`Model.insert_from`                               |
|                 | * :meth:`Model.replace` (Postgres unsupported)            |
|                 | * :meth:`Model.replace_many` (Postgres unsupported)       |
+-----------------+-----------------------------------------------------------+
| UPDATE          | * :meth:`Model.save`                                      |
|                 | * :meth:`Model.update`                                    |
+-----------------+-----------------------------------------------------------+
| DELETE          | * :meth:`Model.delete_instance`                           |
|                 | * :meth:`Model.delete`                                    |
+-----------------+-----------------------------------------------------------+

.. seealso:: :ref:`Extensive library of SQL / Peewee examples <query-library>`

.. _inserting-records:

Inserting Records
-----------------

Creating a single row
^^^^^^^^^^^^^^^^^^^^^

:meth:`~Model.create` inserts a row and returns the saved model instance:

.. code-block:: pycon

   >>> charlie = User.create(username='charlie')
   >>> charlie.id
   1

This will INSERT a new row into the database. The primary key will
automatically be retrieved and stored on the model instance.

Alternatively, instantiate the model and call :meth:`~Model.save`. The
first call to ``save()`` on a new instance performs an INSERT:

.. code-block:: pycon

   >>> user = User(username='huey')
   >>> user.save()
   1  # Returns number of rows modified.
   >>> user.id
   2

After the first save, the model instance holds its primary key. Any subsequent
call to ``save()`` performs an UPDATE instead:

.. code-block:: pycon

   >>> user.username = 'Huey'
   >>> user.save()
   1  # Returns number of rows updated.

For a foreign key field, pass either the related model instance or its raw
primary key value:

.. code-block:: python

   Tweet.create(user=huey, content='Hello!')
   Tweet.create(user=2, content='Also valid.')

To insert without constructing a model instance, use :meth:`~Model.insert`.
It returns the primary key of the new row:

.. code-block:: pycon

   >>> User.insert(username='mickey').execute()
   3

.. _bulk-inserts:

Bulk Inserts
------------

Calling :meth:`Model.create` or :meth:`Model.save` in a loop should be avoided:

.. code-block:: python

   data = [
       {'username': 'alice'},
       {'username': 'bob'},
       {'username': 'carol'},
   ]

   for data_dict in data:
       User.create(**data_dict)

The above is slow:

1. **Does not wrap the loop in a transaction.** Result is each
   :meth:`~Model.create` happens in its own :ref:`transaction <transactions>`.
2. **Python interpreter** is getting in the way, and each :class:`InsertQuery`
   must be generated and parsed into SQL.
3. **Large amount of data** (in terms of raw bytes of SQL) may be sent to the
   database to parse.
4. **Retrieving the last insert id**, which may not be necessary.

You can get a significant speedup by simply wrapping this in a transaction with
:meth:`~Database.atomic`:

.. code-block:: python
   :emphasize-lines: 1

   with db.atomic():
       for data_dict in data:
           User.create(**data_dict)

The fastest way to insert many rows is :meth:`~Model.insert_many`. It
accepts a list of dicts or tuples and emits a single multi-row INSERT:

.. code-block:: python

   data = [
       {'username': 'alice'},
       {'username': 'bob'},
       {'username': 'carol'},
   ]
   User.insert_many(data).execute()

   # Tuples require an explicit field list:
   data = [('alice',), ('bob',), ('carol',)]
   User.insert_many(data, fields=[User.username]).execute()

Optionally wrap the bulk insert in a transaction:

.. code-block:: python

   with db.atomic():
       User.insert_many(data, fields=fields).execute()

Insert queries support :meth:`~WriteQuery.returning` with Postgresql and SQLite
to obtain the inserted rows:

.. code-block:: python

   query = (User
            .insert_many([{'username': 'alice'}, {'username': 'bob'}])
            .returning(User))
   for user in query:
       print(f'Added {user.username} with id = {user.id}')

Batching large data sets
^^^^^^^^^^^^^^^^^^^^^^^^

Depending on the number of rows in your data source, you may need to break it
up into chunks. SQLite in particular may have a `limit of 32766 <https://www.sqlite.org/limits.html#max_variable_number>`_
variables-per-query (batch size would then be 32766 // row length).

You can write a loop to batch your data into chunks. It is **strongly recommended**
you use a :ref:`transaction <transactions>`:

.. code-block:: python

   from peewee import chunked

   with db.atomic():
       for batch in chunked(data, 100):
           User.insert_many(batch).execute()

:func:`chunked` works on any iterable, including generators.

Bulk-creating model instances
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:meth:`~Model.bulk_create` accepts a list of unsaved model instances and
inserts them efficiently. Pass ``batch_size`` to avoid hitting database limits:

.. code-block:: python

   users = [User(username=f'user_{i}') for i in range(1000)]
   with db.atomic():
       User.bulk_create(users, batch_size=100)

.. note::
   If you are using Postgresql (which supports the ``RETURNING`` clause), then
   the previously-unsaved model instances will have their new primary key
   values automatically populated. Other backends will not.

Loading from another table
^^^^^^^^^^^^^^^^^^^^^^^^^^

:meth:`~Model.insert_from` generates an ``INSERT INTO ... SELECT`` query,
copying rows from one table into another without round-tripping data through
Python:

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

.. _updating-records:

Updating Records
----------------

Updating a model instance
^^^^^^^^^^^^^^^^^^^^^^^^^^

Modify attributes on a fetched instance and call :meth:`~Model.save` to
persist the changes:

.. code-block:: python

   charlie = User.get(User.username == 'charlie')
   charlie.username = 'charlie_admin'
   charlie.save()   # Issues UPDATE WHERE id = charlie.id

By default, ``save()`` re-saves all fields. To only emit changed fields, set
``only_save_dirty = True`` in the model's ``Meta``, or pass only the fields
you want to update:

.. code-block:: python

   charlie.username = 'charlie_v2'
   charlie.save(only=[User.username])

.. note::
   If a model instance does not have a primary key, the first call to
   :meth:`~Model.save` will perform an INSERT query.

   Once a model instance has a primary key, subsequent calls to :meth:`~Model.save`
   result in an *UPDATE*.

Updating multiple rows
^^^^^^^^^^^^^^^^^^^^^^

:meth:`~Model.update` issues a single UPDATE that affects every row
matching the WHERE clause:

.. code-block:: python

   # Publish all unpublished tweets older than one week.
   one_week_ago = datetime.datetime.now() - datetime.timedelta(days=7)

   nrows = (Tweet
            .update(is_published=True)
            .where(
                (Tweet.is_published == False) &
                (Tweet.timestamp < one_week_ago))
            .execute())

The return value is the number of rows affected.

Update queries support :meth:`~WriteQuery.returning` with Postgresql and SQLite
to obtain the updated rows:

.. code-block:: python

   query = (User
            .update(spam=True)
            .where(User.username.contains('billing'))
            .returning(User))
   for user in query:
       print(f'Marked {user.username} as spam')

Because UPDATE queries do not support joins, we can use subqueries to update
rows based on values in related tables. For example, unpublish all tweets by
users with ``'billing'`` in their username:

.. code-block:: python

   spammers = User.select().where(User.username.contains('billing'))

   (Tweet
    .update(is_published=False)
    .where(Tweet.user.in_(spammers))
    .execute())

Atomic updates
^^^^^^^^^^^^^^

Use column expressions in ``update()`` to modify values without a read-modify-write
cycle. Performing updates atomically prevents race-conditions:

.. code-block:: python

   # WRONG: reads each row into Python, increments, then saves.
   # Vulnerable to race conditions; slow on many rows.
   for stat in Stat.select().where(Stat.url == url):
       stat.counter += 1
       stat.save()

   # CORRECT: single UPDATE statement, atomic at the database level.
   Stat.update(counter=Stat.counter + 1).where(Stat.url == url).execute()

Any SQL expression is valid on the right-hand side:

.. code-block:: python

   # Give every employee a 10% salary bonus added to their existing bonus.
   Employee.update(bonus=Employee.bonus + (Employee.salary * 0.10)).execute()

   # Denormalize a count column from a subquery.
   tweet_count = (Tweet
                  .select(fn.COUNT(Tweet.id))
                  .where(Tweet.user == User.id))
   User.update(num_tweets=tweet_count).execute()

Bulk-updating model instances
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When you have a list of modified model instances and want to update specific
fields across all of them in one query, use :meth:`~Model.bulk_update`:

.. code-block:: python

   u1, u2, u3 = User.select().limit(3)
   u1.username = 'u1-new'
   u2.username = 'u2-new'
   u3.username = 'u3-new'

   User.bulk_update([u1, u2, u3], fields=[User.username])

This emits a single UPDATE using a SQL ``CASE`` expression. For large lists,
specify a ``batch_size`` and wrap in a transaction:

.. code-block:: python

   with db.atomic():
       User.bulk_update(users, fields=[User.username], batch_size=50)

.. note::
   ``bulk_update`` may be slower than a direct UPDATE query when the list is
   very large, because the generated ``CASE`` expression grows proportionally.
   For updates that can be expressed as a single WHERE clause, the direct
   :meth:`~Model.update` approach is faster.

.. _upsert:

Upsert
------

An *upsert* (INSERT or UPDATE) inserts a new row, or if a unique constraint
would be violated, updates the existing row instead.

Peewee provides two complementary approaches.

``on_conflict_replace`` - SQLite and MySQL
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

SQLite and MySQL support a ``REPLACE`` query, which will replace the row in the
event of a conflict:

.. code-block:: python

   class User(BaseModel):
       username = TextField(unique=True)
       last_login = DateTimeField(null=True)

   # Insert, or replace the entire existing row.
   User.replace(username='huey', last_login=datetime.datetime.now()).execute()

   # Equivalent using insert():
   (User
    .insert(username='huey', last_login=datetime.datetime.now())
    .on_conflict_replace()
    .execute())

.. warning::
   ``replace`` deletes and re-inserts, which changes the primary key. Use
   ``on_conflict`` (below) when the primary key must be preserved, or when
   only some columns should be updated.

``on_conflict`` - all backends
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :meth:`~Insert.on_conflict` method is much more powerful.

.. code-block:: python

   class User(BaseModel):
       username = TextField(unique=True)
       last_login = DateTimeField(null=True)
       login_count = IntegerField(default=0)

   now = datetime.datetime.now()

   (User
    .insert(username='huey', last_login=now, login_count=1)
    .on_conflict(
        # Postgresql and SQLite require identifying the conflicting constraint.
        # MySQL does not need this.
        conflict_target=[User.username],

        # Columns whose values should come from the incoming row:
        preserve=[User.last_login],

        # Columns to update using an expression:
        update={User.login_count: User.login_count + 1})
    .execute())

Calling this query repeatedly will increment ``login_count`` atomically and
update ``last_login`` on each call, without creating duplicate rows.

The ``EXCLUDED`` namespace references the values that would have been inserted
if the constraint had not fired. This allows conditional updates:

.. code-block:: python

   class KV(BaseModel):
       key = TextField(unique=True)
       value = IntegerField()

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

There are several important concepts to understand when using ``ON CONFLICT``:

* ``conflict_target=``: which column(s) have the UNIQUE constraint. For a user
  table, this might be the user's email (SQLite and Postgresql only).
* ``preserve=``: if a conflict occurs, this parameter is used to indicate which
  values from the **new** data we wish to update.
* ``update=``: if a conflict occurs, this is a mapping of data to apply to the
  pre-existing row.
* ``EXCLUDED``: this "magic" namespace allows you to reference the new data
  that would have been inserted if the constraint hadn't failed.

Full example:

.. code-block:: python

   class User(Model):
       email = CharField(unique=True)  # Unique identifier for user.
       last_login = DateTimeField()
       login_count = IntegerField(default=0)
       ip_log = TextField(default='')


   # Demonstrates the above 4 concepts.
   def login(email, ip):
       rowid = (User
                .insert({User.email: email,
                         User.last_login: datetime.now(),
                         User.login_count: 1,
                         User.ip_log: ip})
                .on_conflict(
                    # If the INSERT fails due to a constraint violation on the
                    # user email, then perform an UPDATE instead.
                    conflict_target=[User.email],

                    # Set the "last_login" to the value we would have inserted
                    # (our call to datetime.now()).
                    preserve=[User.last_login],

                    # Increment the user's login count and prepend the new IP
                    # to the user's ip history.
                    update={User.login_count: User.login_count + 1,
                            User.ip_log: fn.CONCAT(EXCLUDED.ip_log, ',', User.ip_log)})
                .execute())

       return rowid

   # This will insert the initial row, returning the new row id (1).
   print(login('test@example.com', '127.1'))

   # Because test@example.com exists, this will trigger the UPSERT. The row id
   # from above is returned again (1).
   print(login('test@example.com', '127.2'))

   u = User.get()
   print(u.login_count, u.ip_log)

   # Prints "2 127.2,127.1"

.. seealso:: :meth:`Insert.on_conflict` and :class:`OnConflict`.

``on_conflict_ignore``
^^^^^^^^^^^^^^^^^^^^^^

Insert the row, and silently do nothing if a constraint would be violated:

.. code-block:: python

   # Insert if username does not exist; ignore if it does.
   User.insert(username='huey').on_conflict_ignore().execute()

Supported by SQLite, MySQL, and Postgresql.

.. _deleting-records:

Deleting Records
----------------

Delete a single fetched instance with :meth:`~Model.delete_instance`:

.. code-block:: python

   tweet = Tweet.get_by_id(42)
   tweet.delete_instance()   # Returns number of rows deleted.

To delete a row along with all dependent rows (rows in other tables that
reference it via foreign key), pass ``recursive=True``:

.. code-block:: python

   # Deletes the user and all their tweets, favorites, etc.
   with db.atomic():
       user.delete_instance(recursive=True)

.. warning::
   ``recursive=True`` works by querying for dependent rows and deleting them
   first - it does not rely on ``ON DELETE CASCADE``. For large graphs of
   related data, this can be slow. Be sure to wrap calls in a
   :ref:`transaction <transactions>` and consider using database-level cascade
   constraints on the foreign keys.

To delete an arbitrary set of rows without fetching them:

.. code-block:: python

   # Delete all unpublished tweets older than 30 days.
   cutoff = datetime.datetime.now() - datetime.timedelta(days=30)
   nrows = (Tweet
            .delete()
            .where(
                (Tweet.is_published == False) &
                (Tweet.timestamp < cutoff))
            .execute())

Delete queries support :meth:`~WriteQuery.returning` with Postgresql and SQLite
to obtain the deleted rows:

.. code-block:: python

   query = (User
            .delete()
            .where(User.username.contains('billing'))
            .returning(User))
   for user in query:
       print(f'Deleted: {user.username}')

Because DELETE queries do not support joins, we can use subqueries to delete
rows based on values in related tables. For example, delete all tweets by users
with ``'billing'`` in their username:

.. code-block:: python

   spammers = User.select().where(User.username.contains('billing'))

   (Tweet
    .delete()
    .where(Tweet.user.in_(spammers))
    .execute())

.. seealso::
   * :meth:`Model.delete_instance`
   * :meth:`Model.delete`
   * :class:`DeleteQuery`

.. _returning-clause:

Returning Clause
----------------

:class:`PostgresqlDatabase` and :class:`SqliteDatabase` (3.35.0+) support a
``RETURNING`` clause on ``UPDATE``, ``INSERT`` and ``DELETE`` queries.
Specifying a ``RETURNING`` clause allows you to iterate over the rows accessed
by the query.

By default, the return values upon execution of the different queries are:

* ``INSERT`` - auto-incrementing primary key value of the newly-inserted row.
  When not using an auto-incrementing primary key, Postgres will return the new
  row's primary key, but SQLite and MySQL will not.
* ``UPDATE`` - number of rows modified
* ``DELETE`` - number of rows deleted

When a returning clause is used the return value upon executing a query will be
an iterable cursor object, providing access to data that was inserted, updated
or deleted by the query.

For example, let's say you have an :class:`Update` that deactivates all
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

   query = (User
            .delete()
            .where(User.is_spam == True)
            .returning(User.id))
   for user in query.execute():
       print(f'Deleted spam user id: {user.id}')

The ``RETURNING`` clause is available on:

* :class:`Insert`
* :class:`Update`
* :class:`Delete`

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

By default the cursor will return :class:`Model` instances, but you can
specify a different row type:

.. code-block:: python

   data = [{'name': 'charlie'}, {'name': 'huey'}, {'name': 'mickey'}]
   query = (User
            .insert_many(data)
            .returning(User.id, User.username)
            .dicts())

   for new_user in query.execute():
       print('Added user "%s", id=%s' % (new_user['username'], new_user['id']))

Just as with :class:`Select` queries, you can specify various :ref:`result row types <row-types>`.
