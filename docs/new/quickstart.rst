.. _quickstart:

Quickstart
==========

This document presents a very brief, high-level overview of Peewee's primary
features. This guide will cover:

* :ref:`model-definition`
* :ref:`storing-data`
* :ref:`retrieving-data`

.. note::
   If you'd like something more in-depth, there is a thorough tutorial on
   :ref:`creating a "twitter"-style web app <tutorial>` using peewee and the
   Flask framework. In the projects ``examples/`` folder you can find more
   self-contained Peewee examples, like a `blog app <https://github.com/coleifer/peewee/tree/master/examples/blog>`__.

.. _model-definition:

Model Definition
-----------------

Model classes, fields and model instances all map to database concepts:

================= =================================
Object            Corresponds to...
================= =================================
Model class       Database table
Field instance    Column on a table
Model instance    Row in a database table
================= =================================

When starting a project with peewee, it's best to begin with your data model:

.. code-block:: python

   import datetime

   from peewee import *


   db = SqliteDatabase('notes.db')


   class Note(Model):
       title = CharField()
       content = TextField()
       added = DateTimeField(
          default=datetime.datetime.now,
          index=True)

       class Meta:
           database = db

Begin by creating the table in the database.

.. code-block:: python

   db.create_tables([Note])

.. _storing-data:

Storing data
------------

To write to the database, we can use :meth:`~Model.create` and :meth:`~Model.save`.

.. code-block:: python

   note = Note.create(title='First note', content='Testing out Peewee')
   print((note.id, note.title, note.added))

   # (1, 'First note', datetime.datetime(2026, ...))

   note = Note(title='Second note')
   note.content = 'Creating another note'
   note.save()

   print((note.id, note.title, note.added))
   # (2, 'Second note', datetime.datetime(2026, ...))

Data can be modified and saved with the :meth:`~Model.save` method:

.. code-block:: python

   note.content = 'Edited the second note'
   note.save()

Deleting data
-------------

To delete a single object, use :meth:`~Model.delete_instance`:

.. code-block:: python

   note = Note.create(title='Third note', content='')
   note.delete_instance()

.. _retrieving-data:

Retrieving a record
-------------------

To retrieve a single record use :meth:`Select.get`:

.. code-block:: python

   note = Note.select().where(Note.title == 'First note').get()

We can also use the equivalent :meth:`Model.get`:

.. code-block:: python

   note = Note.get(Note.title == 'First note')

Lists of records
----------------

To list all the notes in the database, oldest to newest:

.. code-block:: python

   for note in Note.select().order_by(Note.added):
       print(note.title)

Filtering records
-----------------

Peewee supports filter expressions. Let's list all the notes added in 2026
with empty content:

.. code-block:: python

   query = (Note
            .select()
            .where(
                (Note.content == '') &
                (Note.added.year == 2026)))

   for note in query:
       print(note.id, ': ', note.title)


Simple Aggregates
-----------------

How many notes are in the database:

.. code-block:: python

   count = Note.select().count()

When the most-recent note was added:

.. code-block:: python

   latest = Note.select(fn.MAX(Note.added)).scalar()

Database
--------

When done using the database, close the connection:

.. code-block:: python

   db.close()

Working with existing databases
-------------------------------

If you already have a database, peewee can generate models using :ref:`pwiz`.
For example to generate models for a Postgres database named ``blog_db``:

.. code-block:: shell

   python -m pwiz -e postgresql blog > blog_models.py

What next?
----------

This quick-start is intentionally minimal and omits many details. The
:ref:`Twitter app tutorial <tutorial>` is a more thorough example of how to use
Peewee.
