.. _querying:

Querying API
============

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

You can join on tables related to one another by :py:class:`ForeignKeyField`.  The :py:meth:`~SelectQuery.join`
method acts on the :py:class:`Model` that is the current "query context".
This is either:

* the model the query class was initialized with
* the model most recently JOINed on

There are three types of joins by default:

* JOIN_INNER (default)
* JOIN_LEFT_OUTER
* JOIN_FULL

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

The other bit that's unique about the query is that it specifies ``"user__in"``.
Users familiar with Django will recognize this syntax - lookups other than "="
are signified by a double-underscore followed by the lookup type.  The following
lookup types are available in peewee:


================ =======================================
Lookup           Meaning
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

.. note:: If you need more power, check out :py:class:`RawQuery`


Comparing against column data
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

.. py:class:: fn()

    A helper class that will convert arbitrary function calls to SQL function calls.

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
By default it uses an inner join if the foreign key is not nullable, which means
users without tweets won't appear in the list.  To remedy this, manually specify
the type of join to include users with 0 tweets:

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

Arbitrary SQL functions can be expressed using the ``fn`` function.

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


SelectQuery
-----------

.. py:class:: SelectQuery

    By far the most complex of the 4 query classes available in
    peewee.  It supports ``JOIN`` operations on other tables, aggregation via ``GROUP BY`` and ``HAVING``
    clauses, ordering via ``ORDER BY``, and can be iterated and sliced to return only a subset of
    results.

    .. py:method:: __init__(model, *selection)

        :param model: a :py:class:`Model` class to perform query on
        :param selection: a list of models, fields, functions or expressions

        If no query is provided, it will default to all the fields of the given
        model.

        .. code-block:: python

            >>> sq = SelectQuery(User, User.id, User.username)
            >>> sq = SelectQuery(User,
            ...     User, fn.Count(Tweet.id).alias('count')
            ... ).join(Tweet).group_by(User)

    .. py:method:: where(*q_or_node)

        :param q_or_node: a list of expressions (:py:class:`Q` or :py:class:`Node` objects
        :rtype: a :py:class:`SelectQuery` instance

        .. code-block:: python

            >>> sq = SelectQuery(User).where(User.username == 'somebody')
            >>> sq = SelectQuery(Blog).where(
            ...     (User.username == 'somebody') |
            ...     (User.username == 'nobody')
            ... )

        .. note::

            :py:meth:`~SelectQuery.where` calls are chainable

    .. py:method:: join(model, join_type=None, on=None)

        :param model: the model to join on.  there must be a :py:class:`ForeignKeyField` between
            the current ``query context`` and the model passed in.
        :param join_type: allows the type of ``JOIN`` used to be specified explicitly,
            one of ``JOIN_INNER``, ``JOIN_LEFT_OUTER``, ``JOIN_FULL``
        :param on: if multiple foreign keys exist between two models, this parameter
            is the ForeignKeyField to join on.
        :rtype: a :py:class:`SelectQuery` instance

        Generate a ``JOIN`` clause from the current ``query context`` to the ``model`` passed
        in, and establishes ``model`` as the new ``query context``.

        >>> sq = SelectQuery(Tweet).join(User)
        >>> sq = SelectQuery(User).join(Relationship, on=Relationship.to_user)

    .. py:method:: group_by(*clauses)

        :param clauses: either a list of model classes or field names
        :rtype: :py:class:`SelectQuery`

        .. code-block:: python

            >>> # get a list of blogs with the count of entries each has
            >>> sq = User.select(
            ...     User, fn.Count(Tweet.id).alias('count')
            ... ).join(Tweet).group_by(User)

    .. py:method:: having(*q_or_node)

        :param q_or_node: a list of expressions (:py:class:`Q` or :py:class:`Node` objects
        :rtype: :py:class:`SelectQuery`

        .. code-block:: python

            >>> sq = User.select(
            ...     User, fn.Count(Tweet.id).alias('count')
            ... ).join(Tweet).group_by(User).having(fn.Count(Tweet.id) > 10)

    .. py:method:: order_by(*clauses)

        :param clauses: a list of fields or calls to ``field.[asc|desc]()``
        :rtype: :py:class:`SelectQuery`

        example:

        .. code-block:: python

            >>> User.select().order_by(User.username)
            >>> Tweet.select().order_by(Tweet.created_date.desc())
            >>> Tweet.select().join(User).order_by(
            ...     User.username, Tweet.created_date.desc()
            ... )

    .. py:method:: paginate(page_num, paginate_by=20)

        :param page_num: a 1-based page number to use for paginating results
        :param paginate_by: number of results to return per-page
        :rtype: :py:class:`SelectQuery`

        applies a ``LIMIT`` and ``OFFSET`` to the query.

        .. code-block:: python

            >>> User.select().order_by(User.username).paginate(3, 20) # <-- get users 41-60

    .. py:method:: limit(num)

        :param int num: limit results to ``num`` rows

    .. py:method:: offset(num)

        :param int num: offset results by ``num`` rows

    .. py:method:: count()

        :rtype: an integer representing the number of rows in the current query

        >>> sq = SelectQuery(Tweet)
        >>> sq.count()
        45 # <-- number of tweets
        >>> sq.where(Tweet.status == DELETED)
        >>> sq.count()
        3 # <-- number of tweets that are marked as deleted

    .. py:method:: get()

        :rtype: :py:class:`Model` instance or raises ``DoesNotExist`` exception

        Get a single row from the database that matches the given query.  Raises a
        ``<model-class>.DoesNotExist`` if no rows are returned:

        .. code-block:: python

            >>> active = User.select().where(User.active == True)
            >>> try:
            ...     user = active.where(User.username == username).get()
            ... except User.DoesNotExist:
            ...     user = None

        This method is also exposed via the :py:class:`Model` api, in which case it
        accepts arguments that are translated to the where clause:

            >>> user = User.get(User.active == True, User.username == username)

    .. py:method:: exists()

        :rtype: boolean whether the current query will return any rows.  uses an
            optimized lookup, so use this rather than :py:meth:`~SelectQuery.get`.

        .. code-block:: python

            >>> sq = User.select().where(User.active == True)
            >>> if sq.where(User.username==username, User.password==password).exists():
            ...     authenticated = True

    .. py:method:: annotate(related_model, aggregation=None)

        :param related_model: related :py:class:`Model` on which to perform aggregation,
            must be linked by :py:class:`ForeignKeyField`.
        :param aggregation: the type of aggregation to use, e.g. ``fn.Count(Tweet.id).alias('count')``
        :rtype: :py:class:`SelectQuery`

        Annotate a query with an aggregation performed on a related model, for example,
        "get a list of users with the number of tweets for each"::

            >>> User.select().annotate(Tweet)

        if ``aggregation`` is None, it will default to ``fn.Count(related_model.id).alias('count')``
        but can be anything::

            >>> user_latest = User.select().annotate(Tweet, fn.Max(Tweet.created_date).alias('latest'))

        .. note::

            If the ``ForeignKeyField`` is ``nullable``, then a ``LEFT OUTER`` join
            may need to be used::

                >>> User.select().join(Tweet, JOIN_LEFT_OUTER).annotate(Tweet)

    .. py:method:: aggregate(aggregation)

        :param aggregation: a function specifying what aggregation to perform, for
          example ``fn.Max(Tweet.created_date)``.

        Method to look at an aggregate of rows using a given function and
        return a scalar value, such as the count of all rows or the average
        value of a particular column.

    .. py:method:: for_update([for_update=True])

        :rtype: :py:class:`SelectQuery`

        indicates that this query should lock rows for update

    .. py:method:: distinct()

        :rtype: :py:class:`SelectQuery`

        indicates that this query should only return distinct rows.  results in a
        ``SELECT DISTINCT`` query.

    .. py:method:: naive()

        :rtype: :py:class:`SelectQuery`

        indicates that this query should only attempt to reconstruct a single model
        instance for every row returned by the cursor.  if multiple tables were queried,
        the columns returned are patched directly onto the single model instance.

        .. note::

            this can provide a significant speed improvement when doing simple
            iteration over a large result set.

    .. py:method:: switch(model)

        :param model: model to switch the ``query context`` to.
        :rtype: a :py:class:`SelectQuery` instance

        Switches the ``query context`` to the given model.  Raises an exception if the
        model has not been selected or joined on previously.  The following example
        selects from blog and joins on both entry and user::

        >>> sq = SelectQuery(Blog).join(Entry).switch(Blog).join(User)

    .. py:method:: filter(*args, **kwargs)

        :param args: a list of :py:class:`DQ` or :py:class:`Node` objects
        :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"
        :rtype: :py:class:`SelectQuery` with appropriate ``WHERE`` clauses

        Provides a django-like syntax for building a query. The key difference
        between :py:meth:`~Model.filter` and :py:meth:`SelectQuery.where`
        is that :py:meth:`~Model.filter` supports traversing joins using
        django's "double-underscore" syntax:

        .. code-block:: python

            >>> sq = Entry.filter(blog__title='Some Blog')

        This method is chainable::

            >>> base_q = User.filter(active=True)
            >>> some_user = base_q.filter(username='charlie')

        .. note:: this method is provided for compatibility with peewee 1.

    .. py:method:: execute()

        :rtype: :py:class:`QueryResultWrapper`

        Executes the query and returns a :py:class:`QueryResultWrapper` for iterating over
        the result set.  The results are managed internally by the query and whenever
        a clause is added that would possibly alter the result set, the query is
        marked for re-execution.

    .. py:method:: __iter__()

        Executes the query:

        .. code-block:: python

            >>> for user in User.select().where(User.active == True):
            ...     print user.username


UpdateQuery
-----------

.. py:class:: UpdateQuery

    Used for updating rows in the database.

    .. py:method:: __init__(model, **kwargs)

        :param model: :py:class:`Model` class on which to perform update
        :param kwargs: mapping of field/value pairs containing columns and values to update

        .. code-block:: python

            >>> uq = UpdateQuery(User, active=False).where(User.registration_expired==True)
            >>> uq.execute() # run the query

        .. code-block:: python

            >>> atomic_update = UpdateQuery(User, message_count=User.message_count + 1).where(User.id == 3)
            >>> atomic_update.execute() # run the query

    .. py:method:: where(*args, **kwargs)

        Same as :py:meth:`SelectQuery.where`

    .. py:method:: execute()

        :rtype: Number of rows updated

        Performs the query


DeleteQuery
-----------

.. py:class:: DeleteQuery

    Deletes rows of the given model.

    .. note::
        It will *not* traverse foreign keys or ensure that constraints are obeyed, so use it with care.

    .. py:method:: __init__(model)

        creates a ``DeleteQuery`` instance for the given model:

        .. code-block:: python

            >>> dq = DeleteQuery(User).where(User.active==False)

    .. py:method:: where(*args, **kwargs)

        Same as :py:meth:`SelectQuery.where`

    .. py:method:: execute()

        :rtype: Number of rows deleted

        Performs the query


InsertQuery
-----------

.. py:class:: InsertQuery

    Creates a new row for the given model.

    .. py:method:: __init__(model, **kwargs)

        creates an ``InsertQuery`` instance for the given model where kwargs is a
        dictionary of field name to value:

        .. code-block:: python

            >>> iq = InsertQuery(User, username='admin', password='test', active=True)
            >>> iq.execute() # <--- insert new row

    .. py:method:: execute()

        :rtype: primary key of the new row

        Performs the query


RawQuery
--------

.. py:class:: RawQuery

    Allows execution of an arbitrary query and returns instances
    of the model via a :py:class:`QueryResultsWrapper`.

    .. py:method:: __init__(model, query, *params)

        creates a ``RawQuery`` instance for the given model which, when executed,
        will run the given query with the given parameters and return model instances::

            >>> rq = RawQuery(User, 'SELECT * FROM users WHERE username = ?', 'admin')
            >>> for obj in rq.execute():
            ...     print obj
            <User: admin>

    .. py:method:: execute()

        :rtype: a :py:class:`QueryResultWrapper` for iterating over the result set.  The results are instances of the given model.

        Performs the query
