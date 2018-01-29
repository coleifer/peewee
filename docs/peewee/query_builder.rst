.. _query-builder:

Query Builder
=============

Peewee's high-level :py:class:`Model` and :py:class:`Field` APIs are built upon
lower-level :py:class:`Table` and :py:class:`Column` counterparts. While these
lower-level APIs are not documented in as much detail as their high-level
counterparts, this document will present an overview with examples that should
hopefully allow you to experiment.

We'll use the following schema:

.. code-block:: sql

    CREATE TABLE "entry" (
      "id" INTEGER NOT NULL PRIMARY KEY,
      "title" TEXT NOT NULL,
      "body" TEXT NOT NULL,
      "timestamp" DATETIME NOT NULL);

    CREATE TABLE "entrytag" (
      "entry_id" INTEGER NOT NULL,
      "tag" TEXT NOT NULL,
      PRIMARY KEY ("entry_id", "tag"),
      FOREIGN KEY ("entry_id") REFERENCES "entry" ("id"))

There are two ways we can declare :py:class:`Table` objects for working with
these tables:

.. code-block:: python

    # Explicitly declare columns
    Entry = Table('entry', ('id', 'title', 'body', 'timestamp'))

    # Do not declare columns, they will be accessed using magic ".c" attribute
    EntryTag = Table('entrytag')

Typically we will want to :py:meth:`~Table.bind` our tables to a database. This
saves us having to pass the database explicitly every time we wish to execute a
query on the table:

.. code-block:: python

    db = SqliteDatabase('my_app.db')
    Entry = Entry.bind(db)
    EntryTag = EntryTag.bind(db)

To select the first three entries and print their titles, we can write:

.. code-block:: python

    query = Entry.select().limit(3)
    for entry_dict in query:
        print(entry_dict['title'])

.. note::
    By default, rows will be returned as dictionaries. You can use the
    :py:meth:`~BaseQuery.tuples`, :py:meth:`~BaseQuery.namedtuples` or
    :py:meth:`~BaseQuery.objects` methods to specify a different container for
    the row data, if you wish.

Because we didn't specify any columns, all the columns we defined in the
entry's :py:class:`Table` constructor will be selected. This won't work for
EntryTag, as we didn't specify any columns at all. Here's how we might select
the most popular 5 tags:

.. code-block:: python

    query = (EntryTag
             .select(EntryTag.c.tag, fn.COUNT(EntryTag.c.entry_id))
             .group_by(EntryTag.c.tag)
             .order_by(fn.COUNT(EntryTag.c.entry_id).desc())
             .limit(5))
    for tag, count in query.tuples():
        print(tag, count)

To restrict the most popular tags to those added to entries published in the
last year, we will need to add a join and a where clause:

.. code-block:: python

    query = (EntryTag
             .select(EntryTag.c.tag, fn.COUNT(EntryTag.c.entry_id))
             .join(Entry, on=(EntryTag.c.entry_id == Entry.id))
             .where(Entry.timestamp >= datetime.datetime(2017, 1, 1))
             .group_by(EntryTag.c.tag)
             .order_by(fn.COUNT(EntryTag.c.entry_id).desc())
             .limit(5))
    for tag, count in query.tuples():
        print(tag, count)

.. note::
    When referring to columns on the Entry table, we do not use the magic ".c"
    lookup. This is because the Entry table's columns were defined and are now
    set as attributes on the Table object.
