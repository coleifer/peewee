Querying API
============

Constructing queries
--------------------

Queries in peewee are constructed one piece at a time.

The "pieces" of a peewee query are generally representative of clauses you might
find in a SQL query.  All pieces are chainable so rather complex queries are
possible.

::

    >>> user_q = User.select() # <-- query is not executed
    >>> user_q
    <peewee.SelectQuery object at 0x7f6b0810c610>
    >>> [u.username for u in user_q] # <-- query is evaluated here
    [u'admin', u'staff', u'editor']


We can build up the query by adding some clauses to it::

    >>> user_q = user_q.where(username__in=['admin', 'editor']).order_by(('username', 'desc'))
    >>> [u.username for u in user_q] # <-- query is re-evaluated here
    [u'editor', u'admin']


Where clause
------------

All queries except ``InsertQuery`` support the ``where()`` method.  If you are
familiar with Django's ORM, it is analagous to the ``filter()`` method.

::

    >>> User.select().where(is_staff=True).sql()
    ('SELECT * FROM user WHERE is_staff = ?', [1])


.. note:: ``User.select()`` is equivalent to ``SelectQuery(User)``.

The ``where()`` method acts on the ``Model`` that is the current "context".
This is either:

* the model the query class was initialized with
* the model most recently JOINed on

Here is an example using JOINs::

    >>> User.select().where(is_staff=True).join(Blog).where(status=LIVE)

This query grabs all staff users who have a blog that is "LIVE".  This does the
opposite, grabs all the blogs that are live whose author is a staffer::

    >>> Blog.select().where(status=LIVE).join(User).where(is_staff=True)

.. note:: to ``join()`` from one model to another there must be a 
    ``ForeignKeyField`` linking the two.

Another way to write the above query would be::

    >>> Blog.select().where(status=LIVE, user__in=User.select().where(is_staff=True))

The above bears a little bit of explanation.  First off the SQL generated will
not perform any explicit JOINs - it will rather use a subquery in the WHERE 
clause::

    # using subqueries
    SELECT * FROM blog 
    WHERE (
        status = ? AND 
        user_id IN (
            SELECT t1.id FROM user AS t1 WHERE t1.is_staff = ?
        )
    )
    
    # using joins
    SELECT t1.* FROM blog AS t1 
    INNER JOIN user AS t2 
        ON t1.user_id = t2.id 
    WHERE 
        t1.status = ? AND 
        t2.is_staff = ?


The other bit that's unique about the query is that it specifies "user__in".
Users familiar with Django will recognize this syntax - lookups other than "="
are signified by a double-underscore followed by the lookup type.  The following
lookup types are available in peewee:

``__eq``:
    x = y, the default
    
``__lt``:
    x < y
    
``__lte``:
    x <= y

``__gt``:
    x > y

``__gte``:
    x >= y

``__ne``:
    x != y

``__is``:
    x IS y, used for testing against NULL values

``__contains``:
    case-sensitive check for substring

``__icontains``:
    case-insensitive check for substring

``__in``:
    x IN y, where y is either a list of values or a ``SelectQuery``


Performing advanced queries
^^^^^^^^^^^^^^^^^^^^^^^^^^^

As you may have noticed, all the examples up to now have shown queries that
combine multiple clauses with "AND".  Taking another page from Django's ORM,
peewee allows the creation of arbitrarily complex queries using a special
notation called **Q objects**.

::

    >>> sq = User.select().where(Q(is_staff=True) | Q(is_superuser=True))
    >>> print sq.sql()[0]
    SELECT * FROM user WHERE (is_staff = ? OR is_superuser = ?)


Q objects can be combined using the bitwise "or" and "and" operators.  In order
to negate a Q object, use the bitwise "invert" operator::

    >>> staff_users = User.select().where(is_staff=True)
    >>> Blog.select().where(~Q(user__in=staff_users))

This query generates the following SQL::

    SELECT * FROM blog 
    WHERE 
        NOT user_id IN (
            SELECT t1.id FROM user AS t1 WHERE t1.is_staff = ?
        )

Rather complex lookups are possible::

    >>> sq = User.select().where(
    ...     (Q(is_staff=True) | Q(is_superuser=True)) &
    ...     (Q(join_date__gte=datetime(2009, 1, 1)) | Q(join_date__lt=datetime(2005, 1 1)))
    ... )
    >>> print sq.sql()[0] # cleaned up
    SELECT * FROM user 
    WHERE (
        (is_staff = ? OR is_superuser = ?) AND 
        (join_date >= ? OR join_date < ?)
    )

This query selects all staff or super users who joined after 2009 or before
2005.


Query evaluation
----------------

In order to execute a query, it is *always* necessary to call the ``execute()``
method.

To get a better idea of how querying works let's look at some example queries
and their return values::

    >>> dq = User.delete().where(active=False) # <-- returns a DeleteQuery
    >>> dq
    <peewee.DeleteQuery object at 0x7fc866ada4d0>
    >>> dq.execute() # <-- executes the query and returns number of rows deleted
    3

    >>> uq = User.update(active=True).where(id__gt=3) # <-- returns an UpdateQuery
    >>> uq
    <peewee.UpdateQuery object at 0x7fc865beff50>
    >>> uq.execute() # <-- executes the query and returns number of rows updated
    2
    
    >>> iq = User.insert(username='new user') # <-- returns an InsertQuery
    >>> iq
    <peewee.InsertQuery object at 0x7fc865beff10>
    >>> iq.execute() # <-- executes query and returns the new row's PK
    3

    >>> sq = User.select().where(active=True) # <-- returns a SelectQuery
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


.. note:: iterating over a SelectQuery will cause it to be evaluated, but iterating
    over it multiple times will not result in the query being executed again.


QueryResultWrapper
------------------

As I hope the previous bit showed, Delete, Insert and Update queries are all
pretty straightforward.  Select queries are a little bit tricky in that they
return a special object called a ``QueryResultWrapper``.  The sole purpose of this
class is to allow the results of a query to be iterated over efficiently.  In
general it should not need to be dealt with explicitly.

The preferred method of iterating over a result set is to iterate directly over
the ``SelectQuery``, allowing it to manage the ``QueryResultWrapper`` internally.


SelectQuery
-----------

``SelectQuery`` is by far the most complex of the 4 query classes available in
peewee.  It supports JOINing on other tables, aggregation via GROUP BY and HAVING
clauses, ordering via ORDER BY, and can be sliced to return only a subset of
results.  All methods are chain-able.

.. py:method:: __init__(self, model, query=None)

    if no query is provided, it will default to '*'.  this parameter can be 
    either a dictionary or a string::
    
        >>> sq = SelectQuery(Blog, {Blog: ['id', 'title']})
        >>> sq = SelectQuery(Blog, {
        ...     Blog: ['*'], 
        ...     Entry: [peewee.Count('id')]
        ... }).group_by('id').join(Entry)
        >>> print sq.sql()[0] # formatted
        SELECT t1.*, COUNT(t2.id) AS count 
        FROM blog AS t1 
        INNER JOIN entry AS t2 
            ON t1.id = t2.blog_id
        GROUP BY t1.id
    
        >>> sq = SelectQuery(Blog, 'id, title')
        >>> print sq.sql()[0]
        SELECT id, title FROM blog

.. py:method:: where(self, *args, **kwargs)

    generate a WHERE clause for the current "query context".  *args is either
    a list of ``Q`` or ``Node`` objects, and **kwargs is a mapping of 
    column + lookup to value::
    
        >>> sq = SelectQuery(Blog).where(title='some title', author=some_user)
        >>> sq = SelectQuery(Blog).where(Q(title='some title') | Q(title='other title'))

.. py:method:: join(self, model, join_type=None, on=None)

    generate a JOIN clause from the current "query context" to the ``model`` passed
    in, and establishes ``model`` as the new "query context".
    
    :param model: the model to join on.  there must be a ``ForeignKeyField`` between
        the current "query context" and the model passed in.
    :param join_type: allows the type of JOIN used to be specified explicitly
    :param on: if multiple foreign keys exist between two models, this parameter
        is a string containing the name of the ForeignKeyField to join on.
    
    >>> sq = SelectQuery(Blog).join(Entry).where(title='Some Entry')
    >>> sq = SelectQuery(User).join(Relationship, on='to_user_id').where(from_user=self)

.. py:method:: switch(self, model)

    switches the "query context" to the given model.  raises an exception if the
    model has not been selected or joined on previously.
    
    >>> sq = SelectQuery(Blog).join(Entry).switch(Blog).where(title='Some Blog')

.. py:method:: count(self)

    returns an integer representing the number of rows in the current query
    
    >>> sq = SelectQuery(Blog)
    >>> sq.count()
    45 # <-- number of blogs
    >>> sq.where(status=DELETED)
    >>> sq.count()
    3 # <-- number of blogs that are marked as deleted

.. py:method:: group_by(self, field_name)

    adds field_name to the GROUP BY clause where field_name is a field on the
    current "query context"::
    
    >>> sq = Blog.select({
    ...     Blog: ['*'], 
    ...     Entry: [Count('id')]
    ... }).group_by('id').join(Entry)

.. py:method:: having(self, clause)

    adds the clause to the HAVING clause
    
    >>> sq = Blog.select({
    ...     Blog: ['*'], 
    ...     Entry: [Count('id', 'num_entries')]
    ... }).group_by('id').join(Entry).having('num_entries > 10')

.. py:method:: order_by(self, clause)
    
    adds the provided clause (a field name or alias) to the query's 
    ORDER BY clause.  if a field name is passed in, it must be a field on the
    current "query context", otherwise it is treated as an alias.  peewee also
    provides two convenience methods to allow ordering ascending or descending,
    called ``asc()`` and ``desc()``.
    
    example::
    
        >>> sq = Blog.select().order_by('title')
        >>> sq = Blog.select({
        ...     Blog: ['*'],
        ...     Entry: [Max('pub_date', 'max_pub')]
        ... }).join(Entry).order_by(desc('max_pub'))
    
    check out how the query context applies to ordering::
    
        >>> blog_title = Blog.select().order_by('title').join(Entry)
        >>> print blog_title.sql()[0]
        SELECT t1.* FROM blog AS t1
        INNER JOIN entry AS t2
            ON t1.id = t2.blog_id
        ORDER BY t1.title
        
        >>> entry_title = Blog.select().join(Entry).order_by('title')
        >>> print entry_title.sql()[0]
        SELECT t1.* FROM blog AS t1
        INNER JOIN entry AS t2
            ON t1.id = t2.blog_id
        ORDER BY t2.title # <-- note that it's using the title on Entry this time

.. py:method:: paginate(self, page_num, paginate_by=20)

    applies a LIMIT and OFFSET to the query.
    
    >>> Blog.select().order_by('username').paginate(3, 20) # <-- get blogs 41-60

.. py:method:: distinct(self)

    indicates that this query should only return distinct rows.  results in a
    SELECT DISTINCT query.

.. py:method:: execute(self)

    executes the query and returns a ``QueryResultWrapper`` for iterating over
    the result set.  the results are managed internally by the query and whenever
    a clause is added that would possibly alter the result set, the query is
    marked for re-execution.

.. py:method:: __iter__(self)

    executes the query::
    
        >>> for user in User.select().where(active=True):
        ...     print user.username


UpdateQuery
-----------

``UpdateQuery`` is fairly straightforward and is used for updating rows in the
database.

.. py:method:: __init__(self, model, **kwargs)

    creates an ``UpdateQuery`` instance for the given model.  "kwargs" is a dictionary
    of field: value pairs::
    
        >>> uq = UpdateQuery(User, active=False).where(registration_expired=True)
        >>> print uq.sql()
        ('UPDATE user SET active=? WHERE registration_expired = ?', [0, 1])

.. py:method:: execute(self)

    performs the query, returning the number of rows that were updated


DeleteQuery
-----------

``DeleteQuery`` deletes rows of the given model.  It will *not* traverse 
foreign keys or ensure that constraints are obeyed, so use it with care.

.. py:method:: __init__(self, model)

    creates a ``DeleteQuery`` instance for the given model::
    
        >>> dq = DeleteQuery(User).where(active=False)
        >>> print dq.sql()
        ('DELETE FROM user WHERE active = ?', [0])

.. py:method:: execute(self)

    performs the query, returning the number of rows that were deleted


InsertQuery
-----------

``InsertQuery`` creates a new row for the given model.

.. py:method:: __init__(self, model, **kwargs)

    creates an ``InsertQuery`` instance for the given model where kwargs is a
    dictionary of field name to value::
    
        >>> iq = InsertQuery(User, username='admin', password='test', active=True)
        >>> print iq.sql()
        ('INSERT INTO user (username, password, active) VALUES (?, ?, ?)', ['admin', 'test', 1])

.. py:method:: execute(self)

    performs the query, returning the primary key of the row that was added
