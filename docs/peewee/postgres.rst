.. _postgresql:

Postgresql
==========

The ``playhouse.postgres_ext`` module exposes Postgresql-specific field types
and features that are not available in the standard :class:`PostgresqlDatabase`.

.. contents:: On this page
   :local:
   :depth: 1

Getting Started
---------------

To get started import the ``playhouse.postgres_ext`` module and use the :class:`PostgresqlExtDatabase`
database class:

.. code-block:: python

    from playhouse.postgres_ext import *

    db = PostgresqlExtDatabase('peewee_test', user='postgres')

    class BaseExtModel(Model):
        class Meta:
            database = db

.. _postgres-ext-api:

PostgresqlExtDatabase
---------------------

.. class:: PostgresqlExtDatabase(database, server_side_cursors=False, register_hstore=False, prefer_psycopg3=False, **kwargs)

   Extends :class:`PostgresqlDatabase` and is required to use:

   * :class:`ArrayField`
   * :class:`DateTimeTZField`
   * :class:`JSONField` / :class:`BinaryJSONField`
   * :class:`HStoreField`
   * :class:`TSVectorField`
   * :ref:`postgres-server-side-cursors`

   :param str database: Name of database to connect to.
   :param bool server_side_cursors: Whether ``SELECT`` queries should utilize
       server-side cursors.
   :param bool register_hstore: Register the hstore extension.
   :param bool prefer_psycopg3: If both psycopg2 and psycopg3 are installed,
       instruct Peewee to prefer psycopg3.

   When using ``server_side_cursors`` be sure to wrap your queries with :func:`ServerSide`.

.. class:: PooledPostgresqlExtDatabase(database, **kwargs)

   Connection-pooling variant of :class:`PostgresqlExtDatabase`.

.. class:: Psycopg3Database(database, **kwargs)

   Same as :class:`PostgresqlExtDatabase` but specifies ``prefer_psycopg3=True``.

.. class:: PooledPsycopg3Database(database, **kwargs)

   Connection-pooling variant of :class:`Psycopg3Database`.

.. _postgres-json:

JSON Support
------------

Peewee provides two JSON field types for Postgresql:

- :class:`JSONField` - stores JSON as text, supports key access and comparison.
- :class:`BinaryJSONField` - stores JSON in the efficient binary ``jsonb``
  format and adds containment operators.

In general always use :class:`BinaryJSONField`.

.. code-block:: python

   from playhouse.postgres_ext import PostgresqlExtDatabase, BinaryJSONField

   db = PostgresqlExtDatabase('my_app')

   class Event(Model):
       data = BinaryJSONField()
       class Meta:
           database = db

   # Store data:
   Event.create(data={
       'type': 'login',
       'user_id': 42,
       'request': {'ip': '1.2.3.4'},
       'success': True})

   # Filter using a nested key:
   query = (Event
            .select()
            .where(Event.data['request']['ip'] == '1.2.3.4'))

   # Select, group and order-by JSON values.
   query = (Event
            .select(Event.data['user_id'],
                    fn.COUNT(Event.id))
            .group_by(Event.data['user_id'])
            .order_by(Event.data['user_id'])
            .tuples())

   # Retrieve JSON objects.
   query = (Event
            .select(Event.data['request'].as_json().alias('request'))
            .where(Event.data['user_id'] == 42))
   for event in query:
       print(event.request['ip'])

.. tip::
   Refer to the `Postgresql JSON documentation <https://www.postgresql.org/docs/current/functions-json.html>`__
   for in-depth discussion and examples of using JSON and JSONB.

JSONField and BinaryJSONField
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. class:: JSONField(*args, **kwargs)

   Field that stores and retrieves JSON data. Supports ``__getitem__`` key
   access for filtering and sub-object retrieval.

   .. note::
      Consider using the :class:`BinaryJSONField` instead as it
      offers better performance and more powerful querying options.

   .. method:: as_json()

      Deserialize and return the JSON value at the given path.

   .. method:: concat(data)

      Concatenate the field value with ``data``. Note this is a shallow
      operation and does not deep-merge nested objects.

      Example:

      .. code-block:: python

         # Add object - if "result" key existed before it is overwritten.
         (Event
          .update(data=Event.data.concat({'result': {'success': True}}))
          .execute())


.. class:: BinaryJSONField()

   Extends :class:`JSONField` for the ``jsonb`` type.

   .. note::
       By default BinaryJSONField will use a GiST index. To disable this,
       initialize the field with ``index=False``.

   .. method:: as_json()

      Deserialize and return the JSON value at the given path.

   .. method:: concat(data)

      Concatenate the field value with ``data``. Note this is a shallow
      operation and does not deep-merge nested objects.

      Example:

      .. code-block:: python

         # Add object - if "result" key existed before it is overwritten.
         (Event
          .update(data=Event.data.concat({'result': {'success': True}}))
          .execute())

   .. method:: contains(other)

      Test whether this field's value contains ``other`` (as a subset).
      ``other`` may be a partial dict, list, or scalar value.

      .. code-block:: python

         Event.create(data={
             'type': 'rename',
             'name': 'new name',
             'tags': ['t1', 't2', 't3']})

         # Search by partial object:
         Event.select().where(Event.data.contains({'type': 'rename'}))

         # Search arrays by one or more items:
         Event.select().where(Event.data['tags'].contains(['t2', 't1']))

         # Search arrays by individual item:
         Event.select().where(Event.data['tags'].contains('t1'))

   .. method:: contains_any(*keys)

      Test whether any of ``keys`` is present in the JSON value.

      .. code-block:: python

         Event.create(data={
             'type': 'rename',
             'name': 'new name',
             'tags': ['t1', 't2', 't3']})

         (Event
          .select()
          .where(Event.data.contains_any('name', 'other')))

   .. method:: contains_all(*keys)

      Test whether all of ``keys`` are present in the JSON value.

      .. code-block:: python

         Event.create(data={
             'type': 'rename',
             'name': 'new name',
             'tags': ['t1', 't2', 't3']})

         (Event
          .select()
          .where(Event.data.contains_all('name', 'tags')))

   .. method:: contained_by(other)

      Test whether this field's value is a subset of ``other``.

      .. code-block:: python

         Event.create(data={
             'type': 'login',
             'result': {'success': True}})

         (Event
          .select()
          .where(Event.data.contained_by({
              'type': 'login',
              'result': {'success': True, 'message': 'OK'}})))

   .. method:: has_key(key)

      Test whether ``key`` exists.

      .. code-block:: python

         Event.select().where(Event.data.has_key('result'))

         Event.select().where(Event.data['result'].has_key('success'))

   .. method:: remove(*keys)

      Remove one or more keys from the JSON object.

      .. code-block:: python

         # Atomically remove key:
         Event.update(data=Event.data.remove('result')).execute()


.. _postgres-hstore:

HStore
------

Postgresql's `hstore <https://www.postgresql.org/docs/current/hstore.html>`_
extension stores arbitrary key/value pairs in a single column. Enable it by
passing ``register_hstore=True`` when initializing the database:

.. code-block:: python

   db = PostgresqlExtDatabase('my_app', register_hstore=True)

   class Event(Model):
       data = HStoreField()
       class Meta:
           database = db

:class:`HStoreField` supports the following operations:

* Store and retrieve arbitrary dictionaries
* Filter by key(s) or partial dictionary
* Update/add one or more keys to an existing dictionary
* Delete one or more keys from an existing dictionary
* Select keys, values, or zip keys and values
* Retrieve a slice of keys/values
* Test for the existence of a key
* Test that a key has a non-NULL value

Example:

.. code-block:: python

   # Create a record with arbitrary attributes:
   Event.create(data={
       'type': 'register',
       'ip': '1.2.3.4',
       'email': 'charles@example.com',
       'result': 'success',
       'referrer': 'google.com'})

   Event.create(data={
       'type': 'login',
       'ip': '1.2.3.4',
       'email': 'charles@example.com',
       'result': 'success'})

   # Lookup nested values in the data:
   Event.select().where(Event.data['type'] == 'login')

   # Filter by a key/value pair:
   Event.select().where(Event.data.contains({'result': 'success'})

   # Filter by key existence:
   Event.select().where(Event.data.exists('referrer'))

   # Atomic update - adds new keys, updates existing ones:
   new_data = Event.data.update({
       'result': 'ok',
       'status': 'success'})
   (Event
    .update(data=new_data)
    .where(Event.data['result'] == 'success')
    .execute())

   # Atomic key deletion:
   (Event
    .update(data=Event.data.delete('referrer'))
    .where(Event.data['referrer'] == 'google.com')
    .execute())

   # Retrieve keys or values as a list:
   for event in Event.select(Event.id, Event.data.keys().alias('k')):
       print(event.id, event.k)

   # Prints:
   # 1 ['ip', 'type', 'email', 'result', 'status']

   # Retrieve a subset of data:
   query = (Event
            .select(Event.id,
                    Event.data.slice('ip', 'email').alias('source'))
            .order_by(Event.data['ip']))
   for event in query:
       print(event.id, event.source)

   # Prints:
   # 1 {'ip': '1.2.3.4', 'email': 'charles@example.com'}

HStoreField API
^^^^^^^^^^^^^^^

.. class:: HStoreField()

   .. note::
      By default ``HStoreField`` will use a *GiST* index. To disable this,
      initialize the field with ``index=False``.

   .. method:: __getitem__(key)

      :param str key: get value at given key.

      Example:

      .. code-block:: python

         Event.select().where(Event.data['type'] == 'login')

   .. method:: contains(value)

      :param value: value to search for.
      :type value: dict, list, tuple or string key.

      Test whether the HStore data contains the given ``dict`` (match keys and
      values), ``list``/``tuple`` (match keys), or ``str`` key.

      Example:

      .. code-block:: python

         # Contains key/value pairs:
         Event.select().where(Event.data.contains({'result': 'success'}))

         # Contains a list of keys:
         Event.select().where(Event.data.contains(['result', 'status']))

         # Contains a single key:
         Event.select().where(Event.data.contains('result'))

   .. method:: contains_any(*keys)

      Test whether the HStore contains any of the given keys.

   .. method:: exists(key)

      Test whether key exists in data.

   .. method:: defined(key)

      Test whether key is non-NULL in data.

   .. method:: update(__data=None, **data)

      :param dict __data: Specify update as a ``dict``.
      :param data: Specify update as keyword arguments.

      Perform an in-place, atomic update.

      .. code-block:: python

         # Atomic update - adds new keys, updates existing ones:
         new_data = Event.data.update({
             'result': 'ok',
             'status': 'success'})
         (Event
          .update(data=new_data)
          .where(Event.data['result'] == 'success')
          .execute())

   .. method:: delete(*keys)

      :param keys: one or more keys to delete from data.

      .. code-block:: python

         # Atomic key deletion:
         (Event
          .update(data=Event.data.delete('referrer'))
          .where(Event.data['referrer'] == 'google.com')
          .execute())

   .. method:: slice(*keys)

      :param str keys: keys to retrieve.

      Retrieve only the provided key/value pairs:

      .. code-block:: python

         query = (Event
                  .select(Event.id,
                          Event.data.slice('ip', 'email').alias('source'))
                  .order_by(Event.data['ip']))
         for event in query:
             print(event.id, event.source)

         # 1 {'ip': '1.2.3.4', 'email': 'charles@example.com'}

   .. method:: keys()

      Return the keys as a list.

      .. code-block:: python

         query = Event.select(Event.data.keys().alias('keys'))
         for event in query:
             print(event.keys)

         # ['ip', 'type', 'email', 'result', 'status']

   .. method:: values()

      Return the values as a list.

   .. method:: items()

      Return the key-value pairs as a 2-dimensional list.

      .. code-block:: python

         query = Event.select(Event.data.items().alias('items'))
         for event in query:
             print(event.items)

         # [['ip', '1.2.3.4'],
         #  ['type', 'register'],
         #  ['email', 'charles@example.com'],
         #  ['result', 'ok'],
         #  ['status', 'success']]

.. _postgres-arrays:

Arrays
------

.. class:: ArrayField(field_class=IntegerField, field_kwargs=None, dimensions=1, convert_values=False)

   Stores a Postgresql array of the given field type.

   :param field_class: a subclass of :class:`Field`, e.g. :class:`IntegerField`.
   :param dict field_kwargs: arguments to initialize ``field_class``.
   :param int dimensions: Number of array dimensions.
   :param bool convert_values: Apply ``field_class`` value conversion to
       retrieved data.

   .. note::
      By default ArrayField will use a GIN index. To disable this, initialize
      the field with ``index=False``.

   Example:

   .. code-block:: python

      class Post(Model):
          tags = ArrayField(CharField)

      Post.create(tags=['python', 'peewee', 'postgresql'])
      Post.create(tags=['python', 'sqlite'])

      # Get an item by index.
      Post.select(Post.tags[0].alias('first_tag'))

      # Get a slice:
      Post.select(Post.tags[:2].alias('first_two'))

   Multi-dimensional array example:

   .. code-block:: python

      class Outline(Model):
          points = ArrayField(IntegerField, dimensions=2)

      Outline.create(points=[[1, 1], [1, 5], [5, 5], [5, 1]])

   .. method:: contains(*items)

      Filter rows where the array contains all of the given values.

      :param items: One or more items that must be in the given array field.

      .. code-block:: python

         Post.select().where(Post.tags.contains('postgresql', 'python'))

   .. method:: contains_any(*items)

      Filter rows where the array contains any of the given values.

      :param items: One or more items to search for in the given array field.

      .. code-block:: python

         Post.select().where(Post.tags.contains('postgresql', 'python'))

.. _postgres-interval:

Interval
--------

.. class:: IntervalField(**kwargs)

   Stores Python ``datetime.timedelta`` instances using Postgresql's native
   ``INTERVAL`` type.

   .. code-block:: python

      from datetime import timedelta

      class Subscription(Model):
          duration = IntervalField()

      Subscription.create(duration=timedelta(days=30))

      (Subscription
       .select()
       .where(Subscription.duration > timedelta(days=10)))

.. _postgres-datetimetz:

DateTimeTZ Field
-----------------

.. class:: DateTimeTZField(**kwargs)

   Timezone-aware datetime field using Postgresql's ``TIMESTAMP WITH TIME ZONE``
   type.

   .. code-block:: python

      class Event(Model):
          timestamp = DateTimeTZField()

      now = datetime.datetime.now().astimezone(datetime.timezone.utc)

      Event.create(timestamp=now)

      event = Event.get()
      print(event.timestamp)
      # 2026-01-02 03:04:05.012345+00:00

.. _postgres-fts:

Full-Text Search
----------------

Postgresql full-text search uses the ``tsvector`` and ``tsquery`` types.
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

The :func:`Match` function will automatically convert the left-hand operand
to a ``tsvector``, and the right-hand operand to a ``tsquery``. For better
performance, create a ``GIN`` index:

.. code-block:: sql

   CREATE INDEX posts_fts ON post USING gin(to_tsvector('english', body));

**Dedicated column** - better performance:

.. code-block:: python

   class Post(Model):
       body = TextField()
       search_content = TSVectorField()  # Automatically gets a GIN index.

   # Store a post and populate the search vector:
   Post.create(
       body=body_text,
       search_content=fn.to_tsvector(body_text))

   # Search:
   Post.select().where(Post.search_content.match('python postgresql'))

   # Search using expressions:
   terms = 'python & (sqlite | postgres)'
   Post.select().where(Post.search_content.match(terms))

For more information, see the `Postgres full-text search docs <https://www.postgresql.org/docs/current/textsearch.html>`_.

.. function:: Match(field, query)

   Generate a full-text search expression that converts ``field`` to
   ``tsvector`` and ``query`` to ``tsquery`` automatically.


.. class:: TSVectorField()

   Field type for storing pre-computed ``tsvector`` data. Automatically
   created with a GIN index (use ``index=False`` to disable).

   .. note::
      Data must be explicitly converted to ``tsvector`` on write using
      ``fn.to_tsvector()``.

   Example:

   .. code-block:: python

      class Post(Model):
          body = TextField()
          search_content = TSVectorField()

      Post.create(
          body=body_text,
          search_content=fn.to_tsvector(body_text))

      (Post
       .select()
       .where(Post.search_content.match('python & (sqlite | postgres)')))

   .. method:: match(query, language=None, plain=False)

      :param str query: Full-text search query.
      :param str language: Optional language name.
      :param bool plain: Use the plain (simple) query parser instead of the
          default one, which supports ``&``, ``|``, and ``!`` operators.

.. _postgres-server-side-cursors:

Server-Side Cursors
-------------------

For large result sets, server-side (named) cursors stream rows from the server
rather than loading the entire result into memory. Rows are fetched
transparently from the server as you iterate.

Refer to your driver documentation for details:

* `psycopg2 server-side cursors <https://www.psycopg.org/docs/usage.html#server-side-cursors>`__
* `psycopg3 server-side cursors <https://www.psycopg.org/psycopg3/docs/advanced/cursors.html#server-side-cursors>`__

.. note:: To use server-side (or named) cursors, you must be using :class:`PostgresqlExtDatabase`.

Wrap any SELECT query with :func:`ServerSide`:

.. code-block:: python

   from playhouse.postgres_ext import ServerSide

   # Must be in a transaction to use server-side cursors.
   with db.atomic():

       # Create a normal SELECT query.
       large_query = PageView.select()

       # Then wrap in `ServerSide` and iterate.
       for page_view in ServerSide(large_query):
           # Do something interesting.
           pass

       # At this point server side resources are released.

For more granular control or to close the cursor explicitly:

.. code-block:: python

   with db.atomic():
       large_query = PageView.select().order_by(PageView.id.desc())

       # Rows will be fetched 1000 at-a-time, but iteration is transparent.
       query = ServerSideQuery(query, array_size=1000)

       # Read 9500 rows then close server-side cursor.
       accum = []
       for i, obj in enumerate(query.iterator()):
           if i == 9500:
               break
           accum.append(obj)

       # Release server-side resource.
       query.close()

.. warning::
   Server-side cursors live only within a transaction. If you are using psycopg2
   (not psycopg3), cursors are declared ``WITH HOLD`` and must be fully
   exhausted or explicitly closed to release server resources.

.. function:: ServerSide(select_query)

   :param select_query: a :class:`SelectQuery` instance.
   :rtype generator:

   Wrap ``select_query`` in a transaction and iterate using :meth:`~SelectQuery.iterator`
   (disables row caching).

.. _crdb:

CockroachDB
-----------

`CockroachDB <https://www.cockroachlabs.com>`_ (CRDB) is compatible with
Postgresql's wire protocol and is well-supported by Peewee. Use the dedicated
:class:`CockroachDatabase` class rather than :class:`PostgresqlDatabase`
to get CRDB-specific handling.

.. code-block:: python

   from playhouse.cockroachdb import CockroachDatabase

   db = CockroachDatabase('my_app', user='root', host='10.8.0.1')

If you are using `Cockroach Cloud <https://cockroachlabs.cloud/>`_, you may
find it easier to specify the connection parameters using a connection-string:

.. code-block:: python

   db = CockroachDatabase('postgresql://root:secret@host:26257/defaultdb...')

SSL configuration:

.. code-block:: python

   db = CockroachDatabase(
       'my_app',
       user='root',
       host='10.8.0.1',
       sslmode='verify-full',
       sslrootcert='/path/to/root.crt')

   # Or, alternatively, specified as part of a connection-string:
   db = CockroachDatabase('postgresql://root:secret@host:26257/dbname'
                          '?sslmode=verify-full&sslrootcert=/path/to/root.crt'
                          '&options=--cluster=my-cluster-xyz')

Key differences from Postgresql
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* **No nested transactions.** CRDB does not support savepoints, so calling
  :meth:`~Database.atomic` inside another ``atomic()`` block raises an
  exception. Use :meth:`~Database.transaction` instead, which ignores
  nested calls and commits only when the outermost block exits.
* **Client-side retries.** CRDB may abort transactions due to contention.
  Use :meth:`~CockroachDatabase.run_transaction` for automatic retries.

Special field-types that may be useful when using CRDB:

* :class:`UUIDKeyField` - a primary-key field implementation that uses
  CRDB's ``UUID`` type with a default randomly-generated UUID.
* :class:`RowIDField` - a primary-key field implementation that uses CRDB's
  ``INT`` type with a default ``unique_rowid()``.
* :class:`JSONField` - same as the Postgres :class:`BinaryJSONField`, as
  CRDB treats all JSON as JSONB.
* :class:`ArrayField` - same as the Postgres extension (but does not support
  multi-dimensional arrays).

Transactions:

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

   from playhouse.cockroachdb import CockroachDatabase

   db = CockroachDatabase('my_app')

   def transfer_funds(from_id, to_id, amt):
       """
       Returns a 3-tuple of (success?, from balance, to balance). If there are
       not sufficient funds, then the original balances are returned.
       """
       def thunk(db_ref):
           src, dest = (Account
                        .select()
                        .where(Account.id.in_([from_id, to_id])))
           if src.id != from_id:
               src, dest = dest, src  # Swap order.

           # Cannot perform transfer, insufficient funds!
           if src.balance < amt:
               return False, src.balance, dest.balance

           # Update each account, returning the new balance.
           src, = (Account
                   .update(balance=Account.balance - amt)
                   .where(Account.id == from_id)
                   .returning(Account.balance)
                   .execute())
           dest, = (Account
                    .update(balance=Account.balance + amt)
                    .where(Account.id == to_id)
                    .returning(Account.balance)
                    .execute())
           return True, src.balance, dest.balance

       # Perform the queries that comprise a logical transaction. In the
       # event the transaction fails due to contention, it will be auto-
       # matically retried (up to 10 times).
       return db.run_transaction(thunk, max_attempts=10)

CRDB API
^^^^^^^^^

.. class:: CockroachDatabase(database, **kwargs)

   Subclass of :class:`PostgresqlDatabase` for CockroachDB.

   .. method:: run_transaction(callback, max_attempts=None, system_time=None, priority=None)

      :param callback: Callable accepting a single ``db`` argument.
          Must not manage the transaction itself. May be called multiple times.
      :param int max_attempts: Retry limit.
      :param datetime system_time: Execute ``AS OF SYSTEM TIME`` with respect
          to the given value.
      :param str priority: ``'low'``, ``'normal'``, or ``'high'``.
      :raises ExceededMaxAttempts: When ``max_attempts`` is exceeded.

      Execute SQL in a transaction with automatic client-side retries.

      User-provided ``callback``:

      * **Must** accept one parameter, the ``db`` instance representing the
        connection the transaction is running under.
      * **Must** not attempt to commit, rollback or otherwise manage the
        transaction.
      * **May** be called more than one time.
      * **Should** ideally only contain SQL operations.

      Additionally, the database must not have any open transactions at the
      time this function is called, as CRDB does not support nested
      transactions. Attempting to do so will raise a ``NotImplementedError``.


.. class:: PooledCockroachDatabase(database, **kwargs)

   Connection-pooling variant of :class:`CockroachDatabase`.


.. function:: run_transaction(db, callback, max_attempts=None, system_time=None, priority=None)

    Run SQL in a transaction with automatic client-side retries. See
    :meth:`CockroachDatabase.run_transaction` for details.

    .. note::
        This function is equivalent to the identically-named method on
        the :class:`CockroachDatabase` class.


CRDB-specific field types:

.. class:: UUIDKeyField()
   :noindex:

   UUID primary key auto-populated with CRDB's ``gen_random_uuid()``.

.. class:: RowIDField()
   :noindex:

   Integer primary key auto-populated with CRDB's ``unique_rowid()``.
