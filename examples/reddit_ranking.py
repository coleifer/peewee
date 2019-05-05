import datetime
import math

from peewee import *
from peewee import query_to_string


db = SqliteDatabase(':memory:')

@db.func('log')
def log(n, b):
    return math.log(n, b)

class Base(Model):
    class Meta:
        database = db

class Post(Base):
    content = TextField()
    timestamp = TimestampField()
    ups = IntegerField(default=0)
    downs = IntegerField(default=0)


db.create_tables([Post])

# Populate with a number of posts.
data = (
    # Hours ago, ups, downs.
    (1, 5, 0),
    (1, 7, 1),
    (2, 10, 2),
    (2, 2, 0),
    (2, 1, 2),
    (3, 11, 2),
    (4, 20, 2),
    (4, 60, 12),
    (5, 3, 0),
    (5, 1, 0),
    (6, 30, 3),
    (6, 30, 20),
    (7, 45, 10),
    (7, 45, 20),
    (8, 11, 2),
    (8, 3, 1),
)

now = datetime.datetime.now()
Post.insert_many([
    ('post %2dh %2d up, %2d down' % (hours, ups, downs),
     now - datetime.timedelta(seconds=hours * 3600),
     ups,
     downs) for hours, ups, downs in data]).execute()


score = (Post.ups - Post.downs)
order = fn.log(fn.max(fn.abs(score), 1), 10)
sign = Case(None, (
    ((score > 0), 1),
    ((score < 0), -1)), 0)
seconds = (Post.timestamp) - 1134028003

hot = (sign * order) + (seconds / 45000)
query = Post.select(Post.content, hot.alias('score')).order_by(SQL('score').desc())
#print(query_to_string(query))
print('Posts, ordered best-to-worse:')

for post in query:
    print(post.content, round(post.score, 3))
