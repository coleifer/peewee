import datetime
import re

from peewee import *
from peewee import Expression

from .base import BaseTestCase
from .base import TestModel
from .base import db
from .base import requires_mysql
from .base import requires_sqlite
from .base import __sql__


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

    def test_select_subselect_function(self):
        exists = fn.EXISTS(Tweet
                           .select(Tweet.c.id)
                           .where(Tweet.c.user_id == User.c.id))
        query = User.select(User.c.username, exists.alias('has_tweet'))
        self.assertSQL(query, (
            'SELECT "t1"."username", EXISTS('
            'SELECT "t2"."id" FROM "tweets" AS "t2" '
            'WHERE ("t2"."user_id" = "t1"."id")) AS "has_tweet" '
            'FROM "users" AS "t1"'), [])

    def test_select_extend(self):
        query = User.select(User.c.id, User.c.username)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1"'), [])

        query = query.select(User.c.username, User.c.is_admin)
        self.assertSQL(query, (
            'SELECT "t1"."username", "t1"."is_admin" FROM "users" AS "t1"'),
            [])

        query = query.select_extend(User.c.is_active, User.c.id)
        self.assertSQL(query, (
            'SELECT "t1"."username", "t1"."is_admin", "t1"."is_active", '
            '"t1"."id" FROM "users" AS "t1"'), [])

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
            'SELECT "t1"."id", "t1"."username", COUNT("t2"."id") AS "ct" '
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
            '(SELECT COUNT("t2"."id") AS "ct" '
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

    def test_simple_cte(self):
        cte = User.select(User.c.id).cte('user_ids')
        query = (User
                 .select(User.c.username)
                 .where(User.c.id.in_(cte))
                 .with_cte(cte))
        self.assertSQL(query, (
            'WITH "user_ids" AS (SELECT "t1"."id" FROM "users" AS "t1") '
            'SELECT "t2"."username" FROM "users" AS "t2" '
            'WHERE ("t2"."id" IN "user_ids")'), [])

    def test_two_ctes(self):
        c1 = User.select(User.c.id).cte('user_ids')
        c2 = User.select(User.c.username).cte('user_names')
        query = (User
                 .select(c1.c.id, c2.c.username)
                 .where((c1.c.id == User.c.id) &
                        (c2.c.username == User.c.username))
                 .with_cte(c1, c2))
        self.assertSQL(query, (
            'WITH "user_ids" AS (SELECT "t1"."id" FROM "users" AS "t1"), '
            '"user_names" AS (SELECT "t1"."username" FROM "users" AS "t1") '
            'SELECT "user_ids"."id", "user_names"."username" '
            'FROM "users" AS "t2" '
            'WHERE (("user_ids"."id" = "t2"."id") AND '
            '("user_names"."username" = "t2"."username"))'), [])

    def test_select_from_cte(self):
        # Use the "select_from()" helper on the CTE object.
        cte = User.select(User.c.username).cte('user_cte')
        query = cte.select_from(cte.c.username).order_by(cte.c.username)
        self.assertSQL(query, (
            'WITH "user_cte" AS (SELECT "t1"."username" FROM "users" AS "t1") '
            'SELECT "user_cte"."username" FROM "user_cte" '
            'ORDER BY "user_cte"."username"'), [])

        # Test selecting from multiple CTEs, which is done manually.
        c1 = User.select(User.c.username).where(User.c.is_admin == 1).cte('c1')
        c2 = User.select(User.c.username).where(User.c.is_staff == 1).cte('c2')
        query = (Select((c1, c2), (c1.c.username, c2.c.username))
                 .with_cte(c1, c2))
        self.assertSQL(query, (
            'WITH "c1" AS ('
            'SELECT "t1"."username" FROM "users" AS "t1" '
            'WHERE ("t1"."is_admin" = ?)), '
            '"c2" AS ('
            'SELECT "t1"."username" FROM "users" AS "t1" '
            'WHERE ("t1"."is_staff" = ?)) '
            'SELECT "c1"."username", "c2"."username" FROM "c1", "c2"'), [1, 1])

    def test_fibonacci_cte(self):
        q1 = Select(columns=(
            Value(1).alias('n'),
            Value(0).alias('fib_n'),
            Value(1).alias('next_fib_n'))).cte('fibonacci', recursive=True)
        n = (q1.c.n + 1).alias('n')
        rterm = Select(columns=(
            n,
            q1.c.next_fib_n,
            q1.c.fib_n + q1.c.next_fib_n)).from_(q1).where(n < 10)

        cte = q1.union_all(rterm)
        query = cte.select_from(cte.c.n, cte.c.fib_n)
        self.assertSQL(query, (
            'WITH RECURSIVE "fibonacci" AS ('
            'SELECT ? AS "n", ? AS "fib_n", ? AS "next_fib_n" '
            'UNION ALL '
            'SELECT ("fibonacci"."n" + ?) AS "n", "fibonacci"."next_fib_n", '
            '("fibonacci"."fib_n" + "fibonacci"."next_fib_n") '
            'FROM "fibonacci" '
            'WHERE ("n" < ?)) '
            'SELECT "fibonacci"."n", "fibonacci"."fib_n" '
            'FROM "fibonacci"'), [1, 0, 1, 1, 10])

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
            'SELECT "t1"."region", SUM("t1"."amount") AS "total_sales" '
            'FROM "orders" AS "t1" '
            'GROUP BY "t1"."region"'
            '), '
            '"top_regions" AS ('
            'SELECT "regional_sales"."region" '
            'FROM "regional_sales" '
            'WHERE ("regional_sales"."total_sales" > '
            '(SELECT (SUM("regional_sales"."total_sales") / ?) '
            'FROM "regional_sales"))'
            ') '
            'SELECT "t2"."region", "t2"."product", '
            'SUM("t2"."quantity") AS "product_units", '
            'SUM("t2"."amount") AS "product_sales" '
            'FROM "orders" AS "t2" '
            'WHERE ('
            '"t2"."region" IN ('
            'SELECT "top_regions"."region" '
            'FROM "top_regions")'
            ') GROUP BY "t2"."region", "t2"."product"'), [10])

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
            'SELECT "t2"."username" '
            'FROM "users" AS "t2" '
            'WHERE ("t2"."admin" = ?) '
            'UNION '
            'SELECT "U2"."id" '
            'FROM "users" AS "U2" '
            'WHERE ("U2"."superuser" = ?)'), ['charlie', True, False])

    def test_compound_operations(self):
        admin = (User
                 .select(User.c.username, Value('admin').alias('role'))
                 .where(User.c.is_admin == True))
        editors = (User
                   .select(User.c.username, Value('editor').alias('role'))
                   .where(User.c.is_editor == True))

        union = admin.union(editors)
        self.assertSQL(union, (
            'SELECT "t1"."username", ? AS "role" '
            'FROM "users" AS "t1" '
            'WHERE ("t1"."is_admin" = ?) '
            'UNION '
            'SELECT "t2"."username", ? AS "role" '
            'FROM "users" AS "t2" '
            'WHERE ("t2"."is_editor" = ?)'), ['admin', 1, 'editor', 1])

        xcept = editors.except_(admin)
        self.assertSQL(xcept, (
            'SELECT "t1"."username", ? AS "role" '
            'FROM "users" AS "t1" '
            'WHERE ("t1"."is_editor" = ?) '
            'EXCEPT '
            'SELECT "t2"."username", ? AS "role" '
            'FROM "users" AS "t2" '
            'WHERE ("t2"."is_admin" = ?)'), ['editor', 1, 'admin', 1])

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
            'ON Magic("t1"."id", "t2"."id") AS "magic"'), [])

    def test_all_clauses(self):
        count = fn.COUNT(Tweet.c.id).alias('ct')
        query = (User
                 .select(User.c.username, count)
                 .join(Tweet, JOIN.LEFT_OUTER,
                       on=(User.c.id == Tweet.c.user_id))
                 .where(User.c.is_admin == 1)
                 .group_by(User.c.username)
                 .having(count > 10)
                 .order_by(count.desc()))
        self.assertSQL(query, (
            'SELECT "t1"."username", COUNT("t2"."id") AS "ct" '
            'FROM "users" AS "t1" '
            'LEFT OUTER JOIN "tweets" AS "t2" '
            'ON ("t1"."id" = "t2"."user_id") '
            'WHERE ("t1"."is_admin" = ?) '
            'GROUP BY "t1"."username" '
            'HAVING ("ct" > ?) '
            'ORDER BY "ct" DESC'), [1, 10])

    def test_in_value_representation(self):
        query = (User
                 .select(User.c.id)
                 .where(User.c.username.in_(['foo', 'bar', 'baz'])))
        self.assertSQL(query, (
            'SELECT "t1"."id" FROM "users" AS "t1" '
            'WHERE ("t1"."username" IN (?, ?, ?))'), ['foo', 'bar', 'baz'])

    def test_tuple_comparison(self):
        name_dob = Tuple(Person.name, Person.dob)
        query = (Person
                 .select(Person.id)
                 .where(name_dob == ('foo', '2017-01-01')))
        expected = ('SELECT "t1"."id" FROM "person" AS "t1" '
                    'WHERE (("t1"."name", "t1"."dob") = (?, ?))')
        self.assertSQL(query, expected, ['foo', '2017-01-01'])

        # Also works specifying rhs values as Tuple().
        query = (Person
                 .select(Person.id)
                 .where(name_dob == Tuple('foo', '2017-01-01')))
        self.assertSQL(query, expected, ['foo', '2017-01-01'])

    def test_empty_in(self):
        query = User.select(User.c.id).where(User.c.username.in_([]))
        self.assertSQL(query, (
            'SELECT "t1"."id" FROM "users" AS "t1" '
            'WHERE (0 = 1)'), [])

        query = User.select(User.c.id).where(User.c.username.not_in([]))
        self.assertSQL(query, (
            'SELECT "t1"."id" FROM "users" AS "t1" '
            'WHERE (1 = 1)'), [])

    def test_add_custom_op(self):
        def mod(lhs, rhs):
            return Expression(lhs, '%', rhs)

        Stat = Table('stats')
        query = (Stat
                 .select(fn.COUNT(Stat.c.id))
                 .where(mod(Stat.c.index, 10) == 0))
        self.assertSQL(query, (
            'SELECT COUNT("t1"."id") FROM "stats" AS "t1" '
            'WHERE (("t1"."index" % ?) = ?)'), [10, 0])


class TestInsertQuery(BaseTestCase):
    def test_insert_simple(self):
        query = User.insert({
            User.c.username: 'charlie',
            User.c.superuser: False,
            User.c.admin: True})
        self.assertSQL(query, (
            'INSERT INTO "users" ("admin", "superuser", "username") '
            'VALUES (?, ?, ?)'), [True, False, 'charlie'])

    @requires_sqlite
    def test_replace_sqlite(self):
        query = User.replace({
            User.c.username: 'charlie',
            User.c.superuser: False})
        self.assertSQL(query, (
            'INSERT OR REPLACE INTO "users" ("superuser", "username") '
            'VALUES (?, ?)'), [False, 'charlie'])

    @requires_mysql
    def test_replace_mysql(self):
        query = User.replace({
            User.c.username: 'charlie',
            User.c.superuser: False})
        self.assertSQL(query, (
            'REPLACE INTO "users" ("superuser", "username") '
            'VALUES (?, ?)'), [False, 'charlie'])

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
            'WITH "foo" AS (SELECT "t1"."username" FROM "users" AS "t1") '
            'INSERT INTO "person" ("name") '
            'SELECT "foo"."username" FROM "foo"'), [])

    def test_insert_single_value_query(self):
        query = Person.select(Person.id).where(Person.name == 'huey')
        insert = Note.insert({
            Note.person_id: query,
            Note.content: 'hello'})
        self.assertSQL(insert, (
            'INSERT INTO "note" ("content", "person_id") VALUES (?, '
            '(SELECT "t1"."id" FROM "person" AS "t1" '
            'WHERE ("t1"."name" = ?)))'), ['hello', 'huey'])

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
        count = fn.COUNT(Tweet.c.id).alias('ct')
        subquery = (User
                    .select(User.c.id, count)
                    .join(Tweet, on=(Tweet.c.user_id == User.c.id))
                    .group_by(User.c.id)
                    .having(count > 100))
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
            'SELECT "users"."id", COUNT("t1"."id") AS "ct" '
            'FROM "users" AS "users" '
            'INNER JOIN "tweets" AS "t1" '
            'ON ("t1"."user_id" = "users"."id") '
            'GROUP BY "users"."id" '
            'HAVING ("ct" > ?)))'), [0, True, 100])

    def test_update_from(self):
        data = [(1, 'u1-x'), (2, 'u2-x')]
        vl = ValuesList(data, columns=('id', 'username'), alias='tmp')
        query = (User
                 .update(username=QualifiedNames(vl.c.username))
                 .from_(vl)
                 .where(QualifiedNames(User.c.id == vl.c.id)))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = "tmp"."username" '
            'FROM (VALUES (?, ?), (?, ?)) AS "tmp"("id", "username") '
            'WHERE ("users"."id" = "tmp"."id")'), [1, 'u1-x', 2, 'u2-x'])

        subq = vl.select(vl.c.id, vl.c.username)
        query = (User
                 .update({User.c.username: QualifiedNames(subq.c.username)})
                 .from_(subq)
                 .where(QualifiedNames(User.c.id == subq.c.id)))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = "t1"."username" FROM ('
            'SELECT "tmp"."id", "tmp"."username" '
            'FROM (VALUES (?, ?), (?, ?)) AS "tmp"("id", "username")) AS "t1" '
            'WHERE ("users"."id" = "t1"."id")'), [1, 'u1-x', 2, 'u2-x'])

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
            'DELETE FROM "users" WHERE ("username" != ?) LIMIT ?',
            ['charlie', 3])

    def test_delete_subquery(self):
        count = fn.COUNT(Tweet.c.id).alias('ct')
        subquery = (User
                    .select(User.c.id, count)
                    .join(Tweet, on=(Tweet.c.user_id == User.c.id))
                    .group_by(User.c.id)
                    .having(count > 100))
        query = (User
                 .delete()
                 .where(User.c.id << subquery))
        self.assertSQL(query, (
            'DELETE FROM "users" '
            'WHERE ("id" IN ('
            'SELECT "users"."id", COUNT("t1"."id") AS "ct" '
            'FROM "users" AS "users" '
            'INNER JOIN "tweets" AS "t1" ON ("t1"."user_id" = "users"."id") '
            'GROUP BY "users"."id" '
            'HAVING ("ct" > ?)))'), [100])

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
            '(SELECT "t1"."id" FROM "users" AS "t1" WHERE ("t1"."admin" = ?)) '
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

    def test_ordered_unpartitioned(self):
        query = (Register
                 .select(
                     Register.value,
                     fn.RANK().over(order_by=[Register.value])))
        self.assertSQL(query, (
            'SELECT "t1"."value", RANK() OVER (ORDER BY "t1"."value") '
            'FROM "register" AS "t1"'), [])

    def test_ordered_partitioned(self):
        query = Register.select(
            Register.value,
            fn.SUM(Register.value).over(
                order_by=Register.id,
                partition_by=Register.category).alias('rsum'))
        self.assertSQL(query, (
            'SELECT "t1"."value", SUM("t1"."value") '
            'OVER (PARTITION BY "t1"."category" ORDER BY "t1"."id") AS "rsum" '
            'FROM "register" AS "t1"'), [])

    def test_empty_over(self):
        query = (Register
                 .select(Register.value, fn.LAG(Register.value, 1).over())
                 .order_by(Register.value))
        self.assertSQL(query, (
            'SELECT "t1"."value", LAG("t1"."value", ?) OVER () '
            'FROM "register" AS "t1" '
            'ORDER BY "t1"."value"'), [1])

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
                     start=Window.CURRENT_ROW,
                     end=Window.following())))
        self.assertSQL(query, (
            'SELECT "t1"."value", AVG("t1"."value") '
            'OVER (PARTITION BY "t1"."category" '
            'ORDER BY "t1"."value" '
            'ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) '
            'FROM "register" AS "t1"'), [])

    def test_frame_types(self):
        def assertFrame(over_kwargs, expected):
            query = Register.select(
                Register.value,
                fn.SUM(Register.value).over(**over_kwargs))
            sql, params = __sql__(query)
            match_obj = re.search('OVER \((.*?)\) FROM', sql)
            self.assertTrue(match_obj is not None)
            self.assertEqual(match_obj.groups()[0], expected)
            self.assertEqual(params, [])

        # No parameters -- empty OVER().
        assertFrame({}, (''))
        # Explicitly specify RANGE / ROWS frame-types.
        assertFrame({'frame_type': Window.RANGE}, 'RANGE UNBOUNDED PRECEDING')
        assertFrame({'frame_type': Window.ROWS}, 'ROWS UNBOUNDED PRECEDING')

        # Start and end boundaries.
        assertFrame({'start': Window.preceding(), 'end': Window.following()},
                    'ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING')
        assertFrame({
            'start': Window.preceding(),
            'end': Window.following(),
            'frame_type': Window.RANGE,
        }, 'RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING')
        assertFrame({
            'start': Window.preceding(),
            'end': Window.following(),
            'frame_type': Window.ROWS,
        }, 'ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING')

        # Start boundary.
        assertFrame({'start': Window.preceding()}, 'ROWS UNBOUNDED PRECEDING')
        assertFrame({'start': Window.preceding(), 'frame_type': Window.RANGE},
                    'RANGE UNBOUNDED PRECEDING')
        assertFrame({'start': Window.preceding(), 'frame_type': Window.ROWS},
                    'ROWS UNBOUNDED PRECEDING')

        # Ordered or partitioned.
        assertFrame({'order_by': Register.value}, 'ORDER BY "t1"."value"')
        assertFrame({'frame_type': Window.RANGE, 'order_by': Register.value},
                    'ORDER BY "t1"."value" RANGE UNBOUNDED PRECEDING')
        assertFrame({'frame_type': Window.ROWS, 'order_by': Register.value},
                    'ORDER BY "t1"."value" ROWS UNBOUNDED PRECEDING')
        assertFrame({'partition_by': Register.category},
                    'PARTITION BY "t1"."category"')
        assertFrame({
            'frame_type': Window.RANGE,
            'partition_by': Register.category,
        }, 'PARTITION BY "t1"."category" RANGE UNBOUNDED PRECEDING')
        assertFrame({
            'frame_type': Window.ROWS,
            'partition_by': Register.category,
        }, 'PARTITION BY "t1"."category" ROWS UNBOUNDED PRECEDING')

        # Ordering and boundaries.
        assertFrame({'order_by': Register.value, 'start': Window.CURRENT_ROW,
                     'end': Window.following()},
                    ('ORDER BY "t1"."value" '
                     'ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING'))
        assertFrame({'order_by': Register.value, 'start': Window.CURRENT_ROW,
                     'end': Window.following(), 'frame_type': Window.RANGE},
                    ('ORDER BY "t1"."value" '
                     'RANGE BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING'))
        assertFrame({'order_by': Register.value, 'start': Window.CURRENT_ROW,
                     'end': Window.following(), 'frame_type': Window.ROWS},
                    ('ORDER BY "t1"."value" '
                     'ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING'))

    def test_running_total(self):
        EventLog = Table('evtlog', ('id', 'timestamp', 'data'))

        w = fn.SUM(EventLog.timestamp).over(order_by=[EventLog.timestamp])
        query = (EventLog
                 .select(EventLog.timestamp, EventLog.data, w.alias('elapsed'))
                 .order_by(EventLog.timestamp))
        self.assertSQL(query, (
            'SELECT "t1"."timestamp", "t1"."data", '
            'SUM("t1"."timestamp") OVER (ORDER BY "t1"."timestamp") '
            'AS "elapsed" '
            'FROM "evtlog" AS "t1" ORDER BY "t1"."timestamp"'), [])

        w = fn.SUM(EventLog.timestamp).over(
            order_by=[EventLog.timestamp],
            partition_by=[EventLog.data])
        query = (EventLog
                 .select(EventLog.timestamp, EventLog.data, w.alias('elapsed'))
                 .order_by(EventLog.timestamp))
        self.assertSQL(query, (
            'SELECT "t1"."timestamp", "t1"."data", '
            'SUM("t1"."timestamp") OVER '
            '(PARTITION BY "t1"."data" ORDER BY "t1"."timestamp") AS "elapsed"'
            ' FROM "evtlog" AS "t1" ORDER BY "t1"."timestamp"'), [])

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

    def test_alias_window(self):
        w = Window(order_by=Register.value).alias('wx')
        query = Register.select(Register.value, fn.RANK().over(w)).window(w)

        # We can re-alias the window and it's updated alias is reflected
        # correctly in the final query.
        w.alias('wz')
        self.assertSQL(query, (
            'SELECT "t1"."value", RANK() OVER wz '
            'FROM "register" AS "t1" '
            'WINDOW wz AS (ORDER BY "t1"."value")'), [])

    def test_reuse_window(self):
        EventLog = Table('evt', ('id', 'timestamp', 'key'))
        window = Window(partition_by=[EventLog.key],
                        order_by=[EventLog.timestamp])
        query = (EventLog
                 .select(EventLog.timestamp, EventLog.key,
                         fn.NTILE(4).over(window).alias('quartile'),
                         fn.NTILE(5).over(window).alias('quintile'),
                         fn.NTILE(100).over(window).alias('percentile'))
                 .order_by(EventLog.timestamp)
                 .window(window))
        self.assertSQL(query, (
            'SELECT "t1"."timestamp", "t1"."key", '
            'NTILE(?) OVER w AS "quartile", '
            'NTILE(?) OVER w AS "quintile", '
            'NTILE(?) OVER w AS "percentile" '
            'FROM "evt" AS "t1" '
            'WINDOW w AS ('
            'PARTITION BY "t1"."key" ORDER BY "t1"."timestamp") '
            'ORDER BY "t1"."timestamp"'), [4, 5, 100])

    def test_filter_clause(self):
        condsum = fn.SUM(Register.value).filter(Register.value > 1).over(
            order_by=[Register.id], partition_by=[Register.category],
            start=Window.preceding(1))
        query = (Register
                 .select(Register.category, Register.value, condsum)
                 .order_by(Register.category))
        self.assertSQL(query, (
            'SELECT "t1"."category", "t1"."value", SUM("t1"."value") FILTER ('
            'WHERE ("t1"."value" > ?)) OVER (PARTITION BY "t1"."category" '
            'ORDER BY "t1"."id" ROWS 1 PRECEDING) '
            'FROM "register" AS "t1" '
            'ORDER BY "t1"."category"'), [1])


class TestValuesList(BaseTestCase):
    _data = [(1, 'one'), (2, 'two'), (3, 'three')]

    def test_values_list(self):
        vl = ValuesList(self._data)

        query = vl.select(SQL('*'))
        self.assertSQL(query, (
            'SELECT * FROM (VALUES (?, ?), (?, ?), (?, ?)) AS "t1"'),
            [1, 'one', 2, 'two', 3, 'three'])

    def test_values_list_named_columns(self):
        vl = ValuesList(self._data).columns('idx', 'name')
        query = (vl
                 .select(vl.c.idx, vl.c.name)
                 .order_by(vl.c.idx))
        self.assertSQL(query, (
            'SELECT "t1"."idx", "t1"."name" '
            'FROM (VALUES (?, ?), (?, ?), (?, ?)) AS "t1"("idx", "name") '
            'ORDER BY "t1"."idx"'), [1, 'one', 2, 'two', 3, 'three'])

    def test_named_values_list(self):
        vl = ValuesList(self._data, ['idx', 'name']).alias('vl')
        query = (vl
                 .select(vl.c.idx, vl.c.name)
                 .order_by(vl.c.idx))
        self.assertSQL(query, (
            'SELECT "vl"."idx", "vl"."name" '
            'FROM (VALUES (?, ?), (?, ?), (?, ?)) AS "vl"("idx", "name") '
            'ORDER BY "vl"."idx"'), [1, 'one', 2, 'two', 3, 'three'])

    def test_docs_examples(self):
        data = [(1, 'first'), (2, 'second')]
        vl = ValuesList(data, columns=('idx', 'name'))
        query = (vl
                 .select(vl.c.idx, vl.c.name)
                 .order_by(vl.c.idx))
        self.assertSQL(query, (
            'SELECT "t1"."idx", "t1"."name" '
            'FROM (VALUES (?, ?), (?, ?)) AS "t1"("idx", "name") '
            'ORDER BY "t1"."idx"'), [1, 'first', 2, 'second'])

        vl = ValuesList([(1, 'first'), (2, 'second')])
        vl = vl.columns('idx', 'name').alias('v')
        query = vl.select(vl.c.idx, vl.c.name)
        self.assertSQL(query, (
            'SELECT "v"."idx", "v"."name" '
            'FROM (VALUES (?, ?), (?, ?)) AS "v"("idx", "name")'),
            [1, 'first', 2, 'second'])


class TestCaseFunction(BaseTestCase):
    def test_case_function(self):
        NameNum = Table('nn', ('name', 'number'))

        query = (NameNum
                 .select(NameNum.name, Case(NameNum.number, (
                     (1, 'one'),
                     (2, 'two')), '?').alias('num_str')))
        self.assertSQL(query, (
            'SELECT "t1"."name", CASE "t1"."number" '
            'WHEN ? THEN ? '
            'WHEN ? THEN ? '
            'ELSE ? END AS "num_str" '
            'FROM "nn" AS "t1"'), [1, 'one', 2, 'two', '?'])

        query = (NameNum
                 .select(NameNum.name, Case(None, (
                     (NameNum.number == 1, 'one'),
                     (NameNum.number == 2, 'two')), '?')))
        self.assertSQL(query, (
            'SELECT "t1"."name", CASE '
            'WHEN ("t1"."number" = ?) THEN ? '
            'WHEN ("t1"."number" = ?) THEN ? '
            'ELSE ? END '
            'FROM "nn" AS "t1"'), [1, 'one', 2, 'two', '?'])


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

    def test_distinct_count(self):
        query = Person.select(fn.COUNT(Person.name.distinct()))
        self.assertSQL(query, (
            'SELECT COUNT(DISTINCT "t1"."name") FROM "person" AS "t1"'), [])

    def test_filtered_count(self):
        filtered_count = (fn.COUNT(Person.name)
                          .filter(Person.dob < datetime.date(2000, 1, 1)))
        query = Person.select(fn.COUNT(Person.name), filtered_count)
        self.assertSQL(query, (
            'SELECT COUNT("t1"."name"), COUNT("t1"."name") '
            'FILTER (WHERE ("t1"."dob" < ?)) '
            'FROM "person" AS "t1"'), [datetime.date(2000, 1, 1)])

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


#Person = Table('person', ['id', 'name', 'dob'])

class TestOnConflictSqlite(BaseTestCase):
    database = SqliteDatabase(None)

    def test_replace(self):
        query = Person.insert(name='huey').on_conflict('replace')
        self.assertSQL(query, (
            'INSERT OR REPLACE INTO "person" ("name") VALUES (?)'), ['huey'])

    def test_ignore(self):
        query = Person.insert(name='huey').on_conflict('ignore')
        self.assertSQL(query, (
            'INSERT OR IGNORE INTO "person" ("name") VALUES (?)'), ['huey'])

    def test_update_not_supported(self):
        query = Person.insert(name='huey').on_conflict(
            preserve=(Person.dob,),
            update={Person.name: Person.name.concat(' (updated)')})
        with self.assertRaisesCtx(ValueError):
            self.database.get_sql_context().parse(query)


class TestOnConflictMySQL(BaseTestCase):
    database = MySQLDatabase(None)

    def test_replace(self):
        query = Person.insert(name='huey').on_conflict('replace')
        self.assertSQL(query, (
            'REPLACE INTO "person" ("name") VALUES (?)'), ['huey'])

    def test_ignore(self):
        query = Person.insert(name='huey').on_conflict('ignore')
        self.assertSQL(query, (
            'INSERT IGNORE INTO "person" ("name") VALUES (?)'), ['huey'])

    def test_update(self):
        dob = datetime.date(2010, 1, 1)
        query = (Person
                 .insert(name='huey', dob=dob)
                 .on_conflict(
                     preserve=(Person.dob,),
                     update={Person.name: Person.name.concat('-x')}))
        self.assertSQL(query, (
            'INSERT INTO "person" ("dob", "name") VALUES (?, ?) '
            'ON DUPLICATE KEY '
            'UPDATE "dob" = VALUES("dob"), "name" = ("name" || ?)'),
            [dob, 'huey', '-x'])

        query = (Person
                 .insert(name='huey', dob=dob)
                 .on_conflict(preserve='dob'))
        self.assertSQL(query, (
            'INSERT INTO "person" ("dob", "name") VALUES (?, ?) '
            'ON DUPLICATE KEY '
            'UPDATE "dob" = VALUES("dob")'), [dob, 'huey'])

    def test_where_not_supported(self):
        query = Person.insert(name='huey').on_conflict(
            preserve=(Person.dob,),
            where=(Person.name == 'huey'))
        with self.assertRaisesCtx(ValueError):
            self.database.get_sql_context().parse(query)


class TestOnConflictPostgresql(BaseTestCase):
    database = PostgresqlDatabase(None)

    def test_ignore(self):
        query = Person.insert(name='huey').on_conflict('ignore')
        self.assertSQL(query, (
            'INSERT INTO "person" ("name") VALUES (?) '
            'ON CONFLICT DO NOTHING'), ['huey'])

    def test_conflict_target_required(self):
        query = Person.insert(name='huey').on_conflict(preserve=(Person.dob,))
        with self.assertRaisesCtx(ValueError):
            self.database.get_sql_context().parse(query)

    def test_conflict_resolution_required(self):
        query = Person.insert(name='huey').on_conflict(conflict_target='name')
        with self.assertRaisesCtx(ValueError):
            self.database.get_sql_context().parse(query)

    def test_update(self):
        dob = datetime.date(2010, 1, 1)
        query = (Person
                 .insert(name='huey', dob=dob)
                 .on_conflict(
                     conflict_target=(Person.name,),
                     preserve=(Person.dob,),
                     update={Person.name: Person.name.concat('-x')}))
        self.assertSQL(query, (
            'INSERT INTO "person" ("dob", "name") VALUES (?, ?) '
            'ON CONFLICT ("name") DO '
            'UPDATE SET "dob" = EXCLUDED."dob", '
            '"name" = ("person"."name" || ?)'),
            [dob, 'huey', '-x'])

        query = (Person
                 .insert(name='huey', dob=dob)
                 .on_conflict(
                     conflict_target='name',
                     preserve='dob'))
        self.assertSQL(query, (
            'INSERT INTO "person" ("dob", "name") VALUES (?, ?) '
            'ON CONFLICT ("name") DO '
            'UPDATE SET "dob" = EXCLUDED."dob"'), [dob, 'huey'])

        query = (Person
                 .insert(name='huey')
                 .on_conflict(
                     conflict_target=Person.name,
                     preserve=Person.dob,
                     update={Person.name: Person.name.concat('-x')},
                     where=(Person.name != 'zaizee')))
        self.assertSQL(query, (
            'INSERT INTO "person" ("name") VALUES (?) '
            'ON CONFLICT ("name") DO '
            'UPDATE SET "dob" = EXCLUDED."dob", '
            '"name" = ("person"."name" || ?) '
            'WHERE ("person"."name" != ?)'), ['huey', '-x', 'zaizee'])


#Person = Table('person', ['id', 'name', 'dob'])
#Note = Table('note', ['id', 'person_id', 'content'])

class TestIndex(BaseTestCase):
    database = SqliteDatabase(None)

    def test_simple_index(self):
        pidx = Index('person_name', Person, (Person.name,), unique=True)
        self.assertSQL(pidx, (
            'CREATE UNIQUE INDEX "person_name" ON "person" ("name")'), [])

        pidx = pidx.where(Person.dob > datetime.date(1950, 1, 1))
        self.assertSQL(pidx, (
            'CREATE UNIQUE INDEX "person_name" ON "person" '
            '("name") WHERE ("dob" > ?)'), [datetime.date(1950, 1, 1)])

    def test_advanced_index(self):
        Article = Table('article')
        aidx = Index('foo_idx', Article, (
            Article.c.status,
            Article.c.timestamp.desc(),
            fn.SUBSTR(Article.c.title, 1, 1)), safe=True)
        self.assertSQL(aidx, (
            'CREATE INDEX IF NOT EXISTS "foo_idx" ON "article" '
            '("status", "timestamp" DESC, SUBSTR("title", ?, ?))'), [1, 1])

        aidx = aidx.where(Article.c.flags.bin_and(4) == 4)
        self.assertSQL(aidx, (
            'CREATE INDEX IF NOT EXISTS "foo_idx" ON "article" '
            '("status", "timestamp" DESC, SUBSTR("title", ?, ?)) '
            'WHERE (("flags" & ?) = ?)'), [1, 1, 4, 4])

    def test_str_cols(self):
        uidx = Index('users_info', User, ('username DESC', 'id'))
        self.assertSQL(uidx, (
            'CREATE INDEX "users_info" ON "users" (username DESC, id)'), [])
