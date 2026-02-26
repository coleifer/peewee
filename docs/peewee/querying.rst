.. _querying:

Querying
========

This document covers reading data from the database: SELECT queries, filtering,
sorting, aggregation, and result-set iteration. Writing data (INSERT, UPDATE,
DELETE) is covered in :ref:`writing`.

All examples use the following models (see :ref:`models`):

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


.. seealso:: :ref:`Extensive library of SQL / Peewee examples <query-library>`

Selecting Records
-----------------

:meth:`Model.select` returns a :class:`Select` query. The query is lazy - the
database is not queried until you iterate over the result, index, slice or call
a method that forces execution.

.. code-block:: python

   # All users. No query issued yet.
   query = User.select()

   # Query executes here.
   for user in query:
       print(user.username)

Iterating over the same query object a second time does not re-query the
database: results are cached on the query object. To disable caching (for
example, when iterating over a large result set), use :meth:`~BaseQuery.iterator`:

.. code-block:: python

   for user in User.select().iterator():
       process(user)   # One row at a time, not cached.

To select specific columns rather than all columns, pass field expressions to
``select()``:

.. code-block:: python

   for user in User.select(User.username):
       print(user.username)
       # user.id is not populated - it was not selected.

To select columns from multiple models, pass both model classes or their
fields. Peewee reconstructs the model graph from the result set:

.. code-block:: python

   query = Tweet.select(Tweet, User).join(User)
   for tweet in query:
       # tweet.user is a fully populated User instance.
       # No extra query is issued.
       print(tweet.user.username, '->', tweet.content)

.. seealso::
   :ref:`relationships` covers joins in detail.


Retrieving a Single Record
--------------------------

:meth:`Model.get` executes the query and returns the first matching row.
If no row matches, :exc:`~Model.DoesNotExist` is raised:

.. code-block:: python

   user = User.get(User.username == 'charlie')

   # Equivalent long form:
   user = User.select().where(User.username == 'charlie').get()

:meth:`~Model.get_by_id` and the subscript operator are shortcuts for
primary-key lookups:

.. code-block:: python

   user = User.get_by_id(1)
   user = User[1]             # Same.

:meth:`~Model.get_or_none` returns ``None`` instead of raising an exception
when no row is found:

.. code-block:: python

   user = User.get_or_none(User.username == 'charlie')
   if user is None:
       print('Not found.')

:meth:`~SelectBase.first` returns the first row of a query, or ``None``:

.. code-block:: python

   latest = Tweet.select().order_by(Tweet.timestamp.desc()).first()

Get or Create
^^^^^^^^^^^^^

:meth:`~Model.get_or_create` retrieves a matching row, or creates it if it
does not exist. It returns a ``(instance, created)`` tuple:

.. code-block:: python

   user, created = User.get_or_create(username='charlie')
   if created:
       print('New user created.')

Use the ``defaults`` keyword to supply values that are only used during
creation, not as lookup keys:

.. code-block:: python

   user, created = User.get_or_create(
       username='charlie',
       defaults={'joined': datetime.date.today()})

When uniqueness is enforced by a database constraint, the recommended pattern
is to attempt creation first and fall back to retrieval on failure:

.. code-block:: python

   try:
       with db.atomic():
           return User.create(username=username)
   except IntegrityError:
       return User.get(User.username == username)

This avoids a race window between the lookup and the insert.

.. _filtering:

Filtering
---------

:meth:`~Query.where` accepts expressions built from field comparisons. Peewee
overloads Python's comparison operators to produce SQL expressions:

.. code-block:: python

   # Equality
   User.select().where(User.username == 'charlie')

   # Inequality
   Tweet.select().where(Tweet.is_published != False)

   # Comparison
   Tweet.select().where(Tweet.timestamp < datetime.datetime(2024, 1, 1))

.. warning::
   Peewee uses **bitwise** operators (``&`` and ``|``) rather than logical
   operators (``and`` and ``or``). The reason for this is that Python coerces
   the logical operations to a boolean value. This is also the reason why "IN"
   queries must be expressed using ``.in_()`` rather than the ``in`` operator.

.. seealso:: :ref:`Query operations <query-operators>` to see all operators.

Combine conditions with ``&`` (AND) and ``|`` (OR):

.. code-block:: python

   # Published tweets by charlie:
   query = (Tweet
            .select()
            .join(User)
            .where(
                (User.username == 'charlie') &
                (Tweet.is_published == True)))

   # Tweets by charlie OR huey:
   query = (Tweet
            .select()
            .join(User)
            .where(
                (User.username == 'charlie') |
                (User.username == 'huey')))

Negate a condition with ``~``:

.. code-block:: python

   # All users except charlie:
   User.select().where(~(User.username == 'charlie'))

Calling ``.where()`` multiple times on a query ANDs the conditions:

.. code-block:: python

   # Equivalent to WHERE is_published = 1 AND timestamp > ...
   query = (Tweet
            .select()
            .where(Tweet.is_published == True)
            .where(Tweet.timestamp > one_week_ago))

Common filtering methods
^^^^^^^^^^^^^^^^^^^^^^^^

============================================= ====================================
Method                                        SQL equivalent
============================================= ====================================
``User.username == 'charlie'``                ``username = 'charlie'``
``User.username != 'charlie'``                ``username != 'charlie'``
``Tweet.timestamp < dt``                      ``timestamp < dt``
``Tweet.timestamp >= dt``                     ``timestamp >= dt``
``Tweet.timestamp.between(start, end)``       ``timestamp BETWEEN start AND end``
``User.username.in_(['a', 'b'])``             ``username IN ('a', 'b')``
``User.username.not_in(['a', 'b'])``          ``username NOT IN ...``
``User.username.contains('char')``            ``username LIKE '%char%'``
``User.username.startswith('ch')``            ``username LIKE 'ch%'``
``User.username.endswith('ie')``              ``username LIKE '%ie'``
``User.username.regexp(r'^[a-z]+$')``         ``username REGEXP ...``
``User.username.is_null()``                   ``username IS NULL``
``User.username.is_null(False)``              ``username IS NOT NULL``
============================================= ====================================

.. note::
   ``IN`` queries must use ``.in_()`` rather than Python's ``in`` operator,
   because Python's ``in`` returns a boolean and cannot be overridden.

.. seealso::
   :ref:`query-operators` for the full list of supported operators and methods.

SQL functions
^^^^^^^^^^^^^

The :class:`fn` helper calls any SQL function by name:

.. code-block:: python

   from peewee import fn

   # Users whose username starts with a vowel (case-insensitive).
   vowels = ('a', 'e', 'i', 'o', 'u')
   query = User.select().where(
       fn.LOWER(fn.SUBSTR(User.username, 1, 1)).in_(vowels))

   # Tweets whose content is less than 10 characters long.
   query = Tweet.select().where(
       fn.LENGTH(Tweet.content) < 10)


Sorting
-------

:meth:`~Query.order_by` specifies the column(s) to sort by:

.. code-block:: python

   # Ascending (default).
   Tweet.select().order_by(Tweet.timestamp)

   # Descending.
   Tweet.select().order_by(Tweet.timestamp.desc())

   # Using the + / - prefix operators:
   Tweet.select().order_by(+Tweet.timestamp)     # Ascending.
   Tweet.select().order_by(-Tweet.timestamp)     # Descending.

Sort on multiple columns by passing multiple arguments:

.. code-block:: python

   query = (Tweet
            .select()
            .join(User)
            .order_by(User.username, Tweet.timestamp.desc()))

Sorting by a calculated or aliased value
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When ordering by an aggregate or expression that appears in ``select()``,
reference it by re-using the expression or by wrapping the alias in
:class:`SQL`:

.. code-block:: python

   tweet_count = fn.COUNT(Tweet.id)

   query = (User
            .select(User.username, tweet_count.alias('num_tweets'))
            .join(Tweet, JOIN.LEFT_OUTER)
            .group_by(User.username)
            .order_by(tweet_count.desc()))

   # Alternatively, reference the alias string via SQL():
   query = (User
            .select(User.username, fn.COUNT(Tweet.id).alias('num_tweets'))
            .join(Tweet, JOIN.LEFT_OUTER)
            .group_by(User.username)
            .order_by(SQL('num_tweets').desc()))

Random ordering
^^^^^^^^^^^^^^^

:meth:`Database.random` provides a database-specific implementation of the
random function, which can be used for ordering:

.. code-block:: python

   # Select 5 random winners.
   LotteryEntry.select().order_by(db.random()).limit(5)


Pagination, Limiting, and Offsetting
--------------------------------------

:meth:`~Query.limit` and :meth:`~Query.offset` map directly to SQL:

.. code-block:: python

   # First 10 rows.
   Tweet.select().order_by(Tweet.id).limit(10)

   # Rows 11-20.
   Tweet.select().order_by(Tweet.id).limit(10).offset(10)

:meth:`~Query.paginate` is a convenience wrapper:

.. code-block:: python

   # Page 3, 20 items per page (rows 41-60).
   Tweet.select().order_by(Tweet.id).paginate(3, 20)

.. attention::
   Page numbers are 1-based. Page 1 returns the first ``items_per_page`` rows.


Counting
--------

:meth:`~SelectBase.count` wraps the query in a ``SELECT COUNT(1) FROM (...)``
and returns an integer:

.. code-block:: python

   total = Tweet.select().count()
   published = Tweet.select().where(Tweet.is_published == True).count()


Aggregates and GROUP BY
------------------------

Use :class:`fn` to call aggregate functions and :meth:`~Select.group_by`
to group:

.. code-block:: python

   query = (User
            .select(User.username, fn.COUNT(Tweet.id).alias('tweet_count'))
            .join(Tweet, JOIN.LEFT_OUTER)
            .group_by(User.username)
            .order_by(SQL('tweet_count').desc()))

   for user in query:
       print(user.username, user.tweet_count)

Filter groups with :meth:`~Select.having`:

.. code-block:: python

   # Users with more than 5 published tweets.
   query = (User
            .select(User.username, fn.COUNT(Tweet.id).alias('n'))
            .join(Tweet)
            .where(Tweet.is_published == True)
            .group_by(User.username)
            .having(fn.COUNT(Tweet.id) > 5))


Scalar Values
-------------

:meth:`~SelectBase.scalar` executes a query and returns the first column of the
first row as a Python value. Use it when a query produces a single number or
string:

.. code-block:: python

   oldest = Tweet.select(fn.MIN(Tweet.timestamp)).scalar()
   distinct_users = Tweet.select(fn.COUNT(Tweet.user.distinct())).scalar()

Pass ``as_tuple=True`` to retrieve multiple scalar columns:

.. code-block:: python

   min_ts, max_ts = Tweet.select(
       fn.MIN(Tweet.timestamp),
       fn.MAX(Tweet.timestamp)
   ).scalar(as_tuple=True)

.. _row-types:

Row Types
---------

By default, SELECT queries return model instances. Four alternative row types
are available by chaining a method before iteration:

* :meth:`~BaseQuery.dicts`
* :meth:`~BaseQuery.tuples`
* :meth:`~BaseQuery.namedtuples`
* :meth:`~BaseQuery.objects`

Example:

.. code-block:: python

   # Dictionaries.
   for row in User.select().dicts():
       print(row)   # {'id': 1, 'username': 'charlie'}

   # Tuples.
   for row in User.select().tuples():
       print(row)   # (1, 'charlie')

   # Named tuples.
   for row in User.select().namedtuples():
       print(row.username)

   # Flatten any related data and return model instances.
   for row in User.select().objects():
       print(row.username)

   # Or pass a constructor callable.
   for row in User.select().objects(MyUserClass):
       print(row.my_username)

Using tuples or dicts instead of model instances is faster for queries that
produce many rows, because Peewee skips constructing model objects.

``objects()`` without an argument returns model instances but does not
reconstruct the model graph from joined data, assigning all columns directly
onto the primary model. This avoids the overhead of graph reconstruction when
you have joined data and don't need nested model instances.

.. _large-results:

Iterating Over Large Result Sets
----------------------------------

For queries returning many rows, disable result caching with
:meth:`~BaseQuery.iterator` to keep memory usage flat:

.. code-block:: python

   # Combine iterator() with tuples() for maximum throughput.
   query = (Stat
            .select()
            .tuples()
            .iterator())

   for stat_tuple in query:
       write_to_file(stat_tuple)

When iterating over joined queries with ``.iterator()``, use ``.objects()``
to avoid the overhead of model-graph reconstruction per row:

.. code-block:: python

   query = (Tweet
            .select(Tweet.content, User.username)
            .join(User)
            .objects()
            .iterator())

   for tweet in query:
       print(tweet.username, tweet.content)

For maximum performance, execute the query and iterate the cursor directly:

.. code-block:: python

   query = Tweet.select(Tweet.content, User.username).join(User)
   cursor = db.execute(query)
   for content, username in cursor:
       print(username, '->', content)


.. _window-functions:

Window Functions
----------------

A :class:`Window` function refers to an aggregate function that operates on
a sliding window of data that is being processed as part of a ``SELECT`` query.
Window functions make it possible to do things like:

1. Perform aggregations against subsets of a result-set.
2. Calculate a running total.
3. Rank results.
4. Compare a row value to a value in the preceding (or succeeding!) row(s).

peewee comes with support for SQL window functions, which can be created by
calling :meth:`Function.over` and passing in your partitioning or ordering
parameters.

For the following examples, we'll use the following model and sample data:

.. code-block:: python

   class Sample(Model):
       counter = IntegerField()
       value = FloatField()

   data = [(1, 10),
           (1, 20),
           (2, 1),
           (2, 3),
           (3, 100)]
   Sample.insert_many(data, fields=[Sample.counter, Sample.value]).execute()

Our sample table now contains:

=== ======== ======
id  counter  value
=== ======== ======
1   1        10.0
2   1        20.0
3   2        1.0
4   2        3.0
5   3        100.0
=== ======== ======

Ordered Windows
^^^^^^^^^^^^^^^

Let's calculate a running sum of the ``value`` field. In order for it to be a
"running" sum, we need it to be ordered, so we'll order with respect to the
Sample's ``id`` field:

.. code-block:: python

   query = Sample.select(
       Sample.counter,
       Sample.value,
       fn.SUM(Sample.value).over(order_by=[Sample.id]).alias('total'))

   for sample in query:
       print(sample.counter, sample.value, sample.total)

   # 1    10.    10.
   # 1    20.    30.
   # 2     1.    31.
   # 2     3.    34.
   # 3   100    134.

For another example, we'll calculate the difference between the current value
and the previous value, when ordered by the ``id``:

.. code-block:: python

   difference = Sample.value - fn.LAG(Sample.value, 1).over(order_by=[Sample.id])
   query = Sample.select(
       Sample.counter,
       Sample.value,
       difference.alias('diff'))

   for sample in query:
       print(sample.counter, sample.value, sample.diff)

   # 1    10.   NULL
   # 1    20.    10.  -- (20 - 10)
   # 2     1.   -19.  -- (1 - 20)
   # 2     3.     2.  -- (3 - 1)
   # 3   100     97.  -- (100 - 3)

Partitioned Windows
^^^^^^^^^^^^^^^^^^^

Let's calculate the average ``value`` for each distinct "counter" value. Notice
that there are three possible values for the ``counter`` field (1, 2, and 3).
We can do this by calculating the ``AVG()`` of the ``value`` column over a
window that is partitioned depending on the ``counter`` field:

.. code-block:: python

   query = Sample.select(
       Sample.counter,
       Sample.value,
       fn.AVG(Sample.value).over(partition_by=[Sample.counter]).alias('cavg'))

   for sample in query:
       print(sample.counter, sample.value, sample.cavg)

   # 1    10.    15.
   # 1    20.    15.
   # 2     1.     2.
   # 2     3.     2.
   # 3   100    100.

We can use ordering within partitions by specifying both the ``order_by`` and
``partition_by`` parameters. For an example, let's rank the samples by value
within each distinct ``counter`` group.

.. code-block:: python

   query = Sample.select(
       Sample.counter,
       Sample.value,
       fn.RANK().over(
           order_by=[Sample.value],
           partition_by=[Sample.counter]).alias('rank'))

   for sample in query:
       print(sample.counter, sample.value, sample.rank)

   # 1    10.    1
   # 1    20.    2
   # 2     1.    1
   # 2     3.    2
   # 3   100     1

Bounded Windows
^^^^^^^^^^^^^^^

By default, window functions are evaluated using an *unbounded preceding* start
for the window, and the *current row* as the end. We can change the bounds of
the window our aggregate functions operate on by specifying a ``start`` and/or
``end`` in the call to :meth:`Function.over`. Additionally, Peewee comes
with helper-methods on the :class:`Window` object for generating the
appropriate boundary references:

* :attr:`Window.CURRENT_ROW` - attribute that references the current row.
* :meth:`Window.preceding` - specify number of row(s) preceding, or omit
  number to indicate **all** preceding rows.
* :meth:`Window.following` - specify number of row(s) following, or omit
  number to indicate **all** following rows.

To examine how boundaries work, we'll calculate a running total of the
``value`` column, ordered with respect to ``id``, **but** we'll only look the
running total of the current row and it's two preceding rows:

.. code-block:: python

   query = Sample.select(
       Sample.counter,
       Sample.value,
       fn.SUM(Sample.value).over(
           order_by=[Sample.id],
           start=Window.preceding(2),
           end=Window.CURRENT_ROW).alias('rsum'))

   for sample in query:
       print(sample.counter, sample.value, sample.rsum)

   # 1    10.    10.
   # 1    20.    30.  -- (20 + 10)
   # 2     1.    31.  -- (1 + 20 + 10)
   # 2     3.    24.  -- (3 + 1 + 20)
   # 3   100    104.  -- (100 + 3 + 1)

.. note::
   Technically we did not need to specify the ``end=Window.CURRENT`` because
   that is the default. It was shown in the example for demonstration.

Let's look at another example. In this example we will calculate the "opposite"
of a running total, in which the total sum of all values is decreased by the
value of the samples, ordered by ``id``. To accomplish this, we'll calculate
the sum from the current row to the last row.

.. code-block:: python

   query = Sample.select(
       Sample.counter,
       Sample.value,
       fn.SUM(Sample.value).over(
           order_by=[Sample.id],
           start=Window.CURRENT_ROW,
           end=Window.following()).alias('rsum'))

   # 1    10.   134.  -- (10 + 20 + 1 + 3 + 100)
   # 1    20.   124.  -- (20 + 1 + 3 + 100)
   # 2     1.   104.  -- (1 + 3 + 100)
   # 2     3.   103.  -- (3 + 100)
   # 3   100    100.  -- (100)

Filtered Aggregates
^^^^^^^^^^^^^^^^^^^

Aggregate functions may also support filter functions (Postgres and Sqlite
3.25+), which get translated into a ``FILTER (WHERE...)`` clause. Filter
expressions are added to an aggregate function with the
:meth:`Function.filter` method.

For an example, we will calculate the running sum of the ``value`` field with
respect to the ``id``, but we will filter-out any samples whose ``counter=2``.

.. code-block:: python

   query = Sample.select(
       Sample.counter,
       Sample.value,
       fn.SUM(Sample.value).filter(Sample.counter != 2).over(
           order_by=[Sample.id]).alias('csum'))

   for sample in query:
       print(sample.counter, sample.value, sample.csum)

   # 1    10.    10.
   # 1    20.    30.
   # 2     1.    30.
   # 2     3.    30.
   # 3   100    130.

.. note::
   The call to :meth:`~Function.filter` must precede the call to
   :meth:`~Function.over`.

Reusing Window Definitions
^^^^^^^^^^^^^^^^^^^^^^^^^^

If you intend to use the same window definition for multiple aggregates, you
can create a :class:`Window` object. The :class:`Window` object takes the
same parameters as :meth:`Function.over`, and can be passed to the
``over()`` method in-place of the individual parameters.

Here we'll declare a single window, ordered with respect to the sample ``id``,
and call several window functions using that window definition:

.. code-block:: python

   win = Window(order_by=[Sample.id])
   query = Sample.select(
       Sample.counter,
       Sample.value,
       fn.LEAD(Sample.value).over(win),
       fn.LAG(Sample.value).over(win),
       fn.SUM(Sample.value).over(win)
   ).window(win)  # Include our window definition in query.

   for row in query.tuples():
       print(row)

   # counter  value  lead()  lag()  sum()
   # 1          10.     20.   NULL    10.
   # 1          20.      1.    10.    30.
   # 2           1.      3.    20.    31.
   # 2           3.    100.     1.    34.
   # 3         100.    NULL     3.   134.

Multiple Window Definitions
^^^^^^^^^^^^^^^^^^^^^^^^^^^

In the previous example, we saw how to declare a :class:`Window` definition
and re-use it for multiple different aggregations. You can include as many
window definitions as you need in your queries, but it is necessary to ensure
each window has a unique alias:

.. code-block:: python

   w1 = Window(order_by=[Sample.id]).alias('w1')
   w2 = Window(partition_by=[Sample.counter]).alias('w2')
   query = Sample.select(
       Sample.counter,
       Sample.value,
       fn.SUM(Sample.value).over(w1).alias('rsum'),  # Running total.
       fn.AVG(Sample.value).over(w2).alias('cavg')   # Avg per category.
   ).window(w1, w2)  # Include our window definitions.

   for sample in query:
       print(sample.counter, sample.value, sample.rsum, sample.cavg)

   # counter  value   rsum     cavg
   # 1          10.     10.     15.
   # 1          20.     30.     15.
   # 2           1.     31.      2.
   # 2           3.     34.      2.
   # 3         100     134.    100.

Similarly, if you have multiple window definitions that share similar
definitions, it is possible to extend a previously-defined window definition.
For example, here we will be partitioning the data-set by the counter value, so
we'll be doing our aggregations with respect to the counter. Then we'll define
a second window that extends this partitioning, and adds an ordering clause:

.. code-block:: python

   w1 = Window(partition_by=[Sample.counter]).alias('w1')

   # By extending w1, this window definition will also be partitioned
   # by "counter".
   w2 = Window(extends=w1, order_by=[Sample.value.desc()]).alias('w2')

   query = (Sample
            .select(Sample.counter, Sample.value,
                    fn.SUM(Sample.value).over(w1).alias('group_sum'),
                    fn.RANK().over(w2).alias('revrank'))
            .window(w1, w2)
            .order_by(Sample.id))

   for sample in query:
       print(sample.counter, sample.value, sample.group_sum, sample.revrank)

   # counter  value   group_sum   revrank
   # 1        10.     30.         2
   # 1        20.     30.         1
   # 2        1.      4.          2
   # 2        3.      4.          1
   # 3        100.    100.        1

.. _window-frame-types:

Frame Types: RANGE vs ROWS vs GROUPS
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Depending on the frame type, the database will process ordered groups
differently. Let's create two additional ``Sample`` rows to visualize the
difference:

.. code-block:: pycon

   >>> Sample.create(counter=1, value=20.)
   <Sample 6>
   >>> Sample.create(counter=2, value=1.)
   <Sample 7>

Our table now contains:

=== ======== ======
id  counter  value
=== ======== ======
1   1        10.0
2   1        20.0
3   2        1.0
4   2        3.0
5   3        100.0
6   1        20.0
7   2        1.0
=== ======== ======

Let's examine the difference by calculating a "running sum" of the samples,
ordered with respect to the ``counter`` and ``value`` fields. To specify the
frame type, we can use either:

* :attr:`Window.RANGE`
* :attr:`Window.ROWS`
* :attr:`Window.GROUPS`

The behavior of :attr:`~Window.RANGE`, when there are logical duplicates,
may lead to unexpected results:

.. code-block:: python

   query = Sample.select(
       Sample.counter,
       Sample.value,
       fn.SUM(Sample.value).over(
           order_by=[Sample.counter, Sample.value],
           frame_type=Window.RANGE).alias('rsum'))

   for sample in query.order_by(Sample.counter, Sample.value):
       print(sample.counter, sample.value, sample.rsum)

   # counter  value   rsum
   # 1          10.     10.
   # 1          20.     50.
   # 1          20.     50.
   # 2           1.     52.
   # 2           1.     52.
   # 2           3.     55.
   # 3         100     155.

With the inclusion of the new rows we now have some rows that have duplicate
``category`` and ``value`` values. The :attr:`~Window.RANGE` frame type
causes these duplicates to be evaluated together rather than separately.

The more expected result can be achieved by using :attr:`~Window.ROWS` as
the frame-type:

.. code-block:: python

   query = Sample.select(
       Sample.counter,
       Sample.value,
       fn.SUM(Sample.value).over(
           order_by=[Sample.counter, Sample.value],
           frame_type=Window.ROWS).alias('rsum'))

   for sample in query.order_by(Sample.counter, Sample.value):
       print(sample.counter, sample.value, sample.rsum)

   # counter  value   rsum
   # 1          10.     10.
   # 1          20.     30.
   # 1          20.     50.
   # 2           1.     51.
   # 2           1.     52.
   # 2           3.     55.
   # 3         100     155.

Peewee uses these rules for determining what frame-type to use:

* If the user specifies a ``frame_type``, that frame type will be used.
* If ``start`` and/or ``end`` boundaries are specified Peewee will default to
  using ``ROWS``.
* If the user did not specify frame type or start/end boundaries, Peewee will
  use the database default, which is ``RANGE``.

The :attr:`Window.GROUPS` frame type looks at the window range specification
in terms of groups of rows, based on the ordering term(s). Using ``GROUPS``, we
can define the frame so it covers distinct groupings of rows. Let's look at an
example:

.. code-block:: python

   query = (Sample
            .select(Sample.counter, Sample.value,
                    fn.SUM(Sample.value).over(
                       order_by=[Sample.counter, Sample.value],
                       frame_type=Window.GROUPS,
                       start=Window.preceding(1)).alias('gsum'))
            .order_by(Sample.counter, Sample.value))

   for sample in query:
       print(sample.counter, sample.value, sample.gsum)

   #  counter   value    gsum
   #  1         10       10
   #  1         20       50
   #  1         20       50   (10) + (20+0)
   #  2         1        42
   #  2         1        42   (20+20) + (1+1)
   #  2         3        5    (1+1) + 3
   #  3         100      103  (3) + 100

As you can hopefully infer, the window is grouped by its ordering term, which
is ``(counter, value)``. We are looking at a window that extends between one
previous group and the current group.

.. note::
   For information about the window function APIs, see:

   * :meth:`Function.over`
   * :meth:`Function.filter`
   * :class:`Window`

   For general information on window functions, read the postgres `window functions tutorial <https://www.postgresql.org/docs/current/tutorial-window.html>`_

   Additionally, the `postgres docs <https://www.postgresql.org/docs/current/sql-select.html#SQL-WINDOW>`_
   and the `sqlite docs <https://www.sqlite.org/windowfunctions.html>`_
   contain a lot of good information.

.. _cte:

Common Table Expressions
------------------------

A CTE factors out a subquery and gives it a name, making complex queries more
readable and sometimes more efficient. CTEs also support recursion.

Define a CTE with :meth:`~SelectQuery.cte` and include it with
:meth:`~Query.with_cte`:

Simple Example
^^^^^^^^^^^^^^

For an example, let's say we have some data points that consist of a key and a
floating-point value. Let's define our model and populate some test data:

.. code-block:: python

   class Sample(Model):
       key = TextField()
       value = FloatField()

   data = (
       ('a', (1.25, 1.5, 1.75)),
       ('b', (2.1, 2.3, 2.5, 2.7, 2.9)),
       ('c', (3.5, 3.5)))

   # Populate data.
   for key, values in data:
       Sample.insert_many([(key, value) for value in values],
                          fields=[Sample.key, Sample.value]).execute()

Let's use a CTE to calculate, for each distinct key, which values were
above-average for that key.

.. code-block:: python

   # First we'll declare the query that will be used as a CTE. This query
   # simply determines the average value for each key.
   cte = (Sample
          .select(Sample.key, fn.AVG(Sample.value).alias('avg_value'))
          .group_by(Sample.key)
          .cte('key_avgs', columns=('key', 'avg_value')))

   # Now we'll query the sample table, using our CTE to find rows whose value
   # exceeds the average for the given key. We'll calculate how far above the
   # average the given sample's value is, as well.
   query = (Sample
            .select(Sample.key, Sample.value)
            .join(cte, on=(Sample.key == cte.c.key))
            .where(Sample.value > cte.c.avg_value)
            .order_by(Sample.value)
            .with_cte(cte))

We can iterate over the samples returned by the query to see which samples had
above-average values for their given group:

.. code-block:: pycon

   >>> for sample in query:
   ...     print(sample.key, sample.value)

   # 'a', 1.75
   # 'b', 2.7
   # 'b', 2.9

Complex Example
^^^^^^^^^^^^^^^

For a more complete example, let's consider the following query which uses
multiple CTEs to find per-product sales totals in only the top sales regions.
Our model looks like this:

.. code-block:: python

   class Order(Model):
       region = TextField()
       amount = FloatField()
       product = TextField()
       quantity = IntegerField()

Here is how the query might be written in SQL. This example can be found in
the `postgresql documentation <https://www.postgresql.org/docs/current/static/queries-with.html>`_.

.. code-block:: sql

   WITH regional_sales AS (
       SELECT region, SUM(amount) AS total_sales
       FROM orders
       GROUP BY region
     ), top_regions AS (
       SELECT region
       FROM regional_sales
       WHERE total_sales > (SELECT SUM(total_sales) / 10 FROM regional_sales)
     )
   SELECT region,
          product,
          SUM(quantity) AS product_units,
          SUM(amount) AS product_sales
   FROM orders
   WHERE region IN (SELECT region FROM top_regions)
   GROUP BY region, product;

With Peewee, we would write:

.. code-block:: python

   reg_sales = (Order
                .select(Order.region,
                        fn.SUM(Order.amount).alias('total_sales'))
                .group_by(Order.region)
                .cte('regional_sales'))

   top_regions = (reg_sales
                  .select(reg_sales.c.region)
                  .where(reg_sales.c.total_sales > (
                      reg_sales.select(fn.SUM(reg_sales.c.total_sales) / 10)))
                  .cte('top_regions'))

   query = (Order
            .select(Order.region,
                    Order.product,
                    fn.SUM(Order.quantity).alias('product_units'),
                    fn.SUM(Order.amount).alias('product_sales'))
            .where(Order.region.in_(top_regions.select(top_regions.c.region)))
            .group_by(Order.region, Order.product)
            .with_cte(reg_sales, top_regions))

Recursive CTEs
^^^^^^^^^^^^^^

Peewee supports recursive CTEs. Recursive CTEs can be useful when, for example,
you have a tree data-structure represented by a parent-link foreign key.
Suppose, for example, that we have a hierarchy of categories for an online
bookstore. We wish to generate a table showing all categories and their
absolute depths, along with the path from the root to the category.

We'll assume the following model definition, in which each category has a
foreign-key to its immediate parent category:

.. code-block:: python

   class Category(Model):
       name = TextField()
       parent = ForeignKeyField('self', backref='children', null=True)

To list all categories along with their depth and parents, we can use a
recursive CTE:

.. code-block:: python

   # Define the base case of our recursive CTE. This will be categories that
   # have a null parent foreign-key.
   Base = Category.alias()
   level = Value(1).alias('level')
   path = Base.name.alias('path')
   base_case = (Base
                .select(Base.id, Base.name, Base.parent, level, path)
                .where(Base.parent.is_null())
                .cte('base', recursive=True))

   # Define the recursive terms.
   RTerm = Category.alias()
   rlevel = (base_case.c.level + 1).alias('level')
   rpath = base_case.c.path.concat('->').concat(RTerm.name).alias('path')
   recursive = (RTerm
                .select(RTerm.id, RTerm.name, RTerm.parent, rlevel, rpath)
                .join(base_case, on=(RTerm.parent == base_case.c.id)))

   # The recursive CTE is created by taking the base case and UNION ALL with
   # the recursive term.
   cte = base_case.union_all(recursive)

   # We will now query from the CTE to get the categories, their levels,  and
   # their paths.
   query = (cte
            .select_from(cte.c.name, cte.c.level, cte.c.path)
            .order_by(cte.c.path))

   # We can now iterate over a list of all categories and print their names,
   # absolute levels, and path from root -> category.
   for category in query:
       print(category.name, category.level, category.path)

   # Example output:
   # root, 1, root
   # p1, 2, root->p1
   # c1-1, 3, root->p1->c1-1
   # c1-2, 3, root->p1->c1-2
   # p2, 2, root->p2
   # c2-1, 3, root->p2->c2-1

Data-Modifying CTE
^^^^^^^^^^^^^^^^^^

Peewee supports data-modifying CTE's.

Example of using a data-modifying CTE to move data from one table to an archive
table, using a single query:

.. code-block:: python

   class Event(Model):
       name = CharField()
       timestamp = DateTimeField()

   class Archive(Model):
       name = CharField()
       timestamp = DateTimeField()

   # Move rows older than 24 hours from the Event table to the Archive.
   cte = (Event
          .delete()
          .where(Event.timestamp < (datetime.now() - timedelta(days=1)))
          .returning(Event)
          .cte('moved_rows'))

   # Create a simple SELECT to get the resulting rows from the CTE.
   src = Select((cte,), (cte.c.id, cte.c.name, cte.c.timestamp))

   # Insert into the archive table whatever data was returned by the DELETE.
   res = (Archive
          .insert_from(src, (Archive.id, Archive.name, Archive.timestamp))
          .with_cte(cte)
          .execute())

The above corresponds to, roughly, the following SQL:

.. code-block:: sql

   WITH "moved_rows" AS (
       DELETE FROM "event" WHERE ("timestamp" < XXXX-XX-XXTXX:XX:XX)
       RETURNING "id", "name", "timestamp")
   INSERT INTO "archive" ("id", "name", "timestamp")
   SELECT "moved_rows"."id", "moved_rows"."name", "moved_rows"."timestamp"
   FROM "moved_rows";

For additional examples, refer to the tests in ``models.py`` and ``sql.py``:

* https://github.com/coleifer/peewee/blob/master/tests/models.py
* https://github.com/coleifer/peewee/blob/master/tests/sql.py
