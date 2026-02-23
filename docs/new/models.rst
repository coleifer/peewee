.. _models:

Models and Fields
=================

Models and Fields allow Peewee applications to declare the tables and columns
they will use, and issue queries using Python. This document explains how to
use Peewee to express database schema concepts.

By the end of this document you will understand:

* How :class:`Model` and :class:`Field` define a table
* What types of fields Peewee provides, and the data-types they support.
* How to control table settings.

:class:`Model` classes, :class:`Field` instances and model instances all
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
    constraint. Because we have not specified a primary key, Peewee will
    automatically add an auto-incrementing integer primary key field named
    *id*.

.. seealso::
   :ref:`pwiz` can generate model definitions for existing databases.

.. _fields:

Fields
------

The :class:`Field` class is used to describe the mapping of :class:`Model`
attributes to database columns. Each field type has a corresponding SQL storage
class (varchar, int, etc), and conversion between python data types and
underlying storage is handled transparently.

When creating a :class:`Model` class, fields are defined as class attributes:

.. code-block:: python

   class User(Model):
       username = CharField()
       join_date = DateTimeField()
       about_me = TextField()

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

Field initialization
^^^^^^^^^^^^^^^^^^^^

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

Special parameters
^^^^^^^^^^^^^^^^^^

+-----------------------------+------------------------------------------------+
| Field type                  | Special Parameters                             |
+=============================+================================================+
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
| :class:`ForeignKeyField`    | ``model``, ``field``, ``backref``,             |
|                             | ``on_delete``, ``on_update``, ``deferrable``   |
|                             | ``lazy_load``                                  |
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

In some instances it may make sense for the default value to be dynamic. A
common scenario is using the current date and time. Peewee allows you to
specify a **callable** in these cases, whose return value will be used when the
object is created.

.. code-block:: python

   class Message(Model):
       context = TextField()
       timestamp = DateTimeField(default=datetime.datetime.now)

.. note::
   If you are using a field that accepts a mutable type (``list``, ``dict``,
   etc), and would like to provide a default, it is a good idea to wrap your
   default value in a simple function so that multiple model instances are not
   sharing a reference to the same underlying object:

   .. code-block:: python

      def house_defaults():
          return {'beds': 0, 'baths': 0}

      class House(Model):
          number = TextField()
          street = TextField()
          attributes = JSONField(default=house_defaults)

The database can also provide the default value for a field. While Peewee does
not explicitly provide an API for setting a server-side default value, you can
use the ``constraints`` and :func:`Default` to specify the server default:

.. code-block:: python

   class Message(Model):
       content = TextField()
       timestamp = DateTimeField(constraints=[Default('CURRENT_TIMESTAMP')])

.. note::
   **Remember:** when using the ``default`` parameter, the values are set by
   Peewee rather than being a part of the actual table and column definition.

ForeignKeyField
---------------

:class:`ForeignKeyField` is a special field type that allows one model to
reference another. Typically a foreign key will reference the primary key of
the related model, but you can specify a particular column by specifying
``field=``.

Foreign keys allow data to be `normalized <http://en.wikipedia.org/wiki/Database_normalization>`_.
In our example models, there is a foreign key from ``Tweet`` to ``User``. This
means that all the users are stored in one table, tweets in another. The
foreign key from tweet to user allows each tweet to *point* to a particular
user object.

.. seealso::
   Refer to the :ref:`relationships` document for an in-depth discussion of
   foreign keys, joins and relationships between models.

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

.. note::
   SQLite does not have a native date type, so dates are stored in formatted
   text columns. To ensure that comparisons work correctly, the dates need to
   be formatted so they are sorted lexicographically. That is why they are
   stored, by default, as ``YYYY-MM-DD HH:MM:SS``.

.. _model-options:

Model settings
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

======================  ====================================================== ====================
Option                  Meaning                                                Inheritable?
======================  ====================================================== ====================
``database``            database for model                                     yes
``table_name``          name of the table to store data                        no
``table_function``      function to generate table name dynamically            yes
``indexes``             a list of fields to index                              yes
``primary_key``         a :class:`CompositeKey` instance                       yes
``constraints``         a list of table constraints                            yes
``schema``              the database schema for the model                      yes
``only_save_dirty``     when calling model.save(), only save dirty fields      yes
``options``             dictionary of options for create table extensions      yes
``table_settings``      list of setting strings to go after close parentheses  yes
``temporary``           indicate temporary table                               yes
``legacy_table_names``  use legacy table name generation (enabled by default)  yes
``depends_on``          indicate this table depends on another for creation    no
``without_rowid``       indicate table should not have rowid (SQLite only)     no
``strict_tables``       indicate strict data-types (SQLite only, 3.37+)        yes
======================  ====================================================== ====================

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

Primary Key
^^^^^^^^^^^

The ``Meta.primary_key`` attribute is used to specify either a
:class:`CompositeKey` or to indicate that the model has *no* primary key.
Composite primary keys are discussed in more detail here: :ref:`composite-key`.

To indicate that a model should have NO primary key, then set ``primary_key = False``.

Examples:

.. code-block:: python
   :emphasize-lines: 7, 13

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
your model class. To explicitly specify the table name for a model class, use
the ``Meta.table_name`` setting. This can be useful when dealing with
pre-existing database schemas that have used awkward naming conventions:

.. code-block:: python

   class UserProfile(Model):
       class Meta:
           table_name = 'user_profile_tbl'

Automatically generated table-names depend on the value of ``Meta.legacy_table_names``.
By default, ``legacy_table_names=True`` so as to avoid breaking backwards-compatibility.
However, if you wish to use the new and improved table-name generation, specify
``legacy_table_names=False`` in your BaseModel class.

This table shows the ways Peewee generates table names:

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

.. note::
   To preserve backwards-compatibility, the current release (Peewee 3 and 4)
   specify ``legacy_table_names=True`` by default.

If you wish to implement your own naming convention, you can specify the
``table_function`` Meta option. This function will be called with your model
class and should return the desired table name as a string. Suppose all table
names should be lower-cased and end with "_tbl":

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

Primary Keys, Composite Keys and other Tricks
---------------------------------------------

The :class:`AutoField` is used to identify an auto-incrementing integer primary
key. If a primary key is not specified, Peewee will automatically create an
auto-incrementing primary key named ``id``.

To specify an auto-incrementing primary key using a different field name:

.. code-block:: python

   class Event(Model):
       event_id = AutoField()  # Event.event_id will be auto-incrementing PK.
       name = CharField()
       timestamp = DateTimeField(default=datetime.datetime.now)
       metadata = BlobField()

You can identify a different field as the primary key, in which case an ``id``
column will not be created. In this example we will use a person's email
address as the primary key:

.. code-block:: python

   class Person(Model):
       email = CharField(primary_key=True)
       name = TextField()
       dob = DateField()

.. warning::
   The following is NOT an auto-incrementing integer primary key:

   .. code-block:: python

      class MyModel(Model):
          id = IntegerField(primary_key=True)

   Peewee understands the above model declaration as a model with an integer
   primary key, but the value of that ID is determined by the application. To
   create an auto-incrementing integer primary key, you would instead write:

   .. code-block:: python

      class MyModel(Model):
          id = AutoField()  # primary_key=True is implied.

Composite primary keys can be declared using :class:`CompositeKey`. Note
that doing this may cause issues with :class:`ForeignKeyField`, as Peewee
does not support the concept of a "composite foreign-key".

**Recommendation**: only use composite primary keys in trivial many-to-many
junction tables:

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

Non-integer primary keys
^^^^^^^^^^^^^^^^^^^^^^^^

If you would like use a non-integer primary key specify ``primary_key=True``
when declaring the field. When you wish to create a new instance for a model
using a non-autoincrementing primary key, ensure calls to :meth:`~Model.save`
specify ``force_insert=True``.

.. code-block:: python

   from peewee import *

   class UUIDModel(Model):
       id = UUIDField(primary_key=True)

Auto-incrementing IDs are, as their name says, automatically generated for you
when you insert a new row into the database. When you call
:meth:`~Model.save`, peewee determines whether to do an *INSERT* versus an
*UPDATE* based on the presence of a primary key value.

With the uuid example, the database won't generate a new ID, we need to specify
it manually. When calling ``save()`` for the first time, specify
``force_insert=True``:

.. code-block:: python

   # This works because .create() will specify `force_insert=True`.
   obj1 = UUIDModel.create(id=uuid.uuid4())

   # This will not work, however. Peewee will attempt to do an update:
   obj2 = UUIDModel(id=uuid.uuid4())
   obj2.save()  # WRONG.

   obj2.save(force_insert=True)  # CORRECT.

   # Once the object has been INSERTed, save() works as expected.
   obj2.save()

.. note::
   Foreign keys to a model with a non-integer primary key will automatically
   use the same underlying storage type as the primary key they relate to.

.. _composite-key:

Composite primary keys
^^^^^^^^^^^^^^^^^^^^^^

Peewee has very basic support for composite keys.  In order to use a composite
key, you must set the ``primary_key`` attribute of the model options to a
:class:`CompositeKey` instance:

.. code-block:: python

   class BlogToTag(Model):
       """A simple "through" table for many-to-many relationship."""
       blog = ForeignKeyField(Blog)
       tag = ForeignKeyField(Tag)

       class Meta:
           primary_key = CompositeKey('blog', 'tag')

.. warning::
   Peewee does not support foreign-keys to models that define a
   :class:`CompositeKey` primary key. If you wish to add a foreign-key to a
   model that has a composite primary key, replicate the columns on the
   related model and add a custom accessor (e.g. a property).

Table constraints
^^^^^^^^^^^^^^^^^

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
