.. _models:

Model and Fields
================

This document describes how to work with database models. For the full API documentation, see:

* :ref:`Models API reference <model-api>`
* :ref:`Fields API reference <fields-api>`

Models
------

:py:class:`Model` classes and their associated :py:class:`Field` instances provide a direct mapping to database tables and columns. Model instances correspond to rows in the database table, and their attributes are the column values for the given row.

The following code shows the typical way you will define your database connection and model classes.

.. _blog-models:

.. include:: includes/user_tweet_with_db

1. Create an instance of a :py:class:`Database`.

    .. code-block:: python

        db = SqliteDatabase('my_app.db')

    The ``db`` object will be used to manage the connections to the Sqlite database. In this example we're using :py:class:`SqliteDatabase`, but you could also use one of the other :ref:`database engines <database_cookbook>`_.

2. Create a base model class which specifies our database.

    .. code-block:: python

        class BaseModel(Model):
            class Meta:
                database = db

    It is good practice to define a base model class which establishes the database connection. This makes your code DRY as you will not have to specify the database for subsequent models.

    Model configuration is kept namespaced in a special class called ``Meta``. This convention is borrowed from Django.  ``Meta`` configuration is passed on to subclasses, so our project's models will all subclass ``BaseModel``. There are :ref:`many different attributes <model-options>` you can configure using *Model.Meta*.

3. Define a model class.

    .. code-block:: python

        class User(BaseModel):
            username = CharField(unique=True)

    Model definition uses the declarative style seen in other popular ORMs like SQLAlchemy or Django. Note that we are extending the *BaseModel* class so the *User* model will inherit the database connection.

    We have explicitly defined a single *username* column with a unique constraint. Because we have not specified a primary key, peewee will automatically add an auto-incrementing integer primary key field named *id*.

.. note::
    If you would like to start using peewee with an existing database, you can use :ref:`pwiz` to automatically generate model definitions.

Creating tables
---------------

In order to start using these models, its necessary to open a connection to the database and create the tables first. Peewee will run the necessary *CREATE TABLE* queries, additionally creating any constraints and indexes.

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

Model instances
---------------

.. include:: includes/crud

Traversing foriegn keys
^^^^^^^^^^^^^^^^^^^^^^^

Referring back to the :ref:`User and Tweet models <blog-models>`, note that there is a :py:class:`ForeignKeyField` from *Tweet* to *User*. The foreign key can be traversed, allowing you access to the associated user instance:

.. code-block:: pycon

    >>> tweet.user.username
    'charlie'

.. note::
    Unless the *User* model was explicitly selected when retrieving the *Tweet*, an additional query will be required to load the *User* data. To learn how to avoid the extra query, see the :ref:`N+1 query documentation <nplusone>`.

The reverse is also true, and we can iterate over the tweets associated with a given *User* instance:

.. code-block:: python

    >>> for tweet in user.tweets:
    ...     print tweet.message
    ...
    http://www.youtube.com/watch?v=xdhLQCYQ-nQ

Under the hood, the *tweets* attribute is just a :py:class:`SelectQuery` with the *WHERE* clause pre-populated to point to the given *User* instance:

.. code-block:: python

    >>> user.tweets
    <class 'twx.Tweet'> SELECT t1."id", t1."user_id", t1."message", ...

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
    AttributeError: type object 'Preson' has no attribute 'Meta'

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

.. _model-options:

There are several options you can specify as ``Meta`` attributes. While most options are inheritable, some are table-specific and will not be inherited by subclasses.

===================   ==============================================   ============
Option                Meaning                                          Inheritable?
===================   ==============================================   ============
``database``          database for model                               yes
``db_table``          name of the table to store data                  no
``indexes``           a list of fields to index                        yes
``order_by``          a list of fields to use for default ordering     yes
``primary_key``       a :py:class:`CompositeKey` instance              yes
``table_alias``       an alias to use for the table in queries         no
===================   ==============================================   ============

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

.. _model_indexes:

Specifying indexes for a model
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Peewee can create indexes on single or multiple columns, optionally including a *UNIQUE* constraint.

Single column indexes are defined using field initialization parameters. The following example adds a unique index on the *username* field, and a normal index on the *email* field:

.. code-block:: python

    class User(Model):
        username = CharField(unique=True)
        email = CharField(index=True)

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

Specifying a default ordering
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can specify a default sort-order for your models. It is simply a tuple of field names. If a field should be ordered descending, prefix it with a dash ("-").

.. code-block:: python

    class Tweet(Model):
        message = TextField()
        created = DateTimeField()

        class Meta:
            # order by created date descending
            order_by = ('-created',)

.. note:: This can be overridden at any time by calling :py:meth:`SelectQuery.order_by`.

This feature is provided for users familiar with the Django framework and, while it may seem convenient, I would caution against using this as it can sometimes lead to subtle bugs.

Inheriting model metadata
^^^^^^^^^^^^^^^^^^^^^^^^^

Some options are *inheritable* (see :ref:`model options table <model-options>`), which means that you can define a database on one model, then subclass that model and the child models will use the same database.

.. code-block:: python

    my_db = PostgresqlDatabase('my_db')

    class BaseModel(Model):
        class Meta:
            database = my_db

    class SomeModel(BaseModel):
        field1 = CharField()

        class Meta:
            order_by = ('field1',)
            # no need to define database again since it will be inherited from
            # the BaseModel

.. _fields:

Fields
------

The :py:class:`Field` class is used to describe the mapping of :py:class:`Model` attributes to database columns. Each field type has a corresponding SQL storage class (i.e. varchar, int), and conversion between python data types and underlying storage is handled transparently.

When creating a :py:class:`Model` class, fields are defined as class-level attributes. This should look familiar to users of the django framework. Here's an example:

.. code-block:: python

    from peewee import *

    class User(Model):
        username = CharField()
        join_date = DateTimeField()
        about_me = TextField()

There is one special type of field, :py:class:`ForeignKeyField`, which allows you
to expose foreign-key relationships between models in an intuitive way:

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


Field initialization arguments
------------------------------

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


Field types table
-----------------

===================   =================   =================   =================
Field Type            Sqlite              Postgresql          MySQL
===================   =================   =================   =================
``CharField``         varchar             varchar             varchar
``TextField``         text                text                longtext
``DateTimeField``     datetime            timestamp           datetime
``IntegerField``      integer             integer             integer
``BooleanField``      smallint            boolean             bool
``FloatField``        real                real                real
``DoubleField``       real                double precision    double precision
``BigIntegerField``   integer             bigint              bigint
``DecimalField``      decimal             numeric             numeric
``PrimaryKeyField``   integer             serial              integer
``ForeignKeyField``   integer             integer             integer
``DateField``         date                date                date
``TimeField``         time                time                time
``BlobField``         blob                bytea               blob
``UUIDField``         not supported       uuid                not supported
===================   =================   =================   =================

Some fields take special parameters...
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

+--------------------------------+------------------------------------------------+
| Field type                     | Special Parameters                             |
+================================+================================================+
| :py:class:`CharField`          | ``max_length``                                 |
+--------------------------------+------------------------------------------------+
| :py:class:`DateTimeField`      | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`DateField`          | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`TimeField`          | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`DecimalField`       | ``max_digits``, ``decimal_places``,            |
|                                | ``auto_round``, ``rounding``                   |
+--------------------------------+------------------------------------------------+
| :py:class:`ForeignKeyField`    | ``rel_model``, ``related_name``, ``to_field``, |
|                                | ``on_delete``, ``on_update``, ``extra``        |
+--------------------------------+------------------------------------------------+


A note on validation
^^^^^^^^^^^^^^^^^^^^

Both ``default`` and ``choices`` could be implemented at the database level as
``DEFAULT`` and ``CHECK CONSTRAINT`` respectively, but any application change would
require a schema change.  Because of this, ``default`` is implemented purely in
python and ``choices`` are not validated but exist for metadata purposes only.

To add database (server-side) constraints, use the ``constraints`` parameter.


Self-referential Foreign Keys
-----------------------------

Since the class is not available at the time the field is declared,
when creating a self-referential foreign key pass in 'self' as the "to"
relation:

.. code-block:: python

    class Category(Model):
        name = CharField()
        parent = ForeignKeyField('self', related_name='children', null=True)

.. _manytomany:

Implementing Many to Many
-------------------------

Peewee does not provide a "field" for many to many relationships the way that
django does -- this is because the "field" really is hiding an intermediary
table.  To implement many-to-many with peewee, you will therefore create the
intermediary table yourself and query through it:

.. code-block:: python

    class Student(Model):
        name = CharField()

    class Course(Model):
        name = CharField()

    class StudentCourse(Model):
        student = ForeignKeyField(Student)
        course = ForeignKeyField(Course)

To query, let's say we want to find students who are enrolled in math class:

.. code-block:: python

    for student in Student.select().join(StudentCourse).join(Course).where(Course.name == 'math'):
        print student.name

To query what classes a given student is enrolled in:

.. code-block:: python

    courses = (Course
        .select()
        .join(StudentCourse)
        .join(Student)
        .where(Student.name == 'da vinci'))

    for course in courses:
        print course.name

To efficiently iterate over a many-to-many relation, i.e., list all students
and their respective courses, we will query the "through" model ``StudentCourse``
and "precompute" the Student and Course:

.. code-block:: python

    query = (StudentCourse
        .select(StudentCourse, Student, Course)
        .join(Course)
        .switch(StudentCourse)
        .join(Student)
        .order_by(Student.name))

To print a list of students and their courses you might do the following:

.. code-block:: python

    last = None
    for student_course in query:
        student = student_course.student
        if student != last:
            last = student
            print 'Student: %s' % student.name
        print '    - %s' % student_course.course.name

Since we selected all fields from ``Student`` and ``Course`` in the ``select``
clause of the query, these foreign key traversals are "free" and we've done the
whole iteration with just 1 query.


.. _non_int_pks:

Non-integer Primary Keys
------------------------

First of all, let me say that I do not think using non-integer primary keys is a
good idea.  The cost in storage is higher, the index lookups will be slower, and
foreign key joins will be more expensive.  That being said, here is how you can
use non-integer pks in peewee.

.. code-block:: python

    from peewee import Model, PrimaryKeyField, VarCharColumn

    class UUIDModel(Model):
        # explicitly declare a primary key field, and specify the class to use
        id = CharField(primary_key=True)


Auto-increment IDs are, as their name says, automatically generated for you when
you insert a new row into the database.  The way peewee determines whether to
do an ``INSERT`` versus an ``UPDATE`` comes down to checking whether the primary
key value is ``None``.  If ``None``, it will do an insert, otherwise it does an
update on the existing value.  Since, with our uuid example, the database driver
won't generate a new ID, we need to specify it manually.  When we call save()
for the first time, pass in ``force_insert = True``:

.. code-block:: python

    inst = UUIDModel(id=str(uuid.uuid4()))
    inst.save() # <-- WRONG!!  this will try to do an update

    inst.save(force_insert=True) # <-- CORRECT

    # to update the instance after it has been saved once
    inst.save()

.. note::
    Any foreign keys to a model with a non-integer primary key will have the
    ``ForeignKeyField`` use the same underlying storage type as the primary key
    they are related to.


DateTimeField, DateField and TimeField
--------------------------------------

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

These properties can be used just like any other expression.  Let's say we have
an events calendar and want to hi-lite all the days in the current month that
have an event attached:

.. code-block:: python

    # Get the current time.
    now = datetime.datetime.now()

    # Get days that have events for the current month.
    Event.select(Event.event_date.day.alias('day')).where(
        (Event.event_date.year == now.year) &
        (Event.event_date.month == now.month))


.. _custom-fields:

Creating a custom field
-----------------------

It isn't too difficult to add support for custom field types in peewee. Let's add
a UUID field for postgresql (which has a native UUID column type). This code is
contained in the ``playhouse.postgres_ext`` module, for reference.

To add a custom field type you need to first identify what type of column the field
data will be stored in.  If you just want to add "python" behavior atop, say, a
decimal field (for instance to make a currency field) you would just subclass
:py:class:`DecimalField`.  On the other hand, if the database offers a custom
column type you will need to let peewee know.  This is controlled by the :py:attr:`Field.db_field`
attribute.

Let's start by defining our UUID field:

.. code-block:: python

    class UUIDField(Field):
        db_field = 'uuid'


We will store the UUIDs in a native UUID column.  Since psycopg2 treats the data as
a string by default, we will add two methods to the field to handle:

* the data coming out of the database to be used in our application
* the data from our python app going into the database

.. code-block:: python

    import uuid

    class UUIDField(Field):
        db_field = 'uuid'

        def db_value(self, value):
            return str(value) # convert UUID to str

        def python_value(self, value):
            return uuid.UUID(value) # convert str to UUID

Now, we need to let the database know how to map this "uuid" label to an actual "uuid"
column type in the database.  There are 2 ways of doing this:

1. Specify the overrides in the :py:class:`Database` constructor:

  .. code-block:: python

      db = PostgresqlDatabase('my_db', fields={'uuid': 'uuid'})

2. Register them class-wide using :py:meth:`Database.register_fields`:

  .. code-block:: python

      # will affect all instances of PostgresqlDatabase
      PostgresqlDatabase.register_fields({'uuid': 'uuid'})


That is it!  Some fields may support exotic operations, like the postgresql HStore field
acts like a key/value store and has custom operators for things like "contains" and
"update".  You can specify "op overrides" as well.  For more information, check out
the source code for the :py:class:`HStoreField`, in ``playhouse.postgres_ext``.
