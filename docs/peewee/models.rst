.. _models:

Models and Fields
=================

:py:class:`Model` classes, :py:class:`Field` instances and model instances all
map to database concepts:

================= =================================
Thing             Corresponds to...
================= =================================
Model class       Database table
Field instance    Column on a table
Model instance    Row in a database table
================= =================================

The following code shows the typical way you will define your database
connection and model classes.

.. _blog-models:

.. code-block:: python

    import datetime
    from peewee import *

    db = SqliteDatabase('my_app.db')

    class BaseModel(Model):
        class Meta:
            database = db

    class User(BaseModel):
        username = CharField(unique=True)

    class Tweet(BaseModel):
        user = ForeignKeyField(User, backref='tweets')
        message = TextField()
        created_date = DateTimeField(default=datetime.datetime.now)
        is_published = BooleanField(default=True)

1. Create an instance of a :py:class:`Database`.

    .. code-block:: python

        db = SqliteDatabase('my_app.db')

    The ``db`` object will be used to manage the connections to the Sqlite
    database. In this example we're using :py:class:`SqliteDatabase`, but you
    could also use one of the other :ref:`database engines <database>`.

2. Create a base model class which specifies our database.

    .. code-block:: python

        class BaseModel(Model):
            class Meta:
                database = db

    It is good practice to define a base model class which establishes the
    database connection. This makes your code DRY as you will not have to
    specify the database for subsequent models.

    Model configuration is kept namespaced in a special class called ``Meta``.
    This convention is borrowed from Django. :ref:`Meta <model-options>`
    configuration is passed on to subclasses, so our project's models will all
    subclass *BaseModel*. There are :ref:`many different attributes
    <model-options>` you can configure using *Model.Meta*.

3. Define a model class.

    .. code-block:: python

        class User(BaseModel):
            username = CharField(unique=True)

    Model definition uses the declarative style seen in other popular ORMs like
    SQLAlchemy or Django. Note that we are extending the *BaseModel* class so
    the *User* model will inherit the database connection.

    We have explicitly defined a single *username* column with a unique
    constraint. Because we have not specified a primary key, peewee will
    automatically add an auto-incrementing integer primary key field named
    *id*.

.. note::
    If you would like to start using peewee with an existing database, you can
    use :ref:`pwiz` to automatically generate model definitions.

.. _fields:

Fields
------

The :py:class:`Field` class is used to describe the mapping of
:py:class:`Model` attributes to database columns. Each field type has a
corresponding SQL storage class (i.e. varchar, int), and conversion between
python data types and underlying storage is handled transparently.

When creating a :py:class:`Model` class, fields are defined as class
attributes. This should look familiar to users of the django framework. Here's
an example:

.. code-block:: python

    class User(Model):
        username = CharField()
        join_date = DateTimeField()
        about_me = TextField()

In the above example, because none of the fields are initialized with
``primary_key=True``, an auto-incrementing primary key will automatically be
created and named "id". Peewee uses :py:class:`AutoField` to signify an
auto-incrementing integer primary key, which implies ``primary_key=True``.

There is one special type of field, :py:class:`ForeignKeyField`, which allows
you to represent foreign-key relationships between models in an intuitive way:

.. code-block:: python

    class Message(Model):
        user = ForeignKeyField(User, backref='messages')
        body = TextField()
        send_date = DateTimeField(default=datetime.datetime.now)

This allows you to write code like the following:

.. code-block:: python

    >>> print(some_message.user.username)
    Some User

    >>> for message in some_user.messages:
    ...     print(message.body)
    some message
    another message
    yet another message

.. note::
    Refer to the :ref:`relationships` document for an in-depth discussion of
    foreign-keys, joins and relationships between models.

For full documentation on fields, see the :ref:`Fields API notes <fields-api>`

.. _field_types_table:

Field types table
^^^^^^^^^^^^^^^^^

=====================   =================   =================   =================
Field Type              Sqlite              Postgresql          MySQL
=====================   =================   =================   =================
``AutoField``           integer             serial              integer
``BigAutoField``        integer             bigserial           bigint
``IntegerField``        integer             integer             integer
``BigIntegerField``     integer             bigint              bigint
``SmallIntegerField``   integer             smallint            smallint
``IdentityField``       not supported       int identity        not supported
``FloatField``          real                real                real
``DoubleField``         real                double precision    double precision
``DecimalField``        decimal             numeric             numeric
``CharField``           varchar             varchar             varchar
``FixedCharField``      char                char                char
``TextField``           text                text                text
``BlobField``           blob                bytea               blob
``BitField``            integer             bigint              bigint
``BigBitField``         blob                bytea               blob
``UUIDField``           text                uuid                varchar(40)
``BinaryUUIDField``     blob                bytea               varbinary(16)
``DateTimeField``       datetime            timestamp           datetime
``DateField``           date                date                date
``TimeField``           time                time                time
``TimestampField``      integer             integer             integer
``IPField``             integer             bigint              bigint
``BooleanField``        integer             boolean             bool
``BareField``           untyped             not supported       not supported
``ForeignKeyField``     integer             integer             integer
=====================   =================   =================   =================

.. note::
    Don't see the field you're looking for in the above table? It's easy to
    create custom field types and use them with your models.

    * :ref:`custom-fields`
    * :py:class:`Database`, particularly the ``fields`` parameter.

Field initialization arguments
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Parameters accepted by all field types and their default values:

* ``null = False`` -- allow null values
* ``index = False`` -- create an index on this column
* ``unique = False`` -- create a unique index on this column. See also :ref:`adding composite indexes <model_indexes>`.
* ``column_name = None`` -- explicitly specify the column name in the database.
* ``default = None`` -- any value or callable to use as a default for uninitialized models
* ``primary_key = False`` -- primary key for the table
* ``constraints = None`` - one or more constraints, e.g. ``[Check('price > 0')]``
* ``sequence = None`` -- sequence name (if backend supports it)
* ``collation = None`` -- collation to use for ordering the field / index
* ``unindexed = False`` -- indicate field on virtual table should be unindexed (**SQLite-only**)
* ``choices = None`` -- optional iterable containing 2-tuples of ``value``, ``display``
* ``help_text = None`` -- string representing any helpful text for this field
* ``verbose_name = None`` -- string representing the "user-friendly" name of this field
* ``index_type = None`` -- specify a custom index-type, e.g. for Postgres you might specify a ``'BRIN'`` or ``'GIN'`` index.

Some fields take special parameters...
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

+--------------------------------+------------------------------------------------+
| Field type                     | Special Parameters                             |
+================================+================================================+
| :py:class:`CharField`          | ``max_length``                                 |
+--------------------------------+------------------------------------------------+
| :py:class:`FixedCharField`     | ``max_length``                                 |
+--------------------------------+------------------------------------------------+
| :py:class:`DateTimeField`      | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`DateField`          | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`TimeField`          | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`TimestampField`     | ``resolution``, ``utc``                        |
+--------------------------------+------------------------------------------------+
| :py:class:`DecimalField`       | ``max_digits``, ``decimal_places``,            |
|                                | ``auto_round``, ``rounding``                   |
+--------------------------------+------------------------------------------------+
| :py:class:`ForeignKeyField`    | ``model``, ``field``, ``backref``,             |
|                                | ``on_delete``, ``on_update``, ``deferrable``   |
|                                | ``lazy_load``                                  |
+--------------------------------+------------------------------------------------+
| :py:class:`BareField`          | ``adapt``                                      |
+--------------------------------+------------------------------------------------+

.. note::
    Both ``default`` and ``choices`` could be implemented at the database level
    as *DEFAULT* and *CHECK CONSTRAINT* respectively, but any application
    change would require a schema change. Because of this, ``default`` is
    implemented purely in python and ``choices`` are not validated but exist
    for metadata purposes only.

    To add database (server-side) constraints, use the ``constraints``
    parameter.

Default field values
^^^^^^^^^^^^^^^^^^^^

Peewee can provide default values for fields when objects are created. For
example to have an ``IntegerField`` default to zero rather than ``NULL``, you
could declare the field with a default value:

.. code-block:: python

    class Message(Model):
        context = TextField()
        read_count = IntegerField(default=0)

In some instances it may make sense for the default value to be dynamic. A
common scenario is using the current date and time. Peewee allows you to
specify a function in these cases, whose return value will be used when the
object is created. Note we only provide the function, we do not actually *call*
it:

.. code-block:: python

    class Message(Model):
        context = TextField()
        timestamp = DateTimeField(default=datetime.datetime.now)

.. note::
    If you are using a field that accepts a mutable type (`list`, `dict`, etc),
    and would like to provide a default, it is a good idea to wrap your default
    value in a simple function so that multiple model instances are not sharing
    a reference to the same underlying object:

    .. code-block:: python

        def house_defaults():
            return {'beds': 0, 'baths': 0}

        class House(Model):
            number = TextField()
            street = TextField()
            attributes = JSONField(default=house_defaults)

The database can also provide the default value for a field. While peewee does
not explicitly provide an API for setting a server-side default value, you can
use the ``constraints`` parameter to specify the server default:

.. code-block:: python

    class Message(Model):
        context = TextField()
        timestamp = DateTimeField(constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])

.. note::
    **Remember:** when using the ``default`` parameter, the values are set by
    Peewee rather than being a part of the actual table and column definition.

ForeignKeyField
^^^^^^^^^^^^^^^

:py:class:`ForeignKeyField` is a special field type that allows one model to
reference another. Typically a foreign key will contain the primary key of the
model it relates to (but you can specify a particular column by specifying a
``field``).

Foreign keys allow data to be `normalized <http://en.wikipedia.org/wiki/Database_normalization>`_.
In our example models, there is a foreign key from ``Tweet`` to ``User``. This
means that all the users are stored in their own table, as are the tweets, and
the foreign key from tweet to user allows each tweet to *point* to a particular
user object.

.. note::
    Refer to the :ref:`relationships` document for an in-depth discussion of
    foreign keys, joins and relationships between models.

In peewee, accessing the value of a :py:class:`ForeignKeyField` will return the
entire related object, e.g.:

.. code-block:: python

    tweets = (Tweet
              .select(Tweet, User)
              .join(User)
              .order_by(Tweet.created_date.desc()))
    for tweet in tweets:
        print(tweet.user.username, tweet.message)

.. note::
    In the example above the ``User`` data was selected as part of the query.
    For more examples of this technique, see the :ref:`Avoiding N+1 <nplusone>`
    document.

If we did not select the ``User``, though, then an **additional query** would
be issued to fetch the associated ``User`` data:

.. code-block:: python

    tweets = Tweet.select().order_by(Tweet.created_date.desc())
    for tweet in tweets:
        # WARNING: an additional query will be issued for EACH tweet
        # to fetch the associated User data.
        print(tweet.user.username, tweet.message)

Sometimes you only need the associated primary key value from the foreign key
column. In this case, Peewee follows the convention established by Django, of
allowing you to access the raw foreign key value by appending ``"_id"`` to the
foreign key field's name:

.. code-block:: python

    tweets = Tweet.select()
    for tweet in tweets:
        # Instead of "tweet.user", we will just get the raw ID value stored
        # in the column.
        print(tweet.user_id, tweet.message)

To prevent accidentally resolving a foreign-key and triggering an additional
query, :py:class:`ForeignKeyField` supports an initialization paramater
``lazy_load`` which, when disabled, behaves like the ``"_id"`` attribute. For
example:

.. code-block:: python

    class Tweet(Model):
        # ... same fields, except we declare the user FK to have
        # lazy-load disabled:
        user = ForeignKeyField(User, backref='tweets', lazy_load=False)

    for tweet in Tweet.select():
        print(tweet.user, tweet.message)

    # With lazy-load disabled, accessing tweet.user will not perform an extra
    # query and the user ID value is returned instead.
    # e.g.:
    # 1  tweet from user1
    # 1  another from user1
    # 2  tweet from user2

    # However, if we eagerly load the related user object, then the user
    # foreign key will behave like usual:
    for tweet in Tweet.select(Tweet, User).join(User):
        print(tweet.user.username, tweet.message)

    # user1  tweet from user1
    # user1  another from user1
    # user2  tweet from user1

ForeignKeyField Back-references
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:py:class:`ForeignKeyField` allows for a backreferencing property to be bound
to the target model. Implicitly, this property will be named ``classname_set``,
where ``classname`` is the lowercase name of the class, but can be overridden
using the parameter ``backref``:

.. code-block:: python

    class Message(Model):
        from_user = ForeignKeyField(User, backref='outbox')
        to_user = ForeignKeyField(User, backref='inbox')
        text = TextField()

    for message in some_user.outbox:
        # We are iterating over all Messages whose from_user is some_user.
        print(message)

    for message in some_user.inbox:
        # We are iterating over all Messages whose to_user is some_user
        print(message)


DateTimeField, DateField and TimeField
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The three fields devoted to working with dates and times have special properties
which allow access to things like the year, month, hour, etc.

:py:class:`DateField` has properties for:

* ``year``
* ``month``
* ``day``

:py:class:`TimeField` has properties for:

* ``hour``
* ``minute``
* ``second``

:py:class:`DateTimeField` has all of the above.

These properties can be used just like any other expression. Let's say we have
an events calendar and want to highlight all the days in the current month that
have an event attached:

.. code-block:: python

    # Get the current time.
    now = datetime.datetime.now()

    # Get days that have events for the current month.
    Event.select(Event.event_date.day.alias('day')).where(
        (Event.event_date.year == now.year) &
        (Event.event_date.month == now.month))

.. note::
    SQLite does not have a native date type, so dates are stored in formatted
    text columns. To ensure that comparisons work correctly, the dates need to
    be formatted so they are sorted lexicographically. That is why they are
    stored, by default, as ``YYYY-MM-DD HH:MM:SS``.

BitField and BigBitField
^^^^^^^^^^^^^^^^^^^^^^^^

The :py:class:`BitField` and :py:class:`BigBitField` are new as of 3.0.0. The
former provides a subclass of :py:class:`IntegerField` that is suitable for
storing feature toggles as an integer bitmask. The latter is suitable for
storing a bitmap for a large data-set, e.g. expressing membership or
bitmap-type data.

As an example of using :py:class:`BitField`, let's say we have a *Post* model
and we wish to store certain True/False flags about how the post. We could
store all these feature toggles in their own :py:class:`BooleanField` objects,
or we could use :py:class:`BitField` instead:

.. code-block:: python

    class Post(Model):
        content = TextField()
        flags = BitField()

        is_favorite = flags.flag(1)
        is_sticky = flags.flag(2)
        is_minimized = flags.flag(4)
        is_deleted = flags.flag(8)

Using these flags is quite simple:

.. code-block:: pycon

    >>> p = Post()
    >>> p.is_sticky = True
    >>> p.is_minimized = True
    >>> print(p.flags)  # Prints 4 | 2 --> "6"
    6
    >>> p.is_favorite
    False
    >>> p.is_sticky
    True

We can also use the flags on the Post class to build expressions in queries:

.. code-block:: python

    # Generates a WHERE clause that looks like:
    # WHERE (post.flags & 1 != 0)
    favorites = Post.select().where(Post.is_favorite)

    # Query for sticky + favorite posts:
    sticky_faves = Post.select().where(Post.is_sticky & Post.is_favorite)

Since the :py:class:`BitField` is stored in an integer, there is a maximum of
64 flags you can represent (64-bits is common size of integer column). For
storing arbitrarily large bitmaps, you can instead use :py:class:`BigBitField`,
which uses an automatically managed buffer of bytes, stored in a
:py:class:`BlobField`.

When bulk-updating one or more bits in a :py:class:`BitField`, you can use
bitwise operators to set or clear one or more bits:

.. code-block:: python

    # Set the 4th bit on all Post objects.
    Post.update(flags=Post.flags | 8).execute()

    # Clear the 1st and 3rd bits on all Post objects.
    Post.update(flags=Post.flags & ~(1 | 4)).execute()

For simple operations, the flags provide handy ``set()`` and ``clear()``
methods for setting or clearing an individual bit:

.. code-block:: python

    # Set the "is_deleted" bit on all posts.
    Post.update(flags=Post.is_deleted.set()).execute()

    # Clear the "is_deleted" bit on all posts.
    Post.update(flags=Post.is_deleted.clear()).execute()

Example usage:

.. code-block:: python

    class Bitmap(Model):
        data = BigBitField()

    bitmap = Bitmap()

    # Sets the ith bit, e.g. the 1st bit, the 11th bit, the 63rd, etc.
    bits_to_set = (1, 11, 63, 31, 55, 48, 100, 99)
    for bit_idx in bits_to_set:
        bitmap.data.set_bit(bit_idx)

    # We can test whether a bit is set using "is_set":
    assert bitmap.data.is_set(11)
    assert not bitmap.data.is_set(12)

    # We can clear a bit:
    bitmap.data.clear_bit(11)
    assert not bitmap.data.is_set(11)

    # We can also "toggle" a bit. Recall that the 63rd bit was set earlier.
    assert bitmap.data.toggle_bit(63) is False
    assert bitmap.data.toggle_bit(63) is True
    assert bitmap.data.is_set(63)

BareField
^^^^^^^^^

The :py:class:`BareField` class is intended to be used only with SQLite. Since
SQLite uses dynamic typing and data-types are not enforced, it can be perfectly
fine to declare fields without *any* data-type. In those cases you can use
:py:class:`BareField`. It is also common for SQLite virtual tables to use
meta-columns or untyped columns, so for those cases as well you may wish to use
an untyped field (although for full-text search, you should use
:py:class:`SearchField` instead!).

:py:class:`BareField` accepts a special parameter ``adapt``. This parameter is
a function that takes a value coming from the database and converts it into the
appropriate Python type. For instance, if you have a virtual table with an
un-typed column but you know that it will return ``int`` objects, you can
specify ``adapt=int``.

Example:

.. code-block:: python

    db = SqliteDatabase(':memory:')

    class Junk(Model):
        anything = BareField()

        class Meta:
            database = db

    # Store multiple data-types in the Junk.anything column:
    Junk.create(anything='a string')
    Junk.create(anything=12345)
    Junk.create(anything=3.14159)

.. _custom-fields:

Creating a custom field
^^^^^^^^^^^^^^^^^^^^^^^

It is easy to add support for custom field types in peewee. In this example we
will create a UUID field for postgresql (which has a native UUID column type).

To add a custom field type you need to first identify what type of column the
field data will be stored in. If you just want to add python behavior atop,
say, a decimal field (for instance to make a currency field) you would just
subclass :py:class:`DecimalField`. On the other hand, if the database offers a
custom column type you will need to let peewee know. This is controlled by the
:py:attr:`Field.field_type` attribute.

.. note::
    Peewee ships with a :py:class:`UUIDField`, the following code is intended
    only as an example.

Let's start by defining our UUID field:

.. code-block:: python

    class UUIDField(Field):
        field_type = 'uuid'

We will store the UUIDs in a native UUID column. Since psycopg2 treats the data
as a string by default, we will add two methods to the field to handle:

* The data coming out of the database to be used in our application
* The data from our python app going into the database

.. code-block:: python

    import uuid

    class UUIDField(Field):
        field_type = 'uuid'

        def db_value(self, value):
            return value.hex  # convert UUID to hex string.

        def python_value(self, value):
            return uuid.UUID(value) # convert hex string to UUID

**This step is optional.** By default, the ``field_type`` value will be used
for the columns data-type in the database schema. If you need to support
multiple databases which use different data-types for your field-data, we need
to let the database know how to map this *uuid* label to an actual *uuid*
column type in the database. Specify the overrides in the :py:class:`Database` constructor:

  .. code-block:: python

      # Postgres, we use UUID data-type.
      db = PostgresqlDatabase('my_db', field_types={'uuid': 'uuid'})

      # Sqlite doesn't have a UUID type, so we use text type.
      db = SqliteDatabase('my_db', field_types={'uuid': 'text'})

That is it! Some fields may support exotic operations, like the postgresql
HStore field acts like a key/value store and has custom operators for things
like *contains* and *update*. You can specify :ref:`custom operations
<custom-operators>` as well. For example code, check out the source code for
the :py:class:`HStoreField`, in ``playhouse.postgres_ext``.

Field-naming conflicts
^^^^^^^^^^^^^^^^^^^^^^

:py:class:`Model` classes implement a number of class- and instance-methods,
for example :py:meth:`Model.save` or :py:meth:`Model.create`. If you declare a
field whose name coincides with a model method, it could cause problems.
Consider:

.. code-block:: python

    class LogEntry(Model):
        event = TextField()
        create = TimestampField()  # Uh-oh.
        update = TimestampField()  # Uh-oh.

To avoid this problem while still using the desired column name in the database
schema, explicitly specify the ``column_name`` while providing an alternative
name for the field attribute:

.. code-block:: python

    class LogEntry(Model):
        event = TextField()
        create_ = TimestampField(column_name='create')
        update_ = TimestampField(column_name='update')


Creating model tables
---------------------

In order to start using our models, its necessary to open a connection to the
database and create the tables first. Peewee will run the necessary *CREATE
TABLE* queries, additionally creating any constraints and indexes.

.. code-block:: python

    # Connect to our database.
    db.connect()

    # Create the tables.
    db.create_tables([User, Tweet])

.. note::
    Strictly speaking, it is not necessary to call :py:meth:`~Database.connect`
    but it is good practice to be explicit. That way if something goes wrong,
    the error occurs at the connect step, rather than some arbitrary time
    later.

.. note::
    By default, Peewee includes an ``IF NOT EXISTS`` clause when creating
    tables. If you want to disable this, specify ``safe=False``.

After you have created your tables, if you choose to modify your database
schema (by adding, removing or otherwise changing the columns) you will need to
either:

* Drop the table and re-create it.
* Run one or more *ALTER TABLE* queries. Peewee comes with a schema migration
  tool which can greatly simplify this. Check the :ref:`schema migrations <migrate>`
  docs for details.

.. _model-options:

Model options and table metadata
--------------------------------

In order not to pollute the model namespace, model-specific configuration is
placed in a special class called *Meta* (a convention borrowed from the django
framework):

.. code-block:: python

    from peewee import *

    contacts_db = SqliteDatabase('contacts.db')

    class Person(Model):
        name = CharField()

        class Meta:
            database = contacts_db

This instructs peewee that whenever a query is executed on *Person* to use the
contacts database.

.. note::
    Take a look at :ref:`the sample models <blog-models>` - you will notice
    that we created a ``BaseModel`` that defined the database, and then
    extended. This is the preferred way to define a database and create models.

Once the class is defined, you should not access ``ModelClass.Meta``, but
instead use ``ModelClass._meta``:

.. code-block:: pycon

    >>> Person.Meta
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    AttributeError: type object 'Person' has no attribute 'Meta'

    >>> Person._meta
    <peewee.ModelOptions object at 0x7f51a2f03790>

The :py:class:`ModelOptions` class implements several methods which may be of
use for retrieving model metadata (such as lists of fields, foreign key
relationships, and more).

.. code-block:: pycon

    >>> Person._meta.fields
    {'id': <peewee.AutoField object at 0x7f51a2e92750>,
     'name': <peewee.CharField object at 0x7f51a2f0a510>}

    >>> Person._meta.primary_key
    <peewee.AutoField object at 0x7f51a2e92750>

    >>> Person._meta.database
    <peewee.SqliteDatabase object at 0x7f519bff6dd0>

There are several options you can specify as ``Meta`` attributes. While most
options are inheritable, some are table-specific and will not be inherited by
subclasses.

======================  ====================================================== ====================
Option                  Meaning                                                Inheritable?
======================  ====================================================== ====================
``database``            database for model                                     yes
``table_name``          name of the table to store data                        no
``table_function``      function to generate table name dynamically            yes
``indexes``             a list of fields to index                              yes
``primary_key``         a :py:class:`CompositeKey` instance                    yes
``constraints``         a list of table constraints                            yes
``schema``              the database schema for the model                      yes
``only_save_dirty``     when calling model.save(), only save dirty fields      yes
``options``             dictionary of options for create table extensions      yes
``table_settings``      list of setting strings to go after close parentheses  yes
``temporary``           indicate temporary table                               yes
``legacy_table_names``  use legacy table name generation (enabled by default)  yes
``depends_on``          indicate this table depends on another for creation    no
``without_rowid``       indicate table should not have rowid (SQLite only)     no
======================  ====================================================== ====================

Here is an example showing inheritable versus non-inheritable attributes:

.. code-block:: pycon

    >>> db = SqliteDatabase(':memory:')
    >>> class ModelOne(Model):
    ...     class Meta:
    ...         database = db
    ...         table_name = 'model_one_tbl'
    ...
    >>> class ModelTwo(ModelOne):
    ...     pass
    ...
    >>> ModelOne._meta.database is ModelTwo._meta.database
    True
    >>> ModelOne._meta.table_name == ModelTwo._meta.table_name
    False

Meta.primary_key
^^^^^^^^^^^^^^^^

The ``Meta.primary_key`` attribute is used to specify either a
:py:class:`CompositeKey` or to indicate that the model has *no* primary key.
Composite primary keys are discussed in more detail here: :ref:`composite-key`.

To indicate that a model should not have a primary key, then set ``primary_key = False``.

Examples:

.. code-block:: python

    class BlogToTag(Model):
        """A simple "through" table for many-to-many relationship."""
        blog = ForeignKeyField(Blog)
        tag = ForeignKeyField(Tag)

        class Meta:
            primary_key = CompositeKey('blog', 'tag')

    class NoPrimaryKey(Model):
        data = IntegerField()

        class Meta:
            primary_key = False

.. _table_names:

Table Names
^^^^^^^^^^^

By default Peewee will automatically generate a table name based on the name of
your model class. The way the table-name is generated depends on the value of
``Meta.legacy_table_names``. By default, ``legacy_table_names=True`` so as to
avoid breaking backwards-compatibility. However, if you wish to use the new and
improved table-name generation, you can specify ``legacy_table_names=False``.

This table shows the differences in how a model name is converted to a SQL
table name, depending on the value of ``legacy_table_names``:

=================== ========================= ==============================
Model name          legacy_table_names=True   legacy_table_names=False (new)
=================== ========================= ==============================
User                user                      user
UserProfile         userprofile               user_profile
APIResponse         apiresponse               api_response
WebHTTPRequest      webhttprequest            web_http_request
mixedCamelCase      mixedcamelcase            mixed_camel_case
Name2Numbers3XYZ    name2numbers3xyz          name2_numbers3_xyz
=================== ========================= ==============================

.. attention::
    To preserve backwards-compatibility, the current release (Peewee 3.x)
    specifies ``legacy_table_names=True`` by default.

    In the next major release (Peewee 4.0), ``legacy_table_names`` will have a
    default value of ``False``.

To explicitly specify the table name for a model class, use the ``table_name``
Meta option. This feature can be useful for dealing with pre-existing database
schemas that may have used awkward naming conventions:

.. code-block:: python

    class UserProfile(Model):
        class Meta:
            table_name = 'user_profile_tbl'

If you wish to implement your own naming convention, you can specify the
``table_function`` Meta option. This function will be called with your model
class and should return the desired table name as a string. Suppose our company
specifies that table names should be lower-cased and end with "_tbl", we can
implement this as a table function:

.. code-block:: python

    def make_table_name(model_class):
        model_name = model_class.__name__
        return model_name.lower() + '_tbl'

    class BaseModel(Model):
        class Meta:
            table_function = make_table_name

    class User(BaseModel):
        # table_name will be "user_tbl".

    class UserProfile(BaseModel):
        # table_name will be "userprofile_tbl".

.. _model_indexes:

Indexes and Constraints
-----------------------

Peewee can create indexes on single or multiple columns, optionally including a
*UNIQUE* constraint. Peewee also supports user-defined constraints on both
models and fields.

Single-column indexes and constraints
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Single column indexes are defined using field initialization parameters. The
following example adds a unique index on the *username* field, and a normal
index on the *email* field:

.. code-block:: python

    class User(Model):
        username = CharField(unique=True)
        email = CharField(index=True)

To add a user-defined constraint on a column, you can pass it in using the
``constraints`` parameter. You may wish to specify a default value as part of
the schema, or add a ``CHECK`` constraint, for example:

.. code-block:: python

    class Product(Model):
        name = CharField(unique=True)
        price = DecimalField(constraints=[Check('price < 10000')])
        created = DateTimeField(
            constraints=[SQL("DEFAULT (datetime('now'))")])

Multi-column indexes
^^^^^^^^^^^^^^^^^^^^

Multi-column indexes may be defined as *Meta* attributes using a nested tuple.
Each database index is a 2-tuple, the first part of which is a tuple of the
names of the fields, the second part a boolean indicating whether the index
should be unique.

.. code-block:: python

    class Transaction(Model):
        from_acct = CharField()
        to_acct = CharField()
        amount = DecimalField()
        date = DateTimeField()

        class Meta:
            indexes = (
                # create a unique on from/to/date
                (('from_acct', 'to_acct', 'date'), True),

                # create a non-unique on from/to
                (('from_acct', 'to_acct'), False),
            )

.. note::
    Remember to add a **trailing comma** if your tuple of indexes contains only one item:

    .. code-block:: python

        class Meta:
            indexes = (
                (('first_name', 'last_name'), True),  # Note the trailing comma!
            )

Advanced Index Creation
^^^^^^^^^^^^^^^^^^^^^^^

Peewee supports a more structured API for declaring indexes on a model using
the :py:meth:`Model.add_index` method or by directly using the
:py:class:`ModelIndex` helper class.

Examples:

.. code-block:: python

    class Article(Model):
        name = TextField()
        timestamp = TimestampField()
        status = IntegerField()
        flags = IntegerField()

    # Add an index on "name" and "timestamp" columns.
    Article.add_index(Article.name, Article.timestamp)

    # Add a partial index on name and timestamp where status = 1.
    Article.add_index(Article.name, Article.timestamp,
                      where=(Article.status == 1))

    # Create a unique index on timestamp desc, status & 4.
    idx = Article.index(
        Article.timestamp.desc(),
        Article.flags.bin_and(4),
        unique=True)
    Article.add_index(idx)

.. warning::
    SQLite does not support parameterized ``CREATE INDEX`` queries. This means
    that when using SQLite to create an index that involves an expression or
    scalar value, you will need to declare the index using the :py:class:`SQL`
    helper:

    .. code-block:: python

        # SQLite does not support parameterized CREATE INDEX queries, so
        # we declare it manually.
        Article.add_index(SQL('CREATE INDEX ...'))

    See :py:meth:`~Model.add_index` for details.

For more information, see:

* :py:meth:`Model.add_index`
* :py:meth:`Model.index`
* :py:class:`ModelIndex`
* :py:class:`Index`

Table constraints
^^^^^^^^^^^^^^^^^

Peewee allows you to add arbitrary constraints to your :py:class:`Model`, that
will be part of the table definition when the schema is created.

For instance, suppose you have a *people* table with a composite primary key of
two columns, the person's first and last name. You wish to have another table
relate to the *people* table, and to do this, you will need to define a foreign
key constraint:

.. code-block:: python

    class Person(Model):
        first = CharField()
        last = CharField()

        class Meta:
            primary_key = CompositeKey('first', 'last')

    class Pet(Model):
        owner_first = CharField()
        owner_last = CharField()
        pet_name = CharField()

        class Meta:
            constraints = [SQL('FOREIGN KEY(owner_first, owner_last) '
                               'REFERENCES person(first, last)')]

You can also implement ``CHECK`` constraints at the table level:

.. code-block:: python

    class Product(Model):
        name = CharField(unique=True)
        price = DecimalField()

        class Meta:
            constraints = [Check('price < 10000')]

.. _non_integer_primary_keys:

Primary Keys, Composite Keys and other Tricks
---------------------------------------------

The :py:class:`AutoField` is used to identify an auto-incrementing integer
primary key. If you do not specify a primary key, Peewee will automatically
create an auto-incrementing primary key named "id".

To specify an auto-incrementing ID using a different field name, you can write:

.. code-block:: python

    class Event(Model):
        event_id = AutoField()  # Event.event_id will be auto-incrementing PK.
        name = CharField()
        timestamp = DateTimeField(default=datetime.datetime.now)
        metadata = BlobField()

You can identify a different field as the primary key, in which case an "id"
column will not be created. In this example we will use a person's email
address as the primary key:

.. code-block:: python

    class Person(Model):
        email = CharField(primary_key=True)
        name = TextField()
        dob = DateField()

.. warning::
    I frequently see people write the following, expecting an auto-incrementing
    integer primary key:

    .. code-block:: python

        class MyModel(Model):
            id = IntegerField(primary_key=True)

    Peewee understands the above model declaration as a model with an integer
    primary key, but the value of that ID is determined by the application. To
    create an auto-incrementing integer primary key, you would instead write:

    .. code-block:: python

        class MyModel(Model):
            id = AutoField()  # primary_key=True is implied.

Composite primary keys can be declared using :py:class:`CompositeKey`. Note
that doing this may cause issues with :py:class:`ForeignKeyField`, as Peewee
does not support the concept of a "composite foreign-key". As such, I've found
it only advisable to use composite primary keys in a handful of situations,
such as trivial many-to-many junction tables:

.. code-block:: python

    class Image(Model):
        filename = TextField()
        mimetype = CharField()

    class Tag(Model):
        label = CharField()

    class ImageTag(Model):  # Many-to-many relationship.
        image = ForeignKeyField(Image)
        tag = ForeignKeyField(Tag)

        class Meta:
            primary_key = CompositeKey('image', 'tag')

In the extremely rare case you wish to declare a model with *no* primary key,
you can specify ``primary_key = False`` in the model ``Meta`` options.

Non-integer primary keys
^^^^^^^^^^^^^^^^^^^^^^^^

If you would like use a non-integer primary key (which I generally don't
recommend), you can specify ``primary_key=True`` when creating a field. When
you wish to create a new instance for a model using a non-autoincrementing
primary key, you need to be sure you :py:meth:`~Model.save` specifying
``force_insert=True``.

.. code-block:: python

    from peewee import *

    class UUIDModel(Model):
        id = UUIDField(primary_key=True)

Auto-incrementing IDs are, as their name says, automatically generated for you
when you insert a new row into the database. When you call
:py:meth:`~Model.save`, peewee determines whether to do an *INSERT* versus an
*UPDATE* based on the presence of a primary key value. Since, with our uuid
example, the database driver won't generate a new ID, we need to specify it
manually. When we call save() for the first time, pass in ``force_insert = True``:

.. code-block:: python

    # This works because .create() will specify `force_insert=True`.
    obj1 = UUIDModel.create(id=uuid.uuid4())

    # This will not work, however. Peewee will attempt to do an update:
    obj2 = UUIDModel(id=uuid.uuid4())
    obj2.save() # WRONG

    obj2.save(force_insert=True) # CORRECT

    # Once the object has been created, you can call save() normally.
    obj2.save()

.. note::
    Any foreign keys to a model with a non-integer primary key will have a
    ``ForeignKeyField`` use the same underlying storage type as the primary key
    they are related to.

.. _composite-key:

Composite primary keys
^^^^^^^^^^^^^^^^^^^^^^

Peewee has very basic support for composite keys.  In order to use a composite
key, you must set the ``primary_key`` attribute of the model options to a
:py:class:`CompositeKey` instance:

.. code-block:: python

    class BlogToTag(Model):
        """A simple "through" table for many-to-many relationship."""
        blog = ForeignKeyField(Blog)
        tag = ForeignKeyField(Tag)

        class Meta:
            primary_key = CompositeKey('blog', 'tag')

.. warning::
    Peewee does not support foreign-keys to models that define a
    :py:class:`CompositeKey` primary key. If you wish to add a foreign-key to a
    model that has a composite primary key, replicate the columns on the
    related model and add a custom accessor (e.g. a property).

Manually specifying primary keys
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes you do not want the database to automatically generate a value for
the primary key, for instance when bulk loading relational data. To handle this
on a *one-off* basis, you can simply tell peewee to turn off ``auto_increment``
during the import:

.. code-block:: python

    data = load_user_csv() # load up a bunch of data

    User._meta.auto_increment = False # turn off auto incrementing IDs
    with db.atomic():
        for row in data:
            u = User(id=row[0], username=row[1])
            u.save(force_insert=True) # <-- force peewee to insert row

    User._meta.auto_increment = True

Although a better way to accomplish the above, without resorting to hacks, is
to use the :py:meth:`Model.insert_many` API:

.. code-block:: python

    data = load_user_csv()
    fields = [User.id, User.username]
    with db.atomic():
        User.insert_many(data, fields=fields).execute()

If you *always* want to have control over the primary key, simply do not use
the :py:class:`AutoField` field type, but use a normal
:py:class:`IntegerField` (or other column type):

.. code-block:: python

    class User(BaseModel):
        id = IntegerField(primary_key=True)
        username = CharField()

    >>> u = User.create(id=999, username='somebody')
    >>> u.id
    999
    >>> User.get(User.username == 'somebody').id
    999

Models without a Primary Key
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you wish to create a model with no primary key, you can specify
``primary_key = False`` in the inner ``Meta`` class:

.. code-block:: python

    class MyData(BaseModel):
        timestamp = DateTimeField()
        value = IntegerField()

        class Meta:
            primary_key = False

This will yield the following DDL:

.. code-block:: sql

    CREATE TABLE "mydata" (
      "timestamp" DATETIME NOT NULL,
      "value" INTEGER NOT NULL
    )

.. warning::
    Some model APIs may not work correctly for models without a primary key,
    for instance :py:meth:`~Model.save` and :py:meth:`~Model.delete_instance`
    (you can instead use :py:meth:`~Model.insert`, :py:meth:`~Model.update` and
    :py:meth:`~Model.delete`).

Self-referential foreign keys
-----------------------------

When creating a hierarchical structure it is necessary to create a
self-referential foreign key which links a child object to its parent.  Because
the model class is not defined at the time you instantiate the self-referential
foreign key, use the special string ``'self'`` to indicate a self-referential
foreign key:

.. code-block:: python

    class Category(Model):
        name = CharField()
        parent = ForeignKeyField('self', null=True, backref='children')

As you can see, the foreign key points *upward* to the parent object and the
back-reference is named *children*.

.. attention:: Self-referential foreign-keys should always be ``null=True``.

When querying against a model that contains a self-referential foreign key you
may sometimes need to perform a self-join. In those cases you can use
:py:meth:`Model.alias` to create a table reference. Here is how you might query
the category and parent model using a self-join:

.. code-block:: python

    Parent = Category.alias()
    GrandParent = Category.alias()
    query = (Category
             .select(Category, Parent)
             .join(Parent, on=(Category.parent == Parent.id))
             .join(GrandParent, on=(Parent.parent == GrandParent.id))
             .where(GrandParent.name == 'some category')
             .order_by(Category.name))

.. _circular-fks:

Circular foreign key dependencies
---------------------------------

Sometimes it happens that you will create a circular dependency between two
tables.

.. note::
    My personal opinion is that circular foreign keys are a code smell and
    should be refactored (by adding an intermediary table, for instance).

Adding circular foreign keys with peewee is a bit tricky because at the time
you are defining either foreign key, the model it points to will not have been
defined yet, causing a ``NameError``.

.. code-block:: python

    class User(Model):
        username = CharField()
        favorite_tweet = ForeignKeyField(Tweet, null=True)  # NameError!!

    class Tweet(Model):
        message = TextField()
        user = ForeignKeyField(User, backref='tweets')

One option is to simply use an :py:class:`IntegerField` to store the raw ID:

.. code-block:: python

    class User(Model):
        username = CharField()
        favorite_tweet_id = IntegerField(null=True)

By using :py:class:`DeferredForeignKey` we can get around the problem and still
use a foreign key field:

.. code-block:: python

    class User(Model):
        username = CharField()
        # Tweet has not been defined yet so use the deferred reference.
        favorite_tweet = DeferredForeignKey('Tweet', null=True)

    class Tweet(Model):
        message = TextField()
        user = ForeignKeyField(User, backref='tweets')

    # Now that Tweet is defined, "favorite_tweet" has been converted into
    # a ForeignKeyField.
    print(User.favorite_tweet)
    # <ForeignKeyField: "user"."favorite_tweet">

There is one more quirk to watch out for, though. When you call
:py:class:`~Model.create_table` we will again encounter the same issue. For
this reason peewee will not automatically create a foreign key constraint for
any *deferred* foreign keys.

To create the tables *and* the foreign-key constraint, you can use the
:py:meth:`SchemaManager.create_foreign_key` method to create the constraint
after creating the tables:

.. code-block:: python

    # Will create the User and Tweet tables, but does *not* create a
    # foreign-key constraint on User.favorite_tweet.
    db.create_tables([User, Tweet])

    # Create the foreign-key constraint:
    User._schema.create_foreign_key(User.favorite_tweet)

.. note::
    Because SQLite has limited support for altering tables, foreign-key
    constraints cannot be added to a table after it has been created.
