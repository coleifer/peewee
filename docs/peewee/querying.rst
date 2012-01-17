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

    >>> user_q = user_q.where(username__in=['admin', 'editor'])
    >>> user_q = user_q.order_by(('username', 'desc'))
    >>> [u.username for u in user_q] # <-- query is re-evaluated here
    [u'editor', u'admin']


Django-style queries
^^^^^^^^^^^^^^^^^^^^

If you are already familiar with the Django ORM, you can construct :py:class:`SelectQuery` instances
using the familiar "double-underscore" syntax to generate the proper ``JOINs`` and
``WHERE`` clauses.


Comparing the two methods of querying
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Get active users:
    .. code-block:: python
    
        User.select().where(active=True)
    
        User.filter(active=True)

Get users who are either staff or superusers:
    .. code-block:: python
    
        User.select().where(Q(is_staff=True) | Q(is_superuser=True))
    
        User.filter(Q(is_staff=True) | Q(is_superuser=True))

Get tweets by user named "charlie":
    .. code-block:: python
    
        Tweet.select().join(User).where(username='charlie')
    
        Tweet.filter(user__username='charlie')

Get tweets by staff or superusers (assumes FK relationship):
    .. code-block:: python
    
        Tweet.select().join(User).where(
            Q(is_staff=True) | Q(is_superuser=True)
        )
    
        Tweet.filter(Q(user__is_staff=True) | Q(user__is_superuser=True))


Where clause
------------

All queries except :py:class:`InsertQuery` support the ``where()`` method.  If you are
familiar with Django's ORM, it is analagous to the ``filter()`` method.

.. code-block:: python

    >>> User.select().where(is_staff=True).sql()
    ('SELECT * FROM user WHERE is_staff = ?', [1])


.. note:: ``User.select()`` is equivalent to ``SelectQuery(User)``.

The ``where()`` method acts on the :py:class:`Model` that is the current "query context".
This is either:

* the model the query class was initialized with
* the model most recently JOINed on

Here is an example using JOINs:

.. code-block:: python

    >>> User.select().where(is_staff=True).join(Blog).where(status=LIVE)

This query grabs all staff users who have a blog that is "LIVE".  This does the
opposite, grabs all the blogs that are live whose author is a staffer:

.. code-block:: python

    >>> Blog.select().where(status=LIVE).join(User).where(is_staff=True)

.. note::
    to :py:meth:`~SelectQuery.join` from one model to another there must be a :py:class:`ForeignKeyField` linking the two.

Another way to write the above query would be:

.. code-block:: python

    >>> Blog.select().where(
    ...     status=LIVE,
    ...     user__in=User.select().where(is_staff=True)
    ... )

The above bears a little bit of explanation.  First off the SQL generated will
not perform any explicit ``JOIN`` - it will rather use a subquery in the ``WHERE``
clause:

.. code-block:: sql

    # using subqueries
    SELECT * FROM blog 
    WHERE (
        status = ? AND 
        user_id IN (
            SELECT t1.id FROM user AS t1 WHERE t1.is_staff = ?
        )
    )

And here it is using joins:

.. code-block:: sql
    
    # using joins
    SELECT t1.* FROM blog AS t1 
    INNER JOIN user AS t2 
        ON t1.user_id = t2.id 
    WHERE 
        t1.status = ? AND 
        t2.is_staff = ?


Column lookups
^^^^^^^^^^^^^^

The other bit that's unique about the query is that it specifies ``"user__in"``.
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
    x IN y, where y is either a list of values or a :py:class:`SelectQuery`


Performing advanced queries
^^^^^^^^^^^^^^^^^^^^^^^^^^^

As you may have noticed, all the examples up to now have shown queries that
combine multiple clauses with "AND".  Taking another page from Django's ORM,
peewee allows the creation of arbitrarily complex queries using a special
notation called :py:class:`Q` objects.

.. code-block:: python

    >>> sq = User.select().where(Q(is_staff=True) | Q(is_superuser=True))
    >>> print sq.sql()[0]
    SELECT * FROM user WHERE (is_staff = ? OR is_superuser = ?)


:py:class:`Q` objects can be combined using the bitwise "or" and "and" operators.  In order
to negate a :py:class:`Q` object, use the bitwise "invert" operator:

.. code-block:: python

    >>> staff_users = User.select().where(is_staff=True)
    >>> Blog.select().where(~Q(user__in=staff_users))

This query generates the following SQL:

.. code-block:: sql

    SELECT * FROM blog 
    WHERE 
        NOT user_id IN (
            SELECT t1.id FROM user AS t1 WHERE t1.is_staff = ?
        )

Rather complex lookups are possible:

.. code-block:: python

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

.. note:: If you need more power, check out :py:class:`RawQuery`


Comparing against column data
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Suppose you have a model that looks like the following:

.. code-block:: python

    class WorkerProfiles(Model):
        salary = IntegerField()
        desired = IntegerField()

What if we want to query ``WorkerProfiles`` to find all the rows where "salary" is greater
than "desired" (maybe you want to find out who may be looking for a raise)?

To solve this problem, peewee borrows the notion of :py:class:`F` objects from the django
orm.  An :py:class:`F` object allows you to query against arbitrary data present in
another column:

.. code-block:: python

    WorkerProfile.select().where(salary__gt=F('desired'))

That's it.  If the other column exists on a model that is accessed via a JOIN,
you will need to specify that model as the second argument to the :py:class:`F`
object.  Let's supposed that the "desired" salary exists on a separate model:

.. code-block:: python

    WorkerProfile.select().join(Desired).where(desired_salary__lt=F('salary', WorkerProfile))

Atomic updates
^^^^^^^^^^^^^^

The :py:class:`F` object also works for updating data.  Suppose you cache counts of tweets for
every user in a special table to avoid an expensive COUNT() query.  You want to
update the cache table every time a user tweets, but do so atomically:

.. code-block:: python

    cache_row = CacheCount.get(user=some_user)
    update_query = cache_row.update(tweet_count=F('tweet_count') + 1)
    update_query.execute()


Aggregating records
^^^^^^^^^^^^^^^^^^^

Suppose you have some blogs and want to get a list of them along with the count
of entries in each.  First I will show you the shortcut:

.. code-block:: python

    query = Blog.select().annotate(Entry)

This is equivalent to the following:

.. code-block:: python

    query = Blog.select({
        Blog: ['*'],
        Entry: [Count('id')],
    }).group_by(Blog).join(Entry)

The resulting query will return ``Blog`` objects with all their normal attributes
plus an additional attribute 'count' which will contain the number of entries.
By default it uses an inner join if the foreign key is not nullable, which means
blogs without entries won't appear in the list.  To remedy this, manually specify
the type of join to include blogs with 0 entries:

.. code-block:: python

    query = Blog.select().join(Entry, 'left outer').annotate(Entry)

You can also specify a custom aggregator:

.. code-block:: python

    query = Blog.select().annotate(Entry, peewee.Max('pub_date', 'max_pub_date'))


Saving Queries by Selecting Related Models
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Returning to my favorite models, ``Blog`` and ``Entry``, between which there is a
:py:class:`ForeignKeyField`, a common pattern might be to display a list of the
latest 10 entries with some info about the blog they're on as well.  We can do
this pretty easily:

.. code-block:: python

    for entry in Entry.select().order_by(('pub_date', 'desc')).limit(10):
        print '%s, posted on %s' % (entry.title, entry.blog.title)

Looking at the query log, though, this will cause 11 queries:

* 1 query for the entries
* 1 query for every related blog (10 total)

This can be optimized into one query very easily, though:

.. code-block:: python

    entries = Entry.select({
        Entry: ['*'],
        Blog: ['*'],
    }).order_by(('pub_date', 'desc')).join(Blog)
    
    for entry in entries.limit(10):
        print '%s, posted on %s' % (entry.title, entry.blog.title)

Will cause only one query that looks something like this:

.. code-block:: sql

    SELECT t1.pk, t1.title, t1.content, t1.pub_date, t1.blog_id, t2.id, t2.title 
    FROM entry AS t1 
    INNER JOIN blog AS t2 
        ON t1.blog_id = t2.id
    ORDER BY t1.pub_date desc
    LIMIT 10

peewee will handle constructing the objects and you can access them as you would
normally.

.. note:: Note in the above example the call to ``.join(Blog)``

This works for following objects "up" the chain, i.e. following foreign key relationships.
The reverse is not true, however -- you cannot issue a single query and get all related
sub-objects, i.e. list blogs and prefetch all related entries.  This *can* be done by
fetching all entries (with related blog data), then reconstructing the blogs in python, but
is not provided as part of peewee.


Query evaluation
----------------

In order to execute a query, it is *always* necessary to call the ``execute()``
method.

To get a better idea of how querying works let's look at some example queries
and their return values:

.. code-block:: python

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

    .. py:method:: __init__(model, query=None)
        
        :param model: a :py:class:`Model` class to perform query on
        :param query: either a dictionary, keyed by model with a list of columns, or a string of columns

        If no query is provided, it will default to ``'*'``.  this parameter can be 
        either a dictionary or a string:
        
        .. code-block:: python
        
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

    .. py:method:: filter(*args, **kwargs)

        :param args: a list of :py:class:`Q` or :py:class:`Node` objects
        :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"
        :rtype: a :py:class:`SelectQuery` instance

        Provides a django-like syntax for building a query.
        The key difference between :py:meth:`~SelectQuery.filter` and :py:meth:`~SelectQuery.where` is that ``filter``
        supports traversing joins using django's "double-underscore" syntax:
        
        .. code-block:: python
        
            >>> sq = SelectQuery(Entry).filter(blog__title='Some Blog')
        
        This method is chainable:
        
        .. code-block:: python
        
            >>> base_q = User.filter(active=True)
            >>> some_user = base_q.filter(username='charlie')

    .. py:method:: get(*args, **kwargs)

        :param args: a list of :py:class:`Q` or :py:class:`Node` objects
        :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"
        :rtype: :py:class:`Model` instance or raises ``DoesNotExist`` exception

        Get a single row from the database that matches the given query.  Raises a
        ``<model-class>.DoesNotExist`` if no rows are returned:
        
        .. code-block:: python
        
            >>> active = User.select().where(active=True)
            >>> try:
            ...     user = active.get(username=username, password=password)
            ... except User.DoesNotExist:
            ...     user = None
        
        This method is also exposed via the :py:class:`Model` api:
        
            >>> user = User.get(username=username, password=password)

    .. py:method:: where(*args, **kwargs)

        :param args: a list of :py:class:`Q` or :py:class:`Node` objects
        :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"
        :rtype: a :py:class:`SelectQuery` instance

        Calling ``where()`` will act on the model that is currently the ``query context``.
        Unlike :py:meth:`~SelectQuery.filter`, only columns from the current query context are exposed::
        
            >>> sq = SelectQuery(Blog).where(title='some title', author=some_user)
            >>> sq = SelectQuery(Blog).where(Q(title='some title') | Q(title='other title'))
        
        .. note::
        
            :py:meth:`~SelectQuery.where` calls are chainable

    .. py:method:: join(model, join_type=None, on=None)

        :param model: the model to join on.  there must be a :py:class:`ForeignKeyField` between
            the current ``query context`` and the model passed in.
        :param join_type: allows the type of ``JOIN`` used to be specified explicitly
        :param on: if multiple foreign keys exist between two models, this parameter
            is a string containing the name of the ForeignKeyField to join on.
        :rtype: a :py:class:`SelectQuery` instance

        Generate a ``JOIN`` clause from the current ``query context`` to the ``model`` passed
        in, and establishes ``model`` as the new ``query context``.
        
        >>> sq = SelectQuery(Blog).join(Entry).where(title='Some Entry')
        >>> sq = SelectQuery(User).join(Relationship, on='to_user_id').where(from_user=self)

    .. py:method:: switch(model)
    
        :param model: model to switch the ``query context`` to.
        :rtype: a :py:class:`SelectQuery` instance

        Switches the ``query context`` to the given model.  Raises an exception if the
        model has not been selected or joined on previously.
        
        >>> sq = SelectQuery(Blog).join(Entry).switch(Blog).where(title='Some Blog')

    .. py:method:: count()

        :rtype: an integer representing the number of rows in the current query
        
        >>> sq = SelectQuery(Blog)
        >>> sq.count()
        45 # <-- number of blogs
        >>> sq.where(status=DELETED)
        >>> sq.count()
        3 # <-- number of blogs that are marked as deleted

    .. py:method:: exists()

        :rtype: boolean whether the current query will return any rows.  uses an
            optimized lookup, so use this rather than :py:meth:`~SelectQuery.get`.
        
        .. code-block:: python
        
            >>> sq = User.select().where(active=True)
            >>> if sq.where(username=username, password=password).exists():
            ...     authenticated = True

    .. py:method:: annotate(related_model, aggregation=None)
    
        :param related_model: related :py:class:`Model` on which to perform aggregation,
            must be linked by :py:class:`ForeignKeyField`.
        :param aggregation: the type of aggregation to use, e.g. ``Max('pub_date', 'max_pub')``
        :rtype: :py:class:`SelectQuery`

        Annotate a query with an aggregation performed on a related model, for example,
        "get a list of blogs with the number of entries on each"::
        
            >>> Blog.select().annotate(Entry)
        
        if ``aggregation`` is None, it will default to ``Count(related_model, 'count')``,
        but can be anything::
        
            >>> blog_with_latest = Blog.select().annotate(Entry, Max('pub_date', 'max_pub'))
        
        .. note::
        
            If the ``ForeignKeyField`` is ``nullable``, then a ``LEFT OUTER`` join
            will be used, otherwise the join is an ``INNER`` join.  If an ``INNER``
            join is used, in the above example blogs with no entries would not be
            returned.  To avoid this, you can explicitly join before calling ``annotate()``::
            
                >>> Blog.select().join(Entry, 'left outer').annotate(Entry)

    .. py:method:: group_by(clause)

        :param clause: either a single field name or a list of field names, in 
            which case it takes its context from the current query_context.  it can
            *also* be a model class, in which case all that models fields will be
            included in the ``GROUP BY`` clause
        :rtype: :py:class:`SelectQuery`
        
        .. code-block:: python
        
            >>> # get a list of blogs with the count of entries each has
            >>> sq = Blog.select({
            ...     Blog: ['*'], 
            ...     Entry: [Count('id')]
            ... }).group_by('id').join(Entry)

            >>> # slightly more complex, get a list of blogs ordered by most recent pub_date
            >>> sq = Blog.select({
            ...     Blog: ['*'],
            ...     Entry: [Max('pub_date', 'max_pub_date')],
            ... }).join(Entry)
            >>> # now, group by the entry's blog id, followed by all the blog fields
            >>> sq = sq.group_by('blog_id').group_by(Blog)
            >>> # finally, order our results by max pub date
            >>> sq = sq.order_by(peewee.desc('max_pub_date'))

    .. py:method:: having(clause)
    
        :param clause: Expression to use as the ``HAVING`` clause
        :rtype: :py:class:`SelectQuery`
        
        .. code-block:: python
            
            >>> sq = Blog.select({
            ...     Blog: ['*'], 
            ...     Entry: [Count('id', 'num_entries')]
            ... }).group_by('id').join(Entry).having('num_entries > 10')

    .. py:method:: order_by(*clauses)
    
        :param clauses: Expression(s) to use as the ``ORDER BY`` clause, see notes below
        :rtype: :py:class:`SelectQuery`
        
        .. note::
            Adds the provided clause (a field name or alias) to the query's 
            ``ORDER BY`` clause.  It can be either a single field name, in which
            case it will apply to the current query context, or a 2- or 3-tuple.
            
            The 2-tuple can be either ``(Model, 'field_name')`` or ``('field_name', 'ASC'/'DESC')``.
            
            The 3-tuple is ``(Model, 'field_name', 'ASC'/'DESC')``.
            
            If the field is not found on the model evaluated against, it will be
            treated as an alias.
        
        example:
        
        .. code-block:: python
        
            >>> sq = Blog.select().order_by('title')
            >>> sq = Blog.select({
            ...     Blog: ['*'],
            ...     Entry: [Max('pub_date', 'max_pub')]
            ... }).join(Entry).order_by(desc('max_pub'))
        
        slightly more complex example:
        
        .. code-block:: python
        
            >>> sq = Entry.select().join(Blog).order_by(
            ...     (Blog, 'title'), # order by blog title ascending
            ...     (Entry, 'pub_date', 'DESC'), # then order by entry pub date desc
            ... )
        
        check out how the ``query context`` applies to ordering:
        
        .. code-block:: python
        
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

    .. py:method:: paginate(page_num, paginate_by=20)
    
        :param page_num: a 1-based page number to use for paginating results
        :param paginate_by: number of results to return per-page
        :rtype: :py:class:`SelectQuery`

        applies a ``LIMIT`` and ``OFFSET`` to the query.
        
        .. code-block:: python
        
            >>> Blog.select().order_by('username').paginate(3, 20) # <-- get blogs 41-60

    .. py:method:: distinct()

        :rtype: :py:class:`SelectQuery`

        indicates that this query should only return distinct rows.  results in a
        ``SELECT DISTINCT`` query.

    .. py:method:: execute()
    
        :rtype: :py:class:`QueryResultWrapper`

        Executes the query and returns a :py:class:`QueryResultWrapper` for iterating over
        the result set.  The results are managed internally by the query and whenever
        a clause is added that would possibly alter the result set, the query is
        marked for re-execution.

    .. py:method:: __iter__()

        Executes the query:
        
        .. code-block:: python
        
            >>> for user in User.select().where(active=True):
            ...     print user.username


UpdateQuery
-----------

.. py:class:: UpdateQuery

    Used for updating rows in the database.

    .. py:method:: __init__(model, **kwargs)
    
        :param model: :py:class:`Model` class on which to perform update
        :param kwargs: mapping of field/value pairs containing columns and values to update
        
        .. code-block:: python
        
            >>> uq = UpdateQuery(User, active=False).where(registration_expired=True)
            >>> print uq.sql()
            ('UPDATE user SET active=? WHERE registration_expired = ?', [0, True])
        
        .. code-block:: python
        
            >>> atomic_update = UpdateQuery(User, message_count=F('message_count') + 1).where(id=3)
            >>> print atomic_update.sql()
            ('UPDATE user SET message_count=(message_count + 1) WHERE id = ?', [3])
    
    .. py:method:: where(*args, **kwargs)

        :param args: a list of :py:class:`Q` or :py:class:`Node` objects
        :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"
        :rtype: a :py:class:`UpdateQuery` instance

        .. note::
        
            :py:meth:`~UpdateQuery.where` calls are chainable

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
        
            >>> dq = DeleteQuery(User).where(active=False)
            >>> print dq.sql()
            ('DELETE FROM user WHERE active = ?', [0])
    
    .. py:method:: where(*args, **kwargs)

        :param args: a list of :py:class:`Q` or :py:class:`Node` objects
        :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"
        :rtype: a :py:class:`DeleteQuery` instance

        .. note::
        
            :py:meth:`~DeleteQuery.where` calls are chainable

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
            >>> print iq.sql()
            ('INSERT INTO user (username, password, active) VALUES (?, ?, ?)', ['admin', 'test', 1])

    .. py:method:: execute()
    
        :rtype: primary key of the new row

        Performs the query


RawQuery
--------

.. py:class:: RawQuery

    Allows execution of an arbitrary ``SELECT`` query and returns instances
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
