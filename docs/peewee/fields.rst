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

* ``null = False``
* ``db_index = False``
* ``unique = False``
* ``verbose_name = None``
* ``help_text = None``

+-------------------------------+--------------------------------+-------------------------------+
| Field type                    | Underlying storage             | Special Parameters            |
+===============================+================================+===============================+
| :py:class:`CharField`         | ``varchar``                    | ``max_length``                |
+-------------------------------+--------------------------------+-------------------------------+
| :py:class:`TextField`         | * ``text``, sqlite, psql       | none                          |
|                               | * ``longtext``, mysql          |                               |
+-------------------------------+--------------------------------+-------------------------------+
| :py:class:`DateTimeField`     | * ``datetime``, sqlite         | none                          |
|                               | * ``datetime``, mysql          |                               |
|                               | * ``timestamp``, psql          |                               |
+-------------------------------+--------------------------------+-------------------------------+
| :py:class:`IntegerField`      | ``integer``                    | none                          |
+-------------------------------+--------------------------------+-------------------------------+
| :py:class:`BooleanField`      | * ``smallint``, sqlite, psql   | none                          |
|                               | * ``bool``, mysql              |                               |
+-------------------------------+--------------------------------+-------------------------------+
| :py:class:`FloatField`        | * ``real``, sqlite, psql       | none                          |
|                               | * ``double precision``, mysql  |                               |
+-------------------------------+--------------------------------+-------------------------------+
| :py:class:`PrimaryKeyField`   | * ``integer``, sqlite          | none                          |
|                               | * ``serial``, psql             |                               |
|                               | * ``integer auto_increment``,  |                               |
|                               |   mysql                        |                               |
+-------------------------------+--------------------------------+-------------------------------+
| :py:class:`ForeignKeyField`   | ``integer``                    | ``to``, ``related_name``,     |
|                               |                                | ``cascade``, ``extra``        |
+-------------------------------+--------------------------------+-------------------------------+


Self-referential Foreign Keys
-----------------------------

Since the class is not available at the time the field is declared,
when creating a self-referential foreign key pass in 'self' as the "to"
relation:

.. code-block:: python

    class Category(Model):
        name = CharField()
        parent = ForeignKeyField('self', related_name='children', null=True)


Field class API
---------------

.. py:class:: Field

    The base class from which all other field types extend.
    
    .. py:method:: __init__(null=False, db_index=False, unique=False, verbose_name=None, help_text=None, *args, **kwargs)
    
        :param null: this column can accept ``None`` or ``NULL`` values
        :param db_index: create an index for this column when creating the table
        :param unique: create a unique index for this column when creating the table
        :param verbose_name: specify a "verbose name" for this field, useful for metadata purposes
        :param help_text: specify some instruction text for the usage/meaning of this field
    
    .. py:method:: db_value(value)
    
        :param value: python data type to prep for storage in the database
        :rtype: converted python datatype
    
    .. py:method:: python_value(value)
    
        :param value: data coming from the backend storage
        :rtype: python data type
    
    .. py:method:: lookup_value(lookup_type, value)
    
        :param lookup_type: a peewee lookup type, such as 'eq' or 'contains'
        :param value: a python data type
        :rtype: data type converted for use when querying

.. py:class:: CharField

    Stores: small strings (0-255 bytes)

.. py:class:: TextField

    Stores: arbitrarily large strings
    
.. py:class:: DateTimeField

    Stores: python ``datetime`` instances

.. py:class:: IntegerField

    Stores: integers

.. py:class:: BooleanField

    Stores: ``True`` / ``False``

.. py:class:: FloatField

    Stores: floating-point numbers

.. py:class:: PrimaryKeyField

    Stores: auto-incrementing integer fields suitable for use as primary key

.. py:class:: ForeignKeyField

    Stores: relationship to another model
    
    .. py:method:: __init__(to[, related_name=None[, ...]])
    
        :param to: related :py:class:`Model` class or the string 'self' if declaring
                   a self-referential foreign key
        :param related_name: attribute to expose on related model
        
        .. code-block:: python
        
            class Blog(Model):
                name = CharField()
            
            class Entry(Model):
                blog = ForeignKeyField(Blog, related_name='entries')
                title = CharField()
                content = TextField()
            
            # "blog" attribute
            >>> some_entry.blog
            <Blog: My Awesome Blog>
            
            # "entries" related name attribute
            >>> for entry in my_awesome_blog.entries:
            ...     print entry.title
            Some entry
            Another entry
            Yet another entry
