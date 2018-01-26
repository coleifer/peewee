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
* :ref:`LSM1 extension support <sqlite-lsm1>`
* :ref:`Closure table extension support <sqlite-closure-table>`
* :ref:`User-defined virtual tables <sqlite-vtfunc>` (functions that return
  rows of tabular data, as opposed to :ref:`scalar or aggregates <sqlite-user-functions>`).
* :ref:`Support for online backups using backup API <sqlite-backups>`.
* :ref:`BLOB API support, for efficient binary data storage <sqlite-blob>`.
* Additional helpers, like a :ref:`bloom filter <sqlite-bloomfilter>`.

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
        ('foreign_keys', 1))  # Enforce foreign-key constraints.

.. _sqlite-fts:

Full-text Search
----------------

.. _sqlite-json1:

JSON Extension
--------------

.. _sqlite-lsm1:

LSM1 Key/Value Store
--------------------

.. _sqlite-closure-table:

Closure Table Extension
-----------------------

.. _sqlite-vtfunc:

User-defined Table Functions
----------------------------

.. _sqlite-backups:

Online Backups API
------------------

.. _sqlite-blob:

SQLite Blob-store
-----------------

.. _sqlite-extras:

Additional Features
-------------------

.. _sqlite-bloomfilter:

Bloom Filter
^^^^^^^^^^^^

API
---

.. py:module:: playhouse.sqlite_ext

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
    :param bool bloomfilter: Make the :ref:`sqlite-bloomfilter` available.

    Extends :py:class:`SqliteDatabase` and inherits methods for declaring
    user-defined functions, pragmas, etc.

    .. py:method table_function([name=None])

        Class-decorator for registering a :py:class:`TableFunction`. Table
        functions are user-defined functions that, rather than returning a
        single, scalar value, can return any number of rows of tabular data.

        Example:

        .. code-block:: python

            from playhouse.sqlite_ext import TableFunction

            @db.table_function('series')
            class Series(TableFunction):
                columns = ['value']
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

            # Usage:
            cursor = db.execute_sql('SELECT * FROM series(?, ?, ?)', (0, 5, 2))
            for value, in cursor:
                print(value)

            # Prints:
            # 0
            # 2
            # 4

.. py:class:: CSqliteExtDatabase(database[, pragmas=None[, timeout=5[, c_extensions=None[, rank_functions=True[, hash_functions=False[, regexp_function=False[, bloomfilter=False]]]]]]])

    Extends :py:class:`SqliteExtDatabase` and requires that the
    ``playhouse._sqlite_ext`` extension module be available.

    .. py:method:: on_commit(fn)

        Register a callback to be executed whenever a transaction is committed
        on the current connection. The callback accepts no parameters and the
        return value is ignored.

        However, if the callback raises a :py:class:`ValueError`, the
        transaction will be aborted and rolled-back.

    .. py:method:: on_rollback(fn)

        Register a callback to be executed whenever a transaction is rolled
        back on the current connection. The callback accepts no parameters and
        the return value is ignored.

    .. py:method:: on_update(fn)

        Register a callback to be executed whenever the database is written to
        (via an *UPDATE*, *INSERT* or *DELETE* query). The callback should
        accept the following parameters:

        * ``query`` - the type of query, either *INSERT*, *UPDATE* or *DELETE*.
        * database name - the default database is named *main*.
        * table name - name of table being modified.
        * rowid - the rowid of the row being modified.

        The callback's return value is ignored.

    .. py:method:: changes()

        Return the number of rows modified in the currently-open transaction.

    .. py:attribute:: autocommit

        Property which returns a boolean indicating if autocommit is enabled.
        By default, this value will be ``True`` except when inside a
        transaction (or :py:meth:`~Database.atomic` block).

    .. py:method:: backup(destination)

        :param SqliteDatabase destination: Database object to serve as
            destination for the backup.

        Example:

        .. code-block:: python

            master = CSqliteExtDatabase('master.db')
            replica = CSqliteExtDatabase('replica.db')

            # Backup the contents of master to replica.
            master.backup(replica)

    .. py:method:: backup_to_file(filename)

        :param filename: Filename to store the database backup.

        Backup the current database to a file. The backed-up data is not a
        database dump, but an actual SQLite database file.

    .. py:method:: blob_open(table, column, rowid[, read_only=False])

        :param str table: Name of table containing data.
        :param str column: Name of column containing data.
        :param int rowid: ID of row to retrieve.
        :param bool read_only: Open the blob for reading only.
        :returns: :py:class:`Blob` instance which provides efficient access to
            the underlying binary data.
        :rtype: Blob

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

.. py:class:: DocIDField()

    Subclass of :py:class:`RowIDField` for use on virtual tables that
    specifically use the convention of ``docid`` for the primary key. As far as
    I know this only pertains to tables using the FTS3 and FTS4 full-text
    search extensions.

.. py:class:: AutoIncrementField()

    SQLite, by default, may reuse primary key values after rows are deleted. To
    ensure that the primary key is *always* monotonically increasing,
    regardless of deletions, you should use :py:class:`AutoIncrementField`.
    There is a small performance cost for this feature. For more information,
    see the SQLite docs on `autoincrement <https://sqlite.org/autoinc.html>`_.

.. py:class:: JSONField()

    Field class suitable for storing JSON data, with special methods designed
    to work with the `json1 extension <https://sqlite.org/json1.html>`_.

    Most functions that operate on JSON fields take a ``path`` argument. The
    JSON documents specify that the path should begin with ``$`` followed by
    zero or more instances of ``.objectlabel`` or ``[arrayindex]``. Peewee
    simplifies this by allowing you to omit the ``$`` character and just
    specify the path you need or ``None`` for an empty path:

    * ``path=''`` --> ``'$'``
    * ``path='tags'`` --> ``'$.tags'``
    * ``path='[0][1].bar'`` --> ``'$[0][1].bar'``
    * ``path='metadata[0]'`` --> ``'$.metadata[0]'``
    * ``path='user.data.email'`` --> ``'$.user.data.email'``

    .. py:method:: length(*paths)

        :param paths: Zero or more JSON paths.

        Returns the length of the JSON object stored, either in the column, or
        at one or more paths within the column data.

    .. py:method:: extract(*paths)

        :param paths: One or more JSON paths.

        Extracts the JSON objects at the given path(s) from the column data.
        For example if you have a complex JSON object and only need to work
        with the value of a specific key, you can use the extract method,
        specifying the path to the key, to return only the data you need.

    .. py:method:: insert(*pairs)

        :param pairs: A flat list consisting of *key*, *value* pairs. E.g.,
            k1, v1, k2, v2, k3, v3. The key may be a simple string or a JSON
            path.

        Insert the values at the given keys (or paths) in the column data. If
        the key/path specified already has a value, it will **not** be
        overwritten.

    .. py:method:: replace(*pairs)

        :param pairs: A flat list consisting of *key*, *value* pairs. E.g.,
            k1, v1, k2, v2, k3, v3. The key may be a simple string or a JSON
            path.

        Replace the values at the given keys (or paths) in the column data. If
        the key/path specified does not exist, a new key will not be created.
        Data must exist first in order to be replaced.

    .. py:method:: set(*pairs)

        :param pairs: A flat list consisting of *key*, *value* pairs. E.g.,
            k1, v1, k2, v2, k3, v3. The key may be a simple string or a JSON
            path.

        Set the values at the given keys (or paths) in the column data. The
        values will be updated regardless of whether the key exists already.

    .. py:method:: remove(*paths)

        :param paths: One or more JSON paths.

        Remove the data at the given paths from the column data.

    .. py:method:: update(data)

        :param data: A JSON value.

        Updates the column data in-place, merging the new data with the data
        already present in the column.

    .. py:method:: json_type([path=None])

        :param path: A JSON path (optional).

        Return a string identifying the type of value stored in the column (or
        at the given path).

    .. py:method:: children([path=None])

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

        For examples, see `my blog post on JSON1 <http://charlesleifer.com/blog/using-the-sqlite-json1-and-fts5-extensions-with-python/>`_.

        `SQLite documentation on json_each <https://www.sqlite.org/json1.html#jeach>`_.

    .. py:method:: tree([path=None])

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

        For examples, see `my blog post on JSON1 <http://charlesleifer.com/blog/using-the-sqlite-json1-and-fts5-extensions-with-python/>`_.

        `SQLite documentation on json_tree <https://www.sqlite.org/json1.html#jeach>`_.


.. py:class:: SearchField([unindexed=False[, column_name=None]])

    Field-class to be used for columns on models representing full-text search
    virtual tables. The full-text search extensions prohibit the specification
    of any typing or constraints on columns. This behavior is enforced by the
    :py:class:`SearchField`, which raises an exception if any configuration is
    attempted that would be incompatible with the full-text search extensions.


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
    * FTS models contain a ``docid`` field which is automatically created and
      managed by SQLite (unless you choose to explicitly set it during model
      creation). Lookups on this column **are fast and efficient**.

    Given these constraints, it is strongly recommended that all fields
    declared on an ``FTSModel`` subclass be instances of
    :py:class:`SearchField` (though an exception is made for explicitly
    declaring a :py:class:`DocIDField`). Using :py:class:`SearchField` will
    help prevent you accidentally creating invalid column constraints.

    Because of the lack of secondary indexes, it usually makes sense to use
    the ``docid`` primary key as a pointer to a row in a regular table. For
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
            title = SearchField()
            content = SearchField()

            class Meta:
                database = db
                # Use the porter stemming algorithm to tokenize content.
                extension_options = {'tokenize': 'porter'}

    To store a document in the document index, we will ``INSERT`` a row into
    the ``DocumentIndex`` table, manually setting the ``docid`` so that it
    matches the primary-key of the corresponding ``Document``:

    .. code-block:: python

        def store_document(document):
            DocumentIndex.insert({
                DocumentIndex.docid: document.id,
                DocumentIndex.title: document.title,
                DocumentIndex.content: document.content}).execute()

    To perform a search and return ranked results, we can query the
    ``Document`` table and join on the ``DocumentIndex``. This join will be
    efficient because lookups on an FTSModel's ``docid`` field are fast:

    .. code-block:: python

        def search(phrase):
            # Query the search index and join the corresponding Document
            # object on each search result.
            return (Document
                    .select()
                    .join(
                        DocumentIndex,
                        on=(Document.id == DocumentIndex.docid))
                    .where(DocumentIndex.match(phrase))
                    .order_by(DocumentIndex.bm25()))

    .. warning::
        All SQL queries on ``FTSModel`` classes will be slow **except**
        full-text searches and ``docid`` lookups.

    Continued examples:

    .. code-block:: python

        # Use the "match" operation for FTS queries.
        matching_docs = (DocumentIndex
                         .select()
                         .where(DocumentIndex.match('some query')))

        # To sort by best match, use the custom "rank" function.
        best = (DocumentIndex
                .select()
                .where(DocumentIndex.match('some query'))
                .order_by(DocumentIndex.rank()))

        # Or use the shortcut method:
        best = DocumentIndex.search('some phrase')

        # Peewee allows you to specify weights for columns.
        # Matches in the title will be 2x more valuable than matches
        # in the content field:
        best = DocumentIndex.search(
            'some phrase',
            weights=[2.0, 1.0],
        )

    Examples using the BM25 ranking algorithm:

    .. code-block:: python

        # you can also use the BM25 algorithm to rank documents:
        best = (DocumentIndex
                .select()
                .where(DocumentIndex.match('some query'))
                .order_by(DocumentIndex.bm25()))

        # There is a shortcut method for bm25 as well:
        best_bm25 = DocumentIndex.search_bm25('some phrase')

        # BM25 allows you to specify weights for columns.
        # Matches in the title will be 2x more valuable than matches
        # in the content field:
        best_bm25 = DocumentIndex.search_bm25(
            'some phrase',
            weights=[2.0, 1.0],
        )

    If the primary source of the content you are indexing exists in a separate table, you can save some disk space by instructing SQLite to not store an additional copy of the search index content. SQLite will still create the metadata and data-structures needed to perform searches on the content, but the content itself will not be stored in the search index.

    To accomplish this, you can specify a table or column using the ``content`` option. The `FTS4 documentation <http://sqlite.org/fts3.html#section_6_2>`_ has more information.

    Here is a short code snippet illustrating how to implement this with peewee:

    .. code-block:: python

        class Blog(Model):
            title = CharField()
            pub_date = DateTimeField()
            content = TextField()  # we want to search this.

            class Meta:
                database = db

        class BlogIndex(FTSModel):
            content = SearchField()

            class Meta:
                database = db
                extension_options = {'content': Blog.content}

        db.create_tables([Blog, BlogIndex])

        # Now, we can manage content in the FTSBlog.  To populate it with
        # content:
        BlogIndex.rebuild()

        # Optimize the index.
        BlogIndex.optimize()

    The ``content`` option accepts either a single :py:class:`Field` or a :py:class:`Model`
    and can reduce the amount of storage used.  However, content will need to be
    manually moved to/from the associated ``FTSModel``.
