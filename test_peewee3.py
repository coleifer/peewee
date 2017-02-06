from peewee3 import *

User = Table('users')
Tweet = Table('tweets')

def pq(q):
    print Context().sql(q).query()

s = (User
     .select(
         User.c.id,
         User.c.username,
         fn.COUNT(Tweet.c.id).alias('ct'))
     .join(Tweet, on=(Tweet.c.user_id == User.c.id))
     .group_by(User.c.id, User.c.username))
pq(s)


UA = User.alias('alt')
s2 = s.join(UA, on=(User.c.id == UA.c.id)).order_by(UA.c.nuggz)
pq(s2)


Order = Table('orders', columns=(
    'region',
    'amount',
    'product',
    'quantity'))
regional_sales = (Order
                  .select(
                      Order.region,
                      fn.SUM(Order.amount).alias('total_sales'))
                  .group_by(Order.region)
                  .cte('regional_sales'))

top_regions = (regional_sales
               .select(regional_sales.c.region)
               .where(regional_sales.c.total_sales > (
                   regional_sales.select(
                       fn.SUM(regional_sales.c.total_sales) / 10)))
               .cte('top_regions'))

query = (Order
         .select(
             Order.region,
             Order.product,
             fn.SUM(Order.quantity).alias('product_units'),
             fn.SUM(Order.amount).alias('product_sales'))
         .where(
             Order.region << top_regions.select(top_regions.c.region))
         .group_by(Order.region, Order.product)
         .with_cte(regional_sales, top_regions))
pq(query)

q1 = User.select(User.c.id).where(User.c.username == 'charlie')
U2 = User.alias('U2')
q2 = U2.select(U2.c.id).where(U2.c.admin == True)
u = (q1 | q2).limit(3)
pq(u)

iq = User.insert({
    User.c.username: 'charlie',
    User.c.admin: True})
pq(iq)

uq = User.update({
    User.c.username: 'nuggie',
    User.c.counter: User.c.counter + 1}).where(User.c.username == 'nugz')
pq(uq)

pq(User.delete().where(User.c.username != 'asden').limit(3))

db = SqliteDatabase(':memory:')

class BM(Model):
    class Meta:
        database = db

class Person(BM):
    first = CharField()
    last = CharField()
    dob = DateField(index=True)

    class Meta:
        indexes = (
            (('first', 'last'), True),
        )

class Note(BM):
    author = ForeignKeyField(Person)
    content = TextField()

class Category(BM):
    parent = ForeignKeyField('self', backref='children', null=True)
    name = CharField(max_length=20, primary_key=True)

query = (Person
         .select(Person.first, Person.last, fn.COUNT(Note.id).alias('ct'))
         .join(Note)
         .where((Person.last == 'Leifer') & (Person.id < 4)))
pq(query)

print
print Person._schema.create_table(True).query()
for create_index in Person._schema.create_indexes(True):
    print create_index.query()
print
print Note._schema.create_table(True).query()
for create_index in Note._schema.create_indexes(True):
    print create_index.query()
print
print Category._schema.create_table(True).query()
for create_index in Category._schema.create_indexes(True):
    print create_index.query()

class User(Model):
    username = CharField()

class Note(Model):
    author = ForeignKeyField(User)
    content = TextField()

class NoteTag(Model):
    note = ForeignKeyField(Note)
    tag = CharField()

class Permission(Model):
    user = ForeignKeyField(User)
    name = CharField()

query = User.select().join(Note).join(NoteTag).join(Permission, src=User)
pq(query)

UA = User.alias('Poop')
q = UA.select().where(UA.username << User.select(User.username).where(User.id == 3))
pq(q)
