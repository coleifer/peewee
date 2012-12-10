API Reference
=============

.. _expressions:

Expressions
-----------

Peewee was designed to provide a simple, expressive, and pythonic way of executing
queries.  This section will provide a quick overview of some common types of expressions.

There are two primary types of objects that can be composed to create expressions:

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


Comparisons use the :ref:`column-lookups`:

.. code-block:: python

    # username is equal to 'charlie'
    User.username == 'charlie'

    # user has logged in less than 5 times
    User.login_count < 5

Comparisons can be combined using bitwise "and" and "or".  Operator precedence
is controlled by python and comparisons can be nested to an arbitrary depth:

.. code-block:: python

    # user is both and admin and has logged in today
    (User.is_admin == True) & (User.last_login >= today)

    # user's username is either charlie or charles
    (User.username == 'charlie') | (User.username == 'charles')

Comparisons can be used with functions as well:

.. code-block:: python

    # user's username starts with a 'g' or a 'G':
    fn.Lower(fn.Substr(User.username, 1, 1)) == 'g'

We can do some fairly interesting things, as expressions can be compared against
other expressions.  Expressions also support arithmetic operations:

.. code-block:: python

    # users who entered the incorrect more than half the time and have logged
    # in at least 10 times
    (User.failed_logins > (User.login_count * .5)) & (User.login_count > 10)

Expressions allow us to do atomic updates:

.. code-block:: python

    # when a user logs in we want to increment their login count:
    User.update(login_count=User.login_count + 1).where(User.id == user_id)

Expressions can be used in all parts of a query, so experiment!

.. _model-api:

Models
------

.. py:class:: Model(**kwargs)

    Models provide a 1-to-1 mapping to database tables.  Subclasses of ``Model``
    declare any number of :py:class:`Field` instances as class attributes.  These
    fields correspond to columns on the table.

    Table-level operations, such as select/update/insert/delete queries, are implemented
    as classmethods.  Row-level operations such as saving or deleting individual instances
    are implemented as instancemethods.

    :param kwargs: Initialize the model, assigning the given key/values to the
        appropriate fields.

    Example:

    .. code-block:: python

        class User(Model):
            username = CharField()
            join_date = DateTimeField()
            is_admin = BooleanField()

        u = User(username='charlie', is_admin=True)

    .. py:classmethod:: select(*selection)

        :param selection: a list of model classes, field instances, functions or expressions
        :rtype: a :py:class:`SelectQuery` for the given ``Model``

        Examples of selecting all columns (default):

        .. code-block:: python

            >>> User.select().where(User.active == True).order_by(User.username)

        Example of selecting all columns on ``Tweet`` *and* the parent model, ``User``.  When
        the ``user`` foreign key is accessed on a ``tweet`` instance no additional query will
        be needed:

        .. code-block:: python

            >>> Tweet.select(Tweet, User).join(User).order_by(Tweet.created_date.desc())

    .. py:classmethod:: update(**update)

        :param update: mapping of field-name to expression
        :rtype: an :py:class:`UpdateQuery` for the given ``Model``

        Example showing users being marked inactive if their registration expired:

        .. code-block:: python

            >>> q = User.update(active=False).where(User.registration_expired == True)
            >>> q.execute() # <-- execute the query

        Example showing an atomic update:

            >>> q = PageView.update(count=PageView.count + 1).where(PageView.url == url)
            >>> q.execute() # <-- execute the query

    .. py:classmethod:: insert(**insert)

        :param insert: mapping of field-name to expression
        :rtype: an :py:class:`InsertQuery` for the given ``Model``

        Example showing creation of a new user:

        .. code-block:: python

            >>> q = User.insert(username='admin', active=True, registration_expired=False)
            >>> q.execute()
            1

    .. py:classmethod:: delete()

        :rtype: a :py:class:`DeleteQuery` for the given ``Model``

        Example showing the deletion of all inactive users:

        .. code-block:: python

            >>> q = User.delete().where(User.active == False)
            >>> q.execute() # <-- execute it

        .. warning::
            This method performs a delete on the *entire table*.  To delete a single
            instance, see :py:meth:`Model.delete_instance`.

    .. py:classmethod:: raw(sql, *params)

        :param sql: a string SQL expression
        :param params: any number of parameters to interpolate
        :rtype: a :py:class:`RawQuery` for the given ``Model``

        Example selecting rows from the User table:

        .. code-block:: python

            >>> q = User.raw('select id, username from users')
            >>> for user in q:
            ...     print user.id, user.username

        .. note::
            Generally the use of ``raw`` is reserved for those cases where you
            can significantly optimize a select query.  It is useful for select
            queries since it will return instances of the model.

    .. py:classmethod:: create(**attributes)

        :param attributes: key/value pairs of model attributes
        :rtype: a model instance with the provided attributes

        Example showing the creation of a user (a row will be added to the database):

        .. code-block:: python

            >>> user = User.create(username='admin', password='test')

        .. note::
            The create() method is a shorthand for instantiate-then-save.

    .. py:classmethod:: get(*args, **kwargs)

        :param args: a list of query expressions, e.g. ``User.username == 'foo'``
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

        .. note::
            The ``get()`` method is shorthand for selecting with a limit of 1. It
            has the added behavior of raising an exception when no matching row is
            found.  If more than one row is found, the first row returned by the
            database cursor will be used.

        .. warning:: the "kwargs" style syntax is provided for compatibility with
            version 1.0.  The expression-style syntax is preferable.

    .. py:classmethod:: get_or_create(**attributes)

        .. deprecated:: 2.0
            Because this relies of "django-style" expressions, it has been deprecated
            as of 2.0.  Use :py:meth:`Model.get` and :py:meth:`Model.create` explicitly.

        :param attributes: key/value pairs of model attributes
        :rtype: a :py:class:`Model` instance

        Get the instance with the given attributes set.  If the instance
        does not exist it will be created.

        Example showing get/create an object cached in the database:

        .. code-block:: python

            >>> CachedObj.get_or_create(key=key, val=some_val)

    .. py:classmethod:: filter(*args, **kwargs)

        .. deprecated:: 2.0
           Use :py:class:`~Model.select` instead.

        :param args: a list of :py:class:`DQ` or expression objects
        :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"
        :rtype: :py:class:`SelectQuery` with appropriate ``WHERE`` clauses

        Provides a django-like syntax for building a query. The key difference
        between :py:meth:`~Model.filter` and :py:meth:`SelectQuery.where`
        is that :py:meth:`~Model.filter` supports traversing joins using
        django's "double-underscore" syntax:

        .. code-block:: python

            >>> sq = Entry.filter(blog__title='Some Blog')

    .. py:classmethod:: create_table([fail_silently=False])

        :param bool fail_silently: If set to ``True``, the method will check for the existence of the table
            before attempting to create.

        Create the table for the given model.

        Example:

        .. code-block:: python

            >>> database.connect()
            >>> SomeModel.create_table() # <-- creates the table for SomeModel

    .. py:classmethod:: drop_table([fail_silently=False])

        :param bool fail_silently: If set to ``True``, the query will check for the existence of
            the table before attempting to remove.

        Drop the table for the given model.

        .. note::
            Cascading deletes are not handled by this method, nor is the removal
            of any constraints.

    .. py:classmethod:: table_exists()

        :rtype: Boolean whether the table for this model exists in the database

    .. py:method:: save([force_insert=False])

        Save the given instance, creating or updating depending on whether it has a
        primary key.  If ``force_insert=True`` an ``INSERT`` will be issued regardless
        of whether or not the primary key exists.

        Example showing saving a model instance:

        .. code-block:: python

            >>> user = User()
            >>> user.username = 'some-user' # <-- does not touch the database
            >>> user.save() # <-- change is persisted to the db

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

    .. py:method:: dependencies([search_nullable=False])

        :param bool search_nullable: Search models related via a nullable foreign key
        :rtype: Generator expression yielding queries and foreign key fields

        Generate a list of queries of dependent models.  Yields a 2-tuple containing
        the query and corresponding foreign key field.  Useful for searching dependencies
        of a model, i.e. things that would be orphaned in the event of a delete.


.. _fields-api:

Fields
------

.. py:class:: Field(null=False, index=False, unique=False, verbose_name=None, help_text=None, db_column=None, default=None, choices=None, *args, **kwargs)

    The base class from which all other field types extend.

    :param bool null: whether this column can accept ``None`` or ``NULL`` values
    :param bool index: whether to create an index for this column when creating the table
    :param bool unique: whether to create a unique index for this column when creating the table
    :param string verbose_name: specify a "verbose name" for this field, useful for metadata purposes
    :param string help_text: specify some instruction text for the usage/meaning of this field
    :param string db_column: column name to use for underlying storage, useful for compatibility with legacy databases
    :param default: a value to use as an uninitialized default
    :param choices: an iterable of 2-tuples mapping ``value`` to ``display``
    :param bool primary_key: whether to use this as the primary key for the table
    :param string sequence: name of sequence (if backend supports it)
    :param kwargs: named attributes containing values that may pertain to specific field subclasses, such as "max_length" or "decimal_places"

    .. py:attribute:: db_field = '<some field type>'

        Attribute used to map this field to a column type, e.g. "string" or "datetime"

    .. py:attribute:: template = '%(column_type)s'

        A template for generating the SQL for this field

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

.. py:class:: IntegerField

    Stores: integers

    .. py:attribute:: db_field = 'int'

.. py:class:: BigIntegerField

    Stores: big integers

    .. py:attribute:: db_field = 'bigint'

.. py:class:: PrimaryKeyField

    Stores: auto-incrementing integer fields suitable for use as primary key.

    .. py:attribute:: db_field = 'primary_key'

.. py:class:: FloatField

    Stores: floating-point numbers

    .. py:attribute:: db_field = 'float'

.. py:class:: DoubleField

    Stores: double-precision floating-point numbers

    .. py:attribute:: db_field = 'double'

.. py:class:: DecimalField

    Stores: decimal numbers, using python standard library ``Decimal`` objects

    Additional attributes and values:

    ==================  ===================================
    ``max_digits``      ``10``
    ``decimal_places``  ``5``
    ``auto_round``      ``False``
    ``rounding``        ``decimal.DefaultContext.rounding``
    ==================  ===================================

    .. py:attribute:: db_field = 'decimal'

    .. py:attribute:: template = '%(column_type)s(%(max_digits)d, %(decimal_places)d)'

.. py:class:: CharField

    Stores: small strings (0-255 bytes)

    Additional attributes and values:

    ================  =========================
    ``max_length``    ``255``
    ================  =========================

    .. py:attribute:: db_field = 'string'

    .. py:attribute:: template = '%(column_type)s(%(max_length)s)'

.. py:class:: TextField

    Stores: arbitrarily large strings

    .. py:attribute:: db_field = 'text'

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

    .. py:attribute:: db_field = 'datetime'

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

    .. py:attribute:: db_field = 'date'

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

    .. py:attribute:: db_field = 'time'

.. py:class:: BooleanField

    Stores: ``True`` / ``False``

    .. py:attribute:: db_field = 'bool'

.. py:class:: ForeignKeyField(rel_model[, related_name=None[, cascade=False[, ...]]])

    Stores: relationship to another model

    :param rel_model: related :py:class:`Model` class or the string 'self' if declaring
               a self-referential foreign key
    :param string related_name: attribute to expose on related model
    :param bool cascade: set up foreign key to do cascading deletes

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

    .. note:: Foreign keys do not have a particular ``db_field`` as they will
        take their field type depending on the type of primary key on the model they are
        related to.


.. _query-types:

Query Types
-----------

.. py:class:: Query

    The parent class from which all other query classes are drived.

    .. py:method:: where(*expressions)

        :param expressions: a list of one or more :ref:`expressions <expressions>`
        :rtype: a :py:class:`SelectQuery` instance

        Example selection users where the username is equal to 'somebody':

        .. code-block:: python

            >>> sq = SelectQuery(User).where(User.username == 'somebody')

        Example selecting tweets made by users who are either editors or administrators:

        .. code-block:: python

            >>> sq = SelectQuery(Tweet).join(User).where(
            ...     (User.is_editor == True) |
            ...     (User.is_admin == True)
            ... )

        .. note::

            :py:meth:`~SelectQuery.where` calls are chainable.  Multiple calls will
            be "AND"-ed together.

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

        Example selecting tweets and joining on user in order to restrict to
        only those tweets made by "admin" users:

        .. code-block:: python

            >>> sq = SelectQuery(Tweet).join(User).where(User.is_admin == True)

        Example selecting users and joining on a particular foreign key field.
        See the :py:ref:`example app <example-app>` for a real-life usage:

        .. code-block:: python

            >>> sq = SelectQuery(User).join(Relationship, on=Relationship.to_user)

    .. py:method:: switch(model)

        :param model: model to switch the ``query context`` to.
        :rtype: a clone of the query with a new query context

        Switches the ``query context`` to the given model.  Raises an exception if the
        model has not been selected or joined on previously.  Useful for performing
        multiple joins from a single table.

        The following example selects from blog and joins on both entry and user:

        .. code-block:: python

            >>> sq = SelectQuery(Blog).join(Entry).switch(Blog).join(User)

    .. py:method:: filter(*args, **kwargs)

        .. deprecated:: 2.0
            Use instead :py:meth:`Query.where`

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

    .. py:method:: sql(compiler)

        :param compiler: an instance of :py:class:`QueryCompiler`
        :rtype: a 2-tuple containing the appropriate SQL query and a tuple of parameters

        .. warning: This method should be implemented by subclasses

    .. py:method:: execute()

        Execute the given query

        .. warning: This method should be implemented by subclasses


.. py:class:: SelectQuery(model, *selection)

    By far the most complex of the query classes available in peewee. It supports
    all clauses commonly associated with select queries.

    Methods on the select query can be chained together.

    ``SelectQuery`` implements an :py:meth:`~SelectQuery.__iter__` method, allowing it to be iterated
    to return model instances.

    :param model: a :py:class:`Model` class to perform query on
    :param selection: a list of models, fields, functions or expressions

    If no selection is provided, it will default to all the fields of the given
    model.

    Example selecting some user instances from the database.  Only the ``id``
    and ``username`` columns are selected.  When iterated, will return instances
    of the ``User`` model:

    .. code-block:: python

        >>> sq = SelectQuery(User, User.id, User.username)
        >>> for user in sq:
        ...     print user.username

    Example selecting users and additionally the number of tweets made by the user.
    The ``User`` instances returned will have an additional attribute, 'count', that
    corresponds to the number of tweets made:

    .. code-block:: python

        >>> sq = SelectQuery(User,
        ...     User, fn.Count(Tweet.id).alias('count')
        ... ).join(Tweet).group_by(User)

    .. py:method:: group_by(*clauses)

        :param clauses: a list of expressions, which can be model classes or individual field instances
        :rtype: :py:class:`SelectQuery`

        Group by one or more columns.  If a model class is provided, all the fields
        on that model class will be used.

        Example selecting users, joining on tweets, and grouping by the user so
        a count of tweets can be calculated for each user:

        .. code-block:: python

            >>> sq = User.select(
            ...     User, fn.Count(Tweet.id).alias('count')
            ... ).join(Tweet).group_by(User)

    .. py:method:: having(*expressions)

        :param expressions: a list of one or more :ref:`expressions <expressions>`
        :rtype: :py:class:`SelectQuery`

        Here is the above example selecting users and tweet counts, but restricting
        the results to those users who have created 100 or more tweets:

        .. code-block:: python

            >>> sq = User.select(
            ...     User, fn.Count(Tweet.id).alias('count')
            ... ).join(Tweet).group_by(User).having(fn.Count(Tweet.id) > 100)

    .. py:method:: order_by(*clauses)

        :param clauses: a list of fields, calls to ``field.[asc|desc]()`` or one or more :ref:`expressions <expressions>`
        :rtype: :py:class:`SelectQuery`

        Example of ordering users by username:

        .. code-block:: python

            >>> User.select().order_by(User.username)

        Example of selecting tweets and ordering them first by user, then newest
        first:

        .. code-block:: python

            >>> Tweet.select().join(User).order_by(
            ...     User.username, Tweet.created_date.desc()
            ... )

        A more complex example ordering users by the number of tweets made (greatest
        to least), then ordered by username in the event of a tie:

        .. code-block:: python

            >>> sq = User.select(
            ...     User, fn.Count(Tweet.id).alias('count')
            ... ).join(Tweet).group_by(User).order_by(
            ...     fn.Count(Tweet.id).desc(), User.username
            ... )

    .. py:method:: limit(num)

        :param int num: limit results to ``num`` rows

    .. py:method:: offset(num)

        :param int num: offset results by ``num`` rows

    .. py:method:: paginate(page_num, paginate_by=20)

        :param page_num: a 1-based page number to use for paginating results
        :param paginate_by: number of results to return per-page
        :rtype: :py:class:`SelectQuery`

        Shorthand for applying a ``LIMIT`` and ``OFFSET`` to the query.

        .. code-block:: python

            >>> User.select().order_by(User.username).paginate(3, 20) # <-- get users 41-60

    .. py:method:: distinct()

        :rtype: :py:class:`SelectQuery`

        indicates that this query should only return distinct rows.  results in a
        ``SELECT DISTINCT`` query.

    .. py:method:: for_update([for_update=True])

        :rtype: :py:class:`SelectQuery`

        indicates that this query should lock rows for update

    .. py:method:: naive()

        :rtype: :py:class:`SelectQuery`

        Flag this query indicating it should only attempt to reconstruct a single model
        instance for every row returned by the cursor.  If multiple tables were queried,
        the columns returned are patched directly onto the single model instance.

        Generally this method is useful for speeding up the time needed to construct
        model instances given a database cursor.

        .. note::

            this can provide a significant speed improvement when doing simple
            iteration over a large result set.

    .. py:method:: annotate(related_model, aggregation=None)

        :param related_model: related :py:class:`Model` on which to perform aggregation,
            must be linked by :py:class:`ForeignKeyField`.
        :param aggregation: the type of aggregation to use, e.g. ``fn.Count(Tweet.id).alias('count')``
        :rtype: :py:class:`SelectQuery`

        Annotate a query with an aggregation performed on a related model, for example,
        "get a list of users with the number of tweets for each":

        .. code-block:: python

            >>> User.select().annotate(Tweet)

        If ``aggregation`` is None, it will default to ``fn.Count(related_model.id).alias('count')``
        but can be anything:

        .. code-block:: python

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

    .. py:method:: count()

        :rtype: an integer representing the number of rows in the current query

        >>> sq = SelectQuery(Tweet)
        >>> sq.count()
        45 # <-- number of tweets
        >>> sq.where(Tweet.status == DELETED)
        >>> sq.count()
        3 # <-- number of tweets that are marked as deleted

    .. py:method:: wrapped_count()

        :rtype: an integer representing the number of rows in the current query

        Wrap the count query in a subquery.  Additional overhead but will give
        correct counts when performing ``DISTINCT`` queries or those with ``GROUP BY``
        clauses.

        .. note::
            :py:meth:`~SelectQuery.count` will automatically default to :py:meth:`~SelectQuery.wrapped_count`
            in the event the query is distinct or has a grouping.

    .. py:method:: exists()

        :rtype: boolean whether the current query will return any rows.  uses an
            optimized lookup, so use this rather than :py:meth:`~SelectQuery.get`.

        .. code-block:: python

            >>> sq = User.select().where(User.active == True)
            >>> if sq.where(User.username==username, User.password==password).exists():
            ...     authenticated = True

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

    .. py:method:: execute()

        :rtype: :py:class:`QueryResultWrapper`

        Executes the query and returns a :py:class:`QueryResultWrapper` for iterating over
        the result set.  The results are managed internally by the query and whenever
        a clause is added that would possibly alter the result set, the query is
        marked for re-execution.

    .. py:method:: __iter__()

        Executes the query and returns populated model instances:

        .. code-block:: python

            >>> for user in User.select().where(User.active == True):
            ...     print user.username


.. py:class:: UpdateQuery(model, **kwargs)

    :param model: :py:class:`Model` class on which to perform update
    :param kwargs: mapping of field/value pairs containing columns and values to update

    Example in which users are marked inactive if their registration expired:

    .. code-block:: python

        >>> uq = UpdateQuery(User, active=False).where(User.registration_expired==True)
        >>> uq.execute() # run the query

    Example of an atomic update:

    .. code-block:: python

        >>> atomic_update = UpdateQuery(PageCount, count = PageCount.count + 1).where(PageCount.url == url)
        >>> atomic_update.execute() # run the query

    .. py:method:: execute()

        :rtype: Number of rows updated

        Performs the query


.. py:class:: InsertQuery(model, **kwargs)

    Creates an ``InsertQuery`` instance for the given model where kwargs is a
    dictionary of field name to value:

    .. code-block:: python

        >>> iq = InsertQuery(User, username='admin', password='test', active=True)
        >>> iq.execute() # <--- insert new row and return primary key
        2L

    .. py:method:: execute()

        :rtype: primary key of the new row

        Performs the query


.. py:class:: DeleteQuery

    Creates a ``DeleteQuery`` instance for the given model.

    .. note::
        DeleteQuery will *not* traverse foreign keys or ensure that constraints
        are obeyed, so use it with care.

    Example deleting users whose account is inactive:

    .. code-block:: python

        >>> dq = DeleteQuery(User).where(User.active==False)

    .. py:method:: execute()

        :rtype: Number of rows deleted

        Performs the query


.. py:class:: RawQuery

    Allows execution of an arbitrary query and returns instances
    of the model via a :py:class:`QueryResultsWrapper`.

    .. note::
        Generally you will only need this for executing highly optimized SELECT
        queries.

    .. warning::
        If you are executing a parameterized query, you must use the correct
        interpolation string for your database.  SQLite uses ``'?'`` and most others
        use ``'%s'``.

    Example selecting users with a given username:

    .. code-block:: python

        >>> rq = RawQuery(User, 'SELECT * FROM users WHERE username = ?', 'admin')
        >>> for obj in rq.execute():
        ...     print obj
        <User: admin>

    .. py:method:: execute()

        :rtype: a :py:class:`QueryResultWrapper` for iterating over the result set.  The results are instances of the given model.

        Performs the query


Database and its subclasses
---------------------------

.. py:class:: Database(database[, threadlocals=False[, autocommit=True[, **connect_kwargs]]])

    :param database: the name of the database (or filename if using sqlite)
    :param threadlocals: whether to store connections in a threadlocal
    :param autocommit: automatically commit every query executed by calling :py:meth:`~Database.execute`
    :param connect_kwargs: any arbitrary parameters to pass to the database driver when connecting

    .. note::
        if your database name is not known when the class is declared, you can pass
        ``None`` in as the database name which will mark the database as "deferred"
        and any attempt to connect while in this state will raise an exception.  To
        initialize your database, call the :py:meth:`Database.init` method with
        the database name

    A high-level api for working with the supported database engines.  ``Database``
    provides a wrapper around some of the functions performed by the ``Adapter``,
    in addition providing support for:

    - execution of SQL queries
    - creating and dropping tables and indexes

    .. py:attribute:: commit_select = False

        Whether to issue a commit after executing a select query.  With some engines
        can prevent implicit transactions from piling up.

    .. py:attribute:: compiler_class = QueryCompiler

        A class suitable for compiling queries

    .. py:attribute:: field_overrides = {}

        A mapping of field types to database column types, e.g. ``{'primary_key': 'SERIAL'}``

    .. py:attribute:: for_update = False

        Whether the given backend supports selecting rows for update

    .. py:attribute:: interpolation = '?'

        The string used by the driver to interpolate query parameters

    .. py:attribute:: op_overrides = {}

        A mapping of operation codes to string operations, e.g. ``{OP_LIKE: 'LIKE BINARY'}``

    .. py:attribute:: quote_char = '"'

        The string used by the driver to quote names

    .. py:attribute:: reserved_tables = []

        Table names that are reserved by the backend -- if encountered in the
        application a warning will be issued.

    .. py:attribute:: sequences = False

        Whether the given backend supports sequences

    .. py:attribute:: subquery_delete_same_table = True

        Whether the given backend supports deleting rows using a subquery
        that selects from the same table

    .. py:method:: init(database[, **connect_kwargs])

        If the database was instantiated with ``database=None``, the database is said to be in
        a 'deferred' state (see :ref:`notes <deferring_initialization>`) -- if this is the case,
        you can initialize it at any time by calling the ``init`` method.

        :param database: the name of the database (or filename if using sqlite)
        :param connect_kwargs: any arbitrary parameters to pass to the database driver when connecting

    .. py:method:: connect()

        Establishes a connection to the database

        .. note::
            If you initialized with ``threadlocals=True``, then this will store
            the connection inside a threadlocal, ensuring that connections are not
            shared across threads.

    .. py:method:: close()

        Closes the connection to the database (if one is open)

        .. note::
            If you initialized with ``threadlocals=True``, only a connection local
            to the calling thread will be closed.

    .. py:method:: get_conn()

        :rtype: a connection to the database, creates one if does not exist

    .. py:method:: get_cursor()

        :rtype: a cursor for executing queries

    .. py:method:: last_insert_id(cursor, model)

        :param cursor: the database cursor used to perform the insert query
        :param model: the model class that was just created
        :rtype: the primary key of the most recently inserted instance

    .. py:method:: rows_affected(cursor)

        :rtype: number of rows affected by the last query

    .. py:method:: get_compiler()

        :rtype: an instance of :py:class:`QueryCompiler` using the field and
            op overrides specified.

    .. py:method:: execute(query)

        :param: a query instance, such as a :py:class:`SelectQuery`
        :rtype: the resulting cursor

    .. py:method:: execute_sql(sql[, params=None[, require_commit=True]])

        :param sql: a string sql query
        :param params: a list or tuple of parameters to interpolate

        .. note::
            You can configure whether queries will automatically commit by using
            the :py:meth:`~Database.set_autocommit` and :py:meth:`Database.get_autocommit`
            methods.

    .. py:method:: begin()

        Initiate a new transaction.  By default **not** implemented as this is not
        part of the DB-API 2.0, but provided for API compatibility.

    .. py:method:: commit()

        Call ``commit()`` on the active connection, committing the current transaction

    .. py:method:: rollback()

        Call ``rollback()`` on the active connection, rolling back the current transaction

    .. py:method:: set_autocommit(autocommit)

        :param autocommit: a boolean value indicating whether to turn on/off autocommit
            **for the current connection**

    .. py:method:: get_autocommit()

        :rtype: a boolean value indicating whether autocommit is on **for the current connection**

    .. py:method:: get_tables()

        :rtype: a list of table names in the database

        .. warning::
            Not implemented -- implementations exist in subclasses

    .. py:method:: get_indexes_for_table(table)

        :param table: the name of table to introspect
        :rtype: a list of ``(index_name, is_unique)`` tuples

        .. warning::
            Not implemented -- implementations exist in subclasses

    .. py:method:: sequence_exists(sequence_name)

        :rtype boolean:

        .. warning::
            Not implemented -- implementations exist in subclasses

    .. py:method:: create_table(model_class)

        :param model_class: :py:class:`Model` class to create table for

    .. py:method:: create_index(model_class, fields[, unique=False])

        :param model_class: :py:class:`Model` table on which to create index
        :param fields: field(s) to create index on (either field instances or field names)
        :param unique: whether the index should enforce uniqueness

    .. py:method:: create_foreign_key(model_class, field)

        :param model_class: :py:class:`Model` table on which to create foreign key index / constraint
        :param field: :py:class:`Field` object

    .. py:method:: create_sequence(sequence_name)

        :param sequence_name: name of sequence to create

        .. note:: only works with database engines that support sequences

    .. py:method:: drop_table(model_class[, fail_silently=False])

        :param model_class: :py:class:`Model` table to drop
        :param fail_silently: if ``True``, query will add a ``IF EXISTS`` clause

        .. note::
            Cascading drop tables are not supported at this time, so if a constraint
            exists that prevents a table being dropped, you will need to handle
            that in application logic.

    .. py:method:: drop_sequence(sequence_name)

        :param sequence_name: name of sequence to drop

        .. note:: only works with database engines that support sequences

    .. py:method:: transaction()

        Return a context manager that executes statements in a transaction.  If an
        error is raised inside the context manager, the transaction will be rolled
        back, otherwise statements are committed when exiting.

        .. code-block:: python

            # delete a blog instance and all its associated entries, but
            # do so within a transaction
            with database.transaction():
                blog.delete_instance(recursive=True)

    .. py:method:: commit_on_success(func)

        Decorator that wraps the given function in a single transaction, which,
        upon success will be committed.  If an error is raised inside the function,
        the transaction will be rolled back and the error will be re-raised.

        :param func: function to decorate

        .. code-block:: python

            @database.commit_on_success
            def transfer_money(from_acct, to_acct, amt):
                from_acct.charge(amt)
                to_acct.pay(amt)
                return amt


.. py:class:: SqliteDatabase(Database)

    :py:class:`Database` subclass that communicates to the "sqlite3" driver

.. py:class:: MySQLDatabase(Database)

    :py:class:`Database` subclass that communicates to the "MySQLdb" driver

.. py:class:: PostgresqlDatabase(Database)

    :py:class:`Database` subclass that communicates to the "psycopg2" driver


Misc
----


.. py:class:: fn()

    A helper class that will convert arbitrary function calls to SQL function calls.

    To express functions in peewee, use the :py:class:`fn` object.  The way it works is
    anything to the right of the "dot" operator will be treated as a function.  You can
    pass that function arbitrary parameters which can be other valid expressions.

    For example:

    ============================================ ============================================
    Peewee expression                            Equivalent SQL
    ============================================ ============================================
    ``fn.Count(Tweet.id).alias('count')``        ``Count(t1."id") AS count``
    ``fn.Lower(fn.Substr(User.username, 1, 1))`` ``Lower(Substr(t1."username", 1, 1))``
    ``fn.Rand().alias('random')``                ``Rand() AS random``
    ``fn.Stddev(Employee.salary).alias('sdv')``  ``Stddev(t1."salary") AS sdv``
    ============================================ ============================================

.. py:function:: raw_sql(query)

    :param query: a :py:class:`Query` instance.
    :rtype: 2-tuple of SQL query and parameters for the given query
