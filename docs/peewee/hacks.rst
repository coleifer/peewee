.. _hacks:

Hacks
=====

Collected hacks using peewee. Have a cool hack you'd like to share? Open `an issue on GitHub <https://github.com/coleifer/peewee/issues/new>`_ or `contact me <https://charlesleifer.com/contact/>`_.

.. _optimistic_locking:

Optimistic Locking
------------------

Optimistic locking is useful in situations where you might ordinarily use a
*SELECT FOR UPDATE* (or in SQLite, *BEGIN IMMEDIATE*). For example, you might
fetch a user record from the database, make some modifications, then save the
modified user record. Typically this scenario would require us to lock the user
record for the duration of the transaction, from the moment we select it, to
the moment we save our changes.

In optimistic locking, on the other hand, we do *not* acquire any lock and
instead rely on an internal *version* column in the row we're modifying. At
read time, we see what version the row is currently at, and on save, we ensure
that the update takes place only if the version is the same as the one we
initially read. If the version is higher, then some other process must have
snuck in and changed the row -- to save our modified version could result in
the loss of important changes.

It's quite simple to implement optimistic locking in Peewee, here is a base
class that you can use as a starting point:

.. code-block:: python

    from peewee import *

    class ConflictDetectedException(Exception): pass

    class BaseVersionedModel(Model):
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

            query = ModelClass.update(**field_data).where(
                (ModelClass.version == current_version) &
                (ModelClass.id == self.id))
            if query.execute() == 0:
                # No rows were updated, indicating another process has saved
                # a new version. How you handle this situation is up to you,
                # but for simplicity I'm just raising an exception.
                raise ConflictDetectedException()
            else:
                # Increment local version to match what is now in the db.
                self.version += 1
                return True

Here's an example of how this works. Let's assume we have the following model
definition. Note that there's a unique constraint on the username -- this is
important as it provides a way to prevent double-inserts.

.. code-block:: python

    class User(BaseVersionedModel):
        username = CharField(unique=True)
        favorite_animal = CharField()

Example:

.. code-block:: pycon

    >>> u = User(username='charlie', favorite_animal='cat')
    >>> u.save_optimistic()
    True

    >>> u.version
    1

    >>> u.save_optimistic()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "x.py", line 18, in save_optimistic
        raise ValueError('No changes have been made.')
    ValueError: No changes have been made.

    >>> u.favorite_animal = 'kitten'
    >>> u.save_optimistic()
    True

    # Simulate a separate thread coming in and updating the model.
    >>> u2 = User.get(User.username == 'charlie')
    >>> u2.favorite_animal = 'macaw'
    >>> u2.save_optimistic()
    True

    # Now, attempt to change and re-save the original instance:
    >>> u.favorite_animal = 'little parrot'
    >>> u.save_optimistic()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "x.py", line 30, in save_optimistic
        raise ConflictDetectedException()
    ConflictDetectedException: current version is out of sync

.. _top_item_per_group:

Top object per group
--------------------

These examples describe several ways to query the single top item per group. For a thorough discuss of various techniques, check out my blog post `Querying the top item by group with Peewee ORM <https://charlesleifer.com/blog/techniques-for-querying-lists-of-objects-and-determining-the-top-related-item/>`_. If you are interested in the more general problem of querying the top *N* items, see the section below :ref:`top_n_per_group`.

In these examples we will use the *User* and *Tweet* models to find each user and their most-recent tweet.

The most efficient method I found in my testing uses the ``MAX()`` aggregate function.

We will perform the aggregation in a non-correlated subquery, so we can be confident this method will be performant. The idea is that we will select the posts, grouped by their author, whose timestamp is equal to the max observed timestamp for that user.

.. code-block:: python

    # When referencing a table multiple times, we'll call Model.alias() to create
    # a secondary reference to the table.
    TweetAlias = Tweet.alias()

    # Create a subquery that will calculate the maximum Tweet created_date for each
    # user.
    subquery = (TweetAlias
                .select(
                    TweetAlias.user,
                    fn.MAX(TweetAlias.created_date).alias('max_ts'))
                .group_by(TweetAlias.user)
                .alias('tweet_max_subquery'))

    # Query for tweets and join using the subquery to match the tweet's user
    # and created_date.
    query = (Tweet
             .select(Tweet, User)
             .join(User)
             .switch(Tweet)
             .join(subquery, on=(
                 (Tweet.created_date == subquery.c.max_ts) &
                 (Tweet.user == subquery.c.user_id))))

SQLite and MySQL are a bit more lax and permit grouping by a subset of the columns that are selected. This means we can do away with the subquery and express it quite concisely:

.. code-block:: python

    query = (Tweet
             .select(Tweet, User)
             .join(User)
             .group_by(Tweet.user)
             .having(Tweet.created_date == fn.MAX(Tweet.created_date)))

.. _top_n_per_group:

Top N objects per group
-----------------------

These examples describe several ways to query the top *N* items per group reasonably efficiently. For a thorough discussion of various techniques, check out my blog post `Querying the top N objects per group with Peewee ORM <https://charlesleifer.com/blog/querying-the-top-n-objects-per-group-with-peewee-orm/>`_.

In these examples we will use the *User* and *Tweet* models to find each user and their three most-recent tweets.

Postgres lateral joins
^^^^^^^^^^^^^^^^^^^^^^

`Lateral joins <http://blog.heapanalytics.com/postgresqls-powerful-new-join-type-lateral/>`_ are a neat Postgres feature that allow reasonably efficient correlated subqueries. They are often described as SQL ``for each`` loops.

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


Window functions
^^^^^^^^^^^^^^^^

`Window functions <http://www.postgresql.org/docs/9.1/static/tutorial-window.html>`_, which are :ref:`supported by peewee <window-functions>`, provide scalable, efficient performance.

The desired SQL is:

.. code-block:: sql

    SELECT subq.message, subq.username
    FROM (
        SELECT
            t2.message,
            t3.username,
            RANK() OVER (
                PARTITION BY t2.user_id
                ORDER BY t2.created_date DESC
            ) AS rnk
        FROM tweet AS t2
        INNER JOIN user AS t3 ON (t2.user_id = t3.id)
    ) AS subq
    WHERE (subq.rnk <= 3)

To accomplish this with peewee, we will wrap the ranked Tweets in an outer query that performs the filtering.

.. code-block:: python

    TweetAlias = Tweet.alias()

    # The subquery will select the relevant data from the Tweet and
    # User table, as well as ranking the tweets by user from newest
    # to oldest.
    subquery = (TweetAlias
                .select(
                    TweetAlias.message,
                    User.username,
                    fn.RANK().over(
                        partition_by=[TweetAlias.user],
                        order_by=[TweetAlias.created_date.desc()]).alias('rnk'))
                .join(User, on=(TweetAlias.user == User.id))
                .alias('subq'))

    # Since we can't filter on the rank, we are wrapping it in a query
    # and performing the filtering in the outer query.
    query = (Tweet
             .select(subquery.c.message, subquery.c.username)
             .from_(subquery)
             .where(subquery.c.rnk <= 3))

Other methods
^^^^^^^^^^^^^

If you're not using Postgres, then unfortunately you're left with options that exhibit less-than-ideal performance. For a more complete overview of common methods, check out `this blog post <https://charlesleifer.com/blog/querying-the-top-n-objects-per-group-with-peewee-orm/>`_. Below I will summarize the approaches and the corresponding SQL.

Using ``COUNT``, we can get all tweets where there exist less than *N* tweets with more recent timestamps:

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

We can achieve similar results by doing a self-join and performing the filtering in the ``HAVING`` clause:

.. code-block:: python

    TweetAlias = Tweet.alias()

    # Use a self-join and join predicates to count the number of
    # newer tweets.
    query = (Tweet
             .select(Tweet.id, Tweet.message, Tweet.user, User.username)
             .join(User)
             .switch(Tweet)
             .join(TweetAlias, on=(
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


Writing custom functions with SQLite
------------------------------------

SQLite is very easy to extend with custom functions written in Python, that are then callable from your SQL statements. By using the :py:class:`SqliteExtDatabase` and the :py:meth:`~SqliteExtDatabase.func` decorator, you can very easily define your own functions.

Here is an example function that generates a hashed version of a user-supplied password. We can also use this to implement ``login`` functionality for matching a user and password.

.. code-block:: python

    from hashlib import sha1
    from random import random
    from playhouse.sqlite_ext import SqliteExtDatabase

    db = SqliteExtDatabase('my-blog.db')

    def get_hexdigest(salt, raw_password):
        data = salt + raw_password
        return sha1(data.encode('utf8')).hexdigest()

    @db.func()
    def make_password(raw_password):
        salt = get_hexdigest(str(random()), str(random()))[:5]
        hsh = get_hexdigest(salt, raw_password)
        return '%s$%s' % (salt, hsh)

    @db.func()
    def check_password(raw_password, enc_password):
        salt, hsh = enc_password.split('$', 1)
        return hsh == get_hexdigest(salt, raw_password)

Here is how you can use the function to add a new user, storing a hashed password:

.. code-block:: python

    query = User.insert(
        username='charlie',
        password=fn.make_password('testing')).execute()

If we retrieve the user from the database, the password that's stored is hashed and salted:

.. code-block:: pycon

    >>> user = User.get(User.username == 'charlie')
    >>> print(user.password)
    b76fa$88be1adcde66a1ac16054bc17c8a297523170949

To implement ``login``-type functionality, you could write something like this:

.. code-block:: python

    def login(username, password):
        try:
            return (User
                    .select()
                    .where(
                        (User.username == username) &
                        (fn.check_password(password, User.password) == True))
                    .get())
        except User.DoesNotExist:
            # Incorrect username and/or password.
            return False

.. _datemath:

Date math
---------

Each of the databases supported by Peewee implement their own set of functions
and semantics for date/time arithmetic.

This section will provide a short scenario and example code demonstrating how
you might utilize Peewee to do dynamic date manipulation in SQL.

Scenario: we need to run certain tasks every *X* seconds, and both the task
intervals and the task themselves are defined in the database. We need to write
some code that will tell us which tasks we should run at a given time:

.. code-block:: python

    class Schedule(Model):
        interval = IntegerField()  # Run this schedule every X seconds.


    class Task(Model):
        schedule = ForeignKeyField(Schedule, backref='tasks')
        command = TextField()  # Run this command.
        last_run = DateTimeField()  # When was this run last?

Our logic will essentially boil down to:

.. code-block:: python

    # e.g., if the task was last run at 12:00:05, and the associated interval
    # is 10 seconds, the next occurrence should be 12:00:15. So we check
    # whether the current time (now) is 12:00:15 or later.
    now >= task.last_run + schedule.interval

So we can write the following code:

.. code-block:: python

    next_occurrence = something  # ??? how do we define this ???

    # We can express the current time as a Python datetime value, or we could
    # alternatively use the appropriate SQL function/name.
    now = Value(datetime.datetime.now())  # Or SQL('current_timestamp'), e.g.

    query = (Task
             .select(Task, Schedule)
             .join(Schedule)
             .where(now >= next_occurrence))

For Postgresql we will multiple a static 1-second interval to calculate the
offsets dynamically:

.. code-block:: python

    second = SQL("INTERVAL '1 second'")
    next_occurrence = Task.last_run + (Schedule.interval * second)

For MySQL we can reference the schedule's interval directly:

.. code-block:: python

    from peewee import NodeList  # Needed to construct sql entity.

    interval = NodeList((SQL('INTERVAL'), Schedule.interval, SQL('SECOND')))
    next_occurrence = fn.date_add(Task.last_run, interval)

For SQLite, things are slightly tricky because SQLite does not have a dedicated
datetime type. So for SQLite, we convert to a unix timestamp, add the schedule
seconds, then convert back to a comparable datetime representation:

.. code-block:: python

    next_ts = fn.strftime('%s', Task.last_run) + Schedule.interval
    next_occurrence = fn.datetime(next_ts, 'unixepoch')
