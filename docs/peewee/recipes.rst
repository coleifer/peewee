.. _recipes:

Recipes
=======

Collected patterns for common real-world problems. Each recipe assumes
familiarity with :ref:`querying`, :ref:`writing`, and :ref:`relationships`.

All examples use the following models:

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
       created_date = DateTimeField(default=datetime.datetime.now)


.. _optimistic-locking:

Optimistic Locking
------------------

*Optimistic locking* avoids holding a database lock across the read-modify-write
cycle by recording a version number on each row. On write, the update is
conditional on the version not having changed. If another process modified the
row in the meantime, the update matches zero rows and the conflict is detected
in application code.

This is a lighter-weight alternative to ``SELECT FOR UPDATE`` (Postgresql) or
``BEGIN IMMEDIATE`` (SQLite) when lock contention is expected to be low.

A reusable base class:

.. code-block:: python

   class ConflictDetectedException(Exception):
       pass

   class BaseVersionedModel(BaseModel):
       version = IntegerField(default=1, index=True)

       def save_optimistic(self):
           if not self.id:
               # This is a new record, so the default logic is to perform an
               # INSERT. Ideally your model would also have a unique
               # constraint that made it impossible for two INSERTs to happen
               # at the same time.
               return self.save()

           # Update any data that has changed and bump the version counter.
           field_data = dict(self.__data__)
           current_version = field_data.pop('version', 1)
           self._populate_unsaved_relations(field_data)
           field_data = self._prune_fields(field_data, self.dirty_fields)
           if not field_data:
               raise ValueError('No changes have been made.')

           ModelClass = type(self)
           field_data['version'] = ModelClass.version + 1  # Atomic increment.

           updated = (ModelClass
                      .update(**field_data)
                      .where(
                          (ModelClass.version == current_version) &
                          (ModelClass.id == self.id))
                      .execute())
           if updated == 0:
               # No rows were updated, indicating another process has saved
               # a new version.
               raise ConflictDetectedException()
           else:
               # Increment local version to match what is now in the db.
               self.version += 1
               return True

Usage:

.. code-block:: pycon

   class UserProfile(BaseVersionedModel):
       username = TextField(unique=True)
       bio = TextField(default='')

   >>> u = UserProfile(username='charlie')
   >>> u.save_optimistic()
   True

   >>> u.bio = 'Python developer'
   >>> u.save_optimistic()
   True
   >>> u.version
   2

   # Simulate a concurrent modification:
   >>> u2 = UserProfile.get(UserProfile.username == 'charlie')
   >>> u2.bio = 'Changed by another process'
   >>> u2.save_optimistic()
   True

   # The original instance's version is now stale:
   >>> u.bio = 'My update'
   >>> u.save_optimistic()
   ConflictDetectedException


Get-or-Create Safely
---------------------

:meth:`~Model.get_or_create` is convenient but has a small race window
between the SELECT and the INSERT when the row does not yet exist. Two
concurrent processes can both fail the SELECT and both attempt the INSERT,
causing one to fail with an ``IntegrityError``.

The safe pattern attempts the INSERT first and falls back to a GET on
``IntegrityError``:

.. code-block:: python

   def get_or_create_user(username):
       try:
           with db.atomic():
               return User.create(username=username), True
       except IntegrityError:
           return User.get(User.username == username), False

   user, created = get_or_create_user('charlie')

The ``db.atomic()`` wrapper is important: it ensures that the rollback on
``IntegrityError`` affects only this operation, not any surrounding transaction.


.. _top-item-per-group:

Top Item Per Group
------------------

These examples find the single most recent tweet for each user. See
:ref:`top-n-per-group` below for the generalized N-per-group problem.

The most portable approach uses a ``MAX()`` aggregate in a non-correlated
subquery, then joins back to the tweet table on both user and timestamp:

.. code-block:: python

   # When referencing a table multiple times, we'll call Model.alias() to create
   # a secondary reference to the table.
   TweetAlias = Tweet.alias()

   # Create a subquery that will calculate the maximum Tweet created_date for
   # each user.
   subquery = (TweetAlias
               .select(
                   TweetAlias.user,
                   fn.MAX(TweetAlias.created_date).alias('max_ts'))
               .group_by(TweetAlias.user)
               .alias('tweet_max'))

   # Query for tweets and join using the subquery to match the tweet's user
   # and created_date.
   query = (Tweet
            .select(Tweet, User)
            .join(User)
            .switch(Tweet)
            .join(subquery, on=(
                (Tweet.created_date == subquery.c.max_ts) &
                (Tweet.user == subquery.c.user_id))))

SQLite and MySQL permit a shorter form that groups by a subset of selected
columns:

.. code-block:: python

   query = (Tweet
            .select(Tweet, User)
            .join(User)
            .group_by(Tweet.user)
            .having(Tweet.created_date == fn.MAX(Tweet.created_date)))

Postgresql requires the standard subquery form above.

.. _top-n-per-group:

Top N Per Group
---------------

These examples describe several ways to query the top *N* items per group
reasonably efficiently. For a thorough discussion of various techniques, check
out my blog post `Querying the top N objects per group with Peewee ORM
<https://charlesleifer.com/blog/querying-the-top-n-objects-per-group-with-peewee-orm/>`_.

Window functions
^^^^^^^^^^^^^^^^

A ``RANK()`` window function is the cleanest solution. Rank tweets per user by
timestamp (newest first), then filter the outer query to the top N ranks:

.. code-block:: python

   TweetAlias = Tweet.alias()

   ranked = (TweetAlias
             .select(
                 TweetAlias.content,
                 User.username,
                 fn.RANK().over(
                     partition_by=[TweetAlias.user],
                     order_by=[TweetAlias.created_date.desc()]
                 ).alias('rnk'))
             .join(User, on=(TweetAlias.user == User.id))
             .alias('subq'))

   query = (Tweet
            .select(ranked.c.content, ranked.c.username)
            .from_(ranked)
            .where(ranked.c.rnk <= 3))

Postgresql - lateral joins
^^^^^^^^^^^^^^^^^^^^^^^^^^^

A ``LATERAL`` join executes a correlated subquery once per row of the driving
table. For each user, it selects the three most recent tweets.

The desired SQL is:

.. code-block:: sql

    SELECT * FROM
      (SELECT id, username FROM user) AS uq
       LEFT JOIN LATERAL
      (SELECT message, created_date
       FROM tweet
       WHERE (user_id = uq.id)
       ORDER BY created_date DESC LIMIT 3)
      AS pq ON true

To accomplish this with peewee is quite straightforward:

.. code-block:: python

    subq = (Tweet
            .select(Tweet.message, Tweet.created_date)
            .where(Tweet.user == User.id)
            .order_by(Tweet.created_date.desc())
            .limit(3))

    query = (User
             .select(User, subq.c.content, subq.c.created_date)
             .join(subq, JOIN.LEFT_LATERAL)
             .order_by(User.username, subq.c.created_date.desc()))

    # We queried from the "perspective" of user, so the rows are User instances
    # with the addition of a "content" and "created_date" attribute for each of
    # the (up-to) 3 most-recent tweets for each user.
    for row in query:
        print(row.username, row.content, row.created_date)

To implement an equivalent query from the "perspective" of the Tweet model, we
can instead write:

.. code-block:: python

    # subq is the same as the above example.
    subq = (Tweet
            .select(Tweet.message, Tweet.created_date)
            .where(Tweet.user == User.id)
            .order_by(Tweet.created_date.desc())
            .limit(3))

    query = (Tweet
             .select(User.username, subq.c.content, subq.c.created_date)
             .from_(User)
             .join(subq, JOIN.LEFT_LATERAL)
             .order_by(User.username, subq.c.created_date.desc()))

    # Each row is a "tweet" instance with an additional "username" attribute.
    # This will print the (up-to) 3 most-recent tweets from each user.
    for tweet in query:
        print(tweet.username, tweet.content, tweet.created_date)

Correlated subquery count
^^^^^^^^^^^^^^^^^^^^^^^^^

A correlated subquery that counts tweets newer than the current row can also be
used. Rows where fewer than N newer tweets exist are in the top N:

.. code-block:: python

   TweetAlias = Tweet.alias()

   # Create a correlated subquery that calculates the number of
   # tweets with a higher (newer) timestamp than the tweet we're
   # looking at in the outer query.
   subquery = (TweetAlias
               .select(fn.COUNT(TweetAlias.id))
               .where(
                   (TweetAlias.created_date >= Tweet.created_date) &
                   (TweetAlias.user == Tweet.user)))

   # Wrap the subquery and filter on the count.
   query = (Tweet
            .select(Tweet, User)
            .join(User)
            .where(subquery <= 3))

SQLite and MySQL - self-join
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

An alternative: self-join and count newer tweets in the HAVING clause:

.. code-block:: python

   TweetAlias = Tweet.alias()

   query = (Tweet
            .select(Tweet.id, Tweet.content, Tweet.user, User.username)
            .join_from(Tweet, User)
            .join_from(Tweet, TweetAlias, on=(
                (TweetAlias.user == Tweet.user) &
                (TweetAlias.created_date >= Tweet.created_date)))
            .group_by(Tweet.id, Tweet.content, Tweet.user, User.username)
            .having(fn.COUNT(Tweet.id) <= 3))

The last example uses a ``LIMIT`` clause in a correlated subquery.

.. code-block:: python

    TweetAlias = Tweet.alias()

    # The subquery here will calculate, for the user who created the
    # tweet in the outer loop, the three newest tweets. The expression
    # will evaluate to `True` if the outer-loop tweet is in the set of
    # tweets represented by the inner query.
    query = (Tweet
             .select(Tweet, User)
             .join(User)
             .where(Tweet.id << (
                 TweetAlias
                 .select(TweetAlias.id)
                 .where(TweetAlias.user == Tweet.user)
                 .order_by(TweetAlias.created_date.desc())
                 .limit(3))))

For a thorough benchmark comparison of these approaches, see the blog post
`Querying the top N objects per group with Peewee ORM
<https://charlesleifer.com/blog/querying-the-top-n-objects-per-group-with-peewee-orm/>`_.


Bulk-Loading with Explicit Primary Keys
-----------------------------------------

When loading relational data from an external source where primary keys are
already assigned, use :meth:`~Model.insert_many` with the ``id`` field
included. This avoids the ``auto_increment`` workaround that was common in
older Peewee versions:

.. code-block:: python

   data = [(1, 'alice'), (2, 'bob'), (3, 'carol')]
   fields = [User.id, User.username]

   with db.atomic():
       User.insert_many(data, fields=fields).execute()

Because ``insert_many`` never reads rows back, there is no confusion between
INSERT and UPDATE paths.


Custom SQLite Functions
-----------------------

SQLite can be extended with Python functions that are callable from SQL. This
is useful for operations SQLite does not natively support.

Registering a function with the ``@db.func()`` decorator makes it available
immediately after the connection is opened:

.. code-block:: python

   from hashlib import sha256
   import os

   db = SqliteDatabase('my_app.db')

   def _hash_password(salt, password):
       return sha256((salt + password).encode()).hexdigest()

   @db.func()
   def make_password(raw_password):
       salt = os.urandom(8).hex()
       return salt + '$' + _hash_password(salt, raw_password)

   @db.func()
   def check_password(raw_password, stored):
       salt, hsh = stored.split('$', 1)
       return hsh == _hash_password(salt, raw_password)

Store a hashed password:

.. code-block:: python

   User.insert(username='charlie',
               password=fn.make_password('s3cr3t')).execute()

Verify a password at login:

.. code-block:: python

   def login(username, raw_password):
       try:
           return (User
                   .select()
                   .where(
                       (User.username == username) &
                       (fn.check_password(raw_password, User.password) == True))
                   .get())
       except User.DoesNotExist:
           return None

.. seealso::
   :meth:`SqliteDatabase.func`,
   :meth:`SqliteDatabase.aggregate`,
   :meth:`SqliteDatabase.window_function`.


Date Arithmetic Across Databases
----------------------------------

Each database implements date arithmetic differently. This section shows how to
express "next occurrence of a scheduled task" - defined as
``last_run + interval_seconds`` - for each backend.

The schema:

.. code-block:: python

   class Schedule(BaseModel):
       interval = IntegerField()   # Repeat every N seconds.

   class Task(BaseModel):
       schedule = ForeignKeyField(Schedule, backref='tasks')
       command  = TextField()
       last_run = DateTimeField()

We want: tasks where ``now >= last_run + interval``.

Our desired code would look like:

.. code-block:: python

    next_occurrence = something  # ??? how do we define this ???

    # We can express the current time as a Python datetime value, or we could
    # alternatively use the appropriate SQL function/name.
    now = Value(datetime.datetime.now())  # Or SQL('current_timestamp'), e.g.

    query = (Task
             .select(Task, Schedule)
             .join(Schedule)
             .where(now >= next_occurrence))

**Postgresql** - multiply a typed interval:

.. code-block:: python

   one_second = SQL("INTERVAL '1 second'")
   next_run = Task.last_run + (Schedule.interval * one_second)

   now = Value(datetime.datetime.now())
   tasks_due = (Task
                .select(Task, Schedule)
                .join(Schedule)
                .where(now >= next_run))

**MySQL** - use ``DATE_ADD`` with a dynamic INTERVAL expression:

.. code-block:: python

   from peewee import NodeList

   interval = NodeList((SQL('INTERVAL'), Schedule.interval, SQL('SECOND')))
   next_run = fn.DATE_ADD(Task.last_run, interval)

   now = Value(datetime.datetime.now())
   tasks_due = (Task
                .select(Task, Schedule)
                .join(Schedule)
                .where(now >= next_run))

**SQLite** - convert to Unix timestamp, add seconds, convert back:

.. code-block:: python

   next_ts = fn.strftime('%s', Task.last_run) + Schedule.interval
   next_run = fn.datetime(next_ts, 'unixepoch')

   now = Value(datetime.datetime.now())
   tasks_due = (Task
                .select(Task, Schedule)
                .join(Schedule)
                .where(now >= next_run))
