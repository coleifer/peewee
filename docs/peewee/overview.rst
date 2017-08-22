.. _overview:

Overview
========

The purpose of this document is to explain how and why Peewee works. We will
also cover common patterns for applications using Peewee.

Design
------

This is the third iteration of Peewee and, as such, represents a snapshot of my
understanding of what constitutes a **consistent and composable** database API
using Python. By providing **consistent and composable** APIs, it is my hope
that Peewee users:

* Quickly develop confidence; learn something once and apply it everywhere.
* Remember APIs, and when guessing, guess correctly.
* Combine basic query elements to produce reusable application-specific
  data-structures.

At the end of the day, we all want to spend more time coding and less time
reading docs or debugging.

Components
----------

Peewee is composed of several different components, which, taken together,
provide everything you need to work with a relational database. These
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
to define the table's schema. It's a good practice to declare a ``BaseModel``
class, as it allows you to keep global configuration settings in one place. For
now ours will be empty, but we'll add to it later on.

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
        timestamp = DateTimeField(default=datetime.datetime.now)
        is_published = BooleanField(default=True)
