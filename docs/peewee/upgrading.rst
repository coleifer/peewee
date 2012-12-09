.. _upgrading:

Upgrading peewee
================

Peewee went from 2319 source lines of code to ~1600 between 1.0 and 2.0.

Goals for the new API
---------------------

* consistent: there is one way of doing things
* expressive: things can be done that I never thought of


.. _changes:

Changes from version 1.0
------------------------

The biggest changes between 1.0 and 2.0 are in the syntax used for
constructing queries.  The first iteration of peewee I threw up on github
was about 600 lines.  I was passing around strings and dictionaries and
as time went on and I added features, those strings turned into tuples and
objects.  This meant, though, that I needed code to handle all the possible
ways of expressing something.  Look at the code for `parse_select <https://gist.github.com/a957dbbff0310fd88d5c>`_.

I learned a valuable lesson:  keep data in datastructures until the
*absolute* last second.

With the benefit of hindsight and experience, I decided to rewrite and unify
the API a bit.  The result is a tradeoff.  The newer syntax may be a bit more
verbose at times, but at least it will be consistent.

Since seeing is believing, I will show some side-by-side comparisons.  Let's
pretend we're using the models from the cookbook, good ol' user and tweet:

.. code-block:: python

    class User(Model):
        username = CharField()

    class Tweet(Model):
        user = ForeignKeyField(User, related_name='tweets')
        message = TextField()
        created_date = DateTimeField(default=datetime.datetime.now)
        is_published = BooleanField(default=True)


Get me a list of all tweets by a user named "charlie":

.. code-block:: python

    # 1.0
    Tweet.select().join(User).where(username='charlie')

    # 2.0
    Tweet.select().join(User).where(User.username == 'charlie')

Get me a list of tweets ordered by the authors username, then newest to oldest:

.. code-block:: python

    # 1.0 -- this is one where there are like 10 ways to express it
    Tweet.select().join(User).order_by('username', (Tweet, 'created_date', 'desc'))

    # 2.0
    Tweet.select().join(User).order_by(User.username, Tweet.created_date.desc())

Get me a list of tweets created by users named "charlie" or "peewee herman", and
which were created in the last week.

.. code-block:: python

    last_week = datetime.datetime.now() - datetime.timedelta(days=7)

    # 1.0
    Tweet.select().where(created_date__gt=last_week).join(User).where(
        Q(username='charlie') | Q(username='peewee herman')
    )

    # 2.0
    Tweet.select().join(User).where((Tweet.created_date > last_week) & (
        (User.username == 'charlie') | (User.username == 'peewee herman')
    ))

Get me a list of users and when they last tweeted (if ever):

.. code-block:: python

    # 1.0
    User.select({
        User: ['*'],
        Tweet: [Max('created_date', 'last_date')]
    }).join(Tweet, 'LEFT OUTER').group_by(User)

    # 2.0
    User.select(
        User, fn.Max(Tweet.created_date).alias('last_date')
    ).join(Tweet, JOIN_LEFT_OUTER).group_by(User)

Let's do an atomic update on a counter model (you'll have to use your imagination):

.. code-block:: python

    # 1.0
    Counter.update(count=F('count') + 1).where(url=request.url)

    # 2.0
    Counter.update(count=Counter.count + 1).where(Counter.url == request.url)

Let's find all the users whose username starts with 'a' or 'A':

.. code-block:: python

    # 1.0
    User.select().where(R('LOWER(SUBSTR(username, 1, 1)) = %s', 'a'))

    # 2.0
    User.select().where(fn.Lower(fn.Substr(User.username, 1, 1)) == 'a')


I hope a couple things jump out at you from these examples.  What I see is
that the 1.0 API is sometimes a bit less verbose, but it relies on strings in
many places (which may be fields, aliases, selections, join types, functions, etc).  In the
where clause stuff gets crazy as there are args being combined with bitwise
operators ("Q" expressions) and also kwargs being used with django-style "double-underscore"
lookups. The crazy thing is, there are so many different ways I could have expressed
some of the above queries using peewee 1.0 that I had a hard time deciding which
to even write.

The 2.0 API is hopefully more consistent.  Selections, groupings, functions, joins
and orderings all pretty much conform to the same API.  Likewise, where and having
clauses are handled the same way (in 1.0 the having clause is simply a raw string).
The new :py:class:`fn` object actually is a wrapper -- whatever appears to the right of the
dot (i.e. fn.*Lower*) -- is treated as a function that can take any arbitrary
parameters.

If you're feeling froggy and want to get coding, you might want to check out:

* :ref:`the cookbook <cookbook>`, which contains many practical examples
* :ref:`the example app documentation <example-app>`, which shows how to build a simple twitter-like site
* :ref:`using "fn" <fn_examples>`
* :ref:`the querying docs <querying>`, which contain an in-depth overview of the query apis


Changes in fields and columns
-----------------------------

Well, for one, columns are gone.  They were a shim that I used to hack in non-integer
primary keys.  I always thought the field SQL generation was one of the grosser
parts of the module and even worse was the back-and-forth that happened between the
field and column classes.  So, columns are gone - its just fields - and they're
hopefully a bit smaller and saner.  I also cleaned up the primary key business.
Basically it works like this:

* if you don't specify a primary key, one will be created named "id"
* if you do specify a primary key and it is a PrimaryKeyField (or subclass),
  it will be an automatically incrementing integer
* if you specify a primary key and it is anything else peewee assumes you are
  in control and will stay out of the way.

The API for specifying a non-auto-incrementing primary key changed:

.. code-block:: python

    # 1.0
    class OldSchool(Model):
        uuid = PrimaryKeyField(column_class=VarCharColumn)

    # 2.0
    class NewSchool(Model):
        uuid = CharField(primary_key=True)

The kwargs for the Field constructor changed slightly, the biggest probably
being that ``db_index`` was renamed to ``index``.


Changes in model definitions
----------------------------

When specifying a default ordering for a model:

.. code-block:: python

    # 1.0
    class Old(Model):
        class Meta:
            ordering = (('field1', 'desc'), ('field2', 'asc'))

    # 2.0
    class New(Model):
        class Meta:
            order_by = ('-field1', 'field2') # note it is "order_by"


Changes in database and adapter
-------------------------------

In peewee 1.0 there were two classes that controlled access to the database --
the Database subclass and an Adapter.  The adapter's job was to say what features
a database backend provided, what operations were valid, what column types were
supported, and how to open a connection.  The database was a bit higher-level and
its main job was to execute queries and provide metadata about the database, like
lists of tables, last insert id, etc.

I chose to consolidate these two classes, since inevitably they always went in
pairs (e.g. SqliteDatabase/SqliteAdapter).  The database class now encapsulates
all this functionality.


How the SQL gets made
---------------------

The first thing I started with is the QueryCompiler and the data structures it
uses.  You can see it start to take shape in my `first commit <https://github.com/coleifer/peewee/blob/3cc1799b707e41183e2afb237b9e61c6e760d3a7/p2.py>`_.
It takes the data structures from peewee and spits out SQL.  It works recursively and knows
about a few types of expressions:

* the query tree
* comparison statements like '==', 'IN', 'LIKE' which comprise the leaves of the tree
* expressions like addition, substraction, bitwise operations
* sql functions like ``substr`` and ``lower``
* aggregate functions like ``count`` and ``max``
* columns, which may be selected, joined on, grouped by, ordered by, used as parameters
  for functions and aggregates, etc.
* python objects to use as query parameters

At the heart of it is the ``Expr`` object, which is for "expression".  It
can be anything that can validly be translated into part of a SQL query.

Expressions can be nested, giving way to interesting possibilities like
the following example I love which selects users whose username starts with "a":

.. code-block:: python

    User.select().where(fn.Substr(fn.Lower(User.username, 1, 1)) == 'a')

The "where" clause now contains a tree with one leaf.  The leaf represents the
nested function expression on the left-hand-side and the scalar value 'a' on the
right hand side.  Peewee will recursively evaluate the expressions on either side
of the operation and generate the correct SQL.

Another aspect is that :py:class:`Field` objects are also expressions, which
makes it possible to write things like:

.. code-block:: python

    Employee.select().where(Employee.salary < (Employee.tenure * 1000) + 40000)

.. note:: I totally went crazy with operator overloading.

If you're interested in looking, the ``QueryCompiler.parse_expr`` method is where
the bulk of the code lives.
