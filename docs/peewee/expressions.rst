Expressions
-----------

Peewee was designed to provide a simple, expressive, and pythonic way of executing
queries.  This section will provide a quick overview of some common types of expressions.

There are two primary types of objects that can be composed to create expressions:

* :py:class:`Field` instances
* SQL aggregations and functions using :py:class:`fn`

We will assume a simple "User" model with fields for username and other things.
It looks like this:

.. code-block:: python

    class User(Model):
        username = CharField()
        is_admin = BooleanField()
        is_active = BooleanField()
        last_login = DateTimeField()
        login_count = IntegerField()
        failed_logins = IntegerField()


Comparisons use the :ref:`column-lookups`:

.. code-block:: python

    # username is equal to 'charlie'
    User.username == 'charlie'

    # user has logged in less than 5 times
    User.login_count < 5

Comparisons can be combined using bitwise "and" and "or".  Operator precedence
is controlled by python and comparisons can be nested to an arbitrary depth:

.. code-block:: python

    # user is both and admin and has logged in today
    (User.is_admin == True) & (User.last_login >= today)

    # user's username is either charlie or charles
    (User.username == 'charlie') | (User.username == 'charles')

Comparisons can be used with functions as well:

.. code-block:: python

    # user's username starts with a 'g' or a 'G':
    fn.Lower(fn.Substr(User.username, 1, 1)) == 'g'

We can do some fairly interesting things, as expressions can be compared against
other expressions.  Expressions also support arithmetic operations:

.. code-block:: python

    # users who entered the incorrect more than half the time and have logged
    # in at least 10 times
    (User.failed_logins > (User.login_count * .5)) & (User.login_count > 10)

Expressions allow us to do atomic updates:

.. code-block:: python

    # when a user logs in we want to increment their login count:
    User.update(login_count=User.login_count + 1).where(User.id == user_id)

Expressions can be used in all parts of a query, so experiment!
