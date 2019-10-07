import datetime

from peewee import *
from playhouse.postgres_ext import *
from playhouse.cockroach import CockroachDatabase


db = CockroachDatabase('peewee_test', user='root', port=26257)


class Base(Model):
    class Meta:
        database = db


class User(Base):
    id = UUIDField(primary_key=True,
                   constraints=[SQL('default gen_random_uuid()')])
    username = TextField()


class Note(Base):
    user = ForeignKeyField(User, backref='notes')
    content = TextField()
    timestamp = TimestampField(resolution=3)


db.connect()
db.drop_tables([User, Note])
db.create_tables([User, Note])


data = (
    ('huey', ('meow', 'purr', 'hiss')),
    ('mickey', ('woof', 'bow-wow')),
    ('zaizee', ()),
    ('beanie', ('myip',)))
with db.atomic():
    for username, tweets in data:
        user = User.create(username=username)
        for tweet in tweets:
            Note.create(user=user, content=tweet)


q = (User
     .select(User, fn.COUNT(Note.id).alias('tweet_count'))
     .join(Note, JOIN.LEFT_OUTER)
     .group_by(User)
     .order_by(SQL('tweet_count')))
for user in q:
    print(user.username, user.tweet_count)

db.drop_tables([User, Note])
