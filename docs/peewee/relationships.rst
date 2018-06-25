.. _relationships:

Relationships and Joins
=======================

In this document we'll cover how Peewee handles relationships between models.

Model definitions
-----------------

We'll use the following model definitions for our examples:

.. code-block:: python

    import datetime
    from peewee import *


    db = SqliteDatabase(':memory:')

    class BaseModel(Model):
        class Meta:
            database = db

    class User(BaseModel):
        username = TextField()

    class Tweet(BaseModel):
        content = TextField()
        timestamp = DateTimeField(default=datetime.datetime.now)
        user = ForeignKeyField(User, backref='tweets')

    class Favorite(BaseModel):
        user = ForeignKeyField(User, backref='favorites')
        tweet = ForeignKeyField(Tweet, backref='favorites')


Peewee uses :py:class:`ForeignKeyField` to define foreign-key relationships
between models. Every foreign-key field has an implied back-reference, which is
exposed as a pre-filtered :py:class:`Select` query using the provided
``backref`` attribute.

Creating test data
^^^^^^^^^^^^^^^^^^

To follow along with the examples, let's populate this database with some test
data:

.. code-block:: python

    def populate_test_data():
        data = (
            ('huey', ('meow', 'hiss', 'purr')),
            ('mickey', ('woof', 'whine')),
            ('zaizee', ()))
        for username, tweets in data:
            user = User.create(username=username)
            for tweet in tweets:
                Tweet.create(user=user, content=tweet)

        # Populate a few favorites for our users, such that:
        favorite_data = (
            ('huey', ['whine']),
            ('mickey', ['purr']),
            ('zaizee', ['meow', 'purr']))
        for username, favorites in favorite_data:
            user = User.get(User.username == username)
            for content in favorites:
                tweet = Tweet.get(Tweet.content == content)
                Favorite.create(user=user, tweet=tweet)

This gives us the following:

========= ========== ===========================
User      Tweet      Favorited by
========= ========== ===========================
huey      meow       zaizee
huey      hiss
huey      purr       mickey, zaizee
mickey    woof
mickey    whine      huey
========= ========== ===========================

Performing simple joins
-----------------------

As an exercise in learning how to perform joins with Peewee, let's write a
query to print out all the tweets by "huey". To do this we'll select from the
``Tweet`` model and join on the ``User`` model, so we can then filter on the
``User.username`` field:

.. code-block:: pycon

    >>> query = Tweet.select().join(User).where(User.username == 'huey')
    >>> for tweet in query:
    ...     print(tweet.content)
    ...
    meow
    hiss
    purr

.. note::
    We did not have to explicitly specify the join predicate (the "ON" clause),
    because Peewee inferred from the models that when we joined from Tweet to
    User, we were joining on the ``Tweet.user`` foreign-key.

    The following code is equivalent, but more explicit:

    .. code-block:: python

        query = (Tweet
                 .select()
                 .join(User, on=(Tweet.user == User.id))
                 .where(User.username == 'huey'))

If we already had a reference to the ``User`` object for "huey", we could use
the ``User.tweets`` back-reference to list all of huey's tweets:

.. code-block:: pycon

    >>> huey = User.get(User.username == 'huey')
    >>> for tweet in huey.tweets:
    ...     print(tweet.content)
    ...
    meow
    hiss
    purr

Taking a closer look at ``huey.tweets``, we can see that it is just a simple
pre-filtered ``SELECT`` query:

.. code-block:: pycon

    >>> huey.tweets
    <peewee.ModelSelect at 0x7f0483931fd0>

    >>> huey.tweets.sql()
    ('SELECT "t1"."id", "t1"."content", "t1"."timestamp", "t1"."user_id"
      FROM "tweet" AS "t1" WHERE ("t1"."user_id" = ?)', [1])

Joining multiple tables
-----------------------

Let's take another look at joins by querying the list of users and getting the
count of how many tweet's they've authored that were favorited. This will
require us to join twice: from user to tweet, and from tweet to favorite. We'll
add the additional requirement that users should be included who have not
created any tweets, as well as users whose tweets have not been favorited. The
query, expressed in SQL, would be:

.. code-block:: sql

    SELECT user.username, COUNT(favorite.id)
    FROM user
    LEFT OUTER JOIN tweet ON tweet.user_id = user.id
    LEFT OUTER JOIN favorite ON favorite.tweet_id = tweet.id
    GROUP BY user.username

.. note::
    In the above query both joins are LEFT OUTER, since a user may not have any
    tweets or, if they have tweets, none of them may have been favorited.

Peewee has a concept of a *join context*, meaning that whenever we call the
:py:meth:`~ModelSelect.join` method, we are implicitly joining on the
previously-joined model (or if this is the first call, the model we are
selecting from). Since we are joining straight through, from user to tweet,
then from tweet to favorite, we can simply write:

.. code-block:: python

    query = (User
             .select(User.username, fn.COUNT(Favorite.id).alias('count'))
             .join(Tweet, JOIN.LEFT_OUTER)  # Joins user -> tweet.
             .join(Favorite, JOIN.LEFT_OUTER)  # Joins tweet -> favorite.
             .group_by(User.username))

Iterating over the results:

.. code-block:: pycon

    >>> for user in query:
    ...     print(user.username, user.count)
    ...
    huey 3
    mickey 1
    zaizee 0

For a more complicated example involving multiple joins and switching join
contexts, let's find all the tweets by Huey and the number of times they've
been favorited. To do this we'll need to perform two joins and we'll also use
an aggregate function to calculate the favorite count.

Here is how we would write this query in SQL:

.. code-block:: sql

    SELECT tweet.content, COUNT(favorite.id)
    FROM tweet
    INNER JOIN user ON tweet.user_id = user.id
    LEFT OUTER JOIN favorite ON favorite.tweet_id = tweet.id
    WHERE user.username = 'huey'
    GROUP BY tweet.content;

.. note::
    We use a LEFT OUTER join from tweet to favorite since a tweet may not have
    any favorites, yet we still wish to display it's content (along with a
    count of zero) in the result set.

With Peewee, the resulting Python code looks very similar to what we would
write in SQL:

.. code-block:: python

    query = (Tweet
             .select(Tweet.content, fn.COUNT(Favorite.id).alias('count'))
             .join(User)  # Join from tweet -> user.
             .switch(Tweet)  # Move "join context" back to tweet.
             .join(Favorite, JOIN.LEFT_OUTER)  # Join from tweet -> favorite.
             .where(User.username == 'huey')
             .group_by(Tweet.content))

Note the call to :py:meth:`~ModelSelect.switch` - that instructs Peewee to set
the *join context* back to ``Tweet``. If we had omitted the explicit call to
switch, Peewee would have used ``User`` (the last model we joined) as the join
context and constructed the join from User to Favorite using the
``Favorite.user`` foreign-key, which would have given us incorrect results.

We can iterate over the results of the above query to print the tweet's content
and the favorite count:

.. code-block:: pycon

    >>> for tweet in query:
    ...     print('%s favorited %d times' % (tweet.content, tweet.count))
    ...
    meow favorited 1 times
    hiss favorited 0 times
    purr favorited 2 times

Selecting from multiple sources
-------------------------------

If we wished to list all the tweets in the database, along with the username of
their author, you might try writing this:

.. code-block:: pycon

    >>> for tweet in Tweet.select():
    ...     print(tweet.user.username, '->', tweet.content)
    ...
    huey -> meow
    huey -> hiss
    huey -> purr
    mickey -> woof
    mickey -> whine

There is a big problem with the above loop: it executes an additional query for
every tweet to look up the ``tweet.user`` foreign-key. For our small table the
performance penalty isn't obvious, but we would find the delays grew as the
number of rows increased.

If you're familiar with SQL, you might remember that it's possible to SELECT
from multiple tables, allowing us to get the tweet content *and* the username
in a single query:

.. code-block:: sql

    SELECT tweet.content, user.username
    FROM tweet
    INNER JOIN user ON tweet.user_id = user.id;

Peewee makes this quite easy. In fact, we only need to modify our query a
little bit. We tell Peewee we wish to select ``Tweet.content`` as well as
the ``User.username`` field, then we include a join from tweet to user.
To make it a bit more obvious that it's doing the correct thing, we can ask
Peewee to return the rows as dictionaries.

.. code-block:: pycon

    >>> for row in Tweet.select(Tweet.content, User.username).join(User).dicts():
    ...     print(row)
    ...
    {'content': 'meow', 'username': 'huey'}
    {'content': 'hiss', 'username': 'huey'}
    {'content': 'purr', 'username': 'huey'}
    {'content': 'woof', 'username': 'mickey'}
    {'content': 'whine', 'username': 'mickey'}

Now we'll leave off the call to ".dicts()" and return the rows as ``Tweet``
objects. Notice that Peewee assigns the ``username`` value to
``tweet.user.username`` -- NOT ``tweet.username``!  Because there is a
foreign-key from tweet to user, and we have selected fields from both models,
Peewee will reconstruct the model-graph for us:

.. code-block:: pycon

    >>> for tweet in Tweet.select(Tweet.content, User.username).join(User):
    ...     print(tweet.user.username, '->', tweet.content)
    ...
    huey -> meow
    huey -> hiss
    huey -> purr
    mickey -> woof
    mickey -> whine

If we wish to, we can control where Peewee puts the joined ``User`` instance in
the above query, by specifying an ``attr`` in the ``join()`` method:

.. code-block:: pycon

    >>> query = Tweet.select(Tweet.content, User.username).join(User, attr='author')
    >>> for tweet in query:
    ...     print(tweet.author.username, '->', tweet.content)
    ...
    huey -> meow
    huey -> hiss
    huey -> purr
    mickey -> woof
    mickey -> whine

Conversely, if we simply wish *all* attributes we select to me attributes of
the ``Tweet`` instance, we can add a call to :py:meth:`~ModelSelect.objects` at
the end of our query (similar to how we called ``dicts()``):

.. code-block:: pycon

    >>> for tweet in query.objects():
    ...     print(tweet.username, '->', tweet.content)
    ...
    huey -> meow
    (etc)

More complex example
^^^^^^^^^^^^^^^^^^^^

As a more complex example, in this query, we will write a single query that
selects all the favorites, along with the user who created the favorite, the
tweet that was favorited, and that tweet's author.

In SQL we would write:

.. code-block:: sql

    SELECT owner.username, tweet.content, author.username AS author
    FROM favorite
    INNER JOIN user AS owner ON (favorite.user_id = owner.id)
    INNER JOIN tweet ON (favorite.tweet_id = tweet.id)
    INNER JOIN user AS author ON (tweet.user_id = author.id);

Note that we are selecting from the user table twice - once in the context of
the user who created the favorite, and again as the author of the tweet.

With Peewee, we use :py:meth:`Model.alias` to alias a model class so it can be
referenced twice in a single query:

.. code-block:: python

    Owner = User.alias()
    query = (Favorite
             .select(Favorite, Tweet.content, User.username, Owner.username)
             .join(Owner)  # Join favorite -> user (owner of favorite).
             .switch(Favorite)
             .join(Tweet)  # Join favorite -> tweet
             .join(User))   # Join tweet -> user

We can iterate over the results and access the joined values in the following
way. Note how Peewee has resolved the fields from the various models we
selected and reconstructed the model graph:

.. code-block:: pycon

    >>> for fav in query:
    ...     print(fav.user.username, 'liked', fav.tweet.content, 'by', fav.tweet.user.username)
    ...
    huey liked whine by mickey
    mickey liked purr by huey
    zaizee liked meow by huey
    zaizee liked purr by huey

.. attention::
    If you are unsure how many queries are being executed, you can add the
    following code, which will log all queries to the console:

    .. code-block:: python

        import logging
        logger = logging.getLogger('peewee')
        logger.addHandler(logging.StreamHandler())
        logger.setLevel(logging.DEBUG)
