Model API (smells like django)
==============================

Models and their fields map directly to database tables and columns.  Consider 
the following::

    class Blog(peewee.Model):
        name = peewee.CharField() # <-- VARCHAR
    
    
    class Entry(peewee.Model):
        headline = peewee.CharField()
        content = peewee.TextField() # <-- TEXT
        pub_date = peewee.DateTimeField() # <-- DATETIME
        blog = peewee.ForeignKeyField() # <-- INTEGER referencing the Blog table


Creating tables
---------------

In order to start using these models, its necessary to open a connection to the
database and create the tables first::

    >>> import peewee
    >>> peewee.database.connect() # <-- opens connection to the default db, `peewee.db`
    >>> Blog.create_table()
    >>> Entry.create_table()


Model instances
---------------

Assuming you've created the tables and connected to the database, you are now 
free to create models and execute queries.

Creating models from the command-line is a snap::

    >>> blog = Blog.create(name='Funny pictures of animals blog')
    >>> cat_entry = Entry.create(
    ...     headline='maru the kitty',
    ...     content='http://www.youtube.com/watch?v=xdhLQCYQ-nQ',
    ...     pub_date=datetime.datetime.now(),
    ...     blog=blog
    ... )
    >>> entry.blog
    <__main__.Blog object at 0x151f4d0>
    >>> entry.blog.name
    'Funny pictures of animals blog'

As you can see from above, the foreign key from ``Entry`` to ``Blog`` can be
traversed automatically.  The reverse is also true::

    >>> for entry in blog.entry_set:
    ...     print entry.headline
    ... 
    maru the kitty

Under the hood, the ``entry_set`` attribute is just a ``SelectQuery``::

    >>> blog.entry_set
    <peewee.SelectQuery object at 0x151f510>
    >>> blog.entry_set.sql()
    ('SELECT * FROM entry WHERE blog_id = ?', [1])


Model options
-------------

In order not to pollute the model namespace, model-specific configuration is
placed in a special class called ``Meta``::

    import peewee
    
    custom_db = peewee.Database(peewee.SqliteAdapter(), 'custom.db')
    
    class CustomModel(peewee.Model):
        ... fields ...
        
        class Meta:
            database = custom_db


This instructs peewee that whenever a query is executed on CustomModel to use
the custom database.  Like the default database, a connection to ``custom_db``
must be created before any queries can be executed.


Model methods
-------------

.. py:method:: save(self)

    save the given instance, creating or updating depending on whether it has a
    primary key.
    
    example::
    
        >>> some_obj.title = 'new title' # <-- does not touch the database
        >>> some_obj.save() # <-- change is persisted to the db

.. py:method:: create(cls, **attributes)

    create an instance of ``cls`` with the given attributes set.
    
    :param attributes: key/value pairs of model attributes
    
    example::
        
        >>> user = User.create(username='admin', password='test')

.. py:method:: filter(self, *args, **kwargs)

    :param args: a list of ``Q`` or ``Node`` objects
    :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"

    provides a django-like syntax for building a query.
    The key difference between ``filter`` and ``where`` is that ``filter``
    supports traversing joins using django's "double-underscore" syntax::
    
        >>> sq = Entry.filter(blog__title='Some Blog')
    
    This method is chainable::
    
        >>> base_q = User.filter(active=True)
        >>> some_user = base_q.filter(username='charlie')

.. py:method:: get(self, *args, **kwargs)

    :param args: a list of ``Q`` or ``Node`` objects
    :param kwargs: a mapping of column + lookup to value, e.g. "age__gt=55"

    get a single row from the database that matches the given query.  raises a
    ``<model-class>.DoesNotExist`` if no rows are returned::
    
        >>> active = User.select().where(active=True)
        >>> try:
        ...     user = active.get(username=username, password=password)
        ... except User.DoesNotExist:
        ...     user = None
    
    this method is also expose via the model api::
    
        >>> user = User.get(username=username, password=password)

.. py:method:: get_or_create(cls, **attributes)

    get the instance of ``cls`` with the given attributes set.  if the instance
    does not exist it will be created.
    
    :param attributes: key/value pairs of model attributes
    
    example::
    
        >>> CachedObj.get_or_create(key=key, val=some_val)

.. py:method:: select(cls, query=None)

    create a SelectQuery for the given ``cls``
    
    example::
    
        >>> User.select().where(active=True).order_by('username')

.. py:method:: update(cls, **query)

    create an UpdateQuery for the given ``cls``
    
    example::
    
        >>> q = User.update(active=False).where(registration_expired=True)
        >>> q.sql()
        ('UPDATE user SET active=? WHERE registration_expired = ?', [0, 1])
        >>> q.execute() # <-- execute it

.. py:method:: delete(cls, **query)

    create an DeleteQuery for the given ``cls``
    
    example::
    
        >>> q = User.delete().where(active=False)
        >>> q.sql()
        ('DELETE FROM user WHERE active = ?', [0])
        >>> q.execute() # <-- execute it

.. py:method:: insert(cls, **query)

    create an InsertQuery for the given ``cls``
    
    example::
    
        >>> q = User.insert(username='admin', active=True, registration_expired=False)
        >>> q.sql()
        ('INSERT INTO user (username,active,registration_expired) VALUES (?,?,?)', ['admin', 1, 0])
        >>> q.execute()
        1

.. py:method:: create_table(cls, fail_silently=False)

    create the table for the given model.
    
    example::
    
        >>> database.connect()
        >>> SomeModel.create_table() # <-- creates the table for SomeModel

.. py:method:: drop_table(cls, fail_silently=False)

    drops the table for the given model.  will fail if the table does not exist.
