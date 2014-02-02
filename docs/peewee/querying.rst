.. _querying:

Querying
========

.. _expressions:

.. include:: expressions.rst

Constructing queries
--------------------

Queries in peewee are constructed one piece at a time.

The "pieces" of a peewee query are generally representative of clauses you might
find in a SQL query.  Most methods are chainable, so you build your query up
one clause at a time.  This way, rather complex queries are possible.

Here is a barebones select query:

.. code-block:: pycon

    >>> user_q = User.select() # <-- query is not executed
    >>> user_q
    <peewee.SelectQuery object at 0x7f6b0810c610>

    >>> [u.username for u in user_q] # <-- query is evaluated here
    [u'admin', u'staff', u'editor']

We can build up the query by adding some clauses to it:

.. code-block:: pycon

    >>> user_q = user_q.where(User.username << ['admin', 'editor'])
    >>> user_q = user_q.order_by(User.username.desc())
    >>> [u.username for u in user_q] # <-- query is re-evaluated here
    [u'editor', u'admin']

Peewee and SQL Injection
^^^^^^^^^^^^^^^^^^^^^^^^

Because peewee uses parameterized queries, values passed in are automatically
escaped and cannot be used for SQL injection attacks. If you are writing SQL
via either :py:class:`RawQuery` or :py:meth:`~Database.execute_sql` simply be
sure that you pass any untrusted values in as parameters to the query.

.. _query_compare:

Looking at some simple queries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

.. _where_clause:

Where clause
------------

All queries except :py:class:`InsertQuery` and :py:class:`RawQuery` support the
:py:meth:`~Query.where` method.  If you are familiar with Django's ORM, it is
analagous to the ``filter()`` method.  Inside the where clause, you will place
one or more :ref:`expressions`.

.. code-block:: python

    User.select().where(User.is_staff == True)

.. note:: ``User.select()`` is equivalent to ``SelectQuery(User)``.

.. note::
    Multiple calls to :py:meth:`~Query.where` will be ``AND``-ed together. To
    dynamically connect clauses with ``OR``:

    .. code-block:: python

        import operator
        or_clauses = reduce(operator.or_, clauses)  # OR together all clauses

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

You can also perform "BETWEEN" lookups by calling the ``between`` method on
a field object:

.. code-block:: python

    Employee.select().where(Employee.salary.between(50000, 60000))

.. note::
    Because SQLite's ``LIKE`` operation is case-insensitive by default,
    peewee will use the SQLite ``GLOB`` operation for case-sensitive searches.
    The glob operation uses asterisks for wildcards as opposed to the usual
    percent-sign.  **If you are using SQLite and want case-sensitive partial
    string matching, remember to use asterisks for the wildcard (``*``).**

.. _custom-lookups:

Adding user-defined operators
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Because I ran out of python operators to overload, there are some missing
operators in peewee, for instance `modulo <https://github.com/coleifer/peewee/issues/177>`_.
If you find that you need to support an operator that is not in the table
above, it is very easy to add your own.

Here is how you might add support for ``modulo`` and ``regexp`` in SQLite:

.. code-block:: python

    from peewee import *
    from peewee import Expression # the building block for expressions

    OP_MOD = 'mod'
    OP_REGEXP = 'regexp'

    def mod(lhs, rhs):
        return Expression(lhs, OP_MOD, rhs)

    def regexp(lhs, rhs):
        return Expression(lhs, OP_REGEXP, rhs)

    SqliteDatabase.register_ops({OP_MOD: '%', OP_REGEXP: 'REGEXP'})

Now you can use these custom operators to build richer queries:

.. code-block:: python

    # users with even ids
    User.select().where(mod(User.id, 2) == 0)

    # users whose username starts with a number
    User.select().where(regexp(User.username, '[0-9].*'))

For more examples check out the source to the ``playhouse.postgresql_ext``
module, as it contains numerous operators specific to postgresql's hstore.


Joining Tables
--------------

You can join on tables related to one another by :py:class:`ForeignKeyField`.  The :py:meth:`~Query.join`
method acts on the :py:class:`Model` that is the current "query context".
This is either:

* the model the query class was initialized with
* the model most recently JOINed on

There are three types of joins by default:

* ``JOIN_INNER`` (default)
* ``JOIN_LEFT_OUTER``
* ``JOIN_FULL``

Here are some examples:

.. code-block:: python

    User.select().join(Blog).where(
        (User.is_staff == True) & (Blog.status == LIVE))

The above query grabs all staff users who have a blog that is "LIVE".  This next does the
inverse: grabs all the blogs that are live whose author is a staffer:

.. code-block:: python

    Blog.select().join(User).where(
        (User.is_staff == True) & (Blog.status == LIVE))

Another way to write the above query would be to use a subquery:

.. code-block:: python

    staff = User.select().where(User.is_staff == True)
    Blog.select().where(
        (Blog.status == LIVE) & (Blog.user << staff))

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

Here is what the SQL looks like if we use the ``join`` method:

.. code-block:: sql

    -- and here it would be if using joins --
    SELECT t1.* FROM blog AS t1
    INNER JOIN user AS t2
        ON t1.user_id = t2.id
    WHERE
        t1.status = ? AND
        t2.is_staff = ?


.. _self-joins:

Self-joins
^^^^^^^^^^

Suppose you have some models organized in a self-referential hierarchy:

.. code-block:: python

    class Category(Model):
        name = CharField()
        parent = ForeignKeyField('self', null=True)

If you want to do a self-join you will need to use the :py:meth:`Model.alias` method:

.. code-block:: python

    Parent = Category.alias()

    # select all categories where the parent is named "Parent Category"
    Category.select().join(Parent, on=(Category.parent == Parent.id)).where(
        Parent.name == 'Parent Category')

.. note:: You must explicitly specify how to construct the join when doing a self-join

.. _non-fk-joins:

Joining on Unrelated Models or Conditions other than Equality
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It is possible to use peewee's rich expressions to specify join conditions.  This
can also be used to create joins on models not related by :py:class:`ForeignKeyField`.

.. code-block:: python

    # No explicit foreign key between these models.
    OutboundShipment.select().join(InboundShipment, on=(
        OutboundShipment.barcode == InboundShipment.barcode))


Performing advanced queries
---------------------------

To create arbitrarily complex queries, simply use python's bitwise "and"
and "or" operators:

.. code-block:: python

    sq = User.select().where(
        (User.is_staff == True) |
        (User.is_superuser == True))

The ``WHERE`` clause will look something like:

.. code-block:: sql

    WHERE (is_staff = ? OR is_superuser = ?)

In order to negate an expression, use the bitwise "invert" operator:

.. code-block:: python

    staff_users = User.select().where(User.is_staff == True)
    Tweet.select().where(
        ~(Tweet.user << staff_users))

This query generates roughly the following SQL:

.. code-block:: sql

    SELECT t1.* FROM blog AS t1
    WHERE
        NOT t1.user_id IN (
            SELECT t2.id FROM user AS t2 WHERE t2.is_staff = ?)

Rather complex lookups are possible:

.. code-block:: python

    sq = User.select().where(
        ((User.is_staff == True) | (User.is_superuser == True)) &
        (User.join_date >= datetime(2009, 1, 1))

This generates roughly the following SQL:

.. code-block:: sql

    SELECT * FROM user
    WHERE (
        (is_staff = ? OR is_superuser = ?) AND
        (join_date >= ?))


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
        WorkerProfile.salary < WorkerProfile.desired)

We can also create expressions, like to find employees who might not be getting
paid enough based on their tenure:

.. code-block:: python

    WorkerProfile.select().where(
        WorkerProfile.salary < (WorkerProfile.tenure * 1000) + 40000)


Atomic updates
^^^^^^^^^^^^^^

The techniques shown above also work for updating data.  Suppose you
are counting pageviews in a special table:

.. code-block:: python

    PageView.update(count=PageView.count + 1).where(
        PageView.url == request.url)


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

    query = User.select().annotate(
        Tweet, fn.Max(Tweet.created_date).alias('latest'))

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

    users = (User
        .select(User, fn.Count(Tweet.id).alias('count'))
        .join(Tweet)
        .group_by(User))

    for user in users:
        print user.username, 'posted', user.count, 'tweets'


This functionality can also be used as part of the ``WHERE`` or ``HAVING`` clauses:

.. code-block:: pycon

    >>> a_users = User.select().where(fn.Lower(fn.Substr(User.username, 1, 1)) == 'a')
    >>> for user in a_users:
    ...   print user.username

    alpha
    Alton


Window functions
^^^^^^^^^^^^^^^^

peewee comes with basic support for SQL window functions, which can be created
by calling :py:meth:`fn.over` and passing in your partitioning or ordering
parameters.

.. code-block:: python

    # Get the list of employees and the average salary for their dept.
    query = (Employee
             .select(
                 Employee.name,
                 Employee.department,
                 Employee.salary,
                 fn.Avg(Employee.salary).over(
                     partition_by=[Employee.department]))
             .order_by(Employee.name))

    # Rank employees by salary.
    query = (Employee
             .select(
                 Employee.name,
                 Employee.salary,
                 fn.rank().over(
                     order_by=[Employee.salary])))

For general information on window functions, check
out the `postgresql docs <http://www.postgresql.org/docs/9.1/static/tutorial-window.html>`_.


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
To accomplish the reverse, i.e. list users and prefetch all related tweets, you will need
to use the :py:func:`prefetch` API discussed in the next secion.

.. _prefetch:

Pre-fetching related instances
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As a corollary to the previous section in which we selected models going "up" the
chain, in this section I will show you to select models going "down" the chain
in a 1 -> many relationship.  For example, selecting users and all of their tweets.

Assume you want to display a list of users and all of their tweets:

.. code-block:: python

    for user in User.select():
        print user.username
        for tweet in user.tweets:
            print tweet.message

This will generate N queries, however - 1 for the users, and then N for each user's
tweets.  Instead of doing N queries, we can do 2 instead:

1. One for all the users
2. One for all the tweets for the users selected in (1)

.. code-block:: sql

    -- first query --
    SELECT t1.id, t1.username FROM users AS t1;

    -- second query --
    SELECT t1.id, t1.message, t1.user_id
    FROM tweet AS t1
    WHERE t1.user_id IN (
        SELECT t2.id FROM users AS t2)

Peewee can evaluate both queries and "prefetch" the tweets for each user, storing
them in an attribute on the user model.  To do this, use the :py:func:`prefetch`
function:

.. code-block:: python

    users = User.select()
    tweets = Tweet.select()
    users_prefetch = prefetch(users, tweets)

    for user in users_prefetch:
        print user.username

        # note we are using a different attr -- it is the "related name" + "_prefetch"
        for tweet in user.tweets_prefetch:
            print tweet.message

This will result in 2 queries -- one for the users and one for the tweets.  Either
query can have restrictions, such as a ``WHERE`` clause, and the queries can follow
relationships arbitrarily deep:

.. code-block:: python

    # let's say we have users -> photos -> comments / tags
    # such that a user posts photos, assigns tags to those photos, and all those
    # photos can be commented on

    users = User.select().where(User.active == True)
    photos = Photo.select().where(Photo.published == True)
    tags = Tag.select()
    comments = Comment.select().where(Comment.is_spam == False, Comment.flags < 3)

    # this will execute 4 queries, one for each model
    users_prefetch = prefetch(users, photos, tags, comments)

    for user in users_prefetch:
        print user.username
        for photo in user.photo_set_prefetch:
            print 'photo: ', photo.filename
            for tag in photo.tag_set_prefetch:
                print 'tagged with:', tag.tag
            for comment in photo.comment_set_prefetch:
                print 'comment:', comment.comment

.. warning::
    Care should be used with prefetch!  It can save you queries, but it can also
    use a lot of memory if the number of results returned is large.  To mitigate
    this, apply a ``LIMIT`` to your outer query.


Speeding up simple select queries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Complex select queries can get a performance boost (especially when iterating over large
result sets) by calling :py:meth:`~SelectQuery.naive`.  This method simply patches all
attributes directly from the cursor onto the model.  For simple queries this will have
no noticeable impact.  The *only* difference is when multiple tables are queried, as in the
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

To iterate over raw tuples, use the :py:meth:`~SelectQuery.tuples` method:

.. code-block:: python

    stats = Stat.select(Stat.url, fn.Count(Stat.url)).group_by(Stat.url).tuples()
    for stat_url, count in stats:
        print stat_url, count

To iterate over dictionaries, use the :py:meth:`~SelectQuery.dicts` method:

.. code-block:: python

    stats = Stat.select(Stat.url, fn.Count(Stat.url).alias('ct')).group_by(Stat.url).dicts()
    for stat in stats:
        print stat['url'], stat['ct']


Query evaluation
----------------

In order to execute a query, it is *always* necessary to call the ``execute()``
method.

To get a better idea of how querying works let's look at some example queries
and their return values:

.. code-block:: pycon

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


.. _using_sql:

Writing queries by hand with SQL
--------------------------------

There are two ways to execute hand-crafted SQL statements with peewee:

1. :py:meth:`Database.execute_sql` for executing any type of query
2. :py:class:`RawQuery` for executing ``SELECT`` queries and *returning model instances*.

Example:

.. code-block:: python

    db = SqliteDatabase(':memory:')

    class Person(Model):
        name = CharField()
        class Meta:
            database = db

    # let's pretend we want to do an "upsert", something that SQLite can
    # do, but peewee cannot.
    for name in ('charlie', 'mickey', 'huey'):
        db.execute_sql('REPLACE INTO person (name) VALUES (?)', (name,))

    # now let's iterate over the people using our own query.
    for person in Person.raw('select * from person'):
        print person.name  # .raw() will return model instances.
