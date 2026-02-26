.. _relationships:

Relationships and Joins
=======================

Relational databases derive most of their power from the ability to link rows
across tables. This document explains how Peewee models those links, what
happens under the hood when you traverse them, and how to write queries that
cross table boundaries efficiently.

By the end of this document you will understand:

* How :class:`ForeignKeyField` behaves at runtime, not just at schema
  definition time.
* What a back-reference is and when to use one.
* What the N+1 problem is and how to recognise it.
* How to write joins, including multi-table and self-referential joins.
* How many-to-many relationships are modelled.
* When to use :func:`prefetch` instead of a join.


Model Definitions
-----------------

All examples in this document use the following three models. They will be
defined once here and reused throughout.

.. code-block:: python

   import datetime
   from peewee import *

   db = SqliteDatabase(':memory:')

   class BaseModel(Model):
       class Meta:
           database = db

   class User(BaseModel):
       username = TextField()

   class Tweet(BaseModel):
       user = ForeignKeyField(User, backref='tweets')
       content = TextField()
       timestamp = DateTimeField(default=datetime.datetime.now)

   class Favorite(BaseModel):
       user = ForeignKeyField(User, backref='favorites')
       tweet = ForeignKeyField(Tweet, backref='favorites')

A :class:`ForeignKeyField` links one model to another. ``Tweet.user`` links
each tweet to the user who wrote it. ``Favorite.user`` and ``Favorite.tweet``
together record which users have favorited which tweets.

The following helper populates test data that the examples below will query:

.. code-block:: python

   def create_test_data():
       db.create_tables([User, Tweet, Favorite])

       users = {
           name: User.create(username=name)
           for name in ('huey', 'mickey', 'zaizee')
       }

       tweet_data = {
           'huey':   ('meow', 'hiss', 'purr'),
           'mickey': ('woof', 'whine'),
           'zaizee': (),
       }
       tweets = {}
       for username, contents in tweet_data.items():
           for content in contents:
               tweets[content] = Tweet.create(
                   user=users[username],
                   content=content)

       # huey favorites mickey's "whine",
       # mickey favorites huey's "purr",
       # zaizee favorites huey's "meow" and "purr".
       favorite_data = (
           ('huey',   ['whine']),
           ('mickey', ['purr']),
           ('zaizee', ['meow', 'purr']),
       )
       for username, contents in favorite_data:
           for content in contents:
               Favorite.create(user=users[username], tweet=tweets[content])

This gives the following data:

========= ============= ==================
User      Tweet         Favorited by
========= ============= ==================
huey      meow          zaizee
huey      hiss
huey      purr          mickey, zaizee
mickey    woof
mickey    whine         huey
zaizee    (no tweets)
========= ============= ==================

.. note::
   To log every query Peewee executes to the console - useful for verifying
   query counts while working through this document - add the following before
   running any queries:

   .. code-block:: python

      import logging
      logging.getLogger('peewee').addHandler(logging.StreamHandler())
      logging.getLogger('peewee').setLevel(logging.DEBUG)

.. _foreign-keys:

Foreign Keys
------------

When you declare a :class:`ForeignKeyField`, Peewee creates two things on
the model: a field that stores the raw integer ID value, and a descriptor that
resolves that ID into a full model instance on access.

.. code-block:: python

   tweet = Tweet.get(Tweet.content == 'meow')

   # Accessing .user resolves the foreign key - Peewee issues a SELECT
   # query to fetch the related User row.
   print(tweet.user.username)  # 'huey'

   # Accessing .user_id returns the raw integer stored in the column,
   # without issuing any query.
   print(tweet.user_id)  # 1

The ``_id`` suffix accessor is available for every foreign key field. Use it
whenever only the ID value is needed, since it avoids the extra query entirely.

Lazy loading
^^^^^^^^^^^^

By default, a :class:`ForeignKeyField` is *lazy-loaded*: the related object
is not fetched until the attribute is first accessed, at which point a
``SELECT`` query is issued automatically. This is convenient but can lead to
performance problems - see :ref:`nplusone` below.

To disable lazy loading on a specific field, pass ``lazy_load=False``. With
lazy loading disabled, accessing the attribute returns the raw ID value rather
than issuing a query, matching the behaviour of the ``_id`` accessor:

.. code-block:: python

   class Tweet(BaseModel):
       user = ForeignKeyField(User, backref='tweets', lazy_load=False)

   for tweet in Tweet.select():
       # Returns the integer ID, not a User instance. No extra query.
       print(tweet.user)

   # If the User data was eagerly loaded via a join, the full User
   # instance is accessible as normal, even with lazy_load=False.
   for tweet in Tweet.select(Tweet, User).join(User):
       print(tweet.user.username)

.. seealso::
   :ref:`nplusone` explains when and why disabling lazy loading is useful.

.. _backreferences:

Back-references
---------------

Every :class:`ForeignKeyField` automatically creates a *back-reference* on
the related model. The back-reference is a pre-filtered :class:`Select`
query that returns all rows pointing at a given instance.

In the example schema, ``Tweet.user`` is a foreign key to ``User``. The
``backref='tweets'`` parameter means that every ``User`` instance gains a
``tweets`` attribute, which is a pre-filtered :class:`Select` query:

.. code-block:: pycon

   >>> huey = User.get(User.username == 'huey')

   >>> huey.tweets  # back-reference is a Select query.
   <peewee.ModelSelect object at 0x...>

   >>> for tweet in huey.tweets:
   ...     print(tweet.content)
   meow
   hiss
   purr

Taking a closer look at ``huey.tweets``, we can see that it is just a simple
pre-filtered ``SELECT`` query:

.. code-block:: pycon

   >>> huey.tweets
   <peewee.ModelSelect at 0x7f0483931fd0>

   >>> huey.tweets.sql()
   ('SELECT "t1"."id", "t1"."content", "t1"."timestamp", "t1"."user_id"
     FROM "tweet" AS "t1" WHERE ("t1"."user_id" = ?)', [1])

A back-reference behaves like any other :class:`Select` query and can be
filtered, ordered, and chained:

.. code-block:: python

   recent = (huey.tweets
             .order_by(Tweet.timestamp.desc())
             .limit(2))

If no ``backref`` name is specified, Peewee generates one automatically using
the pattern ``<lowercase_classname>_set``. Specifying an explicit ``backref``
is recommended for clarity.

.. _nplusone:

The N+1 Problem
---------------

The *N+1 problem* occurs when code issues one query to fetch a list of N rows,
then issues one or more additional queries *per row* to fetch related data -
N+1 queries in total instead of one or two. At small scale this is invisible,
but at production scale it can make pages that should take milliseconds take
seconds.

Consider printing every tweet alongside its author's username:

.. code-block:: python

   # Bad: issues 1 query for tweets + 1 query per tweet for the user.
   for tweet in Tweet.select():
       print(tweet.user.username, '->', tweet.content)

   # Good: only one query is needed.
   query = (Tweet
            .select(Tweet, User)
            .join(User))

   for tweet in query:
       # tweet.user is a User instance populated from the joined data.
       # No additional query is issued.
       print(tweet.user.username, '->', tweet.content)

Without joining and selecting the related User, each access to ``tweet.user``
triggers a ``SELECT`` on the ``user`` table. With five tweets, this produces
six queries. With five thousand tweets, it produces five thousand and one.

The same problem can occur when iterating over back-references:

.. code-block:: python

   # Bad: issues 1 query for users + 1 query per user for their tweets.
   for user in User.select():
       print(user.username)
       for tweet in user.tweets:  # A new query for each user.
           print('  ', tweet.content)

   # Better:
   for user in User.select().prefetch(Tweet):
       print(user.username)
       for tweet in user.tweets:  # Pre-fetched, no additional query.
           print('  ', tweet.content)

Peewee provides two complementary tools for avoiding N+1 queries:

* **Joins** - combine rows from multiple tables in a single ``SELECT``. Best
  when traversing a foreign key *toward* its target (many-to-one direction),
  for example fetching tweets with their authors.
* **Prefetch** - issue one query per table and stitch the results together in
  Python. Best when traversing a back-reference (one-to-many direction), for
  example fetching users with all their tweets.

Both are covered in the sections below. The choice between them depends on the
shape of the query.

.. _joins:

Joins
-----

A SQL join combines columns from two or more tables into a single result set.
Peewee's :meth:`~ModelSelect.join` method generates the appropriate ``JOIN``
clause and, when the full result is returned as model instances, reconstructs
the model graph automatically.

Join context
^^^^^^^^^^^^

Peewee tracks a *join context*: the model from which the next ``join()`` call
will depart. At the start of a query the join context is the model being
selected from. Each call to ``join()`` moves the join context to the model just
joined.

.. code-block:: python

   # Context starts at Tweet.
   # After .join(User), context moves to User.
   query = Tweet.select().join(User)

When joining through multiple tables in a chain, this is usually what you want.
When joining from one model to two different models, the join context needs to
be reset explicitly using :meth:`~ModelSelect.switch` or
:meth:`~ModelSelect.join_from`.

Peewee infers the join predicate (the ``ON`` clause) from the foreign keys
defined on the models. If only one foreign key exists between two models, no
additional specification is required. If multiple foreign keys exist, the
relevant one must be specified explicitly.

The following code is equivalent to the prevoius example:

.. code-block:: python
   :emphasize-lines: 3

   query = (Tweet
            .select()
            .join(User, on=(Tweet.user == User.id))
            .where(User.username == 'huey'))

Simple joins
^^^^^^^^^^^^

To fetch all of huey's tweets, join from ``Tweet`` to ``User`` and filter on
the username:

.. code-block:: python

   query = (Tweet
            .select()
            .join(User)
            .where(User.username == 'huey'))

   for tweet in query:
       print(tweet.content)

Peewee inferred the join predicate since ``Tweet.user`` is the only key between
the two models. To explicitly specify the join predicate use ``on=``:

.. code-block:: python

   query = (Tweet
            .select()
            .join(User, on=(Tweet.user == User.id))
            .where(User.username == 'huey'))

If a ``User`` instance is already available, the back-reference is simpler and
equivalent for straightforward cases:

.. code-block:: python

   huey = User.get(User.username == 'huey')
   for tweet in huey.tweets:
       print(tweet.content)

The join is the better choice when filtering or joining further. The
back-reference is more readable for simple access to related rows.

Joining across multiple tables
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To count how many favorites each user has received across all their tweets,
a join must traverse ``User -> Tweet -> Favorite``. Because each join moves the
context forward, this chain can be written directly:

.. code-block:: python

   # Context: User -> join -> Tweet -> join -> Favorite
   query = (User
            .select(User.username, fn.COUNT(Favorite.id).alias('fav_count'))
            .join(Tweet, JOIN.LEFT_OUTER)
            .join(Favorite, JOIN.LEFT_OUTER)
            .group_by(User.username))

   for user in query:
       print(f'{user.username}: {user.fav_count} favorites received')

Both joins use ``LEFT OUTER`` because a user may have no tweets, and a tweet
may have no favorites - yet both should appear in the result with a count of
zero.

Switching join context
^^^^^^^^^^^^^^^^^^^^^^

When a query needs to branch - joining from one model to two different models
- the join context must be reset manually using :meth:`~ModelSelect.switch`.

To find all tweets by huey and how many times each has been favorited:

.. code-block:: python

   # Context: Tweet -> join -> User (context is now User)
   # switch(Tweet) resets context to Tweet
   # -> join -> Favorite (context is now Favorite)
   query = (Tweet
            .select(Tweet.content, fn.COUNT(Favorite.id).alias('fav_count'))
            .join(User)
            .switch(Tweet)
            .join(Favorite, JOIN.LEFT_OUTER)
            .where(User.username == 'huey')
            .group_by(Tweet.content))

   for tweet in query:
       print(f'{tweet.content}: favorited {tweet.fav_count} times')

Without the call to ``.switch(Tweet)``, Peewee would attempt to join from
``User`` to ``Favorite`` using ``Favorite.user``, which would produce
incorrect results.

Using ``join_from``
^^^^^^^^^^^^^^^^^^^

:meth:`~ModelSelect.join_from` is an alternative to ``switch().join()`` that
makes the join source explicit in a single call. The above query can be
written equivalently as:

.. code-block:: python

   query = (Tweet
            .select(Tweet.content, fn.COUNT(Favorite.id).alias('fav_count'))
            .join_from(Tweet, User)
            .join_from(Tweet, Favorite, JOIN.LEFT_OUTER)
            .where(User.username == 'huey')
            .group_by(Tweet.content))

``join_from(A, B)`` is equivalent to ``switch(A).join(B)`` and is often more
readable when a query branches across several paths.

Selecting columns from joined models
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When columns from multiple models are included in ``select()``, Peewee
reconstructs the model graph and assigns related model instances to their
corresponding attributes.

.. code-block:: python

   query = (Tweet
            .select(Tweet.content, User.username)
            .join(User))

   for tweet in query:
       # tweet.user is a User instance populated from the joined data.
       # No additional query is issued.
       print(tweet.user.username, '->', tweet.content)

   # huey -> meow
   # huey -> hiss
   # huey -> purr
   # mickey -> woof
   # mickey -> whine

To make it a bit more obvious that it's doing the correct thing, we can ask
Peewee to return the rows as dictionaries.

.. code-block:: python

   query = (Tweet
            .select(Tweet.content, User.username)
            .join(User)
            .dicts())

   for row in query:
       print(row)

   # {'content': 'meow', 'username': 'huey'}
   # {'content': 'hiss', 'username': 'huey'}
   # {'content': 'purr', 'username': 'huey'}
   # {'content': 'woof', 'username': 'mickey'}
   # {'content': 'whine', 'username': 'mickey'}

Compare these queries to the N+1 version: here, only one query is executed
regardless of how many tweets are returned.

The attribute name that Peewee uses to store the joined instance follows the
foreign key field name (``tweet.user`` in this case). To override it, pass
``attr`` to ``join()``:

.. code-block:: python

   query = (Tweet
            .select(Tweet.content, User.username)
            .join(User, attr='author'))

   for tweet in query:
       print(tweet.author.username, '->', tweet.content)

To flatten all selected columns onto the primary model instance rather than
nesting them in a sub-object, append ``.objects()``:

.. code-block:: python

   query = (Tweet
            .select(Tweet.content, User.username)
            .join(User)
            .objects())

   for tweet in query:
       # username is now an attribute on tweet directly.
       print(tweet.username, '->', tweet.content)

   # huey -> meow

See :ref:`row-types` for the different ways Peewee can return rows.

More complex example
^^^^^^^^^^^^^^^^^^^^

As a more complex example, in this query, we will write a single query that
selects all the favorites, along with the user who created the favorite, the
tweet that was favorited, and that tweet's author.

In SQL we would write:

.. code-block:: sql

   SELECT owner.username, tweet.content, author.username AS author
   FROM favorite
   INNER JOIN user AS owner ON (favorite.user_id = owner.id)
   INNER JOIN tweet ON (favorite.tweet_id = tweet.id)
   INNER JOIN user AS author ON (tweet.user_id = author.id);

Note that we are selecting from the user table twice - once in the context of
the user who created the favorite, and again as the author of the tweet.

With Peewee, we use :meth:`Model.alias` to alias a model class so it can be
referenced twice in a single query:

.. code-block:: python

   Owner = User.alias()
   query = (Favorite
            .select(Favorite, Tweet.content, User.username, Owner.username)
            .join_from(Favorite, Owner)  # Determine owner of favorite.
            .join_from(Favorite, Tweet)  # Join favorite -> tweet.
            .join_from(Tweet, User))     # Join tweet -> user.

We can iterate over the results and access the joined values in the following
way. Note how Peewee has resolved the fields from the various models we
selected and reconstructed the model graph:

.. code-block:: python

   for fav in query:
       print(fav.user.username, 'liked', fav.tweet.content, 'by', fav.tweet.user.username)

   # huey liked whine by mickey
   # mickey liked purr by huey
   # zaizee liked meow by huey
   # zaizee liked purr by huey

.. _join-subquery:

Subqueries
^^^^^^^^^^

Peewee allows you to join on any table-like object, including subqueries or
common table expressions (see :ref:`cte`). To demonstrate joining on a
subquery, let's query for all users and their latest tweet.

Here is the SQL:

.. code-block:: sql

   SELECT tweet.*, user.*
   FROM tweet
   INNER JOIN (
       SELECT latest.user_id, MAX(latest.timestamp) AS max_ts
       FROM tweet AS latest
       GROUP BY latest.user_id) AS latest_query
   ON ((tweet.user_id = latest_query.user_id) AND (tweet.timestamp = latest_query.max_ts))
   INNER JOIN user ON (tweet.user_id = user.id)

We'll do this by creating a subquery which selects each user and the timestamp
of their latest tweet. Then we can query the tweets table in the outer query
and join on the user and timestamp combination from the subquery.

.. code-block:: python

   # Define our subquery first. We'll use an alias of the Tweet model, since
   # we will be querying from the Tweet model directly in the outer query.
   Latest = Tweet.alias()
   latest_query = (Latest
                   .select(Latest.user, fn.MAX(Latest.timestamp).alias('max_ts'))
                   .group_by(Latest.user)
                   .alias('latest_query'))

   # Our join predicate will ensure that we match tweets based on their
   # timestamp *and* user_id.
   predicate = ((Tweet.user == latest_query.c.user_id) &
                (Tweet.timestamp == latest_query.c.max_ts))

   # We put it all together, querying from tweet and joining on the subquery
   # using the above predicate.
   query = (Tweet
            .select(Tweet, User)  # Select all columns from tweet and user.
            .join_from(Tweet, latest_query, on=predicate)  # Join tweet -> subquery.
            .join_from(Tweet, User))  # Join from tweet -> user.

Iterating over the query, we can see each user and their latest tweet.

.. code-block:: python

   for tweet in query:
       print(tweet.user.username, '->', tweet.content)

   # huey -> purr
   # mickey -> whine

There are a couple things you may not have seen before in the code we used to
create the query in this section:

* We used :meth:`~ModelSelect.join_from` to explicitly specify the join
  context. We wrote ``.join_from(Tweet, User)``, which is equivalent to
  ``.switch(Tweet).join(User)``.
* We referenced columns in the subquery using the magic ``.c`` attribute,
  for example ``latest_query.c.max_ts``. The ``.c`` attribute is used to
  dynamically create column references.
* Instead of passing individual fields to ``Tweet.select()``, we passed the
  ``Tweet`` and ``User`` models. This is shorthand for selecting all fields on
  the given model.

Common-table Expressions
^^^^^^^^^^^^^^^^^^^^^^^^

In the previous section we joined on a subquery, but we could just as easily
have used a :ref:`common-table expression (CTE) <cte>`. We will repeat the same
query as before, listing users and their latest tweets, but this time we will
do it using a CTE.

Here is the SQL:

.. code-block:: sql

   WITH latest AS (
       SELECT user_id, MAX(timestamp) AS max_ts
       FROM tweet
       GROUP BY user_id)
   SELECT tweet.*, user.*
   FROM tweet
   INNER JOIN latest
       ON ((latest.user_id = tweet.user_id) AND (latest.max_ts = tweet.timestamp))
   INNER JOIN user
       ON (tweet.user_id = user.id)

This example looks very similar to the previous example with the subquery:

.. code-block:: python

   # Define our CTE first. We'll use an alias of the Tweet model, since
   # we will be querying from the Tweet model directly in the main query.
   Latest = Tweet.alias()
   cte = (Latest
          .select(Latest.user, fn.MAX(Latest.timestamp).alias('max_ts'))
          .group_by(Latest.user)
          .cte('latest'))

   # Our join predicate will ensure that we match tweets based on their
   # timestamp *and* user_id.
   predicate = ((Tweet.user == cte.c.user_id) &
                (Tweet.timestamp == cte.c.max_ts))

   # We put it all together, querying from tweet and joining on the CTE
   # using the above predicate.
   query = (Tweet
            .select(Tweet, User)  # Select all columns from tweet and user.
            .join(cte, on=predicate)  # Join tweet -> CTE.
            .join_from(Tweet, User)  # Join from tweet -> user.
            .with_cte(cte))

We can iterate over the result-set, which consists of the latest tweets for
each user:

.. code-block:: python

   for tweet in query:
       print(tweet.user.username, '->', tweet.content)

   # huey -> purr
   # mickey -> whine

.. note::
   For more information about using CTEs, including information on writing
   recursive CTEs, see the :ref:`cte` section of the "Querying" document.

Multiple foreign keys to the same model
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When two foreign keys on the same model both point at the same target model,
Peewee cannot infer which one to use for a join. The field must be specified
explicitly.

Consider a ``Relationship`` model recording which users follow which other
users:

.. code-block:: python

   class Relationship(BaseModel):
       from_user = ForeignKeyField(User, backref='following')
       to_user = ForeignKeyField(User, backref='followers')

       class Meta:
           indexes = ((('from_user', 'to_user'), True),)

To find everyone that ``huey`` follows:

.. code-block:: python

   huey = User.get(User.username == 'huey')

   following = (User
                .select()
                .join(Relationship, on=Relationship.to_user)
                .where(Relationship.from_user == huey))

To find everyone who follows ``huey``:

.. code-block:: python

   followers = (User
                .select()
                .join(Relationship, on=Relationship.from_user)
                .where(Relationship.to_user == huey))

Passing the field instance to ``on=`` tells Peewee which foreign key column to
use for the join.

Joining without a foreign key
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A join can be performed on any two tables, even when no :class:`ForeignKeyField`
exists between them, by supplying an explicit join predicate as an expression:

.. code-block:: python

   query = (User
            .select(User, ActivityLog)
            .join(ActivityLog,
                  on=(User.id == ActivityLog.object_id),
                  attr='log')
            .where(
                (ActivityLog.activity_type == 'login') &
                (User.username == 'huey')))

   for user in query:
       print(user.username, '->', user.log.description)

Self-joins
^^^^^^^^^^

A self-join queries a model against an alias of itself. Use :meth:`Model.alias`
to create the alias:

.. code-block:: python

   # Find all categories and their immediate parent name.
   class Category(BaseModel):
       name = TextField()
       parent = ForeignKeyField('self', null=True, backref='children')

   Parent = Category.alias()
   query = (Category
            .select(Category.name, Parent.name)
            .join(Parent, JOIN.LEFT_OUTER, on=(Category.parent == Parent.id))
            .order_by(Category.name))

   for row in query:
       print(row.name, 'parent:', row.parent.name if row.parent else 'None')

.. seealso::
   Recursive queries over self-referential structures are covered in
   :ref:`cte` using recursive CTEs.

.. _manytomany:

Many-to-Many Relationships
--------------------------

A many-to-many relationship - where one row in table A can relate to many rows
in table B *and vice versa* - requires an intermediate *through table* that
holds pairs of foreign keys.

Manual through table (recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The explicit approach gives full control over the through table and its
queries:

.. code-block:: python

   class Student(BaseModel):
       name = TextField()

   class Course(BaseModel):
       title = TextField()

   class Enrollment(BaseModel):
       """Through table linking students to courses."""
       student = ForeignKeyField(Student, backref='enrollments')
       course = ForeignKeyField(Course, backref='enrollments')
       enrolled_on = DateField(default=datetime.date.today)

       class Meta:
           indexes = (
               (('student', 'course'), True),
           )

To query all courses a given student is enrolled in:

.. code-block:: python

   huey = Student.get(Student.name == 'Huey')

   courses = (Course
              .select()
              .join(Enrollment)
              .where(Enrollment.student == huey)
              .order_by(Course.title))

   for course in courses:
       print(course.title)

To query all students in a given course, along with when they enrolled:

.. code-block:: python

   cs101 = Course.get(Course.title == 'CS 101')

   query = (Student
            .select(Student, Enrollment.enrolled_on)
            .join(Enrollment)
            .where(Enrollment.course == cs101)
            .order_by(Student.name))

   for student in query:
       print(student.name, student.enrollment.enrolled_on)

   # To attach enrollment date to the Student for simplicity:
   for student in query.objects():
       print(student.name, student.enrolled_on)

Since all data is available via the through table model, this approach is most
flexible and handles any querying requirement without special casing.

ManyToManyField
^^^^^^^^^^^^^^^

:class:`ManyToManyField` provides a shortcut API that manages the through
table automatically. It is suitable for simple cases where the through table
requires no extra columns and complex querying is not needed.

.. code-block:: python

   class Student(BaseModel):
       name = TextField()

   class Course(BaseModel):
       title = TextField()
       students = ManyToManyField(Student, backref='courses')

   # Retrieve the auto-generated through model if direct access is needed.
   Enrollment = Course.students.get_through_model()

   db.create_tables([Student, Course, Enrollment])

   huey = Student.create(name='Huey')
   cs101 = Course.create(title='CS 101')

   # Adding and removing relationships:
   huey.courses.add(cs101)
   huey.courses.add(Course.select().where(Course.title.contains('Math')))

   cs101.students.remove(huey)
   cs101.students.clear()   # Removes all students from this course.

   # Querying through the field:
   for course in huey.courses.order_by(Course.title):
       print(course.title)

.. warning::
   :class:`ManyToManyField` does not work correctly with model inheritance.
   The through table contains foreign keys back to the original models, and
   those pointers are not automatically updated for subclasses. For any model
   that will be subclassed, use an explicit through table instead.

.. seealso::
   :meth:`ManyToManyField.add`, :meth:`ManyToManyField.remove`,
   :meth:`ManyToManyField.clear`, :meth:`ManyToManyField.get_through_model`.


.. _prefetch:

Avoiding N+1 with Prefetch
--------------------------

Joins solve the N+1 problem when traversing from the *many* side toward the
*one* side - for example, fetching tweets with their authors. Each tweet has
exactly one author, so a join produces exactly one result row per tweet.

The situation is different when traversing from the *one* side toward the
*many* side - for example, fetching users *with all their tweets*. A join in
this direction produces one result row *per tweet*, which means users with
multiple tweets appear multiple times in the result set. Deduplicating those
rows in application code is awkward and error-prone.

:func:`prefetch` solves this by issuing one query per table, then stitching
the results together in Python. Instead of *O(n)* queries for *n* rows, we will
do *O(k)* queries for *k* tables:

.. code-block:: python

   # Two queries total, regardless of how many users or tweets there are:
   # SELECT * FROM user
   # SELECT * FROM tweet WHERE user_id IN (...)
   users = User.select().prefetch(Tweet)

   # Equivalent to above.
   users = prefetch(User.select(), Tweet.select())

   for user in users:
       print(user.username)
       for tweet in user.tweets:  # No additional query, user.tweets is a list.
           print(f'  {tweet.content}')

The models passed to :func:`prefetch` must be linked by foreign keys.
Peewee infers the relationships and assigns the prefetched rows to the
appropriate back-reference attribute on each instance.

Prefetch can span more than two tables. To fetch users, their tweets, and the
favorites on each tweet in three queries:

.. code-block:: python

   users = prefetch(User.select(), Tweet.select(), Favorite.select())

   for user in users:
       for tweet in user.tweets:
           print(f'{user.username}: {tweet.content} '
                 f'({len(tweet.favorites)} favorites)')

Filtering prefetched rows
^^^^^^^^^^^^^^^^^^^^^^^^^

Both the outer query and the prefetch subqueries can carry ``WHERE`` clauses
and other modifiers independently:

.. code-block:: python

   one_week_ago = datetime.date.today() - datetime.timedelta(days=7)

   users = prefetch(
       User.select().order_by(User.username),
       Tweet.select().where(Tweet.timestamp >= one_week_ago),
   )

The filter on ``Tweet`` applies only to the prefetched tweets; it does not
affect which users are returned.

Choosing between joins and prefetch
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use a **join** when:

* Traversing from the many side to the one side (tweet -> author).
* Filtering on columns in the related table (tweets by users whose username
  starts with "h").
* Only a subset of related fields is needed.

Use **prefetch** when:

* Traversing from the one side to the many side (user -> all their tweets).
* The full set of related rows is needed for each parent row.
* Nesting more than one level of related data (users -> tweets -> favorites).

.. note::
   ``LIMIT`` on the outer query of a :func:`prefetch` call works as
   expected. Limiting the *inner* queries (the prefetched tables) is not
   directly supported and requires a manual approach - see
   :ref:`top-n-per-group` in the recipes document for techniques.

.. seealso::
   :func:`prefetch` API reference.
