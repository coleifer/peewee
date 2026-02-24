.. _postgres-ext:

PostgreSQL Extensions
=====================

The ``playhouse.postgres_ext`` module exposes PostgreSQL-specific field types
and features that are not available in the standard :class:`PostgresqlDatabase`.
Most of these features require substituting :class:`PostgresqlExtDatabase`
for the standard class.

.. code-block:: python

   from playhouse.postgres_ext import PostgresqlExtDatabase

   db = PostgresqlExtDatabase(
       'my_app',
       user='postgres',
       register_hstore=False,     # Set True to use HStoreField.
       server_side_cursors=False, # Set True to use server-side cursors globally.
   )

.. _postgres-ext-api:

PostgresqlExtDatabase
---------------------

.. class:: PostgresqlExtDatabase(database, server_side_cursors=False, register_hstore=False, prefer_psycopg3=False, **kwargs)

   Extends :class:`PostgresqlDatabase` and is required to use:

   - :class:`ArrayField`
   - :class:`DateTimeTZField`
   - :class:`JSONField` / :class:`BinaryJSONField`
   - :class:`HStoreField`
   - :class:`TSVectorField`
   - Server-side cursors

   :param bool server_side_cursors: Use server-side cursors for all
       ``SELECT`` queries by default.
   :param bool register_hstore: Register the HStore extension with each
       connection. Required when using :class:`HStoreField`.
   :param bool prefer_psycopg3: When both psycopg2 and psycopg3 are
       installed, prefer psycopg3.


JSON Support
------------

Peewee provides two JSON field types for PostgreSQL:

- :class:`JSONField` - stores JSON as text, supports key access and
  comparison (PostgreSQL 9.2+).
- :class:`BinaryJSONField` - stores JSON in the efficient binary ``jsonb``
  format and adds containment operators (PostgreSQL 9.4+).

For most new applications, prefer :class:`BinaryJSONField`.

.. code-block:: python

   from playhouse.postgres_ext import PostgresqlExtDatabase, BinaryJSONField

   db = PostgresqlExtDatabase('my_app')

   class Event(Model):
       name    = CharField()
       payload = BinaryJSONField()
       class Meta:
           database = db

   # Store a dict transparently:
   Event.create(name='login', payload={'user_id': 42, 'ip': '1.2.3.4'})

   # Filter using a nested key:
   suspicious = Event.select().where(
       Event.payload['ip'] == '1.2.3.4')

   # Retrieve a sub-object as Python data:
   for e in Event.select(Event.payload['user_id'].alias('uid')):
       print(e.uid)

.. class:: JSONField()

   Field that stores and retrieves JSON data. Supports ``__getitem__`` key
   access for filtering and sub-object retrieval.

   .. method:: as_json()

      Return the value at this path as deserialized Python data rather than
      a raw string.

.. class:: BinaryJSONField()

   Extends :class:`JSONField` for the ``jsonb`` type. Supports all
   :class:`JSONField` methods plus:

   .. method:: contains(other)

      Test whether this field's value contains ``other`` (as a subset).
      ``other`` may be a partial dict, list, or scalar value.

      .. code-block:: python

          # Find events where the payload contains both keys.
          Event.select().where(Event.payload.contains({'ip': '1.2.3.4'}))

   .. method:: contains_any(*items)

      Test whether any of ``items`` is present in the JSON value.

   .. method:: contains_all(*items)

      Test whether all of ``items`` are present in the JSON value.

   .. method:: contained_by(other)

      Test whether this field's value is a subset of ``other``.

   .. method:: concat(data)

      Concatenate the field value with ``data``. Note this is a shallow
      operation and does not deep-merge nested objects.

   .. method:: has_key(key)

      Test whether ``key`` exists at the top level of the JSON object.

   .. method:: remove(*keys)

      Remove one or more top-level keys from the JSON object.


.. _hstore:

HStore
------

PostgreSQL's `hstore <https://www.postgresql.org/docs/current/hstore.html>`_
extension stores arbitrary key/value pairs in a single column. Enable it by
passing ``register_hstore=True`` when constructing the database:

.. code-block:: python

   db = PostgresqlExtDatabase('my_app', register_hstore=True)

   class Property(Model):
       address  = CharField()
       features = HStoreField()
       class Meta:
           database = db

   # Create a record with arbitrary attributes:
   p = Property.create(
       address='123 Main St',
       features={'garage': '2 cars', 'bath': '2 bath'})

   # Filter by a key/value pair:
   Property.select().where(Property.features.contains({'garage': '2 cars'}))

   # Filter by key existence:
   Property.select().where(Property.features.exists('garage'))

   # Atomic update - adds new keys, updates existing ones:
   new_features = Property.features.update({'bath': '2.5 bath', 'sqft': '1100'})
   Property.update(features=new_features).where(Property.id == p.id).execute()

   # Atomic key deletion:
   Property.update(
       features=Property.features.delete('bath')
   ).where(Property.id == p.id).execute()

   # Retrieve keys or values:
   for prop in Property.select(Property.address, Property.features.keys().alias('k')):
       print(prop.address, prop.k)

   # Retrieve a sub-slice:
   for prop in Property.select(
           Property.address,
           Property.features.slice('garage').alias('garage_info')):
       print(prop.address, prop.garage_info)  # {'garage': '2 cars'}

Available operations: ``contains(key_or_dict_or_list)``, ``exists(key)``,
``update(dict)``, ``delete(*keys)``, ``keys()``, ``values()``, ``items()``,
``slice(*keys)``.


.. _pg-arrays:

Arrays
------

.. class:: ArrayField(field_class=IntegerField, field_kwargs=None, dimensions=1, convert_values=False)

   Stores a PostgreSQL array of the given field type.

   :param field_class: Element type (e.g. :class:`CharField`).
   :param int dimensions: Number of array dimensions.
   :param bool convert_values: Apply ``field_class`` value conversion to
       retrieved data.

   By default, a GIN index is created. Pass ``index=False`` to disable.

   .. code-block:: python

       class Post(Model):
           tags = ArrayField(CharField)

       post = Post(tags=['python', 'peewee', 'sqlite'])

       # Get the first tag (1-based index in PostgreSQL):
       Post.select(Post.tags[1].alias('first_tag'))

       # Get a slice (first two tags):
       Post.select(Post.tags[1:3].alias('first_two'))

   .. method:: contains(*items)

      Filter rows where the array contains all of the given values.

   .. method:: contains_any(*items)

      Filter rows where the array contains any of the given values.


.. _pg-interval:

Interval
--------

.. class:: IntervalField(**kwargs)

   Stores Python ``datetime.timedelta`` instances using PostgreSQL's native
   ``INTERVAL`` type.

   .. code-block:: python

       from datetime import timedelta

       class Subscription(Model):
           duration = IntervalField()

       Subscription.create(duration=timedelta(days=30))


.. _server-side-cursors:

Server-Side Cursors
-------------------

For large result sets, server-side (named) cursors stream rows from the server
rather than loading the entire result into memory. The default fetch size is
2000 rows; rows are fetched transparently as you iterate.

Wrap any SELECT query with :func:`ServerSide`:

.. code-block:: python

   from playhouse.postgres_ext import ServerSide

   # Server-side cursors must be inside a transaction.
   with db.atomic():
       large_query = PageView.select().order_by(PageView.id)
       for page_view in ServerSide(large_query):
           process(page_view)
       # Cursor is released at the end of the block.

For explicit batch control:

.. code-block:: python

   with db.atomic():
       query = ServerSideQuery(PageView.select(), array_size=500)
       for i, pv in enumerate(query.iterator()):
           if i == 9500:
               break
           process(pv)
       query.close()  # Release the server-side cursor explicitly.

.. warning::
   Server-side cursors live only within a transaction. If you are using psycopg2
   (not psycopg3), cursors are declared ``WITH HOLD`` and must be fully
   exhausted or explicitly closed to release server resources.

.. function:: ServerSide(select_query)

   Wrap ``select_query`` in a transaction and iterate using
   :meth:`~SelectQuery.iterator` (disables row caching).


.. _pg-fts:

Full-Text Search
----------------

PostgreSQL full-text search uses the ``tsvector`` and ``tsquery`` types.
Peewee offers two approaches: the simple :func:`Match` function (no schema
changes required) and the :class:`TSVectorField` for dedicated search columns
(better performance).

**Simple approach** - no schema changes required:

.. code-block:: python

   from playhouse.postgres_ext import Match

   def search_posts(term):
       return Post.select().where(
           (Post.status == 'published') &
           Match(Post.body, term))

For better performance, create a GIN index:

.. code-block:: sql

   CREATE INDEX posts_fts ON post USING gin(to_tsvector('english', body));

**Dedicated column** (recommended for high-traffic search):

.. code-block:: python

   class Post(Model):
       body           = TextField()
       search_content = TSVectorField()  # Automatically gets a GIN index.

   # Store a post and populate the search vector:
   Post.create(
       body=body_text,
       search_content=fn.to_tsvector(body_text))

   # Search:
   Post.select().where(Post.search_content.match('python asyncio'))

.. function:: Match(field, query)

   Generate a full-text search expression that converts ``field`` to
   ``tsvector`` and ``query`` to ``tsquery`` automatically.

.. class:: TSVectorField()

   Field type for storing pre-computed ``tsvector`` data. Automatically
   created with a GIN index (use ``index=False`` to disable).

   .. note::
       Data must be explicitly converted to ``tsvector`` on write using
       ``fn.to_tsvector()``.

   .. method:: match(query, language=None, plain=False)

      :param str query: Full-text search query.
      :param str language: Optional language name.
      :param bool plain: Use the plain (simple) query parser instead of the
          default one, which supports ``&``, ``|``, and ``!`` operators.


.. _pg-timezone:

DateTimeTZ Field
-----------------

.. class:: DateTimeTZField(**kwargs)

   Timezone-aware datetime field using PostgreSQL's ``TIMESTAMP WITH TIME ZONE``
   type.


.. _crdb:

CockroachDB
-----------

`CockroachDB <https://www.cockroachlabs.com>`_ (CRDB) is compatible with
PostgreSQL's wire protocol and is well-supported by Peewee. Use the dedicated
:class:`CockroachDatabase` class rather than :class:`PostgresqlDatabase`
to get CRDB-specific handling.

.. note:: CRDB requires the ``psycopg2`` driver.

.. code-block:: python

   from playhouse.cockroachdb import CockroachDatabase

   db = CockroachDatabase('my_app', user='root', host='10.1.0.8')

   # Cockroach Cloud - connection string form:
   db = CockroachDatabase('postgresql://root:secret@host:26257/defaultdb?...')

SSL configuration:

.. code-block:: python

   db = CockroachDatabase(
       'my_app',
       user='root',
       host='10.1.0.8',
       sslmode='verify-full',
       sslrootcert='/path/to/root.crt')

Key differences from PostgreSQL
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- **No nested transactions.** CRDB does not support savepoints, so calling
  :meth:`~Database.atomic` inside another ``atomic()`` block raises an
  exception. Use :meth:`~Database.transaction` instead, which ignores
  nested calls and commits only when the outermost block exits.
- **Client-side retries.** CRDB may abort transactions due to contention.
  Use :meth:`~CockroachDatabase.run_transaction` for automatic retries.

.. code-block:: python

   # transaction() is safe to nest; the outer block manages the commit.
   @db.transaction()
   def create_user(username):
       return User.create(username=username)

   with db.transaction():
       create_user('alice')   # Nested call is folded into outer transaction.
       create_user('bob')
   # Transaction is committed here.

Client-side retries:

.. code-block:: python

   def transfer_funds(from_id, to_id, amount):
       def thunk(db_ref):
           src, dst = Account.select().where(Account.id.in_([from_id, to_id]))
           if src.balance < amount:
               return False
           (Account.update(balance=Account.balance - amount)
                   .where(Account.id == from_id).execute())
           (Account.update(balance=Account.balance + amount)
                   .where(Account.id == to_id).execute())
           return True

       return db.run_transaction(thunk, max_attempts=10)

CRDB API
^^^^^^^^^

.. class:: CockroachDatabase(database, **kwargs)

   Subclass of :class:`PostgresqlDatabase` for CockroachDB.

   .. method:: run_transaction(callback, max_attempts=None, system_time=None, priority=None)

      :param callback: Callable accepting a single ``db`` argument.
          Must not manage the transaction itself. May be called multiple times.
      :param int max_attempts: Retry limit.
      :param datetime system_time: Execute ``AS OF SYSTEM TIME``.
      :param str priority: ``'low'``, ``'normal'``, or ``'high'``.
      :raises ExceededMaxAttempts: When ``max_attempts`` is exceeded.

      Execute SQL in a transaction with automatic client-side retries.

.. class:: PooledCockroachDatabase(database, **kwargs)

   Connection-pooling variant of :class:`CockroachDatabase`.

CRDB-specific field types:

.. class:: UUIDKeyField()

   UUID primary key auto-populated with CRDB's ``gen_random_uuid()``.

.. class:: RowIDField()

   Integer primary key auto-populated with CRDB's ``unique_rowid()``.


.. _mysql-ext:

MySQL Extensions
----------------

Peewee provides alternate drivers for MySQL through ``playhouse.mysql_ext``.

.. class:: MySQLConnectorDatabase(database, **kwargs)

   Database implementation using the official
   `mysql-connector-python <https://dev.mysql.com/doc/connector-python/en/>`_
   driver instead of ``mysqlclient``.

   .. code-block:: python

       from playhouse.mysql_ext import MySQLConnectorDatabase

       db = MySQLConnectorDatabase('my_db', host='1.2.3.4', user='mysql')

.. class:: MariaDBConnectorDatabase(database, **kwargs)

   Database implementation using the
   `mariadb-connector <https://mariadb-corporation.github.io/mariadb-connector-python/>`_
   driver.

   .. note::
       Does **not** accept ``charset``, ``sql_mode``, or ``use_unicode``
       parameters (charset is always ``utf8mb4``).

   .. code-block:: python

       from playhouse.mysql_ext import MariaDBConnectorDatabase

       db = MariaDBConnectorDatabase('my_db', host='1.2.3.4', user='mysql')

MySQL-specific helpers:

.. class:: JSONField()

   Extends :class:`TextField` with transparent JSON encoding/decoding.

   .. method:: extract(path)

      Extract a value from a JSON document at the given JSON path
      (e.g. ``'$.key'``).

.. function:: Match(columns, expr, modifier=None)

   Helper for MySQL full-text search using ``MATCH ... AGAINST`` syntax.

   :param columns: A single :class:`Field` or a tuple of fields.
   :param str expr: Full-text search expression.
   :param str modifier: Optional modifier, e.g. ``'IN BOOLEAN MODE'``.

   .. code-block:: python

       from playhouse.mysql_ext import Match

       Post.select().where(
           Match((Post.title, Post.body), 'python asyncio',
                 modifier='IN BOOLEAN MODE'))
