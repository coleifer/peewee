.. _overview:

Overview
========

peewee is a lightweight `ORM <http://en.wikipedia.org/wiki/Object-relational_mapping>`_ written
in python.

Examples:

.. code-block:: python

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
    User.select().annotate(Tweet).order_by(('count', 'desc'))

    # another way of expressing the same
    User.select({
        User: ['*'],
        Tweet: [Count('id', 'count')]
    }).group_by('id').join(Tweet).order_by(('count', 'desc'))
    
    # do an atomic update
    TweetCount.update(count=F('count') + 1).where(user=charlie)


You can use django-style syntax to create select queries:

.. code-block:: python

    # how many active users are there?
    User.filter(active=True).count()

    # get tweets by a specific user
    Tweet.filter(user__username='charlie')

    # get tweets by editors
    Tweet.filter(Q(user__is_staff=True) | Q(user__is_superuser=True))



Why?
----

peewee began when I was working on a small app in flask and found myself writing
lots of queries and wanting a very simple abstraction on top of the sql.  I had
so much fun working on it that I kept adding features.  My goal has always been,
though, to keep the implementation incredibly simple.  I've made a couple dives
into django's orm but have never come away with a deep understanding of its
implementation.  peewee is small enough that its my hope anyone with an interest
in orms will be able to understand the code without too much trouble.
