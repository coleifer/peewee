import datetime
import re

from peewee import *
from peewee import Expression
from peewee import query_to_string

from .base import BaseTestCase
from .base import TestModel
from .base import db
from .base import requires_mysql
from .base import requires_sqlite
from .base import __sql__


User = Table('users')
Tweet = Table('tweets')
Person = Table('person', ['id', 'name', 'dob'], primary_key='id')
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

    def test_select_in_list_of_values(self):
        names_vals = [
            ['charlie', 'huey'],
            ('charlie', 'huey'),
            set(('charlie', 'huey')),
            frozenset(('charlie', 'huey'))]

        for names in names_vals:
            query = (Person
                     .select()
                     .where(Person.name.in_(names)))
            sql, params = Context().sql(query).query()
            self.assertEqual(sql, (
                'SELECT "t1"."id", "t1"."name", "t1"."dob" '
                'FROM "person" AS "t1" '
                'WHERE ("t1"."name" IN (?, ?))'))
            self.assertEqual(sorted(params), ['charlie', 'huey'])

    def test_select_subselect_function(self):
        # For functions whose only argument is a subquery, we do not need to
        # include additional parentheses -- in fact, some databases will report
        # a syntax error if we do.
        exists = fn.EXISTS(Tweet
                           .select(Tweet.c.id)
                           .where(Tweet.c.user_id == User.c.id))
        query = User.select(User.c.username, exists.alias('has_tweet'))
        self.assertSQL(query, (
            'SELECT "t1"."username", EXISTS('
            'SELECT "t2"."id" FROM "tweets" AS "t2" '
            'WHERE ("t2"."user_id" = "t1"."id")) AS "has_tweet" '
            'FROM "users" AS "t1"'), [])

        # If the function has more than one argument, we need to wrap the
        # subquery in parentheses.
        Stat = Table('stat', ['id', 'val'])
        SA = Stat.alias('sa')
        subq = SA.select(fn.SUM(SA.val).alias('val_sum'))
        query = Stat.select(fn.COALESCE(subq, 0))
        self.assertSQL(query, (
            'SELECT COALESCE(('
            'SELECT SUM("sa"."val") AS "val_sum" FROM "stat" AS "sa"'
            '), ?) FROM "stat" AS "t1"'), [0])

    def test_subquery_in_select_sql(self):
        subq = User.select(User.c.id).where(User.c.username == 'huey')
        query = Tweet.select(Tweet.c.content,
                             Tweet.c.user_id.in_(subq).alias('is_huey'))
        self.assertSQL(query, (
            'SELECT "t1"."content", ("t1"."user_id" IN ('
            'SELECT "t2"."id" FROM "users" AS "t2" WHERE ("t2"."username" = ?)'
            ')) AS "is_huey" FROM "tweets" AS "t1"'), ['huey'])

        # If we explicitly specify an alias, it will be included.
        subq = subq.alias('sq')
        query = Tweet.select(Tweet.c.content,
                             Tweet.c.user_id.in_(subq).alias('is_huey'))
        self.assertSQL(query, (
            'SELECT "t1"."content", ("t1"."user_id" IN ('
            'SELECT "t2"."id" FROM "users" AS "t2" WHERE ("t2"."username" = ?)'
            ') AS "sq") AS "is_huey" FROM "tweets" AS "t1"'), ['huey'])

    def test_subquery_in_select_expression_sql(self):
        Point = Table('point', ('x', 'y'))
        PA = Point.alias('pa')

        subq = PA.select(fn.SUM(PA.y).alias('sa')).where(PA.x == Point.x)
        query = (Point
                 .select(Point.x, Point.y, subq.alias('sy'))
                 .order_by(Point.x, Point.y))
        self.assertSQL(query, (
            'SELECT "t1"."x", "t1"."y", ('
            'SELECT SUM("pa"."y") AS "sa" FROM "point" AS "pa" '
            'WHERE ("pa"."x" = "t1"."x")) AS "sy" '
            'FROM "point" AS "t1" '
            'ORDER BY "t1"."x", "t1"."y"'), [])

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

    def test_orwhere(self):
        query = (Person
                 .select(Person.name)
                 .orwhere(Person.dob > datetime.date(1980, 1, 1))
                 .orwhere(Person.dob < datetime.date(1950, 1, 1)))
        self.assertSQL(query, (
            'SELECT "t1"."name" '
            'FROM "person" AS "t1" '
            'WHERE (("t1"."dob" > ?) OR ("t1"."dob" < ?))'),
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

    def test_subquery_in_expr(self):
        Team = Table('team')
        Challenge = Table('challenge')
        subq = Team.select(fn.COUNT(Team.c.id) + 1)
        query = (Challenge
                 .select((Challenge.c.points / subq).alias('score'))
                 .order_by(SQL('score')))
        self.assertSQL(query, (
            'SELECT ("t1"."points" / ('
            'SELECT (COUNT("t2"."id") + ?) FROM "team" AS "t2")) AS "score" '
            'FROM "challenge" AS "t1" ORDER BY score'), [1])

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

    def test_materialize_cte(self):
        cases = (
            (True, 'MATERIALIZED '),
            (False, 'NOT MATERIALIZED '),
            (None, ''))
        for materialized, clause in cases:
            cte = (User
                   .select(User.c.id)
                   .cte('user_ids', materialized=materialized))
            query = cte.select_from(cte.c.id).where(cte.c.id < 10)
            self.assertSQL(query, (
                'WITH "user_ids" AS %s('
                'SELECT "t1"."id" FROM "users" AS "t1") '
                'SELECT "user_ids"."id" FROM "user_ids" '
                'WHERE ("user_ids"."id" < ?)') % clause, [10])

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

    def test_cte_with_count(self):
        cte = User.select(User.c.id).cte('user_ids')
        query = (User
                 .select(User.c.username)
                 .join(cte, on=(User.c.id == cte.c.id))
                 .with_cte(cte))
        count = Select([query], [fn.COUNT(SQL('1'))])
        self.assertSQL(count, (
            'SELECT COUNT(1) FROM ('
            'WITH "user_ids" AS (SELECT "t1"."id" FROM "users" AS "t1") '
            'SELECT "t2"."username" FROM "users" AS "t2" '
            'INNER JOIN "user_ids" ON ("t2"."id" = "user_ids"."id")) '
            'AS "t3"'), [])

    def test_cte_subquery_in_expression(self):
        Order = Table('order', ('id', 'description'))
        Item = Table('item', ('id', 'order_id', 'description'))

        cte = Order.select(fn.MAX(Order.id).alias('max_id')).cte('max_order')
        qexpr = (Order
                 .select(Order.id)
                 .join(cte, on=(Order.id == cte.c.max_id))
                 .with_cte(cte))
        query = (Item
                 .select(Item.id, Item.order_id, Item.description)
                 .where(Item.order_id.in_(qexpr)))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."order_id", "t1"."description" '
            'FROM "item" AS "t1" '
            'WHERE ("t1"."order_id" IN ('
            'WITH "max_order" AS ('
            'SELECT MAX("t2"."id") AS "max_id" FROM "order" AS "t2") '
            'SELECT "t3"."id" '
            'FROM "order" AS "t3" '
            'INNER JOIN "max_order" '
            'ON ("t3"."id" = "max_order"."max_id")))'), [])

    def test_multi_update_cte(self):
        data = [(i, 'u%sx' % i) for i in range(1, 3)]
        vl = ValuesList(data)
        cte = vl.select().cte('uv', columns=('id', 'username'))
        subq = cte.select(cte.c.username).where(cte.c.id == User.c.id)
        query = (User
                 .update(username=subq)
                 .where(User.c.id.in_(cte.select(cte.c.id)))
                 .with_cte(cte))
        self.assertSQL(query, (
            'WITH "uv" ("id", "username") AS ('
            'SELECT * FROM (VALUES (?, ?), (?, ?)) AS "t1") '
            'UPDATE "users" SET "username" = ('
            'SELECT "uv"."username" FROM "uv" '
            'WHERE ("uv"."id" = "users"."id")) '
            'WHERE ("users"."id" IN (SELECT "uv"."id" FROM "uv"))'),
            [1, 'u1x', 2, 'u2x'])

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

    def test_compound_parentheses_handling(self):
        admin = (User
                 .select(User.c.username, Value('admin').alias('role'))
                 .where(User.c.is_admin == True)
                 .order_by(User.c.id.desc())
                 .limit(3))
        editors = (User
                   .select(User.c.username, Value('editor').alias('role'))
                   .where(User.c.is_editor == True)
                   .order_by(User.c.id.desc())
                   .limit(5))

        self.assertSQL((admin | editors), (
            '(SELECT "t1"."username", ? AS "role" FROM "users" AS "t1" '
            'WHERE ("t1"."is_admin" = ?) ORDER BY "t1"."id" DESC LIMIT ?) '
            'UNION '
            '(SELECT "t2"."username", ? AS "role" FROM "users" AS "t2" '
            'WHERE ("t2"."is_editor" = ?) ORDER BY "t2"."id" DESC LIMIT ?)'),
            ['admin', 1, 3, 'editor', 1, 5], compound_select_parentheses=True)

        Reg = Table('register', ('value',))
        lhs = Reg.select().where(Reg.value < 2)
        rhs = Reg.select().where(Reg.value > 7)
        compound = lhs | rhs

        for csq_setting in (1, 2):
            self.assertSQL(compound, (
                '(SELECT "t1"."value" FROM "register" AS "t1" '
                'WHERE ("t1"."value" < ?)) '
                'UNION '
                '(SELECT "t2"."value" FROM "register" AS "t2" '
                'WHERE ("t2"."value" > ?))'),
                [2, 7], compound_select_parentheses=csq_setting)

        rhs2 = Reg.select().where(Reg.value == 5)
        c2 = compound | rhs2

        # CSQ = always, we get nested parentheses.
        self.assertSQL(c2, (
            '((SELECT "t1"."value" FROM "register" AS "t1" '
            'WHERE ("t1"."value" < ?)) '
            'UNION '
            '(SELECT "t2"."value" FROM "register" AS "t2" '
            'WHERE ("t2"."value" > ?))) '
            'UNION '
            '(SELECT "t2"."value" FROM "register" AS "t2" '
            'WHERE ("t2"."value" = ?))'),
            [2, 7, 5], compound_select_parentheses=1)  # Always.

        # CSQ = unnested, no nesting but all individual queries have parens.
        self.assertSQL(c2, (
            '(SELECT "t1"."value" FROM "register" AS "t1" '
            'WHERE ("t1"."value" < ?)) '
            'UNION '
            '(SELECT "t2"."value" FROM "register" AS "t2" '
            'WHERE ("t2"."value" > ?)) '
            'UNION '
            '(SELECT "t2"."value" FROM "register" AS "t2" '
            'WHERE ("t2"."value" = ?))'),
            [2, 7, 5], compound_select_parentheses=2)  # Un-nested.

    def test_compound_select_order_limit(self):
        A = Table('a', ('col_a',))
        B = Table('b', ('col_b',))
        C = Table('c', ('col_c',))
        q1 = A.select(A.col_a.alias('foo'))
        q2 = B.select(B.col_b.alias('foo'))
        q3 = C.select(C.col_c.alias('foo'))
        qc = (q1 | q2 | q3)
        qc = qc.order_by(qc.c.foo.desc()).limit(3)

        self.assertSQL(qc, (
            'SELECT "t1"."col_a" AS "foo" FROM "a" AS "t1" UNION '
            'SELECT "t2"."col_b" AS "foo" FROM "b" AS "t2" UNION '
            'SELECT "t3"."col_c" AS "foo" FROM "c" AS "t3" '
            'ORDER BY "foo" DESC LIMIT ?'), [3])

        self.assertSQL(qc, (
            '((SELECT "t1"."col_a" AS "foo" FROM "a" AS "t1") UNION '
            '(SELECT "t2"."col_b" AS "foo" FROM "b" AS "t2")) UNION '
            '(SELECT "t3"."col_c" AS "foo" FROM "c" AS "t3") '
            'ORDER BY "foo" DESC LIMIT ?'),
            [3], compound_select_parentheses=1)

    def test_compound_select_as_subquery(self):
        A = Table('a', ('col_a',))
        B = Table('b', ('col_b',))
        q1 = A.select(A.col_a.alias('foo'))
        q2 = B.select(B.col_b.alias('foo'))
        union = q1 | q2

        # Create an outer query and do grouping.
        outer = (union
                 .select_from(union.c.foo, fn.COUNT(union.c.foo).alias('ct'))
                 .group_by(union.c.foo))
        self.assertSQL(outer, (
            'SELECT "t1"."foo", COUNT("t1"."foo") AS "ct" FROM ('
            'SELECT "t2"."col_a" AS "foo" FROM "a" AS "t2" UNION '
            'SELECT "t3"."col_b" AS "foo" FROM "b" AS "t3") AS "t1" '
            'GROUP BY "t1"."foo"'), [])

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

    def test_order_by_collate(self):
        query = (User
                 .select(User.c.username)
                 .order_by(User.c.username.asc(collation='binary')))
        self.assertSQL(query, (
            'SELECT "t1"."username" FROM "users" AS "t1" '
            'ORDER BY "t1"."username" ASC COLLATE binary'), [])

    def test_order_by_nulls(self):
        query = (User
                 .select(User.c.username)
                 .order_by(User.c.ts.desc(nulls='LAST')))
        self.assertSQL(query, (
            'SELECT "t1"."username" FROM "users" AS "t1" '
            'ORDER BY "t1"."ts" DESC NULLS LAST'), [], nulls_ordering=True)
        self.assertSQL(query, (
            'SELECT "t1"."username" FROM "users" AS "t1" '
            'ORDER BY CASE WHEN ("t1"."ts" IS ?) THEN ? ELSE ? END, '
            '"t1"."ts" DESC'), [None, 1, 0], nulls_ordering=False)

        query = (User
                 .select(User.c.username)
                 .order_by(User.c.ts.desc(nulls='first')))
        self.assertSQL(query, (
            'SELECT "t1"."username" FROM "users" AS "t1" '
            'ORDER BY "t1"."ts" DESC NULLS first'), [], nulls_ordering=True)
        self.assertSQL(query, (
            'SELECT "t1"."username" FROM "users" AS "t1" '
            'ORDER BY CASE WHEN ("t1"."ts" IS ?) THEN ? ELSE ? END, '
            '"t1"."ts" DESC'), [None, 0, 1], nulls_ordering=False)

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

    def test_tuple_comparison_subquery(self):
        PA = Person.alias('pa')
        subquery = (PA
                    .select(PA.name, PA.id)
                    .where(PA.name != 'huey'))

        query = (Person
                 .select(Person.name)
                 .where(Tuple(Person.name, Person.id).in_(subquery)))
        self.assertSQL(query, (
            'SELECT "t1"."name" FROM "person" AS "t1" '
            'WHERE (("t1"."name", "t1"."id") IN ('
            'SELECT "pa"."name", "pa"."id" FROM "person" AS "pa" '
            'WHERE ("pa"."name" != ?)))'), ['huey'])

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

    def test_where_convert_to_is_null(self):
        Note = Table('notes', ('id', 'content', 'user_id'))
        query = Note.select().where(Note.user_id == None)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."content", "t1"."user_id" '
            'FROM "notes" AS "t1" WHERE ("t1"."user_id" IS ?)'), [None])


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

    def test_insert_list_with_columns(self):
        data = [(i,) for i in ('charlie', 'huey', 'zaizee')]
        query = Person.insert(data, columns=[Person.name])
        self.assertSQL(query, (
            'INSERT INTO "person" ("name") VALUES (?), (?), (?)'),
            ['charlie', 'huey', 'zaizee'])

        # Use column name instead of column instance.
        query = Person.insert(data, columns=['name'])
        self.assertSQL(query, (
            'INSERT INTO "person" ("name") VALUES (?), (?), (?)'),
            ['charlie', 'huey', 'zaizee'])

    def test_insert_list_infer_columns(self):
        data = [('p1', '1980-01-01'), ('p2', '1980-02-02')]
        self.assertSQL(Person.insert(data), (
            'INSERT INTO "person" ("name", "dob") VALUES (?, ?), (?, ?)'),
            ['p1', '1980-01-01', 'p2', '1980-02-02'])

        # Cannot infer any columns for User.
        data = [('u1',), ('u2',)]
        self.assertRaises(ValueError, User.insert(data).sql)

        # Note declares columns, but no primary key. So we would have to
        # include it for this to work.
        data = [(1, 'p1-n'), (2, 'p2-n')]
        self.assertRaises(ValueError, Note.insert(data).sql)

        data = [(1, 1, 'p1-n'), (2, 2, 'p2-n')]
        self.assertSQL(Note.insert(data), (
            'INSERT INTO "note" ("id", "person_id", "content") '
            'VALUES (?, ?, ?), (?, ?, ?)'), [1, 1, 'p1-n', 2, 2, 'p2-n'])

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
            'VALUES (?, ?) '
            'RETURNING "person"."id", "person"."name", "person"."dob"'),
            [datetime.date(2000, 1, 2), 'zaizee'])

        query = query.returning(Person.id, Person.name.alias('new_name'))
        self.assertSQL(query, (
            'INSERT INTO "person" ("dob", "name") '
            'VALUES (?, ?) '
            'RETURNING "person"."id", "person"."name" AS "new_name"'),
            [datetime.date(2000, 1, 2), 'zaizee'])

    def test_empty(self):
        class Empty(TestModel): pass
        query = Empty.insert()
        if isinstance(db, MySQLDatabase):
            sql = 'INSERT INTO "empty" () VALUES ()'
        elif isinstance(db, PostgresqlDatabase):
            sql = 'INSERT INTO "empty" DEFAULT VALUES RETURNING "empty"."id"'
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
            '"counter" = ("users"."counter" + ?), '
            '"username" = ? '
            'WHERE ("users"."username" = ?)'), [False, 1, 'nuggie', 'nugz'])

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
            'WHERE ("users"."id" IN ('
            'SELECT "users"."id", COUNT("t1"."id") AS "ct" '
            'FROM "users" AS "users" '
            'INNER JOIN "tweets" AS "t1" '
            'ON ("t1"."user_id" = "users"."id") '
            'GROUP BY "users"."id" '
            'HAVING ("ct" > ?)))'), [0, True, 100])

    def test_update_value_subquery(self):
        subquery = (Tweet
                    .select(fn.MAX(Tweet.c.id))
                    .where(Tweet.c.user_id == User.c.id))
        query = (User
                 .update({User.c.last_tweet_id: subquery})
                 .where(User.c.last_tweet_id.is_null(True)))
        self.assertSQL(query, (
            'UPDATE "users" SET '
            '"last_tweet_id" = (SELECT MAX("t1"."id") FROM "tweets" AS "t1" '
            'WHERE ("t1"."user_id" = "users"."id")) '
            'WHERE ("users"."last_tweet_id" IS ?)'), [None])

    def test_update_from(self):
        data = [(1, 'u1-x'), (2, 'u2-x')]
        vl = ValuesList(data, columns=('id', 'username'), alias='tmp')
        query = (User
                 .update(username=vl.c.username)
                 .from_(vl)
                 .where(User.c.id == vl.c.id))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = "tmp"."username" '
            'FROM (VALUES (?, ?), (?, ?)) AS "tmp"("id", "username") '
            'WHERE ("users"."id" = "tmp"."id")'), [1, 'u1-x', 2, 'u2-x'])

        subq = vl.select(vl.c.id, vl.c.username)
        query = (User
                 .update({User.c.username: subq.c.username})
                 .from_(subq)
                 .where(User.c.id == subq.c.id))
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
            'UPDATE "users" SET "is_admin" = ? WHERE ("users"."username" = ?) '
            'RETURNING "users"."id"'), [True, 'charlie'])

        query = query.returning(User.c.is_admin.alias('new_is_admin'))
        self.assertSQL(query, (
            'UPDATE "users" SET "is_admin" = ? WHERE ("users"."username" = ?) '
            'RETURNING "users"."is_admin" AS "new_is_admin"'),
            [True, 'charlie'])


class TestDeleteQuery(BaseTestCase):
    def test_delete_query(self):
        query = (User
                 .delete()
                 .where(User.c.username != 'charlie')
                 .limit(3))
        self.assertSQL(query, (
            'DELETE FROM "users" WHERE ("users"."username" != ?) LIMIT ?'),
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
            'WHERE ("users"."id" IN ('
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
            'WHERE ("users"."id" IN (SELECT "u"."id" FROM "u"))'), [True])

    def test_delete_returning(self):
        query = (User
                 .delete()
                 .where(User.c.id > 2)
                 .returning(User.c.username))
        self.assertSQL(query, (
            'DELETE FROM "users" '
            'WHERE ("users"."id" > ?) '
            'RETURNING "users"."username"'), [2])

        query = query.returning(User.c.id, User.c.username, SQL('1'))
        self.assertSQL(query, (
            'DELETE FROM "users" '
            'WHERE ("users"."id" > ?) '
            'RETURNING "users"."id", "users"."username", 1'), [2])

        query = query.returning(User.c.id.alias('old_id'))
        self.assertSQL(query, (
            'DELETE FROM "users" '
            'WHERE ("users"."id" > ?) '
            'RETURNING "users"."id" AS "old_id"'), [2])


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

    def test_window_in_orderby(self):
        Register = Table('register', ['id', 'value'])
        w = Window(partition_by=[Register.value], order_by=[Register.id])
        query = (Register
                 .select()
                 .window(w)
                 .order_by(fn.FIRST_VALUE(Register.id).over(w)))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."value" FROM "register" AS "t1" '
            'WINDOW w AS (PARTITION BY "t1"."value" ORDER BY "t1"."id") '
            'ORDER BY FIRST_VALUE("t1"."id") OVER w'), [])

        fv = fn.FIRST_VALUE(Register.id).over(
            partition_by=[Register.value],
            order_by=[Register.id])
        query = Register.select().order_by(fv)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."value" FROM "register" AS "t1" '
            'ORDER BY FIRST_VALUE("t1"."id") '
            'OVER (PARTITION BY "t1"."value" ORDER BY "t1"."id")'), [])

    def test_window_extends(self):
        Tbl = Table('tbl', ('b', 'c'))
        w1 = Window(partition_by=[Tbl.b], alias='win1')
        w2 = Window(extends=w1, order_by=[Tbl.c], alias='win2')
        query = Tbl.select(fn.GROUP_CONCAT(Tbl.c).over(w2)).window(w1, w2)
        self.assertSQL(query, (
            'SELECT GROUP_CONCAT("t1"."c") OVER win2 FROM "tbl" AS "t1" '
            'WINDOW win1 AS (PARTITION BY "t1"."b"), '
            'win2 AS (win1 ORDER BY "t1"."c")'), [])

        w1 = Window(partition_by=[Tbl.b], alias='w1')
        w2 = Window(extends=w1).alias('w2')
        w3 = Window(extends=w2).alias('w3')
        w4 = Window(extends=w3, order_by=[Tbl.c]).alias('w4')
        query = (Tbl
                 .select(fn.GROUP_CONCAT(Tbl.c).over(w4))
                 .window(w1, w2, w3, w4))
        self.assertSQL(query, (
            'SELECT GROUP_CONCAT("t1"."c") OVER w4 FROM "tbl" AS "t1" '
            'WINDOW w1 AS (PARTITION BY "t1"."b"), w2 AS (w1), w3 AS (w2), '
            'w4 AS (w3 ORDER BY "t1"."c")'), [])

    def test_window_ranged(self):
        Tbl = Table('tbl', ('a', 'b'))
        query = (Tbl
                 .select(Tbl.a, fn.SUM(Tbl.b).over(
                     order_by=[Tbl.a.desc()],
                     frame_type=Window.RANGE,
                     start=Window.preceding(1),
                     end=Window.following(2)))
                 .order_by(Tbl.a.asc()))
        self.assertSQL(query, (
            'SELECT "t1"."a", SUM("t1"."b") OVER ('
            'ORDER BY "t1"."a" DESC RANGE BETWEEN 1 PRECEDING AND 2 FOLLOWING)'
            ' FROM "tbl" AS "t1" ORDER BY "t1"."a" ASC'), [])

        query = (Tbl
                 .select(Tbl.a, fn.SUM(Tbl.b).over(
                     order_by=[Tbl.a],
                     frame_type=Window.GROUPS,
                     start=Window.preceding(3),
                     end=Window.preceding(1))))
        self.assertSQL(query, (
            'SELECT "t1"."a", SUM("t1"."b") OVER ('
            'ORDER BY "t1"."a" GROUPS BETWEEN 3 PRECEDING AND 1 PRECEDING) '
            'FROM "tbl" AS "t1"'), [])

        query = (Tbl
                 .select(Tbl.a, fn.SUM(Tbl.b).over(
                     order_by=[Tbl.a],
                     frame_type=Window.GROUPS,
                     start=Window.following(1),
                     end=Window.following(5))))
        self.assertSQL(query, (
            'SELECT "t1"."a", SUM("t1"."b") OVER ('
            'ORDER BY "t1"."a" GROUPS BETWEEN 1 FOLLOWING AND 5 FOLLOWING) '
            'FROM "tbl" AS "t1"'), [])


    def test_window_frametypes(self):
        Tbl = Table('tbl', ('b', 'c'))
        fts = (('as_range', Window.RANGE, 'RANGE'),
               ('as_rows', Window.ROWS, 'ROWS'),
               ('as_groups', Window.GROUPS, 'GROUPS'))
        for method, arg, sql in fts:
            w = getattr(Window(order_by=[Tbl.b + 1]), method)()
            self.assertSQL(Tbl.select(fn.SUM(Tbl.c).over(w)).window(w), (
                'SELECT SUM("t1"."c") OVER w FROM "tbl" AS "t1" '
                'WINDOW w AS (ORDER BY ("t1"."b" + ?) '
                '%s UNBOUNDED PRECEDING)') % sql, [1])

            query = Tbl.select(fn.SUM(Tbl.c)
                               .over(order_by=[Tbl.b + 1], frame_type=arg))
            self.assertSQL(query, (
                'SELECT SUM("t1"."c") OVER (ORDER BY ("t1"."b" + ?) '
                '%s UNBOUNDED PRECEDING) FROM "tbl" AS "t1"') % sql, [1])

    def test_window_frame_exclusion(self):
        Tbl = Table('tbl', ('b', 'c'))
        fts = ((Window.CURRENT_ROW, 'CURRENT ROW'),
               (Window.TIES, 'TIES'),
               (Window.NO_OTHERS, 'NO OTHERS'),
               (Window.GROUP, 'GROUP'))
        for arg, sql in fts:
            query = Tbl.select(fn.MAX(Tbl.b).over(
                order_by=[Tbl.c],
                start=Window.preceding(4),
                end=Window.following(),
                frame_type=Window.ROWS,
                exclude=arg))
            self.assertSQL(query, (
                'SELECT MAX("t1"."b") OVER (ORDER BY "t1"."c" '
                'ROWS BETWEEN 4 PRECEDING AND UNBOUNDED FOLLOWING '
                'EXCLUDE %s) FROM "tbl" AS "t1"') % sql, [])

    def test_filter_window(self):
        # Example derived from sqlite window test 5.1.3.2.
        Tbl = Table('tbl', ('a', 'c'))
        win = Window(partition_by=fn.COALESCE(Tbl.a, ''),
                     frame_type=Window.RANGE,
                     start=Window.CURRENT_ROW,
                     end=Window.following(),
                     exclude=Window.NO_OTHERS)
        query = (Tbl
                 .select(fn.SUM(Tbl.c).filter(Tbl.c < 5).over(win),
                         fn.RANK().over(win),
                         fn.DENSE_RANK().over(win))
                 .window(win))
        self.assertSQL(query, (
            'SELECT SUM("t1"."c") FILTER (WHERE ("t1"."c" < ?)) OVER w, '
            'RANK() OVER w, DENSE_RANK() OVER w '
            'FROM "tbl" AS "t1" '
            'WINDOW w AS (PARTITION BY COALESCE("t1"."a", ?) '
            'RANGE BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING '
            'EXCLUDE NO OTHERS)'), [5, ''])


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

    def test_join_on_valueslist(self):
        vl = ValuesList([('huey',), ('zaizee',)], columns=['username'])
        query = (User
                 .select(vl.c.username)
                 .join(vl, on=(User.c.username == vl.c.username))
                 .order_by(vl.c.username.desc()))
        self.assertSQL(query, (
            'SELECT "t1"."username" FROM "users" AS "t2" '
            'INNER JOIN (VALUES (?), (?)) AS "t1"("username") '
            'ON ("t2"."username" = "t1"."username") '
            'ORDER BY "t1"."username" DESC'), ['huey', 'zaizee'])


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

    def test_for_update_nested(self):
        PA = Person.alias('pa')
        subq = PA.select(PA.id).where(PA.name == 'charlie').for_update()
        query = (Person
                 .delete()
                 .where(Person.id.in_(subq)))
        self.assertSQL(query, (
            'DELETE FROM "person" WHERE ("person"."id" IN ('
            'SELECT "pa"."id" FROM "person" AS "pa" '
            'WHERE ("pa"."name" = ?) FOR UPDATE))'),
            ['charlie'],
            for_update=True)

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

    def setUp(self):
        super(TestOnConflictMySQL, self).setUp()
        self.database.server_version = None

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

    def test_update_use_value_mariadb(self):
        # Verify that we use "VALUE" (not "VALUES") for MariaDB 10.3.3.
        dob = datetime.date(2010, 1, 1)
        query = (Person
                 .insert(name='huey', dob=dob)
                 .on_conflict(preserve=(Person.dob,)))
        self.database.server_version = (10, 3, 3)
        self.assertSQL(query, (
            'INSERT INTO "person" ("dob", "name") VALUES (?, ?) '
            'ON DUPLICATE KEY '
            'UPDATE "dob" = VALUE("dob")'), [dob, 'huey'])

        self.database.server_version = (10, 3, 2)
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

    def test_conflict_update_excluded(self):
        KV = Table('kv', ('key', 'value', 'extra'), _database=self.database)

        query = (KV.insert(key='k1', value='v1', extra=1)
                 .on_conflict(conflict_target=(KV.key, KV.value),
                              update={KV.extra: EXCLUDED.extra + 2},
                              where=(EXCLUDED.extra < KV.extra)))
        self.assertSQL(query, (
            'INSERT INTO "kv" ("extra", "key", "value") VALUES (?, ?, ?) '
            'ON CONFLICT ("key", "value") DO UPDATE '
            'SET "extra" = (EXCLUDED."extra" + ?) '
            'WHERE (EXCLUDED."extra" < "kv"."extra")'), [1, 'k1', 'v1', 2])

    def test_conflict_target_or_constraint(self):
        KV = Table('kv', ('key', 'value', 'extra'), _database=self.database)

        query = (KV.insert(key='k1', value='v1', extra='e1')
                 .on_conflict(conflict_target=[KV.key, KV.value],
                              preserve=[KV.extra]))
        self.assertSQL(query, (
            'INSERT INTO "kv" ("extra", "key", "value") VALUES (?, ?, ?) '
            'ON CONFLICT ("key", "value") DO UPDATE '
            'SET "extra" = EXCLUDED."extra"'), ['e1', 'k1', 'v1'])

        query = (KV.insert(key='k1', value='v1', extra='e1')
                 .on_conflict(conflict_constraint='kv_key_value',
                              preserve=[KV.extra]))
        self.assertSQL(query, (
            'INSERT INTO "kv" ("extra", "key", "value") VALUES (?, ?, ?) '
            'ON CONFLICT ON CONSTRAINT "kv_key_value" DO UPDATE '
            'SET "extra" = EXCLUDED."extra"'), ['e1', 'k1', 'v1'])

        query = KV.insert(key='k1', value='v1', extra='e1')
        self.assertRaises(ValueError, query.on_conflict,
                          conflict_target=[KV.key, KV.value],
                          conflict_constraint='kv_key_value')

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

    def test_conflict_target_partial_index(self):
        KVE = Table('kve', ('key', 'value', 'extra'))
        data = [('k1', 1, 2), ('k2', 2, 3)]
        columns = [KVE.key, KVE.value, KVE.extra]

        query = (KVE
                 .insert(data, columns)
                 .on_conflict(
                     conflict_target=(KVE.key, KVE.value),
                     conflict_where=(KVE.extra > 1),
                     preserve=(KVE.extra,),
                     where=(KVE.key != 'kx')))
        self.assertSQL(query, (
            'INSERT INTO "kve" ("key", "value", "extra") '
            'VALUES (?, ?, ?), (?, ?, ?) '
            'ON CONFLICT ("key", "value") WHERE ("extra" > ?) '
            'DO UPDATE SET "extra" = EXCLUDED."extra" '
            'WHERE ("kve"."key" != ?)'),
            ['k1', 1, 2, 'k2', 2, 3, 1, 'kx'])


#Person = Table('person', ['id', 'name', 'dob'])
#Note = Table('note', ['id', 'person_id', 'content'])

class TestIndex(BaseTestCase):
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


class TestSqlToString(BaseTestCase):
    def _test_sql_to_string(self, _param):
        class FakeDB(SqliteDatabase):
            param = _param

        db = FakeDB(None)
        T = Table('tbl', ('id', 'val')).bind(db)

        query = (T.select()
                 .where((T.val == 'foo') |
                        (T.val == b'bar') |
                        (T.val == True) | (T.val == False) |
                        (T.val == 2) |
                        (T.val == -3.14) |
                        (T.val == datetime.datetime(2018, 1, 1)) |
                        (T.val == datetime.date(2018, 1, 2)) |
                        T.val.is_null() |
                        T.val.is_null(False) |
                        T.val.in_(['aa', 'bb', 'cc'])))

        self.assertEqual(query_to_string(query), (
            'SELECT "t1"."id", "t1"."val" FROM "tbl" AS "t1" WHERE ((((((((((('
            '"t1"."val" = \'foo\') OR '
            '("t1"."val" = \'bar\')) OR '
            '("t1"."val" = 1)) OR '
            '("t1"."val" = 0)) OR '
            '("t1"."val" = 2)) OR '
            '("t1"."val" = -3.14)) OR '
            '("t1"."val" = \'2018-01-01 00:00:00\')) OR '
            '("t1"."val" = \'2018-01-02\')) OR '
            '("t1"."val" IS NULL)) OR '
            '("t1"."val" IS NOT NULL)) OR '
            '("t1"."val" IN (\'aa\', \'bb\', \'cc\')))'))

    def test_sql_to_string_qmark(self):
        self._test_sql_to_string('?')

    def test_sql_to_string_default(self):
        self._test_sql_to_string('%s')
