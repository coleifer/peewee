import datetime

from peewee import *

from .base import BaseTestCase
from .base import TestModel
from .base import db


User = Table('users')
Tweet = Table('tweets')
Person = Table('person', ['id', 'name', 'dob'])
Note = Table('note', ['id', 'person_id', 'content'])


class TestSelectQuery(BaseTestCase):
    def test_select(self):
        query = (User
                 .select(User.c.id, User.c.username)
                 .where(User.c.username == 'foo'))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" '
            'FROM "users" AS "t1" '
            'WHERE ("t1"."username" = ?)'), ['foo'])

    def test_select_explicit_columns(self):
        query = (Person
                 .select()
                 .where(Person.dob < datetime.date(1980, 1, 1)))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name", "t1"."dob" '
            'FROM "person" AS "t1" '
            'WHERE ("t1"."dob" < ?)'), [datetime.date(1980, 1, 1)])

    def test_from_clause(self):
        query = (Note
                 .select(Note.content, Person.name)
                 .from_(Note, Person)
                 .where(Note.person_id == Person.id)
                 .order_by(Note.id))
        self.assertSQL(query, (
            'SELECT "t1"."content", "t2"."name" '
            'FROM "note" AS "t1", "person" AS "t2" '
            'WHERE ("t1"."person_id" = "t2"."id") '
            'ORDER BY "t1"."id"'), [])

    def test_from_query(self):
        inner = Person.select(Person.name)
        query = (Person
                 .select(Person.name)
                 .from_(inner.alias('i1')))
        self.assertSQL(query, (
            'SELECT "t1"."name" '
            'FROM (SELECT "t1"."name" FROM "person" AS "t1") AS "i1"'), [])

        PA = Person.alias('pa')
        inner = PA.select(PA.name).alias('i1')
        query = (Person
                 .select(inner.c.name)
                 .from_(inner)
                 .order_by(inner.c.name))
        self.assertSQL(query, (
            'SELECT "i1"."name" '
            'FROM (SELECT "pa"."name" FROM "person" AS "pa") AS "i1" '
            'ORDER BY "i1"."name"'), [])

    def test_join_explicit_columns(self):
        query = (Note
                 .select(Note.content)
                 .join(Person, on=(Note.person_id == Person.id))
                 .where(Person.name == 'charlie')
                 .order_by(Note.id.desc()))
        self.assertSQL(query, (
            'SELECT "t1"."content" '
            'FROM "note" AS "t1" '
            'INNER JOIN "person" AS "t2" ON ("t1"."person_id" = "t2"."id") '
            'WHERE ("t2"."name" = ?) '
            'ORDER BY "t1"."id" DESC'), ['charlie'])

    def test_multi_join(self):
        Like = Table('likes')
        LikeUser = User.alias('lu')
        query = (Like
                 .select(Tweet.c.content, User.c.username, LikeUser.c.username)
                 .join(Tweet, on=(Like.c.tweet_id == Tweet.c.id))
                 .join(User, on=(Tweet.c.user_id == User.c.id))
                 .join(LikeUser, on=(Like.c.user_id == LikeUser.c.id))
                 .where(LikeUser.c.username == 'charlie')
                 .order_by(Tweet.c.timestamp))
        self.assertSQL(query, (
            'SELECT "t1"."content", "t2"."username", "lu"."username" '
            'FROM "likes" AS "t3" '
            'INNER JOIN "tweets" AS "t1" ON ("t3"."tweet_id" = "t1"."id") '
            'INNER JOIN "users" AS "t2" ON ("t1"."user_id" = "t2"."id") '
            'INNER JOIN "users" AS "lu" ON ("t3"."user_id" = "lu"."id") '
            'WHERE ("lu"."username" = ?) '
            'ORDER BY "t1"."timestamp"'), ['charlie'])

    def test_correlated_subquery(self):
        Employee = Table('employee', ['id', 'name', 'salary', 'dept'])
        EA = Employee.alias('e2')
        query = (Employee
                 .select(Employee.id, Employee.name)
                 .where(Employee.salary > (EA
                                           .select(fn.AVG(EA.salary))
                                           .where(EA.dept == Employee.dept))))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name" '
            'FROM "employee" AS "t1" '
            'WHERE ("t1"."salary" > ('
            'SELECT AVG("e2"."salary") '
            'FROM "employee" AS "e2" '
            'WHERE ("e2"."dept" = "t1"."dept")))'), [])

    def test_multiple_where(self):
        """Ensure multiple calls to WHERE are AND-ed together."""
        query = (Person
                 .select(Person.name)
                 .where(Person.dob < datetime.date(1980, 1, 1))
                 .where(Person.dob > datetime.date(1950, 1, 1)))
        self.assertSQL(query, (
            'SELECT "t1"."name" '
            'FROM "person" AS "t1" '
            'WHERE (("t1"."dob" < ?) AND ("t1"."dob" > ?))'),
            [datetime.date(1980, 1, 1), datetime.date(1950, 1, 1)])

    def test_simple_join(self):
        query = (User
                 .select(
                     User.c.id,
                     User.c.username,
                     fn.COUNT(Tweet.c.id).alias('ct'))
                 .join(Tweet, on=(Tweet.c.user_id == User.c.id))
                 .group_by(User.c.id, User.c.username))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username", COUNT("t2"."id") AS ct '
            'FROM "users" AS "t1" '
            'INNER JOIN "tweets" AS "t2" ON ("t2"."user_id" = "t1"."id") '
            'GROUP BY "t1"."id", "t1"."username"'), [])

    def test_subquery(self):
        inner = (Tweet
                 .select(fn.COUNT(Tweet.c.id).alias('ct'))
                 .where(Tweet.c.user == User.c.id))
        query = (User
                 .select(User.c.username, inner.alias('iq'))
                 .order_by(User.c.username))
        self.assertSQL(query, (
            'SELECT "t1"."username", '
            '(SELECT COUNT("t2"."id") AS ct '
            'FROM "tweets" AS "t2" '
            'WHERE ("t2"."user" = "t1"."id")) AS "iq" '
            'FROM "users" AS "t1" ORDER BY "t1"."username"'), [])

    def test_user_defined_alias(self):
        UA = User.alias('alt')
        query = (User
                 .select(User.c.id, User.c.username, UA.c.nuggz)
                 .join(UA, on=(User.c.id == UA.c.id))
                 .order_by(UA.c.nuggz))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username", "alt"."nuggz" '
            'FROM "users" AS "t1" '
            'INNER JOIN "users" AS "alt" ON ("t1"."id" = "alt"."id") '
            'ORDER BY "alt"."nuggz"'), [])

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

        self.assertSQL(query, (
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
            ') GROUP BY "t1"."region", "t1"."product"'), [10])

    def test_compound_select(self):
        lhs = User.select(User.c.id).where(User.c.username == 'charlie')
        rhs = User.select(User.c.username).where(User.c.admin == True)
        q2 = (lhs | rhs)
        UA = User.alias('U2')
        q3 = q2 | UA.select(UA.c.id).where(UA.c.superuser == False)

        self.assertSQL(q3, (
            'SELECT "t1"."id" '
            'FROM "users" AS "t1" '
            'WHERE ("t1"."username" = ?) '
            'UNION '
            'SELECT "a1"."username" '
            'FROM "users" AS "a1" '
            'WHERE ("a1"."admin" = ?) '
            'UNION '
            'SELECT "U2"."id" '
            'FROM "users" AS "U2" '
            'WHERE ("U2"."superuser" = ?)'), ['charlie', True, False])

    def test_join_on_query(self):
        inner = User.select(User.c.id).alias('j1')
        query = (Tweet
                 .select(Tweet.c.content)
                 .join(inner, on=(Tweet.c.user_id == inner.c.id)))
        self.assertSQL(query, (
            'SELECT "t1"."content" FROM "tweets" AS "t1" '
            'INNER JOIN (SELECT "t2"."id" FROM "users" AS "t2") AS "j1" '
            'ON ("t1"."user_id" = "j1"."id")'), [])

    def test_join_on_misc(self):
        cond = fn.Magic(Person.id, Note.id).alias('magic')
        query = Person.select(Person.id).join(Note, on=cond)
        self.assertSQL(query, (
            'SELECT "t1"."id" FROM "person" AS "t1" '
            'INNER JOIN "note" AS "t2" '
            'ON Magic("t1"."id", "t2"."id") AS magic'), [])


class TestInsertQuery(BaseTestCase):
    def test_insert_query(self):
        query = User.insert({
            User.c.username: 'charlie',
            User.c.superuser: False,
            User.c.admin: True})
        self.assertSQL(query, (
            'INSERT INTO "users" ("admin", "superuser", "username") '
            'VALUES (?, ?, ?)'), [True, False, 'charlie'])

    def test_insert_list(self):
        data = [
            {Person.name: 'charlie'},
            {Person.name: 'huey'},
            {Person.name: 'zaizee'}]
        query = Person.insert(data)
        self.assertSQL(query, (
            'INSERT INTO "person" ("name") VALUES (?), (?), (?)'),
            ['charlie', 'huey', 'zaizee'])

    def test_insert_query(self):
        source = User.select(User.c.username).where(User.c.admin == False)
        query = Person.insert(source, columns=[Person.name])
        self.assertSQL(query, (
            'INSERT INTO "person" ("name") '
            'SELECT "t1"."username" FROM "users" AS "t1" '
            'WHERE ("t1"."admin" = ?)'), [False])

    def test_insert_query_cte(self):
        cte = User.select(User.c.username).cte('foo')
        source = cte.select(cte.c.username)
        query = Person.insert(source, columns=[Person.name]).with_cte(cte)
        self.assertSQL(query, (
            'WITH "foo" AS (SELECT "a1"."username" FROM "users" AS "a1") '
            'INSERT INTO "person" ("name") '
            'SELECT "foo"."username" FROM "foo"'), [])

    def test_insert_returning(self):
        query = (Person
                 .insert({
                     Person.name: 'zaizee',
                     Person.dob: datetime.date(2000, 1, 2)})
                 .returning(Person.id, Person.name, Person.dob))
        self.assertSQL(query, (
            'INSERT INTO "person" ("dob", "name") '
            'VALUES (?, ?) RETURNING "id", "name", "dob"'),
            [datetime.date(2000, 1, 2), 'zaizee'])

    def test_empty(self):
        class Empty(TestModel): pass
        query = Empty.insert()
        if isinstance(db, MySQLDatabase):
            sql = 'INSERT INTO "empty" () VALUES ()'
        elif isinstance(db, PostgresqlDatabase):
            sql = 'INSERT INTO "empty" DEFAULT VALUES RETURNING "id"'
        else:
            sql = 'INSERT INTO "empty" DEFAULT VALUES'
        self.assertSQL(query, sql, [])


class TestUpdateQuery(BaseTestCase):
    def test_update_query(self):
        query = (User
                 .update({
                     User.c.username: 'nuggie',
                     User.c.admin: False,
                     User.c.counter: User.c.counter + 1})
                 .where(User.c.username == 'nugz'))
        self.assertSQL(query, (
            'UPDATE "users" SET '
            '"admin" = ?, '
            '"counter" = ("counter" + ?), '
            '"username" = ? '
            'WHERE ("username" = ?)'), [False, 1, 'nuggie', 'nugz'])

    def test_update_subquery(self):
        subquery = (User
                    .select(User.c.id, fn.COUNT(Tweet.c.id).alias('ct'))
                    .join(Tweet, on=(Tweet.c.user_id == User.c.id))
                    .group_by(User.c.id)
                    .having(SQL('ct') > 100))
        query = (User
                 .update({
                     User.c.muted: True,
                     User.c.counter: 0})
                 .where(User.c.id << subquery))
        self.assertSQL(query, (
            'UPDATE "users" SET '
            '"counter" = ?, '
            '"muted" = ? '
            'WHERE ("id" IN ('
            'SELECT "users"."id", COUNT("t1"."id") AS ct '
            'FROM "users" AS "users" '
            'INNER JOIN "tweets" AS "t1" '
            'ON ("t1"."user_id" = "users"."id") '
            'GROUP BY "users"."id" '
            'HAVING (ct > ?)))'), [0, True, 100])

    def test_update_returning(self):
        query = (User
                 .update({User.c.is_admin: True})
                 .where(User.c.username == 'charlie')
                 .returning(User.c.id))
        self.assertSQL(query, (
            'UPDATE "users" SET "is_admin" = ? WHERE ("username" = ?) '
            'RETURNING "id"'), [True, 'charlie'])


class TestDeleteQuery(BaseTestCase):
    def test_delete_query(self):
        query = (User
                 .delete()
                 .where(User.c.username != 'charlie')
                 .limit(3))
        self.assertSQL(
            query,
            'DELETE FROM "users" WHERE ("username" != ?) LIMIT 3',
            ['charlie'])

    def test_delete_subquery(self):
        subquery = (User
                    .select(User.c.id, fn.COUNT(Tweet.c.id).alias('ct'))
                    .join(Tweet, on=(Tweet.c.user_id == User.c.id))
                    .group_by(User.c.id)
                    .having(SQL('ct') > 100))
        query = (User
                 .delete()
                 .where(User.c.id << subquery))
        self.assertSQL(query, (
            'DELETE FROM "users" '
            'WHERE ("id" IN ('
            'SELECT "users"."id", COUNT("t1"."id") AS ct '
            'FROM "users" AS "users" '
            'INNER JOIN "tweets" AS "t1" ON ("t1"."user_id" = "users"."id") '
            'GROUP BY "users"."id" '
            'HAVING (ct > ?)))'), [100])

    def test_delete_cte(self):
        cte = (User
               .select(User.c.id)
               .where(User.c.admin == True)
               .cte('u'))
        query = (User
                 .delete()
                 .where(User.c.id << cte.select(cte.c.id))
                 .with_cte(cte))
        self.assertSQL(query, (
            'WITH "u" AS '
            '(SELECT "a1"."id" FROM "users" AS "a1" WHERE ("a1"."admin" = ?)) '
            'DELETE FROM "users" '
            'WHERE ("id" IN (SELECT "u"."id" FROM "u"))'), [True])

    def test_delete_returning(self):
        query = (User
                 .delete()
                 .where(User.c.id > 2)
                 .returning(User.c.username))
        self.assertSQL(query, (
            'DELETE FROM "users" '
            'WHERE ("id" > ?) '
            'RETURNING "username"'), [2])

        query = query.returning(User.c.id, User.c.username, SQL('1'))
        self.assertSQL(query, (
            'DELETE FROM "users" '
            'WHERE ("id" > ?) '
            'RETURNING "id", "username", 1'), [2])


Register = Table('register', ('id', 'value', 'category'))


class TestWindowFunctions(BaseTestCase):
    def test_frame(self):
        query = (Register
                 .select(
                     Register.value,
                     fn.AVG(Register.value).over(
                         partition_by=[Register.category],
                         start=Window.preceding(),
                         end=Window.following(2))))
        self.assertSQL(query, (
            'SELECT "t1"."value", AVG("t1"."value") '
            'OVER (PARTITION BY "t1"."category" '
            'ROWS BETWEEN UNBOUNDED PRECEDING AND 2 FOLLOWING) '
            'FROM "register" AS "t1"'), [])

        query = (Register
                 .select(Register.value, fn.AVG(Register.value).over(
                     partition_by=[Register.category],
                     order_by=[Register.value],
                     start=SQL('CURRENT ROW'),
                     end=Window.following())))
        self.assertSQL(query, (
            'SELECT "t1"."value", AVG("t1"."value") '
            'OVER (PARTITION BY "t1"."category" '
            'ORDER BY "t1"."value" '
            'ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) '
            'FROM "register" AS "t1"'), [])

    def test_partition_unordered(self):
        partition = [Register.category]
        query = (Register
                 .select(
                     Register.category,
                     Register.value,
                     fn.AVG(Register.value).over(partition_by=partition))
                 .order_by(Register.id))
        self.assertSQL(query, (
            'SELECT "t1"."category", "t1"."value", AVG("t1"."value") '
            'OVER (PARTITION BY "t1"."category") '
            'FROM "register" AS "t1" ORDER BY "t1"."id"'), [])

    def test_named_window(self):
        window = Window(partition_by=[Register.category])
        query = (Register
                 .select(
                     Register.category,
                     Register.value,
                     fn.AVG(Register.value).over(window))
                 .window(window))

        self.assertSQL(query, (
            'SELECT "t1"."category", "t1"."value", AVG("t1"."value") '
            'OVER w '
            'FROM "register" AS "t1" '
            'WINDOW w AS (PARTITION BY "t1"."category")'), [])

        window = Window(
            partition_by=[Register.category],
            order_by=[Register.value.desc()])
        query = (Register
                 .select(
                     Register.value,
                     fn.RANK().over(window))
                 .window(window))
        self.assertSQL(query, (
            'SELECT "t1"."value", RANK() OVER w '
            'FROM "register" AS "t1" '
            'WINDOW w AS ('
            'PARTITION BY "t1"."category" '
            'ORDER BY "t1"."value" DESC)'), [])

    def test_multiple_windows(self):
        w1 = Window(partition_by=[Register.category]).alias('w1')
        w2 = Window(order_by=[Register.value]).alias('w2')
        query = (Register
                 .select(
                     Register.value,
                     fn.AVG(Register.value).over(w1),
                     fn.RANK().over(w2))
                 .window(w1, w2))
        self.assertSQL(query, (
            'SELECT "t1"."value", AVG("t1"."value") OVER w1, RANK() OVER w2 '
            'FROM "register" AS "t1" '
            'WINDOW w1 AS (PARTITION BY "t1"."category"), '
            'w2 AS (ORDER BY "t1"."value")'), [])

    def test_ordered_unpartitioned(self):
        query = (Register
                 .select(
                     Register.value,
                     fn.RANK().over(order_by=[Register.value])))
        self.assertSQL(query, (
            'SELECT "t1"."value", RANK() OVER (ORDER BY "t1"."value") '
            'FROM "register" AS "t1"'), [])

    def test_empty_over(self):
        query = (Register
                 .select(Register.value, fn.LAG(Register.value, 1).over())
                 .order_by(Register.value))
        self.assertSQL(query, (
            'SELECT "t1"."value", LAG("t1"."value", ?) OVER () '
            'FROM "register" AS "t1" '
            'ORDER BY "t1"."value"'), [1])


class TestSelectFeatures(BaseTestCase):
    def test_reselect(self):
        query = Person.select(Person.name)
        self.assertSQL(query, 'SELECT "t1"."name" FROM "person" AS "t1"', [])

        query = query.columns(Person.id, Person.name, Person.dob)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name", "t1"."dob" '
            'FROM "person" AS "t1"'), [])

    def test_distinct_on(self):
        query = (Note
                 .select(Person.name, Note.content)
                 .join(Person, on=(Note.person_id == Person.id))
                 .order_by(Person.name, Note.content)
                 .distinct(Person.name))
        self.assertSQL(query, (
            'SELECT DISTINCT ON ("t1"."name") '
            '"t1"."name", "t2"."content" '
            'FROM "note" AS "t2" '
            'INNER JOIN "person" AS "t1" ON ("t2"."person_id" = "t1"."id") '
            'ORDER BY "t1"."name", "t2"."content"'), [])

        query = (Person
                 .select(Person.name)
                 .distinct(Person.name))
        self.assertSQL(query, (
            'SELECT DISTINCT ON ("t1"."name") "t1"."name" '
            'FROM "person" AS "t1"'), [])

    def test_distinct(self):
        query = Person.select(Person.name).distinct()
        self.assertSQL(query,
                       'SELECT DISTINCT "t1"."name" FROM "person" AS "t1"', [])

    def test_for_update(self):
        query = (Person
                 .select()
                 .where(Person.name == 'charlie')
                 .for_update())
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name", "t1"."dob" '
            'FROM "person" AS "t1" '
            'WHERE ("t1"."name" = ?) '
            'FOR UPDATE'), ['charlie'], for_update=True)

        query = query.for_update('FOR SHARE NOWAIT')
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."name", "t1"."dob" '
            'FROM "person" AS "t1" '
            'WHERE ("t1"."name" = ?) '
            'FOR SHARE NOWAIT'), ['charlie'], for_update=True)

    def test_parentheses(self):
        query = (Person
                 .select(fn.MAX(
                     fn.IFNULL(1, 10) * 151,
                     fn.IFNULL(None, 10))))
        self.assertSQL(query, (
            'SELECT MAX((IFNULL(?, ?) * ?), IFNULL(?, ?)) '
            'FROM "person" AS "t1"'), [1, 10, 151, None, 10])

        query = (Person
                 .select(Person.name)
                 .where(fn.EXISTS(
                     User.select(User.c.id).where(
                         User.c.username == Person.name))))
        self.assertSQL(query, (
            'SELECT "t1"."name" FROM "person" AS "t1" '
            'WHERE EXISTS('
            'SELECT "t2"."id" FROM "users" AS "t2" '
            'WHERE ("t2"."username" = "t1"."name"))'), [])
