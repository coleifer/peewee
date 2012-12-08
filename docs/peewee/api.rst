
.. _model-api:

Model methods
-------------

.. py:class:: Model

    .. py:method:: save([force_insert=False])

        Save the given instance, creating or updating depending on whether it has a
        primary key.  If ``force_insert=True`` an ``INSERT`` will be issued regardless
        of whether or not the primary key exists.

        example:

        .. code-block:: python

            >>> some_obj.title = 'new title' # <-- does not touch the database
            >>> some_obj.save() # <-- change is persisted to the db

    .. py:classmethod:: create(**attributes)

        :param attributes: key/value pairs of model attributes

        Create an instance of the ``Model`` with the given attributes set.

        example:

        .. code-block:: python

            >>> user = User.create(username='admin', password='test')

    .. py:method:: delete_instance([recursive=False[, delete_nullable=False]])

        :param recursive: Delete this instance and anything that depends on it,
            optionally updating those that have nullable dependencies
        :param delete_nullable: If doing a recursive delete, delete all dependent
            objects regardless of whether it could be updated to NULL

        Delete the given instance.  Any foreign keys set to cascade on
        delete will be deleted automatically.  For more programmatic control,
        you can call with recursive=True, which will delete any non-nullable
        related models (those that *are* nullable will be set to NULL).  If you
        wish to delete all dependencies regardless of whether they are nullable,
        set ``delete_nullable=True``.

        example:

        .. code-block:: python

            >>> some_obj.delete_instance() # <-- it is gone forever

    .. py:classmethod:: get(*args, **kwargs)

        :param args: a list of query expressions, e.g. ``Usre.username == 'foo'``
        :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"
        :rtype: :py:class:`Model` instance or raises ``DoesNotExist`` exception

        Get a single row from the database that matches the given query.  Raises a
        ``<model-class>.DoesNotExist`` if no rows are returned:

        .. code-block:: python

            >>> user = User.get(User.username == username, User.password == password)

        This method is also expose via the :py:class:`SelectQuery`, though it takes
        no parameters:

        .. code-block:: python

            >>> active = User.select().where(User.active == True)
            >>> try:
            ...     users = active.where(User.username == username, User.password == password)
            ...     user = users.get()
            ... except User.DoesNotExist:
            ...     user = None

        .. note:: the "kwargs" style syntax is provided for compatibility with
            version 1.0.  The expression-style syntax is preferable.

    .. py:classmethod:: get_or_create(**attributes)

        :param attributes: key/value pairs of model attributes
        :rtype: a :py:class:`Model` instance

        Get the instance with the given attributes set.  If the instance
        does not exist it will be created.

        example:

        .. code-block:: python

            >>> CachedObj.get_or_create(key=key, val=some_val)

    .. py:classmethod:: select(*selection)

        :param selection: a list of model classes, field instances, functions or expressions
        :rtype: a :py:class:`SelectQuery` for the given ``Model``

        example:

        .. code-block:: python

            >>> User.select().where(User.active == True).order_by(User.username)
            >>> Tweet.select(Tweet, User).join(User).order_by(Tweet.created_date.desc())

    .. py:classmethod:: update(**query)

        :rtype: an :py:class:`UpdateQuery` for the given ``Model``

        example:

        .. code-block:: python

            >>> q = User.update(active=False).where(User.registration_expired == True)
            >>> q.execute() # <-- execute it

    .. py:classmethod:: delete()

        :rtype: a :py:class:`DeleteQuery` for the given ``Model``

        example:

        .. code-block:: python

            >>> q = User.delete().where(User.active == False)
            >>> q.execute() # <-- execute it

        .. warning::
            Assume you have a model instance -- calling ``model_instance.delete()``
            does **not** delete it.

    .. py:classmethod:: insert(**query)

        :rtype: an :py:class:`InsertQuery` for the given ``Model``

        example:

        .. code-block:: python

            >>> q = User.insert(username='admin', active=True, registration_expired=False)
            >>> q.execute()
            1

    .. py:classmethod:: raw(sql, *params)

        :rtype: a :py:class:`RawQuery` for the given ``Model``

        example:

        .. code-block:: python

            >>> q = User.raw('select id, username from users')
            >>> for user in q:
            ...     print user.id, user.username

    .. py:classmethod:: filter(*args, **kwargs)

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

        .. note:: this method is provided for compatibility with peewee 1.0

    .. py:classmethod:: create_table([fail_silently=False])

        :param fail_silently: If set to ``True``, the method will check for the existence of the table
            before attempting to create.

        Create the table for the given model.

        example:

        .. code-block:: python

            >>> database.connect()
            >>> SomeModel.create_table() # <-- creates the table for SomeModel

    .. py:classmethod:: drop_table([fail_silently=False])

        :param fail_silently: If set to ``True``, the query will check for the existence of
            the table before attempting to remove.

        Drop the table for the given model.

        .. note::
            Cascading deletes are not handled by this method, nor is the removal
            of any constraints.

    .. py:classmethod:: table_exists()

        :rtype: Boolean whether the table for this model exists in the database

.. _fields-api:

Field class API
---------------

.. py:class:: Field

    The base class from which all other field types extend.

    .. py:attribute:: db_field = '<some field type>'

        Attribute used to map this field to a column type, e.g. "string" or "datetime"

    .. py:attribute:: template = '%(column_type)s'

        A template for generating the SQL for this field

    .. py:method:: __init__(null=False, index=False, unique=False, verbose_name=None, help_text=None, db_column=None, default=None, choices=None, *args, **kwargs)

        :param null: this column can accept ``None`` or ``NULL`` values
        :param index: create an index for this column when creating the table
        :param unique: create a unique index for this column when creating the table
        :param verbose_name: specify a "verbose name" for this field, useful for metadata purposes
        :param help_text: specify some instruction text for the usage/meaning of this field
        :param db_column: column class to use for underlying storage
        :param default: a value to use as an uninitialized default
        :param choices: an iterable of 2-tuples mapping ``value`` to ``display``
        :param boolean primary_key: whether to use this as the primary key for the table
        :param sequence: name of sequence (if backend supports it)

    .. py:method:: db_value(value)

        :param value: python data type to prep for storage in the database
        :rtype: converted python datatype

    .. py:method:: python_value(value)

        :param value: data coming from the backend storage
        :rtype: python data type

    .. py:method:: coerce(value)

        This method is a shorthand that is used, by default, by both ``db_value`` and
        ``python_value``.  You can usually get away with just implementing this.

        :param value: arbitrary data from app or backend
        :rtype: python data type

    .. py:method:: field_attributes()

        This method is responsible for return a dictionary containing the default
        field attributes for the column, e.g. ``{'max_length': 255}``

        :rtype: a python dictionary

    .. py:method:: class_prepared()

        Simple hook for :py:class:`Field` classes to indicate when the :py:class:`Model`
        class the field exists on has been created.

.. py:class:: CharField

    Stores: small strings (0-255 bytes)

.. py:class:: TextField

    Stores: arbitrarily large strings

.. py:class:: DateTimeField

    Stores: python ``datetime.datetime`` instances

    Accepts a special parameter ``formats``, which contains a list of formats
    the datetime can be encoded with.  The default behavior is:

    .. code-block:: python

        '%Y-%m-%d %H:%M:%S.%f' # year-month-day hour-minute-second.microsecond
        '%Y-%m-%d %H:%M:%S' # year-month-day hour-minute-second
        '%Y-%m-%d' # year-month-day

    .. note::
        If the incoming value does not match a format, it will be returned as-is

.. py:class:: DateField

    Stores: python ``datetime.date`` instances

    Accepts a special parameter ``formats``, which contains a list of formats
    the date can be encoded with.  The default behavior is:

    .. code-block:: python

        '%Y-%m-%d' # year-month-day
        '%Y-%m-%d %H:%M:%S' # year-month-day hour-minute-second
        '%Y-%m-%d %H:%M:%S.%f' # year-month-day hour-minute-second.microsecond

    .. note::
        If the incoming value does not match a format, it will be returned as-is

.. py:class:: TimeField

    Stores: python ``datetime.time`` instances

    Accepts a special parameter ``formats``, which contains a list of formats
    the time can be encoded with.  The default behavior is:

    .. code-block:: python

        '%H:%M:%S.%f' # hour:minute:second.microsecond
        '%H:%M:%S' # hour:minute:second
        '%H:%M' # hour:minute
        '%Y-%m-%d %H:%M:%S.%f' # year-month-day hour-minute-second.microsecond
        '%Y-%m-%d %H:%M:%S' # year-month-day hour-minute-second

    .. note::
        If the incoming value does not match a format, it will be returned as-is

.. py:class:: IntegerField

    Stores: integers

.. py:class:: BooleanField

    Stores: ``True`` / ``False``

.. py:class:: FloatField

    Stores: floating-point numbers

.. py:class:: DecimalField

    Stores: decimal numbers

.. py:class:: PrimaryKeyField

    Stores: auto-incrementing integer fields suitable for use as primary key.

.. py:class:: ForeignKeyField

    Stores: relationship to another model

    .. py:method:: __init__(to[, related_name=None[, ...]])

        :param rel_model: related :py:class:`Model` class or the string 'self' if declaring
                   a self-referential foreign key
        :param related_name: attribute to expose on related model

        .. code-block:: python

            class User(Model):
                name = CharField()

            class Tweet(Model):
                user = ForeignKeyField(User, related_name='tweets')
                content = TextField()

            # "user" attribute
            >>> some_tweet.user
            <User: charlie>

            # "tweets" related name attribute
            >>> for tweet in charlie.tweets:
            ...     print tweet.content
            Some tweet
            Another tweet
            Yet another tweet

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
