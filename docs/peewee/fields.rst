.. _fields:

Fields
======

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


Field class API
---------------

.. py:class:: Field

    The base class from which all other field types extend.

    .. py:attribute:: db_field = '<some field type>'

        Attribute used to map this field to a column type, e.g. "string" or "datetime"

    .. py:attribute:: template = '%(column_type)s'

        A template for generating the SQL for this field

    .. py:method:: __init__(null=False, index=False, unique=False, verbose_name=None, help_text=None, db_column=None, default=None, choices=None, *args, **kwargs)

        :param null: this column can accept ``None`` or ``NULL`` values
        :param index: create an index for this column when creating the table
        :param unique: create a unique index for this column when creating the table
        :param verbose_name: specify a "verbose name" for this field, useful for metadata purposes
        :param help_text: specify some instruction text for the usage/meaning of this field
        :param db_column: column class to use for underlying storage
        :param default: a value to use as an uninitialized default
        :param choices: an iterable of 2-tuples mapping ``value`` to ``display``
        :param boolean primary_key: whether to use this as the primary key for the table
        :param sequence: name of sequence (if backend supports it)

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

.. py:class:: CharField

    Stores: small strings (0-255 bytes)

.. py:class:: TextField

    Stores: arbitrarily large strings

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

.. py:class:: IntegerField

    Stores: integers

.. py:class:: BooleanField

    Stores: ``True`` / ``False``

.. py:class:: FloatField

    Stores: floating-point numbers

.. py:class:: DecimalField

    Stores: decimal numbers

.. py:class:: PrimaryKeyField

    Stores: auto-incrementing integer fields suitable for use as primary key.

.. py:class:: ForeignKeyField

    Stores: relationship to another model

    .. py:method:: __init__(to[, related_name=None[, ...]])

        :param rel_model: related :py:class:`Model` class or the string 'self' if declaring
                   a self-referential foreign key
        :param related_name: attribute to expose on related model

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
