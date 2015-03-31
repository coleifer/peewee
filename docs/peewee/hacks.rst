.. _hacks:

Hacks
=====

Collected hacks using peewee. Have a cool hack you'd like to share? Open `an issue on GitHub <https://github.com/coleifer/peewee/issues/new>`_ or `contact me <http://charlesleifer.com/contact/>`_.

.. _top_item_per_group:

Top object per group
--------------------

These examples describe several ways to query the single top item per group. For a thorough discuss of various techniques, check out my blog post `Querying the top item by group with Peewee ORM <http://charlesleifer.com/blog/techniques-for-querying-lists-of-objects-and-determining-the-top-related-item/>`_. If you are interested in the more general problem of querying the top *N* items, see the section below :ref:`top_n_per_group`.

In these examples we will use the *User* and *Tweet* models to find each user and their most-recent tweet.

The most efficient method I found in my testing uses the ``MAX()`` aggregate function.

We will perform the aggregation in a non-correlated subquery, so we can be confident this method will be performant. The idea is that we will select the posts, grouped by their author, whose timestamp is equal to the max observed timestamp for that user.

.. code-block:: python

    # When referencing a table multiple times, we'll call Model.alias() to create
    # a secondary reference to the table.
    TweetAlias = Tweet.alias()

    # Create a subquery that will calculate the maximum Tweet create_date for each
    # user.
    subquery = (TweetAlias
                .select(
                    TweetAlias.user,
                    fn.MAX(TweetAlias.create_date).alias('max_ts'))
                .group_by(TweetAlias.user)
                .alias('tweet_max_subquery'))

    # Query for tweets and join using the subquery to match the tweet's user
    # and create_date.
    query = (Tweet
             .select(Tweet, User)
             .join(User)
             .switch(Tweet)
             .join(subquery, on=(
                 (Tweet.create_date == subquery.c.max_ts) &
                 (Tweet.user == subquery.c.user_id))))

SQLite and MySQL are a bit more lax and permit grouping by a subset of the columns that are selected. This means we can do away with the subquery and express it quite concisely:

.. code-block:: python

    query = (Tweet
             .select(Tweet, User)
             .join(User)
             .group_by(Tweet.user)
             .having(Tweet.create_date == fn.MAX(Tweet.create_date)))

.. _top_n_per_group:

Top N objects per group
-----------------------

These examples describe several ways to query the top *N* items per group reasonably efficiently. For a thorough discussion of various techniques, check out my blog post `Querying the top N objects per group with Peewee ORM <http://charlesleifer.com/blog/querying-the-top-n-objects-per-group-with-peewee-orm/>`_.

In these examples we will use the *User* and *Tweet* models to find each user and their three most-recent tweets.

Postgres lateral joins
^^^^^^^^^^^^^^^^^^^^^^

`Lateral joins <http://blog.heapanalytics.com/postgresqls-powerful-new-join-type-lateral/>`_ are a neat Postgres feature that allow reasonably efficient correlated subqueries. They are often described as SQL ``for each`` loops.

The desired SQL is:

.. code-block:: sql

    SELECT * FROM
      (SELECT t2.id, t2.username FROM user AS t2) AS uq
       LEFT JOIN LATERAL
      (SELECT t2.message, t2.create_date
       FROM tweet AS t2
       WHERE (t2.user_id = uq.id)
       ORDER BY t2.create_date DESC LIMIT 3)
      AS pq ON true

To accomplish this with peewee we'll need to express the lateral join as a :py:class:`Clause`, which gives us greater flexibility than the :py:meth:`~Query.join` method.

.. code-block:: python

    # We'll reference `Tweet` twice, so keep an alias handy.
    TweetAlias = Tweet.alias()

    # The "outer loop" will be iterating over the users whose
    # tweets we are trying to find.
    user_query = User.select(User.id, User.username).alias('uq')

    # The inner loop will select tweets and is correlated to the
    # outer loop via the WHERE clause. Note that we are using a
    # LIMIT clause.
    tweet_query = (TweetAlias
                   .select(TweetAlias.message, TweetAlias.create_date)
                   .where(TweetAlias.user == user_query.c.id)
                   .order_by(TweetAlias.create_date.desc())
                   .limit(3)
                   .alias('pq'))

    # Now we join the outer and inner queries using the LEFT LATERAL
    # JOIN. The join predicate is *ON TRUE*, since we're effectively
    # joining in the tweet subquery's WHERE clause.
    join_clause = Clause(
        user_query,
        SQL('LEFT JOIN LATERAL'),
        tweet_query,
        SQL('ON %s', True))

    # Finally, we'll wrap these up and SELECT from the result.
    query = (Tweet
             .select(SQL('*'))
             .from_(join_clause))

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
                ORDER BY t2.create_date DESC
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
                        order_by=[TweetAlias.create_date.desc()]).alias('rnk'))
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

If you're not using Postgres, then unfortunately you're left with options that exhibit less-than-ideal performance. For a more complete overview of common methods, check out `this blog post <http://charlesleifer.com/blog/querying-the-top-n-objects-per-group-with-peewee-orm/>`_. Below I will summarize the approaches and the corresponding SQL.

Using ``COUNT``, we can get all tweets where there exist less than *N* tweets with more recent timestamps:

.. code-block:: python

    TweetAlias = Tweet.alias()

    # Create a correlated subquery that calculates the number of
    # tweets with a higher (newer) timestamp than the tweet we're
    # looking at in the outer query.
    subquery = (TweetAlias
                .select(fn.COUNT(TweetAlias.id))
                .where(
                    (TweetAlias.create_date >= Tweet.create_date) &
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
                 (TweetAlias.create_date >= Tweet.create_date)))
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
                 .order_by(TweetAlias.create_date.desc())
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
    >>> print user.password
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
