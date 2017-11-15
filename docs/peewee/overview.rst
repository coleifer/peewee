.. _overview:

Overview
========

The purpose of this document is to explain how and why Peewee works. We will
also cover common patterns for applications using Peewee.

Design
------

This is the third iteration of Peewee and, as such, represents a snapshot of my
understanding of what constitutes a **consistent and composable** database API
using Python. By providing consistent and composable APIs, it is my hope that
Peewee users:

* Quickly develop confidence; learn something once and apply it everywhere.
* Remember APIs, and when guessing, guess correctly.
* Combine basic query elements to produce reusable application-specific
  data-structures.

At the end of the day, we all want to spend more time coding and less time
reading docs or debugging. Peewee aims to help. Have an idea on how to make
things better? [Open a ticket](https://github.com/coleifer/peewee/issues/new).

Components
----------

Peewee is composed of several different components, which, taken together,
provide most everything you need to work with a relational database. These
compoments are:

* :py:class:`Database` object (vendor-specific subclasses are provided for
  SQLite, MySQL and Postgres). The :py:class:`Database` represents a connection
  to the database, including transaction management.
* :py:class:`Table` and :py:class:`Column` classes, and their corollary
  high-level APIs :py:class:`Model` and :py:class:`Field`.
* :py:class:`Select`, :py:class:`Insert`, :py:class:`Update` and
  :py:class:`Delete`, for CRUD operations.
* :py:class:`SchemaManager` for managing the database schema.

Declarative Data Model
----------------------

When starting a new project, I like to begin by defining a data model. Peewee
:py:class:`Model` classes use a declarative syntax that will be familiar to
Django users.

.. note::
    When working with a pre-existing database, the :ref:`pwiz` extension module
    can introspect your database and generate :py:class:`Model` definitions for
    the database tables.

Begin by subclassing ``Model``, then assign field instances as class attributes
to define the table's structure. It's a good practice to declare a
``BaseModel`` class, as it allows you to keep global configuration settings in
one place. For now ours will be empty, but we'll add to it later on.

Here's an example data-model for a very simple note-taking application:

.. code-block:: python

    import datetime
    from peewee import *


    class BaseModel(Model):
        pass


    class User(BaseModel):
        username = CharField(unique=True)


    class Note(BaseModel):
        user = ForeignKeyField(User, backref='notes')
        content = TextField()
        timestamp = DateTimeField(default=datetime.datetime.now, index=True)
        is_published = BooleanField(default=True)


Some things to note:

* We can create relationships using the :py:class:`ForeignKeyField`. In the
  above example, a *user* may have any number of associated *notes*.
* We can also specify some constraints, for instance the *User* table will have
  a *UNIQUE* constraint on the *username* column.
* We can specify single-column indexes by adding ``index=True`` to the field
  constructor.
* Fields may have a default value, which can either be a scalar value *or* in
  the case of the *timestamp* field, a callable.


Composable Expressions
----------------------

The main goal of Peewee can be summed up in two words: **composable** and
**consistent** APIs. What do we mean by that? Simply, that a technique learned
once can be applied anywhere (consistent), and that small pieces can be treated
like building blocks to build larger, reusable pieces.

Let's take a look at how this plays out in practice, using the *User* and
*Note* example models from the earlier section.

We can define a query object representing all published notes in the following
manner:

.. code-block:: python

    published = Note.select().where(Note.is_published == True)

Suppose we wanted to sort the above query by timestamp, newest-to-oldest, and
additionally filter by the user that created the note. We could implement the
following:

.. code-block:: python

    def published_notes():
        return Note.select().where(Note.is_published == True)

    def user_timeline(username):
        published = published_notes()
        return (published
                .join(User)
                .where(User.username == username)
                .order_by(Note.timestamp.desc()))

In the example above, we take the query returned by the *published_notes()*
function and then further filter/extend it with a join, additional where
clause, and an order by clause.

The individual components of a query are reusable and composable. In the
following example, we'll define a SQL function that captures the first letter
of a user's username, and use that in a WHERE clause:

.. code-block:: python

    # Corresponds to LOWER(SUBSTR("user"."username", 1, 1))
    first_letter = fn.LOWER(fn.SUBSTR(User.username, 1, 1))

    # WHERE LOWER(SUBSTR("user"."username", 1, 1)) = 'a'
    a_users = User.select().where(first_letter == 'a')

    # Example of composing expressions:
    # WHERE (LOWER(SUBSTR("user"."username", 1, 1)) = 'a'
    #        OR LOWER(SUBSTR("user"."username", 1, 1)) = 'b'
    a_or_b_users = (User
                    .select()
                    .where((first_letter == 'a') | (first_letter == 'b')))
