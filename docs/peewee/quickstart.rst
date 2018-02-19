.. _quickstart:

Quickstart
==========

This document presents a brief, high-level overview of Peewee's primary
features. This guide will cover:

* :ref:`model-definition`
* :ref:`storing-data`
* :ref:`retrieving-data`

.. note::
    If you'd like something a bit more meaty, there is a thorough tutorial on
    :ref:`creating a "twitter"-style web app <example-app>` using peewee and the
    Flask framework.

I **strongly** recommend opening an interactive shell session and running the
code. That way you can get a feel for typing in queries.

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

When starting a project with peewee, it's typically best to begin with your
data model, by defining one or more :py:class:`Model` classes:

.. code-block:: python

    from peewee import *

    db = SqliteDatabase('people.db')

    class Person(Model):
        name = CharField()
        birthday = DateField()
        is_relative = BooleanField()

        class Meta:
            database = db # This model uses the "people.db" database.

.. note::
    Note that we named our model ``Person`` instead of ``People``. This is a
    convention you should follow -- even though the table will contain multiple
    people, we always name the class using the singular form.

There are lots of :ref:`field types <fields>` suitable for storing various
types of data. Peewee handles converting between *pythonic* values those used
by the database, so you can use Python types in your code without having to
worry.

Things get interesting when we set up relationships between models using
`foreign keys (wikipedia) <http://en.wikipedia.org/wiki/Foreign_key>`_. This is
easy to do with peewee:

.. code-block:: python

    class Pet(Model):
        owner = ForeignKeyField(Person, backref='pets')
        name = CharField()
        animal_type = CharField()

        class Meta:
            database = db # this model uses the "people.db" database

Now that we have our models, let's connect to the database. Although it's not
necessary to open the connection explicitly, it is good practice since it will
reveal any errors with your database connection immediately, as opposed to some
arbitrary time later when the first query is executed. It is also good to close
the connection when you are done -- for instance, a web app might open a
connection when it receives a request, and close the connection when it sends
the response.

.. code-block:: python

    db.connect()

We'll begin by creating the tables in the database that will store our data.
This will create the tables with the appropriate columns, indexes, sequences,
and foreign key constraints:

.. code-block:: python

    db.create_tables([Person, Pet])

.. _storing-data:

Storing data
------------

Let's begin by populating the database with some people. We will use the
:py:meth:`~Model.save` and :py:meth:`~Model.create` methods to add and update
people's records.

.. code-block:: python

    from datetime import date
    uncle_bob = Person(name='Bob', birthday=date(1960, 1, 15), is_relative=True)
    uncle_bob.save() # bob is now stored in the database
    # Returns: 1

.. note::
    When you call :py:meth:`~Model.save`, the number of rows modified is
    returned.

You can also add a person by calling the :py:meth:`~Model.create` method, which
returns a model instance:

.. code-block:: python

    grandma = Person.create(name='Grandma', birthday=date(1935, 3, 1), is_relative=True)
    herb = Person.create(name='Herb', birthday=date(1950, 5, 5), is_relative=False)

To update a row, modify the model instance and call :py:meth:`~Model.save` to
persist the changes. Here we will change Grandma's name and then save the
changes in the database:

.. code-block:: python

    grandma.name = 'Grandma L.'
    grandma.save()  # Update grandma's name in the database.
    # Returns: 1

Now we have stored 3 people in the database. Let's give them some pets. Grandma
doesn't like animals in the house, so she won't have any, but Herb is an animal
lover:

.. code-block:: python

    bob_kitty = Pet.create(owner=uncle_bob, name='Kitty', animal_type='cat')
    herb_fido = Pet.create(owner=herb, name='Fido', animal_type='dog')
    herb_mittens = Pet.create(owner=herb, name='Mittens', animal_type='cat')
    herb_mittens_jr = Pet.create(owner=herb, name='Mittens Jr', animal_type='cat')

After a long full life, Mittens sickens and dies. We need to remove him from
the database:

.. code-block:: python

    herb_mittens.delete_instance() # he had a great life
    # Returns: 1

.. note::
    The return value of :py:meth:`~Model.delete_instance` is the number of rows
    removed from the database.

Uncle Bob decides that too many animals have been dying at Herb's house, so he
adopts Fido:

.. code-block:: python

    herb_fido.owner = uncle_bob
    herb_fido.save()
    bob_fido = herb_fido # rename our variable for clarity

.. _retrieving-data:

Retrieving Data
---------------

The real strength of our database is in how it allows us to retrieve data
through *queries*. Relational databases are excellent for making ad-hoc
queries.

Getting single records
^^^^^^^^^^^^^^^^^^^^^^

Let's retrieve Grandma's record from the database. To get a single record from
the database, use :py:meth:`Select.get`:

.. code-block:: python

    grandma = Person.select().where(Person.name == 'Grandma L.').get()

We can also use the equivalent shorthand :py:meth:`Model.get`:

.. code-block:: python

    grandma = Person.get(Person.name == 'Grandma L.')

Lists of records
^^^^^^^^^^^^^^^^

Let's list all the people in the database:

.. code-block:: python

    for person in Person.select():
        print(person.name, person.is_relative)

    # prints:
    # Bob True
    # Grandma L. True
    # Herb False

Let's list all the cats and their owner's name:

.. code-block:: python

    query = Pet.select().where(Pet.animal_type == 'cat')
    for pet in query:
        print(pet.name, pet.owner.name)

    # prints:
    # Kitty Bob
    # Mittens Jr Herb

There is a big problem with the previous query: because we are accessing
``pet.owner.name`` and we did not select this relation in our original query,
peewee will have to perform an additional query to retrieve the pet's owner.
This behavior is referred to as :ref:`N+1 <nplusone>` and it should generally
be avoided.

We can avoid the extra queries by selecting both *Pet* and *Person*, and adding
a *join*.

.. code-block:: python

    query = (Pet
             .select(Pet, Person)
             .join(Person)
             .where(Pet.animal_type == 'cat'))

    for pet in query:
        print(pet.name, pet.owner.name)

    # prints:
    # Kitty Bob
    # Mittens Jr Herb

Let's get all the pets owned by Bob:

.. code-block:: python

    for pet in Pet.select().join(Person).where(Person.name == 'Bob'):
        print(pet.name)

    # prints:
    # Kitty
    # Fido

We can do another cool thing here to get bob's pets. Since we already have an
object to represent Bob, we can do this instead:

.. code-block:: python

    for pet in Pet.select().where(Pet.owner == uncle_bob):
        print(pet.name)

Sorting
^^^^^^^

Let's make sure these are sorted alphabetically by adding an
:py:meth:`~Select.order_by` clause:

.. code-block:: python

    for pet in Pet.select().where(Pet.owner == uncle_bob).order_by(Pet.name):
        print(pet.name)

    # prints:
    # Fido
    # Kitty

Let's list all the people now, youngest to oldest:

.. code-block:: python

    for person in Person.select().order_by(Person.birthday.desc()):
        print(person.name, person.birthday)

    # prints:
    # Bob 1960-01-15
    # Herb 1950-05-05
    # Grandma L. 1935-03-01

Combining filter expressions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Peewee supports arbitrarily-nested expressions. Let's get all the people whose
birthday was either:

* before 1940 (grandma)
* after 1959 (bob)

.. code-block:: python

    d1940 = date(1940, 1, 1)
    d1960 = date(1960, 1, 1)
    query = (Person
             .select()
             .where((Person.birthday < d1940) | (Person.birthday > d1960)))

    for person in query:
        print(person.name, person.birthday)

    # prints:
    # Bob 1960-01-15
    # Grandma L. 1935-03-01

Now let's do the opposite. People whose birthday is between 1940 and 1960:

.. code-block:: python

    query = (Person
             .select()
             .where(Person.birthday.between(d1940, d1960)))

    for person in query:
        print(person.name, person.birthday)

    # prints:
    # Herb 1950-05-05

Aggregates and Prefetch
^^^^^^^^^^^^^^^^^^^^^^^

Now let's list all the people *and* how many pets they have:

.. code-block:: python

    for person in Person.select():
        print(person.name, person.pets.count(), 'pets')

    # prints:
    # Bob 2 pets
    # Grandma L. 0 pets
    # Herb 1 pets

Once again we've run into a classic example of :ref:`N+1 <nplusone>` query
behavior. In this case, we're executing an additional query for every
``Person`` returned by the original ``SELECT``! We can avoid this by performing
a *JOIN* and using a SQL function to aggregate the results.

.. code-block:: python

    query = (Person
             .select(Person, fn.COUNT(Pet.id).alias('pet_count'))
             .join(Pet, JOIN.LEFT_OUTER)  # include people without pets.
             .group_by(Person)
             .order_by(Person.name))

    for person in query:
        # "pet_count" becomes an attribute on the returned model instances.
        print(person.name, person.pet_count, 'pets')

    # prints:
    # Bob 2 pets
    # Grandma L. 0 pets
    # Herb 1 pets

Now let's list all the people and the names of all their pets. As you may have
guessed, this could easily turn into another :ref:`N+1 <nplusone>` situation if
we're not careful.

Before diving into the code, consider how this example is different from the
earlier example where we listed all the pets and their owner's name. A pet can
only have one owner, so when we performed the join from ``Pet`` to ``Person``,
there was always going to be a single match. The situation is different when we
are joining from ``Person`` to ``Pet`` because a person may have zero pets or
they may have several pets. Because we're using a relational databases, if we
were to do a join from ``Person`` to ``Pet`` then every person with multiple
pets would be repeated, once for each pet.

It would look like this:

.. code-block:: python

    query = (Person
             .select(Person, Pet)
             .join(Pet, JOIN.LEFT_OUTER)
             .order_by(Person.name, Pet.name))
    for person in query:
        # We need to check if they have a pet instance attached, since not all
        # people have pets.
        if hasattr(person, 'pet'):
            print(person.name, person.pet.name)
        else:
            print(person.name, 'no pets')

    # prints:
    # Bob Fido
    # Bob Kitty
    # Grandma L. no pets
    # Herb Mittens Jr

Usually this type of duplication is undesirable. To accomodate the more common
(and intuitive) workflow of listing a person and attaching **a list** of that
person's pets, we can use a special method called
:py:meth:`~ModelSelect.prefetch`:

.. code-block:: python

    query = Person.select().order_by(Person.name).prefetch(Pet)
    for person in query:
        print(person.name)
        for pet in person.pets:
            print('  *', pet.name)

    # prints:
    # Bob
    #   * Kitty
    #   * Fido
    # Grandma L.
    # Herb
    #   * Mittens Jr

SQL Functions
^^^^^^^^^^^^^

One last query. This will use a SQL function to find all people whose names
start with either an upper or lower-case *G*:

.. code-block:: python

    expression = fn.Lower(fn.Substr(Person.name, 1, 1)) == 'g'
    for person in Person.select().where(expression):
        print(person.name)

    # prints:
    # Grandma L.

Closing the database
--------------------

We're done with our database, let's close the connection:

.. code-block:: python

    db.close()

This is just the basics! You can make your queries as complex as you like.

All the other SQL clauses are available as well, such as:

* :py:meth:`~SelectQuery.group_by`
* :py:meth:`~SelectQuery.having`
* :py:meth:`~SelectQuery.limit` and :py:meth:`~SelectQuery.offset`

Check the documentation on :ref:`querying` for more info.

Working with existing databases
-------------------------------

If you already have a database, you can autogenerate peewee models using
:ref:`pwiz`. For instance, if I have a postgresql database named
*charles_blog*, I might run:

.. code-block:: console

    python -m pwiz -e postgresql charles_blog > blog_models.py

What next?
----------

That's it for the quickstart. If you want to look at a full web-app, check out
the :ref:`example-app`.
