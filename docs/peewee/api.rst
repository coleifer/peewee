.. _api:

API Reference
=============

.. _model-api:

Models
------

.. py:class:: Model(**kwargs)

    Models provide a 1-to-1 mapping to database tables. Subclasses of
    ``Model`` declare any number of :py:class:`Field` instances as class
    attributes. These fields correspond to columns on the table.

    Table-level operations, such as :py:meth:`~Model.select`, :py:meth:`~Model.update`,
    :py:meth:`~Model.insert`, and :py:meth:`~Model.delete`, are implemented
    as classmethods. Row-level operations such as :py:meth:`~Model.save` and
    :py:meth:`~Model.delete_instance` are implemented as instancemethods.

    :param kwargs: Initialize the model, assigning the given key/values to the
        appropriate fields.

    Example:

    .. code-block:: python

        class User(Model):
            username = CharField()
            join_date = DateTimeField(default=datetime.datetime.now)
            is_admin = BooleanField()

        u = User(username='charlie', is_admin=True)

    .. py:classmethod:: select(*selection)

        :param selection: A list of model classes, field instances, functions
          or expressions. If no argument is provided, all columns for the given model
          will be selected.
        :rtype: a :py:class:`SelectQuery` for the given :py:class:`Model`.

        Examples of selecting all columns (default):

        .. code-block:: python

            User.select().where(User.active == True).order_by(User.username)

        Example of selecting all columns on *Tweet* and the parent model,
        *User*. When the ``user`` foreign key is accessed on a *Tweet*
        instance no additional query will be needed (see :ref:`N+1 <nplusone>`
        for more details):

        .. code-block:: python

            (Tweet
              .select(Tweet, User)
              .join(User)
              .order_by(Tweet.created_date.desc()))

    .. py:classmethod:: update(**update)

        :param update: mapping of field-name to expression
        :rtype: an :py:class:`UpdateQuery` for the given :py:class:`Model`

        Example showing users being marked inactive if their registration
        expired:

        .. code-block:: python

            q = User.update(active=False).where(User.registration_expired == True)
            q.execute()  # Execute the query, updating the database.

        Example showing an atomic update:

        .. code-block:: python

            q = PageView.update(count=PageView.count + 1).where(PageView.url == url)
            q.execute()  # execute the query, updating the database.

        .. note:: When an update query is executed, the number of rows modified will be returned.

    .. py:classmethod:: insert(**insert)

        Insert a new row into the database. If any fields on the model have
        default values, these values will be used if the fields are not explicitly
        set in the ``insert`` dictionary.

        :param insert: mapping of field or field-name to expression.
        :rtype: an :py:class:`InsertQuery` for the given :py:class:`Model`.

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

        .. note:: When an insert query is executed on a table with an auto-incrementing primary key, the primary key of the new row will be returned.

    .. py:method:: insert_many(rows)

        Insert multiple rows at once. The ``rows`` parameter must be an iterable
        that yields dictionaries. As with :py:meth:`~Model.insert`, fields that
        are not specified in the dictionary will use their default value, if
        one exists.

        .. note::
            Due to the nature of bulk inserts, each row must contain the same
            fields. The following will not work:

            .. code-block:: python

                Person.insert_many([
                    {'first_name': 'Peewee', 'last_name': 'Herman'},
                    {'first_name': 'Huey'},  # Missing "last_name"!
                ])

        :param rows: An iterable containing dictionaries of field-name-to-value.
        :rtype: an :py:class:`InsertQuery` for the given :py:class:`Model`.

        Example of inserting multiple Users:

        .. code-block:: python

            usernames = ['charlie', 'huey', 'peewee', 'mickey']
            row_dicts = ({'username': username} for username in usernames)

            # Insert 4 new rows.
            User.insert_many(row_dicts).execute()

        Because the ``rows`` parameter can be an arbitrary iterable, you can
        also use a generator:

        .. code-block:: python

            def get_usernames():
                for username in ['charlie', 'huey', 'peewee']:
                    yield {'username': username}
            User.insert_many(get_usernames()).execute()

        .. warning::
            If you are using SQLite, your SQLite library must be version 3.7.11
            or newer to take advantage of bulk inserts.

        .. note::
            SQLite has a default limit of 999 bound variables per statement.
            This limit can be modified at compile-time or at run-time, **but**
            if modifying at run-time, you can only specify a *lower* value than
            the default limit.

            For more information, check out the following SQLite documents:

            * `Max variable number limit <https://www.sqlite.org/limits.html#max_variable_number>`_
            * `Changing run-time limits <https://www.sqlite.org/c3ref/limit.html>`_
            * `SQLite compile-time flags <https://www.sqlite.org/compile.html>`_

    .. py:classmethod:: insert_from(fields, query)

        Insert rows into the table using a query as the data source. This API should
        be used for *INSERT INTO...SELECT FROM* queries.

        :param fields: The field objects to map the selected data into.
        :param query: The source of the new rows.
        :rtype: an :py:class:`InsertQuery` for the given :py:class:`Model`.

        Example of inserting data across tables for denormalization purposes:

        .. code-block:: python

            source = (User
                      .select(User.username, fn.COUNT(Tweet.id))
                      .join(Tweet, JOIN.LEFT_OUTER)
                      .group_by(User.username))
            UserTweetDenorm.insert_from(
                [UserTweetDenorm.username, UserTweetDenorm.num_tweets],
                source).execute()

    .. py:classmethod:: delete()

        :rtype: a :py:class:`DeleteQuery` for the given :py:class:`Model`.

        Example showing the deletion of all inactive users:

        .. code-block:: python

            q = User.delete().where(User.active == False)
            q.execute()  # remove the rows

        .. warning::
            This method performs a delete on the *entire table*. To delete a
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
            can significantly optimize a select query. It is useful for select
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

    .. py:classmethod:: get(*args)

        :param args: a list of query expressions, e.g. ``User.username == 'foo'``
        :rtype: :py:class:`Model` instance or raises ``DoesNotExist`` exception

        Get a single row from the database that matches the given query.
        Raises a ``<model-class>.DoesNotExist`` if no rows are returned:

        .. code-block:: python

            user = User.get(User.username == username, User.active == True)

        This method is also exposed via the :py:class:`SelectQuery`, though it
        takes no parameters:

        .. code-block:: python

            active = User.select().where(User.active == True)
            try:
                user = active.where(
                    (User.username == username) &
                    (User.active == True)
                ).get()
            except User.DoesNotExist:
                user = None

        .. note::
            The :py:meth:`~Model.get` method is shorthand for selecting with a limit of 1. It
            has the added behavior of raising an exception when no matching row is
            found. If more than one row is found, the first row returned by the
            database cursor will be used.

    .. py:classmethod:: get_or_create([defaults=None[, **kwargs]])

        :param dict defaults: A dictionary of values to set on newly-created model instances.
        :param kwargs: Django-style filters specifying which model to get, and what values to apply to new instances.
        :returns: A 2-tuple containing the model instance and a boolean indicating whether the instance was created.

        This function attempts to retrieve a model instance based on the provided filters. If no matching model can be found, a new model is created using the parameters specified by the filters and any values in the ``defaults`` dictionary.

        .. note:: Use care when calling ``get_or_create`` with ``autocommit=False``, as the ``get_or_create()`` method will call :py:meth:`Database.atomic` to create either a transaction or savepoint.

        Example **without** ``get_or_create``:

        .. code-block:: python

            # Without `get_or_create`, we might write:
            try:
                person = Person.get(
                    (Person.first_name == 'John') &
                    (Person.last_name == 'Lennon'))
            except Person.DoesNotExist:
                person = Person.create(
                    first_name='John',
                    last_name='Lennon',
                    birthday=datetime.date(1940, 10, 9))

        Equivalent code using ``get_or_create``:

        .. code-block:: python

            person, created = Person.get_or_create(
                first_name='John',
                last_name='Lennon',
                defaults={'birthday': datetime.date(1940, 10, 9)})

    .. py:classmethod:: create_or_get([**kwargs])

        :param kwargs: Field name to value for attempting to create a new instance.
        :returns: A 2-tuple containing the model instance and a boolean indicating whether the instance was created.

        This function attempts to create a model instance based on the provided kwargs. If an ``IntegrityError`` occurs indicating the violation of a constraint, then Peewee will return the model matching the filters.

        .. note:: Peewee will not attempt to match *all* the kwargs when an ``IntegrityError`` occurs. Rather, only primary key fields or fields that have a unique constraint will be used to retrieve the matching instance.

        .. note:: Use care when calling ``create_or_get`` with ``autocommit=False``, as the ``create_or_get()`` method will call :py:meth:`Database.atomic` to create either a transaction or savepoint.

        Example:

        .. code-block:: python

            # This will succeed, there is no user named 'charlie' currently.
            charlie, created = User.create_or_get(username='charlie')

            # This will return the above object, since an IntegrityError occurs
            # when trying to create an object using "charlie's" primary key.
            user2, created = User.create_or_get(username='foo', id=charlie.id)

            assert user2.username == 'charlie'

    .. py:classmethod:: alias()

        :rtype: :py:class:`ModelAlias` instance

        The :py:meth:`alias` method is used to create self-joins.

        Example:

        .. code-block:: pycon

            Parent = Category.alias()
            sq = (Category
                  .select(Category, Parent)
                  .join(Parent, on=(Category.parent == Parent.id))
                  .where(Parent.name == 'parent category'))

        .. note:: When using a :py:class:`ModelAlias` in a join, you must explicitly specify the join condition.

    .. py:classmethod:: create_table([fail_silently=False])

        :param bool fail_silently: If set to ``True``, the method will check
          for the existence of the table before attempting to create.

        Create the table for the given model, along with any constraints and indexes.

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

    .. py:classmethod:: sqlall()

        :returns: A list of queries required to create the table and indexes.

    .. py:method:: save([force_insert=False[, only=None]])

        :param bool force_insert: Whether to force execution of an insert
        :param list only: A list of fields to persist -- when supplied, only the given
            fields will be persisted.

        Save the given instance, creating or updating depending on whether it has a
        primary key.  If ``force_insert=True`` an *INSERT* will be issued regardless
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

            If you **always** want to only save a model's dirty fields, you can use the Meta
            option ``only_save_dirty = True``. Then, any time you call :py:meth:`Model.save()`,
            by default only the dirty fields will be saved, e.g.

            .. code-block:: python

                class Person(Model):
                    first_name = CharField()
                    last_name = CharField()
                    dob = DateField()

                    class Meta:
                        database = db
                        only_save_dirty = True

    .. py:method:: is_dirty()

        Return whether any fields were manually set.

        :rtype: bool

    .. py:method:: prepared()

        This method provides a hook for performing model initialization *after*
        the row data has been populated.


.. _fields-api:

Fields
------

.. py:class:: Field(null=False, index=False, unique=False, verbose_name=None, help_text=None, db_column=None, default=None, choices=None, primary_key=False, sequence=None, constraints=None, schema=None, **kwargs):

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

.. py:class:: CharField

    Stores: small strings (0-255 bytes)

    Additional attributes and values:

    ================  =========================
    ``max_length``    ``255``
    ================  =========================

    .. py:attribute:: db_field = 'string'

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

        An expression suitable for extracting the month from a stored date.

    .. py:attribute:: day

        An expression suitable for extracting the day from a stored date.

    .. py:attribute:: hour

        An expression suitable for extracting the hour from a stored time.

    .. py:attribute:: minute

        An expression suitable for extracting the minute from a stored time.

    .. py:attribute:: second

        An expression suitable for extracting the second from a stored time.

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

.. py:class:: TimestampField

    Stores: python ``datetime.datetime`` instances (stored as integers)

    Accepts a special parameter ``resolution``, which is a power-of-10 up to
    ``10^6``. This allows sub-second precision while still using an
    :py:class:`IntegerField` for storage. Default is ``1`` (second precision).

    Also accepts a boolean parameter ``utc``, used to indicate whether the
    timestamps should be UTC. Default is ``False``.

    Finally, the field ``default`` is the current timestamp. If you do not want
    this behavior, then explicitly pass in ``default=None``.

.. py:class:: BooleanField

    Stores: ``True`` / ``False``

    .. py:attribute:: db_field = 'bool'

.. py:class:: BlobField

    Store arbitrary binary data.

.. py:class:: UUIDField

    Store ``UUID`` values.

    .. note:: Currently this field is only supported by :py:class:`PostgresqlDatabase`.

.. py:class:: BareField

    Intended to be used only with SQLite. Since data-types are not enforced, you can declare fields without *any* data-type. It is also common for SQLite virtual tables to use meta-columns or untyped columns, so for those cases as well you may wish to use an untyped field.

    Accepts a special ``coerce`` parameter, a function that takes a value coming from the database and converts it into the appropriate Python type.

    .. note:: Currently this field is only supported by :py:class:`SqliteDatabase`.

.. py:class:: ForeignKeyField(rel_model[, related_name=None[, on_delete=None[, on_update=None[, to_field=None[, ...]]]]])

    Stores: relationship to another model

    :param rel_model: related :py:class:`Model` class or the string 'self' if declaring a self-referential foreign key
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

.. py:class:: Query()

    The parent class from which all other query classes are drived. While you
    will not deal with :py:class:`Query` directly in your code, it implements some
    methods that are common across all query types.

    .. py:method:: where(*expressions)

        :param expressions: a list of one or more expressions
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
            one of ``JOIN.INNER``, ``JOIN.LEFT_OUTER``, ``JOIN.FULL``
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

    .. py:method:: scalar([as_tuple=False[, convert=False]])

        :param bool as_tuple: return the row as a tuple or a single value
        :param bool convert: attempt to coerce the selected value to the
          appropriate data-type based on it's associated Field type (assuming
          one exists).
        :rtype: the resulting row, either as a single value or tuple

        Provide a way to retrieve single values from select queries, for instance
        when performing an aggregation.

        .. code-block:: pycon

            >>> PageView.select(fn.Count(fn.Distinct(PageView.url))).scalar()
            100 # <-- there are 100 distinct URLs in the pageview table

        This example illustrates the use of the `convert` argument. When using
        a SQLite database, datetimes are stored as strings. To select the max
        datetime, and have it *returned* as a datetime, we will specify
        ``convert=True``.

        .. code-block:: pycon

            >>> PageView.select(fn.MAX(PageView.timestamp)).scalar()
            '2016-04-20 13:37:00.1234'

            >>> PageView.select(fn.MAX(PageView.timestamp)).scalar(convert=True)
            datetime.datetime(2016, 4, 20, 13, 37, 0, 1234)


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

        :param expressions: a list of one or more expressions
        :rtype: :py:class:`SelectQuery`

        Here is the above example selecting users and tweet counts, but restricting
        the results to those users who have created 100 or more tweets:

        .. code-block:: python

            sq = (User
                .select(User, fn.Count(Tweet.id).alias('count'))
                .join(Tweet)
                .group_by(User)
                .having(fn.Count(Tweet.id) > 100))

    .. py:method:: order_by(*clauses[, extend=False])

        :param clauses: a list of fields, calls to ``field.[asc|desc]()`` or
          one or more expressions. If called without any arguments, any
          pre-existing ``ORDER BY`` clause will be removed.
        :param extend: When called with ``extend=True``, Peewee will append any
          to the pre-existing ``ORDER BY`` rather than overwriting it.
        :rtype: :py:class:`SelectQuery`

        Example of ordering users by username:

        .. code-block:: python

            User.select().order_by(User.username)

        Example of selecting tweets and ordering them first by user, then newest
        first:

        .. code-block:: python

            query = (Tweet
                     .select()
                     .join(User)
                     .order_by(
                         User.username,
                         Tweet.created_date.desc()))

        You can also use ``+`` and ``-`` prefixes to indicate ascending or descending order if you prefer:

        .. code-block:: python

            query = (Tweet
                     .select()
                     .join(User)
                     .order_by(
                         +User.username,
                         -Tweet.created_date))

        A more complex example ordering users by the number of tweets made (greatest
        to least), then ordered by username in the event of a tie:

        .. code-block:: python

            tweet_ct = fn.Count(Tweet.id)
            sq = (User
                .select(User, tweet_ct.alias('count'))
                .join(Tweet)
                .group_by(User)
                .order_by(tweet_ct.desc(), User.username))

        Example of removing a pre-existing ``ORDER BY`` clause:

        .. code-block:: python

            # Query will be ordered by username.
            users = User.select().order_by(User.username)

            # Query will be returned in whatever order database chooses.
            unordered_users = users.order_by()


    .. py:method:: window(*windows)

        :param Window windows: One or more :py:class:`Window` instances.

        Add one or more window definitions to this query.

        .. code-block:: python

            window = Window(partition_by=[fn.date_trunc('day', PageView.timestamp)])
            query = (PageView
                     .select(
                         PageView.url,
                         PageView.timestamp,
                         fn.Count(PageView.id).over(window=window))
                     .window(window)
                     .order_by(PageView.timestamp))

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

    .. py:method:: distinct([is_distinct=True])

        :param is_distinct: See notes.
        :rtype: :py:class:`SelectQuery`

        Indicates that this query should only return distinct rows. Results in a
        ``SELECT DISTINCT`` query.

        .. note::
            The value for ``is_distinct`` should either be a boolean, in which
            case the query will (or won't) be `DISTINCT`.

            You can specify a list of one or more expressions to generate a
            ``DISTINCT ON`` query, e.g. ``.distinct([Model.col1, Model.col2])``.

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

    .. py:method:: aggregate_rows()

        :rtype: :py:class:`SelectQuery`

        This method provides one way to avoid the **N+1** query problem.

        Consider a webpage where you wish to display a list of users and all of their
        associated tweets. You could approach this problem by listing the users, then
        for each user executing a separate query to retrieve their tweets. This is the
        **N+1** behavior, because the number of queries varies depending on the number
        of users. Conventional wisdom is that it is preferable to execute fewer queries.
        Peewee provides several ways to avoid this problem.

        You can use the :py:func:`prefetch` helper, which uses ``IN`` clauses to retrieve
        the tweets for the listed users.

        Another method is to select both the user and the tweet data in a single query,
        then de-dupe the users, aggregating the tweets in the process.

        The raw column data might appear like this:

        .. code-block:: python

            # user.id, user.username, tweet.id, tweet.user_id, tweet.message
            [1,        'charlie',     1,        1,             'hello'],
            [1,        'charlie',     2,        1,             'goodbye'],
            [2,        'no-tweets',   NULL,     NULL,          NULL],
            [3,        'huey',        3,        3,             'meow'],
            [3,        'huey',        4,        3,             'purr'],
            [3,        'huey',        5,        3,             'hiss'],

        We can infer from the ``JOIN`` clause that the user data will be duplicated, and
        therefore by de-duping the users, we can collect their tweets in one go and iterate
        over the users and tweets transparently.

        .. code-block:: python

            query = (User
                     .select(User, Tweet)
                     .join(Tweet, JOIN.LEFT_OUTER)
                     .order_by(User.username, Tweet.id)
                     .aggregate_rows())  # .aggregate_rows() tells peewee to de-dupe the rows.
            for user in query:
                print user.username
                for tweet in user.tweets:
                    print '  ', tweet.message

            # Producing the following output:
            charlie
               hello
               goodbye
            huey
               meow
               purr
               hiss
            no-tweets

        .. warning::
            Be sure that you specify an ``ORDER BY`` clause that ensures duplicated data
            will appear in consecutive rows.

        .. note::
            You can specify arbitrarily complex joins, though for more complex queries
            it may be more efficient to use :py:func:`prefetch`. In short, try both and
            see what works best for your data-set.

        .. note:: For more information, see the :ref:`nplusone` document and the :ref:`aggregate-rows` sub-section.

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

                query = (User
                         .select()
                         .join(Tweet, JOIN.LEFT_OUTER)
                         .switch(User)  # Switch query context back to `User`.
                         .annotate(Tweet))

    .. py:method:: aggregate(aggregation)

        :param aggregation: a function specifying what aggregation to perform, for
          example ``fn.Max(Tweet.created_date)``.

        Method to look at an aggregate of rows using a given function and
        return a scalar value, such as the count of all rows or the average
        value of a particular column.

    .. py:method:: count([clear_limit=False])

        :param bool clear_limit: Remove any limit or offset clauses from the query before counting.
        :rtype: an integer representing the number of rows in the current query

        .. note::
            If the query has a GROUP BY, DISTINCT, LIMIT, or OFFSET
            clause, then the :py:meth:`~SelectQuery.wrapped_count` method
            will be used instead.

        >>> sq = SelectQuery(Tweet)
        >>> sq.count()
        45  # number of tweets
        >>> deleted_tweets = sq.where(Tweet.status == DELETED)
        >>> deleted_tweets.count()
        3  # number of tweets that are marked as deleted

    .. py:method:: wrapped_count([clear_limit=False])

        :param bool clear_limit: Remove any limit or offset clauses from the query before counting.
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
            if sq.where(User.username == username, User.active == True).exists():
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

    .. py:method:: first([n=1])

        :param int n: Return the first *n* query results after applying a limit
            of ``n`` records.
        :rtype: :py:class:`Model` instance, list or ``None`` if no results

        Fetch the first *n* rows from a query. Behind-the-scenes, a ``LIMIT n``
        is applied. The results of the query are then cached on the query
        result wrapper so subsequent calls to :py:meth:`~SelectQuery.first`
        will not cause multiple queries.

        If only one row is requested (default behavior), then the return-type
        will be either a model instance or ``None``.

        If multiple rows are requested, the return type will either be a list
        of one to n model instances, or ``None`` if no results are found.

    .. py:method:: peek([n=1])

        :param int n: Return the first *n* query results.
        :rtype: :py:class:`Model` instance, list or ``None`` if no results

        Fetch the first *n* rows from a query. No ``LIMIT`` is applied to the
        query, so the :py:meth:`~SelectQuery.peek` has slightly different
        semantics from :py:meth:`~SelectQuery.first`, which ensures no more
        than *n* rows are requested. The ``peek`` method, on the other hand,
        retains the ability to fetch the entire result set withouth issuing
        additional queries.

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

    .. py:method:: __len__()

        Return the number of items in the result set of this query. If all you need is the count of items and do not intend to do anything with the results, call :py:meth:`~SelectQuery.count`.

        .. warning::
            The ``SELECT`` query will be executed and the result set will be loaded.
            If you want to obtain the number of results without also loading
            the query, use :py:meth:`~SelectQuery.count`.

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

        Create a ``UNION`` query with the right-hand object. The result will contain all values from both the left and right queries.

        .. code-block:: python

            customers = Customer.select(Customer.city).where(Customer.state == 'KS')
            stores = Store.select(Store.city).where(Store.state == 'KS')

            # Get all cities in kansas where we have either a customer or a store.
            all_cities = (customers | stores).order_by(SQL('city'))

        .. note::
            SQLite does not allow ``ORDER BY`` or ``LIMIT`` clauses on the components of a compound query, however SQLite does allow these clauses on the final, compound result. This applies to ``UNION (ALL)``, ``INTERSECT``, and ``EXCEPT``.

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

    .. py:method:: returning(*returning)

        :param returning: A list of model classes, field instances, functions
          or expressions. If no argument is provided, all columns for the given model
          will be selected. To clear any existing values, pass in ``None``.
        :rtype: a :py:class:`UpdateQuery` for the given :py:class:`Model`.

        Add a ``RETURNING`` clause to the query, which will cause the ``UPDATE`` to compute return values based on each row that was actually updated.

        When the query is executed, rather than returning the number of rows updated, an iterator will be returned that yields the updated objects.

        .. note:: Currently only :py:class:`PostgresqlDatabase` supports this feature.

        Example:

        .. code-block:: python

            # Disable all users whose registration expired, and return the user
            # objects that were updated.
            query = (User
                     .update(active=False)
                     .where(User.registration_expired == True)
                     .returning(User))

            # We can iterate over the users that were updated.
            for updated_user in query.execute():
                send_activation_email(updated_user.email)

        For more information, check out :ref:`the RETURNING clause docs <returning-clause>`.

    .. py:method:: tuples()

        :rtype: :py:class:`UpdateQuery`

        .. note:: This method should only be used in conjunction with a call to :py:meth:`~UpdateQuery.returning`.

        When the updated results are returned, they will be returned as row tuples.

    .. py:method:: dicts()

        :rtype: :py:class:`UpdateQuery`

        .. note:: This method should only be used in conjunction with a call to :py:meth:`~UpdateQuery.returning`.

        When the updated results are returned, they will be returned as dictionaries mapping column to value.

    .. py:method:: on_conflict([action=None])

        Add a SQL ``ON CONFLICT`` clause with the specified action to the given ``UPDATE`` query. `Valid actions <https://www.sqlite.org/lang_conflict.html>`_ are:

        * ROLLBACK
        * ABORT
        * FAIL
        * IGNORE
        * REPLACE

        Specifying ``None`` for the action will execute a normal ``UPDATE`` query.

        .. note:: This feature is only available on SQLite databases.


.. py:class:: InsertQuery(model_class[, field_dict=None[, rows=None[, fields=None[, query=None[, validate_fields=False]]]]])

    Creates an ``InsertQuery`` instance for the given model.

    :param dict field_dict: A mapping of either field or field-name to value.
    :param iterable rows: An iterable of dictionaries containing a mapping of
        field or field-name to value.
    :param list fields: A list of field objects to insert data into (only used in combination with the ``query`` parameter).
    :param query: A :py:class:`SelectQuery` to use as the source of data.
    :param bool validate_fields: Check that every column referenced in the insert query has a corresponding field on the model. If validation is enabled and then fails, a ``KeyError`` is raised.

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

    Example inserting using a query as the data source:

    .. code-block:: python

        query = (User
                 .select(User.username, fn.COUNT(Tweet.id))
                 .join(Tweet, JOIN.LEFT_OUTER)
                 .group_by(User.username))
        iq = InsertQuery(
            UserTweetDenorm,
            fields=[UserTweetDenorm.username, UserTweetDenorm.num_tweets],
            query=query)
        iq.execute()

    .. py:method:: execute()

        :rtype: primary key of the new row

        Performs the query

    .. py:method:: upsert([upsert=True])

        Perform an *INSERT OR REPLACE* query with SQLite. MySQL databases will issue a *REPLACE* query. Currently this feature is not supported for Postgres databases, but the 9.5 syntax will be added soon.

        .. note:: This feature is only available on SQLite and MySQL databases.

    .. py:method:: on_conflict([action=None])

        Add a SQL ``ON CONFLICT`` clause with the specified action to the given ``INSERT`` query. Specifying ``REPLACE`` is equivalent to using the :py:meth:`~InsertQuery.upsert` method. `Valid actions <https://www.sqlite.org/lang_conflict.html>`_ are:

        * ROLLBACK
        * ABORT
        * FAIL
        * IGNORE
        * REPLACE

        Specifying ``None`` for the action will execute a normal ``INSERT`` query.

        .. note:: This feature is only available on SQLite databases.

    .. py:method:: return_id_list([return_id_list=True])

        By default, when doing bulk INSERTs, peewee will not return the list of generated primary keys. However, if the database supports returning primary keys via ``INSERT ... RETURNING``, this method instructs peewee to return the generated list of IDs.

        .. note::
            Currently only PostgreSQL supports this behavior. While other databases support bulk inserts, they will simply return ``True`` instead.

        Example:

        .. code-block:: python

            usernames = [
                {'username': username}
                for username in ['charlie', 'huey', 'mickey']]
            query = User.insert_many(usernames).return_id_list()
            user_ids = query.execute()
            print user_ids
            # prints something like [1, 2, 3]

    .. py:method:: returning(*returning)

        :param returning: A list of model classes, field instances, functions
          or expressions. If no argument is provided, all columns for the given model
          will be selected. To clear any existing values, pass in ``None``.
        :rtype: a :py:class:`InsertQuery` for the given :py:class:`Model`.

        Add a ``RETURNING`` clause to the query, which will cause the ``INSERT`` to compute return values based on each row that was inserted.

        When the query is executed, rather than returning the primary key of the new row(s), an iterator will be returned that yields the inserted objects.

        .. note:: Currently only :py:class:`PostgresqlDatabase` supports this feature.

        Example:

        .. code-block:: python

            # Create some users, retrieving the list of IDs assigned to them.
            query = (User
                     .insert_many(list_of_user_data)
                     .returning(User))

            # We can iterate over the users that were created.
            for new_user in query.execute():
                # Do something with the new user's ID...
                do_something(new_user.id)

        For more information, check out :ref:`the RETURNING clause docs <returning-clause>`.

    .. py:method:: tuples()

        :rtype: :py:class:`InsertQuery`

        .. note:: This method should only be used in conjunction with a call to :py:meth:`~InsertQuery.returning`.

        When the inserted results are returned, they will be returned as row tuples.

    .. py:method:: dicts()

        :rtype: :py:class:`InsertQuery`

        .. note:: This method should only be used in conjunction with a call to :py:meth:`~InsertQuery.returning`.

        When the inserted results are returned, they will be returned as dictionaries mapping column to value.

.. py:class:: DeleteQuery(model_class)

    Creates a *DELETE* query for the given model.

    .. note::
        DeleteQuery will *not* traverse foreign keys or ensure that constraints
        are obeyed, so use it with care.

    Example deleting users whose account is inactive:

    .. code-block:: python

        dq = DeleteQuery(User).where(User.active == False)

    .. py:method:: execute()

        :rtype: Number of rows deleted

        Performs the query

    .. py:method:: returning(*returning)

        :param returning: A list of model classes, field instances, functions
          or expressions. If no argument is provided, all columns for the given model
          will be selected. To clear any existing values, pass in ``None``.
        :rtype: a :py:class:`DeleteQuery` for the given :py:class:`Model`.

        Add a ``RETURNING`` clause to the query, which will cause the ``DELETE`` to compute return values based on each row that was removed from the database.

        When the query is executed, rather than returning the number of rows deleted, an iterator will be returned that yields the deleted objects.

        .. note:: Currently only :py:class:`PostgresqlDatabase` supports this feature.

        Example:

        .. code-block:: python

            # Create some users, retrieving the list of IDs assigned to them.
            query = (User
                     .delete()
                     .where(User.account_expired == True)
                     .returning(User))

            # We can iterate over the user objects that were deleted.
            for deleted_user in query.execute():
                # Do something with the deleted user.
                notify_account_deleted(deleted_user.email)

        For more information, check out :ref:`the RETURNING clause docs <returning-clause>`.

    .. py:method:: tuples()

        :rtype: :py:class:`DeleteQuery`

        .. note:: This method should only be used in conjunction with a call to :py:meth:`~DeleteQuery.returning`.

        When the deleted results are returned, they will be returned as row tuples.

    .. py:method:: dicts()

        :rtype: :py:class:`DeleteQuery`

        .. note:: This method should only be used in conjunction with a call to :py:meth:`~DeleteQuery.returning`.

        When the deleted results are returned, they will be returned as dictionaries mapping column to value.


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
        can also pass models, but they will be converted into SelectQueries. If you wish to specify
        a particular model to join against, you can pass a 2-tuple of ``(query_or_model, join_model)``.

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

    .. note:: For more information, see the :ref:`nplusone` document and the :ref:`prefetch` sub-section.

    .. warning::
        :py:func:`prefetch` can use up lots of RAM when the result set is large,
        and will not warn you if you are doing something dangerous, so it is up
        to you to know when to use it.  Additionally, because of the semantics of
        subquerying, there may be some cases when prefetch does not act as you
        expect (for instance, when applying a ``LIMIT`` to subqueries, but there
        may be others) -- please report anything you think is a bug to `github <https://github.com/coleifer/peewee/issues>`_.


Database and its subclasses
---------------------------

.. py:class:: Database(database[, threadlocals=True[, autocommit=True[, fields=None[, ops=None[, autorollback=False[, use_speedups=True[, **connect_kwargs]]]]]]])

    :param database: the name of the database (or filename if using sqlite)
    :param bool threadlocals: whether to store connections in a threadlocal
    :param bool autocommit: automatically commit every query executed by calling :py:meth:`~Database.execute`
    :param dict fields: a mapping of :py:attr:`~Field.db_field` to database column type, e.g. 'string' => 'varchar'
    :param dict ops: a mapping of operations understood by the querycompiler to expressions
    :param bool autorollback: automatically rollback when an exception occurs while executing a query.
    :param bool use_speedups: use the Cython speedups module to improve performance of some queries.
    :param connect_kwargs: any arbitrary parameters to pass to the database driver when connecting

    The ``connect_kwargs`` dictionary is used for vendor-specific parameters that will be passed back directly to your database driver, allowing you to specify the ``user``, ``host`` and ``password``, for instance. For more information and examples, see the :ref:`vendor-specific parameters document <vendor-specific-parameters>`.

    .. note::
        If your database name is not known when the class is declared, you can pass
        ``None`` in as the database name which will mark the database as "deferred"
        and any attempt to connect while in this state will raise an exception.  To
        initialize your database, call the :py:meth:`Database.init` method with
        the database name.

        For an in-depth discussion of run-time database configuration, see the :ref:`deferring_initialization` section.

    A high-level API for working with the supported database engines. The database class:

    * Manages the underlying database connection.
    * Executes queries.
    * Manage transactions and savepoints.
    * Create and drop tables and indexes.
    * Introspect the database.

    .. py:attribute:: commit_select = False

        Whether to issue a commit after executing a select query.  With some engines
        can prevent implicit transactions from piling up.

    .. py:attribute:: compiler_class = QueryCompiler

        A class suitable for compiling queries

    .. py:attribute:: compound_operations = ['UNION', 'INTERSECT', 'EXCEPT']

        Supported compound query operations.

    .. py:attribute:: compound_select_parentheses = False

        Whether ``UNION`` (or other compound ``SELECT`` queries) allow parentheses around the queries.

    .. py:attribute:: distinct_on = False

        Whether the database supports ``DISTINCT ON`` statements.

    .. py:attribute:: drop_cascade = False

        Whether the database supports cascading drop table queries.

    .. py:attribute:: field_overrides = {}

        A mapping of field types to database column types, e.g. ``{'primary_key': 'SERIAL'}``

    .. py:attribute:: foreign_keys = True

        Whether the given backend enforces foreign key constraints.

    .. py:attribute:: for_update = False

        Whether the given backend supports selecting rows for update

    .. py:attribute:: for_update_nowait = False

        Whether the given backend supports selecting rows for update

    .. py:attribute:: insert_many = True

        Whether the database supports multiple ``VALUES`` clauses for ``INSERT`` queries.

    .. py:attribute:: insert_returning = False

        Whether the database supports returning the primary key for newly inserted rows.

    .. py:attribute:: interpolation = '?'

        The string used by the driver to interpolate query parameters

    .. py:attribute:: op_overrides = {}

        A mapping of operation codes to string operations, e.g. ``{OP.LIKE: 'LIKE BINARY'}``

    .. py:attribute:: quote_char = '"'

        The string used by the driver to quote names

    .. py:attribute:: reserved_tables = []

        Table names that are reserved by the backend -- if encountered in the
        application a warning will be issued.

    .. py:attribute:: returning_clause = False

        Whether the database supports ``RETURNING`` clauses for ``UPDATE``, ``INSERT`` and ``DELETE`` queries.

        .. note:: Currently only :py:class:`PostgresqlDatabase` supports this.

        See the following for more information:

        * :py:meth:`UpdateQuery.returning`
        * :py:meth:`InsertQuery.returning`
        * :py:meth:`DeleteQuery.returning`

    .. py:attribute:: savepoints = True

        Whether the given backend supports savepoints.

    .. py:attribute:: sequences = False

        Whether the given backend supports sequences

    .. py:attribute:: subquery_delete_same_table = True

        Whether the given backend supports deleting rows using a subquery
        that selects from the same table

    .. py:attribute:: window_functions = False

        Whether the given backend supports window functions.

    .. py:method:: init(database[, **connect_kwargs])

        This method is used to initialize a deferred database. For details on configuring your database at run-time, see the :ref:`deferring_initialization` section.

        :param database: the name of the database (or filename if using sqlite)
        :param connect_kwargs: any arbitrary parameters to pass to the database driver when connecting

    .. py:method:: connect()

        Establishes a connection to the database

        .. note::
            By default, connections will be stored on a threadlocal, ensuring connections are not shared across threads. To disable this behavior, initialize the database with ``threadlocals=False``.

    .. py:method:: close()

        Closes the connection to the database (if one is open)

        .. note::
            If you initialized with ``threadlocals=True``, only a connection local
            to the calling thread will be closed.

    .. py:method:: initialize_connection(conn)

        Perform additional intialization on a newly-opened connection. For example, if you are using SQLite you may want to enable foreign key constraint enforcement (off by default).

        Here is how you might use this hook to load a SQLite extension:

        .. code-block:: python

            class CustomSqliteDatabase(SqliteDatabase):
                def initialize_connection(self, conn):
                    conn.load_extension('fts5')

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

    .. py:method:: execute(clause)

        :param Node clause: a :py:class:`Node` instance or subclass (e.g. a :py:class:`SelectQuery`).

        The clause will be compiled into SQL then sent to the :py:meth:`~Database.execute_sql` method.

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

        Call ``commit()`` on the active connection, committing the current transaction.

    .. py:method:: rollback()

        Call ``rollback()`` on the active connection, rolling back the current transaction.

    .. py:method:: set_autocommit(autocommit)

        :param autocommit: a boolean value indicating whether to turn on/off autocommit.

    .. py:method:: get_autocommit()

        :rtype: a boolean value indicating whether autocommit is enabled.

    .. py:method:: get_tables([schema=None])

        :rtype: a list of table names in the database.

    .. py:method:: get_indexes(table, [schema=None])

        :rtype: a list of :py:class:`IndexMetadata` instances, representing the indexes for the given table.

    .. py:method:: get_columns(table, [schema=None])

        :rtype: a list of :py:class:`ColumnMetadata` instances, representing the columns for the given table.

    .. py:method:: get_primary_keys(table, [schema=None])

        :rtype: a list containing the primary key column name(s) for the given table.

    .. py:method:: get_foreign_keys(table, [schema=None])

        :rtype: a list of :py:class:`ForeignKeyMetadata` instances, representing the foreign keys for the given table.

    .. py:method:: sequence_exists(sequence_name)

        :rtype boolean:

    .. py:method:: create_table(model_class[, safe=True])

        :param model_class: :py:class:`Model` class.
        :param bool safe: If `True`, the table will not be created if it already exists.

        .. warning::
            Unlike :py:meth:`Model.create_table`, this method does not create indexes or constraints. This method will only create the table itself. If you wish to create the table along with any indexes and constraints, use either :py:meth:`Model.create_table` or :py:meth:`Database.create_tables`.

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

            DeferredPost = DeferredRelation()

            class User(Model):
                username = CharField()
                favorite_post = ForeignKeyField(DeferredPost, null=True)

            class Post(Model):
                title = CharField()
                author = ForeignKeyField(User, related_name='posts')

            DeferredPost.set_model(Post)

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

    .. py:method:: create_tables(models[, safe=False])

        :param list models: A list of models.
        :param bool safe: Check first whether the table exists before attempting to create it.

        This method should be used for creating tables as it will resolve the model dependency graph and ensure the tables are created in the correct order. This method will also create any indexes and constraints defined on the models.

        Usage:

        .. code-block:: python

            db.create_tables([User, Tweet, Something], safe=True)

    .. py:method:: drop_tables(models[, safe=False[, cascade=False]])

        :param list models: A list of models.
        :param bool safe: Check the table exists before attempting to drop it.
        :param bool cascade: drop table with ``CASCADE`` option.

        This method should be used for dropping tables, as it will resolve the model dependency graph and ensure the tables are dropped in the correct order.

        Usage:

        .. code-block:: python

            db.drop_tables([User, Tweet, Something], safe=True)

    .. py:method:: atomic()

        Execute statements in either a transaction or a savepoint. The outer-most call to *atomic* will use a transaction,
        and any subsequent nested calls will use savepoints.

        ``atomic`` can be used as either a context manager or a decorator.

        .. note::
            For most use-cases, it makes the most sense to always use :py:meth:`~Database.atomic` when you wish to execute queries in a transaction. The benefit of using ``atomic`` is that you do not need to manually keep track of the transaction stack depth, as this will be managed for you.

        Context manager example code:

        .. code-block:: python

            with db.atomic() as txn:
                perform_some_operations()

                with db.atomic() as nested_txn:
                    do_other_things()
                    if something_bad_happened():
                        # Roll back these changes, but preserve the changes
                        # made in the outer block.
                        nested_txn.rollback()

        Decorator example code:

        .. code-block:: python

            @db.atomic()
            def create_user(username):
                # This function will execute in a transaction/savepoint.
                return User.create(username=username)

    .. py:method:: transaction()

        Execute statements in a transaction using either a context manager or decorator. If an
        error is raised inside the wrapped block, the transaction will be rolled
        back, otherwise statements are committed when exiting. Transactions can also be explicitly rolled back or committed within the transaction block by calling :py:meth:`~transaction.rollback` or :py:meth:`~transaction.commit`. If you manually commit or roll back, a new transaction will be started automatically.

        Nested blocks can be wrapped with ``transaction`` - the database
        will keep a stack and only commit when it reaches the end of the outermost
        function / block.

        Context manager example code:

        .. code-block:: python

            # delete a blog instance and all its associated entries, but
            # do so within a transaction
            with database.transaction():
                blog.delete_instance(recursive=True)


            # Explicitly roll back a transaction.
            with database.transaction() as txn:
                do_some_stuff()
                if something_bad_happened():
                    # Roll back any changes made within this block.
                    txn.rollback()

        Decorator example code:

        .. code-block:: python

            @database.transaction()
            def transfer_money(from_acct, to_acct, amt):
                from_acct.charge(amt)
                to_acct.pay(amt)
                return amt

    .. py:method:: commit_on_success(func)

        .. note:: Use :py:meth:`~Database.atomic` or :py:meth:`~Database.transaction` instead.

    .. py:method:: savepoint([sid=None])

        Execute statements in a savepoint using either a context manager or decorator.  If an
        error is raised inside the wrapped block, the savepoint will be rolled
        back, otherwise statements are committed when exiting. Like :py:meth:`~Database.transaction`, a savepoint can also be explicitly rolled-back or committed by calling :py:meth:`~savepoint.rollback` or :py:meth:`~savepoint.commit`. If you manually commit or roll back, a new savepoint **will not** be created.

        Savepoints can be thought of as nested transactions.

        :param str sid: An optional string identifier for the savepoint.

        Context manager example code:

        .. code-block:: python

            with db.transaction() as txn:
                do_some_stuff()
                with db.savepoint() as sp1:
                    do_more_things()

                with db.savepoint() as sp2:
                    even_more()
                    # Oops, something bad happened, roll back
                    # just the changes made in this block.
                    if something_bad_happened():
                        sp2.rollback()

    .. py:method:: execution_context([with_transaction=True])

        Create an :py:class:`ExecutionContext` context manager or decorator. Blocks wrapped with an *ExecutionContext* will run using their own connection. By default, the wrapped block will also run in a transaction, although this can be disabled specifyin ``with_transaction=False``.

        For more explanation of :py:class:`ExecutionContext`, see the :ref:`advanced_connection_management` section.

        .. warning:: ExecutionContext is very new and has not been tested extensively.

    .. py:classmethod:: register_fields(fields)

        Register a mapping of field overrides for the database class.  Used
        to register custom fields or override the defaults.

        :param dict fields: A mapping of :py:attr:`~Field.db_field` to column type

    .. py:classmethod:: register_ops(ops)

        Register a mapping of operations understood by the QueryCompiler to their
        SQL equivalent, e.g. ``{OP.EQ: '='}``.  Used to extend the types of field
        comparisons.

        :param dict fields: A mapping of :py:attr:`~Field.db_field` to column type

    .. py:method:: extract_date(date_part, date_field)

        Return an expression suitable for extracting a date part from a date
        field.  For instance, extract the year from a :py:class:`DateTimeField`.

        :param str date_part: The date part attribute to retrieve.  Valid options
          are: "year", "month", "day", "hour", "minute" and "second".
        :param Field date_field: field instance storing a datetime, date or time.
        :rtype: an expression object.

    .. py:method:: truncate_date(date_part, date_field)

        Return an expression suitable for truncating a date / datetime to the given resolution. This can be used, for example, to group a collection of timestamps by day.

        :param str date_part: The date part to truncate to. Valid options are: "year", "month", "day", "hour", "minute" and "second".
        :param Field date_field: field instance storing a datetime, date or time.
        :rtype: an expression object.

        Example:

        .. code-block:: python

            # Get tweets from today.
            tweets = Tweet.select().where(
                db.truncate_date('day', Tweet.timestamp) == datetime.date.today())


.. py:class:: SqliteDatabase(Database)

    :py:class:`Database` subclass that works with the ``sqlite3`` driver (or ``pysqlite2``). In addition to the default database parameters, :py:class:`SqliteDatabase` also accepts a *journal_mode* parameter which will configure the journaling mode.

    .. note:: If you have both ``sqlite3`` and ``pysqlite2`` installed on your system, peewee will use whichever points at a newer version of SQLite.

    .. note:: SQLite is unique among the databases supported by Peewee in that it allows a high degree of customization by the host application. This means you can do things like write custom functions or aggregates *in Python* and then call them from your SQL queries. This feature, and many more, are available through the :py:class:`SqliteExtDatabase`, part of ``playhouse.sqlite_ext``. I *strongly* recommend you use :py:class:`SqliteExtDatabase` as it exposes many of the features that make SQLite so powerful.

    Custom parameters:

    :param str journal_mode: Journaling mode.
    :param list pragmas: List of 2-tuples containing ``PRAGMA`` statements to run against new connections.

    SQLite allows run-time configuration of a number of parameters through ``PRAGMA`` statements (`documentation <https://www.sqlite.org/pragma.html>`_). These statements are typically run against a new database connection. To run one or more ``PRAGMA`` statements against new connections, you can specify them as a list of 2-tuples containing the pragma name and value:

    .. code-block:: python

        db = SqliteDatabase('my_app.db', pragmas=(
            ('journal_mode', 'WAL'),
            ('cache_size', 10000),
            ('mmap_size', 1024 * 1024 * 32),
        ))

    .. py:attribute:: insert_many = True *if* using SQLite 3.7.11.0 or newer.


.. py:class:: MySQLDatabase(Database)

    :py:class:`Database` subclass that works with either "MySQLdb" or "pymysql".

    .. py:attribute:: commit_select = True

    .. py:attribute:: compound_operations = ['UNION']

    .. py:attribute:: for_update = True

    .. py:attribute:: subquery_delete_same_table = False

.. py:class:: PostgresqlDatabase(Database)

    :py:class:`Database` subclass that works with the "psycopg2" driver

    .. py:attribute:: commit_select = True

    .. py:attribute:: compound_select_parentheses = True

    .. py:attribute:: distinct_on = True

    .. py:attribute:: for_update = True

    .. py:attribute:: for_update_nowait = True

    .. py:attribute:: insert_returning = True

    .. py:attribute:: returning_clause = True

    .. py:attribute:: sequences = True

    .. py:attribute:: window_functions = True

    .. py:attribute:: register_unicode = True

        Control whether the ``UNICODE`` and ``UNICODEARRAY`` psycopg2 extensions are loaded automatically.

Transaction, Savepoint and ExecutionContext
-------------------------------------------

The easiest way to create transactions and savepoints is to use :py:meth:`Database.atomic`. The :py:meth:`~Database.atomic` method will create a transaction or savepoint depending on the level of nesting.

.. code-block:: python

    with db.atomic() as txn:
        # The outer-most call will be a transaction.
        with db.atomic() as sp:
            # Nested calls will be savepoints instead.
            execute_some_statements()

.. py:class:: transaction(database)

    Context manager that encapsulates a database transaction. Statements executed within the wrapped block will be committed at the end of the block unless an exception occurs, in which case any changes will be rolled back.

    .. warning:: Transactions should not be nested as this could lead to unpredictable behavior in the event of an exception in a nested block. If you wish to use nested transactions, use the :py:meth:`~Database.atomic` method, which will create a transaction at the outer-most layer and use savepoints for nested blocks.

    .. note:: In practice you should not create :py:class:`transaction` objects directly, but rather use the :py:meth:`Database.transaction` method.

    .. py:method:: commit()

        Manually commit any pending changes and begin a new transaction.

    .. py:method:: rollback()

        Manually roll-back any pending changes and begin a new transaction.

.. py:class:: savepoint(database[, sid=None])

    Context manager that encapsulates a savepoint (nested transaction). Statements executed within the wrapped block will be committed at the end of the block unless an exception occurs, in which case any changes will be rolled back.

    .. warning:: Savepoints must be created within a transaction. It is recommended that you use :py:meth:`~Database.atomic` instead of manually managing the transaction+savepoint stack.

    .. note:: In practice you should not create :py:class:`savepoint` objects directly, but rather use the :py:meth:`Database.savepoint` method.

    .. py:method:: commit()

        Manually commit any pending changes. If the savepoint is manually committed and additional changes are made, they will be executed in the context of the outer block.

    .. py:method:: rollback()

        Manually roll-back any pending changes. If the savepoint is manually rolled-back and additional changes are made, they will be executed in the context of the outer block.

.. py:class:: ExecutionContext(database[, with_transaction=True])

    ExecutionContext provides a way to explicitly run statements in a dedicated connection. Typically a single database connection is maintained per-thread, but in some situations you may wish to explicitly force a new, separate connection. To accomplish this, you can create an :py:class:`ExecutionContext`. Statements executed in the wrapped block will be run in a transaction by default, though you can disable this by specifying ``with_transaction=False``.

    .. note:: Rather than instantiating ``ExecutionContext`` directly, use :py:meth:`Database.execution_context`.

    Example code:

    .. code-block:: python

        # This will return the connection associated with the current thread.
        conn = db.get_conn()

        with db.execution_context():
            # This will be a new connection object. If you are using the
            # connection pool, it may be an unused connection from the pool.
            ctx_conn = db.get_conn()

            # This statement is executed using the new `ctx_conn`.
            User.create(username='huey')

        # At the end of the wrapped block, the connection will be closed and the
        # transaction, if one exists, will be committed.

        # This statement is executed using the regular `conn`.
        User.create(username='mickey')

.. py:class:: Using(database, models[, with_transaction=True])

    For the duration of the wrapped block, all queries against the given ``models`` will use the specified ``database``. Optionally these queries can be run outside a transaction by specifying ``with_transaction=False``.

    ``Using`` provides, in short, a way to run queries on a list of models using a manually specified database.

    :param database: a :py:class:`Database` instance.
    :param models: a list of :py:class:`Model` classes to use with the given database.
    :param with_transaction: Whether the wrapped block should be run in a transaction.

Metadata Types
--------------

.. py:class:: IndexMetadata(name, sql, columns, unique, table)

    .. py:attribute:: name

        The name of the index.

    .. py:attribute:: sql

        The SQL query used to generate the index.

    .. py:attribute:: columns

        A list of columns that are covered by the index.

    .. py:attribute:: unique

        A boolean value indicating whether the index has a unique constraint.

    .. py:attribute:: table

        The name of the table containing this index.

.. py:class:: ColumnMetadata(name, data_type, null, primary_key, table)

    .. py:attribute:: name

        The name of the column.

    .. py:attribute:: data_type

        The data type of the column

    .. py:attribute:: null

        A boolean value indicating whether ``NULL`` is permitted in this column.

    .. py:attribute:: primary_key

        A boolean value indicating whether this column is a primary key.

    .. py:attribute:: table

        The name of the table containing this column.

.. py:class:: ForeignKeyMetadata(column, dest_table, dest_column, table)

    .. py:attribute:: column

        The column containing the foreign key (the "source").

    .. py:attribute:: dest_table

        The table referenced by the foreign key.

    .. py:attribute:: dest_column

        The column referenced by the foreign key (on ``dest_table``).

    .. py:attribute:: table

        The name of the table containing this foreign key.

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

    .. py:method:: over([partition_by=None[, order_by=None[, window=None]]])

        Basic support for SQL window functions.

        :param list partition_by: List of :py:class:`Node` instances to partition by.
        :param list order_by: List of :py:class:`Node` instances to use for ordering.
        :param Window window: A :py:class:`Window` instance to use for this aggregate.

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

            # Same as above but using a window class.
            window = Window(partition_by=[fn.date_trunc('day', PageView.timestamp)])
            query = (PageView
                     .select(
                         PageView.url,
                         PageView.timestamp,
                         fn.Count(PageView.id).over(window=window))
                     .window(window)  # Need to include our Window here.
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
                 .join(Tweet, JOIN.LEFT_OUTER)
                 .group_by(User))

        # Sort the users by number of tweets.
        query = query.order_by(SQL('ct DESC'))

.. py:class:: Window([partition_by=None[, order_by=None]])

    Create a ``WINDOW`` definition.

    :param list partition_by: List of :py:class:`Node` instances to partition by.
    :param list order_by: List of :py:class:`Node` instances to use for ordering.

    Examples:

    .. code-block:: python

        # Get the list of employees and the average salary for their dept.
        window = Window(partition_by=[Employee.department]).alias('dept_w')
        query = (Employee
                 .select(
                     Employee.name,
                     Employee.department,
                     Employee.salary,
                     fn.Avg(Employee.salary).over(window))
                 .window(window)
                 .order_by(Employee.name))

.. py:class:: DeferredRelation()

    Used to reference a not-yet-created model class. Stands in as a placeholder for the related model of a foreign key. Useful for circular references.

    .. code-block:: python

        DeferredPost = DeferredRelation()

        class User(Model):
            username = CharField()

            # `Post` is not available yet, it is declared below.
            favorite_post = ForeignKeyField(DeferredPost, null=True)

        class Post(Model):
            # `Post` comes after `User` since it refers to `User`.
            user = ForeignKeyField(User)
            title = CharField()

        DeferredPost.set_model(Post)  # Post is now available.

    .. py:method:: set_model(model)

        Replace the placeholder with the correct model class.

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

.. py:class:: Node()

    The :py:class:`Node` class is the parent class for all composable parts of a query, and forms the basis of peewee's expression API. The following classes extend :py:class:`Node`:

    * :py:class:`SelectQuery`, :py:class:`UpdateQuery`, :py:class:`InsertQuery`, :py:class:`DeleteQuery`, and :py:class:`RawQuery`.
    * :py:class:`Field`
    * :py:class:`Func` (and :py:func:`fn`)
    * :py:class:`SQL`
    * :py:class:`Expression`
    * :py:class:`Param`
    * :py:class:`Window`
    * :py:class:`Clause`
    * :py:class:`Entity`
    * :py:class:`Check`

    Overridden operators:

    * Bitwise and- and or- (``&`` and ``|``): combine multiple nodes using the given conjunction.
    * ``+``, ``-``, ``*``, ``/`` and ``^`` (add, subtract, multiply, divide and exclusive-or).
    * ``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``: create a binary expression using the given comparator.
    * ``<<``: create an *IN* expression.
    * ``>>``: create an *IS* expression.
    * ``%`` and ``**``: *LIKE* and *ILIKE*.

    .. py:method:: contains(rhs)

        Create a binary expression using case-insensitive string search.

    .. py:method:: startswith(rhs)

        Create a binary expression using case-insensitive prefix search.

    .. py:method:: endswith(rhs)

        Create a binary expression using case-insensitive suffix search.

    .. py:method:: between(low, high)

        Create an expression that will match values between ``low`` and ``high``.

    .. py:method:: regexp(expression)

        Match based on regular expression.

    .. py:method:: concat(rhs)

        Concatenate the current node with the provided ``rhs``.

        .. warning::
            In order for this method to work with MySQL, the MySQL session must
            be set to use ``PIPES_AS_CONCAT``.

            To reliably concatenate strings with MySQL, use
            ``fn.CONCAT(s1, s2...)`` instead.

    .. py:method:: is_null([is_null=True])

        Create an expression testing whether the ``Node`` is (or is not) ``NULL``.

        .. code-block:: python

            # Find all categories whose parent column is NULL.
            root_nodes = Category.select().where(Category.parent.is_null())

            # Find all categores whose parent is NOT NULL.
            child_nodes = Category.select().where(Category.parent.is_null(False))

        To simplify things, peewee will generate the correct SQL for equality and inequality. The :py:meth:`~Node.is_null` method is provided simply for readability.

        .. code-block:: python

            # Equivalent to the previous queries -- peewee will translate these
            # into `IS NULL` and `IS NOT NULL`:
            root_nodes = Category.select().where(Category.parent == None)
            child_nodes = Category.select().where(Category.parent != None)

    .. py:method:: __invert__()

        Negate the node. This translates roughly into *NOT (<node>)*.

    .. py:method:: alias([name=None])

        Apply an alias to the given node. This translates into *<node> AS <name>*.

    .. py:method:: asc()

        Apply ascending ordering to the given node. This translates into *<node> ASC*.

    .. py:method:: desc()

        Apply descending ordering to the given node. This translates into *<node> DESC*.

    .. py:method:: bind_to(model_class)

        Bind the results of an expression to a specific model type. Useful when adding expressions to a select, where the result of the expression should be placed on a particular joined instance.

    .. py:classmethod:: extend([name=None[, clone=False]])

        Decorator for adding the decorated function as a new method on :py:class:`Node` and its subclasses. Useful for adding implementation-specific features to all node types.

        :param str name: Method name. If not provided the name of the wrapped function will be used.
        :param bool clone: Whether this method should return a clone. This is generally true when the method mutates the internal state of the node.

        Example:

        .. code-block:: python

            # Add a `cast()` method to all nodes using the '::' operator.
            PostgresqlDatabase.register_ops({'::', '::'})

            @Node.extend()
            def cast(self, as_type):
                return Expression(self, '::', SQL(as_type))

            # Let's pretend we want to find all data points whose numbers
            # are palindromes. Note that we can use the new *cast* method
            # on both fields and with the `fn` helper:
            reverse_val = fn.REVERSE(DataModel.value.cast('str')).cast('int')

            query = (DataPoint
                     .select()
                     .where(DataPoint.value == reverse_val))

        .. note:: To remove an extended method, simply call ``delattr`` on the class the method was originally added to.
