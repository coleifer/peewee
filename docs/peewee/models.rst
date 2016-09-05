.. _models:

Models and Fields
=================

:py:class:`Model` classes, :py:class:`Field` instances and model instances all map to database concepts:

================= =================================
Thing             Corresponds to...
================= =================================
Model class       Database table
Field instance    Column on a table
Model instance    Row in a database table
================= =================================

The following code shows the typical way you will define your database connection and model classes.

.. _blog-models:

.. code-block:: python

    from peewee import *

    db = SqliteDatabase('my_app.db')

    class BaseModel(Model):
        class Meta:
            database = db

    class User(BaseModel):
        username = CharField(unique=True)

    class Tweet(BaseModel):
        user = ForeignKeyField(User, related_name='tweets')
        message = TextField()
        created_date = DateTimeField(default=datetime.datetime.now)
        is_published = BooleanField(default=True)

1. Create an instance of a :py:class:`Database`.

    .. code-block:: python

        db = SqliteDatabase('my_app.db')

    The ``db`` object will be used to manage the connections to the Sqlite database. In this example we're using :py:class:`SqliteDatabase`, but you could also use one of the other :ref:`database engines <databases>`.

2. Create a base model class which specifies our database.

    .. code-block:: python

        class BaseModel(Model):
            class Meta:
                database = db

    It is good practice to define a base model class which establishes the database connection. This makes your code DRY as you will not have to specify the database for subsequent models.

    Model configuration is kept namespaced in a special class called ``Meta``. This convention is borrowed from Django. :ref:`Meta <model-options>` configuration is passed on to subclasses, so our project's models will all subclass *BaseModel*. There are :ref:`many different attributes <model-options>` you can configure using *Model.Meta*.

3. Define a model class.

    .. code-block:: python

        class User(BaseModel):
            username = CharField(unique=True)

    Model definition uses the declarative style seen in other popular ORMs like SQLAlchemy or Django. Note that we are extending the *BaseModel* class so the *User* model will inherit the database connection.

    We have explicitly defined a single *username* column with a unique constraint. Because we have not specified a primary key, peewee will automatically add an auto-incrementing integer primary key field named *id*.

.. note::
    If you would like to start using peewee with an existing database, you can use :ref:`pwiz` to automatically generate model definitions.

.. _fields:

Fields
------

The :py:class:`Field` class is used to describe the mapping of :py:class:`Model` attributes to database columns. Each field type has a corresponding SQL storage class (i.e. varchar, int), and conversion between python data types and underlying storage is handled transparently.

When creating a :py:class:`Model` class, fields are defined as class attributes. This should look familiar to users of the django framework. Here's an example:

.. code-block:: python

    class User(Model):
        username = CharField()
        join_date = DateTimeField()
        about_me = TextField()

There is one special type of field, :py:class:`ForeignKeyField`, which allows you
to represent foreign-key relationships between models in an intuitive way:

.. code-block:: python

    class Message(Model):
        user = ForeignKeyField(User, related_name='messages')
        body = TextField()
        send_date = DateTimeField()

This allows you to write code like the following:

.. code-block:: python

    >>> print some_message.user.username
    Some User

    >>> for message in some_user.messages:
    ...     print message.body
    some message
    another message
    yet another message

For full documentation on fields, see the :ref:`Fields API notes <fields-api>`

.. _field_types_table:

Field types table
^^^^^^^^^^^^^^^^^

=====================   =================   =================   =================
Field Type              Sqlite              Postgresql          MySQL
=====================   =================   =================   =================
``CharField``           varchar             varchar             varchar
``FixedCharField``      char                char                char
``TextField``           text                text                longtext
``DateTimeField``       datetime            timestamp           datetime
``IntegerField``        integer             integer             integer
``BooleanField``        integer             boolean             bool
``FloatField``          real                real                real
``DoubleField``         real                double precision    double precision
``BigIntegerField``     integer             bigint              bigint
``SmallIntegerField``   integer             smallint            smallint
``DecimalField``        decimal             numeric             numeric
``PrimaryKeyField``     integer             serial              integer
``ForeignKeyField``     integer             integer             integer
``DateField``           date                date                date
``TimeField``           time                time                time
``TimestampField``      integer             integer             integer
``BlobField``           blob                bytea               blob
``UUIDField``           text                uuid                varchar(40)
``BareField``           untyped             not supported       not supported
=====================   =================   =================   =================

.. note::
    Don't see the field you're looking for in the above table? It's easy to create custom field types and use them with your models.

    * :ref:`custom-fields`
    * :py:class:`Database`, particularly the ``fields`` parameter.

Field initialization arguments
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Parameters accepted by all field types and their default values:

* ``null = False`` -- boolean indicating whether null values are allowed to be stored
* ``index = False`` -- boolean indicating whether to create an index on this column
* ``unique = False`` -- boolean indicating whether to create a unique index on this column. See also :ref:`adding composite indexes <model_indexes>`.
* ``verbose_name = None`` -- string representing the "user-friendly" name of this field
* ``help_text = None`` -- string representing any helpful text for this field
* ``db_column = None`` -- string representing the underlying column to use if different, useful for legacy databases
* ``default = None`` -- any value to use as a default for uninitialized models
* ``choices = None`` -- an optional iterable containing 2-tuples of ``value``, ``display``
* ``primary_key = False`` -- whether this field is the primary key for the table
* ``sequence = None`` -- sequence to populate field (if backend supports it)
* ``constraints = None`` - a list of one or more constraints, e.g. ``[Check('price > 0')]``
* ``schema = None`` -- optional name of the schema to use, if your db supports this.

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
| :py:class:`ForeignKeyField`    | ``rel_model``, ``related_name``, ``to_field``, |
|                                | ``on_delete``, ``on_update``, ``extra``        |
+--------------------------------+------------------------------------------------+
| :py:class:`BareField`          | ``coerce``                                     |
+--------------------------------+------------------------------------------------+

.. note::
    Both ``default`` and ``choices`` could be implemented at the database level as *DEFAULT* and *CHECK CONSTRAINT* respectively, but any application change would require a schema change. Because of this, ``default`` is implemented purely in python and ``choices`` are not validated but exist for metadata purposes only.

    To add database (server-side) constraints, use the ``constraints`` parameter.

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

:py:class:`ForeignKeyField` is a special field type that allows one model to reference another. Typically a foreign key will contain the primary key of the model it relates to (but you can specify a particular column by specifying a ``to_field``).

Foreign keys allow data to be `normalized <http://en.wikipedia.org/wiki/Database_normalization>`_. In our example models, there is a foreign key from ``Tweet`` to ``User``. This means that all the users are stored in their own table, as are the tweets, and the foreign key from tweet to user allows each tweet to *point* to a particular user object.

In peewee, accessing the value of a :py:class:`ForeignKeyField` will return the entire related object, e.g.:

.. code-block:: python

    tweets = Tweet.select(Tweet, User).join(User).order_by(Tweet.create_date.desc())
    for tweet in tweets:
        print(tweet.user.username, tweet.message)

In the example above the ``User`` data was selected as part of the query. For more examples of this technique, see the :ref:`Avoiding N+1 <nplusone>` document.

If we did not select the ``User``, though, then an additional query would be issued to fetch the associated ``User`` data:

.. code-block:: python

    tweets = Tweet.select().order_by(Tweet.create_date.desc())
    for tweet in tweets:
        # WARNING: an additional query will be issued for EACH tweet
        # to fetch the associated User data.
        print(tweet.user.username, tweet.message)

Sometimes you only need the associated primary key value from the foreign key column. In this case, Peewee follows the convention established by Django, of allowing you to access the raw foreign key value by appending ``"_id"`` to the foreign key field's name:

.. code-block:: python

    tweets = Tweet.select()
    for tweet in tweets:
        # Instead of "tweet.user", we will just get the raw ID value stored
        # in the column.
        print(tweet.user_id, tweet.message)

:py:class:`ForeignKeyField` allows for a backreferencing property to be bound to the target model. Implicitly, this property will be named `classname_set`, where `classname` is the lowercase name of the class, but can be overridden via the parameter ``related_name``:

.. code-block:: python

    class Message(Model):
        from_user = ForeignKeyField(User)
        to_user = ForeignKeyField(User, related_name='received_messages')
        text = TextField()

    for message in some_user.message_set:
        # We are iterating over all Messages whose from_user is some_user.
        print message

    for message in some_user.received_messages:
        # We are iterating over all Messages whose to_user is some_user
        print message


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
    SQLite does not have a native date type, so dates are stored in formatted text columns. To ensure that comparisons work correctly, the dates need to be formatted so they are sorted lexicographically. That is why they are stored, by default, as ``YYYY-MM-DD HH:MM:SS``.

BareField
^^^^^^^^^

The :py:class:`BareField` class is intended to be used only with SQLite. Since SQLite uses dynamic typing and data-types are not enforced, it can be perfectly fine to declare fields without *any* data-type. In those cases you can use :py:class:`BareField`. It is also common for SQLite virtual tables to use meta-columns or untyped columns, so for those cases as well you may wish to use an untyped field.

:py:class:`BareField` accepts a special parameter ``coerce``. This parameter is a function that takes a value coming from the database and converts it into the appropriate Python type. For instance, if you have a virtual table with an un-typed column but you know that it will return ``int`` objects, you can specify ``coerce=int``.

.. _custom-fields:

Creating a custom field
^^^^^^^^^^^^^^^^^^^^^^^

It isn't too difficult to add support for custom field types in peewee. In this example we will create a UUID field for postgresql (which has a native UUID column type).

To add a custom field type you need to first identify what type of column the field data will be stored in. If you just want to add python behavior atop, say, a decimal field (for instance to make a currency field) you would just subclass :py:class:`DecimalField`. On the other hand, if the database offers a custom column type you will need to let peewee know. This is controlled by the :py:attr:`Field.db_field` attribute.

Let's start by defining our UUID field:

.. code-block:: python

    class UUIDField(Field):
        db_field = 'uuid'

We will store the UUIDs in a native UUID column. Since psycopg2 treats the data as a string by default, we will add two methods to the field to handle:

* The data coming out of the database to be used in our application
* The data from our python app going into the database

.. code-block:: python

    import uuid

    class UUIDField(Field):
        db_field = 'uuid'

        def db_value(self, value):
            return str(value) # convert UUID to str

        def python_value(self, value):
            return uuid.UUID(value) # convert str to UUID

Now, we need to let the database know how to map this *uuid* label to an actual *uuid* column type in the database. There are 2 ways of doing this:

1. Specify the overrides in the :py:class:`Database` constructor:

  .. code-block:: python

      db = PostgresqlDatabase('my_db', fields={'uuid': 'uuid'})

2. Register them class-wide using :py:meth:`Database.register_fields`:

  .. code-block:: python

      # Will affect all instances of PostgresqlDatabase
      PostgresqlDatabase.register_fields({'uuid': 'uuid'})

That is it! Some fields may support exotic operations, like the postgresql HStore field acts like a key/value store and has custom operators for things like *contains* and *update*. You can specify :ref:`custom operations <custom-operators>` as well. For example code, check out the source code for the :py:class:`HStoreField`, in ``playhouse.postgres_ext``.

Creating model tables
---------------------

In order to start using our models, its necessary to open a connection to the database and create the tables first. Peewee will run the necessary *CREATE TABLE* queries, additionally creating any constraints and indexes.

.. code-block:: python

    # Connect to our database.
    db.connect()

    # Create the tables.
    db.create_tables([User, Tweet])

.. note::
    Strictly speaking, it is not necessary to call :py:meth:`~Database.connect` but it is good practice to be explicit. That way if something goes wrong, the error occurs at the connect step, rather than some arbitrary time later.

.. note::
    Peewee can determine if your tables already exist, and conditionally create them:

    .. code-block:: python

        # Only create the tables if they do not exist.
        db.create_tables([User, Tweet], safe=True)

After you have created your tables, if you choose to modify your database schema (by adding, removing or otherwise changing the columns) you will need to either:

* Drop the table and re-create it.
* Run one or more *ALTER TABLE* queries. Peewee comes with a schema migration tool which can greatly simplify this. Check the :ref:`schema migrations <migrate>` docs for details.

.. _model-options:

Model options and table metadata
--------------------------------

In order not to pollute the model namespace, model-specific configuration is placed in a special class called *Meta* (a convention borrowed from the django framework):

.. code-block:: python

    from peewee import *

    contacts_db = SqliteDatabase('contacts.db')

    class Person(Model):
        name = CharField()

        class Meta:
            database = contacts_db

This instructs peewee that whenever a query is executed on *Person* to use the contacts database.

.. note::
    Take a look at :ref:`the sample models <blog-models>` - you will notice that we created a ``BaseModel`` that defined the database, and then extended. This is the preferred way to define a database and create models.

Once the class is defined, you should not access ``ModelClass.Meta``, but instead use ``ModelClass._meta``:

.. code-block:: pycon

    >>> Person.Meta
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    AttributeError: type object 'Person' has no attribute 'Meta'

    >>> Person._meta
    <peewee.ModelOptions object at 0x7f51a2f03790>

The :py:class:`ModelOptions` class implements several methods which may be of use for retrieving model metadata (such as lists of fields, foreign key relationships, and more).

.. code-block:: pycon

    >>> Person._meta.fields
    {'id': <peewee.PrimaryKeyField object at 0x7f51a2e92750>, 'name': <peewee.CharField object at 0x7f51a2f0a510>}

    >>> Person._meta.primary_key
    <peewee.PrimaryKeyField object at 0x7f51a2e92750>

    >>> Person._meta.database
    <peewee.SqliteDatabase object at 0x7f519bff6dd0>

There are several options you can specify as ``Meta`` attributes. While most options are inheritable, some are table-specific and will not be inherited by subclasses.

=====================   ====================================================== ============
Option                  Meaning                                                Inheritable?
=====================   ====================================================== ============
``database``            database for model                                     yes
``db_table``            name of the table to store data                        no
``db_table_func``       function that accepts model and returns a table name   yes
``indexes``             a list of fields to index                              yes
``order_by``            a list of fields to use for default ordering           yes
``primary_key``         a :py:class:`CompositeKey` instance                    yes
``table_alias``         an alias to use for the table in queries               no
``schema``              the database schema for the model                      yes
``constraints``         a list of table constraints                            yes
``validate_backrefs``   ensure backrefs do not conflict with other attributes. yes
``only_save_dirty``     when calling model.save(), only save dirty fields      yes
=====================   ====================================================== ============

Here is an example showing inheritable versus non-inheritable attributes:

.. code-block:: pycon

    >>> db = SqliteDatabase(':memory:')
    >>> class ModelOne(Model):
    ...     class Meta:
    ...         database = db
    ...         db_table = 'model_one_tbl'
    ...
    >>> class ModelTwo(ModelOne):
    ...     pass
    ...
    >>> ModelOne._meta.database is ModelTwo._meta.database
    True
    >>> ModelOne._meta.db_table == ModelTwo._meta.db_table
    False

Meta.order_by
^^^^^^^^^^^^^

Specifying a default ordering is, in my opinion, a bad idea. It's better to be explicit in your code when you want to sort your results.

That said, to specify a default ordering, the syntax is similar to that of Django. ``Meta.order_by`` is a tuple of field names, and to indicate descending ordering, the field name is prefixed by a ``'-'``.

.. code-block:: python

    class Person(Model):
        first_name = CharField()
        last_name = CharField()
        dob = DateField()

        class Meta:
            # Order people by last name, first name. If two people have the
            # same first and last, order them youngest to oldest.
            order_by = ('last_name', 'first_name', '-dob')

Meta.primary_key
^^^^^^^^^^^^^^^^

The ``Meta.primary_key`` attribute is used to specify either a :py:class:`CompositeKey` or to indicate that the model has *no* primary key. Composite primary keys are discussed in more detail here: :ref:`composite-key`.

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

.. _model_indexes:

Indexes and Constraints
-----------------------

Peewee can create indexes on single or multiple columns, optionally including a *UNIQUE* constraint. Peewee also supports user-defined constraints on both models and fields.

Single-column indexes and constraints
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Single column indexes are defined using field initialization parameters. The following example adds a unique index on the *username* field, and a normal index on the *email* field:

.. code-block:: python

    class User(Model):
        username = CharField(unique=True)
        email = CharField(index=True)

To add a user-defined constraint on a column, you can pass it in using the ``constraints`` parameter. You may wish to specify a default value as part of the schema, or add a ``CHECK`` constraint, for example:

.. code-block:: python

    class Product(Model):
        name = CharField(unique=True)
        price = DecimalField(constraints=[Check('price < 10000')])
        created = DateTimeField(
            constraints=[SQL("DEFAULT (datetime('now'))")])

Multi-column indexes
^^^^^^^^^^^^^^^^^^^^

Multi-column indexes are defined as *Meta* attributes using a nested tuple. Each database index is a 2-tuple, the first part of which is a tuple of the names of the fields, the second part a boolean indicating whether the index should be unique.

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

Table constraints
^^^^^^^^^^^^^^^^^

Peewee allows you to add arbitrary constraints to your :py:class:`Model`, that will be part of the table definition when the schema is created.

For instance, suppose you have a *people* table with a composite primary key of two columns, the person's first and last name. You wish to have another table relate to the *people* table, and to do this, you will need to define a foreign key constraint:

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

Non-integer Primary Keys, Composite Keys and other Tricks
---------------------------------------------------------

Non-integer primary keys
^^^^^^^^^^^^^^^^^^^^^^^^

If you would like use a non-integer primary key (which I generally don't recommend), you can specify ``primary_key=True`` when creating a field. When you wish to create a new instance for a model using a non-autoincrementing primary key, you need to be sure you :py:meth:`~Model.save` specifying ``force_insert=True``.

.. code-block:: python

    from peewee import *

    class UUIDModel(Model):
        id = UUIDField(primary_key=True)

Auto-incrementing IDs are, as their name says, automatically generated for you when you insert a new row into the database. When you call :py:meth:`~Model.save`, peewee determines whether to do an *INSERT* versus an *UPDATE* based on the presence of a primary key value. Since, with our uuid example, the database driver won't generate a new ID, we need to specify it manually. When we call save() for the first time, pass in ``force_insert = True``:

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
    Any foreign keys to a model with a non-integer primary key will have a ``ForeignKeyField`` use the same underlying storage type as the primary key they are related to.

.. _composite-key:

Composite primary keys
^^^^^^^^^^^^^^^^^^^^^^

Peewee has very basic support for composite keys.  In order to use a composite key, you must set the ``primary_key`` attribute of the model options to a :py:class:`CompositeKey` instance:

.. code-block:: python

    class BlogToTag(Model):
        """A simple "through" table for many-to-many relationship."""
        blog = ForeignKeyField(Blog)
        tag = ForeignKeyField(Tag)

        class Meta:
            primary_key = CompositeKey('blog', 'tag')

Manually specifying primary keys
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes you do not want the database to automatically generate a value for the primary key, for instance when bulk loading relational data. To handle this on a *one-off* basis, you can simply tell peewee to turn off ``auto_increment`` during the import:

.. code-block:: python

    data = load_user_csv() # load up a bunch of data

    User._meta.auto_increment = False # turn off auto incrementing IDs
    with db.transaction():
        for row in data:
            u = User(id=row[0], username=row[1])
            u.save(force_insert=True) # <-- force peewee to insert row

    User._meta.auto_increment = True

If you *always* want to have control over the primary key, simply do not use the :py:class:`PrimaryKeyField` field type, but use a normal :py:class:`IntegerField` (or other column type):

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

If you wish to create a model with no primary key, you can specify ``primary_key = False`` in the inner ``Meta`` class:

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
    Some model APIs may not work correctly for models without a primary key, for instance :py:meth:`~Model.save` and `~Model.delete_instance` (you can instead use `~Model.insert`, `~Model.update` and `~Model.delete`).

Self-referential foreign keys
-----------------------------

When creating a heirarchical structure it is necessary to create a self-referential foreign key which links a child object to its parent.  Because the model class is not defined at the time you instantiate the self-referential foreign key, use the special string ``'self'`` to indicate a self-referential foreign key:

.. code-block:: python

    class Category(Model):
        name = CharField()
        parent = ForeignKeyField('self', null=True, related_name='children')

As you can see, the foreign key points *upward* to the parent object and the back-reference is named *children*.

.. attention:: Self-referential foreign-keys should always be ``null=True``.

When querying against a model that contains a self-referential foreign key you may sometimes need to perform a self-join. In those cases you can use :py:meth:`Model.alias` to create a table reference. Here is how you might query the category and parent model using a self-join:

.. code-block:: python

    Parent = Category.alias()
    GrandParent = Category.alias()
    query = (Category
             .select(Category, Parent)
             .join(Parent, on=(Category.parent == Parent.id))
             .join(GrandParent, on=(Parent.parent == GrandParent.id))
             .where(GrandParent.name == 'some category')
             .order_by(Category.name))

Circular foreign key dependencies
---------------------------------

Sometimes it happens that you will create a circular dependency between two tables.

.. note::
  My personal opinion is that circular foreign keys are a code smell and should be refactored (by adding an intermediary table, for instance).

Adding circular foreign keys with peewee is a bit tricky because at the time you are defining either foreign key, the model it points to will not have been defined yet, causing a ``NameError``.

.. code-block:: python

    class User(Model):
        username = CharField()
        favorite_tweet = ForeignKeyField(Tweet, null=True)  # NameError!!

    class Tweet(Model):
        message = TextField()
        user = ForeignKeyField(User, related_name='tweets')

One option is to simply use an :py:class:`IntegerField` to store the raw ID:

.. code-block:: python

    class User(Model):
        username = CharField()
        favorite_tweet_id = IntegerField(null=True)

By using :py:class:`DeferredRelation` we can get around the problem and still use a foreign key field:

.. code-block:: python

    # Create a reference object to stand in for our as-yet-undefined Tweet model.
    DeferredTweet = DeferredRelation()

    class User(Model):
        username = CharField()
        # Tweet has not been defined yet so use the deferred reference.
        favorite_tweet = ForeignKeyField(DeferredTweet, null=True)

    class Tweet(Model):
        message = TextField()
        user = ForeignKeyField(User, related_name='tweets')

    # Now that Tweet is defined, we can initialize the reference.
    DeferredTweet.set_model(Tweet)

After initializing the deferred relation, the foreign key fields are now correctly set up. There is one more quirk to watch out for, though. When you call :py:class:`~Model.create_table` we will again encounter the same issue. For this reason peewee will not automatically create a foreign key constraint for any *deferred* foreign keys.

Here is how to create the tables:

.. code-block:: python

    # Foreign key constraint from User -> Tweet will NOT be created because the
    # Tweet table does not exist yet. `favorite_tweet` will just be a regular
    # integer field:
    User.create_table()

    # Foreign key constraint from Tweet -> User will be created normally.
    Tweet.create_table()

    # Now that both tables exist, we can create the foreign key from User -> Tweet:
    # NOTE: this will not work in SQLite!
    db.create_foreign_key(User, User.favorite_tweet)

.. warning::
    SQLite does not support adding constraints to existing tables through the ``ALTER TABLE`` statement.
