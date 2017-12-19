.. _models:

Models
======

:py:class:`Model` classes, :py:class:`Field` instances and model instances all
map to familiar database concepts:

=================== =====================================
Thing               Corresponds to...
=================== =====================================
Model class         Database table
Field instance      Column on a table
Model instance      Row in a database
=================== =====================================

The following code shows the typical way you will define your database
connection and model classes:

.. code-block:: python

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


Breaking down the above code, let's look at each part in detail.

1. Create an instance of a :py:class:`Database`.

    .. code-block:: python

        db = SqliteDatabase('my_app.db')

    The ``db`` object will be used to manage the connections to the Sqlite
    database. In this example we're using :py:class:`SqliteDatabase`, but you
    could also use one of the other database engines.

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


Creating tables and indexes
---------------------------

To create the table, indexes and constraints for a given model, you can use the
:py:meth:`~Model.create_table` classmethod:

.. code-block:: python

    User.create_table()

When models have foreign-key dependencies, it is important to ensure that
models are created in the proper order. To create table(s) and automatically
resolve the dependency order, you can use :py:class:`Database.create_tables`:

.. code-block:: python

    db.create_tables([User, Tweet])

To drop a table, you can use the :py:meth:`~Model.drop_table` classmethod:

.. code-block:: python

    User.drop_table()

Similarly, to drop multiple tables in the proper order, you can use
:py:class:`Database.drop_tables`:

.. code-block:: python

    db.drop_tables([User, Tweet])

SchemaManager
^^^^^^^^^^^^^

The :py:class:`Model` embeds a :py:class:`SchemaManager` instance, accessible
at ``ModelClass._schema``, which provides
