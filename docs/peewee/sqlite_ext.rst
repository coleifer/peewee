.. _sqlite_ext:

SQLite Extensions
=================

The default :py:class:`SqliteDatabase` already includes many SQLite-specific
features:

* :ref:`General notes on using SQLite <using_sqlite>`.
* :ref:`Configuring SQLite using PRAGMA statements <sqlite-pragma>`.
* :ref:`User-defined functions, aggregate and collations <sqlite-user-functions>`.
* :ref:`Locking modes for transactions <sqlite-locking>`.

The ``playhouse.sqlite_ext`` includes even more SQLite features, including:

* :ref:`Full-text search <sqlite-fts>`
* :ref:`JSON extension integration <sqlite-json1>`
* :ref:`Sqlite-specific field types <sqlite-fields>`

.. note::
   These features are also included in the ``playhouse.cysqlite_ext`` module and
   can be used interchangeably with :py:class:`CySqliteDatabase`.

Getting started
---------------

To get started with the features described in this document, you will want to
use the :py:class:`SqliteExtDatabase` class from the ``playhouse.sqlite_ext``
module or :py:class:`CySqliteDatabase` from ``playhouse.cysqlite_ext``.

Using :py:class:`SqliteExtDatabase`:

.. code-block:: python

    from playhouse.sqlite_ext import SqliteExtDatabase

    db = SqliteExtDatabase('my_app.db', pragmas=(
        ('cache_size', -1024 * 64),  # 64MB page-cache.
        ('journal_mode', 'wal'),  # Use WAL-mode (you should always use this!).
        ('foreign_keys', 1)))  # Enforce foreign-key constraints.

Using :py:class:`CySqliteDatabase`:

.. code-block:: python

    from playhouse.cysqlite_ext import CySqliteDatabase

    db = CySqliteDatabase('my_app.db', pragmas={
        'cache_size': -1024 * 64,  # 64MB page-cache.
        'journal_mode': 'wal',,  # Use WAL-mode (you should always use this!).
        'foreign_keys': 1})  # Enforce foreign-key constraints.

APIs
----

.. py:class:: SqliteExtDatabase(database, pragmas=None, timeout=5, rank_functions=True, regexp_function=False, json_contains=False)

    :param list pragmas: A list of 2-tuples containing pragma key and value to
        set every time a connection is opened.
    :param timeout: Set the busy-timeout on the SQLite driver (in seconds).
    :param bool rank_functions: Make search result ranking functions available.
    :param bool regexp_function: Make the REGEXP function available.
    :param bool json_contains: Make json_containts() function available.

    Extends :py:class:`SqliteDatabase` and inherits methods for declaring
    user-defined functions, pragmas, etc.

    .. attention::
        In past versions :py:class:`SqliteExtDatabase` contained additional
        functionality, but practically all of that functionality has been moved
        into the standard :py:class:`SqliteDatabase`. The only functionality
        that remains specific solely to ``SqliteExtDatabase`` is:

        * accepts ``__init__`` arguments to register full-text search ranking
          functions (enabled by default).
        * accepts ``__init__`` argument to register ``json_contains()``
          user-defined funciton.

.. _sqlite-fields:

.. py:class:: RowIDField()

    Primary-key field that corresponds to the SQLite ``rowid`` field. For more
    information, see the SQLite documentation on `rowid tables <https://www.sqlite.org/rowidtable.html>`_..

    Example:

    .. code-block:: python

        class Note(Model):
            rowid = RowIDField()  # Will be primary key.
            content = TextField()
            timestamp = TimestampField()


.. py:class:: DocIDField()

    Subclass of :py:class:`RowIDField` for use on virtual tables that
    specifically use the convention of ``docid`` for the primary key. As far as
    I know this only pertains to tables using the FTS3 and FTS4 full-text
    search extensions.

    .. attention::
        In FTS3 and FTS4, "docid" is simply an alias for "rowid". To reduce
        confusion, it's probably best to just always use :py:class:`RowIDField`
        and never use :py:class:`DocIDField`.

    .. code-block:: python

        class NoteIndex(FTSModel):
            docid = DocIDField()  # "docid" is used as an alias for "rowid".
            content = SearchField()

            class Meta:
                database = db


.. py:class:: AutoIncrementField()

    SQLite, by default, may reuse primary key values after rows are deleted. To
    ensure that the primary key is *always* monotonically increasing,
    regardless of deletions, you should use :py:class:`AutoIncrementField`.
    There is a small performance cost for this feature. For more information,
    see the SQLite docs on `autoincrement <https://sqlite.org/autoinc.html>`_.


.. py:class:: ISODateTimeField()

    SQLite does not have a native DateTime data-type. Python ``datetime``
    objects are stored as strings by default. This subclass of
    :py:class:`DateTimeField` ensures that the UTC offset is stored properly
    for tz-aware datetimes and read-back properly when decoding row data.

.. _sqlite-json1:

.. py:class:: JSONField(json_dumps=None, json_loads=None, ...)

    Field class suitable for storing JSON data, with special methods designed
    to work with the `json1 extension <https://sqlite.org/json1.html>`_.

    SQLite 3.9.0 added `JSON support <https://www.sqlite.org/json1.html>`_ in
    the form of an extension library. The SQLite json1 extension provides a
    number of helper functions for working with JSON data. These APIs are
    exposed as methods of a special field-type, :py:class:`JSONField`.

    To access or modify specific object keys or array indexes in a JSON
    structure, you can treat the :py:class:`JSONField` as if it were a
    dictionary/list.

    :param json_dumps: (optional) function for serializing data to JSON
        strings. If not provided, will use the stdlib ``json.dumps``.
    :param json_loads: (optional) function for de-serializing JSON to Python
        objects. If not provided, will use the stdlib ``json.loads``.

    .. note::
        To customize the JSON serialization or de-serialization, you can
        specify a custom ``json_dumps`` and ``json_loads`` callables. These
        functions should accept a single paramter: the object to serialize, and
        the JSON string, respectively. To modify the parameters of the stdlib
        JSON functions, you can use ``functools.partial``:

        .. code-block:: python

            # Do not escape unicode code-points.
            my_json_dumps = functools.partial(json.dumps, ensure_ascii=False)

            class SomeModel(Model):
                # Specify our custom serialization function.
                json_data = JSONField(json_dumps=my_json_dumps)

    Let's look at some examples of using the SQLite json1 extension with
    Peewee. Here we'll prepare a database and a simple model for testing the
    `json1 extension <http://sqlite.org/json1.html>`_:

    .. code-block:: pycon

        >>> from playhouse.sqlite_ext import *
        >>> db = SqliteExtDatabase(':memory:')
        >>> class KV(Model):
        ...     key = TextField()
        ...     value = JSONField()
        ...     class Meta:
        ...         database = db
        ...

        >>> KV.create_table()

    Storing data works as you might expect. There's no need to serialize
    dictionaries or lists as JSON, as this is done automatically by Peewee:

    .. code-block:: pycon

        >>> KV.create(key='a', value={'k1': 'v1'})
        <KV: 1>
        >>> KV.get(KV.key == 'a').value
        {'k1': 'v1'}

    We can access specific parts of the JSON data using dictionary lookups:

    .. code-block:: pycon

        >>> KV.get(KV.value['k1'] == 'v1').key
        'a'

    It's possible to update a JSON value in-place using the :py:meth:`~JSONField.update`
    method. Note that "k1=v1" is preserved:

    .. code-block:: pycon

        >>> KV.update(value=KV.value.update({'k2': 'v2', 'k3': 'v3'})).execute()
        1
        >>> KV.get(KV.key == 'a').value
        {'k1': 'v1', 'k2': 'v2', 'k3': 'v3'}

    We can also update existing data atomically, or remove keys by setting
    their value to ``None``. In the following example, we'll update the value
    of "k1" and remove "k3" ("k2" will not be modified):

    .. code-block:: pycon

        >>> KV.update(value=KV.value.update({'k1': 'v1-x', 'k3': None})).execute()
        1
        >>> KV.get(KV.key == 'a').value
        {'k1': 'v1-x', 'k2': 'v2'}

    We can also set individual parts of the JSON data using the :py:meth:`~JSONField.set` method:

    .. code-block:: pycon

        >>> KV.update(value=KV.value['k1'].set('v1')).execute()
        1
        >>> KV.get(KV.key == 'a').value
        {'k1': 'v1', 'k2': 'v2'}

    The :py:meth:`~JSONField.set` method can also be used with objects, in
    addition to scalar values:

    .. code-block:: pycon

        >>> KV.update(value=KV.value['k2'].set({'x2': 'y2'})).execute()
        1
        >>> KV.get(KV.key == 'a').value
        {'k1': 'v1', 'k2': {'x2': 'y2'}}

    Individual parts of the JSON data can be removed atomically as well, using
    :py:meth:`~JSONField.remove`:

    .. code-block:: pycon

        >>> KV.update(value=KV.value['k2'].remove()).execute()
        1
        >>> KV.get(KV.key == 'a').value
        {'k1': 'v1'}

    We can also get the type of value stored at a specific location in the JSON
    data using the :py:meth:`~JSONField.json_type` method:

    .. code-block:: pycon

        >>> KV.select(KV.value.json_type(), KV.value['k1'].json_type()).tuples()[:]
        [('object', 'text')]

    Let's add a nested value and then see how to iterate through it's contents
    recursively using the :py:meth:`~JSONField.tree` method:

    .. code-block:: pycon

        >>> KV.create(key='b', value={'x1': {'y1': 'z1', 'y2': 'z2'}, 'x2': [1, 2]})
        <KV: 2>
        >>> tree = KV.value.tree().alias('tree')
        >>> query = KV.select(KV.key, tree.c.fullkey, tree.c.value).from_(KV, tree)
        >>> query.tuples()[:]
        [('a', '$', {'k1': 'v1'}),
         ('a', '$.k1', 'v1'),
         ('b', '$', {'x1': {'y1': 'z1', 'y2': 'z2'}, 'x2': [1, 2]}),
         ('b', '$.x2', [1, 2]),
         ('b', '$.x2[0]', 1),
         ('b', '$.x2[1]', 2),
         ('b', '$.x1', {'y1': 'z1', 'y2': 'z2'}),
         ('b', '$.x1.y1', 'z1'),
         ('b', '$.x1.y2', 'z2')]

    The :py:meth:`~JSONField.tree` and :py:meth:`~JSONField.children` methods
    are powerful. For more information on how to utilize them, see the
    `json1 extension documentation <http://sqlite.org/json1.html#jtree>`_.

    Also note, that :py:class:`JSONField` lookups can be chained:

    .. code-block:: pycon

        >>> query = KV.select().where(KV.value['x1']['y1'] == 'z1')
        >>> for obj in query:
        ...     print(obj.key, obj.value)
        ...

        'b', {'x1': {'y1': 'z1', 'y2': 'z2'}, 'x2': [1, 2]}

    For more information, refer to the `sqlite json1 documentation <http://sqlite.org/json1.html>`_.

    .. py:method:: __getitem__(item)

        :param item: Access a specific key or array index in the JSON data.
        :return: a special object exposing access to the JSON data.
        :rtype: JSONPath

        Access a specific key or array index in the JSON data. Returns a
        :py:class:`JSONPath` object, which exposes convenient methods for
        reading or modifying a particular part of a JSON object.

        Example:

        .. code-block:: python

            # If metadata contains {"tags": ["list", "of", "tags"]}, we can
            # extract the first tag in this way:
            Post.select(Post, Post.metadata['tags'][0].alias('first_tag'))

        For more examples see the :py:class:`JSONPath` API documentation.

    .. py:method:: extract(*paths)

        :param paths: One or more JSON paths to extract.

        Extract the value(s) at the specified JSON paths. If multiple paths are
        provided, then Sqlite will return the values as a ``list``.

    .. py:method:: extract_json(path)

        :param str path: JSON path

        Extract the value at the specified path as a JSON data-type. This
        corresponds to the ``->`` operator added in Sqlite 3.38.

    .. py:method:: extract_text(path)

        :param str path: JSON path

        Extract the value at the specified path as a SQL data-type. This
        corresponds to the ``->>`` operator added in Sqlite 3.38.

    .. py:method:: set(value, as_json=None)

        :param value: a scalar value, list, or dictionary.
        :param bool as_json: force the value to be treated as JSON, in which
            case it will be serialized as JSON in Python beforehand. By
            default, lists and dictionaries are treated as JSON to be
            serialized, while strings and integers are passed as-is.

        Set the value stored in a :py:class:`JSONField`.

        Uses the `json_set() <http://sqlite.org/json1.html#jset>`_ function
        from the json1 extension.

    .. py:method:: replace(value, as_json=None)

        :param value: a scalar value, list, or dictionary.
        :param bool as_json: force the value to be treated as JSON, in which
            case it will be serialized as JSON in Python beforehand. By
            default, lists and dictionaries are treated as JSON to be
            serialized, while strings and integers are passed as-is.

        Replace the existing value stored in a :py:class:`JSONField`.

        Uses the `json_replace() <http://sqlite.org/json1.html#jset>`_ function
        from the json1 extension.

    .. py:method:: insert(value, as_json=None)

        :param value: a scalar value, list, or dictionary.
        :param bool as_json: force the value to be treated as JSON, in which
            case it will be serialized as JSON in Python beforehand. By
            default, lists and dictionaries are treated as JSON to be
            serialized, while strings and integers are passed as-is.

        Insert value into :py:class:`JSONField`.

        Uses the `json_insert() <http://sqlite.org/json1.html#jset>`_ function
        from the json1 extension.

    .. py:method:: append(value, as_json=None)

        :param value: a scalar value, list, or dictionary.
        :param bool as_json: force the value to be treated as JSON, in which
            case it will be serialized as JSON in Python beforehand. By
            default, lists and dictionaries are treated as JSON to be
            serialized, while strings and integers are passed as-is.

        Append to the array stored in a :py:class:`JSONField`.

        Uses the `json_set() <http://sqlite.org/json1.html#jset>`_ function
        from the json1 extension.

    .. py:method:: update(data)

        :param data: a scalar value, list or dictionary to merge with the data
            currently stored in a :py:class:`JSONField`. To remove a particular
            key, set that key to ``None`` in the updated data.

        Merge new data into the JSON value using the RFC-7396 MergePatch
        algorithm to apply a patch (``data`` parameter) against the column
        data. MergePatch can add, modify, or delete elements of a JSON object,
        which means :py:meth:`~JSONField.update` is a generalized replacement
        for both :py:meth:`~JSONField.set` and :py:meth:`~JSONField.remove`.
        MergePatch treats JSON array objects as atomic, so ``update()`` cannot
        append to an array, nor modify individual elements of an array.

        For more information as well as examples, see the SQLite `json_patch() <http://sqlite.org/json1.html#jpatch>`_
        function documentation.

    .. py:method:: remove()

        Remove the data stored in the :py:class:`JSONField`.

        Uses the `json_remove <https://www.sqlite.org/json1.html#jrm>`_ function
        from the json1 extension.

    .. py:method:: json_type()

        Return a string identifying the type of value stored in the column.

        The type returned will be one of:

        * object
        * array
        * integer
        * real
        * true
        * false
        * text
        * null  <-- the string "null" means an actual NULL value
        * NULL  <-- an actual NULL value means the path was not found

        Uses the `json_type <https://www.sqlite.org/json1.html#jtype>`_
        function from the json1 extension.

    .. py:method:: length()

        Return the length of the array stored in the column.

        Uses the `json_array_length <https://www.sqlite.org/json1.html#jarraylen>`_
        function from the json1 extension.

    .. py:method:: children()

        The ``children`` function corresponds to ``json_each``, a table-valued
        function that walks the JSON value provided and returns the immediate
        children of the top-level array or object. If a path is specified, then
        that path is treated as the top-most element.

        The rows returned by calls to ``children()`` have the following
        attributes:

        * ``key``: the key of the current element relative to its parent.
        * ``value``: the value of the current element.
        * ``type``: one of the data-types (see :py:meth:`~JSONField.json_type`).
        * ``atom``: the scalar value for primitive types, ``NULL`` for arrays and objects.
        * ``id``: a unique ID referencing the current node in the tree.
        * ``parent``: the ID of the containing node.
        * ``fullkey``: the full path describing the current element.
        * ``path``: the path to the container of the current row.

        Internally this method uses the `json_each <https://www.sqlite.org/json1.html#jeach>`_
        (documentation link) function from the json1 extension.

        Example usage (compare to :py:meth:`~JSONField.tree` method):

        .. code-block:: python

            class KeyData(Model):
                key = TextField()
                data = JSONField()

            KeyData.create(key='a', data={'k1': 'v1', 'x1': {'y1': 'z1'}})
            KeyData.create(key='b', data={'x1': {'y1': 'z1', 'y2': 'z2'}})

            # We will query the KeyData model for the key and all the
            # top-level keys and values in it's data field.
            kd = KeyData.data.children().alias('children')
            query = (KeyData
                     .select(kd.c.key, kd.c.value, kd.c.fullkey)
                     .from_(KeyData, kd)
                     .order_by(kd.c.key)
                     .tuples())
            print(query[:])

            # PRINTS:
            [('a', 'k1', 'v1',                    '$.k1'),
             ('a', 'x1', '{"y1":"z1"}',           '$.x1'),
             ('b', 'x1', '{"y1":"z1","y2":"z2"}', '$.x1')]

    .. py:method:: tree()

        The ``tree`` function corresponds to ``json_tree``, a table-valued
        function that recursively walks the JSON value provided and returns
        information about the keys at each level. If a path is specified, then
        that path is treated as the top-most element.

        The rows returned by calls to ``tree()`` have the same attributes as
        rows returned by calls to :py:meth:`~JSONField.children`:

        * ``key``: the key of the current element relative to its parent.
        * ``value``: the value of the current element.
        * ``type``: one of the data-types (see :py:meth:`~JSONField.json_type`).
        * ``atom``: the scalar value for primitive types, ``NULL`` for arrays and objects.
        * ``id``: a unique ID referencing the current node in the tree.
        * ``parent``: the ID of the containing node.
        * ``fullkey``: the full path describing the current element.
        * ``path``: the path to the container of the current row.

        Internally this method uses the `json_tree <https://www.sqlite.org/json1.html#jtree>`_
        (documentation link) function from the json1 extension.

        Example usage:

        .. code-block:: python

            class KeyData(Model):
                key = TextField()
                data = JSONField()

            KeyData.create(key='a', data={'k1': 'v1', 'x1': {'y1': 'z1'}})
            KeyData.create(key='b', data={'x1': {'y1': 'z1', 'y2': 'z2'}})

            # We will query the KeyData model for the key and all the
            # keys and values in it's data field, recursively.
            kd = KeyData.data.tree().alias('tree')
            query = (KeyData
                     .select(kd.c.key, kd.c.value, kd.c.fullkey)
                     .from_(KeyData, kd)
                     .order_by(kd.c.key)
                     .tuples())
            print(query[:])

            # PRINTS:
            [('a',  None,  '{"k1":"v1","x1":{"y1":"z1"}}', '$'),
             ('b',  None,  '{"x1":{"y1":"z1","y2":"z2"}}', '$'),
             ('a',  'k1',  'v1',                           '$.k1'),
             ('a',  'x1',  '{"y1":"z1"}',                  '$.x1'),
             ('b',  'x1',  '{"y1":"z1","y2":"z2"}',        '$.x1'),
             ('a',  'y1',  'z1',                           '$.x1.y1'),
             ('b',  'y1',  'z1',                           '$.x1.y1'),
             ('b',  'y2',  'z2',                           '$.x1.y2')]


.. py:class:: JSONPath(field, path=None)

    :param JSONField field: the field object we intend to access.
    :param tuple path: Components comprising the JSON path.

    A convenient, Pythonic way of representing JSON paths for use with
    :py:class:`JSONField`.

    The ``JSONPath`` object implements ``__getitem__``, accumulating path
    components, which it can turn into the corresponding json-path expression.

    .. py:method:: __getitem__(item)

        :param item: Access a sub-key key or array index.
        :return: a :py:class:`JSONPath` representing the new path.

        Access a sub-key or array index in the JSON data. Returns a
        :py:class:`JSONPath` object, which exposes convenient methods for
        reading or modifying a particular part of a JSON object.

        Example:

        .. code-block:: python

            # If metadata contains {"tags": ["list", "of", "tags"]}, we can
            # extract the first tag in this way:
            first_tag = Post.metadata['tags'][0]
            query = (Post
                     .select(Post, first_tag.alias('first_tag'))
                     .order_by(first_tag))

    .. py:method:: set(value, as_json=None)

        :param value: a scalar value, list, or dictionary.
        :param bool as_json: force the value to be treated as JSON, in which
            case it will be serialized as JSON in Python beforehand. By
            default, lists and dictionaries are treated as JSON to be
            serialized, while strings and integers are passed as-is.

        Set the value at the given location in the JSON data.

        Uses the `json_set() <http://sqlite.org/json1.html#jset>`_ function
        from the json1 extension.

    .. py:method:: replace(value, as_json=None)

        :param value: a scalar value, list, or dictionary.
        :param bool as_json: force the value to be treated as JSON, in which
            case it will be serialized as JSON in Python beforehand. By
            default, lists and dictionaries are treated as JSON to be
            serialized, while strings and integers are passed as-is.

        Replace the existing value at the given location in the JSON data.

        Uses the `json_replace() <http://sqlite.org/json1.html#jset>`_ function
        from the json1 extension.

    .. py:method:: insert(value, as_json=None)

        :param value: a scalar value, list, or dictionary.
        :param bool as_json: force the value to be treated as JSON, in which
            case it will be serialized as JSON in Python beforehand. By
            default, lists and dictionaries are treated as JSON to be
            serialized, while strings and integers are passed as-is.

        Insert a new value at the given location in the JSON data.

        Uses the `json_insert() <http://sqlite.org/json1.html#jset>`_ function
        from the json1 extension.

    .. py:method:: append(value, as_json=None)

        :param value: a scalar value, list, or dictionary.
        :param bool as_json: force the value to be treated as JSON, in which
            case it will be serialized as JSON in Python beforehand. By
            default, lists and dictionaries are treated as JSON to be
            serialized, while strings and integers are passed as-is.

        Append to the array stored at the given location in the JSON data.

        Uses the `json_set() <http://sqlite.org/json1.html#jset>`_ function
        from the json1 extension.

    .. py:method:: update(data)

        :param data: a scalar value, list or dictionary to merge with the data
            at the given location in the JSON data. To remove a particular key,
            set that key to ``None`` in the updated data.

        Merge new data into the JSON value using the RFC-7396 MergePatch
        algorithm to apply a patch (``data`` parameter) against the column
        data. MergePatch can add, modify, or delete elements of a JSON object,
        which means :py:meth:`~JSONPath.update` is a generalized replacement
        for both :py:meth:`~JSONPath.set` and :py:meth:`~JSONPath.remove`.
        MergePatch treats JSON array objects as atomic, so ``update()`` cannot
        append to an array, nor modify individual elements of an array.

        For more information as well as examples, see the SQLite `json_patch() <http://sqlite.org/json1.html#jpatch>`_
        function documentation.

    .. py:method:: remove()

        Remove the data stored in at the given location in the JSON data.

        Uses the `json_type <https://www.sqlite.org/json1.html#jrm>`_ function
        from the json1 extension.

    .. py:method:: json_type()

        Return a string identifying the type of value stored at the given
        location in the JSON data.

        The type returned will be one of:

        * object
        * array
        * integer
        * real
        * true
        * false
        * text
        * null  <-- the string "null" means an actual NULL value
        * NULL  <-- an actual NULL value means the path was not found

        Uses the `json_type <https://www.sqlite.org/json1.html#jtype>`_
        function from the json1 extension.

    .. py:method:: length()

        Return the length of the array stored at the given location in the JSON
        data.

        Uses the `json_array_length <https://www.sqlite.org/json1.html#jarraylen>`_
        function from the json1 extension.

    .. py:method:: children()

        Table-valued function that exposes the direct descendants of a JSON
        object at the given location. See also :py:meth:`JSONField.children`.

    .. py:method:: tree()

        Table-valued function that exposes all descendants, recursively, of a
        JSON object at the given location. See also :py:meth:`JSONField.tree`.


.. py:class:: JSONBField(json_dumps=None, json_loads=None, ...)

    Field-class suitable for use with data stored on-disk in ``jsonb`` format
    (available starting Sqlite 3.45.0). This field-class should be used with
    care, as the data may be returned in it's encoded format depending on how
    you query it. For example:

    .. code-block:: pycon

        >>> KV.create(key='a', value={'k1': 'v1'})
        <KV: 1>
        >>> KV.get(KV.key == 'a').value
        b"l'k1'v1"

    To get the JSON value, it is necessary to use ``fn.json()`` or the helper
    :py:meth:`JSONBField.json` method:

    .. code-block:: pycon

        >>> kv = KV.select(KV.value.json()).get()
        >>> kv.value
        {'k1': 'v1'}


.. py:class:: JSONBPath(field, path=None)

    Subclass of :py:class:`JSONPath` for working with ``jsonb`` data.


.. py:class:: SearchField(unindexed=False, column_name=None)

    Field-class to be used for columns on models representing full-text search
    virtual tables. The full-text search extensions prohibit the specification
    of any typing or constraints on columns. This behavior is enforced by the
    :py:class:`SearchField`, which raises an exception if any configuration is
    attempted that would be incompatible with the full-text search extensions.

    Example model for document search index (timestamp is stored in the table
    but it's data is not searchable):

    .. code-block:: python

        class DocumentIndex(FTSModel):
            title = SearchField()
            content = SearchField()
            tags = SearchField()
            timestamp = SearchField(unindexed=True)

    .. py:method:: match(term)

        :param str term: full-text search query/terms
        :return: a :py:class:`Expression` corresponding to the ``MATCH``
            operator.

        Sqlite's full-text search supports searching either the full table,
        including all indexed columns, **or** searching individual columns. The
        :py:meth:`~SearchField.match` method can be used to restrict search to
        a single column:

        .. code-block:: python

            class SearchIndex(FTSModel):
                title = SearchField()
                body = SearchField()

            # Search *only* the title field and return results ordered by
            # relevance, using bm25.
            query = (SearchIndex
                     .select(SearchIndex, SearchIndex.bm25().alias('score'))
                     .where(SearchIndex.title.match('python'))
                     .order_by(SearchIndex.bm25()))

        To instead search *all* indexed columns, use the
        :py:meth:`FTSModel.match` method:

        .. code-block:: python

            # Searches *both* the title and body and return results ordered by
            # relevance, using bm25.
            query = (SearchIndex
                     .select(SearchIndex, SearchIndex.bm25().alias('score'))
                     .where(SearchIndex.match('python'))
                     .order_by(SearchIndex.bm25()))

    .. py:method:: highlight(left, right)

        :param str left: opening tag for highlight, e.g. ``'<b>'``
        :param str right: closing tag for highlight, e.g. ``'</b>'``

        When performing a search using the ``MATCH`` operator, FTS5 can return
        text highlighting matches in a given column.

        .. code-block:: python

            # Search for items matching string 'python' and return the title
            # highlighted with square brackets.
            query = (SearchIndex
                     .search('python')
                     .select(SearchIndex.title.highlight('[', ']').alias('hi')))

            for result in query:
                print(result.hi)

            # For example, might print:
            # Learn [python] the hard way

    .. py:method:: snippet(left, right, over_length='...', max_tokens=16)

        :param str left: opening tag for highlight, e.g. ``'<b>'``
        :param str right: closing tag for highlight, e.g. ``'</b>'``
        :param str over_length: text to prepend or append when snippet exceeds
            the maximum number of tokens.
        :param int max_tokens: max tokens returned, **must be 1 - 64**.

        When performing a search using the ``MATCH`` operator, FTS5 can return
        text with a snippet containing the highlighted match in a given column.

        .. code-block:: python

            # Search for items matching string 'python' and return the title
            # highlighted with square brackets.
            query = (SearchIndex
                     .search('python')
                     .select(SearchIndex.title.snippet('[', ']').alias('snip')))

            for result in query:
                print(result.snip)


.. py:class:: VirtualModel()

    Model class designed to be used to represent virtual tables. The default
    metadata settings are slightly different, to match those frequently used by
    virtual tables.

    Metadata options:

    * ``arguments`` - arguments passed to the virtual table constructor.
    * ``extension_module`` - name of extension to use for virtual table.
    * ``options`` - a dictionary of settings to apply in virtual table
          constructor.
    * ``primary_key`` - defaults to ``False``, indicating no primary key.

    These all are combined in the following way:

    .. code-block:: sql

        CREATE VIRTUAL TABLE <table_name>
        USING <extension_module>
        ([prefix_arguments, ...] fields, ... [arguments, ...], [options...])

.. _sqlite-fts:

.. py:class:: FTSModel()

    Subclass of :py:class:`VirtualModel` to be used with the `FTS3 and FTS4 <https://sqlite.org/fts3.html>`_
    full-text search extensions.

    FTSModel subclasses should be defined normally, however there are a couple
    caveats:

    * Unique constraints, not null constraints, check constraints and foreign
      keys are not supported.
    * Indexes on fields and multi-column indexes are ignored completely
    * Sqlite will treat all column types as ``TEXT`` (although you
      can store other data types, Sqlite will treat them as text).
    * FTS models contain a ``rowid`` field which is automatically created and
      managed by SQLite (unless you choose to explicitly set it during model
      creation). Lookups on this column **are fast and efficient**.

    Given these constraints, it is strongly recommended that all fields
    declared on an ``FTSModel`` subclass be instances of
    :py:class:`SearchField` (though an exception is made for explicitly
    declaring a :py:class:`RowIDField`). Using :py:class:`SearchField` will
    help prevent you accidentally creating invalid column constraints. If you
    wish to store metadata in the index but would not like it to be included in
    the full-text index, then specify ``unindexed=True`` when instantiating the
    :py:class:`SearchField`.

    The only exception to the above is for the ``rowid`` primary key, which can
    be declared using :py:class:`RowIDField`. Lookups on the ``rowid`` are very
    efficient. If you are using FTS4 you can also use :py:class:`DocIDField`,
    which is an alias for the rowid (though there is no benefit to doing so).

    Because of the lack of secondary indexes, it usually makes sense to use
    the ``rowid`` primary key as a pointer to a row in a regular table. For
    example:

    .. code-block:: python

        class Document(Model):
            # Canonical source of data, stored in a regular table.
            author = ForeignKeyField(User, backref='documents')
            title = TextField(null=False, unique=True)
            content = TextField(null=False)
            timestamp = DateTimeField()

            class Meta:
                database = db

        class DocumentIndex(FTSModel):
            # Full-text search index.
            rowid = RowIDField()
            title = SearchField()
            content = SearchField()

            class Meta:
                database = db
                # Use the porter stemming algorithm to tokenize content.
                options = {'tokenize': 'porter'}

    To store a document in the document index, we will ``INSERT`` a row into
    the ``DocumentIndex`` table, manually setting the ``rowid`` so that it
    matches the primary-key of the corresponding ``Document``:

    .. code-block:: python

        def store_document(document):
            DocumentIndex.insert({
                DocumentIndex.rowid: document.id,
                DocumentIndex.title: document.title,
                DocumentIndex.content: document.content}).execute()

    To perform a search and return ranked results, we can query the
    ``Document`` table and join on the ``DocumentIndex``. This join will be
    efficient because lookups on an FTSModel's ``rowid`` field are fast:

    .. code-block:: python

        def search(phrase):
            # Query the search index and join the corresponding Document
            # object on each search result.
            return (Document
                    .select()
                    .join(
                        DocumentIndex,
                        on=(Document.id == DocumentIndex.rowid))
                    .where(DocumentIndex.match(phrase))
                    .order_by(DocumentIndex.bm25()))

    .. warning::
        All SQL queries on ``FTSModel`` classes will be full-table scans
        **except** full-text searches and ``rowid`` lookups.

    If the primary source of the content you are indexing exists in a separate
    table, you can save some disk space by instructing SQLite to not store an
    additional copy of the search index content. SQLite will still create the
    metadata and data-structures needed to perform searches on the content, but
    the content itself will not be stored in the search index.

    To accomplish this, you can specify a table or column using the ``content``
    option. The `FTS4 documentation <http://sqlite.org/fts3.html#section_6_2>`_
    has more information.

    Here is a short example illustrating how to implement this with peewee:

    .. code-block:: python

        class Blog(Model):
            title = TextField()
            pub_date = DateTimeField(default=datetime.datetime.now)
            content = TextField()  # We want to search this.

            class Meta:
                database = db

        class BlogIndex(FTSModel):
            content = SearchField()

            class Meta:
                database = db
                options = {'content': Blog.content}  # <-- specify data source.

        db.create_tables([Blog, BlogIndex])

        # Now, we can manage content in the BlogIndex. To populate the
        # search index:
        BlogIndex.rebuild()

        # Optimize the index.
        BlogIndex.optimize()

    The ``content`` option accepts either a single :py:class:`Field` or a
    :py:class:`Model` and can reduce the amount of storage used by the database
    file. However, content will need to be manually moved to/from the
    associated ``FTSModel``.

    .. py:classmethod:: match(term)

        :param term: Search term or expression.

        Generate a SQL expression representing a search for the given term or
        expression in the table. SQLite uses the ``MATCH`` operator to indicate
        a full-text search.

        Example:

        .. code-block:: python

            # Search index for "search phrase" and return results ranked
            # by relevancy using the BM25 algorithm.
            query = (DocumentIndex
                     .select()
                     .where(DocumentIndex.match('search phrase'))
                     .order_by(DocumentIndex.bm25()))
            for result in query:
                print('Result: %s' % result.title)

    .. py:classmethod:: search(term, weights=None, with_score=False, score_alias='score', explicit_ordering=False)

        :param str term: Search term to use.
        :param weights: A list of weights for the columns, ordered with respect
          to the column's position in the table. **Or**, a dictionary keyed by
          the field or field name and mapped to a value.
        :param with_score: Whether the score should be returned as part of
          the ``SELECT`` statement.
        :param str score_alias: Alias to use for the calculated rank score.
          This is the attribute you will use to access the score
          if ``with_score=True``.
        :param bool explicit_ordering: Order using full SQL function to
            calculate rank, as opposed to simply referencing the score alias
            in the ORDER BY clause.

        Shorthand way of searching for a term and sorting results by the
        quality of the match.

        .. note::
            This method uses a simplified algorithm for determining the
            relevance rank of results. For more sophisticated result ranking,
            use the :py:meth:`~FTSModel.search_bm25` method.

        .. code-block:: python

            # Simple search.
            docs = DocumentIndex.search('search term')
            for result in docs:
                print(result.title)

            # More complete example.
            docs = DocumentIndex.search(
                'search term',
                weights={'title': 2.0, 'content': 1.0},
                with_score=True,
                score_alias='search_score')
            for result in docs:
                print(result.title, result.search_score)

    .. py:classmethod:: search_bm25(term, weights=None, with_score=False, score_alias='score', explicit_ordering=False)

        :param str term: Search term to use.
        :param weights: A list of weights for the columns, ordered with respect
          to the column's position in the table. **Or**, a dictionary keyed by
          the field or field name and mapped to a value.
        :param with_score: Whether the score should be returned as part of
          the ``SELECT`` statement.
        :param str score_alias: Alias to use for the calculated rank score.
          This is the attribute you will use to access the score
          if ``with_score=True``.
        :param bool explicit_ordering: Order using full SQL function to
            calculate rank, as opposed to simply referencing the score alias
            in the ORDER BY clause.

        Shorthand way of searching for a term and sorting results by the
        quality of the match using the BM25 algorithm.

        .. attention::
            The BM25 ranking algorithm is only available for FTS4. If you are
            using FTS3, use the :py:meth:`~FTSModel.search` method instead.

    .. py:classmethod:: search_bm25f(term, weights=None, with_score=False, score_alias='score', explicit_ordering=False)

        Same as :py:meth:`FTSModel.search_bm25`, but using the BM25f variant
        of the BM25 ranking algorithm.

    .. py:classmethod:: search_lucene(term, weights=None, with_score=False, score_alias='score', explicit_ordering=False)

        Same as :py:meth:`FTSModel.search_bm25`, but using the result ranking
        algorithm from the Lucene search engine.

    .. py:classmethod:: rank(col1_weight, col2_weight...coln_weight)

        :param float col_weight: (Optional) weight to give to the *ith* column
            of the model. By default all columns have a weight of ``1.0``.

        Generate an expression that will calculate and return the quality of
        the search match. This ``rank`` can be used to sort the search results.
        A higher rank score indicates a better match.

        The ``rank`` function accepts optional parameters that allow you to
        specify weights for the various columns. If no weights are specified,
        all columns are considered of equal importance.

        .. note::
            The algorithm used by :py:meth:`~FTSModel.rank` is simple and
            relatively quick. For more sophisticated result ranking, use:

            * :py:meth:`~FTSModel.bm25`
            * :py:meth:`~FTSModel.bm25f`
            * :py:meth:`~FTSModel.lucene`

        .. code-block:: python

            query = (DocumentIndex
                     .select(
                         DocumentIndex,
                         DocumentIndex.rank().alias('score'))
                     .where(DocumentIndex.match('search phrase'))
                     .order_by(DocumentIndex.rank()))

            for search_result in query:
                print(search_result.title, search_result.score)

    .. py:classmethod:: bm25(col1_weight, col2_weight...coln_weight)

        :param float col_weight: (Optional) weight to give to the *ith* column
            of the model. By default all columns have a weight of ``1.0``.

        Generate an expression that will calculate and return the quality of
        the search match using the `BM25 algorithm <https://en.wikipedia.org/wiki/Okapi_BM25>`_.
        This value can be used to sort the search results, with higher scores
        corresponding to better matches.

        Like :py:meth:`~FTSModel.rank`, ``bm25`` function accepts optional
        parameters that allow you to specify weights for the various columns.
        If no weights are specified, all columns are considered of equal
        importance.

        .. attention::
            The BM25 result ranking algorithm requires FTS4. If you are using
            FTS3, use :py:meth:`~FTSModel.rank` instead.

        .. code-block:: python

            query = (DocumentIndex
                     .select(
                         DocumentIndex,
                         DocumentIndex.bm25().alias('score'))
                     .where(DocumentIndex.match('search phrase'))
                     .order_by(DocumentIndex.bm25()))

            for search_result in query:
                print(search_result.title, search_result.score)

        .. note::
            The above code example is equivalent to calling the
            :py:meth:`~FTSModel.search_bm25` method:

            .. code-block:: python

                query = DocumentIndex.search_bm25('search phrase', with_score=True)
                for search_result in query:
                    print(search_result.title, search_result.score)

    .. py:classmethod:: bm25f(col1_weight, col2_weight...coln_weight)

        Identical to :py:meth:`~FTSModel.bm25`, except that it uses the BM25f
        variant of the BM25 ranking algorithm.

    .. py:classmethod:: lucene(col1_weight, col2_weight...coln_weight)

        Identical to :py:meth:`~FTSModel.bm25`, except that it uses the Lucene
        search result ranking algorithm.

    .. py:classmethod:: rebuild()

        Rebuild the search index -- this only works when the ``content`` option
        was specified during table creation.

    .. py:classmethod:: optimize()

        Optimize the search index.


.. py:class:: FTS5Model()

    Subclass of :py:class:`VirtualModel` to be used with the `FTS5 <https://sqlite.org/fts5.html>`_
    full-text search extensions.

    FTS5Model subclasses should be defined normally, however there are a couple
    caveats:

    * FTS5 explicitly disallows specification of any constraints, data-type or
      indexes on columns. For that reason, all columns **must** be instances
      of :py:class:`SearchField`.
    * FTS5 models contain a ``rowid`` field which is automatically created and
      managed by SQLite (unless you choose to explicitly set it during model
      creation). Lookups on this column **are fast and efficient**.
    * Indexes on fields and multi-column indexes are not supported.

    The ``FTS5`` extension comes with a built-in implementation of the BM25
    ranking function. Therefore, the ``search`` and ``search_bm25`` methods
    have been overridden to use the builtin ranking functions rather than
    user-defined functions.

    .. py:classmethod:: fts5_installed()

        Return a boolean indicating whether the FTS5 extension is installed. If
        it is not installed, an attempt will be made to load the extension.

    .. py:classmethod:: search(term, weights=None, with_score=False, score_alias='score')

        :param str term: Search term to use.
        :param weights: A list of weights for the columns, ordered with respect
          to the column's position in the table. **Or**, a dictionary keyed by
          the field or field name and mapped to a value.
        :param with_score: Whether the score should be returned as part of
          the ``SELECT`` statement.
        :param str score_alias: Alias to use for the calculated rank score.
          This is the attribute you will use to access the score
          if ``with_score=True``.
        :param bool explicit_ordering: Order using full SQL function to
            calculate rank, as opposed to simply referencing the score alias
            in the ORDER BY clause.

        Shorthand way of searching for a term and sorting results by the
        quality of the match. The ``FTS5`` extension provides a built-in
        implementation of the BM25 algorithm, which is used to rank the results
        by relevance.

        Higher scores correspond to better matches.

        .. code-block:: python

            # Simple search.
            docs = DocumentIndex.search('search term')
            for result in docs:
                print(result.title)

            # More complete example.
            docs = DocumentIndex.search(
                'search term',
                weights={'title': 2.0, 'content': 1.0},
                with_score=True,
                score_alias='search_score')
            for result in docs:
                print(result.title, result.search_score)

    .. py:classmethod:: search_bm25(term, weights=None, with_score=False, score_alias='score')

        With FTS5, :py:meth:`~FTS5Model.search_bm25` is identical to the
        :py:meth:`~FTS5Model.search` method.

    .. py:classmethod:: rank(col1_weight, col2_weight...coln_weight)

        :param float col_weight: (Optional) weight to give to the *ith* column
            of the model. By default all columns have a weight of ``1.0``.

        Generate an expression that will calculate and return the quality of
        the search match using the `BM25 algorithm <https://en.wikipedia.org/wiki/Okapi_BM25>`_.
        This value can be used to sort the search results, with higher scores
        corresponding to better matches.

        The :py:meth:`~FTS5Model.rank` function accepts optional parameters
        that allow you to specify weights for the various columns.  If no
        weights are specified, all columns are considered of equal importance.

        .. code-block:: python

            query = (DocumentIndex
                     .select(
                         DocumentIndex,
                         DocumentIndex.rank().alias('score'))
                     .where(DocumentIndex.match('search phrase'))
                     .order_by(DocumentIndex.rank()))

            for search_result in query:
                print(search_result.title, search_result.score)

        .. note::
            The above code example is equivalent to calling the
            :py:meth:`~FTS5Model.search` method:

            .. code-block:: python

                query = DocumentIndex.search('search phrase', with_score=True)
                for search_result in query:
                    print(search_result.title, search_result.score)

    .. py:classmethod:: bm25(col1_weight, col2_weight...coln_weight)

        Because FTS5 provides built-in support for BM25, the
        :py:meth:`~FTS5Model.bm25` method is identical to the
        :py:meth:`~FTS5Model.rank` method.

    .. py:classmethod:: VocabModel(table_type='row'|'col'|'instance', table_name=None)

        :param str table_type: Either 'row', 'col' or 'instance'.
        :param table_name: Name for the vocab table. If not specified, will be
            "fts5tablename_v".

        Generate a model class suitable for accessing the `vocab table <http://sqlite.org/fts5.html#the_fts5vocab_virtual_table_module>`_
        corresponding to FTS5 search index.
