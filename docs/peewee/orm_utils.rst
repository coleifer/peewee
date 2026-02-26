.. _orm-utils:

ORM Utilities
=============

These modules provide higher-level abstractions on top of Peewee's core ORM
and work with any database backend.

.. contents:: On this page
   :local:
   :depth: 1


.. _shortcuts:

Shortcuts
---------

``playhouse.shortcuts`` provides helpers for serializing model instances to
and from dictionaries, resolving compound queries, and thread-safe database
swapping.

Model Serialization
^^^^^^^^^^^^^^^^^^^

.. module:: playhouse.shortcuts

.. function:: model_to_dict(model, recurse=True, backrefs=False, only=None, exclude=None, extra_attrs=None, fields_from_query=None, max_depth=None, manytomany=False)

   Convert a model instance to a dictionary.

   :param bool recurse: Follow foreign keys and include the related object
       as a nested dict (default: ``True``).
   :param bool backrefs: Follow back-references and include related
       collections as nested lists of dicts.
   :param only: A list or set of field instances to include exclusively.
   :param exclude: A list or set of field instances to exclude.
   :param extra_attrs: A list of attribute or method names to include in
       the output dict.
   :param Select fields_from_query: Restrict serialization to only the
       fields that were explicitly selected in the generating query.
   :param int max_depth: Maximum depth when following relations.
   :param bool manytomany: Include many-to-many fields.

   Examples:

   .. code-block:: python

       user = User.create(username='alice')
       model_to_dict(user)
       # {'id': 1, 'username': 'alice'}

       model_to_dict(user, backrefs=True)
       # {'id': 1, 'username': 'alice', 'tweets': []}

       t = Tweet.create(user=user, content='hello')
       model_to_dict(t)
       # {'id': 1, 'content': 'hello', 'user': {'id': 1, 'username': 'alice'}}

       model_to_dict(t, recurse=False)
       # {'id': 1, 'content': 'hello', 'user': 1}

       model_to_dict(user, backrefs=True)
       # {'id': 1, 'tweets': [{'id': 1, 'content': 'hello'}], 'username': 'alice'}

   .. note::
       If your use case is unusual, write a small custom function rather
       than trying to coerce ``model_to_dict`` with a complex combination
       of parameters.

.. function:: dict_to_model(model_class, data, ignore_unknown=False)

   Construct a model instance from a dictionary. Foreign keys may be
   provided as nested dicts; back-references as lists of dicts.

   :param Model model_class: The model class to construct.
   :param dict data: A dictionary of data. Foreign keys can be included as nested dictionaries, and back-references as lists of dictionaries.
   :param bool ignore_unknown: Allow keys that do not correspond to any
       field on the model.

   .. code-block:: python

       user = dict_to_model(User, {'id': 1, 'username': 'alice'})
       user.username   # 'alice'

       # Nested foreign key:
       tweet = dict_to_model(Tweet, {
           'id': 1, 'content': 'hi',
           'user': {'id': 1, 'username': 'alice'}})
       tweet.user.username   # 'alice'

.. function:: update_model_from_dict(instance, data, ignore_unknown=False)

   Update an existing model instance with values from a dictionary.
   Follows the same rules as :func:`dict_to_model`.

   :param Model instance: The model instance to update.
   :param dict data: A dictionary of data. Foreign keys can be included as nested dictionaries, and back-references as lists of dictionaries.
   :param bool ignore_unknown: Allow keys that do not correspond to any
       field on the model.


Compound Query Resolution
^^^^^^^^^^^^^^^^^^^^^^^^^

.. function:: resolve_multimodel_query(query, key='_model_identifier')

   Resolve rows from a compound ``UNION`` or similar query to the correct
   model class. Useful when two tables are unioned and you need each row
   as an instance of the appropriate model.

   :param query: A compound :class:`SelectQuery`.
   :param str key: Name of the column used to identify the model.
   :returns: An iterable that yields properly typed model instances.


Thread-Safe Database Swapping
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. class:: ThreadSafeDatabaseMetadata()

   Model :class:`Metadata` implementation that enables the ``database``
   attribute to safely changed in a multi-threaded application. Use this when
   your application may swap the active database (e.g. primary / read replica)
   at runtime across threads:

   .. code-block:: python

       from playhouse.shortcuts import ThreadSafeDatabaseMetadata

       primary  = PostgresqlDatabase('main')
       replica  = PostgresqlDatabase('replica')

       class BaseModel(Model):
           class Meta:
               database = primary
               model_metadata_class = ThreadSafeDatabaseMetadata

       # Safe to do at runtime from any thread:
       BaseModel._meta.database = replica


.. _hybrid:

.. module:: playhouse.hybrid

Hybrid Attributes
-----------------

A *hybrid attribute* behaves differently depending on whether it is accessed
on a model **instance** (executes Python logic) or on the model **class**
(generates a SQL expression). This lets you write Python methods that work
both as Python computations and as composable SQL clauses.

The concept is borrowed from SQLAlchemy's `hybrid extension <https://docs.sqlalchemy.org/en/14/orm/extensions/hybrid.html>`_.

.. code-block:: python

   from playhouse.hybrid import hybrid_property, hybrid_method

   class Interval(Model):
       start = IntegerField()
       end = IntegerField()

       @hybrid_property
       def length(self):
           return self.end - self.start

       @hybrid_method
       def contains(self, point):
           return (self.start <= point) & (point < self.end)

On an instance, Python arithmetic runs:

.. code-block:: python

   i = Interval(start=1, end=5)
   i.length  # 4 (Python arithmetic)
   i.contains(3)  # True (Python comparison)

On the class, SQL is generated:

.. code-block:: python

   Interval.select().where(Interval.length > 5)
   # WHERE ("end" - "start") > 5

   Interval.select().where(Interval.contains(2))
   # WHERE ("start" <= 2) AND (2 < "end")

When the Python and SQL implementations differ, provide a separate
``expression`` override:

.. code-block:: python

   class Interval(Model):
       start = IntegerField()
       end = IntegerField()

       @hybrid_property
       def radius(self):
           return abs(self.length) / 2  # Python: uses Python abs()

       @radius.expression
       def radius(cls):
           return fn.ABS(cls.length) / 2  # SQL: uses fn.ABS()

Example:

.. code-block:: python

   query = Interval.select().where(Interval.radius < 3)

This query is equivalent to the following SQL:

.. code-block:: sql

   SELECT "t1"."id", "t1"."start", "t1"."end"
   FROM "interval" AS t1
   WHERE ((abs("t1"."end" - "t1"."start") / 2) < 3)

.. class:: hybrid_property(fget, fset=None, fdel=None, expr=None)

   Decorator for defining a property with separate instance and class
   behaviors. Use ``@prop.expression`` to specify the SQL form when it
   differs from the Python form.

   Examples:

   .. code-block:: python

      class Interval(Model):
          start = IntegerField()
          end = IntegerField()

          @hybrid_property
          def length(self):
              return self.end - self.start

          @hybrid_property
          def radius(self):
              return abs(self.length) / 2

          @radius.expression
          def radius(cls):
              return fn.ABS(cls.length) / 2

   When accessed on an ``Interval`` instance, the ``length`` and ``radius``
   properties will behave as you would expect. When accessed as class
   attributes, though, a SQL expression will be generated instead:

   .. code-block:: python

      query = (Interval
               .select()
               .where(
                   (Interval.length > 6) &
                   (Interval.radius >= 3)))

   Would generate the following SQL:

   .. code-block:: sql

      SELECT "t1"."id", "t1"."start", "t1"."end"
      FROM "interval" AS t1
      WHERE (
          (("t1"."end" - "t1"."start") > 6) AND
          ((abs("t1"."end" - "t1"."start") / 2) >= 3)
      )

.. class:: hybrid_method(func, expr=None)

   Decorator for defining a method with separate instance and class
   behaviors. Use ``@method.expression`` to specify the SQL form.

   Example:

   .. code-block:: python

      class Interval(Model):
          start = IntegerField()
          end = IntegerField()

          @hybrid_method
          def contains(self, point):
              return (self.start <= point) & (point < self.end)

   When called with an ``Interval`` instance, the ``contains`` method will
   behave as you would expect. When called as a classmethod, though, a SQL
   expression will be generated:

   .. code-block:: python

      query = Interval.select().where(Interval.contains(2))

   Would generate the following SQL:

   .. code-block:: sql

      SELECT "t1"."id", "t1"."start", "t1"."end"
      FROM "interval" AS t1
      WHERE (("t1"."start" <= 2) AND (2 < "t1"."end"))


.. _kv:

.. module:: playhouse.kv

Key/Value Store
---------------

``playhouse.kv.KeyValue`` provides a persistent dictionary backed by a Peewee
database instance.


.. code-block:: python

   from playhouse.kv import KeyValue

   KV = KeyValue()   # Defaults to an in-memory SQLite database.

   KV['k1'] = 'v1'
   KV.update(k2='v2', k3='v3')

   assert KV['k2'] == 'v2'
   print(dict(KV))   # {'k1': 'v1', 'k2': 'v2', 'k3': 'v3'}

   # Expression-based access:
   for value in KV[KV.key > 'k1']:
       print(value)    # 'v2', 'v3'

   # Expression-based bulk update:
   KV[KV.key > 'k1'] = 'updated'

   # Expression-based deletion:
   del KV[KV.key > 'k1']

.. class:: KeyValue(key_field=None, value_field=None, ordered=False, database=None, table_name='keyvalue')

   :param Field key_field: Field for the key. Defaults to
       :class:`CharField`. Must specify ``primary_key=True``.
   :param Field value_field: Field for the value. Defaults to
       :class:`PickleField`.
   :param bool ordered: Return keys in sorted order when iterating.
   :param Database database: Database to use. Defaults to an in-memory
       SQLite database.
   :param str table_name: Name of the underlying table.

   The table is created automatically on construction if it does not exist.
   Supports the standard dictionary interface plus expression-based access.

   .. method:: __contains__(expr)

      :param expr: a single key or an expression
      :returns: Boolean whether key/expression exists.

      Example:

      .. code-block:: python

         kv = KeyValue()
         kv.update(k1='v1', k2='v2')

         'k1' in kv  # True

         'kx' in kv  # False

         (KV.key < 'k2') in KV  # True
         (KV.key > 'k2') in KV  # False

   .. method:: __len__()

      :returns: Count of items stored.

   .. method:: __getitem__(expr)

      :param expr: a single key or an expression.
      :returns: value(s) corresponding to key/expression.
      :raises: ``KeyError`` if single key given and not found.

      Examples:

      .. code-block:: python

         KV = KeyValue()
         KV.update(k1='v1', k2='v2', k3='v3')

         KV['k1']  # 'v1'
         KV['kx']  # KeyError: "kx" not found

         KV[KV.key > 'k1']  # ['v2', 'v3']
         KV[KV.key < 'k1']  # []

   .. method:: __setitem__(expr, value)

      :param expr: a single key or an expression.
      :param value: value to set for key(s)

      Set value for the given key. If ``expr`` is an expression, then any
      keys matching the expression will have their value updated.

      Example:

      .. code-block:: python

         KV = KeyValue()
         KV.update(k1='v1', k2='v2', k3='v3')

         KV['k1'] = 'v1-x'
         print(KV['k1'])  # 'v1-x'

         KV[KV.key >= 'k2'] = 'v99'
         print(dict(KV))  # {'k1': 'v1-x', 'k2': 'v99', 'k3': 'v99'}

   .. method:: __delitem__(expr)

      :param expr: a single key or an expression.

      Delete the given key. If an expression is given, delete all keys that
      match the expression.

      Example:

      .. code-block:: python

         KV = KeyValue()
         KV.update(k1=1, k2=2, k3=3)

         del KV['k1']  # Deletes "k1".
         del KV['k1']  # KeyError: "k1" does not exist

         del KV[KV.key > 'k2']  # Deletes "k3".
         del KV[KV.key > 'k99']  # Nothing deleted, no keys match.

   .. method:: keys()

      :returns: an iterable of all keys in the table.

   .. method:: values()

      :returns: an iterable of all values in the table.

   .. method:: items()

      :returns: an iterable of all key/value pairs in the table.

   .. method:: update(__data=None, **mapping)

      Efficiently bulk-insert or replace the given key/value pairs.

      Example:

      .. code-block:: python

         KV = KeyValue()
         KV.update(k1=1, k2=2)  # Sets 'k1'=1, 'k2'=2.

         print(dict(KV))  # {'k1': 1, 'k2': 2}

         KV.update(k2=22, k3=3)  # Updates 'k2'->22, sets 'k3'=3.

         print(dict(KV))  # {'k1': 1, 'k2': 22, 'k3': 3}

         KV.update({'k2': -2, 'k4': 4})  # Also can pass a dictionary.

         print(dict(KV))  # {'k1': 1, 'k2': -2, 'k3': 3, 'k4': 4}

   .. method:: get(expr, default=None)

      :param expr: a single key or an expression.
      :param default: default value if key not found.
      :returns: value of given key/expr or default if single key not found.

      Get the value at the given key. If the key does not exist, the default
      value is returned, unless the key is an expression in which case an
      empty list will be returned.

   .. method:: pop(expr, default=Sentinel)

      :param expr: a single key or an expression.
      :param default: default value if key does not exist.
      :returns: value of given key/expr or default if single key not found.

      Get value and delete the given key. If the key does not exist, the
      default value is returned, unless the key is an expression in which
      case an empty list is returned.

   .. method:: clear()

      Remove all items from the key-value table.


.. _signals:

.. module:: playhouse.signals

Signals
-------

``playhouse.signals`` adds Django-style model lifecycle signals. Models must
subclass ``playhouse.signals.Model`` (not ``peewee.Model``) for hooks to fire.

.. code-block:: python

   from playhouse.signals import Model, post_save

   class MyModel(Model):
       data = IntegerField()
       class Meta:
           database = db

   @post_save(sender=MyModel)
   def on_save(model_class, instance, created):
       if created:
           notify_new(instance)

The following signals are provided:

``pre_save``
    Called immediately before an object is saved to the database. Provides an
    additional keyword argument ``created``, indicating whether the model is being
    saved for the first time or updated.
``post_save``
    Called immediately after an object is saved to the database. Provides an
    additional keyword argument ``created``, indicating whether the model is being
    saved for the first time or updated.
``pre_delete``
    Called immediately before an object is deleted from the database when :meth:`Model.delete_instance`
    is used.
``post_delete``
    Called immediately after an object is deleted from the database when :meth:`Model.delete_instance`
    is used.
``pre_init``
    Called when a model class is first instantiated

.. warning::
   Signals fire only through the high-level instance methods
   (:meth:`~Model.save`, :meth:`~Model.delete_instance`). Bulk
   operations via :meth:`~Model.insert`, :meth:`~Model.update`, and
   :meth:`~Model.delete` do not trigger signals because no model instance
   is involved.

Connecting handlers
^^^^^^^^^^^^^^^^^^^

Whenever a signal is dispatched, it will call any handlers that have been
registered. This allows totally separate code to respond to events like model
save and delete.

The :class:`Signal` class provides a :meth:`~Signal.connect` method,
which takes a callback function and two optional parameters for "sender" and
"name". If specified, the "sender" parameter should be a single model class
and allows your callback to only receive signals from that one model class.
The "name" parameter is used as a convenient alias in the event you wish to
unregister your signal handler.

Example:

.. code-block:: python

   @post_save(sender=MyModel, name='project.cache_buster')
   def cache_bust(sender, instance, created):
       cache.delete(make_cache_key(instance))

Or connect manually:

.. code-block:: python

   def on_delete(sender, instance):
       audit_log(instance)

   pre_delete.connect(on_delete, sender=MyModel)

Disconnect by name or reference:

.. code-block:: python

   post_save.disconnect(name='project.cache_buster')
   pre_delete.disconnect(on_delete)

Signal callback signature:

- ``pre_init(sender, instance)``
- ``pre_save(sender, instance, created)``
- ``post_save(sender, instance, created)``
- ``pre_delete(sender, instance)``
- ``post_delete(sender, instance)``

.. class:: Signal()

   Stores a list of receivers (callbacks) and calls them when the "send"
   method is invoked.

   .. method:: connect(receiver, name=None, sender=None)

      :param callable receiver: a callable that takes at least two parameters,
          a "sender", which is the Model subclass that triggered the signal, and
          an "instance", which is the actual model instance.
      :param string name: a short alias
      :param Model sender: if specified, only instances of this model class will
          trigger the receiver callback.

      Add the receiver to the internal list of receivers, which will be called
      whenever the signal is sent.

      .. code-block:: python

          from playhouse.signals import post_save
          from project.handlers import cache_buster

          post_save.connect(cache_buster, name='project.cache_buster')

   .. method:: disconnect(receiver=None, name=None, sender=None)

      :param callable receiver: the callback to disconnect
      :param string name: a short alias
      :param Model sender: disconnect model-specific handler.

      Disconnect the given receiver (or the receiver with the given name alias)
      so that it no longer is called. Either the receiver or the name must be
      provided.

      .. code-block:: python

         post_save.disconnect(name='project.cache_buster')

    .. method:: send(instance, *args, **kwargs)

       :param instance: a model instance

       Iterates over the receivers and will call them in the order in which
       they were connected. If the receiver specified a sender, it will only
       be called if the instance is an instance of the sender.


.. _dataset:

.. module:: playhouse.dataset

DataSet
-------

``playhouse.dataset`` exposes a dict-oriented API for relational data, modeled
after the `dataset library <https://dataset.readthedocs.io/>`_. It is useful
for quick scripts, data loading, and CSV/JSON import-export.

Basic operations:

.. code-block:: python

   from playhouse.dataset import DataSet

   db = DataSet('sqlite:///data.db')

   # Access a table (created automatically if it doesn't exist):
   users = db['user']

   # Insert rows with any columns:
   users.insert(name='Alice', age=30)
   users.insert(name='Bob', age=25, active=True)  # New column added automatically.

   # Retrieve rows:
   alice = users.find_one(name='Alice')
   print(alice)   # {'id': 1, 'name': 'Alice', 'age': 30, 'active': None}

   for user in users:
       print(user['name'])

   for admin in users.find(active=True):
       print(admin['name'])  # Bob.

   # Update:
   users.update(name='Alice', age=31, columns=['name'])  # 'name' is the lookup.

   # Update all records:
   users.update(admin=False)

   # Delete:
   users.delete(name='Bob')

Export and import data:

.. code-block:: python

   # Export to JSON:
   db.freeze(users.all(), format='json', filename='users.json')

   # Export CSV to stdout:
   db.freeze(users.all(), format='csv', file_obj=sys.stdout)

   # Import from CSV:
   db.thaw('user', format='csv', filename='import.csv')

   # Import a JSON file to a new table.
   db.thaw('new_table', format='json', filename='json-data.json')

Transactions:

.. code-block:: python

   # Transactions.
   with db.transaction() as txn:
       users.insert(name='Charlie')

       with db.transaction() as nested_txn:
           table.update(name='Charlie', favorite_orm='sqlalchemy', columns=['name'])

           nested_txn.rollback()  # JK.

Introspection:

.. code-block:: python

   print(db.tables)
   # ['new_table', 'user']

   print(db['user'].columns)
   # ['id', 'age', 'name', 'active', 'admin', 'favorite_orm']

   print(len(db['user']))
   # 2


.. class:: DataSet(url, **kwargs)

   :param url: :ref:`db-url` or a :class:`Database` instance.
   :param kwargs: additional keyword arguments passed to
       :meth:`Introspector.generate_models` when introspecting the db.

   .. attribute:: tables

      List of table names in the database (computed dynamically).

   .. method:: __getitem__(table_name)

      Return a :class:`Table` for the given name. Creates the table if
      it doesn't exist.

   .. method:: query(sql, params=None, commit=True)

      :param str sql: A SQL query.
      :param list params: Optional parameters for the query.
      :param bool commit: Whether the query should be committed upon execution.
      :return: A database cursor.

      Execute the provided query against the database.

   .. method:: transaction()

      Return a context manager representing a transaction.

   .. method:: freeze(query, format='csv', filename=None, file_obj=None, encoding='utf8', **kwargs)

      :param query: A :class:`SelectQuery`, generated using :meth:`~Table.all` or `~Table.find`.
      :param format: Output format. By default, *csv* and *json* are supported.
      :param filename: Filename to write output to.
      :param file_obj: File-like object to write output to.
      :param str encoding: File encoding.
      :param kwargs: Arbitrary parameters for export-specific functionality.

      Export data to a file.

   .. method:: thaw(table, format='csv', filename=None, file_obj=None, strict=False, encoding='utf8', **kwargs)

      :param str table: The name of the table to load data into.
      :param format: Input format. By default, *csv* and *json* are supported.
      :param filename: Filename to read data from.
      :param file_obj: File-like object to read data from.
      :param bool strict: Whether to store values for columns that do not already exist on the table.
      :param str encoding: File encoding.
      :param kwargs: Arbitrary parameters for import-specific functionality.

      Import data from a file into ``table``. If ``strict=False`` (default),
      new columns are added automatically.

   .. method:: connect()
               close()

      Open or close the underlying database connection.

.. class:: Table(dataset, name, model_class)

   Provides a high-level API for working with rows in a given table.

   .. attribute:: columns

      List of column names.

   .. attribute:: model_class

      A dynamically-created :class:`Model` class.

   .. method:: insert(**data)

      Insert a row, adding new columns as needed.

   .. method:: update(columns=None, conjunction=None, **data)

      Update the table using the provided data. If one or more columns are
      specified in the *columns* parameter, then those columns' values in the
      *data* dictionary will be used to determine which rows to update.

      .. code-block:: python

         # Update all rows.
         db['users'].update(favorite_orm='peewee')

         # Only update Huey's record, setting his age to 3.
         db['users'].update(name='Huey', age=3, columns=['name'])

   .. method:: find(**query)

      Return all rows matching equality conditions (all rows if no
      conditions given).

   .. method:: find_one(**query)

      Return the first matching row, or ``None``.

   .. method:: all()

      Return all rows.

   .. method:: delete(**query)

      Delete matching rows (all rows if no conditions given).

   .. method:: create_index(columns, unique=False)

      Create an index on the given columns:

      .. code-block:: python

          # Create a unique index on the `username` column.
          db['users'].create_index(['username'], unique=True)

   .. method:: freeze(format='csv', filename=None, file_obj=None, **kwargs)

      :param format: Output format. By default, *csv* and *json* are supported.
      :param filename: Filename to write output to.
      :param file_obj: File-like object to write output to.
      :param kwargs: Arbitrary parameters for export-specific functionality.

   .. method:: thaw(format='csv', filename=None, file_obj=None, strict=False, **kwargs)

      :param format: Input format. By default, *csv* and *json* are supported.
      :param filename: Filename to read data from.
      :param file_obj: File-like object to read data from.
      :param bool strict: Whether to store values for columns that do not already exist on the table.
      :param kwargs: Arbitrary parameters for import-specific functionality.


.. _extra-fields:

.. module:: playhouse.fields

Extra Field Types
-----------------

``playhouse.fields`` provides two general-purpose field types.

.. class:: CompressedField(compression_level=6, algorithm='zlib', **kwargs)

   Stores compressed binary data using ``zlib`` or ``bz2``. Extends
   :class:`BlobField`; compression and decompression are transparent:

   .. code-block:: python

       from playhouse.fields import CompressedField

       class LogEntry(Model):
           payload = CompressedField(algorithm='zlib', compression_level=9)

   :param int compression_level: 0-9 (9 is maximum compression).
   :param str algorithm: ``'zlib'`` or ``'bz2'``.

.. class:: PickleField()

   Stores arbitrary Python objects by pickling them into a :class:`BlobField`.

   .. code-block:: python

       from playhouse.fields import PickleField

       class CachedResult(Model):
           data = PickleField()

       CachedResult.create(data={'nested': [1, 2, 3]})


.. _flask-utils:

.. module:: playhouse.flask_utils

Flask Utilities
---------------

``playhouse.flask_utils`` simplifies Peewee integration with
`Flask <https://flask.palletsprojects.com/>`_.

FlaskDB Wrapper
^^^^^^^^^^^^^^^^

:class:`FlaskDB` handles three boilerplate tasks:

1. Creates a Peewee database instance from Flask's ``app.config``.
2. Provides a ``Model`` base class whose ``Meta.database`` is wired to the
   Peewee instance.
3. Registers ``before_request`` / ``teardown_request`` hooks that open and
   close a connection for every request.

Basic setup:

.. code-block:: python

   from flask import Flask
   from playhouse.flask_utils import FlaskDB

   app = Flask(__name__)
   app.config['DATABASE'] = 'postgresql://postgres:pw@localhost/my_app'

   db_wrapper = FlaskDB(app)

   class User(db_wrapper.Model):
       username = CharField(unique=True)

   class Tweet(db_wrapper.Model):
       user = ForeignKeyField(User, backref='tweets')
       content = TextField()

Access the underlying Peewee database:

.. code-block:: python

   peewee_db = db_wrapper.database

   @app.route('/transfer', methods=['POST'])
   def transfer():
       with peewee_db.atomic():
           # ... transactional logic ...
       return jsonify({'ok': True})

Application factory pattern:

.. code-block:: python

   db_wrapper = FlaskDB()

   class User(db_wrapper.Model):
       username = CharField(unique=True)

   def create_app():
       app = Flask(__name__)
       app.config['DATABASE'] = 'sqlite:///my_app.db'
       db_wrapper.init_app(app)
       return app

Configuration via dict or a :class:`Database` instance directly:

.. code-block:: python

   # Dictionary-based (uses playhouse.db_url under the hood):
   app.config['DATABASE'] = {
       'name': 'my_app',
       'engine': 'playhouse.pool.PooledPostgresqlDatabase',
       'user': 'postgres',
       'max_connections': 32,
   }

   # Pass a database object:
   peewee_db = PostgresqlExtDatabase('my_app')
   db_wrapper = FlaskDB(app, peewee_db)

Excluding routes from connection management:

.. code-block:: python

   app.config['FLASKDB_EXCLUDED_ROUTES'] = ('health_check', 'static')

.. class:: FlaskDB(app=None, database=None)

   :param app: Flask application instance (optional; use ``init_app()`` for
       the factory pattern).
   :param database: A database URL string, configuration dictionary, or a
       :class:`Database` instance.

   .. attribute:: database

      The underlying :class:`Database` instance.

   .. attribute:: Model

      A base :class:`Model` class bound to this database instance.

   .. method:: init_app(app)

      Bind to a Flask application (factory pattern).


Query Helpers
^^^^^^^^^^^^^

.. function:: get_object_or_404(query_or_model, *query)

   :param query_or_model: Either a :class:`Model` class or a pre-filtered :class:`SelectQuery`.
   :param query: Peewee filter expressions.

   Retrieve a single object matching the given query, or abort with HTTP
   404 if no match is found.

   .. code-block:: python

       @app.route('/post/<slug>/')
       def post_detail(slug):
           post = get_object_or_404(
               Post.select().where(Post.published == True),
               Post.slug == slug)
           return render_template('post_detail.html', post=post)

.. function:: object_list(template_name, query, context_variable='object_list', paginate_by=20, page_var='page', check_bounds=True, **kwargs)

   Paginate a query and render a template with the results.

   :param str template_name: Template to render.
   :param query: :class:`SelectQuery` to paginate.
   :param str context_variable: Template variable name for the page of
       objects (default: ``'object_list'``).
   :param int paginate_by: Items per page.
   :param str page_var: GET parameter name for the page number.
   :param bool check_bounds: Return 404 for invalid page numbers.
   :param kwargs: Extra template context variables.

   The template receives:

   - ``object_list`` (or ``context_variable``) - page of objects.
   - ``page`` - current page number.
   - ``pagination`` - a :class:`PaginatedQuery` instance.

   .. code-block:: python

       @app.route('/posts/')
       def post_list():
           return object_list(
               'post_list.html',
               query=Post.select().where(Post.published == True),
               paginate_by=10)

.. class:: PaginatedQuery(query_or_model, paginate_by, page_var='page', check_bounds=False)

   :param query_or_model: Either a :class:`Model` or a :class:`SelectQuery` instance containing the collection of records you wish to paginate.
   :param paginate_by: Number of objects per-page.
   :param page_var: The name of the ``GET`` argument which contains the page.
   :param check_bounds: Whether to check that the given page is a valid page. If ``check_bounds`` is ``True`` and an invalid page is specified, then a 404 will be returned.

   Helper class to perform pagination based on ``GET`` arguments.

   .. method:: get_page()

      Return the current page number (1-based; defaults to 1).

   .. method:: get_page_count()

      Return the total number of pages.

   .. method:: get_object_list()

      Return the :class:`SelectQuery` for the requested page, with
      appropriate ``LIMIT`` and ``OFFSET`` applied. Returns a 404 if
      ``check_bounds=True`` and the page is empty.
