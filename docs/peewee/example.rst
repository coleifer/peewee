Example app
===========

.. image:: tweepee.jpg

peewee ships with an example web app that runs on the 
`Flask <http://flask.pocoo.org/>`_ microframework.  If you already have flask
and its dependencies installed you should be good to go, otherwise install from
the included requirements file::

    cd example/
    pip install -r requirements.txt


Running the example
-------------------

After ensuring that flask, jinja2, werkzeug and sqlite3 are all installed,
switch to the example directory and execute the *run_example.py* script::

    python run_example.py


Diving into the code
--------------------

Models
^^^^^^

In the spirit of the ur-python framework, django, peewee uses declarative model 
definitions.  If you're not familiar with django, the idea is that you declare
a class with some members which map directly to the database schema.  For the 
twitter clone, there are just three models:

User:
    represents a user account and stores the username and password, an email
    address for generating avatars using *gravatar*, and a datetime field 
    indicating when that account was created

Relationship:
    this is a "utility model" that contains two foreign-keys to
    the User model and represents *"following"*.

Message:
    analagous to a tweet. this model stores the text content of
    the message, when it was created, and who posted it (foreign key to User).

If you like UML, this is basically what it looks like:

.. image:: schema.jpg


Here is the code::

    database = peewee.Database(peewee.SqliteAdapter(), DATABASE)

    # model definitions
    class User(peewee.Model):
        username = peewee.CharField()
        password = peewee.CharField()
        email = peewee.CharField()
        join_date = peewee.DateTimeField()

        class Meta:
            database = database

        def following(self):
            return User.select().join(
                Relationship, on='to_user_id'
            ).where(from_user=self).order_by('username')

        def followers(self):
            return User.select().join(
                Relationship
            ).where(to_user=self).order_by('username')

        def is_following(self, user):
            return Relationship.select().where(
                from_user=self,
                to_user=user
            ).count() > 0

        def gravatar_url(self, size=80):
            return 'http://www.gravatar.com/avatar/%s?d=identicon&s=%d' % \
                (md5(self.email.strip().lower().encode('utf-8')).hexdigest(), size)


    class Relationship(peewee.Model):
        from_user = peewee.ForeignKeyField(User, related_name='relationships')
        to_user = peewee.ForeignKeyField(User, related_name='related_to')

        class Meta:
            database = database


    class Message(peewee.Model):
        user = peewee.ForeignKeyField(User)
        content = peewee.TextField()
        pub_date = peewee.DateTimeField()

        class Meta:
            database = database


peewee supports a handful of field types which map to different column types in
sqlite.  Conversion between python and the database is handled transparently,
including the proper handling of None/NULL.

.. note:: you might have noticed that each model sets the database attribute 
    explicitly.  by default peewee will use "peewee.db". explicitly setting this
    instructs peewee to use the database specified by ``DATABASE`` (tweepee.db).


Creating the initial tables
^^^^^^^^^^^^^^^^^^^^^^^^^^^

In order to start using the models, its necessary to create the tables.  This is
a one-time operation and can be done quickly using the interactive interpreter::

    >>> from app import *
    >>> create_tables()

The ``create_tables()`` method is defined in the app module and looks like this::

    def create_tables():
        database.connect() # <-- note the explicit call to connect()
        User.create_table()
        Relationship.create_table()
        Message.create_table()

Every model has a ``create_table()`` classmethod which runs a ``CREATE TABLE``
statement in the database.  Usually this is something you'll only do once,
whenever a new model is added.

.. note:: adding fields after the table has been created will required you to
    either drop the table and re-create it or manually add the columns using
    ``ALTER TABLE``.


Connecting to the database
^^^^^^^^^^^^^^^^^^^^^^^^^^

You may have noticed in the above model code that there is a class defined
within each model named ``Meta`` that sets the ``database`` attribute.  peewee
allows every model to specify which database it uses, defaulting to "peewee.db",
but since you probably want a bit more control, you can instantiate your own
database and point your models at it::

    # config
    DATABASE = 'tweepee.db'

    # ... more config here, omitted

    database = peewee.Database(peewee.SqliteAdapter(), DATABASE) # tell our models to use "tweepee.db"

Because sqlite likes to have a separate connection per-thread, we will tell 
flask that during the request/response cycle we need to create a connection to 
the database.  Flask provides some handy decorators to make this a snap::

    @app.before_request
    def before_request():
        g.db = database
        g.db.connect()

    @app.after_request
    def after_request(response):
        g.db.close()
        return response

Note that we're storing the db on the magical variable ``g`` - that's a 
flask-ism and can be ignored as an implementation detail.  The meat of this code
is in the idea that we connect to our db every request and close that connection
every response.  Django does the `exact same thing <http://code.djangoproject.com/browser/django/tags/releases/1.2.3/django/db/__init__.py#L80>`_.


Doing queries
^^^^^^^^^^^^^

In the ``User`` model there are a few instance methods that encapsulate some 
user-specific functionality, i.e.

* ``following()``: who is this user following?
* ``followers()``: who is following this user?

These methods are rather similar in their implementation but with one key 
difference::

    def following(self):
        return User.select().join(
            Relationship, on='to_user_id'
        ).where(from_user=self).order_by('username')

    def followers(self):
        return User.select().join(
            Relationship
        ).where(to_user=self).order_by('username')

.. note: the ``following()`` method specifies an extra bit of metadata,
    ``on='to_user_id'``.  because there are two foreign keys to ``User``, peewee
    will automatically assume the first one, which happens to be ``from_user``.


Specifying the foreign key manually instructs peewee to join on the ``to_user_id`` field.
the queries end up looking like::

    # following:
    SELECT t1.* 
    FROM user AS t1 
    INNER JOIN relationship AS t2 
        ON t1.id = t2.to_user_id  # <-- joining on to_user_id
    WHERE t2.from_user_id = ? 
    ORDER BY username ASC
    
    # followers
    SELECT t1.* 
    FROM user AS t1 
    INNER JOIN relationship AS t2 
        ON t1.id = t2.from_user_id # <-- joining on from_user_id
    WHERE t2.to_user_id = ? 
    ORDER BY username ASC


Creating new objects
^^^^^^^^^^^^^^^^^^^^

So what happens when a new user wants to join the site?  Looking at the 
business end of the ``join()`` view, we can that it does a quick check to see
if the username is taken, and if not executes a ``.create()``::

    try:
        user = User.get(username=request.form['username'])
        flash('That username is already taken')
    except StopIteration:
        user = User.create(
            username=request.form['username'],
            password=md5(request.form['password']).hexdigest(),
            email=request.form['email'],
            join_date=datetime.datetime.now()
        )

Much like the ``create()`` method, all models come with a built-in method called
``get_or_create`` which is used when one user follows another::

    Relationship.get_or_create(
        from_user=session['user'], # <-- the logged-in user
        to_user=user, # <-- the user they want to follow
    )


Doing subqueries
^^^^^^^^^^^^^^^^

If you are logged-in and visit the twitter homepage, you will see tweets from 
the users that you follow.  In order to implement this, it is necessary to do
a subquery::

    >>> qr = Message.select().where(user__in=some_user.following())
    >>> print qr.sql()[0] # formatting cleaned up for readability
    SELECT * 
    FROM message 
    WHERE user_id IN (
        SELECT t1.id 
        FROM user AS t1 
        INNER JOIN relationship AS t2 
            ON t1.id = t2.to_user_id 
        WHERE t2.from_user_id = ? 
        ORDER BY username ASC
    )

peewee supports doing subqueries on any ``ForeignKeyField`` or 
``PrimaryKeyField``.
