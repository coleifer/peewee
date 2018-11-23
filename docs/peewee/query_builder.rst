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

    CREATE TABLE "person" (
        "id" INTEGER NOT NULL PRIMARY KEY,
        "first" TEXT NOT NULL,
        "last" TEXT NOT NULL);

    CREATE TABLE "note" (
        "id" INTEGER NOT NULL PRIMARY KEY,
        "person_id" INTEGER NOT NULL,
        "content" TEXT NOT NULL,
        "timestamp" DATETIME NOT NULL,
        FOREIGN KEY ("person_id") REFERENCES "person" ("id"));

    CREATE TABLE "reminder" (
        "id" INTEGER NOT NULL PRIMARY KEY,
        "note_id" INTEGER NOT NULL,
        "alarm" DATETIME NOT NULL,
        FOREIGN KEY ("note_id") REFERENCES "note" ("id"));

Declaring tables
----------------

There are two ways we can declare :py:class:`Table` objects for working with
these tables:

.. code-block:: python

    # Explicitly declare columns
    Person = Table('person', ('id', 'first', 'last'))

    Note = Table('note', ('id', 'person_id', 'content', 'timestamp'))

    # Do not declare columns, they will be accessed using magic ".c" attribute
    Reminder = Table('reminder')

Typically we will want to :py:meth:`~Table.bind` our tables to a database. This
saves us having to pass the database explicitly every time we wish to execute a
query on the table:

.. code-block:: python

    db = SqliteDatabase('my_app.db')
    Person = Person.bind(db)
    Note = Note.bind(db)
    Reminder = Reminder.bind(db)

Select queries
--------------

To select the first three notes and print their content, we can write:

.. code-block:: python

    query = Note.select().order_by(Note.timestamp).limit(3)
    for note_dict in query:
        print(note_dict['content'])

.. note::
    By default, rows will be returned as dictionaries. You can use the
    :py:meth:`~BaseQuery.tuples`, :py:meth:`~BaseQuery.namedtuples` or
    :py:meth:`~BaseQuery.objects` methods to specify a different container for
    the row data, if you wish.

Because we didn't specify any columns, all the columns we defined in the
note's :py:class:`Table` constructor will be selected. This won't work for
Reminder, as we didn't specify any columns at all.

To select all notes published in 2018 along with the name of the creator, we
will use :py:meth:`~BaseQuery.join`. We'll also request that rows be returned
as *namedtuple* objects:

.. code-block:: python

    query = (Note
             .select(Note.content, Note.timestamp, Person.first, Person.last)
             .join(Person, on=(Note.person_id == Person.id))
             .where(Note.timestamp >= datetime.date(2018, 1, 1))
             .order_by(Note.timestamp)
             .namedtuples())

    for row in query:
        print(row.timestamp, '-', row.content, '-', row.first, row.last)

Let's query for the most prolific people, that is, get the people who have
created the most notes. This introduces calling a SQL function (COUNT), which
is accomplished using the ``fn`` object:

.. code-block:: python

    name = Person.first.concat(' ').concat(Person.last)
    query = (Person
             .select(name.alias('name'), fn.COUNT(Note.id).alias('count'))
             .join(Note, JOIN.LEFT_OUTER, on=(Note.person_id == Person.id))
             .group_by(name)
             .order_by(fn.COUNT(Note.id).desc()))
    for row in query:
        print(row['name'], row['count'])

There are a couple things to note in the above query:

* We store an expression in a variable (``name``), then use it in the query.
* We call SQL functions using ``fn.<function>(...)`` passing arguments as if
  it were a normal Python function.
* The :py:meth:`~ColumnBase.alias` method is used to specify the name used for
  a column or calculation.

As a more complex example, we'll generate a list of all people and the contents
and timestamp of their most recently-published note. To do this, we will end up
using the Note table twice in different contexts within the same query, which
will require us to use a table alias.

.. code-block:: python

    # Start with the query that calculates the timestamp of the most recent
    # note for each person.
    NA = Note.alias('na')
    max_note = (NA
                .select(NA.person_id, fn.MAX(NA.timestamp).alias('max_ts'))
                .group_by(NA.person_id)
                .alias('max_note'))

    # Now we'll select from the note table, joining on both the subquery and
    # on the person table to construct the result set.
    query = (Note
             .select(Note.content, Note.timestamp, Person.first, Person.last)
             .join(max_note, on=((max_note.c.person_id == Note.person_id) &
                                 (max_note.c.max_ts == Note.timestamp)))
             .join(Person, on=(Note.person_id == Person.id))
             .order_by(Person.first, Person.last))

    for row in query.namedtuples():
        print(row.first, row.last, ':', row.timestamp, '-', row.content)

In the join predicate for the join on the *max_note* subquery, we can reference
columns in the subquery using the magical ".c" attribute. So,
*max_note.c.max_ts* is translated into "the max_ts column value from the
max_note subquery".

We can also use the ".c" magic attribute to access columns on tables that do
not explicitly define their columns, like we did with the Reminder table.
Here's a simple query to get all reminders for today, along with their
associated note content:

.. code-block:: python

    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)

    query = (Reminder
             .select(Reminder.c.alarm, Note.content)
             .join(Note, on=(Reminder.c.note_id == Note.id))
             .where(Reminder.c.alarm.between(today, tomorrow))
             .order_by(Reminder.c.alarm))
    for row in query:
        print(row['alarm'], row['content'])

.. note::
    The ".c" attribute will not work on tables that explicitly define their
    columns, to prevent confusion.

Insert queries
--------------

Inserting data is straightforward. We can specify data to
:py:meth:`~Table.insert` in two different ways (in both cases, the ID of the
new row is returned):

.. code-block:: python

    # Using keyword arguments:
    zaizee_id = Person.insert(first='zaizee', last='cat').execute()

    # Using column: value mappings:
    Note.insert({
        Note.person_id: zaizee_id,
        Note.content: 'meeeeowwww',
        Note.timestamp: datetime.datetime.now()}).execute()

It is easy to bulk-insert data, just pass in either:

* A list of dictionaries (all must have the same keys/columns).
* A list of tuples, if the columns are specified explicitly.

Examples:

.. code-block:: python

    people = [
        {'first': 'Bob', 'last': 'Foo'},
        {'first': 'Herb', 'last': 'Bar'},
        {'first': 'Nuggie', 'last': 'Bar'}]

    # Inserting multiple rows returns the ID of the last-inserted row.
    last_id = Person.insert(people).execute()

    # We can also specify row tuples, so long as we tell Peewee which
    # columns the tuple values correspond to:
    people = [
        ('Bob', 'Foo'),
        ('Herb', 'Bar'),
        ('Nuggie', 'Bar')]
    Person.insert(people, columns=[Person.first, Person.last]).execute()

Update queries
--------------

:py:meth:`~Table.update` queries accept either keyword arguments or a
dictionary mapping column to value, just like :py:meth:`~Table.insert`.

Examples:

.. code-block:: python

    # "Bob" changed his last name from "Foo" to "Baze".
    nrows = (Person
             .update(last='Baze')
             .where((Person.first == 'Bob') &
                    (Person.last == 'Foo'))
             .execute())

    # Use dictionary mapping column to value.
    nrows = (Person
             .update({Person.last: 'Baze'})
             .where((Person.first == 'Bob') &
                    (Person.last == 'Foo'))
             .execute())

You can also use expressions as the value to perform an atomic update. Imagine
we have a *PageView* table and we need to atomically increment the page-view
count for some URL:

.. code-block:: python

    # Do an atomic update:
    (PageView
     .update({PageView.count: PageView.count + 1})
     .where(PageView.url == some_url)
     .execute())

Delete queries
--------------

:py:meth:`~Table.delete` queries are simplest of all, as they do not accept any
arguments:

.. code-block:: python

    # Delete all notes created before 2018, returning number deleted.
    n = Note.delete().where(Note.timestamp < datetime.date(2018, 1, 1)).execute()

Because DELETE (and UPDATE) queries do not support joins, we can use subqueries
to delete rows based on values in related tables. For example, here is how you
would delete all notes by anyone whose last name is "Foo":

.. code-block:: python

    # Get the id of all people whose last name is "Foo".
    foo_people = Person.select(Person.id).where(Person.last == 'Foo')

    # Delete all notes by any person whose ID is in the previous query.
    Note.delete().where(Note.person_id.in_(foo_people)).execute()

Query Objects
-------------

One of the fundamental limitations of the abstractions provided by Peewee 2.x
was the absence of a class that represented a structured query with no relation
to a given model class.

An example of this might be computing aggregate values over a subquery. For
example, the :py:meth:`~SelectBase.count` method, which returns the count of
rows in an arbitrary query, is implemented by wrapping the query:

.. code-block:: sql

    SELECT COUNT(1) FROM (...)

To accomplish this with Peewee, the implementation is written in this way:

.. code-block:: python

    def count(query):
        # Select([source1, ... sourcen], [column1, ...columnn])
        wrapped = Select(from_list=[query], columns=[fn.COUNT(SQL('1'))])
        curs = wrapped.tuples().execute(db)
        return curs[0][0]  # Return first column from first row of result.

We can actually express this more concisely using the
:py:meth:`~SelectBase.scalar` method, which is suitable for returning values
from aggregate queries:

.. code-block:: python

    def count(query):
        wrapped = Select(from_list=[query], columns=[fn.COUNT(SQL('1'))])
        return wrapped.scalar(db)

The :ref:`query_examples` document has a more complex example, in which we
write a query for a facility with the highest number of available slots booked:

The SQL we wish to express is:

.. code-block:: sql

    SELECT facid, total FROM (
      SELECT facid, SUM(slots) AS total,
             rank() OVER (order by SUM(slots) DESC) AS rank
      FROM bookings
      GROUP BY facid
    ) AS ranked
    WHERE rank = 1

We can express this fairly elegantly by using a plain :py:class:`Select` for
the outer query:

.. code-block:: python

    # Store rank expression in variable for readability.
    rank_expr = fn.rank().over(order_by=[fn.SUM(Booking.slots).desc()])

    subq = (Booking
            .select(Booking.facility, fn.SUM(Booking.slots).alias('total'),
                    rank_expr.alias('rank'))
            .group_by(Booking.facility))

    # Use a plain "Select" to create outer query.
    query = (Select(columns=[subq.c.facid, subq.c.total])
             .from_(subq)
             .where(subq.c.rank == 1)
             .tuples())

    # Iterate over the resulting facility ID(s) and total(s):
    for facid, total in query.execute(db):
        print(facid, total)

For another example, let's create a recursive common table expression to
calculate the first 10 fibonacci numbers:

.. code-block:: python

    base = Select(columns=(
        Value(1).alias('n'),
        Value(0).alias('fib_n'),
        Value(1).alias('next_fib_n'))).cte('fibonacci', recursive=True)

    n = (base.c.n + 1).alias('n')
    recursive_term = Select(columns=(
        n,
        base.c.next_fib_n,
        base.c.fib_n + base.c.next_fib_n)).from_(base).where(n < 10)

    fibonacci = base.union_all(recursive_term)
    query = fibonacci.select_from(fibonacci.c.n, fibonacci.c.fib_n)

    results = list(query.execute(db))

    # Generates the following result list:
    [{'fib_n': 0, 'n': 1},
     {'fib_n': 1, 'n': 2},
     {'fib_n': 1, 'n': 3},
     {'fib_n': 2, 'n': 4},
     {'fib_n': 3, 'n': 5},
     {'fib_n': 5, 'n': 6},
     {'fib_n': 8, 'n': 7},
     {'fib_n': 13, 'n': 8},
     {'fib_n': 21, 'n': 9},
     {'fib_n': 34, 'n': 10}]

More
----

For a description of the various classes used to describe a SQL AST, see the
:ref:`query builder API documentation <query-builder-api>`.

If you're interested in learning more, you can also check out the `project
source code <https://github.com/coleifer/peewee>`_.
