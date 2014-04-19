API Reference
=============

.. _expressions-api:

.. include:: expressions.rst

.. _model-api:

Models
------

.. py:class:: Model(**kwargs)

    Models provide a 1-to-1 mapping to database tables.  Subclasses of
    ``Model`` declare any number of :py:class:`Field` instances as class
    attributes.  These fields correspond to columns on the table.

    Table-level operations, such as select/update/insert/delete queries, are
    implemented as classmethods.  Row-level operations such as saving or
    deleting individual instances are implemented as instancemethods.

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

        :param selection: a list of model classes, field instances, functions
          or :ref:`expressions <expressions>`
        :rtype: a :py:class:`SelectQuery` for the given ``Model``

        Examples of selecting all columns (default):

        .. code-block:: python

            User.select().where(User.active == True).order_by(User.username)

        Example of selecting all columns on ``Tweet`` *and* the parent model,
        ``User``.  When the ``user`` foreign key is accessed on a ``Tweet``
        instance no additional query will be needed:

        .. code-block:: python

            (Tweet
              .select(Tweet, User)
              .join(User)
              .order_by(Tweet.created_date.desc()))

    .. py:classmethod:: update(**update)

        :param update: mapping of field-name to expression
        :rtype: an :py:class:`UpdateQuery` for the given ``Model``

        Example showing users being marked inactive if their registration
        expired:

        .. code-block:: python

            q = User.update(active=False).where(User.registration_expired == True)
            q.execute()  # execute the query, updating the database.

        Example showing an atomic update:

        .. code-block:: python

            q = PageView.update(count=PageView.count + 1).where(PageView.url == url)
            q.execute()  # execute the query, updating the database.

    .. py:classmethod:: insert(**insert)

        Insert a new row into the database. If any fields on the model have
        default values, these values will be used if the fields are not explicitly
        set in the ``insert`` dictionary.

        :param insert: mapping of field or field-name to expression
        :rtype: an :py:class:`InsertQuery` for the given ``Model``

        Example showing creation of a new user:

        .. code-block:: python

            q = User.insert(username='admin', active=True, registration_expired=False)
            q.execute()  # perform the insert.

        You can also use :py:class:`Field` objects as the keys:

        .. code-block:: python

            User.insert(**{User.username: 'admin'}).execute()

        If you have a model with a default value on one of the fields, and
        that field is not specified in the ``insert`` parameter, the default
        will be used:

        .. code-block:: python

            class User(Model):
                username = CharField()
                active = BooleanField(default=True)

            # This INSERT query will automatically specify `active=True`:
            User.insert(username='charlie')

    .. py:method:: insert_many(rows)

        Insert multiple rows at once. The ``rows`` parameter must be an iterable
        that yields dictionaries. As with :py:meth:`~Model.insert`, fields that
        are not specified in the dictionary will use their default value, if
        one exists.

        .. note::
            Due to the nature of bulk inserts, each row must contain the same
            fields. The following would not work:

            .. code-block:: python

                Person.insert_many([
                    {'first_name': 'Peewee', 'last_name': 'Herman'},
                    {'first_name': 'Huey'},  # Missing "last_name"!
                ])

        :param rows: An iterable containing dictionaries of field-name-to-value.
        :rtype: an :py:class:`InsertQuery` for the given ``Model``.

        Example of inserting multiple Users:

        .. code-block:: python

            usernames = ['charlie', 'huey', 'peewee', 'mickey']
            row_dicts = [{'username': username} for username in usernames]

            # Insert 4 new rows.
            User.insert_many(row_dicts).execute()

        Because the ``rows`` parameter can be an arbitrary iterable, you can
        also use a generator:

        .. code-block:: python

            def get_usernames():
                for username in ['charlie', 'huey', 'peewee']:
                    yield {'username': username}
            User.insert_many(get_usernames()).execute()


    .. py:classmethod:: delete()

        :rtype: a :py:class:`DeleteQuery` for the given ``Model``

        Example showing the deletion of all inactive users:

        .. code-block:: python

            q = User.delete().where(User.active == False)
            q.execute()  # remove the rows

        .. warning::
            This method performs a delete on the *entire table*.  To delete a
            single instance, see :py:meth:`Model.delete_instance`.

    .. py:classmethod:: raw(sql, *params)

        :param sql: a string SQL expression
        :param params: any number of parameters to interpolate
        :rtype: a :py:class:`RawQuery` for the given ``Model``

        Example selecting rows from the User table:

        .. code-block:: python

            q = User.raw('select id, username from users')
            for user in q:
                print user.id, user.username

        .. note::
            Generally the use of ``raw`` is reserved for those cases where you
            can significantly optimize a select query.  It is useful for select
            queries since it will return instances of the model.

    .. py:classmethod:: create(**attributes)

        :param attributes: key/value pairs of model attributes
        :rtype: a model instance with the provided attributes

        Example showing the creation of a user (a row will be added to the
        database):

        .. code-block:: python

            user = User.create(username='admin', password='test')

        .. note::
            The create() method is a shorthand for instantiate-then-save.

    .. py:classmethod:: get(*args, **kwargs)

        :param args: a list of query expressions, e.g. ``User.username == 'foo'``
        :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"
        :rtype: :py:class:`Model` instance or raises ``DoesNotExist`` exception

        Get a single row from the database that matches the given query.
        Raises a ``<model-class>.DoesNotExist`` if no rows are returned:

        .. code-block:: python

            user = User.get(User.username == username, User.password == password)

        This method is also exposed via the :py:class:`SelectQuery`, though it
        takes no parameters:

        .. code-block:: python

            active = User.select().where(User.active == True)
            try:
                users = active.where(User.username == username, User.password == password)
                user = users.get()
            except User.DoesNotExist:
                user = None

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

            CachedObj.get_or_create(key=key, val=some_val)

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

            sq = Entry.filter(blog__title='Some Blog')

    .. py:classmethod:: alias()

        :rtype: :py:class:`ModelAlias` instance

        The alias() method is used to build queries that use self-joins.

        Example:

        .. code-block:: pycon

            Parent = Category.alias()
            sq = (Category
              .select(Category, Parent)
              .join(Parent, on=(Category.parent == Parent.id))
              .where(Parent.name == 'parent category'))

        .. note:: You must explicitly specify which columns to join on

    .. py:classmethod:: create_table([fail_silently=False])

        :param bool fail_silently: If set to ``True``, the method will check
          for the existence of the table before attempting to create.

        Create the table for the given model.

        Example:

        .. code-block:: python

            database.connect()
            SomeModel.create_table()  # Execute the create table query.

    .. py:classmethod:: drop_table([fail_silently=False[, cascade=False]])

        :param bool fail_silently: If set to ``True``, the query will check for
          the existence of the table before attempting to remove.
        :param bool cascade: Drop table with ``CASCADE`` option.

        Drop the table for the given model.

    .. py:classmethod:: table_exists()

        :rtype: Boolean whether the table for this model exists in the database

    .. py:method:: save([force_insert=False[, only=None]])

        :param bool force_insert: Whether to force execution of an insert
        :param list only: A list of fields to persist -- when supplied, only the given
            fields will be persisted.

        Save the given instance, creating or updating depending on whether it has a
        primary key.  If ``force_insert=True`` an ``INSERT`` will be issued regardless
        of whether or not the primary key exists.

        Example showing saving a model instance:

        .. code-block:: python

            user = User()
            user.username = 'some-user'  # does not touch the database
            user.save()  # change is persisted to the db

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

            some_obj.delete_instance()  # it is gone forever

    .. py:method:: dependencies([search_nullable=False])

        :param bool search_nullable: Search models related via a nullable foreign key
        :rtype: Generator expression yielding queries and foreign key fields

        Generate a list of queries of dependent models.  Yields a 2-tuple containing
        the query and corresponding foreign key field.  Useful for searching dependencies
        of a model, i.e. things that would be orphaned in the event of a delete.

    .. py:attribute:: dirty_fields

        Return a list of fields that were manually set.

        :rtype: list

        .. note::
            If you just want to persist modified fields, you can call
            ``model.save(only=model.dirty_fields)``.

    .. py:method:: is_dirty()

        Return whether any fields were manually set.

        :rtype: bool



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
    :param list constraints: a list of constraints, e.g. ``[Check('price > 0')]``.
    :param string schema: name of schema (if backend supports it)
    :param kwargs: named attributes containing values that may pertain to specific field subclasses, such as "max_length" or "decimal_places"

    .. py:attribute:: db_field = '<some field type>'

        Attribute used to map this field to a column type, e.g. "string" or "datetime"

    .. py:attribute:: _is_bound

        Boolean flag indicating if the field is attached to a model class.

    .. py:attribute:: model_class

        The model the field belongs to. *Only applies to bound fields.*

    .. py:attribute:: name

        The name of the field. *Only applies to bound fields.*

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

    .. py:method:: between(low, high)

        Return an expression suitable for performing "BETWEEN" queries.

        :rtype: an ``Expression`` object.

        .. code-block:: python

            # select employees making between $50 and $60
            Employee.select().where(Employee.salary.between(50, 60))

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

    .. py:attribute:: year

        An expression suitable for extracting the year, for example to retrieve
        all blog posts from 2013:

        .. code-block:: python

            Blog.select().where(Blog.pub_date.year == 2013)

    .. py:attribute:: month

        Same as :py:attr:`~DateTimeField.year`, except extract month.

    .. py:attribute:: day

        Same as :py:attr:`~DateTimeField.year`, except extract day.

    .. py:attribute:: hour

        Same as :py:attr:`~DateTimeField.year`, except extract hour.

    .. py:attribute:: minute

        Same as :py:attr:`~DateTimeField.year`, except extract minute.

    .. py:attribute:: second

        Same as :py:attr:`~DateTimeField.year`, except extract second..

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

    .. py:attribute:: year

        An expression suitable for extracting the year, for example to retrieve
        all people born in 1980:

        .. code-block:: python

            Person.select().where(Person.dob.year == 1983)

    .. py:attribute:: month

        Same as :py:attr:`~DateField.year`, except extract month.

    .. py:attribute:: day

        Same as :py:attr:`~DateField.year`, except extract day.

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

    .. py:attribute:: hour

        Extract the hour from a time, for example to retreive all events
        occurring in the evening:

        .. code-block:: python

            Event.select().where(Event.time.hour > 17)

    .. py:attribute:: minute

        Same as :py:attr:`~TimeField.hour`, except extract minute.

    .. py:attribute:: second

        Same as :py:attr:`~TimeField.hour`, except extract second..

.. py:class:: BooleanField

    Stores: ``True`` / ``False``

    .. py:attribute:: db_field = 'bool'

.. py:class:: ForeignKeyField(rel_model[, related_name=None[, on_delete=None[, on_update=None[, to_field=None[, ...]]]]])

    Stores: relationship to another model

    :param rel_model: related :py:class:`Model` class or the string 'self' if declaring
               a self-referential foreign key
    :param string related_name: attribute to expose on related model
    :param string on_delete: on delete behavior, e.g. ``on_delete='CASCADE'``.
    :param string on_update: on update behavior.
    :param to_field: the field (or field name) on ``rel_model`` the foreign key
        references. Defaults to the primary key field for ``rel_model``.

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

    .. note:: If you manually specify a ``to_field``, that field must be either
        a primary key or have a unique constraint.


.. py:class:: CompositeKey(*fields)

    Specify a composite primary key for a model.  Unlike the other fields, a
    composite key is defined in the model's ``Meta`` class after the fields
    have been defined.  It takes as parameters the string names of the fields
    to use as the primary key:

    .. code-block:: python

        class BlogTagThrough(Model):
            blog = ForeignKeyField(Blog, related_name='tags')
            tag = ForeignKeyField(Tag, related_name='blogs')

            class Meta:
                primary_key = CompositeKey('blog', 'tag')


.. _query-types:

Query Types
-----------

.. py:class:: Query

    The parent class from which all other query classes are drived.

    .. py:method:: where(*expressions)

        :param expressions: a list of one or more :ref:`expressions <expressions>`
        :rtype: a :py:class:`Query` instance

        Example selection users where the username is equal to 'somebody':

        .. code-block:: python

            sq = SelectQuery(User).where(User.username == 'somebody')

        Example selecting tweets made by users who are either editors or administrators:

        .. code-block:: python

            sq = SelectQuery(Tweet).join(User).where(
                (User.is_editor == True) |
                (User.is_admin == True))

        Example of deleting tweets by users who are no longer active:

        .. code-block:: python

            dq = DeleteQuery(Tweet).where(
                Tweet.user << User.select().where(User.active == False))
            dq.execute()  # perform the delete query

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
        :rtype: a :py:class:`Query` instance

        Generate a ``JOIN`` clause from the current ``query context`` to the ``model`` passed
        in, and establishes ``model`` as the new ``query context``.

        Example selecting tweets and joining on user in order to restrict to
        only those tweets made by "admin" users:

        .. code-block:: python

            sq = SelectQuery(Tweet).join(User).where(User.is_admin == True)

        Example selecting users and joining on a particular foreign key field.
        See the :py:ref:`example app <example-app>` for a real-life usage:

        .. code-block:: python

            sq = SelectQuery(User).join(Relationship, on=Relationship.to_user)

    .. py:method:: switch(model)

        :param model: model to switch the ``query context`` to.
        :rtype: a clone of the query with a new query context

        Switches the ``query context`` to the given model.  Raises an exception if the
        model has not been selected or joined on previously.  Useful for performing
        multiple joins from a single table.

        The following example selects from blog and joins on both entry and user:

        .. code-block:: python

            sq = SelectQuery(Blog).join(Entry).switch(Blog).join(User)

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

            sq = Entry.filter(blog__title='Some Blog')

        This method is chainable:

        .. code-block:: python

            base_q = User.filter(active=True)
            some_user = base_q.filter(username='charlie')

        .. note:: this method is provided for compatibility with peewee 1.

    .. py:method:: alias(alias=None)

        :param str alias: A string to alias the result of this query
        :rtype: a Query instance

        Assign an alias to given query, which can be used as part of a subquery.

    .. py:method:: sql()

        :rtype: a 2-tuple containing the appropriate SQL query and a tuple of parameters

        .. warning: This method should be implemented by subclasses

    .. py:method:: execute()

        Execute the given query

        .. warning: This method should be implemented by subclasses

    .. py:method:: scalar([as_tuple=False])

        :param bool as_tuple: return the row as a tuple or a single value
        :rtype: the resulting row, either as a single value or tuple

        Provide a way to retrieve single values from select queries, for instance
        when performing an aggregation.

        .. code-block:: pycon

            >>> PageView.select(fn.Count(fn.Distinct(PageView.url))).scalar()
            100 # <-- there are 100 distinct URLs in the pageview table


.. py:class:: SelectQuery(model_class, *selection)

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

        sq = SelectQuery(User, User.id, User.username)
        for user in sq:
            print user.username

    Example selecting users and additionally the number of tweets made by the user.
    The ``User`` instances returned will have an additional attribute, 'count', that
    corresponds to the number of tweets made:

    .. code-block:: python

        sq = (SelectQuery(
            User, User, fn.Count(Tweet.id).alias('count'))
            .join(Tweet)
            .group_by(User))

    .. py:method:: select(*selection)

        :param selection: a list of expressions, which can be model classes or fields.
          if left blank, will default to all the fields of the given model.
        :rtype: :py:class:`SelectQuery`

        .. note::
            Usually the selection will be specified when the instance is created.
            This method simply exists for the case when you want to modify the
            SELECT clause independent of instantiating a query.

        .. code-block:: python

            query = User.select()
            query = query.select(User.username)

    .. py:method:: from_(*args)

        :param args: one or more expressions, for example :py:class:`Model`
          or :py:class:`SelectQuery` instance(s). if left blank, will default
          to the table of the given model.
        :rtype: :py:class:`SelectQuery`

        .. code-block:: python

            # rather than a join, select from both tables and join with where.
            query = User.select().from_(User, Blog).where(Blog.user == User.id)

    .. py:method:: group_by(*clauses)

        :param clauses: a list of expressions, which can be model classes or individual field instances
        :rtype: :py:class:`SelectQuery`

        Group by one or more columns.  If a model class is provided, all the fields
        on that model class will be used.

        Example selecting users, joining on tweets, and grouping by the user so
        a count of tweets can be calculated for each user:

        .. code-block:: python

            sq = (User
                .select(User, fn.Count(Tweet.id).alias('count'))
                .join(Tweet)
                .group_by(User))

    .. py:method:: having(*expressions)

        :param expressions: a list of one or more :ref:`expressions <expressions>`
        :rtype: :py:class:`SelectQuery`

        Here is the above example selecting users and tweet counts, but restricting
        the results to those users who have created 100 or more tweets:

        .. code-block:: python

            sq = (User
                .select(User, fn.Count(Tweet.id).alias('count'))
                .join(Tweet)
                .group_by(User)
                .having(fn.Count(Tweet.id) > 100))

    .. py:method:: order_by(*clauses)

        :param clauses: a list of fields, calls to ``field.[asc|desc]()`` or one or more :ref:`expressions <expressions>`
        :rtype: :py:class:`SelectQuery`

        Example of ordering users by username:

        .. code-block:: python

            User.select().order_by(User.username)

        Example of selecting tweets and ordering them first by user, then newest
        first:

        .. code-block:: python

            Tweet.select().join(User).order_by(
                User.username, Tweet.created_date.desc())

        A more complex example ordering users by the number of tweets made (greatest
        to least), then ordered by username in the event of a tie:

        .. code-block:: python

            tweet_ct = fn.Count(Tweet.id)
            sq = (User
                .select(User, tweet_ct.alias('count'))
                .join(Tweet)
                .group_by(User)
                .order_by(tweet_ct.desc(), User.username))

    .. py:method:: limit(num)

        :param int num: limit results to ``num`` rows

    .. py:method:: offset(num)

        :param int num: offset results by ``num`` rows

    .. py:method:: paginate(page_num, paginate_by=20)

        :param page_num: a 1-based page number to use for paginating results
        :param paginate_by: number of results to return per-page
        :rtype: :py:class:`SelectQuery`

        Shorthand for applying a ``LIMIT`` and ``OFFSET`` to the query.

        Page indices are **1-based**, so page 1 is the first page.

        .. code-block:: python

            User.select().order_by(User.username).paginate(3, 20)  # get users 41-60

    .. py:method:: distinct()

        :rtype: :py:class:`SelectQuery`

        indicates that this query should only return distinct rows.  results in a
        ``SELECT DISTINCT`` query.

    .. py:method:: for_update([for_update=True[, nowait=False]])

        :rtype: :py:class:`SelectQuery`

        Indicate that this query should lock rows for update.  If ``nowait`` is
        ``True`` then the database will raise an ``OperationalError`` if it
        cannot obtain the lock.

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

    .. py:method:: iterator()

        :rtype: ``iterable``

        By default peewee will cache rows returned by the cursor.  This is to
        prevent things like multiple iterations, slicing and indexing from
        triggering extra queries.  When you are iterating over a large number
        of rows, however, this cache can take up a lot of memory. Using ``iterator()``
        will save memory by not storing all the returned model instances.

        .. code-block:: python

            # iterate over large number of rows.
            for obj in Stats.select().iterator():
                # do something.
                pass

    .. py:method:: tuples()

        :rtype: :py:class:`SelectQuery`

        Flag this query indicating it should simply return raw tuples from the cursor.
        This method is useful when you either do not want or do not need full model
        instances.

    .. py:method:: dicts()

        :rtype: :py:class:`SelectQuery`

        Flag this query indicating it should simply return dictionaries from the cursor.
        This method is useful when you either do not want or do not need full model
        instances.

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

                User.select().join(Tweet, JOIN_LEFT_OUTER).annotate(Tweet)

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
        45  # number of tweets
        >>> sq.where(Tweet.status == DELETED)
        >>> sq.count()
        3  # number of tweets that are marked as deleted

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

            sq = User.select().where(User.active == True)
            if sq.where(User.username == username, User.password == password).exists():
                authenticated = True

    .. py:method:: get()

        :rtype: :py:class:`Model` instance or raises ``DoesNotExist`` exception

        Get a single row from the database that matches the given query.  Raises a
        ``<model-class>.DoesNotExist`` if no rows are returned:

        .. code-block:: python

            active = User.select().where(User.active == True)
            try:
                user = active.where(User.username == username).get()
            except User.DoesNotExist:
                user = None

        This method is also exposed via the :py:class:`Model` api, in which case it
        accepts arguments that are translated to the where clause:

            user = User.get(User.active == True, User.username == username)

    .. py:method:: first()

        :rtype: :py:class:`Model` instance or ``None`` if no results

        Fetch the first row from a query. The result will be cached in case the entire
        query result-set should be iterated later.

    .. py:method:: execute()

        :rtype: :py:class:`QueryResultWrapper`

        Executes the query and returns a :py:class:`QueryResultWrapper` for iterating over
        the result set.  The results are managed internally by the query and whenever
        a clause is added that would possibly alter the result set, the query is
        marked for re-execution.

    .. py:method:: __iter__()

        Executes the query and returns populated model instances:

        .. code-block:: python

            for user in User.select().where(User.active == True):
                print user.username

    .. py:method:: __getitem__(value)

        :param value: Either an index or a ``slice`` object.

        Return the model instance(s) at the requested indices. To get the first
        model, for instance:

        .. code-block:: python

            query = User.select().order_by(User.username)
            first_user = query[0]
            first_five = query[:5]

    .. py:method:: __or__(rhs)

        :param rhs: Either a :py:class:`SelectQuery` or a :py:class:`CompoundSelect`
        :rtype: :py:class:`CompoundSelect`

        Create a ``UNION`` query with the right-hand object. The result will contain
        all values from both the left and right queries.

        .. code-block:: python

            customers = Customer.select(Customer.city).where(Customer.state == 'KS')
            stores = Store.select(Store.city).where(Store.state == 'KS')

            # Get all cities in kansas where we have either a customer or a store.
            all_cities = (customers | stores).order_by(SQL('city'))

    .. py:method:: __and__(rhs)

        :param rhs: Either a :py:class:`SelectQuery` or a :py:class:`CompoundSelect`
        :rtype: :py:class:`CompoundSelect`

        Create an ``INTERSECT`` query. The result will contain values that are in
        both the left and right queries.

        .. code-block:: python

            customers = Customer.select(Customer.city).where(Customer.state == 'KS')
            stores = Store.select(Store.city).where(Store.state == 'KS')

            # Get all cities in kanasas where we have both customers and stores.
            cities = (customers & stores).order_by(SQL('city'))

    .. py:method:: __sub__(rhs)

        :param rhs: Either a :py:class:`SelectQuery` or a :py:class:`CompoundSelect`
        :rtype: :py:class:`CompoundSelect`

        Create an ``EXCEPT`` query. The result will contain values that are in
        the left-hand query but not in the right-hand query.

        .. code-block:: python

            customers = Customer.select(Customer.city).where(Customer.state == 'KS')
            stores = Store.select(Store.city).where(Store.state == 'KS')

            # Get all cities in kanasas where we have customers but no stores.
            cities = (customers - stores).order_by(SQL('city'))

    .. py:method:: __xor__(rhs)

        :param rhs: Either a :py:class:`SelectQuery` or a :py:class:`CompoundSelect`
        :rtype: :py:class:`CompoundSelect`

        Create an symmetric difference query. The result will contain values
        that are in either the left-hand query or the right-hand query, but not
        both.

        .. code-block:: python

            customers = Customer.select(Customer.city).where(Customer.state == 'KS')
            stores = Store.select(Store.city).where(Store.state == 'KS')

            # Get all cities in kanasas where we have either customers with no
            # store, or a store with no customers.
            cities = (customers ^ stores).order_by(SQL('city'))


.. py:class:: UpdateQuery(model_class, **kwargs)

    :param model: :py:class:`Model` class on which to perform update
    :param kwargs: mapping of field/value pairs containing columns and values to update

    Example in which users are marked inactive if their registration expired:

    .. code-block:: python

        uq = UpdateQuery(User, active=False).where(User.registration_expired == True)
        uq.execute()  # Perform the actual update

    Example of an atomic update:

    .. code-block:: python

        atomic_update = UpdateQuery(PageCount, count = PageCount.count + 1).where(
            PageCount.url == url)
        atomic_update.execute()  # will perform the actual update

    .. py:method:: execute()

        :rtype: Number of rows updated

        Performs the query


.. py:class:: InsertQuery(model_class[, field_dict=None[, rows=None]])

    Creates an ``InsertQuery`` instance for the given model.

    :param dict field_dict: A mapping of either field or field-name to value.
    :param iterable rows: An iterable of dictionaries containing a mapping of
        field or field-name to value.

    Basic example:

    .. code-block:: pycon

        >>> fields = {'username': 'admin', 'password': 'test', 'active': True}
        >>> iq = InsertQuery(User, fields)
        >>> iq.execute()  # insert new row and return primary key
        2L

    Example inserting multiple rows:

    .. code-block:: python

        users = [
            {'username': 'charlie', 'active': True},
            {'username': 'peewee', 'active': False},
            {'username': 'huey', 'active': True}]
        iq = InsertQuery(User, rows=users)
        iq.execute()

    .. py:method:: execute()

        :rtype: primary key of the new row

        Performs the query

    .. py:method:: upsert([upsert=True])

        Perform an ``INSERT OR REPLACE`` query. Currently only Sqlite supports
        this method.


.. py:class:: DeleteQuery(model_class)

    Creates a ``DeleteQuery`` instance for the given model.

    .. note::
        DeleteQuery will *not* traverse foreign keys or ensure that constraints
        are obeyed, so use it with care.

    Example deleting users whose account is inactive:

    .. code-block:: python

        dq = DeleteQuery(User).where(User.active == False)

    .. py:method:: execute()

        :rtype: Number of rows deleted

        Performs the query


.. py:class:: RawQuery(model_class, sql, *params)

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

    .. code-block:: pycon

        >>> rq = RawQuery(User, 'SELECT * FROM users WHERE username = ?', 'admin')
        >>> for obj in rq.execute():
        ...     print obj
        <User: admin>

    .. py:method:: tuples()

        :rtype: :py:class:`RawQuery`

        Flag this query indicating it should simply return raw tuples from the cursor.
        This method is useful when you either do not want or do not need full model
        instances.

    .. py:method:: dicts()

        :rtype: :py:class:`RawQuery`

        Flag this query indicating it should simply return raw dicts from the cursor.
        This method is useful when you either do not want or do not need full model
        instances.

    .. py:method:: execute()

        :rtype: a :py:class:`QueryResultWrapper` for iterating over the result set.  The results are instances of the given model.

        Performs the query


.. py:class:: CompoundSelect(model_class, lhs, operator, rhs)

    Compound select query.

    :param model_class: The type of model to return, by default the model class
        of the ``lhs`` query.
    :param lhs: Left-hand query, either a :py:class:`SelectQuery` or a :py:class:`CompoundQuery`.
    :param operator: A :py:class:`Node` instance used to join the two queries, for example ``SQL('UNION')``.
    :param rhs: Right query, either a :py:class:`SelectQuery` or a :py:class:`CompoundQuery`.


.. py:function:: prefetch(sq, *subqueries)

    :param sq: :py:class:`SelectQuery` instance
    :param subqueries: one or more :py:class:`SelectQuery` instances to prefetch for ``sq``. You
        can also pass models, but they will be converted into SelectQueries.

    :rtype: :py:class:`SelectQuery` with related instances pre-populated

    Pre-fetch the appropriate instances from the subqueries and apply them to
    their corresponding parent row in the outer query. This function will eagerly
    load the related instances specified in the subqueries. This is a technique used
    to save doing O(n) queries for n rows, and rather is O(k) queries for *k*
    subqueries.

    For example, consider you have a list of users and want to display all their
    tweets:

    .. code-block:: python

        # let's impost some small restrictions on our queries
        users = User.select().where(User.active == True)
        tweets = Tweet.select().where(Tweet.published == True)

        # this will perform 2 queries
        users_pf = prefetch(users, tweets)

        # now we can:
        for user in users_pf:
            print user.username
            for tweet in user.tweets_prefetch:
                print '- ', tweet.content

    You can prefetch an arbitrary number of items.  For instance, suppose we have
    a photo site, User -> Photo -> (Comments, Tags).  That is, users can post photos,
    and these photos can have tags and comments on them.  If we wanted to fetch a
    list of users, all their photos, and all the comments and tags on the photos:

    .. code-block:: python

        users = User.select()
        published_photos = Photo.select().where(Photo.published == True)
        published_comments = Comment.select().where(
            (Comment.is_spam == False) &
            (Comment.num_flags < 3))

        # note that we are just passing the Tag model -- it will be converted
        # to a query automatically
        users_pf = prefetch(users, published_photos, published_comments, Tag)

        # now we can iterate users, photos, and comments/tags
        for user in users_pf:
            for photo in user.photo_set_prefetch:
                for comment in photo.comment_set_prefetch:
                    # ...
                for tag in photo.tag_set_prefetch:
                    # ...


    .. note:: Subqueries must be related by foreign key and can be arbitrarily deep

    .. warning::
        :py:func:`prefetch` can use up lots of RAM when the result set is large,
        and will not warn you if you are doing something dangerous, so it is up
        to you to know when to use it.  Additionally, because of the semantics of
        subquerying, there may be some cases when prefetch does not act as you
        expect (for instnace, when applying a ``LIMIT`` to subqueries, but there
        may be others) -- please report anything you think is a bug to `github <https://github.com/coleifer/peewee/issues>`_.


Database and its subclasses
---------------------------

.. py:class:: Database(database[, threadlocals=False[, autocommit=True[, fields=None[, ops=None[, autorollback=False[, **connect_kwargs]]]]]])

    :param database: the name of the database (or filename if using sqlite)
    :param bool threadlocals: whether to store connections in a threadlocal
    :param bool autocommit: automatically commit every query executed by calling :py:meth:`~Database.execute`
    :param dict fields: a mapping of :py:attr:`~Field.db_field` to database column type, e.g. 'string' => 'varchar'
    :param dict ops: a mapping of operations understood by the querycompiler to expressions
    :param bool autorollback: automatically rollback when an exception occurs while executing a query.
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

    .. py:attribute:: foreign_keys = True

        Whether the given backend enforces foreign key constraints.

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

    .. py:method:: compiler()

        :rtype: an instance of :py:class:`QueryCompiler` using the field and
            op overrides specified.

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

    .. py:method:: create_foreign_key(model_class, field[, constraint=None])

        :param model_class: :py:class:`Model` table on which to create foreign key constraint
        :param field: :py:class:`Field` object
        :param str constraint: Name to give foreign key constraint.

        Manually create a foreign key constraint using an ``ALTER TABLE`` query.
        This is primarily used when creating a circular foreign key dependency,
        for example:

        .. code-block:: python

            PostProxy = Proxy()

            class User(Model):
                username = CharField()
                favorite_post = ForeignKeyField(PostProxy, null=True)

            class Post(Model):
                title = CharField()
                author = ForeignKeyField(User, related_name='posts')

            PostProxy.initialize(Post)

            # Create tables.  The foreign key from Post -> User will be created
            # automatically, but the foreign key from User -> Post must be added
            # manually.
            User.create_table()
            Post.create_table()

            # Manually add the foreign key constraint on `User`, since we could
            # not add it until we had created the `Post` table.
            db.create_foreign_key(User, User.favorite_post)

    .. py:method:: create_sequence(sequence_name)

        :param sequence_name: name of sequence to create

        .. note:: only works with database engines that support sequences

    .. py:method:: drop_table(model_class[, fail_silently=False[, cascade=False]])

        :param model_class: :py:class:`Model` table to drop
        :param bool fail_silently: if ``True``, query will add a ``IF EXISTS`` clause
        :param bool cascade: drop table with ``CASCADE`` option.

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

        Nested functions can be wrapped with ``commit_on_success`` - the database
        will keep a stack and only commit when it reaches the end of the outermost
        function.

        :param func: function to decorate

        .. code-block:: python

            @database.commit_on_success
            def transfer_money(from_acct, to_acct, amt):
                from_acct.charge(amt)
                to_acct.pay(amt)
                return amt

    .. py:method:: savepoint([sid=None])

        Return a context manager that executes statements in a savepoint.  If an
        error is raised inside the context manager, the savepoint will be rolled
        back, otherwise statements are committed when exiting.

        Savepoints can be thought of as nested transactions.

        :param str sid: A string identifier for the savepoint.

    .. py:classmethod:: register_fields(fields)

        Register a mapping of field overrides for the database class.  Used
        to register custom fields or override the defaults.

        :param dict fields: A mapping of :py:attr:`~Field.db_field` to column type

    .. py:classmethod:: register_ops(ops)

        Register a mapping of operations understood by the QueryCompiler to their
        SQL equivalent, e.g. ``{OP_EQ: '='}``.  Used to extend the types of field
        comparisons.

        :param dict fields: A mapping of :py:attr:`~Field.db_field` to column type

    .. py:method:: extract_date(date_part, date_field)

        Return an expression suitable for extracting a date part from a date
        field.  For instance, extract the year from a :py:class:`DateTimeField`.

        :param str date_part: The date part attribute to retrieve.  Valid options
          are: "year", "month", "day", "hour", "minute" and "second".
        :param Field date_field: field instance storing a datetime, date or time.
        :rtype: an expression object.

    .. py:method:: sql_error_handler(exception, sql, params, require_commit)

        This hook is called when an error is raised executing a query, allowing
        your application to inject custom error handling behavior.  The default
        implementation simply reraises the exception.

        .. code-block:: python

            class SqliteDatabaseCustom(SqliteDatabase):
                def sql_error_handler(self, exception, sql, params, require_commit):
                    # Perform some custom behavior, for example close the
                    # connection to the database.
                    self.close()

                    # Re-raise the exception.
                    raise exception


.. py:class:: SqliteDatabase(Database)

    :py:class:`Database` subclass that works with the "sqlite3" driver

.. py:class:: MySQLDatabase(Database)

    :py:class:`Database` subclass that works with either "MySQLdb" or "pymysql".

.. py:class:: PostgresqlDatabase(Database)

    :py:class:`Database` subclass that works with the "psycopg2" driver


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

    .. py:method:: over([partition_by=None[, order_by=None]])

        Basic support for SQL window functions.

        :param list partition_by: List of :py:class:`Node` instances to partition by.
        :param list order_by: List of :py:class:`Node` instances to use for ordering.

        Examples:

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

            # Get a list of page-views, along with avg pageviews for that day.
            query = (PageView
                     .select(
                         PageView.url,
                         PageView.timestamp,
                         fn.Count(PageView.id).over(
                             partition_by=[fn.date_trunc(
                                 'day', PageView.timestamp)]))
                     .order_by(PageView.timestamp))

.. py:class:: SQL(sql, *params)

    Add fragments of SQL to a peewee query.  For example you might want to reference
    an aliased name.

    :param str sql: Arbitrary SQL string.
    :param params: Arbitrary query parameters.

    .. code-block:: python

        # Retrieve user table and "annotate" it with a count of tweets for each
        # user.
        query = (User
                 .select(User, fn.Count(Tweet.id).alias('ct'))
                 .join(Tweet, JOIN_LEFT_OUTER)
                 .group_by(User))

        # Sort the users by number of tweets.
        query = query.order_by(SQL('ct DESC'))


.. py:class:: Proxy()

    Proxy class useful for situations when you wish to defer the initialization of
    an object.  For instance, you want to define your models but you do not know
    what database engine you will be using until runtime.

    Example:

        .. code-block:: python

            database_proxy = Proxy()  # Create a proxy for our db.

            class BaseModel(Model):
                class Meta:
                    database = database_proxy  # Use proxy for our DB.

            class User(BaseModel):
                username = CharField()

            # Based on configuration, use a different database.
            if app.config['DEBUG']:
                database = SqliteDatabase('local.db')
            elif app.config['TESTING']:
                database = SqliteDatabase(':memory:')
            else:
                database = PostgresqlDatabase('mega_production_db')

            # Configure our proxy to use the db we specified in config.
            database_proxy.initialize(database)

    .. py:method:: initialize(obj)

        :param obj: The object to proxy to.

        Once initialized, the attributes and methods on ``obj`` can be accessed
        directly via the :py:class:`Proxy` instance.
