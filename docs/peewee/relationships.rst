.. _relationships:

Relationships and Joins
=======================

Relational databases derive most of their power from the ability to link rows
across tables. This document explains how Peewee models those links, what
happens under the hood when you traverse them, and how to write queries that
cross table boundaries efficiently.


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

:class:`ForeignKeyField` links one model to another. ``Tweet.user`` links
each tweet to the user who wrote it. ``Favorite.user`` and ``Favorite.tweet``
together record which users have favorited which tweets.

The following helper populates test data that the examples below will query:

.. code-block:: python

   def create_test_data():
       db.create_tables([User, Tweet, Favorite])

       users = {
           name: User.create(username=name)
           for name in ('alice', 'bob', 'carol')
       }

       tweet_data = {
           'alice':   ('alice-1', 'alice-2', 'alice-3'),
           'bob': ('bob-1', 'bob-2'),
           'carol': (),
       }
       tweets = {}
       for username, contents in tweet_data.items():
           for content in contents:
               tweets[content] = Tweet.create(
                   user=users[username],
                   content=content)

       # alice favorites bob's "bob-2",
       # bob favorites alice's "alice-3",
       # carol favorites alice's "alice-1" and "alice-3".
       favorite_data = (
           ('alice', ['bob-2']),
           ('bob',   ['alice-3']),
           ('carol', ['alice-1', 'alice-3']),
       )
       for username, contents in favorite_data:
           for content in contents:
               Favorite.create(user=users[username], tweet=tweets[content])

This gives the following data:

========= ============= ==================
User      Tweet         Favorited by
========= ============= ==================
alice     alice-1       carol
alice     alice-2
alice     alice-3       bob, carol
bob       bob-1
bob       bob-2         alice
carol     (no tweets)
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

   tweet = Tweet.get(Tweet.content == 'alice-1')

   # Accessing .user resolves the foreign key. Peewee issues a SELECT
   # query to fetch the related User row.
   print(tweet.user.username)  # 'alice'

   # Accessing .user_id returns the raw integer stored in the column,
   # without issuing any query.
   print(tweet.user_id)  # 1

The ``_id`` suffix accessor is available for every foreign key field. Use it
whenever only the ID value is needed, since it always avoids a query.

Lazy loading
^^^^^^^^^^^^

By default, a :class:`ForeignKeyField` is *lazy-loaded*: the related object
is not fetched until the attribute is first accessed, at which point a
``SELECT`` query is issued automatically. This is convenient but can lead to
performance problems (see :ref:`nplusone` below).

Lazy loading can be disabled for a field by specifying ``lazy_load=False``.
When disabled, accessing the related object returns the raw ID value rather
than issuing a query, matching the behaviour of the ``_id`` accessor:

.. code-block:: python

   class Tweet(BaseModel):
       user = ForeignKeyField(User, backref='tweets', lazy_load=False)
       ...

   for tweet in Tweet.select():
       # Returns the integer ID. User instance is not fetched because this
       # would require an additional query.
       print(tweet.user)

To retrieve the related object(s), select both sources and issue a
:meth:`~ModelSelect.join`:

.. code-block:: python

   # When the User data was eagerly loaded via a join, the full User
   # instance is accessible as normal, even if lazy_load=False.
   query = (Tweet
            .select(Tweet, User)  # Get both the Tweet AND the User.
            .join(User))  # Join is required to traverse the foreign-key.

   for tweet in query:
       print(tweet.user.username)  # No extra query needed.

.. seealso::
   :ref:`nplusone` explains when and why disabling lazy loading is useful.

.. _backreferences:

Back-references
---------------

Every :class:`ForeignKeyField` automatically creates a *back-reference* on
the related model. The back-reference is a pre-filtered :class:`ModelSelect`
query that returns all rows related to the given instance.

In the example schema, ``Tweet.user`` is a foreign key to ``User``. The
``backref='tweets'`` parameter means that every ``User`` instance gains a
``tweets`` attribute, which is a pre-filtered :class:`ModelSelect` query of
that user's tweets:

.. code-block:: pycon

   >>> alice = User.get(User.username == 'alice')

   >>> alice.tweets  # back-reference is a Select query.
   <peewee.ModelSelect object at 0x...>

   >>> for tweet in alice.tweets:
   ...     print(tweet.content)
   alice-1
   alice-2
   alice-3

``alice.tweets`` is a pre-filtered ``SELECT`` query:

.. code-block:: pycon

   >>> alice.tweets.sql()
   ('SELECT "t1"."id", "t1"."user_id", "t1"."content", "t1"."timestamp"
     FROM "tweet" AS "t1" WHERE ("t1"."user_id" = ?)', [1])

A back-reference behaves like any other :class:`Select` query and can be
filtered, ordered, and chained:

.. code-block:: python

   recent = (alice.tweets
             .order_by(Tweet.timestamp.desc())
             .limit(2))

If no ``backref`` name is specified, Peewee generates one automatically using
the pattern ``<lowercase_classname>_set`` (e.g. ``tweet_set``). Specifying an
explicit ``backref`` is recommended for clarity.

.. _nplusone:

The N+1 Problem
---------------

The *N+1 problem* occurs when code issues one query to fetch a list of rows,
then issues one or more additional queries *per row* to fetch related data. For
example, displaying a list of tweets, and then for each tweet issuing an
additional query to select their related user:

.. code-block:: python

   # Bad: issues 1 query for tweets + N queries to get the related users.
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
   for user in User.select().with_related(Load(User.tweets)):
       print(user.username)
       for tweet in user.tweets:  # Eager-loaded, no additional query.
           print('  ', tweet.content)

Peewee provides two complementary tools for avoiding N+1 queries:

* **Joins** - combine rows from multiple tables in a single ``SELECT``. Best
  when traversing a foreign key *toward* its target (many-to-one direction),
  for example fetching tweets with their authors.
* **Eager loading** - issue one query per table and assign the results together
  in Python. Best when traversing a back-reference (one-to-many direction), for
  example fetching users with all their tweets. Peewee provides the
  :meth:`~ModelSelect.with_related` helper for this.

Both are covered in the sections below. The choice between them depends on the
shape of the query.

.. _joins:

Joins
-----

A SQL join combines columns from two or more tables into a single result set.
Peewee's :meth:`~ModelSelect.join` method generates the appropriate ``JOIN``
clause and reconstructs the model graph automatically.

Simple joins
^^^^^^^^^^^^

To fetch all of alice's tweets, join from ``Tweet`` to ``User`` and filter on
the username:

.. code-block:: python

   query = (Tweet
            .select()
            .join(User)
            .where(User.username == 'alice'))

   for tweet in query:
       print(tweet.content)

Peewee inferred the join predicate since ``Tweet.user`` is the only key between
the two models. To explicitly specify the join predicate use ``on=``:

.. code-block:: python

   query = (Tweet
            .select()
            .join(User, on=(Tweet.user == User.id))
            .where(User.username == 'alice'))

If a ``User`` instance is already available, the back-reference is simpler and
equivalent for straightforward cases:

.. code-block:: python

   alice = User.get(User.username == 'alice')
   for tweet in alice.tweets:
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

Join context
^^^^^^^^^^^^

Peewee tracks a *join context*: the model from which the next ``join()`` call
will depart. At the start of a query the join context is the model being
selected from, and each call to ``join()`` moves the context to the model just
joined. Chaining joins therefore walks a path through related models:

.. code-block:: python

   # Get all the favorites for alice's tweets.
   query = (Favorite
            .select()
            .join(Tweet)  # Joins Favorite -> Tweet.
            .join(User)  # Joins Tweet -> User.
            .where(User.username == 'alice'))

A chain is usually what you want. When a query needs to join from one model to
*two* different models, the context must be reset back to the branch point using
:meth:`~ModelSelect.switch`. To find all of alice's tweets and how many times
each has been favorited, we join ``Tweet -> User`` and ``Tweet -> Favorite``,
switching back to ``Tweet`` in between:

.. code-block:: python

   query = (Tweet
            .select(Tweet.content, fn.COUNT(Favorite.id).alias('fav_count'))
            .join(User)
            .switch(Tweet)  # Reset context to Tweet.
            .join(Favorite, JOIN.LEFT_OUTER)
            .where(User.username == 'alice')
            .group_by(Tweet.content))

   for tweet in query:
       print(f'{tweet.content}: favorited {tweet.fav_count} times')

Without the call to ``.switch(Tweet)``, Peewee would attempt to join from
``User`` to ``Favorite`` using ``Favorite.user``, producing incorrect results.

:meth:`~ModelSelect.join_from` is a more explicit alternative that names the
join's source model directly, so no ``switch()`` is needed. ``join_from(A, B)``
is equivalent to ``switch(A).join(B)``:

.. code-block:: python

   query = (Tweet
            .select(Tweet.content, fn.COUNT(Favorite.id).alias('fav_count'))
            .join_from(Tweet, User)
            .join_from(Tweet, Favorite, JOIN.LEFT_OUTER)
            .where(User.username == 'alice')
            .group_by(Tweet.content))

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

   # alice -> alice-1
   # alice -> alice-2
   # alice -> alice-3
   # bob -> bob-1
   # bob -> bob-2

Returning the rows as dictionaries makes this clearer:

.. code-block:: python

   query = (Tweet
            .select(Tweet.content, User.username)
            .join(User)
            .dicts())

   for row in query:
       print(row)

   # {'content': 'alice-1', 'username': 'alice'}
   # {'content': 'alice-2', 'username': 'alice'}
   # {'content': 'alice-3', 'username': 'alice'}
   # {'content': 'bob-1', 'username': 'bob'}
   # {'content': 'bob-2', 'username': 'bob'}

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

   # alice -> alice-1

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

   # alice liked bob-2 by bob
   # bob liked alice-3 by alice
   # carol liked alice-1 by alice
   # carol liked alice-3 by alice

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
   ON (
      (tweet.user_id = latest_query.user_id) AND
      (tweet.timestamp = latest_query.max_ts))
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

   # alice -> alice-3
   # bob -> bob-2

Three things in this query:

* We used :meth:`~ModelSelect.join_from` to explicitly specify the join
  context. We wrote ``.join_from(Tweet, User)``, which is equivalent to
  ``.switch(Tweet).join(User)``.
* We referenced columns in the subquery using the magic ``.c`` attribute,
  for example ``latest_query.c.max_ts``. The ``.c`` attribute is used to
  dynamically create references to columns in subqueries.
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

   # alice -> alice-3
   # bob -> bob-2

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

To find everyone that ``alice`` follows:

.. code-block:: python

   alice = User.get(User.username == 'alice')

   following = (User
                .select()
                .join(Relationship, on=Relationship.to_user)
                .where(Relationship.from_user == alice))

To find everyone who follows ``alice``:

.. code-block:: python

   followers = (User
                .select()
                .join(Relationship, on=Relationship.from_user)
                .where(Relationship.to_user == alice))

Passing the field instance to ``on=`` tells Peewee which foreign key column to
use for the join.

.. _joining-without-fk:

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
                (User.username == 'alice')))

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

.. _related-naming:

Related-instance Names
----------------------

When Peewee reconstructs a model graph from a query, each related instance is
attached to the parent object under an attribute. The attribute name follows
a small set of conventions and can always be overridden explicitly.

Default names
^^^^^^^^^^^^^

For a :class:`ForeignKeyField`:

* **Forward direction**: the foreign-key field's own name. ``Tweet.user``
  produces ``tweet.user``.
* **Back-reference**: the ``backref`` argument to the foreign-key. If ``backref``
  is not given, the default is ``<lowercase_classname>_set``, e.g. ``user.tweet_set``.
  Pass ``backref='+'`` to suppress the back-reference entirely.

For a :class:`ManyToManyField`, the default back-reference is the lowercase
name of the declaring model with an ``s`` suffix. Declaring ``ManyToManyField(User)``
on a ``Note`` model produces ``user.notes``. Pass ``backref='...'`` to override,
or ``backref='+'`` to suppress.

For joins performed by :meth:`~ModelSelect.join`:

* If the join follows a foreign key that Peewee can resolve, the forward
  direction uses the FK field's name, and the backref direction uses the
  destination model's ``_meta.name`` (typically the lowercase class name).
* If the join has no resolvable foreign key (for example, joining on an
  arbitrary expression, a :class:`Table`, or a subquery), the destination's
  default name is used: the model's ``_meta.name``, or the alias / table
  name for non-model sources. Supply ``attr=`` to override - see below.

Overriding with ``attr=``
^^^^^^^^^^^^^^^^^^^^^^^^^

:meth:`~ModelSelect.join` accepts an ``attr`` keyword that overrides the
attribute name used to attach the joined instance:

.. code-block:: python

   query = (Tweet
            .select(Tweet, User)
            .join(User, attr='author'))

   for tweet in query:
       print(tweet.author.username)  # Instead of tweet.user.

``attr`` is optional everywhere. Joins without a resolvable foreign key
(a :class:`Table`, a subquery, an arbitrary expression) attach at the
destination's default name, and ``attr`` overrides it (see
:ref:`joining without a foreign key <joining-without-fk>`). One collision
is rejected: aliasing a join's ``on`` expression with the ``<fk>_id``
column name of a foreign key, e.g.
``on=(Tweet.user == User.id).alias('user_id')``, raises
:exc:`ValueError`, as that attribute holds the raw column value.

Directing computed columns with ``bind_to``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a ``SELECT`` includes a computed or aliased column whose logical
owner is one of the joined sources, use :meth:`~ColumnBase.bind_to` to tell
Peewee which source the column belongs to. The column is then attached to
the corresponding instance in the reconstructed graph:

.. code-block:: python

   name = Case(User.username, [
       ('alice', 'Alice A.'),
       ('bob', 'Bob B.')], 'Someone Else')

   query = (Tweet
            .select(Tweet.content, name.alias('display').bind_to(User))
            .join(User))

   for tweet in query:
       print(tweet.content, tweet.user.display)

Without ``bind_to``, the computed ``display`` column would be bound to the
``tweet`` instance. ``bind_to`` accepts a :class:`Model`, :class:`ModelAlias`,
or any other source that is present in the query's FROM / JOIN list. If the
target is not selected, peewee raises a :exc:`ValueError` when building the
result set.

Outer joins and missing rows
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a ``LEFT OUTER`` (or ``FULL``) join finds no matching row, the join
attribute is populated as ``None``:

.. code-block:: python

   query = (User
            .select(User, Tweet)
            .join(Tweet, JOIN.LEFT_OUTER))

   for user in query:
       if user.tweet is not None:
           print(user.username, user.tweet.content)
       else:
           print(user.username, 'has no tweets')

Peewee detects a missing row by checking whether every column selected from
the joined source came back ``NULL``. As a result:

* A row that *did* match, but whose selected columns all happen to be ``NULL``,
  is indistinguishable from a miss and also populates as ``None``. Include a
  column that is never ``NULL`` (typically the primary key) in the select
  when the two cases must be told apart.
* Only outer joins populate ``None``. With an inner join the attribute is left
  unset, so a foreign-key attribute falls back to its usual behavior of
  lazy-loading the related row on access.

When the join attribute is the foreign key itself (the default in the forward
direction), a miss does not disturb the foreign-key id on the instance. With
a join predicate more restrictive than the foreign key, for example joining
against a filtered subquery, the attribute reads as ``None`` while the
``<fk>_id`` attribute still contains and reports the column's value.

.. _manytomany:

Many-to-Many Relationships
--------------------------

A many-to-many relationship allows one row in table A to relate to many rows
in table B *and vice versa*. This requires an intermediate *through table* that
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

   alice = Student.get(Student.name == 'Alice')

   courses = (Course
              .select()
              .join(Enrollment)
              .where(Enrollment.student == alice)
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

   alice = Student.create(name='Alice')
   cs101 = Course.create(title='CS 101')

   # Adding and removing relationships:
   alice.courses.add(cs101)
   alice.courses.add(Course.select().where(Course.title.contains('Math')))

   cs101.students.remove(alice)
   cs101.students.clear()   # Removes all students from this course.

   # Querying through the field:
   for course in alice.courses.order_by(Course.title):
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

Avoiding N+1 with eager loading
-------------------------------

Joins solve the N+1 problem when traversing from the *many* side toward the
*one* side, for example fetching tweets with their authors. Each tweet has
exactly one author, so a join produces exactly one result row per tweet.

The situation is different when traversing from the *one* side toward the
*many* side, for example fetching users *and all their tweets*. A join in this
direction produces one result row *per tweet*, which means users with multiple
tweets appear multiple times in the result set. Deduplicating those rows in
application code is awkward and error-prone.

Eager loading solves this by issuing one query per table, then distributing the
results in Python. Instead of *O(n)* queries for *n* rows, we do *O(k)* queries
for *k* tables. Peewee has two APIs for this:

* :meth:`~ModelSelect.with_related` with :class:`Load` nodes: the declarative,
  nestable form, recommended for new code.
* :func:`prefetch`: the older flat-list form, kept for backwards compatibility.

They share one execution engine and differ mainly in how the load is
expressed. :func:`prefetch` supports the ``WHERE`` and ``JOIN`` strategies
but rejects ``MATERIALIZE``, which is with_related-only.

Eager loading with with_related
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:meth:`~ModelSelect.with_related` attaches related rows to a query. Each
relationship is named by a :class:`Load` node, which runs when the query
is first executed:

.. code-block:: python

   # Two queries total, regardless of how many users or tweets there are:
   # SELECT * FROM user
   # SELECT * FROM tweet WHERE user_id IN (...)
   query = User.select().with_related(Load(User.tweets))

   for user in query:
       print(user.username)
       for tweet in user.tweets:  # No additional query, user.tweets is a list.
           print(f'  {tweet.content}')

   # Prints:
   # alice
   #   alice-1
   #   alice-2
   #   alice-3
   # bob
   #   bob-1
   #   bob-2
   # carol

``Load`` accepts a back-reference (``Load(User.tweets)``, the one-to-many
direction) or a foreign key (``Load(Tweet.user)``, the many-to-one direction).
The rows are loaded once, when the query is first executed, whether by
iteration, ``get()``, ``first()``, indexing or ``len()``.

:meth:`Load.then` nests one relation inside another, so a load can span over two
tables. To fetch users, their tweets, and the favorites on each tweet in three
queries:

.. code-block:: python

   query = User.select().with_related(
       Load(User.tweets).then(
           Load(Tweet.favorites)))

   for user in query:
       for tweet in user.tweets:
           print(f'{user.username}: {tweet.content} '
                 f'({len(tweet.favorites)} favorites)')

   # Prints:
   # alice: alice-1 (1 favorites)
   # alice: alice-2 (0 favorites)
   # alice: alice-3 (2 favorites)
   # bob: bob-1 (0 favorites)
   # bob: bob-2 (1 favorites)

:meth:`~ModelSelect.with_related` accepts more than one :class:`Load`, so
several independent branches can hang off the same parent in a single call:

.. code-block:: python

   # Each user's tweets and (separately) the tweets they have favorited:
   query = User.select().with_related(
       Load(User.tweets),
       Load(User.favorites))

   for user in query:
       print(f'{user.username}: {len(user.tweets)}, {len(user.favorites)}')

   # alice: 3, 1
   # bob: 2, 1
   # carol: 0, 2

Per-relation query
^^^^^^^^^^^^^^^^^^

:class:`Load` accepts a query as the second parameter.

.. code-block:: python

   recent = (Tweet.select()
             .where(Tweet.content != 'alice-2')
             .order_by(Tweet.timestamp.desc()))
   query = User.select().with_related(Load(User.tweets, recent))

   for user in query:
       print(user.username, [t.content for t in user.tweets])

   # Prints:
   # alice ['alice-3', 'alice-1']
   # bob ['bob-2', 'bob-1']
   # carol []

Because it is a real query it can join other tables and select from them:

.. code-block:: python

   # Each tweet's favorites, with the favoriting user already loaded:
   favorites = Favorite.select(Favorite, User).join(User)
   query = Tweet.select().with_related(Load(Tweet.favorites, favorites))

   for tweet in query:
       for fav in tweet.favorites:
           print(tweet.content, fav.user.username)  # No extra query.

   # Prints:
   # alice-1 carol
   # alice-3 bob
   # alice-3 carol
   # bob-2 alice

A relation can limit the rows fetched per parent with ``per_parent=n``: it keeps
the first ``n`` of each parent's children using a window function, ranked by the
relation query's ``order_by``:

.. code-block:: python

   # The two most-recent tweets for each user, in one query:
   tweets = Tweet.select().order_by(Tweet.timestamp.desc())
   query = User.select().with_related(
       Load(User.tweets, tweets, per_parent=2))

   for user in query:
       print(user.username, [t.content for t in user.tweets])

   # Prints:
   # alice ['alice-3', 'alice-2']
   # bob ['bob-2', 'bob-1']
   # carol []

A plain ``query.limit(n)`` instead applies one ``LIMIT`` to the whole relation,
returning ``n`` rows in total (the same as :func:`prefetch`). Per-parent limits
require window-function support (SQLite 3.25+, PostgreSQL, MySQL 8).

.. _prefetch-strategy:

Load strategy and materialize
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Each relation has to restrict its children to the rows belonging to the parents
already fetched. The ``strategy`` argument controls how:

* ``PREFETCH_TYPE.WHERE`` (the default) filters with an ``IN`` subquery, of the
  form ``... WHERE user_id IN (SELECT id FROM user ...)``. The parent query is
  embedded and re-evaluated by the database.
* ``PREFETCH_TYPE.JOIN`` filters by joining the child table against the parent
  query as a derived table. It returns the same rows as ``WHERE``, only the
  query shape differs.
* ``PREFETCH_TYPE.MATERIALIZE`` reads the parent keys already held in memory and
  sends them as a literal ``IN`` list. This avoids re-running the parent query
  at all, at the cost of one bind parameter per key, so it is bounded by the
  backend's parameter limit.

``WHERE`` and ``JOIN`` embed the parent query, so they work with both
:meth:`~ModelSelect.with_related` and :func:`prefetch`. ``MATERIALIZE`` reads
keys from already-fetched parent instances, which only
:meth:`~ModelSelect.with_related` holds, so :func:`prefetch` rejects it.

.. code-block:: python

   # JOIN: filter via a join against the parent query.
   tweets = Load(User.tweets, strategy=PREFETCH_TYPE.JOIN)
   query = User.select().with_related(tweets)

   # MATERIALIZE: the user ids are sent inline, with no parent subquery.
   tweets = Load(User.tweets, strategy=PREFETCH_TYPE.MATERIALIZE)
   query = User.select().with_related(tweets)

Legacy: prefetch
^^^^^^^^^^^^^^^^

:func:`prefetch` is the original eager-loading API. It takes a flat list of
queries and infers how they connect from the foreign keys between them. It is
still supported, but :meth:`~ModelSelect.with_related` is preferred for new
code.

.. code-block:: python

   users = User.select().prefetch(Tweet)

   # Equivalent to above.
   users = prefetch(User.select(), Tweet.select())

   # Three tables, three queries.
   users = prefetch(User.select(), Tweet.select(), Favorite.select())

The models passed to :func:`prefetch` must be linked by foreign keys. Peewee
infers the relationships and assigns the prefetched rows to the appropriate
back-reference attribute on each instance.

When a subquery relates to more than one previously-listed query (for example a
``Favorite`` that has foreign keys to both ``User`` and ``Tweet``), pass a
``(query, target_model)`` tuple to choose which relationship to follow. This is
the disambiguation that ``with_related`` avoids by naming each foreign key:

.. code-block:: python

   # Fetch favorites via User, not via Tweet.
   query = prefetch(users, tweets, (favorites, User))

Both the outer query and the prefetch subqueries can carry ``WHERE`` clauses
and other modifiers independently:

.. code-block:: python

   one_week_ago = datetime.date.today() - datetime.timedelta(days=7)

   users = prefetch(
       User.select().order_by(User.username),
       Tweet.select().where(Tweet.timestamp >= one_week_ago),
   )

The filter on ``Tweet`` applies only to the prefetched tweets, it does not
affect which users are returned. ``prefetch`` accepts the ``WHERE`` and ``JOIN``
strategies through its ``prefetch_type`` keyword (see :ref:`prefetch-strategy`).

Choosing between joins and eager loading
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use a **join** when:

* Traversing from the many side to the one side (tweet -> author).
* Filtering on columns in the related table (tweets by users whose username
  starts with "h").
* Only a subset of related fields is needed.

Use **eager loading** when:

* Traversing from the one side to the many side (user -> all their tweets).
* The full set of related rows is needed for each parent row.
* Nesting more than one level of related data (users -> tweets -> favorites).

.. note::
   ``LIMIT`` on the outer query works as expected. For top-N-per-parent, use
   :meth:`~ModelSelect.with_related` with ``per_parent=n`` (above), or
   :ref:`top-n-per-group` for the underlying technique.

.. seealso::
   :meth:`~ModelSelect.with_related` and :func:`prefetch` API reference.
