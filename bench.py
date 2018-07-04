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
            fn(*args, **kwargs)
            times.append(time.time() - start)
        print(fn.__name__, round(sum(times) / N, 3))
    return inner

def populate_register(n):
    for i in range(n):
        Register.create(value=i)

def populate_collections(n, n_i):
    for i in range(n):
        c = Collection.create(name=str(i))
        for j in range(n_i):
            Item.create(collection=c, name=str(j))

@timed
def insert():
    with db.atomic():
        populate_register(1000)

@timed
def batch_insert():
    with db.atomic():
        it = range(1000)
        for i in db.batch_commit(it, 100):
            Register.insert(value=i + 100000).execute()

@timed
def bulk_insert():
    with db.atomic():
        for i in range(0, 1000, 100):
            data = [(j,) for j in range(i, i + 100)]
            Register.insert_many(data, fields=[Register.value]).execute()

@timed
def select():
    query = Register.select()
    for row in query:
        pass

@timed
def select_related_dbapi_raw():
    query = Item.select(Item, Collection).join(Collection)
    cursor = db.execute(query)
    for row in cursor:
        pass

@timed
def insert_related():
    with db.atomic():
        populate_collections(30, 35)

@timed
def select_related():
    query = Item.select(Item, Collection).join(Collection)
    for item in query:
        pass

@timed
def select_related_left():
    query = Collection.select(Collection, Item).join(Item, JOIN.LEFT_OUTER)
    for collection in query:
        pass

@timed
def select_related_dicts():
    query = Item.select(Item, Collection).join(Collection).dicts()
    for row in query:
        pass


if __name__ == '__main__':
    db.create_tables([Register, Collection, Item])
    insert()
    insert_related()
    Register.delete().execute()
    batch_insert()
    Register.delete().execute()
    bulk_insert()
    select()
    select_related()
    select_related_left()
    select_related_dicts()
    select_related_dbapi_raw()
    db.drop_tables([Register, Collection, Item])
