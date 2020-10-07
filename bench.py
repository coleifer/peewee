from peewee import *


db = SqliteDatabase(':memory:')
#db = PostgresqlDatabase('peewee_test', host='127.0.0.1', port=26257, user='root')
#db = PostgresqlDatabase('peewee_test', host='127.0.0.1', user='postgres')

class Base(Model):
    class Meta:
        database = db

class Register(Base):
    value = IntegerField()

class Collection(Base):
    name = TextField()

class Item(Base):
    collection = ForeignKeyField(Collection, backref='items')
    name = TextField()

import functools
import time

def timed(fn):
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        times = []
        N = 10
        for i in range(N):
            start = time.time()
            fn(i, *args, **kwargs)
            times.append(time.time() - start)
        print('%0.3f ... %s' % (round(sum(times) / N, 3), fn.__name__))
    return inner

def populate_register(s, n):
    for i in range(s, n):
        Register.create(value=i)

def populate_collections(n, n_i):
    for i in range(n):
        c = Collection.create(name=str(i))
        for j in range(n_i):
            Item.create(collection=c, name=str(j))

@timed
def insert(i):
    with db.atomic():
        populate_register((i * 1000), (i + 1) * 1000)

@timed
def batch_insert(i):
    it = range(i * 1000, (i + 1) * 1000)
    for i in db.batch_commit(it, 100):
        Register.insert(value=i).execute()

@timed
def bulk_insert(i):
    with db.atomic():
        for i in range(i * 1000, (i + 1) * 1000, 100):
            data = [(j,) for j in range(i, i + 100)]
            Register.insert_many(data, fields=[Register.value]).execute()

@timed
def bulk_create(i):
    with db.atomic():
        data = [Register(value=i) for i in range(i * 1000, (i + 1) * 1000)]
        Register.bulk_create(data, batch_size=100)

@timed
def select(i):
    query = Register.select()
    for row in query:
        pass

@timed
def select_related_dbapi_raw(i):
    query = Item.select(Item, Collection).join(Collection)
    cursor = db.execute(query)
    for row in cursor:
        pass

@timed
def insert_related(i):
    with db.atomic():
        populate_collections(30, 35)

@timed
def select_related(i):
    query = Item.select(Item, Collection).join(Collection)
    for item in query:
        pass

@timed
def select_related_left(i):
    query = Collection.select(Collection, Item).join(Item, JOIN.LEFT_OUTER)
    for collection in query:
        pass

@timed
def select_related_dicts(i):
    query = Item.select(Item, Collection).join(Collection).dicts()
    for row in query:
        pass


if __name__ == '__main__':
    db.create_tables([Register, Collection, Item])
    insert()
    insert_related()
    Register.delete().execute()
    batch_insert()
    assert Register.select().count() == 10000
    Register.delete().execute()
    bulk_insert()
    assert Register.select().count() == 10000
    Register.delete().execute()
    bulk_create()
    assert Register.select().count() == 10000
    select()
    select_related()
    select_related_left()
    select_related_dicts()
    select_related_dbapi_raw()
    db.drop_tables([Register, Collection, Item])
