.. _models:

Models and Fields
=================

:py:class:`Model` classes, :py:class:`Field` instances and model instances all
map to database concepts:

================= =================================
Object            Corresponds to...
================= =================================
Model class       Database table
Field instance    Column on a table
Model instance    Row in a database table
================= =================================

The following code shows the typical way you will define your database
connection and model classes.

.. _blog-models:

.. code-block:: python
   :emphasize-lines: 4, 6, 10, 13

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
    :ref:`Meta <model-options>` configuration is passed on to subclasses, so
    our project's models will all subclass *BaseModel*. There are
    :ref:`many different attributes <model-options>` you can configure using *Model.Meta*.

3. Define model classes.

    .. code-block:: python

       class User(BaseModel):
           username = CharField(unique=True)

    Model definition uses the declarative style seen in other popular ORMs.
    Note that we are extending the *BaseModel* class so the *User* model will
    inherit the database connection.

    We have explicitly defined a single *username* column with a unique
    constraint. Because we have not specified a primary key, peewee will
    automatically add an auto-incrementing integer primary key field named
    *id*.

.. seealso::
   If you would like to start using peewee with an existing database, you can
   use :ref:`pwiz` to **automatically** generate model definitions.

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
created and named ``id``. Peewee uses :py:class:`AutoField` to signify an
auto-incrementing integer primary key, which implies ``primary_key=True``.

There is one special type of field, :py:class:`ForeignKeyField`, which allows
you to represent foreign-key relationships between models in an intuitive way:

.. code-block:: python
   :emphasize-lines: 2

   class Message(Model):
       user = ForeignKeyField(User, backref='messages')
       body = TextField()
       send_date = DateTimeField(default=datetime.datetime.now)

This allows you to write code like the following:

.. code-block:: pycon
   :emphasize-lines: 1, 4

   >>> print(some_message.user.username)
   Some User

   >>> for message in some_user.messages:
   ...     print(message.body)
   some message
   another message
   yet another message

.. seealso::
   - :ref:`relationships` in-depth discussion of foreign-keys and joins.
   - :ref:`Fields API <fields-api>`.

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

.. seealso:: :ref:`custom-fields`

Field initialization arguments
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Parameters accepted by all field types and their default values:

================ ========= =======================================================================
Parameter        Default   Description
================ ========= =======================================================================
``null``         ``False`` allow null values
``index``        ``False`` create an index on this column
``unique``       ``False`` create a unique index on this column.
                           See also :ref:`adding composite indexes <model_indexes>`.
``column_name``  ``None``  explicitly specify the column name in the database.
``default``      ``None``  any value or callable to use as a default for uninitialized models
``primary_key``  ``False`` primary key for the table
``constraints``  ``None``  one or more constraints, e.g. ``[Check('price > 0')]``
``sequence``     ``None``  sequence name (if backend supports it)
``collation``    ``None``  collation to use for ordering the field / index
``unindexed``    ``False`` indicate field on virtual table should be unindexed (**SQLite-only**)
``choices``      ``None``  optional iterable containing 2-tuples of ``value``, ``display``
``help_text``    ``None``  string representing any helpful text for this field
``verbose_name`` ``None``  string representing the "user-friendly" name of this field
``index_type``   ``None``  specify a custom index-type, e.g. for Postgres you might
                           specify a ``'BRIN'`` or ``'GIN'`` index.
================ ========= =======================================================================

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
   parameter:

   .. code-block:: python

      class Product(Model):
          price = DecimalField(max_digits=8, decimal_places=2,
                               constraints=[Check('price >= 0')])
          added = DateTimeField(constraints=[Default('CURRENT_TIMESTAMP')])

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
use the ``constraints`` and :func:`Default` to specify the server default:

.. code-block:: python

    class Message(Model):
        context = TextField()
        timestamp = DateTimeField(constraints=[Default('CURRENT_TIMESTAMP')])

.. note::
   **Remember:** when using the ``default`` parameter, the values are set by
   Peewee rather than being a part of the actual table and column definition.

ForeignKeyField
^^^^^^^^^^^^^^^

:class:`ForeignKeyField` is a special field type that allows one model to
reference another. Typically a foreign key will contain the primary key of the
model it relates to (but you can specify a particular column by specifying a
``field``).

Foreign keys allow data to be `normalized <http://en.wikipedia.org/wiki/Database_normalization>`_.
In our example models, there is a foreign key from ``Tweet`` to ``User``. This
means that all the users are stored in their own table, as are the tweets, and
the foreign key from tweet to user allows each tweet to *point* to a particular
user object.

.. seealso::
   Refer to the :ref:`relationships` document for an in-depth discussion of
   foreign keys, joins and relationships between models.

In peewee, accessing the value of a :py:class:`ForeignKeyField` will return the
entire related object, e.g.:

.. code-block:: python
   :emphasize-lines: 2, 6

   tweets = (Tweet
             .select(Tweet, User)
             .join(User)
             .order_by(Tweet.created_date.desc()))
   for tweet in tweets:
       print(tweet.user.username, tweet.message)

.. seealso::
   In the example above the ``User`` data was selected efficiently.
   For more information, see the :ref:`Avoiding N+1 <nplusone>` document.

If we did not select the ``User``, then an **additional query** would be
needed to fetch the associated ``User`` data:

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
   :emphasize-lines: 5

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
to the target model. Implicitly, this property will be named ``<classname>_set``,
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

The :py:class:`BitField` and :py:class:`BigBitField` are suitable for storing
bitmap data. :py:class:`BitField` provides a subclass of :py:class:`IntegerField`
that is suitable for storing feature toggles as an integer bitmask. The latter
is suitable for storing a bitmap for a large data-set, e.g. expressing
membership or bitmap-type data.

As an example of using :py:class:`BitField`, let's say we have a *Post* model
and we wish to store certain True/False flags about how the post. We could
store all these feature toggles in their own :py:class:`BooleanField` objects,
or we could use a single :py:class:`BitField` instead:

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

   # BigBitField supports item accessor by bit-number, e.g.:
   assert bitmap.data[63]
   bitmap.data[0] = 1
   del bitmap.data[0]

   # We can also combine bitmaps using bitwise operators, e.g.
   b = Bitmap(data=b'\x01')
   b.data |= b'\x02'
   assert list(b.data) == [1, 1, 0, 0, 0, 0, 0, 0]
   assert len(b.data) == 1

