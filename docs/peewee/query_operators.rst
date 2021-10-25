.. _query-operators:

Query operators
===============

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
``^``            x XOR y
``~``            Unary negation (e.g., NOT x)
================ =======================================

Because I ran out of operators to override, there are some additional query
operations available as methods:

======================= ===============================================
Method                  Meaning
======================= ===============================================
``.in_(value)``         IN lookup (identical to ``<<``).
``.not_in(value)``      NOT IN lookup.
``.is_null(is_null)``   IS NULL or IS NOT NULL. Accepts boolean param.
``.contains(substr)``   Wild-card search for substring.
``.startswith(prefix)`` Search for values beginning with ``prefix``.
``.endswith(suffix)``   Search for values ending with ``suffix``.
``.between(low, high)`` Search for values between ``low`` and ``high``.
``.regexp(exp)``        Regular expression match (case-sensitive).
``.iregexp(exp)``       Regular expression match (case-insensitive).
``.bin_and(value)``     Binary AND.
``.bin_or(value)``      Binary OR.
``.concat(other)``      Concatenate two strings or objects using ``||``.
``.distinct()``         Mark column for DISTINCT selection.
``.collate(collation)`` Specify column with the given collation.
``.cast(type)``         Cast the value of the column to the given type.
======================= ===============================================

To combine clauses using logical operators, use:

================ ==================== ======================================================
Operator         Meaning              Example
================ ==================== ======================================================
``&``            AND                  ``(User.is_active == True) & (User.is_admin == True)``
``|`` (pipe)     OR                   ``(User.is_admin) | (User.is_superuser)``
``~``            NOT (unary negation) ``~(User.username.contains('admin'))``
================ ==================== ======================================================

Here is how you might use some of these query operators:

.. code-block:: python

    # Find the user whose username is "charlie".
    User.select().where(User.username == 'charlie')

    # Find the users whose username is in [charlie, huey, mickey]
    User.select().where(User.username.in_(['charlie', 'huey', 'mickey']))

    Employee.select().where(Employee.salary.between(50000, 60000))

    Employee.select().where(Employee.name.startswith('C'))

    Blog.select().where(Blog.title.contains(search_string))

Here is how you might combine expressions. Comparisons can be arbitrarily
complex.

.. note::
  Note that the actual comparisons are wrapped in parentheses. Python's operator
  precedence necessitates that comparisons be wrapped in parentheses.

.. code-block:: python

    # Find any users who are active administrations.
    User.select().where(
      (User.is_admin == True) &
      (User.is_active == True))

    # Find any users who are either administrators or super-users.
    User.select().where(
      (User.is_admin == True) |
      (User.is_superuser == True))

    # Find any Tweets by users who are not admins (NOT IN).
    admins = User.select().where(User.is_admin == True)
    non_admin_tweets = Tweet.select().where(Tweet.user.not_in(admins))

    # Find any users who are not my friends (strangers).
    friends = User.select().where(User.username.in_(['charlie', 'huey', 'mickey']))
    strangers = User.select().where(User.id.not_in(friends))

.. warning::
    Although you may be tempted to use python's ``in``, ``and``, ``or`` and
    ``not`` operators in your query expressions, these **will not work.** The
    return value of an ``in`` expression is always coerced to a boolean value.
    Similarly, ``and``, ``or`` and ``not`` all treat their arguments as boolean
    values and cannot be overloaded.

    So just remember:

    * Use ``.in_()`` and ``.not_in()`` instead of ``in`` and ``not in``
    * Use ``&`` instead of ``and``
    * Use ``|`` instead of ``or``
    * Use ``~`` instead of ``not``
    * Use ``.is_null()`` instead of ``is None`` or ``== None``.
    * **Don't forget to wrap your comparisons in parentheses when using logical operators.**

For more examples, see the :ref:`expressions` section.

.. note::
  **LIKE and ILIKE with SQLite**

  Because SQLite's ``LIKE`` operation is case-insensitive by default,
  peewee will use the SQLite ``GLOB`` operation for case-sensitive searches.
  The glob operation uses asterisks for wildcards as opposed to the usual
  percent-sign. If you are using SQLite and want case-sensitive partial
  string matching, remember to use asterisks for the wildcard.

Three valued logic
------------------

Because of the way SQL handles ``NULL``, there are some special operations
available for expressing:

* ``IS NULL``
* ``IS NOT NULL``
* ``IN``
* ``NOT IN``

While it would be possible to use the ``IS NULL`` and ``IN`` operators with the
negation operator (``~``), sometimes to get the correct semantics you will need
to explicitly use ``IS NOT NULL`` and ``NOT IN``.

The simplest way to use ``IS NULL`` and ``IN`` is to use the operator
overloads:

.. code-block:: python

    # Get all User objects whose last login is NULL.
    User.select().where(User.last_login >> None)

    # Get users whose username is in the given list.
    usernames = ['charlie', 'huey', 'mickey']
    User.select().where(User.username << usernames)

If you don't like operator overloads, you can call the Field methods instead:

.. code-block:: python

    # Get all User objects whose last login is NULL.
    User.select().where(User.last_login.is_null(True))

    # Get users whose username is in the given list.
    usernames = ['charlie', 'huey', 'mickey']
    User.select().where(User.username.in_(usernames))

To negate the above queries, you can use unary negation, but for the correct
semantics you may need to use the special ``IS NOT`` and ``NOT IN`` operators:

.. code-block:: python

    # Get all User objects whose last login is *NOT* NULL.
    User.select().where(User.last_login.is_null(False))

    # Using unary negation instead.
    User.select().where(~(User.last_login >> None))

    # Get users whose username is *NOT* in the given list.
    usernames = ['charlie', 'huey', 'mickey']
    User.select().where(User.username.not_in(usernames))

    # Using unary negation instead.
    usernames = ['charlie', 'huey', 'mickey']
    User.select().where(~(User.username << usernames))

.. _custom-operators:

Adding user-defined operators
-----------------------------

Because I ran out of python operators to overload, there are some missing
operators in peewee, for instance ``modulo``. If you find that you need to
support an operator that is not in the table above, it is very easy to add your
own.

Here is how you might add support for ``modulo`` in SQLite:

.. code-block:: python

    from peewee import *
    from peewee import Expression  # The building block for expressions.

    def mod(lhs, rhs):
        # Note: this works with Sqlite, but some drivers may use string-
        # formatting before sending the query to the database, so you may
        # need to use '%%' instead here.
        return Expression(lhs, '%', rhs)

Now you can use these custom operators to build richer queries:

.. code-block:: python

    # Users with even ids.
    User.select().where(mod(User.id, 2) == 0)

For more examples check out the source to the ``playhouse.postgresql_ext``
module, as it contains numerous operators specific to postgresql's hstore.

.. _expressions:

Expressions
-----------

Peewee is designed to provide a simple, expressive, and pythonic way of
constructing SQL queries. This section will provide a quick overview of some
common types of expressions.

There are two primary types of objects that can be composed to create
expressions:

* :py:class:`Field` instances
* SQL aggregations and functions using :py:class:`fn`

We will assume a simple "User" model with fields for username and other things.
It looks like this:

.. code-block:: python

    class User(Model):
        username = CharField()
        is_admin = BooleanField()
        is_active = BooleanField()
        last_login = DateTimeField()
        login_count = IntegerField()
        failed_logins = IntegerField()

Comparisons use the :ref:`query-operators`:

.. code-block:: python

    # username is equal to 'charlie'
    User.username == 'charlie'

    # user has logged in less than 5 times
    User.login_count < 5

Comparisons can be combined using **bitwise** *and* and *or*. Operator
precedence is controlled by python and comparisons can be nested to an
arbitrary depth:

.. code-block:: python

    # User is both and admin and has logged in today
    (User.is_admin == True) & (User.last_login >= today)

    # User's username is either charlie or charles
    (User.username == 'charlie') | (User.username == 'charles')

Comparisons can be used with functions as well:

.. code-block:: python

    # user's username starts with a 'g' or a 'G':
    fn.Lower(fn.Substr(User.username, 1, 1)) == 'g'

We can do some fairly interesting things, as expressions can be compared
against other expressions. Expressions also support arithmetic operations:

.. code-block:: python

    # users who entered the incorrect more than half the time and have logged
    # in at least 10 times
    (User.failed_logins > (User.login_count * .5)) & (User.login_count > 10)

Expressions allow us to do *atomic updates*:

.. code-block:: python

    # when a user logs in we want to increment their login count:
    User.update(login_count=User.login_count + 1).where(User.id == user_id)

Expressions can be used in all parts of a query, so experiment!

Row values
^^^^^^^^^^

Many databases support `row values <https://www.sqlite.org/rowvalue.html>`_,
which are similar to Python `tuple` objects. In Peewee, it is possible to use
row-values in expressions via :py:class:`Tuple`. For example,

.. code-block:: python

    # If for some reason your schema stores dates in separate columns ("year",
    # "month" and "day"), you can use row-values to find all rows that happened
    # in a given month:
    Tuple(Event.year, Event.month) == (2019, 1)

The more common use for row-values is to compare against multiple columns from
a subquery in a single expression. There are other ways to express these types
of queries, but row-values may offer a concise and readable approach.

For example, assume we have a table "EventLog" which contains an event type, an
event source, and some metadata. We also have an "IncidentLog", which has
incident type, incident source, and metadata columns. We can use row-values to
correlate incidents with certain events:

.. code-block:: python

    class EventLog(Model):
        event_type = TextField()
        source = TextField()
        data = TextField()
        timestamp = TimestampField()

    class IncidentLog(Model):
        incident_type = TextField()
        source = TextField()
        traceback = TextField()
        timestamp = TimestampField()

    # Get a list of all the incident types and sources that have occured today.
    incidents = (IncidentLog
                 .select(IncidentLog.incident_type, IncidentLog.source)
                 .where(IncidentLog.timestamp >= datetime.date.today()))

    # Find all events that correlate with the type and source of the
    # incidents that occured today.
    events = (EventLog
              .select()
              .where(Tuple(EventLog.event_type, EventLog.source).in_(incidents))
              .order_by(EventLog.timestamp))

Other ways to express this type of query would be to use a :ref:`join <relationships>`
or to :ref:`join on a subquery <join-subquery>`. The above example is there
just to give you and idea how :py:class:`Tuple` might be used.

You can also use row-values to update multiple columns in a table, when the new
data is derived from a subquery. For an example, see `here <https://www.sqlite.org/rowvalue.html#update_multiple_columns_of_a_table_based_on_a_query>`_.

SQL Functions
-------------

SQL functions, like ``COUNT()`` or ``SUM()``, can be expressed using the
:py:func:`fn` helper:

.. code-block:: python

    # Get all users and the number of tweets they've authored. Sort the
    # results from most tweets -> fewest tweets.
    query = (User
             .select(User, fn.COUNT(Tweet.id).alias('tweet_count'))
             .join(Tweet, JOIN.LEFT_OUTER)
             .group_by(User)
             .order_by(fn.COUNT(Tweet.id).desc()))
    for user in query:
        print('%s -- %s tweets' % (user.username, user.tweet_count))

The ``fn`` helper exposes any SQL function as if it were a method. The
parameters can be fields, values, subqueries, or even nested functions.

Nesting function calls
^^^^^^^^^^^^^^^^^^^^^^

Suppose you need to want to get a list of all users whose username begins with
*a*. There are a couple ways to do this, but one method might be to use some
SQL functions like *LOWER* and *SUBSTR*. To use arbitrary SQL functions, use
the special :py:func:`fn` object to construct queries:

.. code-block:: python

    # Select the user's id, username and the first letter of their username, lower-cased
    first_letter = fn.LOWER(fn.SUBSTR(User.username, 1, 1))
    query = User.select(User, first_letter.alias('first_letter'))

    # Alternatively we could select only users whose username begins with 'a'
    a_users = User.select().where(first_letter == 'a')

    >>> for user in a_users:
    ...    print(user.username)

SQL Helper
----------

There are times when you may want to simply pass in some arbitrary sql. You can
do this using the special :py:class:`SQL` class. One use-case is when
referencing an alias:

.. code-block:: python

    # We'll query the user table and annotate it with a count of tweets for
    # the given user
    query = (User
             .select(User, fn.Count(Tweet.id).alias('ct'))
             .join(Tweet)
             .group_by(User))

    # Now we will order by the count, which was aliased to "ct"
    query = query.order_by(SQL('ct'))

    # You could, of course, also write this as:
    query = query.order_by(fn.COUNT(Tweet.id))

There are two ways to execute hand-crafted SQL statements with peewee:

1. :py:meth:`Database.execute_sql` for executing any type of query
2. :py:class:`RawQuery` for executing ``SELECT`` queries and returning model
   instances.

Security and SQL Injection
--------------------------

By default peewee will parameterize queries, so any parameters passed in by the
user will be escaped. The only exception to this rule is if you are writing a
raw SQL query or are passing in a ``SQL`` object which may contain untrusted
data. To mitigate this, ensure that any user-defined data is passed in as a
query parameter and not part of the actual SQL query:

.. code-block:: python

    # Bad! DO NOT DO THIS!
    query = MyModel.raw('SELECT * FROM my_table WHERE data = %s' % (user_data,))

    # Good. `user_data` will be treated as a parameter to the query.
    query = MyModel.raw('SELECT * FROM my_table WHERE data = %s', user_data)

    # Bad! DO NOT DO THIS!
    query = MyModel.select().where(SQL('Some SQL expression %s' % user_data))

    # Good. `user_data` will be treated as a parameter.
    query = MyModel.select().where(SQL('Some SQL expression %s', user_data))

.. note::
    MySQL and Postgresql use ``'%s'`` to denote parameters. SQLite, on the
    other hand, uses ``'?'``. Be sure to use the character appropriate to your
    database. You can also find this parameter by checking
    :py:attr:`Database.param`.
