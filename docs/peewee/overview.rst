.. _overview:

Overview
========

peewee is a lightweight `ORM <http://en.wikipedia.org/wiki/Object-relational_mapping>`_ written
in python.

Examples:

.. code-block:: python

    # a simple query selecting a user
    User.get(User.username == 'charles')
    
    # get the staff and super users
    editors = User.select().where(
        (User.is_staff == True) |
        (User.is_superuser == True)
    )
    
    # get tweets by editors ("<<" maps to IN)
    Tweet.select().where(Tweet.user << editors)
    
    # how many active users are there?
    User.select().where(User.active == True).count()
    
    # paginate the user table and show me page 3 (users 41-60)
    User.select().order_by(User.username).paginate(3, 20)
    
    # order users by number of tweets
    User.select().annotate(Tweet).order_by(
        fn.Count(Tweet.id).desc()
    )

    # a similar way of expressing the same
    User.select(
        User, fn.Count(Tweet.id).alias('ct')
    ).join(Tweet).group_by(User).order_by(R('ct desc'))
    
    # do an atomic update
    Counter.update(count=Counter.count + 1).where(
        Counter.url == request.url
    )


Check out :ref:`the docs <query_compare>` for notes on the methods of querying.


Why?
----

peewee began when I was working on a small app in flask and found myself writing
lots of queries and wanting a very simple abstraction on top of the sql.  I had
so much fun working on it that I kept adding features.  My goal has always been,
though, to keep the implementation incredibly simple.  I've made a couple dives
into django's orm but have never come away with a deep understanding of its
implementation.  peewee is small enough that its my hope anyone with an interest
in orms will be able to understand the code without too much trouble.
