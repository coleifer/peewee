Peewee Cookbook
===============

Below are outlined some of the ways to perform typical database-related tasks
with peewee.

Examples will use the following models:

.. code-block:: python
    
    import peewee

    class Blog(peewee.Model):
        creator = peewee.CharField()
        name = peewee.CharField()


    class Entry(peewee.Model):
        blog = peewee.ForeignKeyField(Blog)
        title = peewee.CharField()
        body = peewee.TextField()
        pub_date = peewee.DateTimeField()
        published = peewee.BooleanField(default=True)


Database and Connection Recipes
-------------------------------

Creating a database connection and tables
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

While it is not necessary to explicitly connect to the database before using it,
managing connections explicitly is a good practice.  This way if the connection
fails, the exception can be caught during the "connect" step, rather than some
arbitrary time later when a query is executed.

.. code-block:: python

    >>> database = SqliteDatabase('stats.db')
    >>> database.connect()


It is possible to use multiple databases (provided that you don't try and mix
models from each):

.. code-block:: python

    >>> custom_db = peewee.SqliteDatabase('custom.db')
    
    >>> class CustomModel(peewee.Model):
    ...     whatev = peewee.CharField()
    ...     
    ...     class Meta:
    ...         database = custom_db
    ... 
    
    >>> custom_db.connect()
    >>> CustomModel.create_table()


**Best practice:** define a base model class that points at the database object
you wish to use, and then all your models will extend it:

.. code-block:: python

    custom_db = peewee.SqliteDatabase('custom.db')
    
    class CustomModel(peewee.Model):
        class Meta:
            database = custom_db
    
    class Blog(CustomModel):
        creator = peewee.CharField()
        name = peewee.TextField()
    
    class Entry(CustomModel):
        # etc, etc


Using with Postgresql
^^^^^^^^^^^^^^^^^^^^^

Point models at an instance of :py:class:`PostgresqlDatabase`.

.. code-block:: python

    psql_db = peewee.PostgresqlDatabase('my_database', user='code')
    

    class PostgresqlModel(peewee.Model):
        """A base model that will use our MySQL database"""
        class Meta:
            database = psql_db

    class Blog(PostgresqlModel):
        creator = peewee.CharField()
        # etc, etc


Using with MySQL
^^^^^^^^^^^^^^^^

Point models at an instance of :py:class:`MySQLDatabase`.

.. code-block:: python

    mysql_db = peewee.MySQLDatabase('my_database', user='code')
    

    class MySQLModel(peewee.Model):
        """A base model that will use our MySQL database"""
        class Meta:
            database = mysql_db

    class Blog(MySQLModel):
        creator = peewee.CharField()
        # etc, etc
    

    # when you're ready to start querying, remember to connect
    mysql_db.connect()


Multi-threaded applications
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Some database engines may not allow a connection to be shared across threads, notably
sqlite.  If you would like peewee to maintain a single connection per-thread,
instantiate your database with ``threadlocals=True``:

.. code-block:: python

    concurrent_db = SqliteDatabase('stats.db', threadlocals=True)


Creating, Reading, Updating and Deleting
----------------------------------------

Creating a new record
^^^^^^^^^^^^^^^^^^^^^

You can use the :py:meth:`Model.create` method on the model:

.. code-block:: python

    >>> Blog.create(creator='Charlie', name='My Blog')
    <__main__.Blog object at 0x2529350>

This will ``INSERT`` a new row into the database.  The primary key will automatically
be retrieved and stored on the model instance.

Alternatively, you can build up a model instance programmatically and then
save it:

.. code-block:: python

    >>> blog = Blog()
    >>> blog.creator = 'Chuck'
    >>> blog.name = 'Another blog'
    >>> blog.save()
    >>> blog.id
    2


Updating existing records
^^^^^^^^^^^^^^^^^^^^^^^^^

Once a model instance has a primary key, any attempt to re-save it will result
in an ``UPDATE`` rather than another ``INSERT``:

.. code-block:: python

    >>> blog.save()
    >>> blog.id
    2
    >>> blog.save()
    >>> blog.id
    2

If you want to update multiple records, issue an ``UPDATE`` query.  The following
example will update all ``Entry`` objects, marking them as "published", if their
pub_date is less than today's date.

.. code-block:: python

    >>> update_query = Entry.update(published=True).where(pub_date__lt=datetime.today())
    >>> update_query.execute()
    4 # <--- number of rows updated

For more information, see the documentation on :py:class:`UpdateQuery`.


Deleting a record
^^^^^^^^^^^^^^^^^

To delete a single model instance, you can use the :py:meth:`Model.delete_instance`
shortcut:

    >>> blog = Blog.get(id=1)
    >>> blog.delete_instance()
    1 # <--- number of rows deleted

    >>> Blog.get(id=1)
    BlogDoesNotExist: instance matching query does not exist:
    SQL: SELECT "id", "creator", "name" FROM "blog" WHERE "id" = ? LIMIT 1
    PARAMS: [1]

To delete an arbitrary group of records, you can issue a ``DELETE`` query.  The
following will delete all ``Entry`` objects that are a year old.

    >>> delete_query = Entry.delete().where(pub_date__lt=one_year_ago)
    >>> delete_query.execute()
    7 # <--- number of entries deleted

For more information, see the documentation on :py:class:`DeleteQuery`.


Selecting a single record
^^^^^^^^^^^^^^^^^^^^^^^^^

You can use the :py:meth:`Model.get` method to retrieve a single instance matching
the given query (passed in as a mix of :py:class:`Q` objects and keyword arguments).

This method is a shortcut that calls :py:meth:`Model.select` with the given query,
but limits the result set to 1.  Additionally, if no model matches the given query,
a ``DoesNotExist`` exception will be raised.

.. code-block:: python

    >>> Blog.get(id=1)
    <__main__.Blog object at 0x25294d0>

    >>> Blog.get(id=1).name
    u'My Blog'

    >>> Blog.get(creator='Chuck')
    <__main__.Blog object at 0x2529410>

    >>> Blog.get(id=1000)
    BlogDoesNotExist: instance matching query does not exist:
    SQL: SELECT "id", "creator", "name" FROM "blog" WHERE "id" = ? LIMIT 1
    PARAMS: [1000]

For more information see notes on :py:class:`SelectQuery` and :ref:`querying` in general.


Selecting multiple records
^^^^^^^^^^^^^^^^^^^^^^^^^^

To simply get all instances in a table, call the :py:meth:`Model.select` method:

.. code-block:: python

    >>> for blog in Blog.select():
    ...     print blog.name
    ... 
    My Blog
    Another blog

When you iterate over a :py:class:`SelectQuery`, it will automatically execute
it and start returning results from the database cursor.  Subsequent iterations
of the same query will not hit the database as the results are cached.

Another useful note is that you can retrieve instances related by :py:class:`ForeignKeyField`
by iterating.  To get all the related instances for an object, you can query the related name.
Looking at the example models, we have Blogs and Entries.  Entry has a foreign key to Blog,
meaning that any given blog may have 0..n entries.  A blog's related entries are exposed
using a :py:class:`SelectQuery`, and can be iterated the same as any other SelectQuery:

.. code-block:: python

    >>> for entry in blog.entry_set:
    ...     print entry.title
    ... 
    entry 1
    entry 2
    entry 3
    entry 4

The ``entry_set`` attribute is just another select query and any methods available
to :py:class:`SelectQuery` are available:

    >>> for entry in blog.entry_set.order_by(('pub_date', 'desc')):
    ...     print entry.title
    ...
    entry 4
    entry 3
    entry 2
    entry 1


Filtering records
^^^^^^^^^^^^^^^^^

.. code-block:: python

    >>> for entry in Entry.select().where(blog=blog, published=True):
    ...     print '%s: %s (%s)' % (entry.blog.name, entry.title, entry.published)
    ... 
    My Blog: Some Entry (True)
    My Blog: Another Entry (True)

    >>> for entry in Entry.select().where(pub_date__lt=datetime.datetime(2011, 1, 1)):
    ...     print entry.title, entry.pub_date
    ... 
    Old entry 2010-01-01 00:00:00

You can also filter across joins:

.. code-block:: python

    >>> for entry in Entry.select().join(Blog).where(name='My Blog'):
    ...     print entry.title
    Old entry
    Some Entry
    Another Entry

If you are already familiar with Django's ORM, you can use the "double underscore"
syntax:

.. code-block:: python

    >>> for entry in Entry.filter(blog__name='My Blog'):
    ...     print entry.title
    Old entry
    Some Entry
    Another Entry

To perform OR lookups, use the special :py:class:`Q` object.  These work in
both calls to ``filter()`` and ``where()``:

.. code-block:: python

    >>> User.filter(Q(staff=True) | Q(superuser=True)) # get staff or superusers

To perform lookups against *another column* in a given row, use the :py:class:`F` object:

.. code-block:: python

    >>> Employee.filter(salary__lt=F('desired_salary'))


Sorting records
^^^^^^^^^^^^^^^

.. code-block:: python

    >>> for e in Entry.select().order_by('pub_date'):
    ...     print e.pub_date
    ... 
    2010-01-01 00:00:00
    2011-06-07 14:08:48
    2011-06-07 14:12:57

    >>> for e in Entry.select().order_by(peewee.desc('pub_date')):
    ...     print e.pub_date
    ... 
    2011-06-07 14:12:57
    2011-06-07 14:08:48
    2010-01-01 00:00:00

You can also order across joins.  Assuming you want
to order entries by the name of the blog, then by pubdate desc:

.. code-block:: python

    >>> qry = Entry.select().join(Blog).order_by(
    ...     (Blog, 'name'),
    ...     (Entry, 'pub_date', 'DESC'),
    ... )
    
    >>> qry.sql()
    ('SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id ORDER BY t2.name ASC, t1.pub_date DESC', [])


Paginating records
^^^^^^^^^^^^^^^^^^

The paginate method makes it easy to grab a "page" or records -- it takes two
parameters, `page_number`, and `items_per_page`:

.. code-block:: python

    >>> for entry in Entry.select().order_by('id').paginate(2, 10):
    ...     print entry.title
    ... 
    entry 10
    entry 11
    entry 12
    entry 13
    entry 14
    entry 15
    entry 16
    entry 17
    entry 18
    entry 19


Counting records
^^^^^^^^^^^^^^^^

You can count the number of rows in any select query:

.. code-block:: python

    >>> Entry.select().count()
    100
    >>> Entry.select().where(id__gt=50).count()
    50


Performing atomic updates
^^^^^^^^^^^^^^^^^^^^^^^^^

Use the special :py:class:`F` object to perform an atomic update:

.. code-block:: python

    >>> MessageCount.update(count=F('count') + 1).where(user=some_user)


Aggregating records
^^^^^^^^^^^^^^^^^^^

Suppose you have some blogs and want to get a list of them along with the count
of entries in each.  First I will show you the shortcut:

.. code-block:: python

    query = Blog.select().annotate(Entry)

This is equivalent to the following:

.. code-block:: python

    query = Blog.select({
        Blog: ['*'],
        Entry: [Count('id')],
    }).group_by(Blog).join(Entry)

The resulting query will return Blog objects with all their normal attributes
plus an additional attribute 'count' which will contain the number of entries.
By default it uses an inner join if the foreign key is not nullable, which means
blogs without entries won't appear in the list.  To remedy this, manually specify
the type of join to include blogs with 0 entries:

.. code-block:: python

    query = Blog.select().join(Entry, 'left outer').annotate(Entry)

You can also specify a custom aggregator:

.. code-block:: python

    query = Blog.select().annotate(Entry, peewee.Max('pub_date', 'max_pub_date'))

Let's assume you have a tagging application and want to find tags that have a
certain number of related objects.  For this example we'll use some different
models in a Many-To-Many configuration:

.. code-block:: python

    class Photo(Model):
        image = CharField()
    
    class Tag(Model):
        name = CharField()
    
    class PhotoTag(Model):
        photo = ForeignKeyField(Photo)
        tag = ForeignKeyField(Tag)
    
Now say we want to find tags that have at least 5 photos associated with them:

.. code-block:: python

    >>> Tag.select().join(PhotoTag).join(Photo).group_by(Tag).having('count(*) > 5').sql()
    
    SELECT t1."id", t1."name"
    FROM "tag" AS t1 
    INNER JOIN "phototag" AS t2 
        ON t1."id" = t2."tag_id"
    INNER JOIN "photo" AS t3
        ON t2."photo_id" = t3."id"
    GROUP BY 
        t1."id", t1."name"
    HAVING count(*) > 5

Suppose we want to grab the associated count and store it on the tag:

.. code-block:: python

    >>> Tag.select({
    ...     Tag: ['*'],
    ...     Photo: [Count('id', 'count')]
    ... }).join(PhotoTag).join(Photo).group_by(Tag).having('count(*) > 5').sql()
    
    SELECT t1."id", t1."name", COUNT(t3."id") AS count
    FROM "tag" AS t1 
    INNER JOIN "phototag" AS t2 
        ON t1."id" = t2."tag_id"
    INNER JOIN "photo" AS t3
        ON t2."photo_id" = t3."id"
    GROUP BY 
        t1."id", t1."name"
    HAVING count(*) > 5
