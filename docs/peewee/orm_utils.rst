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
   :param int max_depth: Maximum recursion depth when following relations.
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

   .. note::
       If your use case is unusual, write a small custom function rather
       than trying to coerce ``model_to_dict`` with a complex combination
       of parameters.

.. function:: dict_to_model(model_class, data, ignore_unknown=False)

   Construct a model instance from a dictionary. Foreign keys may be
   provided as nested dicts; back-references as lists of dicts.

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

   A ``Metadata`` implementation that protects the ``database`` attribute
   with a read/write lock. Use this when your application may swap the
   active database (e.g. primary → read replica) at runtime across threads:

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

The concept is borrowed from SQLAlchemy's `hybrid extension
<https://docs.sqlalchemy.org/en/14/orm/extensions/hybrid.html>`_.

.. code-block:: python

   from playhouse.hybrid import hybrid_property, hybrid_method

   class Interval(Model):
       start = IntegerField()
       end   = IntegerField()

       @hybrid_property
       def length(self):
           return self.end - self.start

       @hybrid_method
       def contains(self, point):
           return (self.start <= point) & (point < self.end)

On an instance, Python arithmetic runs:

.. code-block:: python

   i = Interval(start=1, end=5)
   i.length       # 4 (Python arithmetic)
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
       end   = IntegerField()

       @hybrid_property
       def radius(self):
           return abs(self.length) / 2     # Python: uses Python abs()

       @radius.expression
       def radius(cls):
           return fn.ABS(cls.length) / 2   # SQL: uses fn.ABS()

.. class:: hybrid_property(fget, fset=None, fdel=None, expr=None)

   Decorator for defining a property with separate instance and class
   behaviors. Use ``@prop.expression`` to specify the SQL form when it
   differs from the Python form.

.. class:: hybrid_method(func, expr=None)

   Decorator for defining a method with separate instance and class
   behaviors. Use ``@method.expression`` to specify the SQL form.


.. _kv:

.. module:: playhouse.kv

Key/Value Store
---------------

``playhouse.kv.KeyValue`` provides a persistent dictionary backed by SQLite
(or another Peewee-supported database).

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
       :class:`CharField` with ``primary_key=True``.
   :param Field value_field: Field for the value. Defaults to
       :class:`PickleField`.
   :param bool ordered: Return keys in sorted order when iterating.
   :param Database database: Database to use. Defaults to an in-memory
       SQLite database.
   :param str table_name: Name of the underlying table.

   The table is created automatically on construction if it does not exist.
   Supports the standard dictionary interface plus expression-based access.

   .. method:: update(data=None, **kwargs)

      Efficiently upsert one or more key/value pairs.

   .. method:: get(expr, default=None)

      Return the value for a key, or ``default`` if missing. If ``expr``
      is an expression rather than a scalar key, returns a list (empty if
      none match).

   .. method:: pop(expr, default=Sentinel)

      Return and remove the value for a key. If ``expr`` is an expression,
      returns and removes all matching pairs as a list.

   .. method:: clear()

      Remove all entries.


.. _signals:

.. module:: playhouse.signals

Signals
-------

``playhouse.signals`` adds Django-style model lifecycle signals. Models must
subclass ``playhouse.signals.Model`` (not ``peewee.Model``) for hooks to fire.

.. code-block:: python

   from playhouse.signals import Model, post_save, pre_delete

   class MyModel(Model):
       data = IntegerField()
       class Meta:
           database = db

   @post_save(sender=MyModel)
   def on_save(model_class, instance, created):
       if created:
           notify_new(instance)

Available signals: ``pre_init``, ``pre_save``, ``post_save``, ``pre_delete``,
``post_delete``.

.. warning::
   Signals fire only through the high-level instance methods
   (:meth:`~Model.save`, :meth:`~Model.delete_instance`). Bulk
   operations via :meth:`~Model.insert`, :meth:`~Model.update`, and
   :meth:`~Model.delete` do not trigger signals because no model instance
   is involved.

Connecting handlers
^^^^^^^^^^^^^^^^^^^

Use the signal as a decorator (recommended):

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

- ``pre_init(model_class, instance)``
- ``pre_save(model_class, instance, created)``
- ``post_save(model_class, instance, created)``
- ``pre_delete(model_class, instance)``
- ``post_delete(model_class, instance)``

.. class:: Signal()

   .. method:: connect(receiver, name=None, sender=None)

      Register a callback. If ``sender`` is given, the callback only fires
      for instances of that model class.

   .. method:: disconnect(receiver=None, name=None, sender=None)

      Unregister a callback by reference or by name.

   .. method:: send(instance, *args, **kwargs)

      Invoke registered callbacks in connection order.


.. _dataset:

.. module:: playhouse.dataset

DataSet
-------

``playhouse.dataset`` exposes a schemaless, dict-oriented API for relational
data, modeled after the `dataset library
<https://dataset.readthedocs.io/>`_. It is useful for quick scripts, data
loading, and CSV/JSON import-export.

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

   # Update:
   users.update(name='Alice', age=31, columns=['name'])  # 'name' is the lookup.

   # Delete:
   users.delete(name='Bob')

   # Export to JSON:
   db.freeze(users.all(), format='json', filename='users.json')

   # Import from CSV:
   db.thaw('user', format='csv', filename='import.csv')

.. class:: DataSet(url, **kwargs)

   :param url: A database URL string or a :class:`Database` instance.

   .. attribute:: tables

      List of table names in the database (computed dynamically).

   .. method:: __getitem__(table_name)

      Return a :class:`Table` for the given name. Creates the table if
      it doesn't exist.

   .. method:: query(sql, params=None, commit=True)

      Execute raw SQL and return a cursor.

   .. method:: transaction()

      Return a context manager representing a transaction.

   .. method:: freeze(query, format='csv', filename=None, file_obj=None, encoding='utf8', **kwargs)

      Export the rows returned by ``query`` to a file. Supported formats:
      ``'csv'``, ``'json'``.

   .. method:: thaw(table, format='csv', filename=None, file_obj=None, strict=False, encoding='utf8', **kwargs)

      Import data from a file into ``table``. If ``strict=False`` (default),
      new columns are added automatically.

   .. method:: connect() / close()

      Open or close the underlying database connection.

.. class:: Table(dataset, name, model_class)

   .. attribute:: columns

      List of column names.

   .. method:: insert(**data)

      Insert a row, adding new columns as needed.

   .. method:: update(columns=None, conjunction=None, **data)

      Update matching rows. ``columns`` specifies which fields to use for
      the ``WHERE`` clause.

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

      Create an index on the given column names.

   .. method:: freeze(...) / thaw(...)

      Table-level variants of the :class:`DataSet` methods.


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

   Stores arbitrary Python objects by pickling them into a
   :class:`BlobField`. Uses ``cPickle`` if available:

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
       user      = ForeignKeyField(User, backref='tweets')
       content   = TextField()

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

   Retrieve a single object matching the given query, or abort with HTTP
   404 if no match is found.

   :param query_or_model: Either a :class:`Model` class or a pre-filtered
       :class:`SelectQuery`.
   :param query: Peewee filter expressions.

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

   Helper for pagination based on a GET parameter.

   .. method:: get_page()

      Return the current page number (1-based; defaults to 1).

   .. method:: get_page_count()

      Return the total number of pages.

   .. method:: get_object_list()

      Return the :class:`SelectQuery` for the requested page, with
      appropriate ``LIMIT`` and ``OFFSET`` applied. Returns a 404 if
      ``check_bounds=True`` and the page is empty.
