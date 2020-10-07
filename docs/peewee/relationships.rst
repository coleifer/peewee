.. _relationships:

Relationships and Joins
=======================

In this document we'll cover how Peewee handles relationships between models.

Model definitions
-----------------

We'll use the following model definitions for our examples:

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
        content = TextField()
        timestamp = DateTimeField(default=datetime.datetime.now)
        user = ForeignKeyField(User, backref='tweets')

    class Favorite(BaseModel):
        user = ForeignKeyField(User, backref='favorites')
        tweet = ForeignKeyField(Tweet, backref='favorites')


Peewee uses :py:class:`ForeignKeyField` to define foreign-key relationships
between models. Every foreign-key field has an implied back-reference, which is
exposed as a pre-filtered :py:class:`Select` query using the provided
``backref`` attribute.

Creating test data
^^^^^^^^^^^^^^^^^^

To follow along with the examples, let's populate this database with some test
data:

.. code-block:: python

    def populate_test_data():
        db.create_tables([User, Tweet, Favorite])

        data = (
            ('huey', ('meow', 'hiss', 'purr')),
            ('mickey', ('woof', 'whine')),
            ('zaizee', ()))
        for username, tweets in data:
            user = User.create(username=username)
            for tweet in tweets:
                Tweet.create(user=user, content=tweet)

        # Populate a few favorites for our users, such that:
        favorite_data = (
            ('huey', ['whine']),
            ('mickey', ['purr']),
            ('zaizee', ['meow', 'purr']))
        for username, favorites in favorite_data:
            user = User.get(User.username == username)
            for content in favorites:
                tweet = Tweet.get(Tweet.content == content)
                Favorite.create(user=user, tweet=tweet)

This gives us the following:

========= ========== ===========================
User      Tweet      Favorited by
========= ========== ===========================
huey      meow       zaizee
huey      hiss
huey      purr       mickey, zaizee
mickey    woof
mickey    whine      huey
========= ========== ===========================

.. attention::
    In the following examples we will be executing a number of queries. If you
    are unsure how many queries are being executed, you can add the following
    code, which will log all queries to the console:

    .. code-block:: python

        import logging
        logger = logging.getLogger('peewee')
        logger.addHandler(logging.StreamHandler())
        logger.setLevel(logging.DEBUG)

.. note::
    In SQLite, foreign keys are not enabled by default. Most things, including
    the Peewee foreign-key API, will work fine, but ON DELETE behaviour will be
    ignored, even if you explicitly specify ``on_delete`` in your
    :py:class:`ForeignKeyField`. In conjunction with the default
    :py:class:`AutoField` behaviour (where deleted record IDs can be reused),
    this can lead to subtle bugs. To avoid problems, I recommend that you
    enable foreign-key constraints when using SQLite, by setting
    ``pragmas={'foreign_keys': 1}`` when you instantiate :py:class:`SqliteDatabase`.

    .. code-block:: python

        # Ensure foreign-key constraints are enforced.
        db = SqliteDatabase('my_app.db', pragmas={'foreign_keys': 1})

Performing simple joins
-----------------------

As an exercise in learning how to perform joins with Peewee, let's write a
query to print out all the tweets by "huey". To do this we'll select from the
``Tweet`` model and join on the ``User`` model, so we can then filter on the
``User.username`` field:

.. code-block:: pycon

    >>> query = Tweet.select().join(User).where(User.username == 'huey')
    >>> for tweet in query:
    ...     print(tweet.content)
    ...
    meow
    hiss
    purr

.. note::
    We did not have to explicitly specify the join predicate (the "ON" clause),
    because Peewee inferred from the models that when we joined from Tweet to
    User, we were joining on the ``Tweet.user`` foreign-key.

    The following code is equivalent, but more explicit:

    .. code-block:: python

        query = (Tweet
                 .select()
                 .join(User, on=(Tweet.user == User.id))
                 .where(User.username == 'huey'))

If we already had a reference to the ``User`` object for "huey", we could use
the ``User.tweets`` back-reference to list all of huey's tweets:

.. code-block:: pycon

    >>> huey = User.get(User.username == 'huey')
    >>> for tweet in huey.tweets:
    ...     print(tweet.content)
    ...
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

Joining multiple tables
-----------------------

Let's take another look at joins by querying the list of users and getting the
count of how many tweet's they've authored that were favorited. This will
require us to join twice: from user to tweet, and from tweet to favorite. We'll
add the additional requirement that users should be included who have not
created any tweets, as well as users whose tweets have not been favorited. The
query, expressed in SQL, would be:

.. code-block:: sql

    SELECT user.username, COUNT(favorite.id)
    FROM user
    LEFT OUTER JOIN tweet ON tweet.user_id = user.id
    LEFT OUTER JOIN favorite ON favorite.tweet_id = tweet.id
    GROUP BY user.username

.. note::
    In the above query both joins are LEFT OUTER, since a user may not have any
    tweets or, if they have tweets, none of them may have been favorited.

Peewee has a concept of a *join context*, meaning that whenever we call the
:py:meth:`~ModelSelect.join` method, we are implicitly joining on the
previously-joined model (or if this is the first call, the model we are
selecting from). Since we are joining straight through, from user to tweet,
then from tweet to favorite, we can simply write:

.. code-block:: python

    query = (User
             .select(User.username, fn.COUNT(Favorite.id).alias('count'))
             .join(Tweet, JOIN.LEFT_OUTER)  # Joins user -> tweet.
             .join(Favorite, JOIN.LEFT_OUTER)  # Joins tweet -> favorite.
             .group_by(User.username))

Iterating over the results:

.. code-block:: pycon

    >>> for user in query:
    ...     print(user.username, user.count)
    ...
    huey 3
    mickey 1
    zaizee 0

For a more complicated example involving multiple joins and switching join
contexts, let's find all the tweets by Huey and the number of times they've
been favorited. To do this we'll need to perform two joins and we'll also use
an aggregate function to calculate the favorite count.

Here is how we would write this query in SQL:

.. code-block:: sql

    SELECT tweet.content, COUNT(favorite.id)
    FROM tweet
    INNER JOIN user ON tweet.user_id = user.id
    LEFT OUTER JOIN favorite ON favorite.tweet_id = tweet.id
    WHERE user.username = 'huey'
    GROUP BY tweet.content;

.. note::
    We use a LEFT OUTER join from tweet to favorite since a tweet may not have
    any favorites, yet we still wish to display it's content (along with a
    count of zero) in the result set.

With Peewee, the resulting Python code looks very similar to what we would
write in SQL:

.. code-block:: python

    query = (Tweet
             .select(Tweet.content, fn.COUNT(Favorite.id).alias('count'))
             .join(User)  # Join from tweet -> user.
             .switch(Tweet)  # Move "join context" back to tweet.
             .join(Favorite, JOIN.LEFT_OUTER)  # Join from tweet -> favorite.
             .where(User.username == 'huey')
             .group_by(Tweet.content))

Note the call to :py:meth:`~ModelSelect.switch` - that instructs Peewee to set
the *join context* back to ``Tweet``. If we had omitted the explicit call to
switch, Peewee would have used ``User`` (the last model we joined) as the join
context and constructed the join from User to Favorite using the
``Favorite.user`` foreign-key, which would have given us incorrect results.

If we wanted to omit the join-context switching we could instead use the
:py:meth:`~ModelSelect.join_from` method. The following query is equivalent to
the previous one:

.. code-block:: python

    query = (Tweet
             .select(Tweet.content, fn.COUNT(Favorite.id).alias('count'))
             .join_from(Tweet, User)  # Join tweet -> user.
             .join_from(Tweet, Favorite, JOIN.LEFT_OUTER)  # Join tweet -> favorite.
             .where(User.username == 'huey')
             .group_by(Tweet.content))

We can iterate over the results of the above query to print the tweet's content
and the favorite count:

.. code-block:: pycon

    >>> for tweet in query:
    ...     print('%s favorited %d times' % (tweet.content, tweet.count))
    ...
    meow favorited 1 times
    hiss favorited 0 times
    purr favorited 2 times

.. _multiple-sources:

Selecting from multiple sources
-------------------------------

If we wished to list all the tweets in the database, along with the username of
their author, you might try writing this:

.. code-block:: pycon

    >>> for tweet in Tweet.select():
    ...     print(tweet.user.username, '->', tweet.content)
    ...
    huey -> meow
    huey -> hiss
    huey -> purr
    mickey -> woof
    mickey -> whine

There is a big problem with the above loop: it executes an additional query for
every tweet to look up the ``tweet.user`` foreign-key. For our small table the
performance penalty isn't obvious, but we would find the delays grew as the
number of rows increased.

If you're familiar with SQL, you might remember that it's possible to SELECT
from multiple tables, allowing us to get the tweet content *and* the username
in a single query:

.. code-block:: sql

    SELECT tweet.content, user.username
    FROM tweet
    INNER JOIN user ON tweet.user_id = user.id;

Peewee makes this quite easy. In fact, we only need to modify our query a
little bit. We tell Peewee we wish to select ``Tweet.content`` as well as
the ``User.username`` field, then we include a join from tweet to user.
To make it a bit more obvious that it's doing the correct thing, we can ask
Peewee to return the rows as dictionaries.

.. code-block:: pycon

    >>> for row in Tweet.select(Tweet.content, User.username).join(User).dicts():
    ...     print(row)
    ...
    {'content': 'meow', 'username': 'huey'}
    {'content': 'hiss', 'username': 'huey'}
    {'content': 'purr', 'username': 'huey'}
    {'content': 'woof', 'username': 'mickey'}
    {'content': 'whine', 'username': 'mickey'}

Now we'll leave off the call to ".dicts()" and return the rows as ``Tweet``
objects. Notice that Peewee assigns the ``username`` value to
``tweet.user.username`` -- NOT ``tweet.username``!  Because there is a
foreign-key from tweet to user, and we have selected fields from both models,
Peewee will reconstruct the model-graph for us:

.. code-block:: pycon

    >>> for tweet in Tweet.select(Tweet.content, User.username).join(User):
    ...     print(tweet.user.username, '->', tweet.content)
    ...
    huey -> meow
    huey -> hiss
    huey -> purr
    mickey -> woof
    mickey -> whine

If we wish to, we can control where Peewee puts the joined ``User`` instance in
the above query, by specifying an ``attr`` in the ``join()`` method:

.. code-block:: pycon

    >>> query = Tweet.select(Tweet.content, User.username).join(User, attr='author')
    >>> for tweet in query:
    ...     print(tweet.author.username, '->', tweet.content)
    ...
    huey -> meow
    huey -> hiss
    huey -> purr
    mickey -> woof
    mickey -> whine

Conversely, if we simply wish *all* attributes we select to be attributes of
the ``Tweet`` instance, we can add a call to :py:meth:`~ModelSelect.objects` at
the end of our query (similar to how we called ``dicts()``):

.. code-block:: pycon

    >>> for tweet in query.objects():
    ...     print(tweet.username, '->', tweet.content)
    ...
    huey -> meow
    (etc)

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

With Peewee, we use :py:meth:`Model.alias` to alias a model class so it can be
referenced twice in a single query:

.. code-block:: python

    Owner = User.alias()
    query = (Favorite
             .select(Favorite, Tweet.content, User.username, Owner.username)
             .join(Owner)  # Join favorite -> user (owner of favorite).
             .switch(Favorite)
             .join(Tweet)  # Join favorite -> tweet
             .join(User))   # Join tweet -> user

We can iterate over the results and access the joined values in the following
way. Note how Peewee has resolved the fields from the various models we
selected and reconstructed the model graph:

.. code-block:: pycon

    >>> for fav in query:
    ...     print(fav.user.username, 'liked', fav.tweet.content, 'by', fav.tweet.user.username)
    ...
    huey liked whine by mickey
    mickey liked purr by huey
    zaizee liked meow by huey
    zaizee liked purr by huey

.. _join-subquery:

Subqueries
----------

Peewee allows you to join on any table-like object, including subqueries or
common table expressions (CTEs). To demonstrate joining on a subquery, let's
query for all users and their latest tweet.

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
             .join(latest_query, on=predicate)  # Join tweet -> subquery.
             .join_from(Tweet, User))  # Join from tweet -> user.

Iterating over the query, we can see each user and their latest tweet.

.. code-block:: pycon

    >>> for tweet in query:
    ...     print(tweet.user.username, '->', tweet.content)
    ...
    huey -> purr
    mickey -> whine

There are a couple things you may not have seen before in the code we used to
create the query in this section:

* We used :py:meth:`~ModelSelect.join_from` to explicitly specify the join
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

.. code-block:: pycon

    >>> for tweet in query:
    ...     print(tweet.user.username, '->', tweet.content)
    ...
    huey -> purr
    mickey -> whine

.. note::
    For more information about using CTEs, including information on writing
    recursive CTEs, see the :ref:`cte` section of the "Querying" document.

Multiple foreign-keys to the same Model
---------------------------------------

When there are multiple foreign keys to the same model, it is good practice to
explicitly specify which field you are joining on.

Referring back to the :ref:`example app's models <example-app-models>`,
consider the *Relationship* model, which is used to denote when one user
follows another. Here is the model definition:

.. code-block:: python

    class Relationship(BaseModel):
        from_user = ForeignKeyField(User, backref='relationships')
        to_user = ForeignKeyField(User, backref='related_to')

        class Meta:
            indexes = (
                # Specify a unique multi-column index on from/to-user.
                (('from_user', 'to_user'), True),
            )

Since there are two foreign keys to *User*, we should always specify which
field we are using in a join.

For example, to determine which users I am following, I would write:

.. code-block:: python

    (User
     .select()
     .join(Relationship, on=Relationship.to_user)
     .where(Relationship.from_user == charlie))

On the other hand, if I wanted to determine which users are following me, I
would instead join on the *from_user* column and filter on the relationship's
*to_user*:

.. code-block:: python

    (User
     .select()
     .join(Relationship, on=Relationship.from_user)
     .where(Relationship.to_user == charlie))

Joining on arbitrary fields
---------------------------

If a foreign key does not exist between two tables you can still perform a
join, but you must manually specify the join predicate.

In the following example, there is no explicit foreign-key between *User* and
*ActivityLog*, but there is an implied relationship between the
*ActivityLog.object_id* field and *User.id*. Rather than joining on a specific
:py:class:`Field`, we will join using an :py:class:`Expression`.

.. code-block:: python

    user_log = (User
                .select(User, ActivityLog)
                .join(ActivityLog, on=(User.id == ActivityLog.object_id), attr='log')
                .where(
                    (ActivityLog.activity_type == 'user_activity') &
                    (User.username == 'charlie')))

    for user in user_log:
        print(user.username, user.log.description)

    #### Print something like ####
    charlie logged in
    charlie posted a tweet
    charlie retweeted
    charlie posted a tweet
    charlie logged out

.. note::
    Recall that we can control the attribute Peewee will assign the joined
    instance to by specifying the ``attr`` parameter in the ``join()`` method.
    In the previous example, we used the following *join*:

    .. code-block:: python

        join(ActivityLog, on=(User.id == ActivityLog.object_id), attr='log')

    Then when iterating over the query, we were able to directly access the
    joined *ActivityLog* without incurring an additional query:

    .. code-block:: python

        for user in user_log:
            print(user.username, user.log.description)

Self-joins
----------

Peewee supports constructing queries containing a self-join.

Using model aliases
^^^^^^^^^^^^^^^^^^^

To join on the same model (table) twice, it is necessary to create a model
alias to represent the second instance of the table in a query. Consider the
following model:

.. code-block:: python

    class Category(Model):
        name = CharField()
        parent = ForeignKeyField('self', backref='children')

What if we wanted to query all categories whose parent category is
*Electronics*. One way would be to perform a self-join:

.. code-block:: python

    Parent = Category.alias()
    query = (Category
             .select()
             .join(Parent, on=(Category.parent == Parent.id))
             .where(Parent.name == 'Electronics'))

When performing a join that uses a :py:class:`ModelAlias`, it is necessary to
specify the join condition using the ``on`` keyword argument. In this case we
are joining the category with its parent category.

Using subqueries
^^^^^^^^^^^^^^^^

Another less common approach involves the use of subqueries. Here is another
way we might construct a query to get all the categories whose parent category
is *Electronics* using a subquery:

.. code-block:: python

    Parent = Category.alias()
    join_query = Parent.select().where(Parent.name == 'Electronics')

    # Subqueries used as JOINs need to have an alias.
    join_query = join_query.alias('jq')

    query = (Category
             .select()
             .join(join_query, on=(Category.parent == join_query.c.id)))

This will generate the following SQL query:

.. code-block:: sql

    SELECT t1."id", t1."name", t1."parent_id"
    FROM "category" AS t1
    INNER JOIN (
      SELECT t2."id"
      FROM "category" AS t2
      WHERE (t2."name" = ?)) AS jq ON (t1."parent_id" = "jq"."id")

To access the ``id`` value from the subquery, we use the ``.c`` magic lookup
which will generate the appropriate SQL expression:

.. code-block:: python

    Category.parent == join_query.c.id
    # Becomes: (t1."parent_id" = "jq"."id")

.. _manytomany:

Implementing Many to Many
-------------------------

Peewee provides a field for representing many-to-many relationships, much like
Django does. This feature was added due to many requests from users, but I
strongly advocate against using it, since it conflates the idea of a field with
a junction table and hidden joins. It's just a nasty hack to provide convenient
accessors.

To implement many-to-many **correctly** with peewee, you will therefore create
the intermediary table yourself and query through it:

.. code-block:: python

    class Student(Model):
        name = CharField()

    class Course(Model):
        name = CharField()

    class StudentCourse(Model):
        student = ForeignKeyField(Student)
        course = ForeignKeyField(Course)

To query, let's say we want to find students who are enrolled in math class:

.. code-block:: python

    query = (Student
             .select()
             .join(StudentCourse)
             .join(Course)
             .where(Course.name == 'math'))
    for student in query:
        print(student.name)

To query what classes a given student is enrolled in:

.. code-block:: python

    courses = (Course
               .select()
               .join(StudentCourse)
               .join(Student)
               .where(Student.name == 'da vinci'))

    for course in courses:
        print(course.name)

To efficiently iterate over a many-to-many relation, i.e., list all students
and their respective courses, we will query the *through* model
``StudentCourse`` and *precompute* the Student and Course:

.. code-block:: python

    query = (StudentCourse
             .select(StudentCourse, Student, Course)
             .join(Course)
             .switch(StudentCourse)
             .join(Student)
             .order_by(Student.name))

To print a list of students and their courses you might do the following:

.. code-block:: python

    for student_course in query:
        print(student_course.student.name, '->', student_course.course.name)

Since we selected all fields from ``Student`` and ``Course`` in the *select*
clause of the query, these foreign key traversals are "free" and we've done the
whole iteration with just 1 query.

ManyToManyField
^^^^^^^^^^^^^^^

The :py:class:`ManyToManyField` provides a *field-like* API over many-to-many
fields. For all but the simplest many-to-many situations, you're better off
using the standard peewee APIs. But, if your models are very simple and your
querying needs are not very complex, :py:class:`ManyToManyField` may work.

Modeling students and courses using :py:class:`ManyToManyField`:

.. code-block:: python

    from peewee import *
    
    db = SqliteDatabase('school.db')

    class BaseModel(Model):
        class Meta:
            database = db

    class Student(BaseModel):
        name = CharField()

    class Course(BaseModel):
        name = CharField()
        students = ManyToManyField(Student, backref='courses')

    StudentCourse = Course.students.get_through_model()

    db.create_tables([
        Student,
        Course,
        StudentCourse])

    # Get all classes that "huey" is enrolled in:
    huey = Student.get(Student.name == 'Huey')
    for course in huey.courses.order_by(Course.name):
        print(course.name)

    # Get all students in "English 101":
    engl_101 = Course.get(Course.name == 'English 101')
    for student in engl_101.students:
        print(student.name)

    # When adding objects to a many-to-many relationship, we can pass
    # in either a single model instance, a list of models, or even a
    # query of models:
    huey.courses.add(Course.select().where(Course.name.contains('English')))

    engl_101.students.add(Student.get(Student.name == 'Mickey'))
    engl_101.students.add([
        Student.get(Student.name == 'Charlie'),
        Student.get(Student.name == 'Zaizee')])

    # The same rules apply for removing items from a many-to-many:
    huey.courses.remove(Course.select().where(Course.name.startswith('CS')))

    engl_101.students.remove(huey)

    # Calling .clear() will remove all associated objects:
    cs_150.students.clear()

.. attention::
    Before many-to-many relationships can be added, the objects being
    referenced will need to be saved first. In order to create relationships in
    the many-to-many through table, Peewee needs to know the primary keys of
    the models being referenced.

.. warning::
    It is **strongly recommended** that you do not attempt to subclass models
    containing :py:class:`ManyToManyField` instances.

    A :py:class:`ManyToManyField`, despite its name, is not a field in the
    usual sense. Instead of being a column on a table, the many-to-many field
    covers the fact that behind-the-scenes there's actually a separate table
    with two foreign-key pointers (the *through table*).

    Therefore, when a subclass is created that inherits a many-to-many field,
    what actually needs to be inherited is the *through table*. Because of the
    potential for subtle bugs, Peewee does not attempt to automatically
    subclass the through model and modify its foreign-key pointers. As a
    result, many-to-many fields typically will not work with inheritance.

For more examples, see:

* :py:meth:`ManyToManyField.add`
* :py:meth:`ManyToManyField.remove`
* :py:meth:`ManyToManyField.clear`
* :py:meth:`ManyToManyField.get_through_model`

.. _nplusone:

Avoiding the N+1 problem
------------------------

The *N+1 problem* refers to a situation where an application performs a query,
then for each row of the result set, the application performs at least one
other query (another way to conceptualize this is as a nested loop). In many
cases, these *n* queries can be avoided through the use of a SQL join or
subquery. The database itself may do a nested loop, but it will usually be more
performant than doing *n* queries in your application code, which involves
latency communicating with the database and may not take advantage of indices
or other optimizations employed by the database when joining or executing a
subquery.

Peewee provides several APIs for mitigating *N+1* query behavior. Recollecting
the models used throughout this document, *User* and *Tweet*, this section will
try to outline some common *N+1* scenarios, and how peewee can help you avoid
them.

.. attention::
    In some cases, N+1 queries will not result in a significant or measurable
    performance hit. It all depends on the data you are querying, the database
    you are using, and the latency involved in executing queries and retrieving
    results. As always when making optimizations, profile before and after to
    ensure the changes do what you expect them to.

List recent tweets
^^^^^^^^^^^^^^^^^^

The twitter timeline displays a list of tweets from multiple users. In addition
to the tweet's content, the username of the tweet's author is also displayed.
The N+1 scenario here would be:

1. Fetch the 10 most recent tweets.
2. For each tweet, select the author (10 queries).

By selecting both tables and using a *join*, peewee makes it possible to
accomplish this in a single query:

.. code-block:: python

    query = (Tweet
             .select(Tweet, User)  # Note that we are selecting both models.
             .join(User)  # Use an INNER join because every tweet has an author.
             .order_by(Tweet.id.desc())  # Get the most recent tweets.
             .limit(10))

    for tweet in query:
        print(tweet.user.username, '-', tweet.message)

Without the join, accessing ``tweet.user.username`` would trigger a query to
resolve the foreign key ``tweet.user`` and retrieve the associated user. But
since we have selected and joined on ``User``, peewee will automatically
resolve the foreign-key for us.

.. note::
    This technique is discussed in more detail in :ref:`multiple-sources`.

List users and all their tweets
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let's say you want to build a page that shows several users and all of their
tweets. The N+1 scenario would be:

1. Fetch some users.
2. For each user, fetch their tweets.

This situation is similar to the previous example, but there is one important
difference: when we selected tweets, they only have a single associated user,
so we could directly assign the foreign key. The reverse is not true, however,
as one user may have any number of tweets (or none at all).

Peewee provides an approach to avoiding *O(n)* queries in this situation. Fetch
users first, then fetch all the tweets associated with those users.  Once
peewee has the big list of tweets, it will assign them out, matching them with
the appropriate user. This method is usually faster but will involve a query
for each table being selected.

.. _prefetch:

Using prefetch
^^^^^^^^^^^^^^

peewee supports pre-fetching related data using sub-queries. This method
requires the use of a special API, :py:func:`prefetch`. Prefetch, as its name
implies, will eagerly load the appropriate tweets for the given users using
subqueries. This means instead of *O(n)* queries for *n* rows, we will do
*O(k)* queries for *k* tables.

Here is an example of how we might fetch several users and any tweets they
created within the past week.

.. code-block:: python

    week_ago = datetime.date.today() - datetime.timedelta(days=7)
    users = User.select()
    tweets = (Tweet
              .select()
              .where(Tweet.timestamp >= week_ago))

    # This will perform two queries.
    users_with_tweets = prefetch(users, tweets)

    for user in users_with_tweets:
        print(user.username)
        for tweet in user.tweets:
            print('  ', tweet.message)

.. note::
    Note that neither the ``User`` query, nor the ``Tweet`` query contained a
    JOIN clause. When using :py:func:`prefetch` you do not need to specify the
    join.

:py:func:`prefetch` can be used to query an arbitrary number of tables. Check
the API documentation for more examples.

Some things to consider when using :py:func:`prefetch`:

* Foreign keys must exist between the models being prefetched.
* `LIMIT` works as you'd expect on the outer-most query, but may be difficult
  to implement correctly if trying to limit the size of the sub-selects.
