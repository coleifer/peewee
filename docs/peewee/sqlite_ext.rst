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
* :ref:`Closure table extension support <sqlite-closure-table>`
* :ref:`LSM1 extension support <sqlite-lsm1>`
* :ref:`User-defined table functions <sqlite-vtfunc>`
* Support for online backups using backup API: :py:meth:`~CSqliteExtDatabase.backup_to_file`
* :ref:`BLOB API support, for efficient binary data storage <sqlite-blob>`.
* :ref:`Additional helpers <sqlite-extras>`, including bloom filter, more.

Getting started
---------------

To get started with the features described in this document, you will want to
use the :py:class:`SqliteExtDatabase` class from the ``playhouse.sqlite_ext``
module. Furthermore, some features require the ``playhouse._sqlite_ext`` C
extension -- these features will be noted in the documentation.

Instantiating a :py:class:`SqliteExtDatabase`:

.. code-block:: python

    from playhouse.sqlite_ext import SqliteExtDatabase

    db = SqliteExtDatabase('my_app.db', pragmas=(
        ('cache_size', -1024 * 64),  # 64MB page-cache.
        ('journal_mode', 'wal'),  # Use WAL-mode (you should always use this!).
        ('foreign_keys', 1)))  # Enforce foreign-key constraints.


APIs
----

.. py:class:: SqliteExtDatabase(database[, pragmas=None[, timeout=5[, c_extensions=None[, rank_functions=True[, hash_functions=False[, regexp_function=False[, bloomfilter=False]]]]]]])

    :param list pragmas: A list of 2-tuples containing pragma key and value to
        set every time a connection is opened.
    :param timeout: Set the busy-timeout on the SQLite driver (in seconds).
    :param bool c_extensions: Declare that C extension speedups must/must-not
        be used. If set to ``True`` and the extension module is not available,
        will raise an :py:class:`ImproperlyConfigured` exception.
    :param bool rank_functions: Make search result ranking functions available.
    :param bool hash_functions: Make hashing functions available (md5, sha1, etc).
    :param bool regexp_function: Make the REGEXP function available.
    :param bool bloomfilter: Make the :ref:`bloom filter <sqlite-extras>` available.

    Extends :py:class:`SqliteDatabase` and inherits methods for declaring
    user-defined functions, pragmas, etc.

.. py:class:: CSqliteExtDatabase(database[, pragmas=None[, timeout=5[, c_extensions=None[, rank_functions=True[, hash_functions=False[, regexp_function=False[, bloomfilter=False[, replace_busy_handler=False]]]]]]]])

    :param list pragmas: A list of 2-tuples containing pragma key and value to
        set every time a connection is opened.
    :param timeout: Set the busy-timeout on the SQLite driver (in seconds).
    :param bool c_extensions: Declare that C extension speedups must/must-not
        be used. If set to ``True`` and the extension module is not available,
        will raise an :py:class:`ImproperlyConfigured` exception.
    :param bool rank_functions: Make search result ranking functions available.
    :param bool hash_functions: Make hashing functions available (md5, sha1, etc).
    :param bool regexp_function: Make the REGEXP function available.
    :param bool bloomfilter: Make the :ref:`bloom filter <sqlite-extras>` available.
    :param bool replace_busy_handler: Use a smarter busy-handler implementation.

    Extends :py:class:`SqliteExtDatabase` and requires that the
    ``playhouse._sqlite_ext`` extension module be available.

    .. py:method:: on_commit(fn)

        Register a callback to be executed whenever a transaction is committed
        on the current connection. The callback accepts no parameters and the
        return value is ignored.

        However, if the callback raises a :py:class:`ValueError`, the
        transaction will be aborted and rolled-back.

        Example:

        .. code-block:: python

            db = CSqliteExtDatabase(':memory:')

            @db.on_commit
            def on_commit():
                logger.info('COMMITing changes')

    .. py:method:: on_rollback(fn)

        Register a callback to be executed whenever a transaction is rolled
        back on the current connection. The callback accepts no parameters and
        the return value is ignored.

        Example:

        .. code-block:: python

            @db.on_rollback
            def on_rollback():
                logger.info('Rolling back changes')

    .. py:method:: on_update(fn)

        Register a callback to be executed whenever the database is written to
        (via an *UPDATE*, *INSERT* or *DELETE* query). The callback should
        accept the following parameters:

        * ``query`` - the type of query, either *INSERT*, *UPDATE* or *DELETE*.
        * database name - the default database is named *main*.
        * table name - name of table being modified.
        * rowid - the rowid of the row being modified.

        The callback's return value is ignored.

        Example:

        .. code-block:: python

            db = CSqliteExtDatabase(':memory:')

            @db.on_update
            def on_update(query_type, db, table, rowid):
                # e.g. INSERT row 3 into table users.
                logger.info('%s row %s into table %s', query_type, rowid, table)

    .. py:method:: changes()

        Return the number of rows modified in the currently-open transaction.

    .. py:attribute:: autocommit

        Property which returns a boolean indicating if autocommit is enabled.
        By default, this value will be ``True`` except when inside a
        transaction (or :py:meth:`~Database.atomic` block).

        Example:

        .. code-block:: pycon

            >>> db = CSqliteExtDatabase(':memory:')
            >>> db.autocommit
            True
            >>> with db.atomic():
            ...     print(db.autocommit)
            ...
            False
            >>> db.autocommit
            True

    .. py:method:: backup(destination[, pages=None, name=None, progress=None])

        :param SqliteDatabase destination: Database object to serve as
            destination for the backup.
        :param int pages: Number of pages per iteration. Default value of -1
            indicates all pages should be backed-up in a single step.
        :param str name: Name of source database (may differ if you used ATTACH
            DATABASE to load multiple databases). Defaults to "main".
        :param progress: Progress callback, called with three parameters: the
            number of pages remaining, the total page count, and whether the
            backup is complete.

        Example:

        .. code-block:: python

            master = CSqliteExtDatabase('master.db')
            replica = CSqliteExtDatabase('replica.db')

            # Backup the contents of master to replica.
            master.backup(replica)

    .. py:method:: backup_to_file(filename[, pages, name, progress])

        :param filename: Filename to store the database backup.
        :param int pages: Number of pages per iteration. Default value of -1
            indicates all pages should be backed-up in a single step.
        :param str name: Name of source database (may differ if you used ATTACH
            DATABASE to load multiple databases). Defaults to "main".
        :param progress: Progress callback, called with three parameters: the
            number of pages remaining, the total page count, and whether the
            backup is complete.

        Backup the current database to a file. The backed-up data is not a
        database dump, but an actual SQLite database file.

        Example:

        .. code-block:: python

            db = CSqliteExtDatabase('app.db')

            def nightly_backup():
                filename = 'backup-%s.db' % (datetime.date.today())
                db.backup_to_file(filename)

    .. py:method:: blob_open(table, column, rowid[, read_only=False])

        :param str table: Name of table containing data.
        :param str column: Name of column containing data.
        :param int rowid: ID of row to retrieve.
        :param bool read_only: Open the blob for reading only.
        :returns: :py:class:`Blob` instance which provides efficient access to
            the underlying binary data.
        :rtype: Blob

        See :py:class:`Blob` and :py:class:`ZeroBlob` for more information.

        Example:

        .. code-block:: python

            class Image(Model):
                filename = TextField()
                data = BlobField()

            buf_size = 1024 * 1024 * 8  # Allocate 8MB for storing file.
            rowid = Image.insert({Image.filename: 'thefile.jpg',
                                  Image.data: ZeroBlob(buf_size)}).execute()

            # Open the blob, returning a file-like object.
            blob = db.blob_open('image', 'data', rowid)

            # Write some data to the blob.
            blob.write(image_data)
            img_size = blob.tell()

            # Read the data back out of the blob.
            blob.seek(0)
            image_data = blob.read(img_size)

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

    .. py:method:: set(value[, as_json=None])

        :param value: a scalar value, list, or dictionary.
        :param bool as_json: force the value to be treated as JSON, in which
            case it will be serialized as JSON in Python beforehand. By
            default, lists and dictionaries are treated as JSON to be
            serialized, while strings and integers are passed as-is.

        Set the value stored in a :py:class:`JSONField`.

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


.. py:class:: JSONPath(field[, path=None])

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

    .. py:method:: set(value[, as_json=None])

        :param value: a scalar value, list, or dictionary.
        :param bool as_json: force the value to be treated as JSON, in which
            case it will be serialized as JSON in Python beforehand. By
            default, lists and dictionaries are treated as JSON to be
            serialized, while strings and integers are passed as-is.

        Set the value at the given location in the JSON data.

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


.. py:class:: SearchField([unindexed=False[, column_name=None]])

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

    .. py:classmethod:: search(term[, weights=None[, with_score=False[, score_alias='score'[, explicit_ordering=False]]]])

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

    .. py:classmethod:: search_bm25(term[, weights=None[, with_score=False[, score_alias='score'[, explicit_ordering=False]]]])

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

    .. py:classmethod:: search_bm25f(term[, weights=None[, with_score=False[, score_alias='score'[, explicit_ordering=False]]]])

        Same as :py:meth:`FTSModel.search_bm25`, but using the BM25f variant
        of the BM25 ranking algorithm.

    .. py:classmethod:: search_lucene(term[, weights=None[, with_score=False[, score_alias='score'[, explicit_ordering=False]]]])

        Same as :py:meth:`FTSModel.search_bm25`, but using the result ranking
        algorithm from the Lucene search engine.

    .. py:classmethod:: rank([col1_weight, col2_weight...coln_weight])

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

    .. py:classmethod:: bm25([col1_weight, col2_weight...coln_weight])

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

    .. py:classmethod:: bm25f([col1_weight, col2_weight...coln_weight])

        Identical to :py:meth:`~FTSModel.bm25`, except that it uses the BM25f
        variant of the BM25 ranking algorithm.

    .. py:classmethod:: lucene([col1_weight, col2_weight...coln_weight])

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

    .. py:classmethod:: search(term[, weights=None[, with_score=False[, score_alias='score']]])

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

    .. py:classmethod:: search_bm25(term[, weights=None[, with_score=False[, score_alias='score']]])

        With FTS5, :py:meth:`~FTS5Model.search_bm25` is identical to the
        :py:meth:`~FTS5Model.search` method.

    .. py:classmethod:: rank([col1_weight, col2_weight...coln_weight])

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

    .. py:classmethod:: bm25([col1_weight, col2_weight...coln_weight])

        Because FTS5 provides built-in support for BM25, the
        :py:meth:`~FTS5Model.bm25` method is identical to the
        :py:meth:`~FTS5Model.rank` method.

    .. py:classmethod:: VocabModel([table_type='row'|'col'|'instance'[, table_name=None]])

        :param str table_type: Either 'row', 'col' or 'instance'.
        :param table_name: Name for the vocab table. If not specified, will be
            "fts5tablename_v".

        Generate a model class suitable for accessing the `vocab table <http://sqlite.org/fts5.html#the_fts5vocab_virtual_table_module>`_
        corresponding to FTS5 search index.

.. _sqlite-vtfunc:

.. py:class:: TableFunction()

    Implement a user-defined table-valued function. Unlike a simple
    :ref:`scalar or aggregate <sqlite-user-functions>` function, which returns
    a single scalar value, a table-valued function can return any number of
    rows of tabular data.

    Simple example:

    .. code-block:: python

        from playhouse.sqlite_ext import TableFunction


        class Series(TableFunction):
            # Name of columns in each row of generated data.
            columns = ['value']

            # Name of parameters the function may be called with.
            params = ['start', 'stop', 'step']

            def initialize(self, start=0, stop=None, step=1):
                """
                Table-functions declare an initialize() method, which is
                called with whatever arguments the user has called the
                function with.
                """
                self.start = self.current = start
                self.stop = stop or float('Inf')
                self.step = step

            def iterate(self, idx):
                """
                Iterate is called repeatedly by the SQLite database engine
                until the required number of rows has been read **or** the
                function raises a `StopIteration` signalling no more rows
                are available.
                """
                if self.current > self.stop:
                    raise StopIteration

                ret, self.current = self.current, self.current + self.step
                return (ret,)

        # Register the table-function with our database, which ensures it
        # is declared whenever a connection is opened.
        db.table_function('series')(Series)

        # Usage:
        cursor = db.execute_sql('SELECT * FROM series(?, ?, ?)', (0, 5, 2))
        for value, in cursor:
            print(value)

    .. note::
        A :py:class:`TableFunction` must be registered with a database
        connection before it can be used. To ensure the table function is
        always available, you can use the
        :py:meth:`SqliteDatabase.table_function` decorator to register the
        function with the database.

    :py:class:`TableFunction` implementations must provide two attributes and
    implement two methods, described below.

    .. py:attribute:: columns

        A list containing the names of the columns for the data returned by the
        function. For example, a function that is used to split a string on a
        delimiter might specify 3 columns: ``[substring, start_idx, end_idx]``.

    .. py:attribute:: params

        The names of the parameters the function may be called with. All
        parameters, including optional parameters, should be listed. For
        example, a function that is used to split a string on a delimiter might
        specify 2 params: ``[string, delimiter]``.

    .. py:attribute:: name

        *Optional* - specify the name for the table function. If not provided,
        name will be taken from the class name.

    .. py:attribute:: print_tracebacks = True

        Print a full traceback for any errors that occur in the
        table-function's callback methods. When set to False, only the generic
        OperationalError will be visible.

    .. py:method:: initialize(**parameter_values)

        :param parameter_values: Parameters the function was called with.
        :returns: No return value.

        The ``initialize`` method is called to initialize the table function
        with the parameters the user specified when calling the function.

    .. py:method:: iterate(idx)

        :param int idx: current iteration step
        :returns: A tuple of row data corresponding to the columns named
            in the :py:attr:`~TableFunction.columns` attribute.
        :raises StopIteration: To signal that no more rows are available.

        This function is called repeatedly and returns successive rows of data.
        The function may terminate before all rows are consumed (especially if
        the user specified a ``LIMIT`` on the results). Alternatively, the
        function can signal that no more data is available by raising a
        ``StopIteration`` exception.

    .. py:classmethod:: register(conn)

        :param conn: A ``sqlite3.Connection`` object.

        Register the table function with a DB-API 2.0 ``sqlite3.Connection``
        object. Table-valued functions **must** be registered before they can
        be used in a query.

        Example:

        .. code-block:: python

            class MyTableFunction(TableFunction):
                name = 'my_func'
                # ... other attributes and methods ...

            db = SqliteDatabase(':memory:')
            db.connect()

            MyTableFunction.register(db.connection())

        To ensure the :py:class:`TableFunction` is registered every time a
        connection is opened, use the :py:meth:`~SqliteDatabase.table_function`
        decorator.


.. _sqlite-closure-table:

.. py:function:: ClosureTable(model_class[, foreign_key=None[, referencing_class=None[, referencing_key=None]]])

    :param model_class: The model class containing the nodes in the tree.
    :param foreign_key: The self-referential parent-node field on the model
        class. If not provided, peewee will introspect the model to find a
        suitable key.
    :param referencing_class: Intermediate table for a many-to-many relationship.
    :param referencing_key: For a many-to-many relationship, the originating
        side of the relation.
    :return: Returns a :py:class:`VirtualModel` for working with a closure table.

    Factory function for creating a model class suitable for working with a
    `transitive closure <http://www.sqlite.org/cgi/src/artifact/636024302cde41b2bf0c542f81c40c624cfb7012>`_
    table. Closure tables are :py:class:`VirtualModel` subclasses that work
    with the transitive closure SQLite extension. These special tables are
    designed to make it easy to efficiently query hierarchical data. The SQLite
    extension manages an AVL tree behind-the-scenes, transparently updating the
    tree when your table changes and making it easy to perform common queries
    on hierarchical data.

    To use the closure table extension in your project, you need:

    1. A copy of the SQLite extension. The source code can be found in
       the `SQLite code repository <http://www.sqlite.org/cgi/src/artifact/636024302cde41b2bf0c542f81c40c624cfb7012>`_
       or by cloning `this gist <https://gist.github.com/coleifer/7f3593c5c2a645913b92>`_:

       .. code-block:: console

           $ git clone https://gist.github.com/coleifer/7f3593c5c2a645913b92 closure
           $ cd closure/

    2. Compile the extension as a shared library, e.g.

       .. code-block:: console

           $ gcc -g -fPIC -shared closure.c -o closure.so

    3. Create a model for your hierarchical data. The only requirement here is
       that the model has an integer primary key and a self-referential foreign
       key. Any additional fields are fine.

       .. code-block:: python

           class Category(Model):
               name = CharField()
               metadata = TextField()
               parent = ForeignKeyField('self', index=True, null=True)  # Required.

           # Generate a model for the closure virtual table.
           CategoryClosure = ClosureTable(Category)

       The self-referentiality can also be achieved via an intermediate table
       (for a many-to-many relation).

       .. code-block:: python

           class User(Model):
               name = CharField()

           class UserRelations(Model):
               user = ForeignKeyField(User)
               knows = ForeignKeyField(User, backref='_known_by')

               class Meta:
                   primary_key = CompositeKey('user', 'knows') # Alternatively, a unique index on both columns.

           # Generate a model for the closure virtual table, specifying the UserRelations as the referencing table
           UserClosure = ClosureTable(
               User,
               referencing_class=UserRelations,
               foreign_key=UserRelations.knows,
               referencing_key=UserRelations.user)

    4. In your application code, make sure you load the extension when you
       instantiate your :py:class:`Database` object. This is done by passing
       the path to the shared library to the :py:meth:`~SqliteExtDatabase.load_extension` method.

       .. code-block:: python

           db = SqliteExtDatabase('my_database.db')
           db.load_extension('/path/to/closure')

    .. warning::
        There are two caveats you should be aware of when using the
        ``transitive_closure`` extension. First, it requires that your *source
        model* have an integer primary key. Second, it is strongly recommended
        that you create an index on the self-referential foreign key.

    Example:

    .. code-block:: python

         class Category(Model):
             name = CharField()
             metadata = TextField()
             parent = ForeignKeyField('self', index=True, null=True)  # Required.

         # Generate a model for the closure virtual table.
         CategoryClosure = ClosureTable(Category)

          # Create the tables if they do not exist.
          db.create_tables([Category, CategoryClosure], True)

    It is now possible to perform interesting queries using the data from the
    closure table:

    .. code-block:: python

        # Get all ancestors for a particular node.
        laptops = Category.get(Category.name == 'Laptops')
        for parent in Closure.ancestors(laptops):
            print(parent.name)

        # Computer Hardware
        # Computers
        # Electronics
        # All products

        # Get all descendants for a particular node.
        hardware = Category.get(Category.name == 'Computer Hardware')
        for node in Closure.descendants(hardware):
            print(node.name)

        # Laptops
        # Desktops
        # Hard-drives
        # Monitors
        # LCD Monitors
        # LED Monitors

    API of the :py:class:`VirtualModel` returned by :py:func:`ClosureTable`.

    .. py:class:: BaseClosureTable()

        .. py:attribute:: id

            A field for the primary key of the given node.

        .. py:attribute:: depth

            A field representing the relative depth of the given node.

        .. py:attribute:: root

            A field representing the relative root node.

        .. py:method:: descendants(node[, depth=None[, include_node=False]])

            Retrieve all descendants of the given node. If a depth is
            specified, only nodes at that depth (relative to the given node)
            will be returned.

            .. code-block:: python

                node = Category.get(Category.name == 'Electronics')

                # Direct child categories.
                children = CategoryClosure.descendants(node, depth=1)

                # Grand-child categories.
                children = CategoryClosure.descendants(node, depth=2)

                # Descendants at all depths.
                all_descendants = CategoryClosure.descendants(node)


        .. py:method:: ancestors(node[, depth=None[, include_node=False]])

            Retrieve all ancestors of the given node. If a depth is specified,
            only nodes at that depth (relative to the given node) will be
            returned.

            .. code-block:: python

                node = Category.get(Category.name == 'Laptops')

                # All ancestors.
                all_ancestors = CategoryClosure.ancestors(node)

                # Grand-parent category.
                grandparent = CategoryClosure.ancestores(node, depth=2)

        .. py:method:: siblings(node[, include_node=False])

            Retrieve all nodes that are children of the specified node's
            parent.

    .. note::
        For an in-depth discussion of the SQLite transitive closure extension,
        check out this blog post, `Querying Tree Structures in SQLite using Python and the Transitive Closure Extension <https://charlesleifer.com/blog/querying-tree-structures-in-sqlite-using-python-and-the-transitive-closure-extension/>`_.

.. _sqlite-lsm1:

.. py:class:: LSMTable()

    :py:class:`VirtualModel` subclass suitable for working with the `lsm1 extension <https://charlesleifer.com/blog/lsm-key-value-storage-in-sqlite3/>`_
    The *lsm1* extension is a virtual table that provides a SQL interface to
    the `lsm key/value storage engine from SQLite4 <http://sqlite.org/src4/doc/trunk/www/lsmusr.wiki>`_.

    .. note::
        The LSM1 extension has not been released yet (SQLite version 3.22 at
        time of writing), so consider this feature experimental with potential
        to change in subsequent releases.

    LSM tables define one primary key column and an arbitrary number of
    additional value columns (which are serialized and stored in a single value
    field in the storage engine). The primary key must be all of the same type
    and use one of the following field types:

    * :py:class:`IntegerField`
    * :py:class:`TextField`
    * :py:class:`BlobField`

    Since the LSM storage engine is a key/value store, primary keys (including
    integers) must be specified by the application.

    .. attention::
        Secondary indexes are not supported by the LSM engine, so the only
        efficient queries will be lookups (or range queries) on the primary
        key.  Other fields can be queried and filtered on, but may result in a
        full table-scan.

    Example model declaration:

    .. code-block:: python

        db = SqliteExtDatabase('my_app.db')
        db.load_extension('lsm.so')  # Load shared library.

        class EventLog(LSMTable):
            timestamp = IntegerField(primary_key=True)
            action = TextField()
            sender = TextField()
            target = TextField()

            class Meta:
                database = db
                filename = 'eventlog.ldb'  # LSM data is stored in separate db.

        # Declare virtual table.
        EventLog.create_table()

    Example queries:

    .. code-block:: python

        # Use dictionary operators to get, set and delete rows from the LSM
        # table. Slices may be passed to represent a range of key values.
        def get_timestamp():
            # Return time as integer expressing time in microseconds.
            return int(time.time() * 1000000)

        # Create a new row, at current timestamp.
        ts = get_timestamp()
        EventLog[ts] = ('pageview', 'search', '/blog/some-post/')

        # Retrieve row from event log.
        log = EventLog[ts]
        print(log.action, log.sender, log.target)
        # Prints ("pageview", "search", "/blog/some-post/")

        # Delete the row.
        del EventLog[ts]

        # We can also use the "create()" method.
        EventLog.create(
            timestamp=get_timestamp(),
            action='signup',
            sender='newsletter',
            target='sqlite-news')

    Simple key/value model declaration:

    .. code-block:: python

        class KV(LSMTable):
            key = TextField(primary_key=True)
            value = TextField()

            class Meta:
                database = db
                filename = 'kv.ldb'

        db.create_tables([KV])

    For tables consisting of a single value field, Peewee will return the value
    directly when getting a single item. You can also request slices of rows,
    in which case Peewee returns a corresponding :py:class:`Select` query,
    which can be iterated over. Below are some examples:

    .. code-block:: pycon

        >>> KV['k0'] = 'v0'
        >>> print(KV['k0'])
        'v0'

        >>> data = [{'key': 'k%d' % i, 'value': 'v%d' % i} for i in range(20)]
        >>> KV.insert_many(data).execute()

        >>> KV.select().count()
        20

        >>> KV['k8']
        'v8'

        >>> list(KV['k4.1':'k7.x']
        [Row(key='k5', value='v5'),
         Row(key='k6', value='v6'),
         Row(key='k7', value='v7')]

        >>> list(KV['k6xxx':])
        [Row(key='k7', value='v7'),
         Row(key='k8', value='v8'),
         Row(key='k9', value='v9')]

    You can also index the :py:class:`LSMTable` using expressions:

    .. code-block:: pycon

        >>> list(KV[KV.key > 'k6'])
        [Row(key='k7', value='v7'),
         Row(key='k8', value='v8'),
         Row(key='k9', value='v9')]

        >>> list(KV[(KV.key > 'k6') & (KV.value != 'v8')])
        [Row(key='k7', value='v7'),
         Row(key='k9', value='v9')]

    You can delete single rows using ``del`` or multiple rows using slices
    or expressions:

    .. code-block:: pycon

        >>> del KV['k1']
        >>> del KV['k3x':'k8']
        >>> del KV[KV.key.between('k10', 'k18')]

        >>> list(KV[:])
        [Row(key='k0', value='v0'),
         Row(key='k19', value='v19'),
         Row(key='k2', value='v2'),
         Row(key='k3', value='v3'),
         Row(key='k9', value='v9')]

    Attempting to get a single non-existant key will result in a ``DoesNotExist``,
    but slices will not raise an exception:

    .. code-block:: pycon

        >>> KV['k1']
        ...
        KV.DoesNotExist: <Model:KV> instance matching query does not exist: ...

        >>> list(KV['k1':'k1'])
        []


.. _sqlite-blob:

.. py:class:: ZeroBlob(length)

    :param int length: Size of blob in bytes.

    :py:class:`ZeroBlob` is used solely to reserve space for storing a BLOB
    that supports incremental I/O. To use the `SQLite BLOB-store <https://www.sqlite.org/c3ref/blob_open.html>`_
    it is necessary to first insert a ZeroBlob of the desired size into the
    row you wish to use with incremental I/O.

    For example, see :py:class:`Blob`.

.. py:class:: Blob(database, table, column, rowid[, read_only=False])

    :param database: :py:class:`SqliteExtDatabase` instance.
    :param str table: Name of table being accessed.
    :param str column: Name of column being accessed.
    :param int rowid: Primary-key of row being accessed.
    :param bool read_only: Prevent any modifications to the blob data.

    Open a blob, stored in the given table/column/row, for incremental I/O.
    To allocate storage for new data, you can use the :py:class:`ZeroBlob`,
    which is very efficient.

    .. code-block:: python

        class RawData(Model):
            data = BlobField()

        # Allocate 100MB of space for writing a large file incrementally:
        query = RawData.insert({'data': ZeroBlob(1024 * 1024 * 100)})
        rowid = query.execute()

        # Now we can open the row for incremental I/O:
        blob = Blob(db, 'rawdata', 'data', rowid)

        # Read from the file and write to the blob in chunks of 4096 bytes.
        while True:
            data = file_handle.read(4096)
            if not data:
                break
            blob.write(data)

        bytes_written = blob.tell()
        blob.close()

    .. py:method:: read([n=None])

        :param int n: Only read up to *n* bytes from current position in file.

        Read up to *n* bytes from the current position in the blob file. If *n*
        is not specified, the entire blob will be read.

    .. py:method:: seek(offset[, whence=0])

        :param int offset: Seek to the given offset in the file.
        :param int whence: Seek relative to the specified frame of reference.

        Values for ``whence``:

        * ``0``: beginning of file
        * ``1``: current position
        * ``2``: end of file

    .. py:method:: tell()

        Return current offset within the file.

    .. py:method:: write(data)

        :param bytes data: Data to be written

        Writes the given data, starting at the current position in the file.

    .. py:method:: close()

        Close the file and free associated resources.

    .. py:method:: reopen(rowid)

        :param int rowid: Primary key of row to open.

        If a blob has already been opened for a given table/column, you can use
        the :py:meth:`~Blob.reopen` method to re-use the same :py:class:`Blob`
        object for accessing multiple rows in the table.

.. _sqlite-extras:

Additional Features
-------------------

The :py:class:`SqliteExtDatabase` accepts an initialization option to register
support for a simple `bloom filter <https://en.wikipedia.org/wiki/Bloom_filter>`_.
The bloom filter, once initialized, can then be used for efficient membership
queries on large set of data.

Here's an example:

.. code-block:: python

    db = CSqliteExtDatabase(':memory:', bloomfilter=True)

    # Create and define a table to store some data.
    db.execute_sql('CREATE TABLE "register" ("data" TEXT)')
    Register = Table('register', ('data',)).bind(db)

    # Populate the database with a bunch of text.
    with db.atomic():
        for i in 'abcdefghijklmnopqrstuvwxyz':
            keys = [i * j for j in range(1, 10)]  # a, aa, aaa, ... aaaaaaaaa
            Register.insert([{'data': key} for key in keys]).execute()

    # Collect data into a 16KB bloomfilter.
    query = Register.select(fn.bloomfilter(Register.data, 16 * 1024).alias('buf'))
    row = query.get()
    buf = row['buf']

    # Use bloomfilter buf to test whether other keys are members.
    test_keys = (
        ('aaaa', True),
        ('abc', False),
        ('zzzzzzz', True),
        ('zyxwvut', False))
    for key, is_present in test_keys:
        query = Register.select(fn.bloomfilter_contains(key, buf).alias('is_member'))
        answer = query.get()['is_member']
        assert answer == is_present


The :py:class:`SqliteExtDatabase` can also register other useful functions:

* ``rank_functions`` (enabled by default): registers functions for ranking
  search results, such as *bm25* and *lucene*.
* ``hash_functions``: registers md5, sha1, sha256, adler32, crc32 and
  murmurhash functions.
* ``regexp_function``: registers a regexp function.

Examples:

.. code-block:: python

    def create_new_user(username, password):
        # DO NOT DO THIS IN REAL LIFE. PLEASE.
        query = User.insert({'username': username, 'password': fn.sha1(password)})
        new_user_id = query.execute()

You can use the *murmurhash* function to hash bytes to an integer for compact
storage:

.. code-block:: pycon

    >>> db = SqliteExtDatabase(':memory:', hash_functions=True)
    >>> db.execute_sql('SELECT murmurhash(?)', ('abcdefg',)).fetchone()
    (4188131059,)
