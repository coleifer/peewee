import sys
import unittest

from peewee3 import *

def __sql__(q):
    return Context().sql(q).query()

def pq(q):
    print __sql__(q)

User = Table('users')
Tweet = Table('tweets')

class BaseTestCase(unittest.TestCase):
    pass

class TestSimpleJoin(BaseTestCase):
    def test_simple_join(self):
        query = (User
                 .select(
                     User.c.id,
                     User.c.username,
                     fn.COUNT(Tweet.c.id).alias('ct'))
                 .join(Tweet, on=(Tweet.c.user_id == User.c.id))
                 .group_by(User.c.id, User.c.username))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'SELECT "t1"."id", "t1"."username", COUNT("t2"."id") AS ct '
            'FROM "users" AS "t1" '
            'INNER JOIN "tweets" AS "t2" ON ("t2"."user_id" = "t1"."id") '
            'GROUP BY "t1"."id", "t1"."username"'))
        self.assertEqual(params, [])


class TestUserDefinedAlias(BaseTestCase):
    def test_user_defined_alias(self):
        UA = User.alias('alt')
        query = (User
                 .select(User.c.id, User.c.username, UA.c.nuggz)
                 .join(UA, on=(User.c.id == UA.c.id))
                 .order_by(UA.c.nuggz))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'SELECT "t1"."id", "t1"."username", "alt"."nuggz" '
            'FROM "users" AS "t1" '
            'INNER JOIN "users" AS "alt" ON ("t1"."id" = "alt"."id") '
            'ORDER BY "alt"."nuggz"'))


class TestComplexSelect(BaseTestCase):
    def test_complex_select(self):
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

        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'WITH "regional_sales" AS ('
            'SELECT "a1"."region", SUM("a1"."amount") AS total_sales '
            'FROM "orders" AS "a1" '
            'GROUP BY "a1"."region"'
            '), '
            '"top_regions" AS ('
            'SELECT "regional_sales"."region" '
            'FROM "regional_sales" '
            'WHERE ("regional_sales"."total_sales" > '
            '(SELECT (SUM("regional_sales"."total_sales") / ?) '
            'FROM "regional_sales"))'
            ') '
            'SELECT "t1"."region", "t1"."product", '
            'SUM("t1"."quantity") AS product_units, '
            'SUM("t1"."amount") AS product_sales '
            'FROM "orders" AS "t1" '
            'WHERE ('
            '"t1"."region" IN ('
            'SELECT "top_regions"."region" '
            'FROM "top_regions")'
            ') GROUP BY "t1"."region", "t1"."product"'))
        self.assertEqual(params, [10])


class TestCompoundSelect(BaseTestCase):
    def test_compound_select(self):
        lhs = User.select(User.c.id).where(User.c.username == 'charlie')
        U2 = User.alias('UA')
        rhs = U2.select(U2.c.username).where(U2.c.admin == True)
        q2 = (lhs | rhs)
        UA = User.alias('U2')
        q3 = q2 | UA.select(UA.c.id).where(UA.c.superuser == False)

        sql, params = __sql__(q3)
        self.assertEqual(sql, (
            'SELECT "t1"."id" '
            'FROM "users" AS "t1" '
            'WHERE ("t1"."username" = ?) '
            'UNION '
            'SELECT "UA"."username" '
            'FROM "users" AS "UA" '
            'WHERE ("UA"."admin" = ?) '
            'UNION '
            'SELECT "U2"."id" '
            'FROM "users" AS "U2" '
            'WHERE ("U2"."superuser" = ?)'))
        self.assertEqual(params, ['charlie', True, False])


class TestInsertQuery(BaseTestCase):
    def test_insert_query(self):
        query = User.insert({
            User.c.username: 'charlie',
            User.c.superuser: False,
            User.c.admin: True})
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'INSERT INTO "users" ("admin", "superuser", "username") '
            'VALUES (?, ?, ?)'))
        self.assertEqual(params, [True, False, 'charlie'])


class TestUpdateQuery(BaseTestCase):
    def test_update_query(self):
        query = (User
                 .update({
                     User.c.username: 'nuggie',
                     User.c.admin: False,
                     User.c.counter: User.c.counter + 1})
                 .where(User.c.username == 'nugz'))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'UPDATE "users" SET '
            '"admin" = ?, '
            '"counter" = ("counter" + ?), '
            '"username" = ? '
            'WHERE ("username" = ?)'))
        self.assertEqual(params, [False, 1, 'nuggie', 'nugz'])


class TestDeleteQuery(BaseTestCase):
    def test_delete_query(self):
        query = (User
                 .delete()
                 .where(User.c.username != 'charlie')
                 .limit(3))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'DELETE FROM "users" WHERE ("username" != ?) LIMIT 3'))
        self.assertEqual(params, ['charlie'])

    def test_delete_subquery(self):
        subquery = (User
                    .select(User.c.id, fn.COUNT(Tweet.c.id).alias('ct'))
                    .join(Tweet, on=(Tweet.c.user_id == User.c.id))
                    .group_by(User.c.id)
                    .having(SQL('ct') > 100))
        query = (User
                 .delete()
                 .where(User.c.id << subquery))
        sql, params = __sql__(query)
        self.assertEqual(sql, (
            'DELETE FROM "users" '
            'WHERE ("id" IN '
            'SELECT "t1"."id", COUNT("t2"."id") AS ct '
            'FROM "users" AS "t1" '
            'INNER JOIN "tweets" AS "t2" ON ("t2"."user_id" = "t1"."id") '
            'GROUP BY "t1"."id" '
            'HAVING (ct > ?))'))
        self.assertEqual(params, [100])


('SELECT "t1"."first", "t1"."last", COUNT("t2"."id") AS ct FROM "person" AS "t1" INNER JOIN "note" AS "t2" ON ("t2"."author_id" = "t1"."id") WHERE (("t1"."last" = ?) AND ("t1"."id" < ?))', [u'Leifer', 4])


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

class UserM(Model):
    username = CharField()

class Note(Model):
    author = ForeignKeyField(UserM)
    content = TextField()

class NoteTag(Model):
    note = ForeignKeyField(Note)
    tag = CharField()

class Permission(Model):
    user = ForeignKeyField(UserM)
    name = CharField()

query = UserM.select().join(Note).join(NoteTag).join(Permission, src=UserM)
pq(query)

UA = UserM.alias('Poop')
q = UA.select().where(UA.username << UserM.select(UserM.username).where(UserM.id == 3))
pq(q)



if __name__ == '__main__':
    unittest.main(argv=sys.argv)
