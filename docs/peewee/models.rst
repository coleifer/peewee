.. _models:

Model API (smells like django)
==============================

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

    
    class Blog(BaseModel):
        name = peewee.CharField() # <-- VARCHAR
    
    
    class Entry(BaseModel):
        headline = peewee.CharField()
        content = peewee.TextField() # <-- TEXT
        pub_date = peewee.DateTimeField() # <-- DATETIME
        blog = peewee.ForeignKeyField() # <-- INTEGER referencing the Blog table


This is a typical example of how to specify models with peewee.  There are several
things going on:

1. Create an instance of a :py:class:`Database`

    .. code-block:: python

        db = SqliteDatabase('test.db')

    This establishes an object, ``db``, which is used by the models to connect to and
    query the database.  There can be multiple database instances per application, but,
    as I hope is obvious, :py:class:`ForeignKeyField` related models must be on the same
    database.

2. Create a base model class which specifies our database

    .. code-block:: python

        class BaseModel(Model):
            class Meta:
                database = db

    Model configuration is kept namespaced in a special class called ``Meta`` -- this
    convention is borrowed from Django, which does the same thing.  ``Meta`` configuration
    is passed on to subclasses, so this code basically allows all our project's models
    to connect to our database.

3. Declare a model or two

    .. code-block:: python

        class Blog(BaseModel):
            name = peewee.CharField()

    Model definition is pretty similar to django or sqlalchemy -- you basically define
    a class which represents a single table in the database, then its attributes (which
    are subclasses of :py:class:`Field`) represent columns.
    
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
    Blog.create_table()
    Entry.create_table()

.. note::
    Strictly speaking, the explicit call to :py:meth:`~Database.connect` is not
    necessary, but it is good practice to be explicit about when you are opening
    and closing connections.


Model instances
---------------

Assuming you've created the tables and connected to the database, you are now 
free to create models and execute queries.

Creating models in the interactive interpreter is a snap.

1. Use the :py:meth:`Model.create` classmethod:

    .. code-block:: python

        >>> blog = Blog.create(name='Funny pictures of animals blog')
        >>> entry = Entry.create(
        ...     headline='maru the kitty',
        ...     content='http://www.youtube.com/watch?v=xdhLQCYQ-nQ',
        ...     pub_date=datetime.datetime.now(),
        ...     blog=blog
        ... )
    
        >>> entry.blog.name
        'Funny pictures of animals blog'

2. Build up the instance programmatically:

    .. code-block:: python
    
        >>> blog = Blog()
        >>> blog.name = 'Another sweet blog'
        >>> blog.save()

Traversing foriegn keys
^^^^^^^^^^^^^^^^^^^^^^^

As you can see from above, the foreign key from ``Entry`` to ``Blog`` can be
traversed automatically:

.. code-block:: python

    >>> entry.blog.name
    'Funny pictures of animals blog'

The reverse is also true, we can iterate a ``Blog`` objects associated ``Entries``:

.. code-block:: python

    >>> for entry in blog.entry_set:
    ...     print entry.headline
    ... 
    maru the kitty

Under the hood, the ``entry_set`` attribute is just a :py:class:`SelectQuery`:

.. code-block:: python

    >>> blog.entry_set
    <peewee.SelectQuery object at 0x151f510>
    
    >>> blog.entry_set.sql()
    ('SELECT * FROM entry WHERE blog_id = ?', [1])


Model options
-------------

In order not to pollute the model namespace, model-specific configuration is
placed in a special class called ``Meta``, which is a convention borrowed from
the django framework:

.. code-block:: python

    from peewee import *
    
    custom_db = SqliteDatabase('custom.db')
    
    class CustomModel(Model):
        class Meta:
            database = custom_db


This instructs peewee that whenever a query is executed on ``CustomModel`` to use
the custom database.

.. note::
    Take a look at :ref:`the sample models <blog-models>` - you will notice that
    we created a ``BaseModel`` that defined the database, and then extended.  This
    is the preferred way to define a database and create models.

There are several options you can specify as ``Meta`` attributes:

* database: specifies a :py:class:`Database` instance to use with this model
* db_table: the name of the database table this model maps to
* ordering: a sequence of columns to use as the default ordering for this model
* pk_sequence: name of sequence to create for the primary key (peewee will autogenerate one
    if not provided and the backend supports sequences).

Example of ordering:

.. code-block:: python

    class Entry(Model):
        title = CharField()
        body = TextField()
        created = DateTimeField()

        class Meta:
            # order by created date descending, then title ascending
            ordering = (('created', 'desc'), 'title')

.. note:: 
    These options are "inheritable", which means that you can define a database
    adapter on one model, then subclass that model and the child models will use
    that database.
    
    .. code-block:: python
    
        my_db = PostgresqlDatabase('my_db')
        
        class BaseModel(Model):
            class Meta:
                database = my_db
        
        class SomeModel(BaseModel):
            field1 = CharField()
            
            class Meta:
                ordering = ('field1',)
                # no need to define database again since it will be inherited from
                # the BaseModel


Model methods
-------------

.. py:class:: Model

    .. py:method:: save()

        Save the given instance, creating or updating depending on whether it has a
        primary key.
        
        example:
        
        .. code-block:: python
        
            >>> some_obj.title = 'new title' # <-- does not touch the database
            >>> some_obj.save() # <-- change is persisted to the db

    .. py:classmethod:: create(**attributes)

        :param attributes: key/value pairs of model attributes

        Create an instance of the ``Model`` with the given attributes set.
        
        example:
        
        .. code-block:: python
            
            >>> user = User.create(username='admin', password='test')

    .. py:method:: delete_instance()

        Delete the given instance

        example:

        .. code-block:: python
        
            >>> some_obj.delete_instance() # <-- it is gone forever

    .. py:classmethod:: filter(*args, **kwargs)

        :param args: a list of :py:class:`Q` or :py:class:`Node` objects
        :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"
        :rtype: :py:class:`SelectQuery` with appropriate ``WHERE`` clauses

        Provides a django-like syntax for building a query. The key difference
        between :py:meth:`~Model.filter` and :py:meth:`SelectQuery.where`
        is that :py:meth:`~Model.filter` supports traversing joins using
        django's "double-underscore" syntax:
        
        .. code-block:: python
        
            >>> sq = Entry.filter(blog__title='Some Blog')
        
        This method is chainable::
        
            >>> base_q = User.filter(active=True)
            >>> some_user = base_q.filter(username='charlie')

    .. py:classmethod:: get(*args, **kwargs)

        :param args: a list of :py:class:`Q` or :py:class:`Node` objects
        :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"
        :rtype: :py:class:`Model` instance or raises ``DoesNotExist`` exception

        Get a single row from the database that matches the given query.  Raises a
        ``<model-class>.DoesNotExist`` if no rows are returned:
        
        .. code-block:: python
        
            >>> user = User.get(username=username, password=password)
        
        This method is also expose via the :py:class:`SelectQuery`:
        
        .. code-block:: python
        
            >>> active = User.select().where(active=True)
            >>> try:
            ...     user = active.get(username=username, password=password)
            ... except User.DoesNotExist:
            ...     user = None

    .. py:classmethod:: get_or_create(**attributes)

        :param attributes: key/value pairs of model attributes
        :rtype: a :py:class:`Model` instance

        Get the instance with the given attributes set.  If the instance
        does not exist it will be created.
        
        example:
        
        .. code-block:: python
        
            >>> CachedObj.get_or_create(key=key, val=some_val)

    .. py:classmethod:: select(query=None)
    
        :rtype: a :py:class:`SelectQuery` for the given ``Model``
        
        example:
        
        .. code-block:: python
        
            >>> User.select().where(active=True).order_by('username')

    .. py:classmethod:: update(**query)

        :rtype: an :py:class:`UpdateQuery` for the given ``Model``
        
        example:
        
        .. code-block:: python
        
            >>> q = User.update(active=False).where(registration_expired=True)
            >>> q.sql()
            ('UPDATE user SET active=? WHERE registration_expired = ?', [0, 1])
            >>> q.execute() # <-- execute it

    .. py:classmethod:: delete(**query)

        :rtype: a :py:class:`DeleteQuery` for the given ``Model``
        
        example:
        
        .. code-block:: python
        
            >>> q = User.delete().where(active=False)
            >>> q.sql()
            ('DELETE FROM user WHERE active = ?', [0])
            >>> q.execute() # <-- execute it
        
        .. warning::
            Assume you have a model instance -- calling ``model_instance.delete()``
            does **not** delete it.

    .. py:classmethod:: insert(**query)

        :rtype: an :py:class:`InsertQuery` for the given ``Model``
        
        example:
        
        .. code-block:: python
        
            >>> q = User.insert(username='admin', active=True, registration_expired=False)
            >>> q.sql()
            ('INSERT INTO user (username,active,registration_expired) VALUES (?,?,?)', ['admin', 1, 0])
            >>> q.execute()
            1

    .. py:classmethod:: create_table([fail_silently=False])
    
        :param fail_silently: If set to ``True``, the method will check for the existence of the table
            before attempting to create.

        Create the table for the given model.
        
        example:
        
        .. code-block:: python
        
            >>> database.connect()
            >>> SomeModel.create_table() # <-- creates the table for SomeModel

    .. py:classmethod:: drop_table([fail_silently=False])
    
        :param fail_silently: If set to ``True``, the query will check for the existence of
            the table before attempting to remove.

        Drop the table for the given model.
        
        .. note::
            Cascading deletes are not handled by this method, nor is the removal
            of any constraints.
    
    .. py:classmethod:: table_exists()
    
        :rtype: Boolean whether the table for this model exists in the database
