import datetime

from peewee import *
from playhouse.postgres_ext import *
from playhouse.cockroach import CockroachDatabase


db = CockroachDatabase('peewee_test', user='root', port=26257)


class Base(Model):
    class Meta:
        database = db


class Note(Base):
    content = TextField()
    timestamp = DateTimeField()
    data = BinaryJSONField()
    tags = ArrayField(CharField, index=False)
    uid = UUIDField(constraints=[SQL('default gen_random_uuid()')])


db.connect()
db.drop_tables([Note])
db.create_tables([Note])

with db.atomic():
    n1 = Note.create(content='n1', timestamp=datetime.datetime(2019, 1, 1),
                     data={'k1': 'v1', 'k2': {'x1': 'y1', 'x2': 'y2'}},
                     tags=['foo', 'bar', 'baz'])
    n2 = Note.create(content='n2', timestamp=datetime.datetime(2019, 1, 2),
                     data={'k3': 'v3', 'i1': ['a1', 'a2', 'a3', 'a4']},
                     tags=['nug', 'bar'])

data = [
    ('n3', datetime.datetime(2018, 12, 31), {'k1': [1, 2.3, 3]}, ['x']),
    ('n4', datetime.datetime(2018, 11, 30), {'k1': 0.}, ['', 'biz']),
]
q = (Note
     .insert_many(data, fields=[Note.content, Note.timestamp, Note.data,
                                Note.tags])
     .returning(Note.id, Note.content, Note.data, Note.uid))
n_ids = {}
for n in q:
    print(n.id, n.content, n.data, n.uid)
    n_ids[n.content] = n.id

q = (Note
     .insert(content='n3-x', timestamp=datetime.datetime(2018, 12, 1),
             data={'k1': [100, 23.4, 0.5]}, tags=['x'], id=n_ids['n3'])
     .on_conflict(
         conflict_target=[Note.id],
         preserve=[Note.content, Note.tags]))
print(q.execute())

print('--')

query = (Note
         .select(Note,
                 Note.timestamp.year.alias('year'),
                 Note.data['k1'].alias('k1'),
                 Note.tags[0].alias('t0'))
         .order_by(Note.id))
for note in query:
    print(note.content, note.data, note.year, note.k1, note.t0, note.uid)

print('--')

q1 = Note.select(Note.content, Note.tags).where(Note.content == 'n1')
q2 = Note.select(Note.content, Note.tags).where(Note.content == 'n4')
u = q1 | q2
print(u.sql())
for note in (q1 | q2):
    print(note.content)


db.drop_tables([Note])
