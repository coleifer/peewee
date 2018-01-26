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
* User-defined virtual tables, which return rows of tabular data as opposed to
  :ref:`scalar or aggregate <sqlite-user-functions>` functions. For API
  details, see: :py:class:`TableFunction` and :py:meth:`~SqliteExtDatabase.table_function`.
* Support for online backups using backup API: :py:meth:`~CSqliteExtDatabase.backup_to_file`
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

SQLite provides excellent full-text search via the :ref:`FTS3/4 <https://sqlite.org/fts3.html>`_
and :ref:`FTS5 <https://sqlite.org/fts5.html>`_ extension libraries. Peewee
provides base model-classes for working with these extensions:

* :py:class:`FTSModel` for versions 3 and 4.
* :py:class:`FTS5Model` for version 5.

Because the APIs are so similar, and because versions 3 and 4 are the most
widely deployed, the following examples will focus on :py:class:`FTSModel`.
However, most everything will apply also to :py:class:`FTS5Model`.

One limitation that applies to all versions of the full-text extension is that
columns do not support constraints, data-types, or indexes. For this reason,
when declaring your search index model, all fields should be
:py:class:`SearchField` instances. If you wish to store metadata in the index
but would not like it to be included in the full-text index, then specify
``unindexed=True`` when instantiating the :py:class:`SearchField`.

The only exception to the above is for the ``rowid`` primary key, which can
be declared using :py:class:`RowIDField`. Lookups on the ``rowid`` are very
efficient.

Example model and associated index:

.. code-block:: python

    db = SqliteExtDatabase('app.db', pragmas=[('journal_mode', 'wal')])

    class Document(Model):
        title = TextField(unique=True)
        content = TextField()
        timestamp = DateTimeField(default=datetime.datetime.now)

        class Meta:
            database = db

    class DocumentIndex(FTSModel):
        rowid = RowIDField()
        title = SearchField()
        content = SearchField()

        class Meta:
            database = db
            options = {'tokenize': 'porter'}

    db.create_tables([Document, DocumentIndex])

To store a document in the document index, we will ``INSERT`` a row into the
``DocumentIndex`` table, manually setting the ``rowid`` to correspond to the
value of the ``Document`` it is associated with (this allows us to do efficient
joins when searching):

.. code-block:: python

    def store_document(document):
        DocumentIndex.insert({
            DocumentIndex.rowid: document.id,
            DocumentIndex.title: document.title,
            DocumentIndex.content: document.content}).execute()

To perform a search and return ranked results, we can query the ``Document``
table and join on the ``DocumentIndex``:

.. code-block:: python

    def search(phrase):
        # Query the search index and join the corresponding Document
        # object on each search result.
        return (Document
                .select()
                .join(DocumentIndex, on=(Document.id == DocumentIndex.rowid))
                .where(DocumentIndex.match(phrase))
                .order_by(DocumentIndex.bm25()))

.. warning::
    All SQL queries on ``FTSModel`` classes will be slow **except** full-text
    searches and ``rowid`` lookups.

Continued examples:

.. code-block:: python

    # To sort by best match, use the "rank" function.
    best = (DocumentIndex
            .select()
            .where(DocumentIndex.match('some query'))
            .order_by(DocumentIndex.rank()))

    # Or use the shortcut method:
    best = DocumentIndex.search('some phrase')

    # Peewee allows you to specify weights for columns.
    # Matches in the title will be 2x more valuable than matches
    # in the content field:
    best = DocumentIndex.search('some phrase', weights=[2.0, 1.0])

Peewee supports the more sophisticated BM25 ranking algorithm for FTS4 and
FTS5. Example of using BM25 to rank search results:

.. code-block:: python

    # You can also use the BM25 algorithm to rank documents:
    best = (Document
            .select(Document, DocumentIndex.bm25().alias('score'))
            .join(DocumentIndex, on=(Document.id == DocumentIndex.rowid))
            .where(DocumentIndex.match('some query'))
            .order_by(SQL('score')))

    # There is a shortcut method for bm25 as well:
    best_bm25 = DocumentIndex.search_bm25('some phrase')

    # BM25 allows you to specify weights for columns.
    # Matches in the title will be 2x more valuable than matches
    # in the content field:
    best_bm25 = DocumentIndex.search_bm25('some phrase', weights={
        'title': 2.0, 'content': 1.0})

If the primary source of the content you are indexing exists in a separate
table, you can save some disk space by instructing SQLite to not store an
additional copy of the search index content. SQLite will still create the
metadata and data-structures needed to perform searches on the content, but the
content itself will not be stored in the search index.

To accomplish this, you can specify a table or column using the ``content``
option. The `FTS4 documentation <http://sqlite.org/fts3.html#section_6_2>`_ has
more information.

Here is a short code snippet illustrating how to implement this with peewee:

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
            options = {'content': Blog.content}

    db.create_tables([Blog, BlogIndex])

    # Now, we can manage content in the FTSBlog. To populate the search index:
    BlogIndex.rebuild()

    # Optimize the index.
    BlogIndex.optimize()

The ``content`` option accepts either a single :py:class:`Field` or a :py:class:`Model`
and can reduce the amount of storage used by the database file. However,
content will need to be manually moved to/from the associated ``FTSModel``.

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

.. _sqlite-json1:

.. py:class:: JSONField()

    Field class suitable for storing JSON data, with special methods designed
    to work with the `json1 extension <https://sqlite.org/json1.html>`_.

    SQLite 3.9.0 added `JSON support <https://www.sqlite.org/json1.html>`_ in
    the form of an extension library. The SQLite json1 extension provides a
    number of helper functions for working with JSON data. These APIs are
    exposed as methods of a special field-type, :py:class:`JSONField`.

    Most functions that operate on JSON fields take a ``path`` argument. The
    JSON extension documents specify that the path should begin with ``$``
    followed by zero or more instances of ``.objectlabel`` or ``[arrayindex]``.
    Peewee simplifies this by allowing you to omit the ``$`` character and just
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

        Example:

        .. code-block:: python

            # Get APIResponses annotated with the count of tags where the
            # category key has a value of "posts".
            query = (APIResponse
                     .select(
                       APIResponse,
                       APIResponse.json_data.length('metadata.tags').alias('tag_count'))
                     .where(APIResponse.json_data['category'] == 'posts'))

    .. py:method:: extract(*paths)

        :param paths: One or more JSON paths.

        Extracts the JSON objects at the given path(s) from the column data.
        For example if you have a complex JSON object and only need to work
        with the value of a specific key, you can use the extract method,
        specifying the path to the key, to return only the data you need.

        Instead of using :py:meth:`~JSONField.extract`, you can also use square
        brackets to express the same thing.

        Example:

        .. code-block:: python

            # Query for the "title" and "category" values stored in the
            # json_data column for APIResponses whose category is "posts".
            query = (APIResponse
                     .select(APIResponse.json_data['title'].alias('title'),
                             APIResponse.json_data['metadata.tags'].alias('tags'))
                     .where(APIResponse.json_data['category'] == 'posts'))

            for response in query:
                print(response.title, response.tags)

            # Example (note that JSON lists are returned as Python lists):
            # ('Post 1', ['foo', 'bar'])
            # ('Post 2', ['baz', 'nug'])
            # ('Post 3', [])

    .. py:method:: insert(*pairs)

        :param pairs: A flat list consisting of *key*, *value* pairs. E.g.,
            k1, v1, k2, v2, k3, v3. The key may be a simple string or a JSON
            path.

        Insert the values at the given keys (or paths) in the column data. If
        the key/path specified already has a value, it will **not** be
        overwritten.

        Example of adding a new key/value to a sub-key:

        .. code-block:: python

            # Existing data in column is preserved and "new_key": "new value"
            # is stored in the "metadata" dictionary. If "new_key" already
            # existed, however, the existing data would not be overwritten.
            nrows = (APIResponse
                     .update(json_data=APIResponse.json_data.insert(
                        'metadata.new_key', 'new value'))
                     .where(APIResponse.json_data['category'] == 'posts')
                     .execute())

    .. py:method:: replace(*pairs)

        :param pairs: A flat list consisting of *key*, *value* pairs. E.g.,
            k1, v1, k2, v2, k3, v3. The key may be a simple string or a JSON
            path.

        Replace the values at the given keys (or paths) in the column data. If
        the key/path specified does not exist, a new key will not be created.
        Data must exist first in order to be replaced.

        Example of replacing the value of an existing key:

        .. code-block:: python

            # Rename the "posts" category to "notes".
            nrows = (APIResponse
                     .update(json_data=APIResponse.json_data.replace(
                        'category', 'notes'))
                     .where(APIResponse.json_data['category'] == 'posts')
                     .execute())

    .. py:method:: set(*pairs)

        :param pairs: A flat list consisting of *key*, *value* pairs. E.g.,
            k1, v1, k2, v2, k3, v3. The key may be a simple string or a JSON
            path.

        Set the values at the given keys (or paths) in the column data. The
        values will be created/updated regardless of whether the key exists
        already.

        Example of setting two new key/value pairs:

        .. code-block:: python

            nrows = (APIResponse
                     .update(json_data=APIResponse.json_data.set(
                        'metadata.key1', 'value1',
                        'metadata.key2', [1, 2, 3]))
                     .execute())

            # Retrieve an arbitrary row from the db to inspect it's metadata.
            obj = APIResponse.get()
            print(obj.json_data['metadata'])  # key1 and key2 are present.
            # {'key2': [1, 2, 3], 'key1': 'value1', 'tags': ['foo', 'bar']}

    .. py:method:: remove(*paths)

        :param paths: One or more JSON paths.

        Remove the data at the given paths from the column data.

    .. py:method:: update(data)

        :param data: A JSON value.

        Updates the column data in-place, *merging* the new data with the data
        already present in the column. This is different than
        :py:meth:`~JSONField.set`, as sub-dictionaries will be merged with
        other sub-dictionaries, recursively.

    .. py:method:: json_type([path=None])

        :param path: A JSON path (optional).

        Return a string identifying the type of value stored in the column (or
        at the given path).

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
    help prevent you accidentally creating invalid column constraints. If you
    wish to store metadata in the index but would not like it to be included in
    the full-text index, then specify ``unindexed=True`` when instantiating the
    :py:class:`SearchField`.

    The only exception to the above is for the ``rowid`` primary key, which can
    be declared using :py:class:`RowIDField`. Lookups on the ``rowid`` are very
    efficient.

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
                options = {'tokenize': 'porter'}

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

        :param float col_weight: (Optional) weight to give to the *i*th column
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
                print search_result.title, search_result.score

    .. py:classmethod:: bm25([col1_weight, col2_weight...coln_weight])

        :param float col_weight: (Optional) weight to give to the *i*th column
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

        :param float col_weight: (Optional) weight to give to the *i*th column
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
    designed to make it easy to efficiently query heirarchical data. The SQLite
    extension manages an AVL tree behind-the-scenes, transparently updating the
    tree when your table changes and making it easy to perform common queries
    on heirarchical data.

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
            print parent.name

        # Computer Hardware
        # Computers
        # Electronics
        # All products

        # Get all descendants for a particular node.
        hardware = Category.get(Category.name == 'Computer Hardware')
        for node in Closure.descendants(hardware):
            print node.name

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
        check out this blog post, `Querying Tree Structures in SQLite using Python and the Transitive Closure Extension <http://charlesleifer.com/blog/querying-tree-structures-in-sqlite-using-python-and-the-transitive-closure-extension/>`_.

.. _sqlite-lsm1:

.. py:class:: LSMTable()

    :py:class:`VirtualModel` subclass suitable for working with the `lsm1 extension <http://charlesleifer.com/blog/lsm-key-value-storage-in-sqlite3/>`_
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


        class EventLog(LSMTable):
            timestamp = IntegerField(primary_key=True)
            action = TextField()
            sender = TextField()
            target = TextField()

            class Meta:
                database = db
                filename = 'eventlog.ldb'  # LSM data is stored in separate db.

        # Declare virtual table.
        db.create_table(EventLog)

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

        # Retreive row from event log.
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
