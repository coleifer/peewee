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
   * :ref:`server_side_cursors`

   :param str database: Name of database to connect to.
   :param bool server_side_cursors: Whether ``SELECT`` queries should utilize
       server-side cursors.
   :param bool register_hstore: Register the hstore extension.
   :param bool prefer_psycopg3: If both psycopg2 and psycopg3 are installed,
       instruct Peewee to prefer psycopg3.

   When using ``server_side_cursors`` be sure to wrap your queries with :func:`ServerSide`.

.. _postgres-json:

JSON Support
------------

Peewee provides two JSON field types for PostgreSQL:

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

PostgreSQL's `hstore <https://www.postgresql.org/docs/current/hstore.html>`_
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

   Stores a PostgreSQL array of the given field type.

   :param field_class: a subclass of :class:`Field`, e.g. :class:`IntegerField`.
   :param dict field_kwargs: arguments to initialize ``field_class``.
   :param int dimensions: Number of array dimensions.
   :param bool convert_values: Apply ``field_class`` value conversion to
       retrieved data.

   .. note::
      By default ArrayField will use a GIN index. To disable this, initialize
      the field with ``index=False``.

   .. code-block:: python

      class Post(Model):
          tags = ArrayField(CharField)

      Post.create(tags=['python', 'peewee', 'postgresql'])
      Post.create(tags=['python', 'sqlite'])

      Post.select(Post.tags[0].alias('first_tag'))

      # Get a slice:
      Post.select(Post.tags[:2].alias('first_two'))

   .. method:: contains(*items)

      Filter rows where the array contains all of the given values.

   .. method:: contains_any(*items)

      Filter rows where the array contains any of the given values.
