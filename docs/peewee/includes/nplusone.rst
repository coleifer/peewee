Avoiding N+1 queries
--------------------

The term *N+1 queries* refers to a situation where an application performs a query, then for each row of the result set, the application performs at least one other query (another way to conceptualize this is as a nested loop). In many cases, these *n* queries can be avoided through the use of a SQL join or subquery. The database itself may do a nested loop, but it will usually be more performant than doing *n* queries in your application code, which involves latency communicating with the database and may not take advantage of indices or other optimizations employed by the database when joining or executing a subquery.

Peewee provides several APIs for mitigating *N+1* query behavior. Recollecting the models used throughout this document, *User* and *Tweet*, this section will try to outline some common *N+1* scenarios, and how peewee can help you avoid them.

List recent tweets
^^^^^^^^^^^^^^^^^^

The twitter timeline displays a list of tweets from multiple users. In addition to the tweet's content, the username of the tweet's author is also displayed. The N+1 scenario here would be:

1. Fetch the 10 most recent tweets.
2. For each tweet, select the author (10 queries).

By selecting both tables and using a *join*, peewee makes it possible to accomplish this in a single query:

.. code-block:: python

    query = (Tweet
             .select(Tweet, User)  # Note that we are selecting both models.
             .join(User)  # Use an INNER join because every tweet has an author.
             .order_by(Tweet.id.desc())  # Get the most recent tweets.
             .limit(10))

    for tweet in query:
        print tweet.user.username, '-', tweet.message

Without the join, accessing ``tweet.user.username`` would trigger a query to resolve the foreign key ``tweet.user`` and retrieve the associated user. But since we have selected and joined on ``User``, peewee will automatically resolve the foreign-key for us.

List users and all their tweets
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let's say you want to build a page that shows several users and all of their tweets. The N+1 scenario would be:

1. Fetch some users.
2. For each user, fetch their tweets.

This situation is similar to the previous example, but there is one important difference: when we selected tweets, they only have a single associated user, so we could directly assign the foreign key. The reverse is not true, however, as one user may have any number of tweets (or none at all).

Peewee provides two approaches to avoiding *O(n)* queries in this situation. We can either:

* Fetch both users and tweets in a single query. User data will be duplicated, so peewee will de-dupe it and aggregate the tweets as it iterates through the result set.
* Fetch users first, then fetch all the tweets associated with those users. Once peewee has the big list of tweets, it will assign them out, matching them with the appropriate user.

Each solution has its place and, depending on the size and shape of the data you are querying, one may be more performant than the other.

Let's look at the first approach, since it is more general and can work with arbitrarily complex queries. We will use a special flag, :py:meth:`~SelectQuery.aggregate_rows`, when creating our query. This method tells peewee to de-duplicate any rows that, due to the structure of the JOINs, may be duplicated.

.. code-block:: python

    query = (User
             .select(User, Tweet)  # As in the previous example, we select both tables.
             .join(Tweet, JOIN_LEFT_OUTER)
             .order_by(User.username)  # We need to specify an ordering here.
             .aggregate_rows())  # Tell peewee to de-dupe and aggregate results.

    for user in query:
        print user.username
        for tweet in user.tweets:
            print '  ', tweet.message

Ordinarily, ``user.tweets`` would be a :py:class:`SelectQuery` and iterating over it would trigger an additional query. By using :py:meth:`~SelectQuery.aggregate_rows`, though, ``user.tweets`` is a Python ``list`` and no additional query occurs.

.. note::
    We used a *LEFT OUTER* join to ensure that users with zero tweets would
    also be included in the result set.

Below is an example of how we might fetch several users and any tweets they created within the past week. Because we are filtering the tweets and the user may not have any tweets, we need our *WHERE* clause to allow *NULL* tweet IDs.

.. code-block:: python

    week_ago = datetime.date.today() - datetime.timedelta(days=7)
    query = (User
             .select(User, Tweet)
             .join(Tweet, JOIN_LEFT_OUTER)
             .where(
                 (Tweet.id >> None) | (
                     (Tweet.is_published == True) &
                     (Tweet.created_date >= week_ago)))
             .order_by(User.username, Tweet.created_date.desc())
             .aggregate_rows())

    for user in query:
        print user.username
        for tweet in user.tweets:
            print '  ', tweet.message

Using prefetch
^^^^^^^^^^^^^^

Besides :py:meth:`~SelectQuery.aggregate_rows`, peewee supports a second approach using sub-queries. This method requires the use of a special API, :py:func:`prefetch`. Pre-fetch, as its name indicates, will eagerly load the appropriate tweets for the given users using subqueries. This means instead of *O(n)* queries for *n* rows, we will do *O(k)* queries for *k* tables.

Here is an example of how we might fetch several users and any tweets they created within the past week.

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
