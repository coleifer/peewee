.. _models:

Model and Fields
================

Also of possible interest:

* :ref:`Models API reference <model-api>`
* :ref:`Fields API reference <fields-api>`

Models
------

Models and their fields map directly to database tables and columns.  Consider
the following:

.. _blog-models:

.. code-block:: python

    from peewee import *

    db = SqliteDatabase('test.db')

    # create a base model class that our application's models will extend
    class BaseModel(Model):
        class Meta:
            database = db

    class User(BaseModel):
        username = CharField()

    class Tweet(BaseModel):
        user = ForeignKeyField(User, related_name='tweets')
        message = TextField()
        created_date = DateTimeField(default=datetime.datetime.now)
        is_published = BooleanField(default=True)


This is a typical example of how to specify models with peewee.  There are several
things going on:

1. Create an instance of a :py:class:`Database`

    .. code-block:: python

        db = SqliteDatabase('test.db')

    This establishes an object, ``db``, which is used by the models to connect to and
    query the database.

2. Create a base model class which specifies our database

    .. code-block:: python

        class BaseModel(Model):
            class Meta:
                database = db

    Model configuration is kept namespaced in a special class called ``Meta`` -- this
    convention is borrowed from Django.  ``Meta`` configuration
    is passed on to subclasses, so our project's models will all subclass ``BaseModel``.

3. Create a model

    .. code-block:: python

        class User(BaseModel):
            username = CharField()

    Model definition is pretty similar to django or sqlalchemy -- you subclass :py:class:`Model`
    and add :py:class:`Field` instances as class attributes.

    Models provide methods for creating/reading/updating/deleting rows in the
    database.


Creating tables
---------------

In order to start using these models, its necessary to open a connection to the
database and create the tables first:

.. code-block:: python

    # connect to our database
    db.connect()

    # create the tables
    User.create_table()
    Tweet.create_table()

.. note::
    Strictly speaking, it is not necessary to call :py:meth:`~Database.connect` but
    it is good practice to be explicit.  That way if something goes wrong, the error
    occurs at the connect step, rather than some arbitrary time later.


Model instances
---------------

Creating models in the interactive interpreter is a snap.

You can use the :py:meth:`Model.create` classmethod:

    .. code-block:: python

        >>> user = User.create(username='charlie')
        >>> tweet = Tweet.create(
        ...     message='http://www.youtube.com/watch?v=xdhLQCYQ-nQ',
        ...     user=user
        ... )

        >>> tweet.user.username
        'charlie'

Or you can build up the instance programmatically:

    .. code-block:: python

        >>> user = User()
        >>> user.username = 'charlie'
        >>> user.save()


Traversing foriegn keys
^^^^^^^^^^^^^^^^^^^^^^^

As you can see from above, the foreign key from ``Tweet`` to ``User`` can be
traversed automatically:

.. code-block:: python

    >>> tweet.user.username
    'charlie'

The reverse is also true, we can iterate a ``User`` objects associated ``Tweets``:

.. code-block:: python

    >>> for tweet in user.tweets:
    ...     print tweet.message
    ...
    http://www.youtube.com/watch?v=xdhLQCYQ-nQ

Under the hood, the ``tweets`` attribute is just a :py:class:`SelectQuery` with
the where clause prepopulated to point at the right ``User`` instance:

.. code-block:: python

    >>> user.tweets
    <peewee.SelectQuery object at 0x151f510>


Model options and table metadata
--------------------------------

In order not to pollute the model namespace, model-specific configuration is
placed in a special class called ``Meta``, which is a convention borrowed from
the django framework:

.. code-block:: python

    from peewee import *

    contacts_db = SqliteDatabase('contacts.db')

    class Person(Model):
        name = CharField()

        class Meta:
            database = contacts_db


This instructs peewee that whenever a query is executed on ``Person`` to use
the contacts database.

.. note::
    Take a look at :ref:`the sample models <blog-models>` - you will notice that
    we created a ``BaseModel`` that defined the database, and then extended.  This
    is the preferred way to define a database and create models.

There are several options you can specify as ``Meta`` attributes:

===================   ==============================================   ============
Option                Meaning                                          Inheritable?
===================   ==============================================   ============
``database``          database for model                               yes
``db_table``          name of the table to store data                  no
``indexes``           a list of fields to index                        yes
``order_by``          a list of fields to use for default ordering     yes
===================   ==============================================   ============


Specifying indexes for a model
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Indexes are stored in a nested tuple.  Each index is a 2-tuple, the first part
of which is another tuple of the names of the fields, the second part a boolean
indicating whether the index should be unique.

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

You can specify a default ordering for your models.  It is simply a tuple of
field names. If a field should be ordered descending, prefix it with a dash ("-").

.. code-block:: python

    class Tweet(Model):
        message = TextField()
        created = DateTimeField()

        class Meta:
            # order by created date descending
            order_by = ('-created',)

.. note:: This can be overridden at any time by calling :py:meth:`SelectQuery.order_by`.


Inheriting model metadata
^^^^^^^^^^^^^^^^^^^^^^^^^

Some options are "inheritable" (see table above), which means that you can define a
database on one model, then subclass that model and the child models will use
the same database.

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

The :py:class:`Field` class is used to describe the mapping of :py:class:`Model`
attributes to database columns.  Each field type has a corresponding SQL storage
class (i.e. varchar, int), and conversion between python data types and underlying
storage is handled transparently.

When creating a :py:class:`Model` class, fields are defined as class-level attributes.
This should look familiar to users of the django framework.  Here's an example:

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


Field types table
-----------------

Parameters accepted by all field types and their default values:

* ``null = False`` -- boolean indicating whether null values are allowed to be stored
* ``index = False`` -- boolean indicating whether to create an index on this column
* ``unique = False`` -- boolean indicating whether to create a unique index on this column
* ``verbose_name = None`` -- string representing the "user-friendly" name of this field
* ``help_text = None`` -- string representing any helpful text for this field
* ``db_column = None`` -- string representing the underlying column to use if different, useful for legacy databases
* ``default = None`` -- any value to use as a default for uninitialized models
* ``choices = None`` -- an optional iterable containing 2-tuples of ``value``, ``display``
* ``primary_key = False`` -- whether this field is the primary key for the table
* ``sequence = None`` -- sequence to populate field (if backend supports it)


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
===================   =================   =================   =================

Some fields take special parameters...
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

+-------------------------------+----------------------------------------------+
| Field type                    | Special Parameters                           |
+===============================+==============================================+
| :py:class:`CharField`         | ``max_length``                               |
+-------------------------------+----------------------------------------------+
| :py:class:`DateTimeField`     | ``formats``                                  |
+-------------------------------+----------------------------------------------+
| :py:class:`DateField`         | ``formats``                                  |
+-------------------------------+----------------------------------------------+
| :py:class:`TimeField`         | ``formats``                                  |
+-------------------------------+----------------------------------------------+
| :py:class:`DecimalField`      | ``max_digits``, ``decimal_places``,          |
|                               | ``auto_round``, ``rounding``                 |
+-------------------------------+----------------------------------------------+
| :py:class:`ForeignKeyField`   | ``rel_model``, ``related_name``,             |
|                               | ``cascade``, ``extra``                       |
+-------------------------------+----------------------------------------------+


A note on validation
^^^^^^^^^^^^^^^^^^^^

Both ``default`` and ``choices`` could be implemented at the database level as
``DEFAULT`` and ``CHECK CONSTRAINT`` respectively, but any application change would
require a schema change.  Because of this, ``default`` is implemented purely in
python and ``choices`` are not validated but exist for metadata purposes only.


Self-referential Foreign Keys
-----------------------------

Since the class is not available at the time the field is declared,
when creating a self-referential foreign key pass in 'self' as the "to"
relation:

.. code-block:: python

    class Category(Model):
        name = CharField()
        parent = ForeignKeyField('self', related_name='children', null=True)


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

    for course in Course.select().join(StudentCourse).join(Student).where(Student.name == 'da vinci'):
        print course.name

To efficiently iterate over a many-to-many relation, i.e., list all students
and their respective courses, we will query the "through" model ``StudentCourse``
and "precompute" the Student and Course:

.. code-block:: python

    query = StudentCourse.select(
        StudentCourse, Student, Course)
    ).join(Course).switch(StudentCourse).join(Student)

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
