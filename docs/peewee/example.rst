.. _example-app:

Example app
===========

.. image:: tweepee.jpg

peewee ships with an example web app that runs on the 
`Flask <http://flask.pocoo.org/>`_ microframework.  If you already have flask
and its dependencies installed you should be good to go, otherwise install from
the included requirements file.

.. code-block:: console

    cd example/
    pip install -r requirements.txt


Running the example
-------------------

After ensuring that flask, jinja2, werkzeug and sqlite3 are all installed,
switch to the example directory and execute the *run_example.py* script:

.. code-block:: console

    python run_example.py


Diving into the code
--------------------

Models
^^^^^^

In the spirit of the ur-python framework, django, peewee uses declarative model 
definitions.  If you're not familiar with django, the idea is that you declare
a class with some members which map directly to the database schema.  For the 
twitter clone, there are just three models:

``User``:
    represents a user account and stores the username and password, an email
    address for generating avatars using *gravatar*, and a datetime field 
    indicating when that account was created

``Relationship``:
    this is a "utility model" that contains two foreign-keys to
    the ``User`` model and represents *"following"*.

``Message``:
    analagous to a tweet. this model stores the text content of
    the message, when it was created, and who posted it (foreign key to User).

If you like UML, this is basically what it looks like:

.. image:: schema.jpg


Here is what the code looks like:

.. code-block:: python

    database = SqliteDatabase(DATABASE)

    # model definitions
    class BaseModel(Model):
        class Meta:
            database = database
        
    class User(BaseModel):
        username = CharField()
        password = CharField()
        email = CharField()
        join_date = DateTimeField()

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


    class Relationship(BaseModel):
        from_user = ForeignKeyField(User, related_name='relationships')
        to_user = ForeignKeyField(User, related_name='related_to')


    class Message(BaseModel):
        user = ForeignKeyField(User)
        content = TextField()
        pub_date = DateTimeField()


peewee supports a handful of field types which map to different column types in
sqlite.  Conversion between python and the database is handled transparently,
including the proper handling of ``None``/``NULL``.

.. note::
    You might have noticed that we created a ``BaseModel`` which sets the
    database, and then all the other models extend the ``BaseModel``.  This is
    a good way to make sure all your models are talking to the right database.


Creating the initial tables
^^^^^^^^^^^^^^^^^^^^^^^^^^^

In order to start using the models, its necessary to create the tables.  This is
a one-time operation and can be done quickly using the interactive interpreter.

Open a python shell in the directory alongside the example app and execute the
following:

.. code-block:: python

    >>> from app import *
    >>> create_tables()

The ``create_tables()`` method is defined in the app module and looks like this:

.. code-block:: python

    def create_tables():
        User.create_table()
        Relationship.create_table()
        Message.create_table()

Every model has a :py:meth:`~Model.create_table` classmethod which runs a ``CREATE TABLE``
statement in the database.  Usually this is something you'll only do once,
whenever a new model is added.

.. note::
    Adding fields after the table has been created will required you to
    either drop the table and re-create it or manually add the columns using ``ALTER TABLE``.

.. note::
    If you want, you can use instead write ``User.create_table(True)`` and it will
    fail silently if the table already exists.

Connecting to the database
^^^^^^^^^^^^^^^^^^^^^^^^^^

You may have noticed in the above model code that there is a class defined on the
base model named ``Meta`` that sets the ``database`` attribute.  peewee
allows every model to specify which database it uses, defaulting to "peewee.db".
Since you probably want a bit more control, you can instantiate your own
database and point your models at it.  This is a peewee idiom:

.. code-block:: python

    # config
    DATABASE = 'tweepee.db'

    # ... more config here, omitted

    database = SqliteDatabase(DATABASE) # tell our models to use "tweepee.db"

Because sqlite likes to have a separate connection per-thread, we will tell 
flask that during the request/response cycle we need to create a connection to 
the database.  Flask provides some handy decorators to make this a snap:

.. code-block:: python

    @app.before_request
    def before_request():
        g.db = database
        g.db.connect()

    @app.after_request
    def after_request(response):
        g.db.close()
        return response

.. note::
    We're storing the db on the magical variable ``g`` - that's a 
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
difference:

.. code-block:: python

    def following(self):
        return User.select().join(
            Relationship, on='to_user_id'
        ).where(from_user=self).order_by('username')

    def followers(self):
        return User.select().join(
            Relationship
        ).where(to_user=self).order_by('username')

.. note:
    The ``following()`` method specifies an extra bit of metadata,
    ``on='to_user_id'``.  Because there are two foreign keys to ``User``, peewee
    will automatically assume the first one, which happens to be ``from_user``.


Specifying the foreign key manually instructs peewee to join on the ``to_user_id`` field.
The queries end up looking like:

.. code-block:: sql

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
if the username is taken, and if not executes a :py:meth:`~Model.create`.

.. code-block:: python

    try:
        user = User.get(username=request.form['username'])
        flash('That username is already taken')
    except User.DoesNotExist:
        user = User.create(
            username=request.form['username'],
            password=md5(request.form['password']).hexdigest(),
            email=request.form['email'],
            join_date=datetime.datetime.now()
        )

Much like the :py:meth:`~Model.create` method, all models come with a built-in method called
:py:meth:`~Model.get_or_create` which is used when one user follows another:

.. code-block:: python

    Relationship.get_or_create(
        from_user=session['user'], # <-- the logged-in user
        to_user=user, # <-- the user they want to follow
    )


Doing subqueries
^^^^^^^^^^^^^^^^

If you are logged-in and visit the twitter homepage, you will see tweets from 
the users that you follow.  In order to implement this, it is necessary to do
a subquery:

.. code-block:: python

    # python code
    qr = Message.select().where(user__in=some_user.following())

Results in the following SQL query:

.. code-block:: sql

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

peewee supports doing subqueries on any :py:class:`ForeignKeyField` or :py:class:`PrimaryKeyField`.

What else is of interest here?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are a couple other neat things going on in the example app that are worth
mentioning briefly.

* Support for paginating lists of results is implemented in a simple function called
  ``object_list`` (after it's corollary in Django).  This function is used by all
  the views that return lists of objects.

  .. code-block:: python
      
      def object_list(template_name, qr, var_name='object_list', **kwargs):
          kwargs.update(
              page=int(request.args.get('page', 1)),
              pages=qr.count() / 20 + 1
          )
          kwargs[var_name] = qr.paginate(kwargs['page'])
          return render_template(template_name, **kwargs)

* Simple authentication system with a ``login_required`` decorator.  The first
  function simply adds user data into the current session when a user successfully
  logs in.  The decorator ``login_required`` can be used to wrap view functions,
  checking for whether the session is authenticated and if not redirecting to the
  login page.

  .. code-block:: python
  
      def auth_user(user):
          session['logged_in'] = True
          session['user'] = user
          session['username'] = user.username
          flash('You are logged in as %s' % (user.username))

      def login_required(f):
          @wraps(f)
          def inner(*args, **kwargs):
              if not session.get('logged_in'):
                  return redirect(url_for('login'))
              return f(*args, **kwargs)
          return inner

* Return a 404 response instead of throwing exceptions when an object is not
  found in the database.
  
  .. code-block:: python
  
      def get_object_or_404(model, **kwargs):
          try:
              return model.get(**kwargs)
          except model.DoesNotExist:
              abort(404)

.. note::
    Like these snippets and interested in more?  Check out `flask-peewee <https://github.com/coleifer/flask-peewee>`_ -
    a flask plugin that provides a django-like Admin interface, RESTful API, Authentication and
    more for your peewee models.
