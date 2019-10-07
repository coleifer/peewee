import datetime

from peewee import *
from playhouse.postgres_ext import *
from playhouse.cockroach import CockroachDatabase


db = CockroachDatabase('peewee_test', user='root', port=26257)


class Base(Model):
    class Meta:
        database = db


class Reg(Base):
    key = TextField(primary_key=True)
    value = TextField()
    uid = UUIDField(constraints=[SQL('default gen_random_uuid()')])


db.connect()
db.drop_tables([Reg])
db.create_tables([Reg])


data = [('k%02d' % i, 'v%s' % i) for i in range(8)]
iq = (Reg
      .insert_many(data, fields=[Reg.key, Reg.value])
      .returning(Reg))
for row in iq.execute():
    print(row.key, row.uid)

print('--')

Reg.replace(key='k01', value='v1-x', uid=fn.gen_random_uuid()).execute()

query = (Reg
         .select(Reg.key, Reg.value, Reg.uid)
         .where(Reg.key.in_(['k00', 'k01'])))
for row in query:
    print(row.key, row.value, row.uid)

print('--')

# Grab 3 rows.
r1, r2, r3 = Reg.select().order_by(Reg.key).limit(3)
r1.value = 'v01-x'
r2.value = 'v02-x'
r3.value = 'v03-x'
Reg.bulk_update([r1, r2, r3], [Reg.value])

query = Reg.select().order_by(Reg.key).limit(4)
for reg in query:
    print(reg.key, reg.value)

db.drop_tables([Reg])
