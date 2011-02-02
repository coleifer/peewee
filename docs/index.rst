.. peewee documentation master file, created by
   sphinx-quickstart on Thu Nov 25 21:20:29 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. image:: peewee-white.png

peewee
======

* a small orm
* written in python
* provides a lightweight querying interface over sql
* uses sql concepts when querying, like joins and where clauses


Examples::

    # a simple query selecting a user
    User.get(username='charles')
    
    # get the staff and super users
    editors = User.select().where(Q(is_staff=True) | Q(is_superuser=True))
    
    # get tweets by editors
    Tweet.select().where(user__in=editors)
    
    # how many active users are there?
    User.select().where(active=True).count()
    
    # paginate the user table and show me page 3 (users 41-60)
    User.select().order_by(('username', 'asc')).paginate(3, 20)
    
    # order users by number of tweets
    User.select({
        User: ['*'],
        Tweet: [Count('id', 'num_tweets')]
    }).group_by('id').join(Tweet).order_by(('num_tweets', 'desc'))


Why?
----

peewee began when I was working on a small app in flask and found myself writing
lots of queries and wanting a very simple abstraction on top of the sql.  I had
so much fun working on it that I kept adding features.  My goal has always been,
though, to keep the implementation incredibly simple.  I've made a couple dives
into django's orm but have never come away with a deep understanding of its
implementation.  peewee is small enough that its my hope anyone with an interest
in orms will be able to understand the code without too much trouble.


Contents:
---------

.. toctree::
   :maxdepth: 3
   :glob:
   
   peewee/installation
   peewee/example
   peewee/models
   peewee/querying

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

