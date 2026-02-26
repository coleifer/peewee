.. _models:

Models and Fields
=================

Models and Fields allow Peewee applications to declare the tables and columns
they will use, and issue queries using Python. This document explains how to
use Peewee to express database tables and columns.

:class:`Model` classes, :class:`Field` instances and model instances all
map to database concepts:

================= =================================
Python construct  Database concept
================= =================================
Model class       Table
Field instance    Column
Model instance    Row
================= =================================

.. tip::
   If you are connecting Peewee to an existing database rather than defining a
   schema from scratch, the :ref:`pwiz <pwiz>` tool can generate model
   definitions automatically by introspecting the database.

The following code shows the typical way you will define your database
connection and model classes.

.. code-block:: python
   :emphasize-lines: 4, 6, 10

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
       content = TextField()
       timestamp = DateTimeField(default=datetime.datetime.now)
       is_published = BooleanField(default=True)

   class Favorite(BaseModel):
       user = ForeignKeyField(User, backref='favorites')
       tweet = ForeignKeyField(Tweet, backref='favorites')

Three things to note:

1. Create an instance of a :class:`Database`.

   .. code-block:: python

      db = SqliteDatabase('my_app.db')

   The ``db`` object will be used to manage the connections to the Sqlite
   database. In this example we're using :class:`SqliteDatabase`, but you
   could also use one of the other :ref:`database engines <database>`.

2. Create a base model class which specifies our database.

   .. code-block:: python

      class BaseModel(Model):
          class Meta:
              database = db

   **BaseModel** exists only to specify the ``database`` setting in its ``Meta``
   class. Because ``Meta.database`` is inheritable, every model that extends
   ``BaseModel`` will automatically use the same database. This pattern avoids
   repeating the database assignment on every model class.

   Model configuration is kept namespaced in a special class called ``Meta``.
   :ref:`Meta <model-options>` configuration is passed on to subclasses, so
   our project's models will all subclass *BaseModel*. There are
   :ref:`many different attributes <model-options>` you can configure using *Model.Meta*.

3. Declare model classes and fields.

   .. code-block:: python

      class User(BaseModel):
          username = CharField(unique=True)

   Model definition uses the declarative style seen in other popular ORMs.
   Note that we are extending the *BaseModel* class so the *User* model will
   inherit the database connection.

   We have explicitly defined a single *username* column with a unique
   constraint. Because we have not specified a primary key, Peewee will
   automatically add an auto-incrementing integer primary key field named
   *id*.

Model Inheritance
-----------------

Model subclasses inherit the ``Meta`` configuration of their parent as well as
the parent's fields. Inherited ``Meta`` attributes (such as ``database``) are
shared; non-inheritable attributes (such as ``table_name``) are re-derived for
each subclass.

.. code-block:: python

   class BaseModel(Model):
       class Meta:
           database = db

   class TimestampedModel(BaseModel):
       """Adds created/updated timestamps to any subclass."""
       created = DateTimeField(default=datetime.datetime.now)
       updated = DateTimeField(default=datetime.datetime.now)

   class Article(TimestampedModel):
       title = TextField()
       body = TextField()
       # Article.created and Article.updated are inherited.
       # Article._meta.database is inherited from BaseModel.

Peewee uses a separate table for each concrete model class. There is no
notion of inheritance spanning multiple tables. If you subclass a model,
both the parent and the child have their own tables.

.. _fields:

Fields
------

The :class:`Field` class is used to describe the mapping of :class:`Model`
attributes to database columns. Each field type has a corresponding SQL storage
class (varchar, int, etc). Fields handle conversion between python data types
and underlying storage transparently.

When creating a :class:`Model` class, fields are defined as class attributes:

.. code-block:: python

   class Tweet(BaseModel):
       user = ForeignKeyField(User, backref='tweets')
       content = TextField()
       timestamp = DateTimeField(default=datetime.datetime.now)
       is_published = BooleanField(default=True)

In the above example, no field specifies ``primary_key=True``. As a result,
Peewee will create an auto-incrementing integer primary key named ``id``.
Peewee uses :class:`AutoField` to signify an auto-incrementing integer primary
key.

.. _field_types_table:

Field types
^^^^^^^^^^^

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

Common field parameters
^^^^^^^^^^^^^^^^^^^^^^^

All field types accept the following keyword arguments:

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

Special parameters
^^^^^^^^^^^^^^^^^^

+-----------------------------+------------------------------------------------+
| Field type                  | Special Parameters                             |
+=============================+================================================+
| :class:`ForeignKeyField`    | ``model``, ``field``, ``backref``,             |
|                             | ``on_delete``, ``on_update``, ``deferrable``   |
|                             | ``lazy_load``                                  |
+-----------------------------+------------------------------------------------+
| :class:`CharField`          | ``max_length``                                 |
+-----------------------------+------------------------------------------------+
| :class:`FixedCharField`     | ``max_length``                                 |
+-----------------------------+------------------------------------------------+
| :class:`DateTimeField`      | ``formats``                                    |
+-----------------------------+------------------------------------------------+
| :class:`DateField`          | ``formats``                                    |
+-----------------------------+------------------------------------------------+
| :class:`TimeField`          | ``formats``                                    |
+-----------------------------+------------------------------------------------+
| :class:`TimestampField`     | ``resolution``, ``utc``                        |
+-----------------------------+------------------------------------------------+
| :class:`DecimalField`       | ``max_digits``, ``decimal_places``,            |
|                             | ``auto_round``, ``rounding``                   |
+-----------------------------+------------------------------------------------+
| :class:`BareField`          | ``adapt``                                      |
+-----------------------------+------------------------------------------------+

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
          status = IntegerField(constraints=[Check('status in (0, 1, 2)')])

Default field values
^^^^^^^^^^^^^^^^^^^^

Peewee can provide default values for fields when objects are created. For
example to have an ``IntegerField`` default to zero rather than ``NULL``, you
could declare the field with a default value:

.. code-block:: python

   class Message(Model):
       context = TextField()
       read_count = IntegerField(default=0)
       created = DateTimeField(default=datetime.datetime.now)

For ``read_count``, Peewee uses the literal value ``0``. For ``created``,
Peewee calls ``datetime.datetime.now`` at the moment of instantiation -
note that the **function itself is passed, not its return value**.

**Mutable defaults require a factory function.** If a default value is a mutable
object such as a ``list`` or ``dict``, passing it directly means every model
instance shares *the same object*. Wrap it in a function instead:

.. code-block:: python

   # Wrong: all instances share one dict.
   class Config(BaseModel):
       settings = JSONField(default={})

   # Correct: each instance gets a fresh dict.
   def default_settings():
       return {}

   class Config(BaseModel):
       settings = JSONField(default=default_settings)

The database can also provide the default value for a field. While Peewee does
not explicitly provide an API for setting a server-side default value, you can
use the ``constraints`` and :func:`Default` to specify the server default:

.. code-block:: python

   class Message(Model):
       content = TextField()
       timestamp = DateTimeField(constraints=[Default('CURRENT_TIMESTAMP')])

This produces a ``DEFAULT CURRENT_TIMESTAMP`` clause in the ``CREATE TABLE``
statement. Peewee's own ``default`` parameter produces no DDL; it only operates
during Python-side model instantiation.

A consequence of using server-generated defaults is that newly-inserted models
will not automatically retrieve the new value. This requires a separate query
to read back the defaults added by the server.

ForeignKeyField
---------------

:class:`ForeignKeyField` links a model to another model. It stores the
related row's primary key as an integer column and provides a Python-level
descriptor that resolves it to a full model instance on access.

.. code-block:: python

   class Tweet(BaseModel):
       user = ForeignKeyField(User, backref='tweets')
       content = TextField()

The ``backref`` parameter creates a reverse accessor on the target model.
With ``backref='tweets'``, every ``User`` instance gains a ``tweets``
attribute that returns a pre-filtered :class:`Select` query of that user's
tweets.

:class:`ForeignKeyField` accepts referential action parameters:

- ``on_delete`` - action to take when the referenced row is deleted.
  Common values: ``'CASCADE'``, ``'SET NULL'``, ``'RESTRICT'``.
- ``on_update`` - action to take when the referenced row's primary key changes.
- ``deferrable`` - defers constraint checking to transaction commit
  (Postgresql and SQLite only).

.. warning::
   SQLite does not enforce foreign key constraints by default. Enable
   enforcement by setting the ``foreign_keys`` pragma on connection:

   .. code-block:: python

      db = SqliteDatabase('my_app.db', pragmas={'foreign_keys': 1})

.. seealso::
   :ref:`relationships` covers how foreign keys behave at runtime, including
   lazy loading, back-references, and avoiding N+1 query problems.

Typically a foreign key will reference the primary key of the related model,
but you can specify a particular column by specifying ``field=``.

In Peewee, accessing the value of a :class:`ForeignKeyField` will return the
entire related object:

.. code-block:: python

   tweets = (Tweet
             .select(Tweet, User)
             .join(User)
             .order_by(Tweet.created_date.desc()))

   for tweet in tweets:
       print(tweet.user.username, tweet.message)

In the example above the ``User`` data was selected efficiently. If we did not
select the ``User``, then an **additional query** would be needed to fetch the
associated ``User`` data:

.. code-block:: python

    tweets = (Tweet
              .select()
              .order_by(Tweet.created_date.desc())

    for tweet in tweets:
        # WARNING: an additional query will be issued for EACH tweet
        # to fetch the associated User data.
        print(tweet.user.username, tweet.message)

Sometimes you only need the associated primary key value from the foreign key
column. Peewee allows you to access the raw foreign key value by appending
``"_id"`` to the foreign key field's name:

.. code-block:: python

   tweets = Tweet.select()

   for tweet in tweets:
       # Instead of "tweet.user", we will just get the raw ID value stored
       # in the column.
       print(tweet.user_id, tweet.message)

To prevent accidentally resolving a foreign-key and triggering an additional
query, :class:`ForeignKeyField` supports an initialization paramater
``lazy_load`` which, when disabled, behaves like the ``"_id"`` attribute:

.. code-block:: python

   class Tweet(Model):
       # lazy-load disabled:
       user = ForeignKeyField(User, backref='tweets', lazy_load=False)
       ...

   for tweet in Tweet.select():
       print(tweet.user, tweet.message)

   # With lazy-load disabled, accessing tweet.user will NOT perform an extra
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

:class:`ForeignKeyField` allows for a back-reference property to be bound to
the target model. This property will be named ``<classname>_set`` by default,
where ``classname`` is the lowercase name of the model class. This name can be
overridden by specifying ``backref=``:

.. code-block:: python

   class Message(Model):
       from_user = ForeignKeyField(User, backref='outbox')
       to_user = ForeignKeyField(User, backref='inbox')
       text = TextField()

   for message in some_user.outbox:
       # We are iterating over all Messages whose from_user is some_user.
       print(message)

Back-references are just pre-filtered select queries, so we can add
additional behavior like ``order_by()``:

.. code-block:: python

   for message in some_user.inbox.order_by(Message.id):
       # Iterate over all Messages whose to_user is some_user.
       print(message)

Self-referential foreign keys
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When creating a hierarchical structure it is necessary to create a
self-referential foreign key which links a child object to its parent. Because
the model class is not defined at the time you instantiate the self-referential
foreign key, use the special string ``'self'`` to indicate a self-referential
foreign key:

.. code-block:: python

   class Category(Model):
       name = CharField()
       parent = ForeignKeyField('self', null=True, backref='children')

The foreign key points **upward** to the parent object and the back-reference
is named **children**.

.. attention:: Self-referential foreign-keys should always be ``null=True``.

When querying against a model that contains a self-referential foreign key you
may sometimes need to perform a self-join. In those cases you can use
:meth:`Model.alias` to create a table reference. Here is how you might query
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

For deeply nested hierarchies, recursive CTEs are more efficient than
repeated self-joins. See :ref:`cte`.

.. seealso:: :ref:`relationships`

Date and Time Fields
--------------------

The three fields devoted to working with dates and times have properties to
access date attributes like year, month, hour, etc.

:class:`DateField`
   Properties for: ``year``, ``month``, ``day``

:class:`TimeField`
   Properties for: ``hour``, ``minute``, ``second``

:class:`DateTimeField`:
   Properties for: ``year``, ``month``, ``day``, ``hour``, ``minute``, ``second``

These properties can be used as an expression in a query. Let's say we have
an events table and want to list all the days in the current month which have
at least one event:

.. code-block:: python

    # Get the current date.
    today = datetime.date.today()

    # Get days that have events for the current month.
    query = (Event
             .select(Event.event_date.day.alias('day'))
             .where(
                 (Event.event_date.year == today.year) &
                 (Event.event_date.month == today.month))
             .distinct())

   # Group activity by hour of day.
   query = (PageView
            .select(
                PageView.timestamp.hour.alias('hour'),
                fn.COUNT(PageView.id).alias('n'))
            .group_by(PageView.timestamp.hour)
            .order_by(PageView.timestamp.hour))

.. note::
   SQLite does not have a native date type, so dates are stored in formatted
   text columns. To ensure that comparisons work correctly, the dates need to
   be formatted so they are sorted lexicographically. That is why they are
   stored, by default, as ``YYYY-MM-DD HH:MM:SS``.

:class:`TimestampField` stores a datetime as a Unix timestamp integer.
The ``resolution`` parameter controls sub-second precision (default: seconds);
``utc=True`` instructs Peewee to treat stored values as UTC.

BitField and BigBitField
------------------------

The :class:`BitField` and :class:`BigBitField` are suitable for storing
bitmap data. :class:`BitField` provides a subclass of :class:`IntegerField`
that is suitable for storing feature toggles as an integer bitmask. The latter
is suitable for storing a bitmap for a large data-set, e.g. expressing
membership or bitmap-type data.

As an example of using :class:`BitField`, let's say we have a *Post* model
and we wish to store certain True/False flags about how the post. We could
store all these feature toggles in their own :class:`BooleanField` objects,
or we could use a single :class:`BitField` instead:

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

Since the :class:`BitField` is stored in an integer, there is a maximum of
64 flags you can represent (64-bits is common size of integer column). For
storing arbitrarily large bitmaps, you can instead use :class:`BigBitField`,
which uses an automatically managed buffer of bytes, stored in a
:class:`BlobField`.

When bulk-updating one or more bits in a :class:`BitField`, you can use
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

.. _model-options:

Model Settings
--------------

Model-specific configuration is placed in a special :class:`Metadata` class
called ``Meta``:

.. code-block:: python
   :emphasize-lines: 8, 9

   from peewee import *

   contacts_db = SqliteDatabase('contacts.db')

   class Person(Model):
       name = CharField()

       class Meta:
           database = contacts_db

This instructs Peewee that whenever a query is executed on *Person* to use the
contacts database.

Once the class is defined metadata settings are accessible at ``ModelClass._meta``:

.. code-block:: pycon

   >>> Person.Meta
   Traceback (most recent call last):
     File "<stdin>", line 1, in <module>
   AttributeError: type object 'Person' has no attribute 'Meta'

   >>> Person._meta
   <peewee.Metadata object at 0x7f51a2f03790>

The :class:`Metadata` class implements several methods which may be of use for
retrieving model metadata (such as lists of fields, foreign key relationships,
and more).

.. code-block:: pycon

   >>> User._meta.fields
   {'id': <peewee.AutoField object at 0x7f51a2e92750>,
    'username': <peewee.CharField object at 0x7f51a2f0a510>}

   >>> User._meta.primary_key
   <peewee.AutoField object at 0x7f51a2e92750>

   >>> User._meta.database
   <peewee.SqliteDatabase object at 0x7f519bff6dd0>

There are several options you can specify as ``Meta`` attributes. While most
options are inheritable, some are table-specific and will not be inherited by
subclasses.

=========================  ======================================================  ============
Option                     Purpose                                                 Inheritable
=========================  ======================================================  ============
``database``               Database instance for this model.                       Yes
``table_name``             Explicit table name.                                    No
``table_function``         Callable that returns a table name from the class.      Yes
``indexes``                Tuple of multi-column index definitions.                Yes
``primary_key``            :class:`CompositeKey` or ``False``.                     Yes
``constraints``            List of table-level constraint expressions.             Yes
``schema``                 Database schema name.                                   Yes
``only_save_dirty``        Only emit changed fields on ``save()``.                 Yes
``options``                Extra options for ``CREATE TABLE`` extensions.          Yes
``table_settings``         Strings appended after the closing parenthesis in DDL.  Yes
``temporary``              Mark as a temporary table.                              Yes
``legacy_table_names``     Use legacy (non-snake-case) table name generation.      Yes
``depends_on``             Declare a dependency on another table for ordering.     No
``without_rowid``          SQLite ``WITHOUT ROWID`` tables.                        No
``strict_tables``          SQLite strict typing (3.37+).                           Yes
=========================  ======================================================  ============

Example of inheritable vs non-inheritable settings:

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

.. _table-names:

Table naming
^^^^^^^^^^^^

By default Peewee derives the table name from the model class name. The exact
transformation depends on ``Meta.legacy_table_names``:

=================== =========================  ==============================
Model class name    legacy (default)           non-legacy
=================== =========================  ==============================
``User``            ``user``                   ``user``
``UserProfile``     ``userprofile``            ``user_profile``
``APIResponse``     ``apiresponse``            ``api_response``
``WebHTTPRequest``  ``webhttprequest``          ``web_http_request``
=================== =========================  ==============================

New projects should opt into non-legacy naming by setting
``legacy_table_names = False`` on ``BaseModel``. The legacy default exists
only for backwards compatibility with existing deployments.

.. code-block:: python

   class BaseModel(Model):
       class Meta:
           database = db
           legacy_table_names = False   # Recommended for new projects.

To override the table name entirely, use ``table_name``:

.. code-block:: python

   class UserProfile(BaseModel):
       class Meta:
           table_name = 'acct_user_profile'   # Maps to pre-existing table.

To apply a naming convention programmatically across all models, use
``table_function``:

.. code-block:: python

   def prefixed_table_name(model_class):
       return 'myapp_' + model_class.__name__.lower()

   class BaseModel(Model):
       class Meta:
           database = db
           table_function = prefixed_table_name

   class User(BaseModel):
       pass   # Table name: "myapp_user"

.. _model_indexes:

Indexes and Constraints
-----------------------

Peewee can create indexes on single or multiple columns, optionally including a
*UNIQUE* constraint. Peewee also supports user-defined constraints on both
models and fields.

Single-column indexes and constraints
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Single column indexes are defined by specifying ``index=True`` or
``unique=True`` when declaring the Field.

Add a unique index on *username* and a normal b-tree index on *email*:

.. code-block:: python

   class User(Model):
       username = CharField(unique=True)
       email = CharField(index=True)

To add a user-defined constraint on a column, you can specify it using the
``constraints`` parameter. You may wish to specify a default value as part of
the schema, or add a ``CHECK`` constraint, for example:

.. code-block:: python

   class Product(Model):
       name = CharField(unique=True)
       price = DecimalField(constraints=[Check('price < 10000')])
       created = DateTimeField(constraints=[Default('CURRENT_TIMESTAMP')])

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

Partial and expression indexes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Partial indexes, indexes with expressions, and more complex indexes can use the
:meth:`Model.add_index` API:

.. code-block:: python

   class Article(BaseModel):
       name = TextField()
       timestamp = TimestampField()
       status = IntegerField()

   # Add a partial index on name and timestamp where status = 1.
   Article.add_index(Article.name, Article.timestamp,
                     where=(Article.status == 1))

   # Create a unique index on timestamp desc, status & 4.
   idx = Article.index(
       Article.timestamp.desc(),
       Article.flags.bin_and(4),
       unique=True)
   Article.add_index(idx)

.. note::
   SQLite does not support parameterized ``CREATE INDEX`` queries. Partial
   indexes and expression indexes on SQLite must be written using
   :class:`SQL`:

   .. code-block:: python

      Article.add_index(SQL('CREATE INDEX ... WHERE status = 1'))

If the above is cumbersome, you can also pass a :class:`SQL` instance to
``Meta.indexes``:

.. code-block:: python

   class Article(BaseModel):
       name = TextField()
       timestamp = TimestampField()
       status = IntegerField()

       class Meta:
           indexes = [
               SQL('CREATE INDEX article_published_lookup ON '
                   'article (name, timestamp) WHERE status = 1'),
           ]

Primary Keys
------------

Auto-incrementing integer primary key
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If a model declares no primary key, Peewee automatically adds an
auto-incrementing integer field named ``id``:

.. code-block:: python

   class Article(BaseModel):
       title = TextField()
       # Peewee implicitly adds: id = AutoField()

To use a different name for the auto-incrementing primary key, declare an
:class:`AutoField` explicitly:

.. code-block:: python

   class Article(BaseModel):
       article_id = AutoField()
       title = TextField()

.. warning::
   A common mistake is writing ``id = IntegerField(primary_key=True)`` when
   intending an auto-incrementing primary key. This declares a plain integer
   column whose value the application must supply - the database will not
   generate it. Use :class:`AutoField` for auto-increment behavior.

Non-integer primary keys
^^^^^^^^^^^^^^^^^^^^^^^^

Any field can serve as the primary key by passing ``primary_key=True``:

.. code-block:: python

   class Country(BaseModel):
       code = CharField(max_length=2, primary_key=True)   # e.g. 'US', 'DE'
       name = TextField()

When using a non-auto-incrementing primary key, Peewee cannot distinguish
between a new row (needs ``INSERT``) and an existing row (needs ``UPDATE``)
by checking whether the primary key is ``None``. On the first save, pass
``force_insert=True`` explicitly:

.. code-block:: python

   country = Country(code='DE', name='Germany')
   country.save(force_insert=True)   # First save: must force INSERT.
   country.name = 'Deutschland'
   country.save()                    # Subsequent saves: UPDATE as normal.

:meth:`Model.create` handles this automatically, so it is the simpler
option for one-step creation:

.. code-block:: python

   country = Country.create(code='DE', name='Germany')

.. _composite-keys:

Composite primary keys
^^^^^^^^^^^^^^^^^^^^^^

Use :class:`CompositeKey` in ``Meta.primary_key`` to designate two or more
columns as a composite primary key:

.. code-block:: python

   class TweetTag(BaseModel):
       tweet = ForeignKeyField(Tweet)
       tag = TextField()

       class Meta:
           primary_key = CompositeKey('tweet', 'tag')

Composite primary keys are most appropriate for junction tables in many-to-many
relationships. Peewee has limited support for foreign keys *to* models with
composite primary keys; avoid them in models that other models will reference.

Models without a primary key
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To create a table with no primary key, set ``primary_key = False``:

.. code-block:: python

   class LogEntry(BaseModel):
       timestamp = DateTimeField()
       event = TextField()

       class Meta:
           primary_key = False

Note that :meth:`Model.save` and :meth:`Model.delete_instance` do not
work on keyless models, since both require a primary key to target a specific
row. Use :meth:`Model.insert`, :meth:`Model.update`, and :meth:`Model.delete`
(the class-level query methods) instead.

Table Constraints
-----------------

Peewee allows arbitrary constraints to :class:`Model` classes.

Suppose you have a *people* table with a composite primary key of two columns:
the person's first and last name. You wish to have another table relate to the
*people* table. To do this define a multi-column foreign key constraint:

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

``CHECK`` constraints can be specified at the table level:

.. code-block:: python

   class Product(Model):
       name = CharField(unique=True)
       price = DecimalField()

       class Meta:
           constraints = [Check('price < 10000')]

Creating Tables
---------------

Once models are defined, create their corresponding tables with
:meth:`Database.create_tables`:

.. code-block:: python

   db.create_tables([User, Tweet, Favorite])

To create a single table, use :meth:`Model.create_table`:

.. code-block:: python

   Tweet.create_table()

.. seealso::
   :ref:`schema` for documentation on table creation and other schema
   management tasks.

.. _advanced-model-topics:

Advanced Topics
---------------

The following sections cover scenarios that arise less frequently. New users
can skip this section and return to it when the need arises.

.. _circular-fks:

Circular foreign key dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes it happens that you will create a circular dependency between two
tables.

.. note::
   Circular foreign keys should be refactored (by adding an intermediary table,
   for instance).

Adding circular foreign keys with peewee is a bit tricky because at the time
you are defining either foreign key, the model it points to will not have been
defined yet, causing a ``NameError``.

.. code-block:: python
   :emphasize-lines: 3

   class User(Model):
       username = CharField()
       favorite_tweet = ForeignKeyField(Tweet, null=True)  # NameError!!

   class Tweet(Model):
       message = TextField()
       user = ForeignKeyField(User, backref='tweets')

One option is to simply use an :class:`IntegerField` to store the raw ID:

.. code-block:: python

   class User(Model):
       username = CharField()
       favorite_tweet_id = IntegerField(null=True)

By using :class:`DeferredForeignKey` we can get around the problem and still
use a foreign key field:

.. code-block:: python

   class User(BaseModel):
       username = TextField()
       favorite_tweet = DeferredForeignKey('Tweet', null=True)

   class Tweet(BaseModel):
       user = ForeignKeyField(User, backref='tweets')
       content = TextField()

   db.create_tables([User, Tweet])

   # Add the constraint that could not be created at table-creation time.
   User._schema.create_foreign_key(User.favorite_tweet)

.. note::
   Because SQLite has limited support for altering tables, foreign-key
   constraints cannot be added to a table after it has been created.

Field naming conflicts
^^^^^^^^^^^^^^^^^^^^^^

Several names are reserved by :class:`Model` for built-in methods and
attributes (for example ``save``, ``create``, ``delete``, ``update``,
``get``). Declaring a field with one of these names overwrites the method.

When the desired column name conflicts with a model method, supply an
alternative attribute name and set ``column_name`` explicitly:

.. code-block:: python

   class LogEntry(BaseModel):
       timestamp = DateTimeField()
       # "create" and "update" would conflict with Model.create / Model.update.
       created_at = DateTimeField(column_name='create')
       updated_at = DateTimeField(column_name='update')

The database column is still named ``create`` and ``update``; the Python
attributes are ``created_at`` and ``updated_at``.

.. _barefield:

BareField (SQLite only)
^^^^^^^^^^^^^^^^^^^^^^^

:class:`BareField` declares a column with no type affinity. It is only
meaningful with SQLite, which permits untyped columns and virtual table
columns.

.. code-block:: python

   class FTSEntry(BaseModel):
       content = BareField()

The optional ``adapt`` parameter specifies a callable that converts values
coming from the database into a Python type:

.. code-block:: python

   class RawData(BaseModel):
       value = BareField(adapt=float)

For full-text search virtual tables, use :class:`SearchField` rather
than :class:`BareField`. See :ref:`sqlite-fts`.

.. _custom-fields:

Custom fields
^^^^^^^^^^^^^

A custom field is a subclass of an existing field that overrides the
Python-to-database and database-to-Python conversion methods. This is most
useful when a database offers a column type that has no built-in Peewee
equivalent, or when a standard column type should carry application-specific
Python behavior.

The two conversion hooks are:

- ``db_value(self, value)`` - converts a Python value to the format the
  database driver expects.
- ``python_value(self, value)`` - converts a value from the database driver
  into the desired Python type.

The following example implements a field that stores a ``pathlib.Path``
value as a ``TEXT`` column:

.. code-block:: python

   from pathlib import Path

   class PathField(TextField):
       def db_value(self, value):
           return str(value) if value is not None else None

       def python_value(self, value):
           return Path(value) if value is not None else None

   class Document(BaseModel):
       path = PathField()

   doc = Document.create(path=Path('/var/data/report.pdf'))
   assert isinstance(doc.path, Path)

When the database requires a completely new storage type (not a variant of an
existing one), set ``field_type`` to the type label and register the label
with each database that will use it:

.. code-block:: python

   class PointField(Field):
       field_type = 'point'   # Custom type label.

       def db_value(self, value):
           if value is not None:
               return f'{value[0]},{value[1]}'

       def python_value(self, value):
           if value is not None:
               x, y = value.split(',')
               return (float(x), float(y))

   # Tell Peewee what DDL type to emit for each database.
   sq_db  = SqliteDatabase('mydb', field_types={'point': 'text'})

.. seealso:: :class:`Field` API reference.
