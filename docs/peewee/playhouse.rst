.. _playhouse:

Playhouse, extensions to Peewee
===============================

Peewee comes with numerous extrension modules which are collected under the ``playhouse`` namespace. Despite the silly name, there are some very useful extensions, particularly those that expose vendor-specific database features like the :ref:`sqlite_ext` and :ref:`postgres_ext` extensions.

Below you will find a loosely organized listing of the various modules that make up the ``playhouse``.

**Database drivers / vendor-specific database functionality**

* :ref:`sqlite_ext`
* :ref:`sqliteq`
* :ref:`sqlite_udf`
* :ref:`apsw`
* :ref:`berkeleydb`
* :ref:`sqlcipher_ext`
* :ref:`postgres_ext`

**High-level features**

* :ref:`extra-fields`
* :ref:`shortcuts`
* :ref:`hybrid`
* :ref:`signals`
* :ref:`dataset`
* :ref:`kv`
* :ref:`gfk`
* :ref:`csv_utils`

**Database management and framework integration**

* :ref:`pwiz`
* :ref:`migrate`
* :ref:`pool`
* :ref:`reflection`
* :ref:`db_url`
* :ref:`read_slaves`
* :ref:`test_utils`
* :ref:`pskel`
* :ref:`flask_utils`
* :ref:`djpeewee`

.. _sqlite_ext:

Sqlite Extensions
-----------------

The SQLite extensions module provides support for some interesting sqlite-only
features:

* Define custom aggregates, collations and functions.
* Support for FTS3/4 (sqlite full-text search) with :ref:`BM25 ranking <sqlite_bm25>`.
* C extension providing fast implementations of ranking and other utility functions.
* Support for the new FTS5 search extension.
* Specify isolation level in transactions.
* Support for virtual tables and SQLite C extensions.
* Support for the `closure table <http://charlesleifer.com/blog/querying-tree-structures-in-sqlite-using-python-and-the-transitive-closure-extension/>`_ extension, which allows efficient querying of heirarchical tables.

sqlite_ext API notes
^^^^^^^^^^^^^^^^^^^^

.. py:class:: SqliteExtDatabase(database, pragmas=(), c_extensions=True, **kwargs)

    :param pragmas: A list or tuple of 2-tuples containing ``PRAGMA`` settings to configure on a per-connection basis.
    :param bool c_extensions: Boolean flag indicating whether to use the fast implementations of various SQLite user-defined functions. If Cython was installed when you built ``peewee``, then these functions should be available. If not, Peewee will fall back to using the slower pure-Python functions.

    Subclass of the :py:class:`SqliteDatabase` that provides some advanced features only offered by Sqlite.

    * Register custom aggregates, collations and functions
    * Support for SQLite virtual tables and C extensions
    * Specify a row factory
    * Advanced transactions (specify isolation level)

    .. py:method:: aggregate([name=None[, num_params=-1]])

        Class-decorator for registering custom aggregation functions.

        :param name: string name for the aggregate, defaults to the name of the class.
        :param num_params: integer representing number of parameters the aggregate function accepts. The default value, ``-1``, indicates the aggregate can accept any number of parameters.

        .. code-block:: python

            @db.aggregate('product', 1)
            class Product(object):
                """Like sum, except calculate the product of a series of numbers."""
                def __init__(self):
                    self.product = 1

                def step(self, value):
                    self.product *= value

                def finalize(self):
                    return self.product

            # To use this aggregate:
            product = (Score
                       .select(fn.product(Score.value))
                       .scalar())

    .. py:method:: unregister_aggregate(name):

        Unregister the given aggregate function.

    .. py:method:: collation([name])

        Function decorator for registering a custom collation.

        :param name: string name to use for this collation.

        .. code-block:: python

            @db.collation()
            def collate_reverse(s1, s2):
                return -cmp(s1, s2)

            # To use this collation:
            Book.select().order_by(collate_reverse.collation(Book.title))

        As you might have noticed, the original ``collate_reverse`` function
        has a special attribute called ``collation`` attached to it.  This extra
        attribute provides a shorthand way to generate the SQL necessary to use
        our custom collation.

    .. py:method:: unregister_collation(name):

        Unregister the given collation function.

    .. py:method:: func([name[, num_params]])

        Function decorator for registering user-defined functions.

        :param name: name to use for this function.
        :param num_params: number of parameters this function accepts.  If not
            provided, peewee will introspect the function for you.

        .. code-block:: python

            @db.func()
            def title_case(s):
                return s.title()

            # Use in the select clause...
            titled_books = Book.select(fn.title_case(Book.title))

            @db.func()
            def sha1(s):
                return hashlib.sha1(s).hexdigest()

            # Use in the where clause...
            user = User.select().where(
                (User.username == username) &
                (fn.sha1(User.password) == password_hash)).get()

    .. py:method:: unregister_function(name):

        Unregister the given user-defiend function.

    .. py:method:: load_extension(extension)

        Load the given C extension. If a connection is currently open in the calling thread, then the extension will be loaded for that connection as well as all subsequent connections.

        For example, if you've compiled the closure table extension and wish to use it in your application, you might write:

        .. code-block:: python

            db = SqliteExtDatabase('my_app.db')
            db.load_extension('closure')

    .. py:method:: unload_extension(name):

        Unload the given SQLite extension.

    .. py:method:: granular_transaction([lock_type='deferred'])

        With the ``granular_transaction`` helper, you can specify the isolation level
        for an individual transaction.  The valid options are:

        * ``exclusive``
        * ``immediate``
        * ``deferred``

        Example usage:

        .. code-block:: python

            with db.granular_transaction('exclusive'):
                # no other readers or writers!
                (Account
                 .update(Account.balance=Account.balance - 100)
                 .where(Account.id == from_acct)
                 .execute())

                (Account
                 .update(Account.balance=Account.balance + 100)
                 .where(Account.id == to_acct)
                 .execute())


.. py:class:: VirtualModel

    Subclass of :py:class:`Model` that signifies the model operates using a
    virtual table provided by a sqlite extension.

    Creating a virtual model is easy, simply subclass ``VirtualModel`` and specify the extension module and any options:

    .. code-block:: python

        class MyVirtualModel(VirtualModel):
            class Meta:
                database = db
                extension_module = 'nextchar'
                extension_options = {}

    .. py:attribute:: Meta.extension_module = 'name of sqlite extension'

    .. py:attribute:: Meta.extension_options = {'tokenize': 'porter', etc}

        SQLite virtual tables often support configuration via arbitrary key/value options which are included in the ``CREATE TABLE`` statement. To configure a virtual table, you can specify options like this:

        .. code-block:: python

            class SearchIndex(FTSModel):
                content = SearchField()
                metadata = SearchField()

                class Meta:
                    database = my_db
                    extension_options = {
                        'prefix': [2, 3],
                        'tokenize': 'porter',
                    }


.. _sqlite_fts:

.. py:class:: FTSModel

    Model class that provides support for Sqlite's full-text search extension.
    Models should be defined normally, however there are a couple caveats:

    * Unique constraints, not null constraints, check constraints and foreign keys are not supported.
    * Indexes on fields and multi-column indexes are ignored completely
    * Sqlite will treat all column types as ``TEXT`` (although you
      can store other data types, Sqlite will treat them as text).
    * FTS models contain a ``docid`` field which is automatically created and managed by SQLite (unless you choose to explicitly set it during model creation). Lookups on this column **are performant**.

    ``sqlite_ext`` provides a :py:class:`SearchField` field class which should be used on ``FTSModel`` implementations instead of the regular peewee field types. This will help prevent you accidentally creating invalid column constraints.

    Because of the lack of secondary indexes, it usually makes sense to use the ``docid`` primary key as a pointer to a row in a regular table. For example:

    .. code-block:: python

        class Document(Model):
            author = ForeignKeyField(User, related_name='documents')
            title = TextField(null=False, unique=True)
            content = TextField(null=False)
            timestamp = DateTimeField()

            class Meta:
                database = db


        class DocumentIndex(FTSModel):
            title = SearchField()
            content = SearchField()

            class Meta:
                database = db
                # Use the porter stemming algorithm to tokenize content.
                extension_options = {'tokenize': 'porter'}

    To store a document in the document index, we will ``INSERT`` a row into the ``DocumentIndex`` table, manually setting the ``docid``:

    .. code-block:: python

        def store_document(document):
            DocumentIndex.insert({
                DocumentIndex.docid: document.id,
                DocumentIndex.title: document.title,
                DocumentIndex.content: document.content}).execute()

    To perform a search and return ranked results, we can query the ``Document`` table and join on the ``DocumentIndex``:

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

    .. warning:: All SQL queries on ``FTSModel`` classes will be slow **except** full-text searches and ``docid`` lookups.

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

    **FTSModel API methods:**

    .. py:classmethod:: create_table([fail_silently=False[, **options]])

        :param boolean fail_silently: do not re-create if table already exists.
        :param options: options passed along when creating the table, e.g. ``content``.

    .. py:classmethod:: match(term)

        Shorthand for generating a ``MATCH`` expression for the given term(s).

        .. code-block:: python

            query = (DocumentIndex
                     .select()
                     .where(DocumentIndex.match('search phrase')))
            for doc in query:
                print 'match: ', doc.title

    .. py:classmethod:: search(term[, weights=None[, with_score=False[, score_alias='score']]])

        Shorthand way of searching for a term and sorting results by the
        quality of the match. This is equivalent to the :py:meth:`~FTSModel.rank`
        example code presented below.

        :param str term: Search term to use.
        :param weights: A list of weights for the columns, ordered with respect to the column's position in the table. **Or**, a dictionary keyed by the field or field name and mapped to a value.
        :param with_score: Whether the score should be returned as part of the ``SELECT`` statement.
        :param str score_alias: Alias to use for the calculated rank score. This is the attribute you will use to access the score if ``with_score=True``.

        .. code-block:: python

            # Simple search.
            docs = DocumentIndex.search('search term')
            for result in docs:
                print result.title

            # More complete example.
            docs = DocumentIndex.search(
                'search term',
                weights={'title': 2.0, 'content': 1.0},
                with_score=True,
                score_alias='search_score')
            for result in docs:
                print result.title, result.search_score

    .. py:classmethod:: rank([col1_weight, col2_weight...coln_weight])

        Generate an expression that will calculate and return the quality of the search match. This ``rank`` can be used to sort the search results. The lower the ``rank``, the better the match.

        The ``rank`` function accepts optional parameters that allow you to specify weights for the various columns. If no weights are specified, all columns are considered of equal importance.

        .. code-block:: python

            query = (DocumentIndex
                     .select(
                         DocumentIndex,
                         DocumentIndex.rank().alias('score'))
                     .where(DocumentIndex.match('search phrase'))
                     .order_by(DocumentIndex.rank()))

            for search_result in query:
                print search_result.title, search_result.score

    .. _sqlite_bm25:

    .. py:classmethod:: search_bm25(term[, weights=None[, with_score=False[, score_alias='score']]])

        Shorthand way of searching for a term and sorting results by the
        quality of the match, as determined by the BM25 algorithm. This is
        equivalent to the :py:meth:`~FTSModel.bm25` example code presented below.

        :param str term: Search term to use.
        :param weights: A list of weights for the columns, ordered with respect to the column's position in the table. **Or**, a dictionary keyed by the field or field name and mapped to a value.
        :param with_score: Whether the score should be returned as part of the ``SELECT`` statement.
        :param str score_alias: Alias to use for the calculated rank score. This is the attribute you will use to access the score if ``with_score=True``.

        .. code-block:: python

            # Simple search.
            docs = DocumentIndex.search('search term')
            for result in docs:
                print result.title

            # More complete example.
            docs = DocumentIndex.search(
                'search term',
                weights={'title': 2.0, 'content': 1.0},
                with_score=True,
                score_alias='search_score')
            for result in docs:
                print result.title, result.search_score

    .. py:classmethod:: bm25([col1_weight, col2_weight...coln_weight])

        Generate an expression that will calculate and return the quality of the search match using the `BM25 algorithm <https://en.wikipedia.org/wiki/Okapi_BM25>`_. This value can be used to sort the search results, and the lower the value the better the match.

        The ``bm25`` function accepts optional parameters that allow you to specify weights for the various columns. If no weights are specified, all columns are considered of equal importance.

        .. code-block:: python

            query = (DocumentIndex
                     .select(
                         DocumentIndex,
                         DocumentIndex.bm25().alias('score'))
                     .where(DocumentIndex.match('search phrase'))
                     .order_by(DocumentIndex.bm25()))

            for search_result in query:
                print search_result.title, search_result.score

    .. py:classmethod:: rebuild()

        Rebuild the search index -- this only works when the ``content`` option
        was specified during table creation.

    .. py:classmethod:: optimize()

        Optimize the search index.


.. py:class:: SearchField([unindexed=False[, db_column=None[, coerce=None]]])

    :param unindexed: Whether the contents of this field should be excluded from the full-text search index.
    :param db_column: Name of the underlying database column.
    :param coerce: Function used to convert the value from the database into the appropriate Python format.


.. py:class:: JSONField()

    Field class suitable for working with JSON stored and manipulated using the `JSON1 extension <https://www.sqlite.org/json1.html>`_.

    Most functions that operate on JSON fields take a ``path`` argument. The JSON documents specify that the path should begin with ``'$'`` followed by zero or more instances of ``'.objectlabel'`` or ``'[arrayindex]'``. Peewee simplifies this by allowing you to omit the ``'$'`` character and just specify the path you need or ``None`` for an empty path:

    * ``path=''`` --> ``'$'``
    * ``path='tags'`` --> ``'$.tags'``
    * ``path='[0][1].bar'`` --> ``'$[0][1].bar'``
    * ``path='metadata[0]'`` --> ``'$.metadata[0]'``
    * ``path='user.data.email'`` --> ``'$.user.data.email'``

    .. py:method:: length([path=None])

        Return the number of items in a JSON array at the given path. If the path is omitted, then return the number of items in the top-level array.

        `SQLite documentation <https://www.sqlite.org/json1.html#jarraylen>`_.

    .. py:method:: extract(path)

        Return the value at the given path. If the value is a JSON object or array, it will be decoded into a ``dict`` or ``list``. If the value is a scalar type, string or ``null`` then it will be returned as the appropriate Python type.

        `SQLite documentation <https://www.sqlite.org/json1.html#jex>`_.

        Example:

        .. code-block:: python

            # data looks like {'post': {'title': 'post 1', 'body': '...'}, ...}
            query = (Post
                     .select(Post.data.json_extract('post.title'))
                     .tuples())

            # Only the `title` value is extracted from the JSON data.
            for title, in query:
                print title

    .. py:method:: set(path, value[, path2, value2...])

        Set values stored in the input JSON string using the given path/value pairs. The ``set`` function returns a **new** JSON string formed by updating the input JSON with the given path/value pairs.

        If the path does not exist, it **will** be created.

        Similarly, if the path does exist, it **will** be overwritten.

        `SQLite documentation <https://www.sqlite.org/json1.html#jset>`_.

        .. _updating-json:

        Example:

        .. code-block:: python

            PostAlias = Post.alias()
            set_query = (PostAlias
                         .select(PostAlias.data.set(
                             'title', 'New title',
                             'tags', ['list', 'of', 'new', 'tags'],
                             'totally.new.field', 3,
                             'status.published', True))
                         .where(PostAlias.id == Post.id))

            # Update multiple fields at one time on the Post
            # with the title "Old title".
            query = (Post
                     .update(data=set_query)
                     .where(Post.data.extract('title') == 'Old title'))
            query.execute()

            post = (Post
                    .select()
                    .where(Post.data.extract('title') == 'New title')
                    .get())

            # Our new data has been added, even nested objects that did not
            # exist before. Any pre-existing data has also been preserved,
            # provided it was not over-written.
            assert post.data == {
                'title': 'New title',
                'tags': ['list', 'of', 'new', 'tags'],
                'totally': {'new': {'field: 3}},
                'status': {'published': True, 'draft': False},
                'other-field': ['this', 'was', 'here', 'before'],
                'another-old-field': 'etc, etc'}

    .. py:method:: insert(path, value[, path2, value2...])

        Insert the given path/value pairs into the JSON string stored in the field. The ``insert`` function returns a **new** JSON string formed by updating the input JSON with the given path/value pairs.

        If the path already exists, it will **not** be overwritten.

        `SQLite documentation <https://www.sqlite.org/json1.html#jins>`_.

    .. py:method:: replace(path, value[, path2, value2...])

        Replace values stored in the input JSON string using the given path/value pairs. The ``replace`` function returns a **new** JSON string formed by updating the input JSON with the given path/value pairs.

        If the path does not exist, it will **not** be created.

        `SQLite documentation <https://www.sqlite.org/json1.html#jrepl>`_.

    .. py:method:: remove(*paths)

        Remove values referenced by the given path(s). The ``remove`` function returns a **new** JSON string formed by removing the specified paths from the input JSON string.

        The process for removing fields from a JSON column is similar to the way you :py:meth:`~JSONField.set` them. For a code example, see :ref:`updating JSON data <updating-json>`.

        `SQLite documentation <https://www.sqlite.org/json1.html#jrm>`_.

    .. py:method:: json_type([path=None])

        Return a string indicating the type of object stored in the field. You can optionally supply a path to specify a sub-item. The types of objects are:

        * object
        * array
        * integer
        * real
        * true
        * false
        * text
        * null  <-- the string "null" means an actual NULL value
        * NULL  <-- an actual NULL value means the path was not found

        `SQLite documentation <https://www.sqlite.org/json1.html#jtype>`_.

    .. py:method:: children([path=None])

        The ``children`` function corresponds to ``json_each``, a table-valued function that walks the JSON value provided and returns the immediate children of the top-level array or object. If a path is specified, then that path is treated as the top-most element.

        The rows returned by calls to ``children()`` have the following attributes:

        * ``key``: the key of the current element relative to its parent.
        * ``value``: the value of the current element.
        * ``type``: one of the data-types (see :py:meth:`~JSONField.json_type`).
        * ``atom``: the scalar value for primitive types, ``NULL`` for arrays and objects.
        * ``id``: a unique ID referencing the current node in the tree.
        * ``parent``: the ID of the containing node.
        * ``fullkey``: the full path describing the current element.
        * ``path``: the path to the container of the current row.

        For examples, see `my blog post on JSON1 <http://charlesleifer.com/blog/using-the-sqlite-json1-and-fts5-extensions-with-python/>`_.

        `SQLite documentation <https://www.sqlite.org/json1.html#jeach>`_.

    .. py:method:: tree([path=None])

        The ``tree`` function corresponds to ``json_tree``, a table-valued function that walks the JSON value provided and recursively returns all descendants of the given root node. If a path is specified, then that path is treated as the root node element.

        The rows returned by calls to ``tree()`` have the same attributes as rows returned by calls to :py:meth:`~JSONField.children`.

        For examples, see `my blog post on JSON1 <http://charlesleifer.com/blog/using-the-sqlite-json1-and-fts5-extensions-with-python/>`_.

        `SQLite documentation <https://www.sqlite.org/json1.html#jtree>`_.


.. py:class:: PrimaryKeyAutoIncrementField()

    Subclass of :py:class:`PrimaryKeyField` that uses a monotonically-increasing value for the primary key. This differs from the default SQLite primary key, which simply uses the "max + 1" approach to determining the next ID.


.. py:class:: RowIDField()

    Subclass of :py:class:`PrimaryKeyField` that provides access to the underlying ``rowid`` field used internally by SQLite.

    .. note:: When added to a Model, this field will act as the primary key. However, this field will not be included by default when selecting rows from the table.


.. py:class:: DocIDField()

    Subclass of :py:class:`PrimaryKeyField` that provides access to the underlying ``docid`` field used internally by SQLite's FTS3/4 virtual tables.

    .. note:: This field should not be created manually, as it is only needed on ``FTSModel`` classes, which include it already.


.. py:function:: match(lhs, rhs)

    Generate a SQLite `MATCH` expression for use in full-text searches.

    .. code-block:: python

        Document.select().where(match(Document.content, 'search term'))


.. py:class:: FTS5Model()

    Model class that should be used to implement virtual tables using the FTS5 extension. Documentation on the FTS5 extension `can be found here <http://sqlite.org/fts5.html>`_. This extension behaves very similarly to the FTS3 and FTS4 extensions, and the ``FTS5Model`` supports many of the same APIs as :py:class:`FTSModel`.

    The ``FTS5`` extension is more strict in enforcing that no column define any type or constraints. For this reason, only :py:class:`SearchField` objects can be used with ``FTS5Model`` implementations.

    Additionally, ``FTS5`` comes with a built-in implementation of the BM25 ranking function. Therefore, the ``search`` and ``search_bm25`` methods have been overridden to use the builtin ranking functions rather than user-defined functions.

    .. py:classmethod:: fts5_installed()

        Return a boolean indicating whether the FTS5 extension is installed. If it is not installed, an attempt will be made to load the extension.

    .. py:classmethod:: search(term[, weights=None[, with_score=False[, score_alias='score']]])

        Shorthand way of searching for a term and sorting results by the
        quality of the match. This is equivalent to the built-in ``rank`` value provided by the ``FTS5`` extension.

        :param str term: Search term to use.
        :param weights: A list of weights for the columns, ordered with respect to the column's position in the table. **Or**, a dictionary keyed by the field or field name and mapped to a value.
        :param with_score: Whether the score should be returned as part of the ``SELECT`` statement.
        :param str score_alias: Alias to use for the calculated rank score. This is the attribute you will use to access the score if ``with_score=True``.

        .. code-block:: python

            # Simple search.
            docs = DocumentIndex.search('search term')
            for result in docs:
                print result.title

            # More complete example.
            docs = DocumentIndex.search(
                'search term',
                weights={'title': 2.0, 'content': 1.0},
                with_score=True,
                score_alias='search_score')
            for result in docs:
                print result.title, result.search_score

    .. py:classmethod:: search_bm25(term[, weights=None[, with_score=False[, score_alias='score']]])

        With FTS5, the ``search_bm25`` method is the same as the :py:meth:`FTS5Model.search` method.

    .. py:classmethod:: VocabModel([table_type='row'|'col'[, table_name=None]])

        :param table_type: Either ``'row'`` or ``'col'``.
        :param table_name: Name for the vocab table. If not specified, will be "fts5tablename_v".


.. _sqlite_closure:

.. py:function:: ClosureTable(model_class[, foreign_key=None])

    Factory function for creating a model class suitable for working with a `transitive closure <http://www.sqlite.org/cgi/src/artifact/636024302cde41b2bf0c542f81c40c624cfb7012>`_ table. Closure tables are :py:class:`VirtualModel` subclasses that work with the transitive closure SQLite extension. These special tables are designed to make it easy to efficiently query heirarchical data. The SQLite extension manages an AVL tree behind-the-scenes, transparently updating the tree when your table changes and making it easy to perform common queries on heirarchical data.

    To use the closure table extension in your project, you need:

    1. A copy of the SQLite extension. The source code can be found in the `SQLite code repository <http://www.sqlite.org/cgi/src/artifact/636024302cde41b2bf0c542f81c40c624cfb7012>`_ or by cloning `this gist <https://gist.github.com/coleifer/7f3593c5c2a645913b92>`_:

       .. code-block:: console

           $ git clone https://gist.github.com/coleifer/7f3593c5c2a645913b92 closure
           $ cd closure/

    2. Compile the extension as a shared library, e.g.

       .. code-block:: console

           $ gcc -g -fPIC -shared closure.c -o closure.so

    3. Create a model for your heirarchical data. The only requirement here is that the model have an integer primary key and a self-referential foreign key. Any additional fields are fine.

       .. code-block:: python

           class Category(Model):
               name = CharField()
               metadata = TextField()
               parent = ForeignKeyField('self', index=True, null=True)  # Required.

           # Generate a model for the closure virtual table.
           CategoryClosure = ClosureTable(Category)

    4. In your application code, make sure you load the extension when you instantiate your :py:class:`Database` object. This is done by passing the path to the shared library to the :py:meth:`~SqliteExtDatabase.load_extension` method.

       .. code-block:: python

           db = SqliteExtDatabase('my_database.db')
           db.load_extension('/path/to/closure')

    :param model_class: The model class containing the nodes in the tree.
    :param foreign_key: The self-referential parent-node field on the model class. If not provided, peewee will introspect the model to find a suitable key.
    :return: Returns a :py:class:`VirtualModel` for working with a closure table.

    .. warning:: There are two caveats you should be aware of when using the ``transitive_closure`` extension. First, it requires that your *source model* have an integer primary key. Second, it is strongly recommended that you create an index on the self-referential foreign key.

    Example code:

    .. code-block:: python

        db = SqliteExtDatabase('my_database.db')
        db.load_extension('/path/to/closure')

        class Category(Model):
            name = CharField()
            parent = ForiegnKeyField('self', index=True, null=True)  # Required.

            class Meta:
                database = db

        CategoryClosure = ClosureTable(Category)

        # Create the tables if they do not exist.
        db.create_tables([Category, CategoryClosure], True)

    It is now possible to perform interesting queries using the data from the closure table:

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


    The :py:class:`VirtualTable` returned by this function contains a handful of interesting methods. The model will be a subclass of :py:class:`BaseClosureTable`.

    .. py:class:: BaseClosureTable()

        .. py:attribute:: id

            A field for the primary key of the given node.

        .. py:attribute:: depth

            A field representing the relative depth of the given node.

        .. py:attribute:: root

            A field representing the relative root node.

        .. py:method:: descendants(node[, depth=None[, include_node=False]])

            Retrieve all descendants of the given node. If a depth is specified, only nodes at that depth (relative to the given node) will be returned.

            .. code-block:: python

                node = Category.get(Category.name == 'Electronics')

                # Direct child categories.
                children = CategoryClosure.descendants(node, depth=1)

                # Grand-child categories.
                children = CategoryClosure.descendants(node, depth=2)

                # Descendants at all depths.
                all_descendants = CategoryClosure.descendants(node)


        .. py:method:: ancestors(node[, depth=None[, include_node=False]])

            Retrieve all ancestors of the given node. If a depth is specified, only nodes at that depth (relative to the given node) will be returned.

            .. code-block:: python

                node = Category.get(Category.name == 'Laptops')

                # All ancestors.
                all_ancestors = CategoryClosure.ancestors(node)

                # Grand-parent category.
                grandparent = CategoryClosure.ancestores(node, depth=2)

        .. py:method:: siblings(node[, include_node=False])

            Retrieve all nodes that are children of the specified node's parent.

    .. note:: For an in-depth discussion of the SQLite transitive closure extension, check out this blog post, `Querying Tree Structures in SQLite using Python and the Transitive Closure Extension <http://charlesleifer.com/blog/querying-tree-structures-in-sqlite-using-python-and-the-transitive-closure-extension/>`_.

.. _sqliteq:

SqliteQ
-------

The ``playhouse.sqliteq`` module provides a subclass of :py:class:`SqliteExtDatabase`,
that will serialize concurrent access to a SQLite database. The :py:class:`SqliteQueueDatabase`
is meant to be used as a drop-in replacement, and all the magic happens below
the public APIs. This should hopefully make it very easy to integrate into an
existing application.

.. note::
    This is a new module and should be considered alpha-quality software.

Explanation
^^^^^^^^^^^

It is important to understand the way SQLite handles concurrency when using
`write-ahead logging <https://www.sqlite.org/wal.html>`_, but in the simpleset
terms only one connection can write to the database at a time **and** any
number of other connections can read while the database is being written to.
Or, in other words, readers don't block the writer, and the writer doesn't
block the readers.

An example that comes to my mind is a web application, which handles each
request in a separate thread/greenlet. If the application is particularly busy
and there are multiple connections open at a given point in time, you can end
up in a bad situation quickly because SQLite limits you to one writer. This
typically manifests as ``OperationalError: database is locked`` exceptions.

Due to the global interpreter lock, however, Python appears single-threaded to
other applications (only one thread can run Python code at a time, per
interpreter process). It follows then, that even though multiple threads are
attempting to access the SQLite database, SQLite only sees one thread accessing
the database at any point in time.

So, what we can do is create a single *worker* thread that is responsible for
all writes to the database, and have our other request-handling threads
hand-off their writes. In this way, we'll have our cake and eat it, too -- our
Python application can queue-up writes from as many threads as it wants and we
should hardly notice the performance hit that comes from pushing all database
accesses through a single thread.

Code sample
^^^^^^^^^^^

Creating a database instance does not require any special handling. The
:py:class:`SqliteQueueDatabase` accepts some special parameters which you
should be aware of, though. If you are using `gevent <http://gevent.org>`_, you
must specify ``use_gevent=True`` when instantiating your database -- this way
Peewee will know to use the appropriate objects for handling queueing, thread
creation, and locking.

.. code-block:: python

    from playhouse.sqliteq import SqliteQueueDatabase

    db = SqliteQueueDatabase(
        'my_app.db',
        use_gevent=False,  # Use standard library "threading" module.
        autostart=False,  # Do not automatically start the workers.
        queue_max_size=1024,  # Max. # of pending writes that can accumulate.
        readers=4,  # Size of reader thread-pool - these handle non-writes.
        results_timeout=5.0)  # Max. time to wait for query to be executed.


If ``autostart=False``, as in the above example, you will need to call
:py:meth:`~SqliteQueueDatabase.start` to bring up the worker threads that will
do the actual query execution. Additionally, because the connections are
managed by the database class itself, you do not need to call
:py:meth:`~Database.connect` or :py:meth:`~Database.close` at any point in your
application.

.. code-block:: python

    @app.before_first_request
    def _start_worker_threads():
        db.start()

When your application is ready to terminate, use the
:py:meth:`~SqliteQueueDatabase.stop` method to shut down the worker threads.
If there was a backlog of work, then this method will block until all pending
work is finished (though no new work is allowed).

.. code-block:: python

    import atexit

    @atexit.register
    def _stop_worker_threads():
        db.stop()


Lastly, the :py:meth:`~SqliteQueueDatabase.is_stopped` method can be used to
determine whether the database workers are up and running.


.. _sqlite_udf:

Sqlite User-Defined Functions
-----------------------------

The ``sqlite_udf`` playhouse module contains a number of user-defined functions, aggregates, and table-valued functions, which you may find useful. The functions are grouped in collections and you can register these user-defined extensions individually, by collection, or register everything.

Scalar functions are functions which take a number of parameters and return a single value. For example, converting a string to upper-case, or calculating the MD5 hex digest.

Aggregate functions are like scalar functions that operate on multiple rows of data, producing a single result. For example, calculating the sum of a list of integers, or finding the smallest value in a particular column.

Table-valued functions are simply functions that can return multiple rows of data. For example, a regular-expression search function that returns all the matches in a given string, or a function that accepts two dates and generates all the intervening days.

.. note:: To use table-valued functions, you will need to install the ``vtfunc`` module. The ``vtfunc`` module is available `on GitHub <https://github.com/coleifer/sqlite-vtfunc>`_ or can be installed using ``pip``.

Functions, listed by collection name
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Scalar functions are indicated by ``(f)``, aggregate functions by ``(a)``, and table-valued functions by ``(t)``.

* ``CONTROL_FLOW``
  * :py:func:`if_then_else` (f)
* ``DATE``
  * :py:func:`strip_tz` (f)
  * :py:func:`human_delta` (f)
  * :py:func:`mintdiff` (a)
  * :py:func:`avgtdiff` (a)
  * :py:func:`duration` (a)
  * :py:func:`date_series` (t)
* ``FILE``
  * :py:func:`file_ext` (f)
  * :py:func:`file_read` (f)
* ``HELPER``
  * :py:func:`gzip` (f)
  * :py:func:`gunzip` (f)
  * :py:func:`hostname` (f)
  * :py:func:`toggle` (f)
  * :py:func:`setting` (f)
  * :py:func:`clear_toggles` (f)
  * :py:func:`clear_settings` (f)
* ``MATH``
  * :py:func:`randomrange` (f)
  * :py:func:`gauss_distribution` (f)
  * :py:func:`sqrt` (f)
  * :py:func:`tonumber` (f)
  * :py:func:`mode` (a)
  * :py:func:`minrange` (a)
  * :py:func:`avgrange` (a)
  * :py:func:`range` (a)
  * :py:func:`median` (a) (requires cython)
* ``STRING``
  * :py:func:`substr_count` (f)
  * :py:func:`strip_chars` (f)
  * :py:func:`md5` (f)
  * :py:func:`sha1` (f)
  * :py:func:`sha256` (f)
  * :py:func:`sha512` (f)
  * :py:func:`adler32` (f)
  * :py:func:`crc32` (f)
  * :py:func:`damerau_levenshtein_dist` (f) (requires cython)
  * :py:func:`levenshtein_dist` (f) (requires cython)
  * :py:func:`str_dist` (f) (requires cython)
  * :py:func:`regex_search` (t)

.. _apsw:

apsw, an advanced sqlite driver
-------------------------------

The ``apsw_ext`` module contains a database class suitable for use with
the apsw sqlite driver.

APSW Project page: https://github.com/rogerbinns/apsw

APSW is a really neat library that provides a thin wrapper on top of SQLite's
C interface, making it possible to use all of SQLite's advanced features.

Here are just a few reasons to use APSW, taken from the documentation:

* APSW gives all functionality of SQLite, including virtual tables, virtual
  file system, blob i/o, backups and file control.
* Connections can be shared across threads without any additional locking.
* Transactions are managed explicitly by your code.
* APSW can handle nested transactions.
* Unicode is handled correctly.
* APSW is faster.

For more information on the differences between apsw and pysqlite,
check `the apsw docs <http://rogerbinns.github.io/apsw/>`_.

How to use the APSWDatabase
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from apsw_ext import *

    db = APSWDatabase(':memory:')

    class BaseModel(Model):
        class Meta:
            database = db

    class SomeModel(BaseModel):
        col1 = CharField()
        col2 = DateTimeField()


apsw_ext API notes
^^^^^^^^^^^^^^^^^^

:py:class:`APSWDatabase` extends the :py:class:`SqliteExtDatabase` and inherits its advanced features.

.. py:class:: APSWDatabase(database, **connect_kwargs)

    :param string database: filename of sqlite database
    :param connect_kwargs: keyword arguments passed to apsw when opening a connection

    .. py:method:: transaction([lock_type='deferred'])

        Functions just like the :py:meth:`Database.transaction` context manager,
        but accepts an additional parameter specifying the type of lock to use.

        :param string lock_type: type of lock to use when opening a new transaction

    .. py:method:: register_module(mod_name, mod_inst)

        Provides a way of globally registering a module.  For more information,
        see the `documentation on virtual tables <http://rogerbinns.github.io/apsw/vtable.html>`_.

        :param string mod_name: name to use for module
        :param object mod_inst: an object implementing the `Virtual Table <http://rogerbinns.github.io/apsw/vtable.html#vttable-class>`_ interface

    .. py:method:: unregister_module(mod_name)

        Unregister a module.

        :param string mod_name: name to use for module

.. note::
    Be sure to use the ``Field`` subclasses defined in the ``apsw_ext``
    module, as they will properly handle adapting the data types for storage.

    For example, instead of using ``peewee.DateTimeField``, be sure you are importing
    and using ``playhouse.apsw_ext.DateTimeField``.

.. _berkeleydb:

BerkeleyDB backend
------------------

BerkeleyDB provides a `SQLite-compatible API <http://www.oracle.com/technetwork/database/database-technologies/berkeleydb/overview/sql-160887.html>`_. BerkeleyDB's SQL API has many advantages over SQLite:

* Higher transactions-per-second in multi-threaded environments.
* Built-in replication and hot backup.
* Fewer system calls, less resource utilization.
* Multi-version concurrency control.

For more details, Oracle has published a short `technical overview <http://www.oracle.com/technetwork/database/berkeleydb/learnmore/bdbvssqlite-wp-186779.pdf>`_.

In order to use peewee with BerkeleyDB, you need to compile BerkeleyDB with the SQL API enabled. Then compile the Python SQLite driver against BerkeleyDB's sqlite replacement.

Begin by downloading and compiling BerkeleyDB:

.. code-block:: console

    wget http://download.oracle.com/berkeley-db/db-6.0.30.tar.gz
    tar xzf db-6.0.30.tar.gz
    cd db-6.0.30/build_unix
    export CFLAGS='-DSQLITE_ENABLE_FTS3=1 -DSQLITE_ENABLE_FTS3_PARENTHESIS=1 -DSQLITE_ENABLE_UPDATE_DELETE_LIMIT -DSQLITE_SECURE_DELETE -DSQLITE_SOUNDEX -DSQLITE_ENABLE_RTREE=1 -fPIC'
    ../dist/configure --enable-static --enable-shared --enable-sql --enable-sql-compat
    make
    sudo make prefix=/usr/local/ install

Then get a copy of the standard library SQLite driver and build it against BerkeleyDB:

.. code-block:: console

    git clone https://github.com/ghaering/pysqlite
    cd pysqlite
    sed -i "s|#||g" setup.cfg
    python setup.py build
    sudo python setup.py install

You can also find up-to-date `step by step instructions <http://charlesleifer.com/blog/building-the-python-sqlite-driver-for-use-with-berkeleydb/>`_ on my blog.

.. py:class:: BerkeleyDatabase(database, **kwargs)

    :param bool multiversion: Enable multiversion concurrency control. Default is ``False``.
    :param int page_size: Set the page size ``PRAGMA``. This option only works on new databases.
    :param int cache_size: Set the cache size ``PRAGMA``.

    Subclass of the :py:class:`SqliteExtDatabase` that supports connecting to BerkeleyDB-backed version of SQLite.

    .. py:classmethod:: check_pysqlite()

        Check whether ``pysqlite2`` was compiled against the BerkeleyDB SQLite. Returns ``True`` or ``False``.

    .. py:classmethod:: check_libsqlite()

        Check whether ``libsqlite3`` is the BerkeleyDB SQLite implementation. Returns ``True`` or ``False``.


.. _sqlcipher_ext:

Sqlcipher backend
-----------------

* Although this extention's code is short, it has not been properly
  peer-reviewed yet and may have introduced vulnerabilities.
* The code contains minimum values for `passphrase` length and
  `kdf_iter`, as well as a default value for the later.
  **Do not** regard these numbers as advice. Consult the docs at
  http://sqlcipher.net/sqlcipher-api/ and security experts.

Also note that this code relies on pysqlcipher_ and sqlcipher_, and
the code there might have vulnerabilities as well, but since these
are widely used crypto modules, we can expect "short zero days" there.

..  _pysqlcipher: https://pypi.python.org/pypi/pysqlcipher
..  _sqlcipher: http://sqlcipher.net

sqlcipher_ext API notes
^^^^^^^^^^^^^^^^^^^^^^^

.. py:class:: SqlCipherDatabase(database, passphrase, kdf_iter=64000, **kwargs)

    Subclass of :py:class:`SqliteDatabase` that stores the database
    encrypted. Instead of the standard ``sqlite3`` backend, it uses pysqlcipher_:
    a python wrapper for sqlcipher_, which -- in turn -- is an encrypted wrapper
    around ``sqlite3``, so the API is *identical* to :py:class:`SqliteDatabase`'s,
    except for object construction parameters:

    :param database: Path to encrypted database filename to open [or create].
    :param passphrase: Database encryption passphrase: should be at least 8 character
        long (or an error is raised), but it is *strongly advised* to enforce better
        `passphrase strength`_ criteria in your implementation.
    :param kdf_iter: [Optional] number of PBKDF2_ iterations.

    * If the ``database`` file doesn't exist, it will be *created* with
      encryption by a key derived from ``passhprase`` with ``kdf_iter``
      PBKDF2_ iterations.
    * When trying to open an existing database, ``passhprase`` and ``kdf_iter``
      should be *identical* to the ones used when it was created.

.. _PBKDF2: https://en.wikipedia.org/wiki/PBKDF2
.. _passphrase strength: https://en.wikipedia.org/wiki/Password_strength

Notes:

    * [Hopefully] there's no way to tell whether the passphrase is wrong
      or the file is corrupt.
      In both cases -- *the first time we try to acces the database* -- a
      :py:class:`DatabaseError` error is raised,
      with the *exact* message: ``"file is encrypted or is not a database"``.

      As mentioned above, this only happens when you *access* the databse,
      so if you need to know *right away* whether the passphrase was correct,
      you can trigger this check by calling [e.g.]
      :py:meth:`~Database.get_tables()` (see example below).

    * Most applications can expect failed attempts to open the database
      (common case: prompting the user for ``passphrase``), so
      the database can't be hardwired into the :py:class:`Meta` of
      model classes. To defer initialization, pass `None` in to the
      database.

Example:

.. code-block:: python

    db = SqlCipherDatabase(None)

    class BaseModel(Model):
        """Parent for all app's models"""
        class Meta:
            # We won't have a valid db until user enters passhrase.
            database = db

    # Derive our model subclasses
    class Person(BaseModel):
        name = CharField(primary_key=True)

    right_passphrase = False
    while not right_passphrase:
        db.init(
            'testsqlcipher.db',
            passphrase=get_passphrase_from_user())

        try:  # Actually execute a query against the db to test passphrase.
            db.get_tables()
        except DatabaseError as exc:
            # We only allow a specific [somewhat cryptic] error message.
            if exc.args[0] != 'file is encrypted or is not a database':
                raise exc
            else:
                tell_user_the_passphrase_was_wrong()
                db.init(None)  # Reset the db.
        else:
            # The password was correct.
            right_passphrase = True

See also: a slightly more elaborate `example <https://gist.github.com/thedod/11048875#file-testpeeweesqlcipher-py>`_.


.. _postgres_ext:

Postgresql Extensions
---------------------

The postgresql extensions module provides a number of "postgres-only" functions,
currently:

* :ref:`hstore support <hstore>`
* :ref:`json support <pgjson>`, including ``jsonb`` for Postgres 9.4.
* :ref:`server-side cursors <server_side_cursors>`
* :ref:`full-text search <pg_fts>`
* :py:class:`ArrayField` field type, for storing arrays.
* :py:class:`HStoreField` field type, for storing key/value pairs.
* :py:class:`JSONField` field type, for storing JSON data.
* :py:class:`BinaryJSONField` field type for the ``jsonb`` JSON data type.
* :py:class:`TSVectorField` field type, for storing full-text search data.
* :py:class:`DateTimeTZ` field type, a timezone-aware datetime field.

In the future I would like to add support for more of postgresql's features.
If there is a particular feature you would like to see added, please
`open a Github issue <https://github.com/coleifer/peewee/issues>`_.

.. warning:: In order to start using the features described below, you will need to use the extension :py:class:`PostgresqlExtDatabase` class instead of :py:class:`PostgresqlDatabase`.

The code below will assume you are using the following database and base model:

.. code-block:: python

    from playhouse.postgres_ext import *

    ext_db = PostgresqlExtDatabase('peewee_test', user='postgres')

    class BaseExtModel(Model):
        class Meta:
            database = ext_db

.. _hstore:

hstore support
^^^^^^^^^^^^^^

`Postgresql hstore <http://www.postgresql.org/docs/current/static/hstore.html>`_ is
an embedded key/value store.  With hstore, you can store arbitrary key/value pairs
in your database alongside structured relational data.

Currently the ``postgres_ext`` module supports the following operations:

* Store and retrieve arbitrary dictionaries
* Filter by key(s) or partial dictionary
* Update/add one or more keys to an existing dictionary
* Delete one or more keys from an existing dictionary
* Select keys, values, or zip keys and values
* Retrieve a slice of keys/values
* Test for the existence of a key
* Test that a key has a non-NULL value


Using hstore
^^^^^^^^^^^^

To start with, you will need to import the custom database class and the hstore
functions from ``playhouse.postgres_ext`` (see above code snippet).  Then, it is
as simple as adding a :py:class:`HStoreField` to your model:

.. code-block:: python

    class House(BaseExtModel):
        address = CharField()
        features = HStoreField()


You can now store arbitrary key/value pairs on ``House`` instances:

.. code-block:: pycon

    >>> h = House.create(address='123 Main St', features={'garage': '2 cars', 'bath': '2 bath'})
    >>> h_from_db = House.get(House.id == h.id)
    >>> h_from_db.features
    {'bath': '2 bath', 'garage': '2 cars'}


You can filter by keys or partial dictionary:

.. code-block:: pycon

    >>> f = House.features
    >>> House.select().where(f.contains('garage')) # <-- all houses w/garage key
    >>> House.select().where(f.contains(['garage', 'bath'])) # <-- all houses w/garage & bath
    >>> House.select().where(f.contains({'garage': '2 cars'})) # <-- houses w/2-car garage

Suppose you want to do an atomic update to the house:

.. code-block:: pycon

    >>> f = House.features
    >>> new_features = House.features.update({'bath': '2.5 bath', 'sqft': '1100'})
    >>> query = House.update(features=new_features)
    >>> query.where(House.id == h.id).execute()
    1
    >>> h = House.get(House.id == h.id)
    >>> h.features
    {'bath': '2.5 bath', 'garage': '2 cars', 'sqft': '1100'}


Or, alternatively an atomic delete:

.. code-block:: pycon

    >>> query = House.update(features=f.delete('bath'))
    >>> query.where(House.id == h.id).execute()
    1
    >>> h = House.get(House.id == h.id)
    >>> h.features
    {'garage': '2 cars', 'sqft': '1100'}


Multiple keys can be deleted at the same time:

.. code-block:: pycon

    >>> query = House.update(features=f.delete('garage', 'sqft'))

You can select just keys, just values, or zip the two:

.. code-block:: pycon

    >>> f = House.features
    >>> for h in House.select(House.address, f.keys().alias('keys')):
    ...     print h.address, h.keys

    123 Main St [u'bath', u'garage']

    >>> for h in House.select(House.address, f.values().alias('vals')):
    ...     print h.address, h.vals

    123 Main St [u'2 bath', u'2 cars']

    >>> for h in House.select(House.address, f.items().alias('mtx')):
    ...     print h.address, h.mtx

    123 Main St [[u'bath', u'2 bath'], [u'garage', u'2 cars']]

You can retrieve a slice of data, for example, all the garage data:

.. code-block:: pycon

    >>> f = House.features
    >>> for h in House.select(House.address, f.slice('garage').alias('garage_data')):
    ...     print h.address, h.garage_data

    123 Main St {'garage': '2 cars'}

You can check for the existence of a key and filter rows accordingly:

.. code-block:: pycon

    >>> for h in House.select(House.address, f.exists('garage').alias('has_garage')):
    ...     print h.address, h.has_garage

    123 Main St True

    >>> for h in House.select().where(f.exists('garage')):
    ...     print h.address, h.features['garage'] # <-- just houses w/garage data

    123 Main St 2 cars

.. _pgjson:

JSON Support
^^^^^^^^^^^^

peewee has basic support for Postgres' native JSON data type, in the form of
:py:class:`JSONField`. As of version 2.4.7, peewee also supports the Postgres 9.4 binary json ``jsonb`` type, via :py:class:`BinaryJSONField`.

.. warning::
  Postgres supports a JSON data type natively as of 9.2 (full support in 9.3). In
  order to use this functionality you must be using the correct version of Postgres
  with `psycopg2` version 2.5 or greater.

  To use :py:class:`BinaryJSONField`, which has many performance and querying advantages, you must have Postgres 9.4 or later.

.. note::
  You must be sure your database is an instance of :py:class:`PostgresqlExtDatabase`
  in order to use the `JSONField`.

Here is an example of how you might declare a model with a JSON field:

.. code-block:: python

    import json
    import urllib2
    from playhouse.postgres_ext import *

    db = PostgresqlExtDatabase('my_database')  # note

    class APIResponse(Model):
        url = CharField()
        response = JSONField()

        class Meta:
            database = db

        @classmethod
        def request(cls, url):
            fh = urllib2.urlopen(url)
            return cls.create(url=url, response=json.loads(fh.read()))

    APIResponse.create_table()

    # Store a JSON response.
    offense = APIResponse.request('http://wtf.charlesleifer.com/api/offense/')
    booking = APIResponse.request('http://wtf.charlesleifer.com/api/booking/')

    # Query a JSON data structure using a nested key lookup:
    offense_responses = APIResponse.select().where(
      APIResponse.response['meta']['model'] == 'offense')

    # Retrieve a sub-key for each APIResponse. By calling .as_json(), the
    # data at the sub-key will be returned as Python objects (dicts, lists,
    # etc) instead of serialized JSON.
    q = (APIResponse
         .select(
           APIResponse.data['booking']['person'].as_json().alias('person'))
         .where(
           APIResponse.data['meta']['model'] == 'booking'))

    for result in q:
        print result.person['name'], result.person['dob']

The :py:class:`BinaryJSONField` works the same and supports the same operations as the regular :py:class:`JSONField`, but provides several additional operations for testing *containment*. Using the binary json field, you can test whether your JSON data contains other partial JSON structures (:py:meth:`~BinaryJSONField.contains`, :py:meth:`~BinaryJSONField.contains_any`, :py:meth:`~BinaryJSONField.contains_all`), or whether it is a subset of a larger JSON document (:py:meth:`~BinaryJSONField.contained_by`).

For more examples, see the :py:class:`JSONField` and :py:class:`BinaryJSONField` API documents below.

.. _server_side_cursors:

Server-side cursors
^^^^^^^^^^^^^^^^^^^

When psycopg2 executes a query, normally all results are fetched and returned to
the client by the backend.  This can cause your application to use a lot of memory
when making large queries.  Using server-side cursors, results are returned a
little at a time (by default 2000 records).  For the definitive reference, please see the `psycopg2 documentation <http://initd.org/psycopg/docs/usage.html#server-side-cursors>`_.

.. note:: To use server-side (or named) cursors, you must be using :py:class:`PostgresqlExtDatabase`.

To execute a query using a server-side cursor, simply wrap your select query
using the :py:func:`ServerSide` helper:

.. code-block:: python

    large_query = PageView.select()  # Build query normally.

    # Iterate over large query inside a transaction.
    for page_view in ServerSide(large_query):
        # do some interesting analysis here.
        pass

    # Server-side resources are released.

If you would like all ``SELECT`` queries to automatically use a server-side
cursor, you can specify this when creating your :py:class:`PostgresqlExtDatabase`:

.. code-block:: python

    from postgres_ext import PostgresqlExtDatabase

    ss_db = PostgresqlExtDatabase('my_db', server_side_cursors=True)

.. note::
    Server-side cursors live only as long as the transaction, so for this reason
    peewee will not automatically call ``commit()`` after executing a ``SELECT``
    query.  If you do not ``commit`` after you are done iterating, you will not
    release the server-side resources until the connection is closed (or the
    transaction is committed later).  Furthermore, since peewee will by default
    cache rows returned by the cursor, you should always call ``.iterator()``
    when iterating over a large query.

    If you are using the :py:func:`ServerSide` helper, the transaction and
    call to ``iterator()`` will be handled transparently.


.. _pg_fts:

Full-text search
^^^^^^^^^^^^^^^^

Postgresql provides `sophisticated full-text search <http://www.postgresql.org/docs/9.3/static/textsearch.html>`_ using special data-types (``tsvector`` and ``tsquery``). Documents should be stored or converted to the ``tsvector`` type, and search queries should be converted to ``tsquery``.

For simple cases, you can simply use the :py:func:`Match` function, which will automatically perform the appropriate conversions, and requires no schema changes:

.. code-block:: python

    def blog_search(query):
        return Blog.select().where(
            (Blog.status == Blog.STATUS_PUBLISHED) &
            Match(Blog.content, query))

The :py:func:`Match` function will automatically convert the left-hand operand to a ``tsvector``, and the right-hand operand to a ``tsquery``. For better performance, it is recommended you create a ``GIN`` index on the column you plan to search:

.. code-block:: sql

    CREATE INDEX blog_full_text_search ON blog USING gin(to_tsvector(content));

Alternatively, you can use the :py:class:`TSVectorField` to maintain a dedicated column for storing ``tsvector`` data:

.. code-block:: python

    class Blog(Model):
        content = TextField()
        search_content = TSVectorField()

You will need to explicitly convert the incoming text data to ``tsvector`` when inserting or updating the ``search_content`` field:

.. code-block:: python

    content = 'Excellent blog post about peewee ORM.'
    blog_entry = Blog.create(
        content=content,
        search_content=fn.to_tsvector(content))

.. note:: If you are using the :py:class:`TSVectorField`, it will automatically be created with a GIN index.


postgres_ext API notes
^^^^^^^^^^^^^^^^^^^^^^

.. py:class:: PostgresqlExtDatabase(database[, server_side_cursors=False[, register_hstore=True[, ...]]])

    Identical to :py:class:`PostgresqlDatabase` but required in order to support:

    * :ref:`server_side_cursors`
    * :py:class:`ArrayField`
    * :py:class:`DateTimeTZField`
    * :py:class:`JSONField`
    * :py:class:`BinaryJSONField`
    * :py:class:`HStoreField`
    * :py:class:`TSVectorField`

    :param str database: Name of database to connect to.
    :param bool server_side_cursors: Whether ``SELECT`` queries should utilize
        server-side cursors.
    :param bool register_hstore: Register the HStore extension with the connection.

    If using ``server_side_cursors``, also be sure to wrap your queries with
    :py:func:`ServerSide`.

    If you do not wish to use the HStore extension, you can specify ``register_hstore=False``.

    .. warning::
        The :py:class:`PostgresqlExtDatabase` by default will attempt to register the ``HSTORE`` extension. Most distributions and recent versions include this, but in some cases the extension may not be available. If you **do not** plan to use the :ref:`HStore features of peewee <hstore>`, you can pass ``register_hstore=False`` when initializing your :py:class:`PostgresqlExtDatabase`.

.. py:function:: ServerSide(select_query)

    Wrap the given select query in a transaction, and call it's :py:meth:`~SelectQuery.iterator`
    method to avoid caching row instances.  In order for the server-side resources
    to be released, be sure to exhaust the generator (iterate over all the rows).

    :param select_query: a :py:class:`SelectQuery` instance.
    :rtype: ``generator``

    Usage:

    .. code-block:: python

        large_query = PageView.select()
        for page_view in ServerSide(large_query):
            # Do something interesting.
            pass

        # At this point server side resources are released.

.. _pgarrays:

.. py:class:: ArrayField([field_class=IntegerField[, dimensions=1]])

    Field capable of storing arrays of the provided `field_class`.

    :param field_class: a subclass of :py:class:`Field`, e.g. :py:class:`IntegerField`.
    :param int dimensions: dimensions of array.

    You can store and retrieve lists (or lists-of-lists):

    .. code-block:: python

        class BlogPost(BaseModel):
            content = TextField()
            tags = ArrayField(CharField)


        post = BlogPost(content='awesome', tags=['foo', 'bar', 'baz'])

    Additionally, you can use the ``__getitem__`` API to query values or slices
    in the database:

    .. code-block:: python

        # Get the first tag on a given blog post.
        first_tag = (BlogPost
                     .select(BlogPost.tags[0].alias('first_tag'))
                     .where(BlogPost.id == 1)
                     .dicts()
                     .get())

        # first_tag = {'first_tag': 'foo'}

    Get a slice of values:

    .. code-block:: python

        # Get the first two tags.
        two_tags = (BlogPost
                    .select(BlogPost.tags[:2].alias('two'))
                    .dicts()
                    .get())
        # two_tags = {'two': ['foo', 'bar']}

    .. py:method:: contains(*items)

        :param items: One or more items that must be in the given array field.

        .. code-block:: python

            # Get all blog posts that are tagged with both "python" and "django".
            Blog.select().where(Blog.tags.contains('python', 'django'))

    .. py:method:: contains_any(*items)

        :param items: One or more items to search for in the given array field.

        Like :py:meth:`~ArrayField.contains`, except will match rows where the
        array contains *any* of the given items.

        .. code-block:: python

            # Get all blog posts that are tagged with "flask" and/or "django".
            Blog.select().where(Blog.tags.contains_any('flask', 'django'))

.. py:class:: DateTimeTZField(*args, **kwargs)

    A timezone-aware subclass of :py:class:`DateTimeField`.

.. py:class:: HStoreField(*args, **kwargs)

    A field for storing and retrieving arbitrary key/value pairs.  For details
    on usage, see :ref:`hstore`.

    .. py:method:: keys()

        Returns the keys for a given row.

        .. code-block:: pycon

            >>> f = House.features
            >>> for h in House.select(House.address, f.keys().alias('keys')):
            ...     print h.address, h.keys

            123 Main St [u'bath', u'garage']

    .. py:method:: values()

        Return the values for a given row.

        .. code-block:: pycon

            >>> for h in House.select(House.address, f.values().alias('vals')):
            ...     print h.address, h.vals

            123 Main St [u'2 bath', u'2 cars']

    .. py:method:: items()

        Like python's ``dict``, return the keys and values in a list-of-lists:

        .. code-block:: pycon

            >>> for h in House.select(House.address, f.items().alias('mtx')):
            ...     print h.address, h.mtx

            123 Main St [[u'bath', u'2 bath'], [u'garage', u'2 cars']]

    .. py:method:: slice(*args)

        Return a slice of data given a list of keys.

        .. code-block:: pycon

            >>> f = House.features
            >>> for h in House.select(House.address, f.slice('garage').alias('garage_data')):
            ...     print h.address, h.garage_data

            123 Main St {'garage': '2 cars'}

    .. py:method:: exists(key)

        Query for whether the given key exists.

        .. code-block:: pycon

            >>> for h in House.select(House.address, f.exists('garage').alias('has_garage')):
            ...     print h.address, h.has_garage

            123 Main St True

            >>> for h in House.select().where(f.exists('garage')):
            ...     print h.address, h.features['garage'] # <-- just houses w/garage data

            123 Main St 2 cars

    .. py:method:: defined(key)

        Query for whether the given key has a value associated with it.

    .. py:method:: update(**data)

        Perform an atomic update to the keys/values for a given row or rows.

        .. code-block:: pycon

            >>> query = House.update(features=House.features.update(
            ...     sqft=2000,
            ...     year_built=2012))
            >>> query.where(House.id == 1).execute()

    .. py:method:: delete(*keys)

        Delete the provided keys for a given row or rows.

        .. note:: We will use an ``UPDATE`` query.

        .. code-block:: pycon

        >>> query = House.update(features=House.features.delete(
        ...     'sqft', 'year_built'))
        >>> query.where(House.id == 1).execute()

    .. py:method:: contains(value)

        :param value: Either a ``dict``, a ``list`` of keys, or a single key.

        Query rows for the existence of either:

        * a partial dictionary.
        * a list of keys.
        * a single key.

        .. code-block:: pycon

            >>> f = House.features
            >>> House.select().where(f.contains('garage')) # <-- all houses w/garage key
            >>> House.select().where(f.contains(['garage', 'bath'])) # <-- all houses w/garage & bath
            >>> House.select().where(f.contains({'garage': '2 cars'})) # <-- houses w/2-car garage

    .. py:method:: contains_any(*keys)

        :param keys: One or more keys to search for.

        Query rows for the existince of *any* key.

.. py:class:: JSONField(dumps=None, *args, **kwargs)

    Field class suitable for storing and querying arbitrary JSON.  When using
    this on a model, set the field's value to a Python object (either a ``dict``
    or a ``list``).  When you retrieve your value from the database it will be
    returned as a Python data structure.

    :param dumps: The default is to call json.dumps() or the dumps function. You can override this method to create a customized JSON wrapper.

    .. note:: You must be using Postgres 9.2 / psycopg2 2.5 or greater.

    .. note:: If you are using Postgres 9.4, strongly consider using the :py:class:`BinaryJSONField` instead as it offers better performance and more powerful querying options.

    Example model declaration:

    .. code-block:: python

        db = PostgresqlExtDatabase('my_db')

        class APIResponse(Model):
            url = CharField()
            response = JSONField()

            class Meta:
                database = db

    Example of storing JSON data:

    .. code-block:: python

        url = 'http://foo.com/api/resource/'
        resp = json.loads(urllib2.urlopen(url).read())
        APIResponse.create(url=url, response=resp)

        APIResponse.create(url='http://foo.com/baz/', response={'key': 'value'})

    To query, use Python's ``[]`` operators to specify nested key or array lookups:

    .. code-block:: python

        APIResponse.select().where(
            APIResponse.response['key1']['nested-key'] == 'some-value')

    To illustrate the use of the ``[]`` operators, imagine we have the following data stored in an ``APIResponse``:

    .. code-block:: javascript

        {
          "foo": {
            "bar": ["i1", "i2", "i3"],
            "baz": {
              "huey": "mickey",
              "peewee": "nugget"
            }
          }
        }

    Here are the results of a few queries:

    .. code-block:: python

        def get_data(expression):
            # Helper function to just retrieve the results of a
            # particular expression.
            query = (APIResponse
                     .select(expression.alias('my_data'))
                     .dicts()
                     .get())
            return query['my_data']

        # Accessing the foo -> bar subkey will return a JSON
        # representation of the list.
        get_data(APIResponse.data['foo']['bar'])
        # '["i1", "i2", "i3"]'

        # In order to retrieve this list as a Python list,
        # we will call .as_json() on the expression.
        get_data(APIResponse.data['foo']['bar'].as_json())
        # ['i1', 'i2', 'i3']

        # Similarly, accessing the foo -> baz subkey will
        # return a JSON representation of the dictionary.
        get_data(APIResponse.data['foo']['baz'])
        # '{"huey": "mickey", "peewee": "nugget"}'

        # Again, calling .as_json() will return an actual
        # python dictionary.
        get_data(APIResponse.data['foo']['baz'].as_json())
        # {'huey': 'mickey', 'peewee': 'nugget'}

        # When dealing with simple values, either way works as
        # you expect.
        get_data(APIResponse.data['foo']['bar'][0])
        # 'i1'

        # Calling .as_json() when the result is a simple value
        # will return the same thing as the previous example.
        get_data(APIResponse.data['foo']['bar'][0].as_json())
        # 'i1'

.. py:class:: BinaryJSONField(dumps=None, *args, **kwargs)

    Store and query arbitrary JSON documents. Data should be stored using normal Python ``dict`` and ``list`` objects, and when data is returned from the database, it will be returned using ``dict`` and ``list`` as well.

    For examples of basic query operations, see the above code samples for :py:class:`JSONField`. The example queries below will use the same ``APIResponse`` model described above.

    :param dumps: The default is to call json.dumps() or the dumps function. You can override this method to create a customized JSON wrapper.

    .. note:: You must be using Postgres 9.4 / psycopg2 2.5 or newer. If you are using Postgres 9.2 or 9.3, you can use the regular :py:class:`JSONField` instead.

    .. py:method:: contains(other)

        Test whether the given JSON data contains the given JSON fragment or key.

        Example:

        .. code-block:: python

            search_fragment = {
                'foo': {'bar': ['i2']}
            }
            query = (APIResponse
                     .select()
                     .where(APIResponse.data.contains(search_fragment)))

            # If we're searching for a list, the list items do not need to
            # be ordered in a particular way:
            query = (APIResponse
                     .select()
                     .where(APIResponse.data.contains({
                         'foo': {'bar': ['i2', 'i1']}})))

        We can pass in simple keys as well. To find APIResponses that contain the key ``foo`` at the top-level:

        .. code-block:: python

            APIResponse.select().where(APIResponse.data.contains('foo'))

        We can also search sub-keys using square-brackets:

        .. code-block:: python

            APIResponse.select().where(
                APIResponse.data['foo']['bar'].contains(['i2', 'i1']))

    .. py:method:: contains_any(*items)

        Search for the presence of one or more of the given items.

        .. code-block:: python

            APIResponse.select().where(
                APIResponse.data.contains_any('foo', 'baz', 'nugget'))

        Like :py:meth:`~BinaryJSONField.contains`, we can also search sub-keys:

        .. code-block:: python

            APIResponse.select().where(
                APIResponse.data['foo']['bar'].contains_any('i2', 'ix'))

    .. py:method:: contains_all(*items)

        Search for the presence of all of the given items.

        .. code-block:: python

            APIResponse.select().where(
                APIResponse.data.contains_all('foo'))

        Like :py:meth:`~BinaryJSONField.contains_any`, we can also search sub-keys:

        .. code-block:: python

            APIResponse.select().where(
                APIResponse.data['foo']['bar'].contains_all('i1', 'i2', 'i3'))

    .. py:method:: contained_by(other)

        Test whether the given JSON document is contained by (is a subset of) the given JSON document. This method is the inverse of :py:meth:`~BinaryJSONField.contains`.

        .. code-block:: python

            big_doc = {
                'foo': {
                    'bar': ['i1', 'i2', 'i3'],
                    'baz': {
                        'huey': 'mickey',
                        'peewee': 'nugget',
                    }
                },
                'other_key': ['nugget', 'bear', 'kitten'],
            }
            APIResponse.select().where(
                APIResponse.data.contained_by(big_doc))


.. py:function:: Match(field, query)

    Generate a full-text search expression, automatically converting the left-hand operand to a ``tsvector``, and the right-hand operand to a ``tsquery``.

    Example:

    .. code-block:: python

        def blog_search(query):
            return Blog.select().where(
                (Blog.status == Blog.STATUS_PUBLISHED) &
                Match(Blog.content, query))

.. py:class:: TSVectorField

    Field type suitable for storing ``tsvector`` data. This field will automatically be created with a ``GIN`` index for improved search performance.

    .. note::
        Data stored in this field will still need to be manually converted to the ``tsvector`` type.

     Example usage:

     .. code-block:: python

          class Blog(Model):
              content = TextField()
              search_content = TSVectorField()

          content = 'this is a sample blog entry.'
          blog_entry = Blog.create(
              content=content,
              search_content=fn.to_tsvector(content))  # Note `to_tsvector()`.


.. _dataset:

DataSet
-------

The *dataset* module contains a high-level API for working with databases modeled after the popular `project of the same name <https://dataset.readthedocs.io/en/latest/index.html>`_. The aims of the *dataset* module are to provide:

* A simplified API for working with relational data, along the lines of working with JSON.
* An easy way to export relational data as JSON or CSV.
* An easy way to import JSON or CSV data into a relational database.

A minimal data-loading script might look like this:

.. code-block:: python

    from playhouse.dataset import DataSet

    db = DataSet('sqlite:///:memory:')

    table = db['sometable']
    table.insert(name='Huey', age=3)
    table.insert(name='Mickey', age=5, gender='male')

    huey = table.find_one(name='Huey')
    print huey
    # {'age': 3, 'gender': None, 'id': 1, 'name': 'Huey'}

    for obj in table:
        print obj
    # {'age': 3, 'gender': None, 'id': 1, 'name': 'Huey'}
    # {'age': 5, 'gender': 'male', 'id': 2, 'name': 'Mickey'}

You can export or import data using :py:meth:`~DataSet.freeze` and :py:meth:`~DataSet.thaw`:

.. code-block:: python

    # Export table content to the `users.json` file.
    db.freeze(table.all(), format='json', filename='users.json')

    # Import data from a CSV file into a new table. Columns will be automatically
    # created for each field in the CSV file.
    new_table = db['stats']
    new_table.thaw(format='csv', filename='monthly_stats.csv')

Getting started
^^^^^^^^^^^^^^^

:py:class:`DataSet` objects are initialized by passing in a database URL of the format ``dialect://user:password@host/dbname``. See the :ref:`db_url` section for examples of connecting to various databases.

.. code-block:: python

    # Create an in-memory SQLite database.
    db = DataSet('sqlite:///:memory:')

Storing data
^^^^^^^^^^^^

To store data, we must first obtain a reference to a table. If the table does not exist, it will be created automatically:

.. code-block:: python

    # Get a table reference, creating the table if it does not exist.
    table = db['users']

We can now :py:meth:`~Table.insert` new rows into the table. If the columns do not exist, they will be created automatically:

.. code-block:: python

    table.insert(name='Huey', age=3, color='white')
    table.insert(name='Mickey', age=5, gender='male')

To update existing entries in the table, pass in a dictionary containing the new values and filter conditions. The list of columns to use as filters is specified in the *columns* argument. If no filter columns are specified, then all rows will be updated.

.. code-block:: python

    # Update the gender for "Huey".
    table.update(name='Huey', gender='male', columns=['name'])

    # Update all records. If the column does not exist, it will be created.
    table.update(favorite_orm='peewee')

Importing data
^^^^^^^^^^^^^^

To import data from an external source, such as a JSON or CSV file, you can use the :py:meth:`~Table.thaw` method. By default, new columns will be created for any attributes encountered. If you wish to only populate columns that are already defined on a table, you can pass in ``strict=True``.

.. code-block:: python

    # Load data from a JSON file containing a list of objects.
    table = dataset['stock_prices']
    table.thaw(filename='stocks.json', format='json')
    table.all()[:3]

    # Might print...
    [{'id': 1, 'ticker': 'GOOG', 'price': 703},
     {'id': 2, 'ticker': 'AAPL', 'price': 109},
     {'id': 3, 'ticker': 'AMZN', 'price': 300}]


Using transactions
^^^^^^^^^^^^^^^^^^

DataSet supports nesting transactions using a simple context manager.

.. code-block:: python

    table = db['users']
    with db.transaction() as txn:
        table.insert(name='Charlie')

        with db.transaction() as nested_txn:
            # Set Charlie's favorite ORM to Django.
            table.update(name='Charlie', favorite_orm='django', columns=['name'])

            # jk/lol
            nested_txn.rollback()

Inspecting the database
^^^^^^^^^^^^^^^^^^^^^^^

You can use the :py:meth:`tables` method to list the tables in the current database:

.. code-block:: pycon

    >>> print db.tables
    ['sometable', 'user']

And for a given table, you can print the columns:

.. code-block:: pycon

    >>> table = db['user']
    >>> print table.columns
    ['id', 'age', 'name', 'gender', 'favorite_orm']

We can also find out how many rows are in a table:

.. code-block:: pycon

    >>> print len(db['user'])
    3

Reading data
^^^^^^^^^^^^

To retrieve all rows, you can use the :py:meth:`~Table.all` method:

.. code-block:: python

    # Retrieve all the users.
    users = db['user'].all()

    # We can iterate over all rows without calling `.all()`
    for user in db['user']:
        print user['name']

Specific objects can be retrieved using :py:meth:`~Table.find` and :py:meth:`~Table.find_one`.

.. code-block:: python

    # Find all the users who like peewee.
    peewee_users = db['user'].find(favorite_orm='peewee')

    # Find Huey.
    huey = db['user'].find_one(name='Huey')

Exporting data
^^^^^^^^^^^^^^

To export data, use the :py:meth:`~DataSet.freeze` method, passing in the query you wish to export:

.. code-block:: python

    peewee_users = db['user'].find(favorite_orm='peewee')
    db.freeze(peewee_users, format='json', filename='peewee_users.json')

API
^^^

.. py:class:: DataSet(url)

    The *DataSet* class provides a high-level API for working with relational databases.

    :param str url: A database URL. See :ref:`db_url` for examples.

    .. py:attribute:: tables

        Return a list of tables stored in the database. This list is computed dynamically each time it is accessed.

    .. py:method:: __getitem__(table_name)

        Provide a :py:class:`Table` reference to the specified table. If the table does not exist, it will be created.

    .. py:method:: query(sql[, params=None[, commit=True]])

        :param str sql: A SQL query.
        :param list params: Optional parameters for the query.
        :param bool commit: Whether the query should be committed upon execution.
        :return: A database cursor.

        Execute the provided query against the database.

    .. py:method:: transaction()

        Create a context manager representing a new transaction (or savepoint).

    .. py:method:: freeze(query[, format='csv'[, filename=None[, file_obj=None[, **kwargs]]]])

        :param query: A :py:class:`SelectQuery`, generated using :py:meth:`~Table.all` or `~Table.find`.
        :param format: Output format. By default, *csv* and *json* are supported.
        :param filename: Filename to write output to.
        :param file_obj: File-like object to write output to.
        :param kwargs: Arbitrary parameters for export-specific functionality.

    .. py:method:: thaw(table[, format='csv'[, filename=None[, file_obj=None[, strict=False[, **kwargs]]]]])

        :param str table: The name of the table to load data into.
        :param format: Input format. By default, *csv* and *json* are supported.
        :param filename: Filename to read data from.
        :param file_obj: File-like object to read data from.
        :param bool strict: Whether to store values for columns that do not already exist on the table.
        :param kwargs: Arbitrary parameters for import-specific functionality.

    .. py:method:: connect()

        Open a connection to the underlying database. If a connection is not opened explicitly, one will be opened the first time a query is executed.

    .. py:method:: close()

        Close the connection to the underlying database.

.. py:class:: Table(dataset, name, model_class)

    The *Table* class provides a high-level API for working with rows in a given table.

    .. py:attribute:: columns

        Return a list of columns in the given table.

    .. py:attribute:: model_class

        A dynamically-created :py:class:`Model` class.

    .. py:method:: create_index(columns[, unique=False])

        Create an index on the given columns:

        .. code-block:: python

            # Create a unique index on the `username` column.
            db['users'].create_index(['username'], unique=True)

    .. py:method:: insert(**data)

        Insert the given data dictionary into the table, creating new columns as needed.

    .. py:method:: update(columns=None, conjunction=None, **data)

        Update the table using the provided data. If one or more columns are specified in the *columns* parameter, then those columns' values in the *data* dictionary will be used to determine which rows to update.

        .. code-block:: python

            # Update all rows.
            db['users'].update(favorite_orm='peewee')

            # Only update Huey's record, setting his age to 3.
            db['users'].update(name='Huey', age=3, columns=['name'])

    .. py:method:: find(**query)

        Query the table for rows matching the specified equality conditions. If no query is specified, then all rows are returned.

        .. code-block:: python

            peewee_users = db['users'].find(favorite_orm='peewee')

    .. py:method:: find_one(**query)

        Return a single row matching the specified equality conditions. If no matching row is found then ``None`` will be returned.

        .. code-block:: python

            huey = db['users'].find_one(name='Huey')

    .. py:method:: all()

        Return all rows in the given table.

    .. py:method:: delete(**query)

        Delete all rows matching the given equality conditions. If no query is provided, then all rows will be deleted.

        .. code-block:: python

            # Adios, Django!
            db['users'].delete(favorite_orm='Django')

            # Delete all the secret messages.
            db['secret_messages'].delete()

    .. py:method:: freeze([format='csv'[, filename=None[, file_obj=None[, **kwargs]]]])

        :param format: Output format. By default, *csv* and *json* are supported.
        :param filename: Filename to write output to.
        :param file_obj: File-like object to write output to.
        :param kwargs: Arbitrary parameters for export-specific functionality.

    .. py:method:: thaw([format='csv'[, filename=None[, file_obj=None[, strict=False[, **kwargs]]]]])

        :param format: Input format. By default, *csv* and *json* are supported.
        :param filename: Filename to read data from.
        :param file_obj: File-like object to read data from.
        :param bool strict: Whether to store values for columns that do not already exist on the table.
        :param kwargs: Arbitrary parameters for import-specific functionality.


.. _djpeewee:

Django Integration
------------------

The Django ORM provides a very high-level abstraction over SQL and as a consequence is in some ways
`limited in terms of flexibility or expressiveness <http://charlesleifer.com/blog/shortcomings-in-the-django-orm-and-a-look-at-peewee-a-lightweight-alternative/>`_. I
wrote a `blog post <http://charlesleifer.com/blog/the-search-for-the-missing-link-what-lies-between-sql-and-django-s-orm-/>`_
describing my search for a "missing link" between Django's ORM and the SQL it
generates, concluding that no such layer exists.  The ``djpeewee`` module attempts
to provide an easy-to-use, structured layer for generating SQL queries for use
with Django's ORM.

A couple use-cases might be:

* Joining on fields that are not related by foreign key (for example UUID fields).
* Performing aggregate queries on calculated values.
* Features that Django does not support such as ``CASE`` statements.
* Utilizing SQL functions that Django does not support, such as ``SUBSTR``.
* Replacing nearly-identical SQL queries with reusable, composable data-structures.

Below is an example of how you might use this:

.. code-block:: python

    # Django model.
    class Event(models.Model):
        start_time = models.DateTimeField()
        end_time = models.DateTimeField()
        title = models.CharField(max_length=255)

    # Suppose we want to find all events that are longer than an hour.  Django
    # does not support this, but we can use peewee.
    from playhouse.djpeewee import translate
    P = translate(Event)
    query = (P.Event
             .select()
             .where(
                 (P.Event.end_time - P.Event.start_time) > timedelta(hours=1)))

    # Now feed our peewee query into Django's `raw()` method:
    sql, params = query.sql()
    Event.objects.raw(sql, params)

Foreign keys and Many-to-many relationships
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :py:func:`translate` function will recursively traverse the graph of models
and return a dictionary populated with everything it finds.  Back-references are
not searched by default, but can be included by specifying ``backrefs=True``.

Example:

.. code-block:: pycon

    >>> from django.contrib.auth.models import User, Group
    >>> from playhouse.djpeewee import translate
    >>> translate(User, Group)
    {'ContentType': peewee.ContentType,
     'Group': peewee.Group,
     'Group_permissions': peewee.Group_permissions,
     'Permission': peewee.Permission,
     'User': peewee.User,
     'User_groups': peewee.User_groups,
     'User_user_permissions': peewee.User_user_permissions}

As you can see in the example above, although only `User` and `Group` were passed
in to :py:func:`translate`, several other models which are related by foreign key
were also created. Additionally, the many-to-many "through" tables were created
as separate models since peewee does not abstract away these types of relationships.

Using the above models it is possible to construct joins.  The following example
will get all users who belong to a group that starts with the letter "A":

.. code-block:: pycon

    >>> P = translate(User, Group)
    >>> query = P.User.select().join(P.User_groups).join(P.Group).where(
    ...     fn.Lower(fn.Substr(P.Group.name, 1, 1)) == 'a')
    >>> sql, params = query.sql()
    >>> print sql  # formatted for legibility
    SELECT t1."id", t1."password", ...
    FROM "auth_user" AS t1
    INNER JOIN "auth_user_groups" AS t2 ON (t1."id" = t2."user_id")
    INNER JOIN "auth_group" AS t3 ON (t2."group_id" = t3."id")
    WHERE (Lower(Substr(t3."name", %s, %s)) = %s)

djpeewee API
^^^^^^^^^^^^

.. py:function:: translate(*models, **options)

    Translate the given Django models into roughly equivalent peewee models
    suitable for use constructing queries. Foreign keys and many-to-many relationships
    will be followed and models generated, although back references are not traversed.

    :param models: One or more Django model classes.
    :param options: A dictionary of options, see note below.
    :returns: A dict-like object containing the generated models, but which supports
        dotted-name style lookups.

    The following are valid options:

    * ``recurse``: Follow foreign keys and many to many (default: ``True``).
    * ``max_depth``: Maximum depth to recurse (default: ``None``, unlimited).
    * ``backrefs``: Follow backrefs (default: ``False``).
    * ``exclude``: A list of models to exclude.


.. _extra-fields:

Fields
------

This module also contains several field classes that implement additional logic like encryption and compression. There is also a :py:class:`ManyToManyField` that makes it easy to work with simple many-to-many relationships.

These fields can be found in the ``playhouse.fields`` module.

.. py:class:: ManyToManyField(rel_model[, related_name=None[, through_model=None]])

    :param rel_model: :py:class:`Model` class.
    :param str related_name: Name for the automatically-created backref. If not
        provided, the pluralized version of the model will be used.
    :param through_model: :py:class:`Model` to use for the intermediary table. If
        not provided, a simple through table will be automatically created.

    The :py:class:`ManyToManyField` provides a simple interface for working with many-to-many relationships, inspired by Django. A many-to-many relationship is typically implemented by creating a junction table with foreign keys to the two models being related. For instance, if you were building a syllabus manager for college students, the relationship between students and courses would be many-to-many. Here is the schema using standard APIs:

    .. code-block:: python

        class Student(Model):
            name = CharField()

        class Course(Model):
            name = CharField()

        class StudentCourse(Model):
            student = ForeignKeyField(Student)
            course = ForeignKeyField(Course)

    To query the courses for a particular student, you would join through the junction table:

    .. code-block:: python

        # List the courses that "Huey" is enrolled in:
        courses = (Course
                   .select()
                   .join(StudentCourse)
                   .join(Student)
                   .where(Student.name == 'Huey'))
        for course in courses:
            print course.name

    The :py:class:`ManyToManyField` is designed to simplify this use-case by providing a *field-like* API for querying and modifying data in the junction table. Here is how our code looks using :py:class:`ManyToManyField`:

    .. code-block:: python

        class Student(Model):
            name = CharField()

        class Course(Model):
            name = CharField()
            students = ManyToManyField(Student, related_name='courses')

    .. note:: It does not matter from Peewee's perspective which model the :py:class:`ManyToManyField` goes on, since the back-reference is just the mirror image. In order to write valid Python, though, you will need to add the ``ManyToManyField`` on the second model so that the name of the first model is in the scope.

    We still need a junction table to store the relationships between students and courses. This model can be accessed by calling the :py:meth:`~ManyToManyField.get_through_model` method. This is useful when creating tables.

    .. code-block:: python

        # Create tables for the students, courses, and relationships between
        # the two.
        db.create_tables([
            Student,
            Course,
            Course.students.get_through_model()])

    When accessed from a model instance, the :py:class:`ManyToManyField` exposes a :py:class:`SelectQuery` representing the set of related objects. Let's use the interactive shell to see how all this works:

    .. code-block:: pycon

        >>> huey = Student.get(Student.name == 'huey')
        >>> [course.name for course in huey.courses]
        ['English 101', 'CS 101']

        >>> engl_101 = Course.get(Course.name == 'English 101')
        >>> [student.name for student in engl_101.students]
        ['Huey', 'Mickey', 'Zaizee']

    To add new relationships between objects, you can either assign the objects directly to the ``ManyToManyField`` attribute, or call the :py:meth:`~ManyToManyField.add` method. The difference between the two is that simply assigning will clear out any existing relationships, whereas ``add()`` can preserve existing relationships.

    .. code-block:: pycon

        >>> huey.courses = Course.select().where(Course.name.contains('english'))
        >>> for course in huey.courses.order_by(Course.name):
        ...     print course.name
        English 101
        English 151
        English 201
        English 221

        >>> cs_101 = Course.get(Course.name == 'CS 101')
        >>> cs_151 = Course.get(Course.name == 'CS 151')
        >>> huey.courses.add([cs_101, cs_151])
        >>> [course.name for course in huey.courses.order_by(Course.name)]
        ['CS 101', 'CS151', 'English 101', 'English 151', 'English 201',
         'English 221']

    This is quite a few courses, so let's remove the 200-level english courses. To remove objects, use the :py:meth:`~ManyToManyField.remove` method.

    .. code-block:: pycon

        >>> huey.courses.remove(Course.select().where(Course.name.contains('2'))
        2
        >>> [course.name for course in huey.courses.order_by(Course.name)]
        ['CS 101', 'CS151', 'English 101', 'English 151']

    To remove all relationships from a collection, you can use the :py:meth:`~SelectQuery.clear` method. Let's say that English 101 is canceled, so we need to remove all the students from it:

    .. code-block:: pycon

        >>> engl_101 = Course.get(Course.name == 'English 101')
        >>> engl_101.students.clear()

    .. note:: For an overview of implementing many-to-many relationships using standard Peewee APIs, check out the :ref:`manytomany` section. For all but the most simple cases, you will be better off implementing many-to-many using the standard APIs.

    .. py:method:: add(value[, clear_existing=True])

        :param value: Either a :py:class:`Model` instance, a list of model instances, or a :py:class:`SelectQuery`.
        :param bool clear_existing: Whether to remove existing relationships first.

        Associate ``value`` with the current instance. You can pass in a single model instance, a list of model instances, or even a :py:class:`SelectQuery`.

        Example code:

        .. code-block:: python

            # Huey needs to enroll in a bunch of courses, including all
            # the English classes, and a couple Comp-Sci classes.
            huey = Student.get(Student.name == 'Huey')

            # We can add all the objects represented by a query.
            english_courses = Course.select().where(
                Course.name.contains('english'))
            huey.courses.add(english_courses)

            # We can also add lists of individual objects.
            cs101 = Course.get(Course.name == 'CS 101')
            cs151 = Course.get(Course.name == 'CS 151')
            huey.courses.add([cs101, cs151])

    .. py:method:: remove(value)

        :param value: Either a :py:class:`Model` instance, a list of model instances, or a :py:class:`SelectQuery`.

        Disassociate ``value`` from the current instance. Like :py:meth:`~ManyToManyField.add`, you can pass in a model instance, a list of model instances, or even a :py:class:`SelectQuery`.

        Example code:

        .. code-block:: python

            # Huey is currently enrolled in a lot of english classes
            # as well as some Comp-Sci. He is changing majors, so we
            # will remove all his courses.
            english_courses = Course.select().where(
                Course.name.contains('english'))
            huey.courses.remove(english_courses)

            # Remove the two Comp-Sci classes Huey is enrolled in.
            cs101 = Course.get(Course.name == 'CS 101')
            cs151 = Course.get(Course.name == 'CS 151')
            huey.courses.remove([cs101, cs151])

    .. py:method:: clear()

        Remove all associated objects.

        Example code:

        .. code-block:: python

            # English 101 is canceled this semester, so remove all
            # the enrollments.
            english_101 = Course.get(Course.name == 'English 101')
            english_101.students.clear()

    .. py:method:: get_through_model()

        Return the :py:class:`Model` representing the many-to-many junction table. This can be specified manually when the field is being instantiated using the ``through_model`` parameter. If a ``through_model`` is not specified, one will automatically be created.

        When creating tables for an application that uses :py:class:`ManyToManyField`, **you must create the through table expicitly**.

        .. code-block:: python

            # Get a reference to the automatically-created through table.
            StudentCourseThrough = Course.students.get_through_model()

            # Create tables for our two models as well as the through model.
            db.create_tables([
                Student,
                Course,
                StudentCourseThrough])

.. py:class:: DeferredThroughModel()

    In some instances, you may need to obtain a reference to a through model before that model is actually defined. In order to avoid weird circular logic, you can use the ``DeferredThroughModel`` as a placeholder, then "fill it in" when you're ready.

    Example:

    .. code-block:: python

        class User(Model):
            username = CharField()

        NoteThroughDeferred = DeferredThroughModel()  # Create placeholder.

        class Note(Model):
            text = TextField()
            users = ManyToManyField(User, through_model=NoteThroughDeferred)

        class NoteThrough(Model):
            user = ForeignKeyField(User)
            note = ForeignKeyField(Note)
            sort_order = IntegerField(default=0)

        # Now that all the models are defined, we can replace the placeholder
        # with the actual through model implementation.
        NoteThroughDeferred.set_model(NoteThrough)

    .. py:method:: set_model(model_class)

        Initialize the deferred placeholder with the appropriate model class.

.. py:class:: CompressedField([compression_level=6[, algorithm='zlib'[, **kwargs]]])

    ``CompressedField`` stores compressed data using the specified algorithm. This field extends :py:class:`BlobField`, transparently storing a compressed representation of the data in the database.

    :param int compression_level: A value from 0 to 9.
    :param str algorithm: Either ``'zlib'`` or ``'bz2'``.

.. py:class:: PasswordField([iterations=12[, **kwargs]])

    ``PasswordField`` stores a password hash and lets you verify it. The password is hashed when it is saved to the database and after reading it from the database you can call ``check_password (password) -> bool`` on it.

    :param int iterations: Indicates the work factor, it does 2^n iterations.

    .. note:: This field requires `bcrypt <https://github.com/pyca/bcrypt/>`_, which can be installed by running ``pip install bcrypt``.

.. py:class:: AESEncryptedField(key[, **kwargs])

    ``AESEncryptedField`` encrypts its contents before storing them in the database.

    :param str key: Encryption key.

    .. note:: This field requires `pycrypto <https://www.dlitz.net/software/pycrypto/>`_, which can be installed by running ``pip install pycrypto``.


.. py:class:: PickledField([**kwargs])

    A field capable of storing arbitrary Python objects.

    .. note:: If the ``cPickle`` module is available, it will be used.

.. _gfk:

Generic foreign keys
--------------------

The ``gfk`` module provides a Generic ForeignKey (GFK), similar to Django.  A GFK
is composed of two columns: an object ID and an object type identifier.  The
object types are collected in a global registry (``all_models``).

How a :py:class:`GFKField` is resolved:

1. Look up the object type in the global registry (returns a model class)
2. Look up the model instance by object ID

.. note:: In order to use Generic ForeignKeys, your application's models *must*
    subclass ``playhouse.gfk.Model``.  This ensures that the model class will
    be added to the global registry.

.. note:: GFKs themselves are not actually a field and will not add a column
    to your table.

Like regular ForeignKeys, GFKs support a "back-reference" via the :py:class:`ReverseGFK`
descriptor.

How to use GFKs
^^^^^^^^^^^^^^^

1. Be sure your model subclasses ``playhouse.gfk.Model``
2. Add a :py:class:`CharField` to store the ``object_type``
3. Add a field to store the ``object_id`` (usually a :py:class:`IntegerField`)
4. Add a :py:class:`GFKField` and instantiate it with the names of the ``object_type``
   and ``object_id`` fields.
5. (optional) On any other models, add a :py:class:`ReverseGFK` descriptor

Example:

.. code-block:: python

    from playhouse.gfk import *

    class Tag(Model):
        tag = CharField()
        object_type = CharField(null=True)
        object_id = IntegerField(null=True)
        object = GFKField('object_type', 'object_id')

    class Blog(Model):
        tags = ReverseGFK(Tag, 'object_type', 'object_id')

    class Photo(Model):
        tags = ReverseGFK(Tag, 'object_type', 'object_id')

How you use these is pretty straightforward hopefully:

.. code-block:: pycon

    >>> b = Blog.create(name='awesome post')
    >>> Tag.create(tag='awesome', object=b)
    >>> b2 = Blog.create(name='whiny post')
    >>> Tag.create(tag='whiny', object=b2)

    >>> b.tags # <-- a select query
    <class '__main__.Tag'> SELECT t1."id", t1."tag", t1."object_type", t1."object_id" FROM "tag" AS t1 WHERE ((t1."object_type" = ?) AND (t1."object_id" = ?)) [u'blog', 1]

    >>> [x.tag for x in b.tags]
    [u'awesome']

    >>> [x.tag for x in b2.tags]
    [u'whiny']

    >>> p = Photo.create(name='picture of cat')
    >>> Tag.create(object=p, tag='kitties')
    >>> Tag.create(object=p, tag='cats')

    >>> [x.tag for x in p.tags]
    [u'kitties', u'cats']

    >>> [x.tag for x in Blog.tags]
    [u'awesome', u'whiny']

    >>> t = Tag.get(Tag.tag == 'awesome')
    >>> t.object
    <__main__.Blog at 0x268f450>

    >>> t.object.name
    u'awesome post'

GFK API
^^^^^^^

.. py:class:: GFKField([model_type_field='object_type'[, model_id_field='object_id']])

    Provide a clean API for storing "generic" foreign keys.  Generic foreign keys
    are comprised of an object type, which maps to a model class, and an object id,
    which maps to the primary key of the related model class.

    Setting the GFKField on a model will automatically populate the ``model_type_field``
    and ``model_id_field``.  Similarly, getting the GFKField on a model instance
    will "resolve" the two fields, first looking up the model class, then looking
    up the instance by ID.

.. py:class:: ReverseGFK(model, [model_type_field='object_type'[, model_id_field='object_id']])

    Back-reference support for :py:class:`GFKField`.

.. _hybrid:

Hybrid Attributes
-----------------

Hybrid attributes encapsulate functionality that operates at both the Python *and* SQL levels. The idea for hybrid attributes comes from a feature of the `same name in SQLAlchemy <http://docs.sqlalchemy.org/en/improve_toc/orm/extensions/hybrid.html>`_. Consider the following example:

.. code-block:: python

    class Interval(Model):
        start = IntegerField()
        end = IntegerField()

        @hybrid_property
        def length(self):
            return self.end - self.start

        @hybrid_method
        def contains(self, point):
            return (self.start <= point) & (point < self.end)

The *hybrid attribute* gets its name from the fact that the ``length`` attribute will behave differently depending on whether it is accessed via the ``Interval`` class or an ``Interval`` instance.

If accessed via an instance, then it behaves just as you would expect.

If accessed via the ``Interval.length`` class attribute, however, the length calculation will be expressed as a SQL expression. For example:

.. code-block:: python

    query = Interval.select().where(Interval.length > 5)

This query will be equivalent to the following SQL:

.. code-block:: sql

    SELECT "t1"."id", "t1"."start", "t1"."end"
    FROM "interval" AS t1
    WHERE (("t1"."end" - "t1"."start") > 5)

The ``hybrid`` module also contains a decorator for implementing hybrid methods which can accept parameters. As with hybrid properties, when accessed via a model instance, then the function executes normally as-written. When the hybrid method is called on the class, however, it will generate a SQL expression.

Example:

.. code-block:: python

    query = Interval.select().where(Interval.contains(2))

This query is equivalent to the following SQL:

.. code-block:: sql

    SELECT "t1"."id", "t1"."start", "t1"."end"
    FROM "interval" AS t1
    WHERE (("t1"."start" <= 2) AND (2 < "t1"."end"))

There is an additional API for situations where the python implementation differs slightly from the SQL implementation. Let's add a ``radius`` method to the ``Interval`` model. Because this method calculates an absolute value, we will use the Python ``abs()`` function for the instance portion and the ``fn.ABS()`` SQL function for the class portion.

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

What is neat is that both the ``radius`` implementations refer to the ``length`` hybrid attribute! When accessed via an ``Interval`` instance, the radius calculation will be executed in Python. When invoked via an ``Interval`` class, we will get the appropriate SQL.

Example:

.. code-block:: python

    query = Interval.select().where(Interval.radius < 3)

This query is equivalent to the following SQL:

.. code-block:: sql

    SELECT "t1"."id", "t1"."start", "t1"."end"
    FROM "interval" AS t1
    WHERE ((abs("t1"."end" - "t1"."start") / 2) < 3)

Pretty neat, right? Thanks for the cool idea, SQLAlchemy!

Hybrid API
^^^^^^^^^^

.. py:class:: hybrid_method(func[, expr=None])

    Method decorator that allows the definition of a Python object method with both instance-level and class-level behavior.

    Example:

    .. code-block:: python

        class Interval(Model):
            start = IntegerField()
            end = IntegerField()

            @hybrid_method
            def contains(self, point):
                return (self.start <= point) & (point < self.end)

    When called with an ``Interval`` instance, the ``contains`` method will behave as you would expect. When called as a classmethod, though, a SQL expression will be generated:

    .. code-block:: python

        query = Interval.select().where(Interval.contains(2))

    Would generate the following SQL:

    .. code-block:: sql

        SELECT "t1"."id", "t1"."start", "t1"."end"
        FROM "interval" AS t1
        WHERE (("t1"."start" <= 2) AND (2 < "t1"."end"))

    .. py:method:: expression(expr)

        Method decorator for specifying the SQL-expression producing method.

.. py:class:: hybrid_property(fget[, fset=None[, fdel=None[, expr=None]]])

    Method decorator that allows the definition of a Python object property with both instance-level and class-level behavior.

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

    When accessed on an ``Interval`` instance, the ``length`` and ``radius`` properties will behave as you would expect. When accessed as class attributes, though, a SQL expression will be generated instead:

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

.. _kv:

Key/Value Store
---------------

Provides a simple key/value store, using a dictionary API.  By default the
the :py:class:`KeyStore` will use an in-memory sqlite database, but any database
will work.

To start using the key-store, create an instance and pass it a field to use
for the values.

.. code-block:: python

    >>> kv = KeyStore(TextField())
    >>> kv['a'] = 'A'
    >>> kv['a']
    'A'

.. note::
  To store arbitrary python objects, use the :py:class:`PickledKeyStore`, which
  stores values in a pickled :py:class:`BlobField`.

  If your objects are JSON-serializable, you can also use the :py:class:`JSONKeyStore`, which stores the values as JSON-encoded strings.

Using the :py:class:`KeyStore` it is possible to use "expressions" to retrieve
values from the dictionary.  For instance, imagine you want to get all keys
which contain a certain substring:

.. code-block:: python

    >>> keys_matching_substr = kv[kv.key % '%substr%']
    >>> keys_start_with_a = kv[fn.Lower(fn.Substr(kv.key, 1, 1)) == 'a']

KeyStore API
^^^^^^^^^^^^

.. py:class:: KeyStore(value_field[, ordered=False[, database=None]])

    Lightweight dictionary interface to a model containing a key and value.
    Implements common dictionary methods, such as ``__getitem__``, ``__setitem__``,
    ``get``, ``pop``, ``items``, ``keys``, and ``values``.

    :param Field value_field: Field instance to use as value field, e.g. an
        instance of :py:class:`TextField`.
    :param boolean ordered: Whether the keys should be returned in sorted order
    :param Database database: :py:class:`Database` class to use for the storage
        backend.  If none is supplied, an in-memory Sqlite DB will be used.

    Example:

    .. code-block:: pycon

        >>> from playhouse.kv import KeyStore
        >>> kv = KeyStore(TextField())
        >>> kv['a'] = 'foo'
        >>> for k, v in kv:
        ...     print k, v
        a foo

        >>> 'a' in kv
        True
        >>> 'b' in kv
        False

.. py:class:: JSONKeyStore([ordered=False[, database=None]])

    Identical to the :py:class:`KeyStore` except the values are stored as JSON-encoded strings, so you can store complex data-types like dictionaries and lists.

    Example:

    .. code-block:: pycon

        >>> from playhouse.kv import JSONKeyStore
        >>> jkv = JSONKeyStore()
        >>> jkv['a'] = 'A'
        >>> jkv['b'] = [1, 2, 3]
        >>> list(jkv.items())
        [(u'a', 'A'), (u'b', [1, 2, 3])]

.. py:class:: PickledKeyStore([ordered=False[, database=None]])

    Identical to the :py:class:`KeyStore` except *anything* can be stored as
    a value in the dictionary.  The storage for the value will be a pickled
    :py:class:`BlobField`.

    Example:

    .. code-block:: pycon

        >>> from playhouse.kv import PickledKeyStore
        >>> pkv = PickledKeyStore()
        >>> pkv['a'] = 'A'
        >>> pkv['b'] = 1.0
        >>> list(pkv.items())
        [(u'a', 'A'), (u'b', 1.0)]

.. _shortcuts:

Shortcuts
---------

This module contains helper functions for expressing things that would otherwise be somewhat verbose or cumbersome using peewee's APIs. There are also helpers for serializing models to dictionaries and vice-versa.

.. py:function:: case(predicate, expression_tuples, default=None)

    :param predicate: A SQL expression or can be ``None``.
    :param expression_tuples: An iterable containing one or more 2-tuples
      comprised of an expression and return value.
    :param default: default if none of the cases match.

    Example SQL case statements:

    .. code-block:: sql

        -- case with predicate --
        SELECT "username",
          CASE "user_id"
            WHEN 1 THEN "one"
            WHEN 2 THEN "two"
            ELSE "?"
          END
        FROM "users";

        -- case with no predicate (inline expressions) --
        SELECT "username",
          CASE
            WHEN "user_id" = 1 THEN "one"
            WHEN "user_id" = 2 THEN "two"
            ELSE "?"
          END
        FROM "users";

    Equivalent function invocations:

    .. code-block:: python

        User.select(User.username, case(User.user_id, (
          (1, "one"),
          (2, "two")), "?"))

        User.select(User.username, case(None, (
          (User.user_id == 1, "one"),  # note the double equals
          (User.user_id == 2, "two")), "?"))

    You can specify a value for the CASE expression using the ``alias()``
    method:

    .. code-block:: python

        User.select(User.username, case(User.user_id, (
          (1, "one"),
          (2, "two")), "?").alias("id_string"))


.. py:function:: cast(node, as_type)

    :param node: A peewee :py:class:`Node`, for instance a :py:class:`Field` or an :py:class:`Expression`.
    :param str as_type: The type name to cast to, e.g. ``'int'``.
    :returns: a function call to cast the node as the given type.

    Example:

    .. code-block:: python

        # Find all data points whose numbers are palindromes. We do this by
        # casting the number to string, reversing it, then casting the reversed
        # string back to an integer.
        reverse_val = cast(fn.REVERSE(cast(DataPoint.value, 'str')), 'int')

        query = (DataPoint
                 .select()
                 .where(DataPoint.value == reverse_val))


.. py:function:: model_to_dict(model[, recurse=True[, backrefs=False[, only=None[, exclude=None[, extra_attrs=None[, fields_from_query=None]]]]]])

    Convert a model instance (and optionally any related instances) to
    a dictionary.

    :param bool recurse: Whether foreign-keys should be recursed.
    :param bool backrefs: Whether lists of related objects should be recursed.
    :param only: A list (or set) of field instances which should be included in the result dictionary.
    :param exclude: A list (or set) of field instances which should be excluded from the result dictionary.
    :param extra_attrs: A list of attribute or method names on the instance which should be included in the dictionary.
    :param SelectQuery fields_from_query: The :py:class:`SelectQuery` that created this model instance. Only the fields and values explicitly selected by the query will be serialized.

    Examples:

    .. code-block:: pycon

        >>> user = User.create(username='charlie')
        >>> model_to_dict(user)
        {'id': 1, 'username': 'charlie'}

        >>> model_to_dict(user, backrefs=True)
        {'id': 1, 'tweets': [], 'username': 'charlie'}

        >>> t1 = Tweet.create(user=user, message='tweet-1')
        >>> t2 = Tweet.create(user=user, message='tweet-2')
        >>> model_to_dict(user, backrefs=True)
        {
          'id': 1,
          'tweets': [
            {'id': 1, 'message': 'tweet-1'},
            {'id': 2, 'message': 'tweet-2'},
          ],
          'username': 'charlie'
        }

        >>> model_to_dict(t1)
        {
          'id': 1,
          'message': 'tweet-1',
          'user': {
            'id': 1,
            'username': 'charlie'
          }
        }

        >>> model_to_dict(t2, recurse=False)
        {'id': 1, 'message': 'tweet-2', 'user': 1}

.. py:function:: dict_to_model(model_class, data[, ignore_unknown=False])

    Convert a dictionary of data to a model instance, creating related
    instances where appropriate.

    :param Model model_class: The model class to construct.
    :param dict data: A dictionary of data. Foreign keys can be included as nested dictionaries, and back-references as lists of dictionaries.
    :param bool ignore_unknown: Whether to allow unrecognized (non-field) attributes.

    Examples:

    .. code-block:: pycon

        >>> user_data = {'id': 1, 'username': 'charlie'}
        >>> user = dict_to_model(User, user_data)
        >>> user
        <__main__.User at 0x7fea8fa4d490>

        >>> user.username
        'charlie'

        >>> note_data = {'id': 2, 'text': 'note text', 'user': user_data}
        >>> note = dict_to_model(Note, note_data)
        >>> note.text
        'note text'
        >>> note.user.username
        'charlie'

        >>> user_with_notes = {
        ...     'id': 1,
        ...     'username': 'charlie',
        ...     'notes': [{'id': 1, 'text': 'note-1'}, {'id': 2, 'text': 'note-2'}]}
        >>> user = dict_to_model(User, user_with_notes)
        >>> user.notes[0].text
        'note-1'
        >>> user.notes[0].user.username
        'charlie'

.. py:class:: RetryOperationalError()

    When mixed-in with a vendor-specific :py:class:`Database` subclass, this class overrides the :py:meth:`~Database.execute_sql` method to automatically reconnect and retry queries that fail due to an ``OperationalError``. The query that failed will be retried only once, and if it fails twice an exception will be raised.

    Usage:

    .. code-block:: python

        from peewee import *
        from playhouse.shortcuts import RetryOperationalError


        class MyRetryDB(RetryOperationalError, MySQLDatabase):
            pass


        db = MyRetryDB('my_app')

.. _signals:

Signal support
--------------

Models with hooks for signals (a-la django) are provided in ``playhouse.signals``. To use the signals, you will need all of your project's models to be a subclass of ``playhouse.signals.Model``, which overrides the necessary methods to provide support for the various signals.

.. highlight:: python
.. code-block:: python

    from playhouse.signals import Model, post_save


    class MyModel(Model):
        data = IntegerField()

    @post_save(sender=MyModel)
    def on_save_handler(model_class, instance, created):
        put_data_in_cache(instance.data)

.. warning::
    For what I hope are obvious reasons, Peewee signals do not work when you use the :py:meth:`Model.insert`, :py:meth:`Model.update`, or :py:meth:`Model.delete` methods. These methods generate queries that execute beyond the scope of the ORM, and the ORM does not know about which model instances might or might not be affected when the query executes.

    Signals work by hooking into the higher-level peewee APIs like :py:meth:`Model.save` and :py:meth:`Model.delete_instance`, where the affected model instance is known ahead of time.

The following signals are provided:

``pre_save``
    Called immediately before an object is saved to the database.  Provides an
    additional keyword argument ``created``, indicating whether the model is being
    saved for the first time or updated.
``post_save``
    Called immediately after an object is saved to the database.  Provides an
    additional keyword argument ``created``, indicating whether the model is being
    saved for the first time or updated.
``pre_delete``
    Called immediately before an object is deleted from the database when :py:meth:`Model.delete_instance`
    is used.
``post_delete``
    Called immediately after an object is deleted from the database when :py:meth:`Model.delete_instance`
    is used.
``pre_init``
    Called when a model class is first instantiated
``post_init``
    Called after a model class has been instantiated and the fields have been populated,
    for example when being selected as part of a database query.


Connecting handlers
^^^^^^^^^^^^^^^^^^^

Whenever a signal is dispatched, it will call any handlers that have been registered.
This allows totally separate code to respond to events like model save and delete.

The :py:class:`Signal` class provides a :py:meth:`~Signal.connect` method, which takes
a callback function and two optional parameters for "sender" and "name".  If specified,
the "sender" parameter should be a single model class and allows your callback to only
receive signals from that one model class.  The "name" parameter is used as a convenient alias
in the event you wish to unregister your signal handler.

Example usage:

.. code-block:: python

    from playhouse.signals import *

    def post_save_handler(sender, instance, created):
        print '%s was just saved' % instance

    # our handler will only be called when we save instances of SomeModel
    post_save.connect(post_save_handler, sender=SomeModel)

All signal handlers accept as their first two arguments ``sender`` and ``instance``,
where ``sender`` is the model class and ``instance`` is the actual model being acted
upon.

If you'd like, you can also use a decorator to connect signal handlers.  This is
functionally equivalent to the above example:

.. code-block:: python

    @post_save(sender=SomeModel)
    def post_save_handler(sender, instance, created):
        print '%s was just saved' % instance


Signal API
^^^^^^^^^^

.. py:class:: Signal()

    Stores a list of receivers (callbacks) and calls them when the "send" method is invoked.

    .. py:method:: connect(receiver[, sender=None[, name=None]])

        Add the receiver to the internal list of receivers, which will be called
        whenever the signal is sent.

        :param callable receiver: a callable that takes at least two parameters,
            a "sender", which is the Model subclass that triggered the signal, and
            an "instance", which is the actual model instance.
        :param Model sender: if specified, only instances of this model class will
            trigger the receiver callback.
        :param string name: a short alias

        .. code-block:: python

            from playhouse.signals import post_save
            from project.handlers import cache_buster

            post_save.connect(cache_buster, name='project.cache_buster')

    .. py:method:: disconnect([receiver=None[, name=None]])

        Disconnect the given receiver (or the receiver with the given name alias)
        so that it no longer is called.  Either the receiver or the name must be
        provided.

        :param callable receiver: the callback to disconnect
        :param string name: a short alias

        .. code-block:: python

            post_save.disconnect(name='project.cache_buster')

    .. py:method:: send(instance, *args, **kwargs)

        Iterates over the receivers and will call them in the order in which
        they were connected.  If the receiver specified a sender, it will only
        be called if the instance is an instance of the sender.

        :param instance: a model instance


    .. py:method __call__([sender=None[, name=None]])

        Function decorator that is an alias for a signal's connect method:

        .. code-block:: python

            from playhouse.signals import connect, post_save

            @post_save(name='project.cache_buster')
            def cache_bust_handler(sender, instance, *args, **kwargs):
                # bust the cache for this instance
                cache.delete(cache_key_for(instance))

.. _pwiz:

pwiz, a model generator
-----------------------

``pwiz`` is a little script that ships with peewee and is capable of introspecting
an existing database and generating model code suitable for interacting with the
underlying data.  If you have a database already, pwiz can give you a nice boost
by generating skeleton code with correct column affinities and foreign keys.

If you install peewee using ``setup.py install``, pwiz will be installed as a "script"
and you can just run:

.. highlight:: console
.. code-block:: console

    python -m pwiz -e postgresql -u postgres my_postgres_db

This will print a bunch of models to standard output.  So you can do this:

.. code-block:: console

    python -m pwiz -e postgresql my_postgres_db > mymodels.py
    python # <-- fire up an interactive shell


.. highlight:: pycon
.. code-block:: pycon

    >>> from mymodels import Blog, Entry, Tag, Whatever
    >>> print [blog.name for blog in Blog.select()]


======    ========================= ============================================
Option    Meaning                   Example
======    ========================= ============================================
-h        show help
-e        database backend          -e mysql
-H        host to connect to        -H remote.db.server
-p        port to connect on        -p 9001
-u        database user             -u postgres
-P        database password         -P secret
-s        postgres schema           -s public
======    ========================= ============================================

The following are valid parameters for the engine:

* sqlite
* mysql
* postgresql

.. _migrate:

Schema Migrations
-----------------

Peewee now supports schema migrations, with well-tested support for Postgresql,
SQLite and MySQL. Unlike other schema migration tools, peewee's migrations
do not handle introspection and database "versioning". Rather, peewee provides a number of
helper functions for generating and running schema-altering statements. This engine provides
the basis on which a more sophisticated tool could some day be built.

Migrations can be written as simple python scripts and executed from the command-line. Since
the migrations only depend on your applications :py:class:`Database` object, it should be
easy to manage changing your model definitions and maintaining a set of migration scripts without
introducing dependencies.

Example usage
^^^^^^^^^^^^^

Begin by importing the helpers from the `migrate` module:

.. code-block:: python

    from playhouse.migrate import *

Instantiate a ``migrator``. The :py:class:`SchemaMigrator` class is responsible for
generating schema altering operations, which can then be run sequentially by the
:py:func:`migrate` helper.

.. code-block:: python

    # Postgres example:
    my_db = PostgresqlDatabase(...)
    migrator = PostgresqlMigrator(my_db)

    # SQLite example:
    my_db = SqliteDatabase('my_database.db')
    migrator = SqliteMigrator(my_db)

Use :py:func:`migrate` to execute one or more operations:

.. code-block:: python

    title_field = CharField(default='')
    status_field = IntegerField(null=True)

    migrate(
        migrator.add_column('some_table', 'title', title_field),
        migrator.add_column('some_table', 'status', status_field),
        migrator.drop_column('some_table', 'old_column'),
    )

.. warning::
    Migrations are not run inside a transaction. If you wish the migration to run
    in a transaction you will need to wrap the call to `migrate` in a transaction
    block, e.g.

    .. code-block:: python

        with my_db.transaction():
            migrate(...)

Supported Operations
^^^^^^^^^^^^^^^^^^^^

Add new field(s) to an existing model:

.. code-block:: python

    # Create your field instances. For non-null fields you must specify a
    # default value.
    pubdate_field = DateTimeField(null=True)
    comment_field = TextField(default='')

    # Run the migration, specifying the database table, field name and field.
    migrate(
        migrator.add_column('comment_tbl', 'pub_date', pubdate_field),
        migrator.add_column('comment_tbl', 'comment', comment_field),
    )

Renaming a field:

.. code-block:: python

    # Specify the table, original name of the column, and its new name.
    migrate(
        migrator.rename_column('story', 'pub_date', 'publish_date'),
        migrator.rename_column('story', 'mod_date', 'modified_date'),
    )

Dropping a field:

.. code-block:: python

    migrate(
        migrator.drop_column('story', 'some_old_field'),
    )

Making a field nullable or not nullable:

.. code-block:: python

    # Note that when making a field not null that field must not have any
    # NULL values present.
    migrate(
        # Make `pub_date` allow NULL values.
        migrator.drop_not_null('story', 'pub_date'),

        # Prevent `modified_date` from containing NULL values.
        migrator.add_not_null('story', 'modified_date'),
    )

Renaming a table:

.. code-block:: python

    migrate(
        migrator.rename_table('story', 'stories_tbl'),
    )

Adding an index:

.. code-block:: python

    # Specify the table, column names, and whether the index should be
    # UNIQUE or not.
    migrate(
        # Create an index on the `pub_date` column.
        migrator.add_index('story', ('pub_date',), False),

        # Create a multi-column index on the `pub_date` and `status` fields.
        migrator.add_index('story', ('pub_date', 'status'), False),

        # Create a unique index on the category and title fields.
        migrator.add_index('story', ('category_id', 'title'), True),
    )

Dropping an index:

.. code-block:: python

    # Specify the index name.
    migrate(migrator.drop_index('story', 'story_pub_date_status'))


Migrations API
^^^^^^^^^^^^^^

.. py:function:: migrate(*operations)

    Execute one or more schema altering operations.

    Usage:

    .. code-block:: python

        migrate(
            migrator.add_column('some_table', 'new_column', CharField(default='')),
            migrator.create_index('some_table', ('new_column',)),
        )

.. py:class:: SchemaMigrator(database)

    :param database: a :py:class:`Database` instance.

    The :py:class:`SchemaMigrator` is responsible for generating schema-altering
    statements.

    .. py:method:: add_column(table, column_name, field)

        :param str table: Name of the table to add column to.
        :param str column_name: Name of the new column.
        :param Field field: A :py:class:`Field` instance.

        Add a new column to the provided table. The ``field`` provided will be used
        to generate the appropriate column definition.

        .. note:: If the field is not nullable it must specify a default value.

        .. note::
            For non-null fields, the field will initially be added as a null field,
            then an ``UPDATE`` statement will be executed to populate the column
            with the default value. Finally, the column will be marked as not null.

    .. py:method:: drop_column(table, column_name[, cascade=True])

        :param str table: Name of the table to drop column from.
        :param str column_name: Name of the column to drop.
        :param bool cascade: Whether the column should be dropped with `CASCADE`.

    .. py:method:: rename_column(table, old_name, new_name)

        :param str table: Name of the table containing column to rename.
        :param str old_name: Current name of the column.
        :param str new_name: New name for the column.

    .. py:method:: add_not_null(table, column)

        :param str table: Name of table containing column.
        :param str column: Name of the column to make not nullable.

    .. py:method:: drop_not_null(table, column)

        :param str table: Name of table containing column.
        :param str column: Name of the column to make nullable.

    .. py:method:: rename_table(old_name, new_name)

        :param str old_name: Current name of the table.
        :param str new_name: New name for the table.

    .. py:method:: add_index(table, columns[, unique=False])

        :param str table: Name of table on which to create the index.
        :param list columns: List of columns which should be indexed.
        :param bool unique: Whether the new index should specify a unique constraint.

    .. py:method:: drop_index(table, index_name)

        :param str table Name of the table containing the index to be dropped.
        :param str index_name: Name of the index to be dropped.

.. py:class:: PostgresqlMigrator(database)

    Generate migrations for Postgresql databases.

.. py:class:: SqliteMigrator(database)

    Generate migrations for SQLite databases.

.. py:class:: MySQLMigrator(database)

    Generate migrations for MySQL databases.


.. _reflection:

Reflection
----------

The reflection module contains helpers for introspecting existing databases. This module is used internally by several other modules in the playhouse, including :ref:`dataset` and :ref:`pwiz`.

.. py:class:: Introspector(metadata[, schema=None])

    Metadata can be extracted from a database by instantiating an :py:class:`Introspector`. Rather than instantiating this class directly, it is recommended to use the factory method :py:meth:`~Introspector.from_database`.

    .. py:classmethod:: from_database(database[, schema=None])

        Creates an :py:class:`Introspector` instance suitable for use with the given database.

        :param database: a :py:class:`Database` instance.
        :param str schema: an optional schema (supported by some databases).

        Usage:

        .. code-block:: python

            db = SqliteDatabase('my_app.db')
            introspector = Introspector.from_database(db)
            models = introspector.generate_models()

            # User and Tweet (assumed to exist in the database) are
            # peewee Model classes generated from the database schema.
            User = models['user']
            Tweet = models['tweet']

    .. py:method:: generate_models()

        Introspect the database, reading in the tables, columns, and foreign key constraints, then generate a dictionary mapping each database table to a dynamically-generated :py:class:`Model` class.

        :return: A dictionary mapping table-names to model classes.


.. _db_url:

Database URL
------------

This module contains a helper function to generate a database connection from a URL connection string.

.. py:function:: connect(url, **connect_params)

    Create a :py:class:`Database` instance from the given connection URL.

    Examples:

    * *sqlite:///my_database.db* will create a :py:class:`SqliteDatabase` instance for the file ``my_database.db`` in the current directory.
    * *sqlite:///:memory:* will create an in-memory :py:class:`SqliteDatabase` instance.
    * *postgresql://postgres:my_password@localhost:5432/my_database* will create a :py:class:`PostgresqlDatabase` instance. A username and password are provided, as well as the host and port to connect to.
    * *mysql://user:passwd@ip:port/my_db* will create a :py:class:`MySQLDatabase` instance for the local MySQL database *my_db*.
    * *mysql+pool://user:passwd@ip:port/my_db?max_connections=20&stale_timeout=300* will create a :py:class:`PooledMySQLDatabase` instance for the local MySQL database *my_db* with max_connections set to 20 and a stale_timeout setting of 300 seconds.

    Supported schemes:

    * ``apsw``: :py:class:`APSWDatabase`
    * ``mysql``: :py:class:`MySQLDatabase`
    * ``mysql+pool``: :py:class:`PooledMySQLDatabase`
    * ``postgres``: :py:class:`PostgresqlDatabase`
    * ``postgres+pool``: :py:class:`PooledPostgresqlDatabase`
    * ``postgresext``: :py:class:`PostgresqlExtDatabase`
    * ``postgresext+pool``: :py:class:`PooledPostgresqlExtDatabase`
    * ``sqlite``: :py:class:`SqliteDatabase`
    * ``sqliteext``: :py:class:`SqliteExtDatabase`
    * ``sqlite+pool``: :py:class:`PooledSqliteDatabase`
    * ``sqliteext+pool``: :py:class:`PooledSqliteExtDatabase`

    Usage:

    .. code-block:: python

        import os
        from playhouse.db_url import connect

        # Connect to the database URL defined in the environment, falling
        # back to a local Sqlite database if no database URL is specified.
        db = connect(os.environ.get('DATABASE') or 'sqlite:///default.db')

.. py:function:: parse(url)

    Parse the information in the given URL into a dictionary containing ``database``, ``host``, ``port``, ``user`` and/or ``password``. Additional connection arguments can be passed in the URL query string.

    If you are using a custom database class, you can use the ``parse()`` function to extract information from a URL which can then be passed in to your database object.

.. py:function:: register_database(db_class, *names)

    :param db_class: A subclass of :py:class:`Database`.
    :param names: A list of names to use as the scheme in the URL, e.g. 'sqlite' or 'firebird'

    Register additional database class under the specified names. This function can be used to extend the ``connect()`` function to support additional schemes. Suppose you have a custom database class for ``Firebird`` named ``FirebirdDatabase``.

    .. code-block:: python

        from playhouse.db_url import connect, register_database

        register_database(FirebirdDatabase, 'firebird')
        db = connect('firebird://my-firebird-db')

.. _csv_utils:

CSV Utils
---------

This module contains helpers for dumping queries into CSV, and for loading CSV data into a database.  CSV files can be introspected to generate an appropriate model class for working with the data. This makes it really easy to explore the data in a CSV file using Peewee and SQL.

Here is how you would load a CSV file into an in-memory SQLite database.  The call to :py:func:`load_csv` returns a :py:class:`Model` instance suitable for working with the CSV data:

.. code-block:: python

    from peewee import *
    from playhouse.csv_loader import load_csv
    db = SqliteDatabase(':memory:')
    ZipToTZ = load_csv(db, 'zip_to_tz.csv')

Now we can run queries using the new model.

.. code-block:: pycon

    # Get the timezone for a zipcode.
    >>> ZipToTZ.get(ZipToTZ.zip == 66047).timezone
    'US/Central'

    # Get all the zipcodes for my town.
    >>> [row.zip for row in ZipToTZ.select().where(
    ...     (ZipToTZ.city == 'Lawrence') && (ZipToTZ.state == 'KS'))]
    [66044, 66045, 66046, 66047, 66049]

For more information and examples check out this `blog post <http://charlesleifer.com/blog/using-peewee-to-explore-csv-files/>`_.

CSV Loader API
^^^^^^^^^^^^^^

.. py:function:: load_csv(db_or_model, filename[, fields=None[, field_names=None[, has_header=True[, sample_size=10[, converter=None[, db_table=None[, **reader_kwargs]]]]]]])

    Load a CSV file into the provided database or model class, returning a
    :py:class:`Model` suitable for working with the CSV data.

    :param db_or_model: Either a :py:class:`Database` instance or a :py:class:`Model` class.  If a model is not provided, one will be automatically generated for you.
    :param str filename: Path of CSV file to load.
    :param list fields: A list of :py:class:`Field` instances mapping to each column in the CSV.  This allows you to manually specify the column types.  If not provided, and a model is not provided, the field types will be determined automatically.
    :param list field_names: A list of strings to use as field names for each column in the CSV.  If not provided, and a model is not provided, the field names will be determined by looking at the header row of the file.  If no header exists, then the fields will be given generic names.
    :param bool has_header: Whether the first row is a header.
    :param int sample_size: Number of rows to look at when introspecting data types.  If set to ``0``, then a generic field type will be used for all fields.
    :param RowConverter converter: a :py:class:`RowConverter` instance to use for introspecting the CSV.  If not provided, one will be created.
    :param str db_table: The name of the database table to load data into.  If this value is not provided, it will be determined using the filename of the CSV file.  If a model is provided, this value is ignored.
    :param reader_kwargs: Arbitrary keyword arguments to pass to the ``csv.reader`` object, such as the dialect, separator, etc.
    :rtype: A :py:class:`Model` suitable for querying the CSV data.

    Basic example -- field names and types will be introspected:

    .. code-block:: python

        from peewee import *
        from playhouse.csv_loader import *
        db = SqliteDatabase(':memory:')
        User = load_csv(db, 'users.csv')

    Using a pre-defined model:

    .. code-block:: python

        class ZipToTZ(Model):
            zip = IntegerField()
            timezone = CharField()

        load_csv(ZipToTZ, 'zip_to_tz.csv')

    Specifying fields:

    .. code-block:: python

        fields = [DecimalField(), IntegerField(), IntegerField(), DateField()]
        field_names = ['amount', 'from_acct', 'to_acct', 'timestamp']
        Payments = load_csv(db, 'payments.csv', fields=fields, field_names=field_names, has_header=False)

Dumping CSV
^^^^^^^^^^^

.. py:function:: dump_csv(query, file_or_name[, include_header=True[, close_file=True[, append=True[, csv_writer=None]]]])

    :param query: A peewee :py:class:`SelectQuery` to dump as CSV.
    :param file_or_name: Either a filename or a file-like object.
    :param include_header: Whether to generate a CSV header row consisting of the names of the selected columns.
    :param close_file: Whether the file should be closed after writing the query data.
    :param append: Whether new data should be appended to the end of the file.
    :param csv_writer: A python ``csv.writer`` instance to use.

    Example usage:

    .. code-block:: python

        with open('account-export.csv', 'w') as fh:
            query = Account.select().order_by(Account.id)
            dump_csv(query, fh)


.. _pool:

Connection pool
---------------

The ``pool`` module contains a number of :py:class:`Database` classes that provide connection pooling for PostgreSQL and MySQL databases. The pool works by overriding the methods on the :py:class:`Database` class that open and close connections to the backend. The pool can specify a timeout after which connections are recycled, as well as an upper bound on the number of open connections.

In a multi-threaded application, up to `max_connections` will be opened. Each thread (or, if using gevent, greenlet) will have it's own connection.

In a single-threaded application, only one connection will be created. It will be continually recycled until either it exceeds the stale timeout or is closed explicitly (using `.manual_close()`).

**By default, all your application needs to do is ensure that connections are closed when you are finished with them, and they will be returned to the pool**. For web applications, this typically means that at the beginning of a request, you will open a connection, and when you return a response, you will close the connection.

Simple Postgres pool example code:

.. code-block:: python

    # Use the special postgresql extensions.
    from playhouse.pool import PooledPostgresqlExtDatabase

    db = PooledPostgresqlExtDatabase(
        'my_app',
        max_connections=32,
        stale_timeout=300,  # 5 minutes.
        user='postgres')

    class BaseModel(Model):
        class Meta:
            database = db

That's it! If you would like finer-grained control over the pool of connections, check out the :ref:`advanced_connection_management` section.

Pool APIs
^^^^^^^^^

.. py:class:: PooledDatabase(database[, max_connections=20[, stale_timeout=None[, **kwargs]]])

    Mixin class intended to be used with a subclass of :py:class:`Database`.

    :param str database: The name of the database or database file.
    :param int max_connections: Maximum number of connections. Provide ``None`` for unlimited.
    :param int stale_timeout: Number of seconds to allow connections to be used.
    :param kwargs: Arbitrary keyword arguments passed to database class.

    .. note:: Connections will not be closed exactly when they exceed their `stale_timeout`. Instead, stale connections are only closed when a new connection is requested.

    .. note:: If the number of open connections exceeds `max_connections`, a `ValueError` will be raised.

    .. py:method:: _connect(*args, **kwargs)

        Request a connection from the pool. If there are no available connections a new one will be opened.

    .. py:method:: _close(conn[, close_conn=False])

        By default `conn` will not be closed and instead will be returned to the pool of available connections. If `close_conn=True`, then `conn` will be closed and *not* be returned to the pool.

    .. py:method:: manual_close()

        Close the currently-open connection without returning it to the pool.

.. py:class:: PooledPostgresqlDatabase

    Subclass of :py:class:`PostgresqlDatabase` that mixes in the :py:class:`PooledDatabase` helper.

.. py:class:: PooledPostgresqlExtDatabase

    Subclass of :py:class:`PostgresqlExtDatabase` that mixes in the :py:class:`PooledDatabase` helper. The :py:class:`PostgresqlExtDatabase` is a part of the
    :ref:`postgres_ext` module and provides support for many Postgres-specific
    features.

.. py:class:: PooledMySQLDatabase

    Subclass of :py:class:`MySQLDatabase` that mixes in the :py:class:`PooledDatabase` helper.

.. py:class:: PooledSqliteDatabase

    Persistent connections for SQLite apps.

.. py:class:: PooledSqliteExtDatabase

    Persistent connections for SQLite apps, using the :ref:`sqlite_ext` advanced database driver :py:class:`SqliteExtDatabase`.


.. _read_slaves:

Read Slaves
-----------

The ``read_slave`` module contains a :py:class:`Model` subclass that can be used
to automatically execute ``SELECT`` queries against different database(s). This
might be useful if you have your databases in a master / slave configuration.

.. py:class:: ReadSlaveModel

    Model subclass that will route ``SELECT`` queries to a different database.

    Master and read-slaves are specified using ``Model.Meta``:

    .. code-block:: python

        # Declare a master and two read-replicas.
        master = PostgresqlDatabase('master')
        replica_1 = PostgresqlDatabase('replica_1')
        replica_2 = PostgresqlDatabase('replica_2')

        # Declare a BaseModel, the normal best-practice.
        class BaseModel(ReadSlaveModel):
            class Meta:
                database = master
                read_slaves = (replica_1, replica_2)

        # Declare your models.
        class User(BaseModel):
            username = CharField()

    When you execute writes (or deletes), they will be executed against the
    master database:

    .. code-block:: python

        User.create(username='Peewee')  # Executed against master.

    When you execute a read query, it will run against one of the replicas:

    .. code-block:: python

        users = User.select().where(User.username == 'Peewee')

    .. note::
        To force a ``SELECT`` query against the master database, manually create
        the :py:class:`SelectQuery`.

        .. code-block:: python

            SelectQuery(User)  # master database.

    .. note::
        Queries will be dispatched among the ``read_slaves`` in round-robin fashion.

.. _test_utils:

Test Utils
----------

Contains utilities helpful when testing peewee projects.

.. py:class:: test_database(db, models[, create_tables=True[, fail_silently=False]])

    Context manager that lets you use a different database with a set of
    models.  Models can also be automatically created and dropped.

    This context manager helps make it possible to test your peewee models
    using a "test-only" database.

    :param Database db: Database to use with the given models
    :param models: a ``list`` or ``tuple`` of :py:class:`Model` classes to use with the ``db``
    :param boolean create_tables: Whether tables should be automatically created
        and dropped.
    :param boolean fail_silently: Whether the table create / drop should fail
        silently.

    Example:

    .. code-block:: python

        from unittest import TestCase
        from playhouse.test_utils import test_database
        from peewee import *

        from my_app.models import User, Tweet

        test_db = SqliteDatabase(':memory:')

        class TestUsersTweets(TestCase):
            def create_test_data(self):
                # ... create a bunch of users and tweets
                for i in range(10):
                    User.create(username='user-%d' % i)

            def test_timeline(self):
                with test_database(test_db, (User, Tweet)):
                    # This data will be created in `test_db`
                    self.create_test_data()

                    # Perform assertions on test data inside ctx manager.
                    self.assertEqual(Tweet.timeline('user-0') [...])

                with test_database(test_db, (User,)):
                    # Test something that just affects user.
                    self.test_some_user_thing()

                # once we exit the context manager, we're back to using the normal database


.. py:class:: count_queries([only_select=False])

    Context manager that will count the number of queries executed within
    the context.

    :param bool only_select: Only count *SELECT* queries.

    .. code-block:: python

        with count_queries() as counter:
            huey = User.get(User.username == 'huey')
            huey_tweets = [tweet.message for tweet in huey.tweets]

        assert counter.count == 2

    .. py:attribute:: count

        The number of queries executed.

    .. py:method:: get_queries()

        Return a list of 2-tuples consisting of the SQL query and a list of
        parameters.


.. py:function:: assert_query_count(expected[, only_select=False])

    Function or method decorator that will raise an ``AssertionError`` if the
    number of queries executed in the decorated function does not equal the
    expected number.

    .. code-block:: python

        class TestMyApp(unittest.TestCase):
            @assert_query_count(1)
            def test_get_popular_blogs(self):
                popular_blogs = Blog.get_popular()
                self.assertEqual(
                    [blog.title for blog in popular_blogs],
                    ["Peewee's Playhouse!", "All About Huey", "Mickey's Adventures"])

    This function can also be used as a context manager:

    .. code-block:: python

        class TestMyApp(unittest.TestCase):
            def test_expensive_operation(self):
                with assert_query_count(1):
                    perform_expensive_operation()

.. _pskel:

pskel
-----

I often find myself writing very small scripts with peewee. *pskel* will generate the boilerplate code for a basic peewee script.

Usage::

    pskel [options] model1 model2 ...

*pskel* accepts the following options:

=================  =============  =======================================
Option             Default        Description
=================  =============  =======================================
``-l,--logging``   False          Log all queries to stdout.
``-e,--engine``    sqlite         Database driver to use.
``-d,--database``  ``:memory:``   Database to connect to.
=================  =============  =======================================

Example::

    $ pskel -e postgres -d my_database User Tweet

This will print the following code to *stdout* (which you can redirect into a file using ``>``):

.. code-block:: python

    #!/usr/bin/env python

    import logging

    from peewee import *
    from peewee import create_model_tables

    db = PostgresqlDatabase('my_database')

    class BaseModel(Model):
        class Meta:
            database = db

    class User(BaseModel):
        pass

    class Tweet(BaseModel):
        pass

    def main():
        create_model_tables([User, Tweet], fail_silently=True)

    if __name__ == '__main__':
        main()


.. _flask_utils:

Flask Utils
-----------

The ``playhouse.flask_utils`` module contains several helpers for integrating peewee with the `Flask <http://flask.pocoo.org/>`_ web framework.

Database wrapper
^^^^^^^^^^^^^^^^

The :py:class:`FlaskDB` class provides a convenient way to configure a peewee :py:class:`Database` instance using Flask app configuration. The :py:class:`FlaskDB` wrapper will also automatically set up request setup and teardown handlers to ensure your connections are managed correctly.

Basic usage:

.. code-block:: python

    import datetime
    from flask import Flask
    from peewee import *
    from playhouse.flask_utils import FlaskDB

    DATABASE = 'postgresql://postgres:password@localhost:5432/my_database'

    app = Flask(__name__)
    app.config.from_object(__name__)

    database = FlaskDB(app)

    class User(database.Model):
        username = CharField(unique=True)

    class Tweet(database.Model):
        user = ForeignKeyField(User, related_name='tweets')
        content = TextField()
        timestamp = DateTimeField(default=datetime.datetime.now)

The above code example will create and instantiate a peewee :py:class:`PostgresqlDatabase` specified by the given database URL. Request hooks will be configured to establish a connection when a request is received, and automatically close the connection when the response is sent. Lastly, the :py:class:`FlaskDB` class exposes a :py:attr:`FlaskDB.Model` property which can be used as a base for your application's models.

.. note:: The underlying peewee database can be accessed using the ``FlaskDB.database`` attribute.

If you prefer, you can also pass the database value directly into the ``FlaskDB`` object:

.. code-block:: python

    app = Flask(__name__)
    database = FlaskDB(app, 'sqlite:///my_app.db')

While the above examples show using a database URL, for more advanced usages you can specify a dictionary of configuration options or simply pass in a peewee :py:class:`Database` instance:

.. code-block:: python

    DATABASE = {
        'name': 'my_app_db',
        'engine': 'playhouse.pool.PooledPostgresqlDatabase',
        'user': 'postgres',
        'max_connections': 32,
        'stale_timeout': 600,
    }

    app = Flask(__name__)
    app.config.from_object(__name__)

    database = FlaskDB(app)

Using a peewee :py:class:`Database` object:

.. code-block:: python

    peewee_db = PostgresqlExtDatabase('my_app')
    app = Flask(__name__)
    flask_db = FlaskDB(app, peewee_db)

Database with Application Factory
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you prefer to use the `application factory pattern <http://flask.pocoo.org/docs/0.10/patterns/appfactories/>`_, the :py:class:`FlaskDB` class implements an ``init_app()`` method.

Using as a factory:

.. code-block:: python

    database = FlaskDB()

    # Even though the database is not yet initialized, you can still use the
    # `Model` property to create model classes.
    class User(database.Model):
        username = CharField(unique=True)


    def create_app():
        app = Flask(__name__)
        app.config['DATABASE'] = 'sqlite:////home/code/apps/my-database.db'
        database.init_app(app)
        return app

Query utilities
^^^^^^^^^^^^^^^

The ``flask_utils`` module provides several helpers for managing queries in your web app. Some common patterns include:

.. py:function:: get_object_or_404(query_or_model, *query)

    Retrieve the object matching the given query, or return a 404 not found response. A common use-case might be a detail page for a weblog. You want to either retrieve the post matching the given URL, or return a 404.

    :param query_or_model: Either a :py:class:`Model` class or a pre-filtered :py:class:`SelectQuery`.
    :param query: An arbitrarily complex peewee expression.

    Example:

    .. code-block:: python

        @app.route('/blog/<slug>/')
        def post_detail(slug):
            public_posts = Post.select().where(Post.published == True)
            post = get_object_or_404(public_posts, (Post.slug == slug))
            return render_template('post_detail.html', post=post)

.. py:function:: object_list(template_name, query[, context_variable='object_list'[, paginate_by=20[, page_var='page'[, check_bounds=True[, **kwargs]]]]])

    Retrieve a paginated list of objects specified by the given query. The paginated object list will be dropped into the context using the given ``context_variable``, as well as metadata about the current page and total number of pages, and finally any arbitrary context data passed as keyword-arguments.

    The page is specified using the ``page`` ``GET`` argument, e.g. ``/my-object-list/?page=3`` would return the third page of objects.

    :param template_name: The name of the template to render.
    :param query: A :py:class:`SelectQuery` instance to paginate.
    :param context_variable: The context variable name to use for the paginated object list.
    :param paginate_by: Number of objects per-page.
    :param page_var: The name of the ``GET`` argument which contains the page.
    :param check_bounds: Whether to check that the given page is a valid page. If ``check_bounds`` is ``True`` and an invalid page is specified, then a 404 will be returned.
    :param kwargs: Arbitrary key/value pairs to pass into the template context.

    Example:

    .. code-block:: python

        @app.route('/blog/')
        def post_index():
            public_posts = (Post
                            .select()
                            .where(Post.published == True)
                            .order_by(Post.timestamp.desc()))

            return object_list(
                'post_index.html',
                query=public_posts,
                context_variable='post_list',
                paginate_by=10)

    The template will have the following context:

    * ``post_list``, which contains a list of up to 10 posts.
    * ``page``, which contains the current page based on the value of the ``page`` ``GET`` parameter.
    * ``pagination``, a :py:class:`PaginatedQuery` instance.

.. py:class:: PaginatedQuery(query_or_model, paginate_by[, page_var='page'[, check_bounds=False]])

    Helper class to perform pagination based on ``GET`` arguments.

    :param query_or_model: Either a :py:class:`Model` or a :py:class:`SelectQuery` instance containing the collection of records you wish to paginate.
    :param paginate_by: Number of objects per-page.
    :param page_var: The name of the ``GET`` argument which contains the page.
    :param check_bounds: Whether to check that the given page is a valid page. If ``check_bounds`` is ``True`` and an invalid page is specified, then a 404 will be returned.

    .. py:method:: get_page()

        Return the currently selected page, as indicated by the value of the ``page_var`` ``GET`` parameter. If no page is explicitly selected, then this method will return 1, indicating the first page.

    .. py:method:: get_page_count()

        Return the total number of possible pages.

    .. py:method:: get_object_list()

        Using the value of :py:meth:`~PaginatedQuery.get_page`, return the page of objects requested by the user. The return value is a :py:class:`SelectQuery` with the appropriate ``LIMIT`` and ``OFFSET`` clauses.

        If ``check_bounds`` was set to ``True`` and the requested page contains no objects, then a 404 will be raised.
