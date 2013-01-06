.. _querying:

Querying
========

Constructing queries
--------------------

Queries in peewee are constructed one piece at a time.

The "pieces" of a peewee query are generally representative of clauses you might
find in a SQL query.  Most methods are chainable, so you build your query up
one clause at a time.  This way, rather complex queries are possible.

Here is a barebones select query:

.. code-block:: python

    >>> user_q = User.select() # <-- query is not executed
    >>> user_q
    <peewee.SelectQuery object at 0x7f6b0810c610>

    >>> [u.username for u in user_q] # <-- query is evaluated here
    [u'admin', u'staff', u'editor']

We can build up the query by adding some clauses to it:

.. code-block:: python

    >>> user_q = user_q.where(User.username << ['admin', 'editor'])
    >>> user_q = user_q.order_by(User.username.desc())
    >>> [u.username for u in user_q] # <-- query is re-evaluated here
    [u'editor', u'admin']

.. _query_compare:

Looking at some simple queries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Get active users:
    .. code-block:: python

        User.select().where(User.active==True)

Get users who are either staff or superusers:
    .. code-block:: python

        User.select().where((User.is_staff==True) | (User.is_superuser==True))

Get tweets by user named "charlie":
    .. code-block:: python

        Tweet.select().join(User).where(User.username=='charlie')

Get tweets by staff or superusers (assumes FK relationship):
    .. code-block:: python

        Tweet.select().join(User).where(
            (User.is_staff==True) | (User.is_superuser==True)
        )

.. _where_clause:

Where clause
------------

All queries except :py:class:`InsertQuery` support the ``where()`` method.  If you are
familiar with Django's ORM, it is analagous to the ``filter()`` method.

.. code-block:: python

    >>> User.select().where(User.is_staff == True)

.. note:: ``User.select()`` is equivalent to ``SelectQuery(User)``.

Joining
^^^^^^^

You can join on tables related to one another by :py:class:`ForeignKeyField`.  The :py:meth:`~Query.join`
method acts on the :py:class:`Model` that is the current "query context".
This is either:

* the model the query class was initialized with
* the model most recently JOINed on

There are three types of joins by default:

* ``JOIN_INNER`` (default)
* ``JOIN_LEFT_OUTER``
* ``JOIN_FULL``

Here is an example using JOINs:

.. code-block:: python

    >>> User.select().join(Blog).where(User.is_staff == True, Blog.status == LIVE)

The above query grabs all staff users who have a blog that is "LIVE".  This next does the
inverse: grabs all the blogs that are live whose author is a staffer:

.. code-block:: python

    >>> Blog.select().join(User).where(User.is_staff == True, Blog.status == LIVE)

Another way to write the above query would be to use a subquery:

.. code-block:: python

    >>> staff = User.select().where(User.is_staff == true)
    >>> Blog.select().where(Blog.status == LIVE, Blog.user << staff)

The above bears a little bit of explanation.  First off the SQL generated will
not perform any explicit ``JOIN`` - it will rather use a subquery in the ``WHERE``
clause:

.. code-block:: sql

    -- translates roughly to --
    SELECT t1.* FROM blog AS t1
    WHERE (
        t1.status = ? AND
        t1.user_id IN (
            SELECT t2.id FROM user AS t2 WHERE t2.is_staff = ?
        )
    )

And here it is using joins:

.. code-block:: sql

    -- and here it would be if using joins --
    SELECT t1.* FROM blog AS t1
    INNER JOIN user AS t2
        ON t1.user_id = t2.id
    WHERE
        t1.status = ? AND
        t2.is_staff = ?

.. _column-lookups:

Column lookups
^^^^^^^^^^^^^^

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
================ =======================================


Performing advanced queries
---------------------------

As you may have noticed, all the examples up to now have shown queries that
combine multiple clauses with "AND".  To create arbitrarily complex queries,
simply use python's bitwise "and" and "or" operators:

.. code-block:: python

    >>> sq = User.select().where(
    ...     (User.is_staff == True) |
    ...     (User.is_superuser == True)
    ... )

The ``WHERE`` clause will look something like:

.. code-block:: sql

    WHERE (is_staff = ? OR is_superuser = ?)

In order to negate an expression, use the bitwise "invert" operator:

.. code-block:: python

    >>> staff_users = User.select().where(is_staff=True)
    >>> Tweet.select().where(
    ...     ~(Tweet.user << staff_users)
    ... )

This query generates roughly the following SQL:

.. code-block:: sql

    SELECT t1.* FROM blog AS t1
    WHERE
        NOT t1.user_id IN (
            SELECT t2.id FROM user AS t2 WHERE t2.is_staff = ?
        )

Rather complex lookups are possible:

.. code-block:: python

    >>> sq = User.select().where(
    ...     ((User.is_staff == True) | (User.is_superuser == True)) &
    ...     (User.join_date >= datetime(2009, 1, 1)
    ... )

This generates roughly the following SQL:

.. code-block:: sql

    SELECT * FROM user
    WHERE (
        (is_staff = ? OR is_superuser = ?) AND
        (join_date >= ?)
    )


Other types of comparisons
^^^^^^^^^^^^^^^^^^^^^^^^^^

Suppose you have a model that looks like the following:

.. code-block:: python

    class WorkerProfiles(Model):
        salary = IntegerField()
        desired = IntegerField()
        tenure = IntegerField()

What if we want to query ``WorkerProfiles`` to find all the rows where "salary" is greater
than "desired" (maybe you want to find out who may be looking for a raise)?


.. code-block:: python

    WorkerProfile.select().where(
        WorkerProfile.salary < WorkerProfile.desired
    )

We can also create expressions, like to find employees who might not be getting
paid enough based on their tenure:

.. code-block:: python

    WorkerProfile.select().where(
        WorkerProfile.salary < (WorkerProfile.tenure * 1000) + 40000
    )


Atomic updates
^^^^^^^^^^^^^^

The techniques shown above also work for updating data.  Suppose you
are counting pageviews in a special table:

.. code-block:: python

    PageView.update(count=PageView.count + 1).where(
        PageView.url == request.url
    )


The "fn" helper
^^^^^^^^^^^^^^^

SQL provides a number of helper functions as a part of the language.  These functions
can be used to calculate counts and sums over rows, perform string manipulations,
do complex math, and more.  There are a lot of functions.

To express functions in peewee, use the :py:class:`fn` object.  The way it works is
anything to the right of the "dot" operator will be treated as a function.  You can
pass that function arbitrary parameters which can be other valid expressions.

For example:

.. _fn_examples:

============================================ ============================================
Peewee expression                            Equivalent SQL
============================================ ============================================
``fn.Count(Tweet.id).alias('count')``        ``Count(t1."id") AS count``
``fn.Lower(fn.Substr(User.username, 1, 1))`` ``Lower(Substr(t1."username", 1, 1))``
``fn.Rand().alias('random')``                ``Rand() AS random``
``fn.Stddev(Employee.salary).alias('sdv')``  ``Stddev(t1."salary") AS sdv``
============================================ ============================================

Functions can be used as any part of a query:

* select
* where
* group_by
* order_by
* having
* update query
* insert query

View API documentation on :py:class:`fn`


Aggregating records
^^^^^^^^^^^^^^^^^^^

Suppose you have some users and want to get a list of them along with the count
of tweets each has made.  First I will show you the shortcut:

.. code-block:: python

    query = User.select().annotate(Tweet)

This is equivalent to the following:

.. code-block:: python

    query = User.select(
        User, fn.Count(Tweet.id).alias('count')
    ).join(Tweet).group_by(User)

The resulting query will return ``User`` objects with all their normal attributes
plus an additional attribute 'count' which will contain the number of tweets.
By default it uses an inner join, which means users without tweets won't appear
in the list.  To remedy this, manually specify the type of join to include users
with 0 tweets:

.. code-block:: python

    query = User.select().join(Tweet, JOIN_LEFT_OUTER).annotate(Tweet)

You can also specify a custom aggregator.  In the following query we will annotate
the users with the date of their most recent tweet:

.. code-block:: python

    query = User.select().annotate(Tweet, fn.Max(Tweet.created_date).alias('latest'))

Conversely, sometimes you want to perform an aggregate query that returns a
scalar value, like the "max id".  Queries like this can be executed by using
the :py:meth:`~SelectQuery.aggregate` method:

.. code-block:: python

    most_recent_tweet = Tweet.select().aggregate(fn.Max(Tweet.created_date))


SQL Functions
^^^^^^^^^^^^^

Arbitrary SQL functions can be expressed using the :py:class:`fn` helper.

Selecting users and counts of tweets:

.. code-block:: python

    >>> users = User.select(User, fn.Count(Tweet.id).alias('count')).join(Tweet).group_by(User)
    >>> for user in users:
    ...     print user.username, 'posted', user.count, 'tweets'


This functionality can also be used as part of the ``WHERE`` or ``HAVING`` clauses:

.. code-block:: python

    >>> a_users = User.select().where(fn.Lower(fn.Substr(User.username, 1, 1)) == 'a')
    >>> for user in a_users:
    ...    print user.username

    alpha
    Alton


Saving Queries by Selecting Related Models
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Returning to my favorite models, ``User`` and ``Tweet``, between which there is a
:py:class:`ForeignKeyField`, a common pattern might be to display a list of the
latest 10 tweets with some info about the user that posted them.  We can do
this pretty easily:

.. code-block:: python

    for tweet in Tweet.select().order_by(Tweet.created_date.desc()).limit(10):
        print '%s, posted on %s' % (tweet.message, tweet.user.username)

Looking at the query log, though, this will cause 11 queries:

* 1 query for the tweets
* 1 query for every related user (10 total)

This can be optimized into one query very easily, though:

.. code-block:: python

    tweets = Tweet.select(Tweet, User).join(User)
    for tweet in tweets.order_by(Tweet.created_date.desc()).limit(10):
        print '%s, posted on %s' % (tweet.message, tweet.user.username)

Will cause only one query that looks something like this:

.. code-block:: sql

    SELECT t1.id, t1.message, t1.user_id, t1.created_date, t2.id, t2.username
    FROM tweet AS t1
    INNER JOIN user AS t2
        ON t1.user_id = t2.id
    ORDER BY t1.created_date desc
    LIMIT 10

peewee will handle constructing the objects and you can access them as you would
normally.

.. note:: Note in the above example the call to ``.join(User)``

This works for following objects "up" the chain, i.e. following foreign key relationships.
The reverse is not true, however -- you cannot issue a single query and get all related
sub-objects, i.e. list users and prefetch all related tweets.  This *can* be done by
fetching all tweets (with related user data), then reconstructing the users in python, but
is not provided as part of peewee.  For a detailed discussion of working
around this, see the `discussion here <https://groups.google.com/forum/?fromgroups#!topic/peewee-orm/RLd2r-eKp7w>`_.

If you are interested, the django developers added this feature.  Take a look 
at `the prefetch_related ticket <https://code.djangoproject.com/ticket/16937>`_.


Speeding up simple select queries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Simple select queries can get a performance boost (especially when iterating over large
result sets) by calling :py:meth:`~SelectQuery.naive`.  This method simply patches all
attributes directly from the cursor onto the model.  For simple queries this should have
no noticeable impact.  The main difference is when multiple tables are queried, as in the
previous example:

.. code-block:: python

    # above example
    tweets = Tweet.select(Tweet, User).join(User)
    for tweet in tweets.order_by(Tweet.created_date.desc()).limit(10):
        print '%s, posted on %s' % (tweet.message, tweet.user.username)

And here is how you would do the same if using a naive query:

.. code-block:: python

    # very similar query to the above -- main difference is we're
    # aliasing the blog title to "blog_title"
    tweets = Tweet.select(Tweet, User.username).join(User).naive()
    for tweet in tweets.order_by(Tweet.created_date.desc()).limit(10):
        print '%s, posted on %s' % (tweet.message, tweet.username)


Query evaluation
----------------

In order to execute a query, it is *always* necessary to call the ``execute()``
method.

To get a better idea of how querying works let's look at some example queries
and their return values:

.. code-block:: python

    >>> dq = User.delete().where(User.active == False) # <-- returns a DeleteQuery
    >>> dq
    <peewee.DeleteQuery object at 0x7fc866ada4d0>
    >>> dq.execute() # <-- executes the query and returns number of rows deleted
    3

    >>> uq = User.update(active=True).where(User.id > 3) # <-- returns an UpdateQuery
    >>> uq
    <peewee.UpdateQuery object at 0x7fc865beff50>
    >>> uq.execute() # <-- executes the query and returns number of rows updated
    2

    >>> iq = User.insert(username='new user') # <-- returns an InsertQuery
    >>> iq
    <peewee.InsertQuery object at 0x7fc865beff10>
    >>> iq.execute() # <-- executes query and returns the new row's PK
    8

    >>> sq = User.select().where(User.active == True) # <-- returns a SelectQuery
    >>> sq
    <peewee.SelectQuery object at 0x7fc865b7a510>
    >>> qr = sq.execute() # <-- executes query and returns a QueryResultWrapper
    >>> qr
    <peewee.QueryResultWrapper object at 0x7fc865b7a6d0>
    >>> [u.id for u in qr]
    [1, 2, 3, 4, 7, 8]
    >>> [u.id for u in qr] # <-- re-iterating over qr does not re-execute query
    [1, 2, 3, 4, 7, 8]

    >>> [u.id for u in sq] # <-- as a shortcut, you can iterate directly over
    >>>                    #     a SelectQuery (which uses a QueryResultWrapper
    >>>                    #     behind-the-scenes)
    [1, 2, 3, 4, 7, 8]


.. note::
    Iterating over a :py:class:`SelectQuery` will cause it to be evaluated, but iterating
    over it multiple times will not result in the query being executed again.


QueryResultWrapper
------------------

As I hope the previous bit showed, ``Delete``, ``Insert`` and ``Update`` queries are all
pretty straightforward.  ``Select`` queries are a little bit tricky in that they
return a special object called a :py:class:`QueryResultWrapper`.  The sole purpose of this
class is to allow the results of a query to be iterated over efficiently.  In
general it should not need to be dealt with explicitly.

The preferred method of iterating over a result set is to iterate directly over
the :py:class:`SelectQuery`, allowing it to manage the :py:class:`QueryResultWrapper` internally.
