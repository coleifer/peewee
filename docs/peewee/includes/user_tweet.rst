.. code-block:: python

    from peewee import *

    class User(Model):
        username = CharField(unique=True)

    class Tweet(Model):
        user = ForeignKeyField(User, related_name='tweets')
        message = TextField()
        created_date = DateTimeField(default=datetime.datetime.now)
        is_published = BooleanField(default=True)
