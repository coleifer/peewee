.. _quickstart:

Quickstart
==========

I'm a sucker for quickstarts, so this will be a very brief overview to present
peewee and some of its features.  This guide will cover:

* :ref:`model-definition`
* :ref:`storing-data`
* :ref:`retrieving-data`

.. note::
    If you'd like something a bit more meaty, there is a thorough tutorial on
    :ref:`creating a "twitter"-style web app  <example-app>` using peewee.

I recommend opening an interactive shell session and running the code.  That way
you can get a feel for typing in queries.

.. _model-definition:

Model Definition
-----------------

Models are a 1-to-1 mapping to database tables:

.. code-block:: python

    from peewee import *

    db = SqliteDatabase('people.db')

    class Person(Model):
        name = CharField()
        birthday = DateField()
        is_relative = BooleanField()

        class Meta:
            database = db # this model uses the people database


There are lots of :ref:`field types <fields>` suitable for storing various types
of data.  peewee handles converting between "pythonic" values those used by the
database, so you don't have to worry about it.

Things get interesting when we set up relationships between models using foreign
keys.  This is easy to do with peewee:

.. code-block:: python

    class Pet(Model):
        owner = ForeignKeyField(Person, related_name='pets')
        name = CharField()
        animal_type = CharField()

        class Meta:
            database = db # this model uses the people database


Now that we have our models, let's create the tables in the database that will
store our data.  This will create the tables with the appropriate columns, indexes
and foreign key constraints:

.. code-block:: pycon

    >>> Person.create_table()
    >>> Pet.create_table()


.. _storing-data:

Storing data
------------

Let's store some people to the database, and then we'll give them some pets.

.. code-block:: pycon

    >>> from datetime import date
    >>> uncle_bob = Person(name='Bob', birthday=date(1960, 1, 15), is_relative=True)
    >>> uncle_bob.save() # bob is now stored in the database

You can automatically add a person by calling the :py:meth:`Model.create` method:

.. code-block:: pycon

    >>> grandma = Person.create(name='Grandma', birthday=date(1935, 3, 1), is_relative=True)
    >>> herb = Person.create(name='Herb', birthday=date(1950, 5, 5), is_relative=False)

Let's say we want to change Grandma's name to be a little more specific:

.. code-block:: pycon

    >>> grandma.name = 'Grandma L.'
    >>> grandma.save() # update grandma's name in the database

Now we have stored 3 people in the database.  Let's give them some pets.  Grandma
doesn't like animals in the house, so she won't have any, but Herb has a lot of pets:

.. code-block:: pycon

    >>> bob_kitty = Pet.create(owner=uncle_bob, name='Kitty', animal_type='cat')
    >>> herb_fido = Pet.create(owner=herb, name='Fido', animal_type='dog')
    >>> herb_mittens = Pet.create(owner=herb, name='Mittens', animal_type='cat')
    >>> herb_mittens_jr = Pet.create(owner=herb, name='Mittens Jr', animal_type='cat')

Let's pretend that, after a long full life, Mittens gets sick and dies.  We need
to remove him from the database:

.. code-block:: pycon

    >>> herb_mittens.delete_instance() # he had a great life
    1

You might notice that it printed "1" -- whenever you call :py:meth:`Model.delete_instance`
it will return the number of rows removed from the database.

Uncle Bob decides that too many animals have been dying at Herb's house, so he
adopts Fido:

.. code-block:: pycon

    >>> herb_fido.owner = uncle_bob
    >>> herb_fido.save()
    >>> bob_fido = herb_fido # rename our variable for clarity


.. _retrieving-data:

Retrieving Data
---------------

The real power of our database comes when we want to retrieve data.  Relational
databases are a great tool for making ad-hoc queries.


Getting single records
^^^^^^^^^^^^^^^^^^^^^^

Let's retrieve Grandma's record from the database.  To get a single record
from the database, use :py:meth:`SelectQuery.get`:

.. code-block:: pycon

    >>> grandma = Person.select().where(Person.name == 'Grandma L.').get()

We can also use a shorthand:

.. code-block:: pycon

    >>> grandma = Person.get(Person.name == 'Grandma L.')


Lists of records
^^^^^^^^^^^^^^^^

Let's list all the people in the database:

.. code-block:: pycon

    >>> for person in Person.select():
    ...     print person.name, person.is_relative
    ...
    Bob True
    Grandma L. True
    Herb False

Now let's list all the people *and* some info about their pets:

.. code-block:: pycon

    >>> for person in Person.select():
    ...     print person.name, person.pets.count(), 'pets'
    ...     for pet in person.pets:
    ...         print '    ', pet.name, pet.animal_type
    ...
    Bob 2 pets
        Kitty cat
        Fido dog
    Grandma L. 0 pets
    Herb 1 pets
        Mittens Jr cat

Let's list all the cats and their owner's name:

.. code-block:: pycon

    >>> for pet in Pet.select().where(Pet.animal_type == 'cat'):
    ...     print pet.name, pet.owner.name
    ...
    Kitty Bob
    Mittens Jr Herb


This one will be a little more interesting and introduces the concept of joins.
Let's get all the pets owned by Bob:

.. code-block:: pycon

    >>> for pet in Pet.select().join(Person).where(Person.name == 'Bob'):
    ...     print pet.name
    ...
    Kitty
    Fido


We can do another cool thing here to get bob's pets.  Since we already have an
object to represent Bob, we can do this instead:

.. code-block:: pycon

    >>> for pet in Pet.select().where(Pet.owner == uncle_bob):
    ...     print pet.name


Let's make sure these are sorted alphabetically.  To do that add an :py:meth:`SelectQuery.order_by`
clause:

.. code-block:: pycon

    >>> for pet in Pet.select().where(Pet.owner == uncle_bob).order_by(Pet.name):
    ...     print pet.name
    ...
    Fido
    Kitty


Let's list all the people now, youngest to oldest:

.. code-block:: pycon

    >>> for person in Person.select().order_by(Person.birthday.desc()):
    ...     print person.name
    ...
    Bob
    Herb
    Grandma L.


Finally, let's do a complicated one.  Let's get all the people whose birthday was
either:

* before 1940 (grandma)
* after 1959 (herb)

.. code-block:: pycon

    >>> d1940 = date(1940, 1, 1)
    >>> d1960 = date(1960, 1, 1)
    >>> for person in Person.select().where((Person.birthday < d1940) | (Person.birthday > d1960)):
    ...     print person.name
    ...
    Bob
    Grandma L.

Now let's do the opposite.  People whose birthday is between 1940 and 1960:

.. code-block:: pycon

    >>> for person in Person.select().where((Person.birthday > d1940) & (Person.birthday < d1960)):
    ...     print person.name
    ...
    Herb

One last query.  This will use a SQL function to find all people whose names
start with either an upper or lower-case "G":

.. code-block:: pycon

    >>> for person in Person.select().where(fn.Lower(fn.Substr(Person.name, 1, 1)) == 'g'):
    ...     print person.name
    ...
    Grandma L.

This is just the basics!  You can make your queries as complex as you like.

All the other SQL clauses are available as well, such as:

* :py:meth:`SelectQuery.group_by`
* :py:meth:`SelectQuery.having`
* :py:meth:`SelectQuery.limit` and :py:meth:`SelectQuery.offset`

Check the documentation on :ref:`querying` for more info.


Do you have a legacy database?
------------------------------

If you already have a database, you can autogenerate peewee models using :ref:`pwiz`
which is part of the "playhouse".


What next?
----------

That's it for the quickstart.  If you want to look at a full web-app, check out
the :ref:`example-app`.

Got a specific problem to solve?  Check the :ref:`cookbook` for common recipes.
