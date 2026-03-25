"""
SQL generation tests for Model-level queries.

These tests verify that queries built using Model classes (with ForeignKeyField
relationships, Meta options, etc.) produce correct SQL. Unlike sql.py which
tests lower-level Table objects, these tests exercise the Model metaclass
machinery including automatic join resolution, field type coercion, and alias
handling.

Test case ordering:

* Core Model query SQL (SELECT, INSERT, UPDATE, DELETE)
* ON CONFLICT SQL with Models
* String-based field references
* Compound SELECT with Models
* Model index SQL
* Query cloning and regressions
"""
import datetime

from peewee import *
from peewee import Alias
from peewee import Database
from peewee import ModelIndex

from .base import get_in_memory_db
from .base import requires_pglike
from .base import skip_if
from .base import BaseTestCase
from .base import IS_CRDB
from .base import ModelDatabaseTestCase
from .base import TestModel
from .base import __sql__
from .base_models import *


class CKM(TestModel):
    category = CharField()
    key = CharField()
    value = IntegerField()
    class Meta:
        primary_key = CompositeKey('category', 'key')


# ===========================================================================
# Core Model query SQL generation
# ===========================================================================

class TestModelSQL(ModelDatabaseTestCase):
    database = get_in_memory_db()
    requires = [Category, CKM, Note, Person, Relationship, Sample, User, DfltM]

    def test_select(self):
        query = User.select()
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1"'))

        query = (Person
                 .select(
                     Person.first,
                     Person.last,
                     fn.COUNT(Note.id).alias('ct'))
                 .join(Note)
                 .where((Person.last == 'Leifer') & (Person.id < 4)))
        self.assertSQL(query, (
            'SELECT "t1"."first", "t1"."last", COUNT("t2"."id") AS "ct" '
            'FROM "person" AS "t1" '
            'INNER JOIN "note" AS "t2" ON ("t2"."author_id" = "t1"."id") '
            'WHERE ('
            '("t1"."last" = ?) AND '
            '("t1"."id" < ?))'), ['Leifer', 4])

    def test_reselect(self):
        sql = 'SELECT "t1"."name", "t1"."parent_id" FROM "category" AS "t1"'

        query = Category.select()
        self.assertSQL(query, sql, [])

        query2 = query.select()
        self.assertSQL(query2, sql, [])

        query = Category.select(Category.name, Category.parent)
        self.assertSQL(query, sql, [])

        query2 = query.select()
        self.assertSQL(query2, 'SELECT  FROM "category" AS "t1"', [])

        query = query2.select(Category.name)
        self.assertSQL(query, 'SELECT "t1"."name" FROM "category" AS "t1"', [])

    def test_select_extend(self):
        query = Note.select()
        ext = query.join(Person).select_extend(Person)
        self.assertSQL(ext, (
            'SELECT "t1"."id", "t1"."author_id", "t1"."content", "t2"."id", '
            '"t2"."first", "t2"."last", "t2"."dob" '
            'FROM "note" AS "t1" INNER JOIN "person" AS "t2" '
            'ON ("t1"."author_id" = "t2"."id")'), [])

    def test_selected_columns(self):
        query = (Person
                 .select(
                     Person.first,
                     Person.last,
                     fn.COUNT(Note.id).alias('ct'))
                 .join(Note))
        f_first, f_last, f_ct = query.selected_columns
        self.assertEqual(f_first.name, 'first')
        self.assertTrue(f_first.model is Person)
        self.assertEqual(f_last.name, 'last')
        self.assertTrue(f_last.model is Person)
        self.assertTrue(isinstance(f_ct, Alias))
        f_ct = f_ct.unwrap()
        self.assertEqual(f_ct.name, 'COUNT')
        f_nid, = f_ct.arguments
        self.assertEqual(f_nid.name, 'id')
        self.assertTrue(f_nid.model is Note)

        query.selected_columns = (Person.first,)
        f_first, = query.selected_columns
        self.assertEqual(f_first.name, 'first')
        self.assertTrue(f_first.model is Person)

    def test_model_select_from(self):
        inner = (User
                 .select(User.id, User.username)
                 .where(User.username == 'x'))
        query = inner.select_from(inner.c.username)
        self.assertSQL(query, (
            'SELECT "t1"."username" FROM ('
            'SELECT "t2"."id", "t2"."username" '
            'FROM "users" AS "t2" '
            'WHERE ("t2"."username" = ?)) AS "t1"'), ['x'])

    def test_model_alias(self):
        TA = Tweet.alias()
        query = (User
                 .select(User, fn.COUNT(TA.id).alias('tc'))
                 .join(TA, on=(User.id == TA.user))
                 .group_by(User))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username", COUNT("t2"."id") AS "tc" '
            'FROM "users" AS "t1" '
            'INNER JOIN "tweet" AS "t2" ON ("t1"."id" = "t2"."user_id") '
            'GROUP BY "t1"."id", "t1"."username"'), [])

    def test_model_alias_with_schema(self):
        class Note(TestModel):
            content = TextField()
            class Meta:
                schema = 'notes'

        query = Note.select()
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."content" '
            'FROM "notes"."note" AS "t1"'), [])

        query = Note.alias('na').select()
        self.assertSQL(query, (
            'SELECT "na"."id", "na"."content" '
            'FROM "notes"."note" AS "na"'), [])

    def test_model_alias_join_with_schema(self):
        class Note(TestModel):
            content = TextField()
            class Meta:
                schema = 'notes'

        NA = Note.alias('na')
        query = (Note
                 .select(Note.content, NA.content)
                 .join(NA, on=(NA.id == Note.id)))
        self.assertSQL(query, (
            'SELECT "t1"."content", "na"."content" '
            'FROM "notes"."note" AS "t1" '
            'INNER JOIN "notes"."note" AS "na" '
            'ON ("na"."id" = "t1"."id")'), [])

    def test_aliases(self):
        class A(TestModel):
            a = CharField()
        class B(TestModel):
            b = CharField()
            a_link = ForeignKeyField(A)
        class C(TestModel):
            c = CharField()
            b_link = ForeignKeyField(B)
        class D(TestModel):
            d = CharField()
            c_link = ForeignKeyField(C)

        query = (D
                 .select(D.d, C.c)
                 .join(C)
                 .where(C.b_link << (
                     B.select(B.id).join(A).where(A.a == 'a'))))
        self.assertSQL(query, (
            'SELECT "t1"."d", "t2"."c" '
            'FROM "d" AS "t1" '
            'INNER JOIN "c" AS "t2" ON ("t1"."c_link_id" = "t2"."id") '
            'WHERE ("t2"."b_link_id" IN ('
            'SELECT "t3"."id" FROM "b" AS "t3" '
            'INNER JOIN "a" AS "t4" ON ("t3"."a_link_id" = "t4"."id") '
            'WHERE ("t4"."a" = ?)))'), ['a'])

    def test_schema(self):
        class WithSchema(TestModel):
            data = CharField(primary_key=True)
            class Meta:
                schema = 'huey'

        query = WithSchema.select().where(WithSchema.data == 'zaizee')
        self.assertSQL(query, (
            'SELECT "t1"."data" '
            'FROM "huey"."with_schema" AS "t1" '
            'WHERE ("t1"."data" = ?)'), ['zaizee'])

    def test_distinct(self):
        query = User.select().distinct()
        self.assertSQL(query, (
            'SELECT DISTINCT "t1"."id", "t1"."username" '
            'FROM "users" AS "t1"'), [])

        query = User.select().distinct(User.username)
        self.assertSQL(query, (
            'SELECT DISTINCT ON ("t1"."username") '
            '"t1"."id", "t1"."username" '
            'FROM "users" AS "t1"'), [])

    def test_string_expression_concat_chain(self):
        class P(TestModel):
            first = CharField()
            last = TextField()
            class Meta:
                database = self.database

        query = P.select(P.first + ' ' + P.last)
        self.assertSQL(query, (
            'SELECT (("t1"."first" || ?) || "t1"."last") '
            'FROM "p" AS "t1"'), [' '])

        query = P.select(P.last + ' ' + P.first)
        self.assertSQL(query, (
            'SELECT (("t1"."last" || ?) || "t1"."first") '
            'FROM "p" AS "t1"'), [' '])

    def test_where_coerce(self):
        query = Person.select(Person.last).where(Person.id == '1337')
        self.assertSQL(query, (
            'SELECT "t1"."last" FROM "person" AS "t1" '
            'WHERE ("t1"."id" = ?)'), [1337])

        query = Person.select(Person.last).where(Person.id < (Person.id - '5'))
        self.assertSQL(query, (
            'SELECT "t1"."last" FROM "person" AS "t1" '
            'WHERE ("t1"."id" < ("t1"."id" - ?))'), [5])

        query = Person.select(Person.last).where(Person.first == b'foo')
        self.assertSQL(query, (
            'SELECT "t1"."last" FROM "person" AS "t1" '
            'WHERE ("t1"."first" = ?)'), ['foo'])

    def test_orwhere(self):
        query = (User
                 .select()
                 .orwhere(User.username == 'huey')
                 .orwhere(User.username == 'zaizee'))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" '
            'FROM "users" AS "t1" '
            'WHERE (("t1"."username" = ?) OR ("t1"."username" = ?))'),
            ['huey', 'zaizee'])

    def test_where_then_orwhere(self):
        query = (User
                 .select()
                 .where(User.id > 0)
                 .orwhere(User.username == 'huey')
                 .orwhere(User.username == 'zaizee'))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" '
            'FROM "users" AS "t1" '
            'WHERE ((("t1"."id" > ?) OR '
            '("t1"."username" = ?)) OR ("t1"."username" = ?))'),
            [0, 'huey', 'zaizee'])

    def test_filter_simple(self):
        query = User.filter(username='huey')
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'WHERE ("t1"."username" = ?)'), ['huey'])

        query = User.filter(username='huey', id__gte=1, id__lt=5)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'WHERE ((("t1"."id" >= ?) AND ("t1"."id" < ?)) AND '
            '("t1"."username" = ?))'), [1, 5, 'huey'])

        query = User.filter(~DQ(id=1), username__in=('foo', 'bar'))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'WHERE (NOT ("t1"."id" = ?) AND ("t1"."username" IN (?, ?)))'),
            [1, 'foo', 'bar'])

        query = User.filter((DQ(id=1) | DQ(id=2)), username__in=('foo', 'bar'))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'WHERE ((("t1"."id" = ?) OR ("t1"."id" = ?)) AND '
            '("t1"."username" IN (?, ?)))'), [1, 2, 'foo', 'bar'])

    def test_filter_expressions(self):
        query = User.filter(
            DQ(username__in=['huey', 'zaizee']) |
            (DQ(id__gt=2) & DQ(id__lt=4)))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" '
            'FROM "users" AS "t1" '
            'WHERE (("t1"."username" IN (?, ?)) OR '
            '(("t1"."id" > ?) AND ("t1"."id" < ?)))'),
            ['huey', 'zaizee', 2, 4])

    def test_filter_join(self):
        query = Tweet.select(Tweet.content).filter(user__username='huey')
        self.assertSQL(query, (
            'SELECT "t1"."content" FROM "tweet" AS "t1" '
            'INNER JOIN "users" AS "t2" ON ("t1"."user_id" = "t2"."id") '
            'WHERE ("t2"."username" = ?)'), ['huey'])

        UA = User.alias('ua')
        query = (Tweet
                 .select(Tweet.content)
                 .join(UA)
                 .filter(ua__username='huey'))
        self.assertSQL(query, (
            'SELECT "t1"."content" FROM "tweet" AS "t1" '
            'INNER JOIN "users" AS "ua" ON ("t1"."user_id" = "ua"."id") '
            'WHERE ("ua"."username" = ?)'), ['huey'])

    def test_filter_with_or_across_joins(self):
        query = (Tweet
                 .select(Tweet.content)
                 .filter(
                     DQ(user__username='huey') |
                     DQ(content__like='%hello%')))
        self.assertSQL(query, (
            'SELECT "t1"."content" FROM "tweet" AS "t1" '
            'INNER JOIN "users" AS "t2" '
            'ON ("t1"."user_id" = "t2"."id") '
            'WHERE (("t2"."username" = ?) OR '
            '("t1"."content" LIKE ?))'), ['huey', '%hello%'])

    def test_filter_join_combine_models(self):
        query = (Tweet
                 .select(Tweet.content)
                 .filter(user__username='huey')
                 .filter(DQ(user__id__gte=1) | DQ(id__lt=5)))
        self.assertSQL(query, (
            'SELECT "t1"."content" FROM "tweet" AS "t1" '
            'INNER JOIN "users" AS "t2" ON ("t1"."user_id" = "t2"."id") '
            'WHERE (("t2"."username" = ?) AND '
            '(("t2"."id" >= ?) OR ("t1"."id" < ?)))'), ['huey', 1, 5])

    def test_mix_filter_methods(self):
        query = (User
                 .select(User, fn.COUNT(Tweet.id).alias('count'))
                 .filter(username__in=('huey', 'zaizee'))
                 .join(Tweet, JOIN.LEFT_OUTER)
                 .group_by(User.id, User.username)
                 .order_by(fn.COUNT(Tweet.id).desc()))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username", COUNT("t2"."id") AS "count" '
            'FROM "users" AS "t1" '
            'LEFT OUTER JOIN "tweet" AS "t2" ON ("t2"."user_id" = "t1"."id") '
            'WHERE ("t1"."username" IN (?, ?)) '
            'GROUP BY "t1"."id", "t1"."username" '
            'ORDER BY COUNT("t2"."id") DESC'), ['huey', 'zaizee'])

    def test_value_flattening(self):
        sql = ('SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
               'WHERE ("t1"."username" IN (?, ?))')
        expected = (sql, ['foo', 'bar'])

        users = User.select().where(User.username.in_(['foo', 'bar']))
        self.assertSQL(users, *expected)

        users = User.select().where(User.username.in_(('foo', 'bar')))
        self.assertSQL(users, *expected)

        genexp = (u for u in ('foo', 'bar'))
        users = User.select().where(User.username.in_(genexp))
        self.assertSQL(users, *expected)

        users = User.select().where(User.username.in_(set(['foo', 'bar'])))
        # Sets are unordered so params may be in either order:
        sql, params = __sql__(users)
        self.assertEqual(sql, expected[0])
        self.assertTrue(params in (['foo', 'bar'], ['bar', 'foo']))

    def test_subquery_correction(self):
        users = User.select().where(User.username.in_(['foo', 'bar']))
        query = Tweet.select().where(Tweet.user.in_(users))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."user_id", "t1"."content", '
            '"t1"."timestamp" '
            'FROM "tweet" AS "t1" '
            'WHERE ("t1"."user_id" IN ('
            'SELECT "t2"."id" FROM "users" AS "t2" '
            'WHERE ("t2"."username" IN (?, ?))))'), ['foo', 'bar'])

        UA = User.alias()
        users = (UA.select(UA.username)
                 .where(UA.username.in_(['foo', 'bar'])))
        query = (User
                 .select()
                 .where(User.username.in_(users)))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" '
            'FROM "users" AS "t1" '
            'WHERE ("t1"."username" IN ('
            'SELECT "t2"."username" FROM "users" AS "t2" '
            'WHERE ("t2"."username" IN (?, ?))))'), ['foo', 'bar'])

    def test_group_by(self):
        query = (User
                 .select(User, fn.COUNT(Tweet.id).alias('tweet_count'))
                 .join(Tweet, JOIN.LEFT_OUTER)
                 .group_by(User))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username", '
            'COUNT("t2"."id") AS "tweet_count" '
            'FROM "users" AS "t1" '
            'LEFT OUTER JOIN "tweet" AS "t2" ON ("t2"."user_id" = "t1"."id") '
            'GROUP BY "t1"."id", "t1"."username"'), [])

        query = (User
                 .select(User.username,
                         fn.COUNT(Tweet.id).alias('tweet_count'))
                 .join(Tweet, JOIN.LEFT_OUTER)
                 .group_by(User.username))
        self.assertSQL(query, (
            'SELECT "t1"."username", '
            'COUNT("t2"."id") AS "tweet_count" '
            'FROM "users" AS "t1" '
            'LEFT OUTER JOIN "tweet" AS "t2" ON ("t2"."user_id" = "t1"."id") '
            'GROUP BY "t1"."username"'), [])

    def test_group_by_extend(self):
        query = (User
                 .select(User, fn.COUNT(Tweet.id).alias('tweet_count'))
                 .join(Tweet, JOIN.LEFT_OUTER)
                 .group_by_extend(User.id).group_by_extend(User.username))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username", '
            'COUNT("t2"."id") AS "tweet_count" '
            'FROM "users" AS "t1" '
            'LEFT OUTER JOIN "tweet" AS "t2" ON ("t2"."user_id" = "t1"."id") '
            'GROUP BY "t1"."id", "t1"."username"'), [])

    def test_having(self):
        query = (User
                 .select(User.username,
                         fn.COUNT(Tweet.id).alias('ct'))
                 .join(Tweet, JOIN.LEFT_OUTER)
                 .group_by(User.username)
                 .having(fn.COUNT(Tweet.id) > 5))
        self.assertSQL(query, (
            'SELECT "t1"."username", COUNT("t2"."id") AS "ct" '
            'FROM "users" AS "t1" '
            'LEFT OUTER JOIN "tweet" AS "t2" '
            'ON ("t2"."user_id" = "t1"."id") '
            'GROUP BY "t1"."username" '
            'HAVING (COUNT("t2"."id") > ?)'), [5])

    def test_order_by(self):
        query = (User
                 .select()
                 .order_by(User.username.desc(), User.id))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'ORDER BY "t1"."username" DESC, "t1"."id"'), [])

    def test_order_by_extend(self):
        query = (User
                 .select()
                 .order_by_extend(User.username.desc())
                 .order_by_extend(User.id))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'ORDER BY "t1"."username" DESC, "t1"."id"'), [])

    def test_paginate(self):
        # Get the first page, default is limit of 20.
        query = User.select().paginate(1)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'LIMIT ? OFFSET ?'), [20, 0])

        # Page 3 contains rows 31-45.
        query = User.select().paginate(3, 15)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'LIMIT ? OFFSET ?'), [15, 30])

    def test_join_ctx(self):
        query = Tweet.select(Tweet.id).join(Favorite).switch(Tweet).join(User)
        self.assertSQL(query, (
            'SELECT "t1"."id" FROM "tweet" AS "t1" '
            'INNER JOIN "favorite" AS "t2" ON ("t2"."tweet_id" = "t1"."id") '
            'INNER JOIN "users" AS "t3" ON ("t1"."user_id" = "t3"."id")'), [])

        query = Tweet.select(Tweet.id).join(User).switch(Tweet).join(Favorite)
        self.assertSQL(query, (
            'SELECT "t1"."id" FROM "tweet" AS "t1" '
            'INNER JOIN "users" AS "t2" ON ("t1"."user_id" = "t2"."id") '
            'INNER JOIN "favorite" AS "t3" ON ("t3"."tweet_id" = "t1"."id")'),
            [])

        query = (Tweet.select(Tweet.id)
                 .left_outer_join(Favorite)
                 .switch(Tweet)
                 .left_outer_join(User))
        self.assertSQL(query, (
            'SELECT "t1"."id" FROM "tweet" AS "t1" '
            'LEFT OUTER JOIN "favorite" AS "t2" ON ("t2"."tweet_id" = "t1"."id") '
            'LEFT OUTER JOIN "users" AS "t3" ON ("t1"."user_id" = "t3"."id")'), [])

        query = (Tweet.select(Tweet.id)
                 .left_outer_join(User)
                 .switch(Tweet)
                 .left_outer_join(Favorite))
        self.assertSQL(query, (
            'SELECT "t1"."id" FROM "tweet" AS "t1" '
            'LEFT OUTER JOIN "users" AS "t2" ON ("t1"."user_id" = "t2"."id") '
            'LEFT OUTER JOIN "favorite" AS "t3" ON ("t3"."tweet_id" = "t1"."id")'),
            [])

    def test_join_parent(self):
        query = (Category
                 .select()
                 .where(Category.parent == 'test'))
        self.assertSQL(query, (
            'SELECT "t1"."name", "t1"."parent_id" FROM "category" AS "t1" '
            'WHERE ("t1"."parent_id" = ?)'), ['test'])

        query = Category.filter(parent='test')
        self.assertSQL(query, (
            'SELECT "t1"."name", "t1"."parent_id" FROM "category" AS "t1" '
            'WHERE ("t1"."parent_id" = ?)'), ['test'])

    def test_cross_join(self):
        class A(TestModel):
            id = IntegerField(primary_key=True)
        class B(TestModel):
            id = IntegerField(primary_key=True)
        query = (A
                 .select(A.id.alias('aid'), B.id.alias('bid'))
                 .join(B, JOIN.CROSS)
                 .order_by(A.id, B.id))
        self.assertSQL(query, (
            'SELECT "t1"."id" AS "aid", "t2"."id" AS "bid" '
            'FROM "a" AS "t1" '
            'CROSS JOIN "b" AS "t2" '
            'ORDER BY "t1"."id", "t2"."id"'), [])

    def test_cross_join_with_on_raises(self):
        query = User.select()
        with self.assertRaisesCtx(ValueError):
            query.join(Tweet, JOIN.CROSS, on=(User.id == Tweet.user))

    def test_join_expr(self):
        class User(TestModel):
            username = TextField(primary_key=True)
        class Tweet(TestModel):
            user = ForeignKeyField(User, backref='tweets')
            content = TextField()

        sql = ('SELECT "t1"."id", "t1"."user_id", "t1"."content", '
               '"t2"."username" FROM "tweet" AS "t1" '
               'INNER JOIN "user" AS "t2" '
               'ON ("t1"."user_id" = "t2"."username")')

        query = Tweet.select(Tweet, User).join(User)
        self.assertSQL(query, sql, [])

        query = (Tweet
                 .select(Tweet, User)
                 .join(User, on=(Tweet.user == User.username)))
        self.assertSQL(query, sql, [])

        join_expr = ((Tweet.user == User.username) & (Value(1) == 1))
        query = Tweet.select().join(User, on=join_expr)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."user_id", "t1"."content" '
            'FROM "tweet" AS "t1" '
            'INNER JOIN "user" AS "t2" '
            'ON (("t1"."user_id" = "t2"."username") AND (? = ?))'), [1, 1])

    def test_join_multiple_fks(self):
        class A(TestModel):
            name = TextField()
        class B(TestModel):
            name = TextField(primary_key=True)
            a1 = ForeignKeyField(A, backref='b_set1')
            a2 = ForeignKeyField(A, field=A.name, backref='b_set2')

        A1 = A.alias('a1')
        A2 = A.alias('a2')

        sql = ('SELECT "t1"."name", "t1"."a1_id", "t1"."a2_id", '
               '"a1"."id", "a1"."name", "a2"."id", "a2"."name" '
               'FROM "b" AS "t1" '
               'INNER JOIN "a" AS "a1" ON ("t1"."a1_id" = "a1"."id") '
               'INNER JOIN "a" AS "a2" ON ("t1"."a2_id" = "a2"."name")')

        query = (B.select(B, A1, A2)
                 .join_from(B, A1, on=B.a1)
                 .join_from(B, A2, on=B.a2))
        self.assertSQL(query, sql, [])

        query = (B.select(B, A1, A2)
                 .join(A1, on=(B.a1 == A1.id)).switch(B)
                 .join(A2, on=(B.a2 == A2.name)))
        self.assertSQL(query, sql, [])

        jx1 = (B.a1 == A1.id) & (Value(1) == 1)
        jx2 = (Value(1) == 1) & (B.a2 == A2.name)
        query = (B.select()
                 .join(A1, on=jx1).switch(B)
                 .join(A2, on=jx2))
        self.assertSQL(query, (
            'SELECT "t1"."name", "t1"."a1_id", "t1"."a2_id" '
            'FROM "b" AS "t1" '
            'INNER JOIN "a" AS "a1" '
            'ON (("t1"."a1_id" = "a1"."id") AND (? = ?)) '
            'INNER JOIN "a" AS "a2" '
            'ON ((? = ?) AND ("t1"."a2_id" = "a2"."name"))'), [1, 1, 1, 1])

    def test_raw(self):
        query = (Person
                 .raw('SELECT first, last, dob FROM person '
                      'WHERE first = ? AND substr(last, 1, 1) = ? '
                      'ORDER BY last', 'huey', 'l'))
        self.assertSQL(query, (
            'SELECT first, last, dob FROM person '
            'WHERE first = ? AND substr(last, 1, 1) = ? '
            'ORDER BY last'), ['huey', 'l'])

    def test_insert(self):
        query = (Person
                 .insert({Person.first: 'huey',
                          Person.last: 'cat',
                          Person.dob: datetime.date(2011, 1, 1)}))
        self.assertSQL(query, (
            'INSERT INTO "person" ("first", "last", "dob") '
            'VALUES (?, ?, ?)'), ['huey', 'cat', datetime.date(2011, 1, 1)])

        query = (Note
                 .insert({Note.author: Person(id=1337),
                          Note.content: 'leet'}))
        self.assertSQL(query, (
            'INSERT INTO "note" ("author_id", "content") '
            'VALUES (?, ?)'), [1337, 'leet'])

        query = Person.insert(first='huey', last='cat')
        self.assertSQL(query, (
            'INSERT INTO "person" ("first", "last") VALUES (?, ?)'),
            ['huey', 'cat'])

    def test_replace(self):
        query = (Person
                 .replace({Person.first: 'huey',
                           Person.last: 'cat'}))
        self.assertSQL(query, (
            'INSERT OR REPLACE INTO "person" ("first", "last") '
            'VALUES (?, ?)'), ['huey', 'cat'])

    def test_insert_many(self):
        query = (Note
                 .insert_many((
                     {Note.author: Person(id=1), Note.content: 'note-1'},
                     {Note.author: Person(id=2), Note.content: 'note-2'},
                     {Note.author: Person(id=3), Note.content: 'note-3'})))
        self.assertSQL(query, (
            'INSERT INTO "note" ("author_id", "content") '
            'VALUES (?, ?), (?, ?), (?, ?)'),
            [1, 'note-1', 2, 'note-2', 3, 'note-3'])

        query = (Note
                 .insert_many((
                     {'author': Person(id=1), 'content': 'note-1'},
                     {'author': Person(id=2), 'content': 'note-2'})))
        self.assertSQL(query, (
            'INSERT INTO "note" ("author_id", "content") '
            'VALUES (?, ?), (?, ?)'),
            [1, 'note-1', 2, 'note-2'])

    def test_insert_many_defaults(self):
        # Verify fields are inferred and values are read correctly, when
        # partial data is given and a field has default values.
        s2 = {'counter': 2, 'value': 2.}
        s3 = {'counter': 3}
        self.assertSQL(Sample.insert_many([s2, s3]), (
            'INSERT INTO "sample" ("counter", "value") VALUES (?, ?), (?, ?)'),
            [2, 2., 3, 1.])

        self.assertSQL(Sample.insert_many([s3, s2]), (
            'INSERT INTO "sample" ("counter", "value") VALUES (?, ?), (?, ?)'),
            [3, 1., 2, 2.])

    def test_insert_many_defaults_nulls(self):
        data = [
            {'name': 'd1'},
            {'name': 'd2', 'dflt1': 10},
            {'name': 'd3', 'dflt2': 30},
            {'name': 'd4', 'dfltn': 40}]
        fields = [DfltM.name, DfltM.dflt1, DfltM.dflt2, DfltM.dfltn]
        self.assertSQL(DfltM.insert_many(data, fields=fields), (
            'INSERT INTO "dflt_m" ("name", "dflt1", "dflt2", "dfltn") VALUES '
            '(?, ?, ?, ?), (?, ?, ?, ?), (?, ?, ?, ?), (?, ?, ?, ?)'),
            ['d1', 1, 2, None,
             'd2', 10, 2, None,
             'd3', 1, 30, None,
             'd4', 1, 2, 40])

    def test_insert_many_list_with_fields(self):
        data = [(i,) for i in ('charlie', 'huey', 'zaizee')]
        query = User.insert_many(data, fields=[User.username])
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") VALUES (?), (?), (?)'),
            ['charlie', 'huey', 'zaizee'])

        # Use field name instead of field obj.
        query = User.insert_many(data, fields=['username'])
        self.assertSQL(query, (
            'INSERT INTO "users" ("username") VALUES (?), (?), (?)'),
            ['charlie', 'huey', 'zaizee'])

    def test_insert_many_infer_fields(self):
        data = [('f1', 'l1', '1980-01-01'),
                ('f2', 'l2', '1980-02-02')]
        self.assertSQL(Person.insert_many(data), (
            'INSERT INTO "person" ("first", "last", "dob") '
            'VALUES (?, ?, ?), (?, ?, ?)'),
            ['f1', 'l1', datetime.date(1980, 1, 1),
             'f2', 'l2', datetime.date(1980, 2, 2)])

        # When primary key is not auto-increment, PKs are included.
        data = [('c1', 'k1', 1), ('c2', 'k2', 2)]
        self.assertSQL(CKM.insert_many(data), (
            'INSERT INTO "ckm" ("category", "key", "value") '
            'VALUES (?, ?, ?), (?, ?, ?)'), ['c1', 'k1', 1, 'c2', 'k2', 2])

    def test_insert_query(self):
        select = (Person
                  .select(Person.id, Person.first)
                  .where(Person.last == 'cat'))
        query = Note.insert_from(select, (Note.author, Note.content))
        self.assertSQL(query, ('INSERT INTO "note" ("author_id", "content") '
                               'SELECT "t1"."id", "t1"."first" '
                               'FROM "person" AS "t1" '
                               'WHERE ("t1"."last" = ?)'), ['cat'])

        query = Note.insert_from(select, ('author', 'content'))
        self.assertSQL(query, ('INSERT INTO "note" ("author_id", "content") '
                               'SELECT "t1"."id", "t1"."first" '
                               'FROM "person" AS "t1" '
                               'WHERE ("t1"."last" = ?)'), ['cat'])

    def test_insert_returning(self):
        class TestDB(Database):
            returning_clause = True

        class User(Model):
            username = CharField()
            class Meta:
                database = TestDB(None)

        query = User.insert({User.username: 'zaizee'})
        self.assertSQL(query, (
            'INSERT INTO "user" ("username") '
            'VALUES (?) RETURNING "user"."id"'), ['zaizee'])

        class Person(Model):
            name = CharField()
            ssn = CharField(primary_key=True)
            class Meta:
                database = TestDB(None)

        query = Person.insert({Person.name: 'charlie', Person.ssn: '123'})
        self.assertSQL(query, (
            'INSERT INTO "person" ("ssn", "name") VALUES (?, ?) '
            'RETURNING "person"."ssn"'), ['123', 'charlie'])

        query = Person.insert({Person.name: 'huey'}).returning()
        self.assertSQL(query, (
            'INSERT INTO "person" ("name") VALUES (?)'), ['huey'])

        query = (Person
                 .insert({Person.name: 'foo'})
                 .returning(Person.ssn.alias('new_ssn')))
        self.assertSQL(query, (
            'INSERT INTO "person" ("name") VALUES (?) '
            'RETURNING "person"."ssn" AS "new_ssn"'), ['foo'])

    def test_insert_get_field_values(self):
        class User(TestModel):
            username = TextField(primary_key=True)
            class Meta:
                database = self.database

        class Tweet(TestModel):
            user = ForeignKeyField(User)
            content = TextField()
            class Meta:
                database = self.database

        queries = (
            User.insert(username='a'),
            User.insert({'username': 'a'}),
            User.insert({User.username: 'a'}))
        for query in queries:
            self.assertSQL(query, ('INSERT INTO "user" ("username") '
                                   'VALUES (?)'), ['a'])

        # Verify that we can provide all kinds of combinations to the
        # constructor to INSERT and it will map the parameters correctly
        # without losing values.
        a = User(username='a')
        queries = (
            Tweet.insert(user=a, content='ca'),
            Tweet.insert({'user': a, 'content': 'ca'}),
            Tweet.insert({Tweet.user: a, 'content': 'ca'}),
            Tweet.insert({'user': a, Tweet.content: 'ca'}),
            Tweet.insert({Tweet.user: a, Tweet.content: 'ca'}),
            Tweet.insert({Tweet.user: a}, content='ca'),
            Tweet.insert({Tweet.content: 'ca'}, user=a),
            Tweet.insert({'user': a}, content='ca'),
            Tweet.insert({'content': 'ca'}, user=a),

            # Also test using the foreign-key descriptor and column name.
            Tweet.insert({Tweet.user_id: a, Tweet.content: 'ca'}),
            Tweet.insert(user_id=a, content='ca'),
            Tweet.insert({'user_id': a, 'content': 'ca'}))

        for query in queries:
            self.assertSQL(query, ('INSERT INTO "tweet" ("user_id", "content")'
                                   ' VALUES (?, ?)'), ['a', 'ca'])

    def test_insert_many_get_field_values(self):
        class User(TestModel):
            username = TextField(primary_key=True)
            class Meta:
                database = self.database

        class Tweet(TestModel):
            user = ForeignKeyField(User)
            content = TextField()
            class Meta:
                database = self.database

        # Ensure we can handle any combination of insert-data key and field
        # list value.
        pairs = ((User.username, 'username'),
                 ('username', User.username),
                 ('username', 'username'),
                 (User.username, User.username))

        for dict_key, fields_key in pairs:
            iq = User.insert_many([{dict_key: u} for u in 'abc'],
                                  fields=[fields_key])
            self.assertSQL(iq, (
                'INSERT INTO "user" ("username") VALUES (?), (?), (?)'),
                ['a', 'b', 'c'])

        a, b = User(username='a'), User(username='b')
        user_content = (
            (a, 'ca1'),
            (a, 'ca2'),
            (b, 'cb1'),
            ('a', 'ca3'))  # Specify user id directly.

        # Ensure we can mix-and-match key type within insert-data.
        pairs = (('user', 'content'),
                 (Tweet.user, Tweet.content),
                 (Tweet.user, 'content'),
                 ('user', Tweet.content),
                 ('user_id', 'content'),
                 (Tweet.user_id, Tweet.content))

        for ukey, ckey in pairs:
            iq = Tweet.insert_many([{ukey: u, ckey: c}
                                    for u, c in user_content])
            self.assertSQL(iq, (
                'INSERT INTO "tweet" ("user_id", "content") VALUES '
                '(?, ?), (?, ?), (?, ?), (?, ?)'),
                ['a', 'ca1', 'a', 'ca2', 'b', 'cb1', 'a', 'ca3'])

    def test_insert_many_dict_and_list(self):
        class R(TestModel):
            k = TextField(column_name='key')
            v = IntegerField(column_name='value', default=0)
            class Meta:
                database = self.database

        data = (
            {'k': 'k1', 'v': 1},
            {R.k: 'k2', R.v: 2},
            {'key': 'k3', 'value': 3},
            ('k4', 4),
            ('k5', '5'),  # Will be converted properly.
            {R.k: 'k6', R.v: '6'},
            {'key': 'k7', 'value': '7'},
            {'k': 'kx'},
            ('ky',))

        param_str = ', '.join('(?, ?)' for _ in range(len(data)))
        queries = (
            R.insert_many(data),
            R.insert_many(data, fields=[R.k, R.v]),
            R.insert_many(data, fields=['k', 'v']))
        for query in queries:
            self.assertSQL(query, (
                'INSERT INTO "r" ("key", "value") VALUES %s' % param_str),
                ['k1', 1, 'k2', 2, 'k3', 3, 'k4', 4, 'k5', 5, 'k6', 6,
                 'k7', 7, 'kx', 0, 'ky', 0])

    def test_insert_modelalias(self):
        UA = User.alias('ua')
        self.assertSQL(UA.insert({UA.username: 'huey'}), (
            'INSERT INTO "users" ("username") VALUES (?)'), ['huey'])
        self.assertSQL(UA.insert(username='huey'), (
            'INSERT INTO "users" ("username") VALUES (?)'), ['huey'])

    def test_update(self):
        class Stat(TestModel):
            url = TextField()
            count = IntegerField()
            timestamp = TimestampField(utc=True)

        query = (Stat
                 .update({Stat.count: Stat.count + 1,
                          Stat.timestamp: datetime.datetime(2017, 1, 1)})
                 .where(Stat.url == '/peewee'))
        self.assertSQL(query, (
            'UPDATE "stat" SET "count" = ("stat"."count" + ?), '
            '"timestamp" = ? '
            'WHERE ("stat"."url" = ?)'),
            [1, 1483228800, '/peewee'])

        query = (Stat
                 .update(count=Stat.count + 1)
                 .where(Stat.url == '/peewee'))
        self.assertSQL(query, (
            'UPDATE "stat" SET "count" = ("stat"."count" + ?) '
            'WHERE ("stat"."url" = ?)'),
            [1, '/peewee'])

    def test_update_subquery(self):
        class U(TestModel):
            username = TextField()
            flood_count = IntegerField()

        class T(TestModel):
            user = ForeignKeyField(U)

        ctq = T.select(fn.COUNT(T.id) / 100).where(T.user == U.id)
        subq = (T
                .select(T.user)
                .group_by(T.user)
                .having(fn.COUNT(T.id) > 100))
        query = (U
                 .update({U.flood_count: ctq})
                 .where(U.id.in_(subq)))
        self.assertSQL(query, (
            'UPDATE "u" SET "flood_count" = ('
            'SELECT (COUNT("t1"."id") / ?) FROM "t" AS "t1" '
            'WHERE ("t1"."user_id" = "u"."id")) '
            'WHERE ("u"."id" IN ('
            'SELECT "t1"."user_id" FROM "t" AS "t1" '
            'GROUP BY "t1"."user_id" '
            'HAVING (COUNT("t1"."id") > ?)))'), [100, 100])

    def test_update_from(self):
        class SalesPerson(TestModel):
            first = TextField()
            last = TextField()

        class Account(TestModel):
            contact_first = TextField()
            contact_last = TextField()
            sales = ForeignKeyField(SalesPerson)

        query = (Account
                 .update(contact_first=SalesPerson.first,
                         contact_last=SalesPerson.last)
                 .from_(SalesPerson)
                 .where(Account.sales == SalesPerson.id))
        self.assertSQL(query, (
            'UPDATE "account" SET '
            '"contact_first" = "t1"."first", '
            '"contact_last" = "t1"."last" '
            'FROM "sales_person" AS "t1" '
            'WHERE ("account"."sales_id" = "t1"."id")'), [])

        query = (User
                 .update({User.username: Tweet.content})
                 .from_(Tweet)
                 .where(Tweet.content == 'tx'))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = "t1"."content" '
            'FROM "tweet" AS "t1" WHERE ("t1"."content" = ?)'), ['tx'])

    def test_update_from_qualnames(self):
        data = [(1, 'u1-x'), (2, 'u2-x')]
        vl = ValuesList(data, columns=('id', 'username'), alias='tmp')
        query = (User
                 .update({User.username: vl.c.username})
                 .from_(vl)
                 .where(User.id == vl.c.id))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = "tmp"."username" '
            'FROM (VALUES (?, ?), (?, ?)) AS "tmp"("id", "username") '
            'WHERE ("users"."id" = "tmp"."id")'), [1, 'u1-x', 2, 'u2-x'])

    def test_update_from_subselect(self):
        data = [(1, 'u1-x'), (2, 'u2-x')]
        vl = ValuesList(data, columns=('id', 'username'), alias='tmp')
        subq = vl.select(vl.c.id, vl.c.username)
        query = (User
                 .update({User.username: subq.c.username})
                 .from_(subq)
                 .where(User.id == subq.c.id))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = "t1"."username" FROM ('
            'SELECT "tmp"."id", "tmp"."username" '
            'FROM (VALUES (?, ?), (?, ?)) AS "tmp"("id", "username")) AS "t1" '
            'WHERE ("users"."id" = "t1"."id")'), [1, 'u1-x', 2, 'u2-x'])

    def test_delete(self):
        query = (Note
                 .delete()
                 .where(Note.author << (Person.select(Person.id)
                                        .where(Person.last == 'cat'))))
        self.assertSQL(query, ('DELETE FROM "note" '
                               'WHERE ("note"."author_id" IN ('
                               'SELECT "t1"."id" FROM "person" AS "t1" '
                               'WHERE ("t1"."last" = ?)))'), ['cat'])

        query = Note.delete().where(Note.author == Person(id=123))
        self.assertSQL(query, (
            'DELETE FROM "note" WHERE ("note"."author_id" = ?)'), [123])

    def test_delete_recursive(self):
        class User(TestModel):
            username = CharField()
        class Tweet(TestModel):
            user = ForeignKeyField(User, backref='tweets')
            content = TextField()
        class Relationship(TestModel):
            from_user = ForeignKeyField(User, backref='relationships')
            to_user = ForeignKeyField(User, backref='related_to')
        class Like(TestModel):
            user = ForeignKeyField(User)
            tweet = ForeignKeyField(Tweet)

        queries = list(User(id=1).dependencies())
        accum = []
        for expr, fk in list(queries):
            query = fk.model.delete().where(expr)
            accum.append(__sql__(query))

        self.assertEqual(sorted(accum), [
            ('DELETE FROM "like" WHERE ('
             '"like"."tweet_id" IN ('
             'SELECT "t1"."id" FROM "tweet" AS "t1" WHERE ('
             '"t1"."user_id" = ?)))', [1]),
            ('DELETE FROM "like" WHERE ("like"."user_id" = ?)', [1]),
            ('DELETE FROM "relationship" '
             'WHERE ("relationship"."from_user_id" = ?)', [1]),
            ('DELETE FROM "relationship" '
             'WHERE ("relationship"."to_user_id" = ?)', [1]),
            ('DELETE FROM "tweet" WHERE ("tweet"."user_id" = ?)', [1]),
        ])


# ===========================================================================
# Advanced Model SQL: RETURNING, window functions, CTE, LATERAL
# ===========================================================================

class TestModelAdvancedSQL(ModelDatabaseTestCase):
    database = get_in_memory_db()
    requires = [Category, Note, Person, Sample, User]

    def test_update_returning(self):
        query = (User
                 .update({User.username: 'zaizee'})
                 .where(User.username == 'charlie')
                 .returning(User))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = ? '
            'WHERE ("users"."username" = ?) '
            'RETURNING "users"."id", "users"."username"'),
            ['zaizee', 'charlie'])

        query = (User
                 .update({User.username: 'zaizee'})
                 .returning(User.id))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = ? '
            'RETURNING "users"."id"'), ['zaizee'])

    def test_update_returning_expression(self):
        query = (User
                 .update({User.username: User.username.concat('-x')})
                 .where(User.id > 2)
                 .returning(User.id, User.username.alias('new_name')))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = ("users"."username" || ?) '
            'WHERE ("users"."id" > ?) '
            'RETURNING "users"."id", "users"."username" AS "new_name"'),
            ['-x', 2])

    def test_delete_returning(self):
        query = (User
                 .delete()
                 .where(User.username == 'zaizee')
                 .returning(User))
        self.assertSQL(query, (
            'DELETE FROM "users" '
            'WHERE ("users"."username" = ?) '
            'RETURNING "users"."id", "users"."username"'), ['zaizee'])

        query = (User
                 .delete()
                 .returning(User.id.alias('removed_id')))
        self.assertSQL(query, (
            'DELETE FROM "users" '
            'RETURNING "users"."id" AS "removed_id"'), [])

    def test_delete_returning_no_fields(self):
        query = (User
                 .delete()
                 .where(User.id > 3)
                 .returning())
        self.assertSQL(query, (
            'DELETE FROM "users" WHERE ("users"."id" > ?)'), [3])

    def test_window_partition(self):
        query = (Sample
                 .select(
                     Sample.counter,
                     Sample.value,
                     fn.AVG(Sample.value).over(
                         partition_by=[Sample.counter]))
                 .order_by(Sample.counter))
        self.assertSQL(query, (
            'SELECT "t1"."counter", "t1"."value", AVG("t1"."value") '
            'OVER (PARTITION BY "t1"."counter") '
            'FROM "sample" AS "t1" ORDER BY "t1"."counter"'), [])

    def test_window_order(self):
        query = (Sample
                 .select(
                     Sample.value,
                     fn.RANK().over(order_by=[Sample.value])))
        self.assertSQL(query, (
            'SELECT "t1"."value", RANK() '
            'OVER (ORDER BY "t1"."value") '
            'FROM "sample" AS "t1"'), [])

    def test_window_empty_over(self):
        query = (Sample
                 .select(
                     Sample.value,
                     fn.LAG(Sample.value, 1).over())
                 .order_by(Sample.value))
        self.assertSQL(query, (
            'SELECT "t1"."value", LAG("t1"."value", ?) OVER () '
            'FROM "sample" AS "t1" '
            'ORDER BY "t1"."value"'), [1])

    def test_window_frame(self):
        query = (Sample
                 .select(
                     Sample.value,
                     fn.SUM(Sample.value).over(
                         partition_by=[Sample.counter],
                         order_by=[Sample.value],
                         start=Window.preceding(),
                         end=Window.CURRENT_ROW)))
        self.assertSQL(query, (
            'SELECT "t1"."value", SUM("t1"."value") '
            'OVER (PARTITION BY "t1"."counter" ORDER BY "t1"."value" '
            'ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) '
            'FROM "sample" AS "t1"'), [])

    def test_window_named(self):
        window = Window(partition_by=[Sample.counter],
                        order_by=[Sample.value])
        query = (Sample
                 .select(
                     Sample.counter,
                     fn.SUM(Sample.value).over(window),
                     fn.AVG(Sample.value).over(window))
                 .window(window))
        self.assertSQL(query, (
            'SELECT "t1"."counter", '
            'SUM("t1"."value") OVER "w", '
            'AVG("t1"."value") OVER "w" '
            'FROM "sample" AS "t1" '
            'WINDOW "w" AS (PARTITION BY "t1"."counter" '
            'ORDER BY "t1"."value")'), [])

    def test_window_filter(self):
        query = (Sample
                 .select(
                     fn.COUNT(Sample.id)
                     .filter(Sample.counter > 1)
                     .over(partition_by=[Sample.counter])))
        self.assertSQL(query, (
            'SELECT COUNT("t1"."id") '
            'FILTER (WHERE ("t1"."counter" > ?)) '
            'OVER (PARTITION BY "t1"."counter") '
            'FROM "sample" AS "t1"'), [1])

    def test_simple_cte(self):
        cte = (Category
               .select(Category.name, Category.parent)
               .cte('catz', columns=('name', 'parent')))
        query = (cte
                 .select_from(cte.c.name)
                 .order_by(cte.c.name))
        self.assertSQL(query, (
            'WITH "catz" ("name", "parent") AS ('
            'SELECT "t1"."name", "t1"."parent_id" '
            'FROM "category" AS "t1") '
            'SELECT "catz"."name" FROM "catz" '
            'ORDER BY "catz"."name"'), [])

    def test_recursive_cte(self):
        base = (Category
                .select(Category.name, Category.parent)
                .where(Category.name == 'root')
                .cte('tree', recursive=True, columns=('name', 'parent_id')))

        CA = Category.alias()
        recursive = (CA
                     .select(CA.name, CA.parent)
                     .join(base, on=(CA.parent == base.c.name)))
        cte = base.union_all(recursive)

        query = (cte
                 .select_from(cte.c.name)
                 .order_by(cte.c.name))
        self.assertSQL(query, (
            'WITH RECURSIVE "tree" ("name", "parent_id") AS ('
            'SELECT "t1"."name", "t1"."parent_id" '
            'FROM "category" AS "t1" '
            'WHERE ("t1"."name" = ?) '
            'UNION ALL '
            'SELECT "t2"."name", "t2"."parent_id" '
            'FROM "category" AS "t2" '
            'INNER JOIN "tree" ON ("t2"."parent_id" = "tree"."name")) '
            'SELECT "tree"."name" FROM "tree" '
            'ORDER BY "tree"."name"'), ['root'])

    def test_cte_in_subquery(self):
        cte = (User
               .select(User.id)
               .where(User.username.startswith('h'))
               .cte('filtered'))
        query = (User
                 .select()
                 .where(User.id.in_(cte.select(cte.c.id)))
                 .with_cte(cte))
        self.assertSQL(query, (
            'WITH "filtered" AS ('
            'SELECT "t1"."id" FROM "users" AS "t1" '
            'WHERE ("t1"."username" ILIKE ?)) '
            'SELECT "t2"."id", "t2"."username" FROM "users" AS "t2" '
            'WHERE ("t2"."id" IN ('
            'SELECT "filtered"."id" FROM "filtered"))'), ['h%'])

    def test_cte_update(self):
        cte = (User
               .select(User.id)
               .where(User.username == 'zaizee')
               .cte('to_update'))
        query = (User
                 .update({User.username: 'zaizee-x'})
                 .where(User.id.in_(cte.select(cte.c.id)))
                 .with_cte(cte))
        self.assertSQL(query, (
            'WITH "to_update" AS ('
            'SELECT "t1"."id" FROM "users" AS "t1" '
            'WHERE ("t1"."username" = ?)) '
            'UPDATE "users" SET "username" = ? '
            'WHERE ("users"."id" IN ('
            'SELECT "to_update"."id" FROM "to_update"))'),
            ['zaizee', 'zaizee-x'])

    def test_cte_delete(self):
        cte = (User
               .select(User.id)
               .where(User.username.startswith('z'))
               .cte('to_delete'))
        query = (User
                 .delete()
                 .where(User.id.in_(cte.select(cte.c.id)))
                 .with_cte(cte))
        self.assertSQL(query, (
            'WITH "to_delete" AS ('
            'SELECT "t1"."id" FROM "users" AS "t1" '
            'WHERE ("t1"."username" ILIKE ?)) '
            'DELETE FROM "users" '
            'WHERE ("users"."id" IN ('
            'SELECT "to_delete"."id" FROM "to_delete"))'), ['z%'])

    def test_materialized_cte(self):
        for materialized, clause in ((True, 'MATERIALIZED '),
                                     (False, 'NOT MATERIALIZED '),
                                     (None, '')):
            cte = (User
                   .select(User.id)
                   .cte('uids', materialized=materialized))
            query = cte.select_from(cte.c.id)
            self.assertSQL(query, (
                'WITH "uids" AS %s('
                'SELECT "t1"."id" FROM "users" AS "t1") '
                'SELECT "uids"."id" FROM "uids"') % clause, [])

    def test_lateral_join(self):
        PA = Person.alias()
        subq = (Note
                .select(Note.content)
                .where(Note.author == PA.id)
                .limit(1))
        query = (PA
                 .select(PA.first, subq.c.content)
                 .join(subq, JOIN.LEFT_LATERAL, on=True))
        self.assertSQL(query, (
            'SELECT "t1"."first", "t2"."content" '
            'FROM "person" AS "t1" '
            'LEFT JOIN LATERAL ('
            'SELECT "t3"."content" FROM "note" AS "t3" '
            'WHERE ("t3"."author_id" = "t1"."id") '
            'LIMIT ?) AS "t2" ON ?'), [1, True])

    def test_lateral_join_inner(self):
        subq = (Note
                .select(Note.content)
                .where(Note.author == Person.id)
                .order_by(Note.id.desc())
                .limit(2))
        query = (Person
                 .select(Person.first, subq.c.content)
                 .join(subq, JOIN.LATERAL, on=True))
        self.assertSQL(query, (
            'SELECT "t1"."first", "t2"."content" '
            'FROM "person" AS "t1" '
            'LATERAL ('
            'SELECT "t3"."content" FROM "note" AS "t3" '
            'WHERE ("t3"."author_id" = "t1"."id") '
            'ORDER BY "t3"."id" DESC LIMIT ?) AS "t2" ON ?'), [2, True])

    def test_ensure_join_noop(self):
        """ensure_join is a no-op when the join already exists."""
        query = (User
                 .select(User, Tweet.content)
                 .join(Tweet)
                 .switch(User)
                 .ensure_join(User, Tweet))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username", "t2"."content" '
            'FROM "users" AS "t1" '
            'INNER JOIN "tweet" AS "t2" ON ("t2"."user_id" = "t1"."id")'),
            [])

    def test_ensure_join_adds(self):
        """ensure_join adds the join when it doesn't exist."""
        query = (User
                 .select(User, Tweet.content)
                 .ensure_join(User, Tweet))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username", "t2"."content" '
            'FROM "users" AS "t1" '
            'INNER JOIN "tweet" AS "t2" ON ("t2"."user_id" = "t1"."id")'),
            [])

    def test_for_update(self):
        query = (User
                 .select()
                 .where(User.username == 'huey')
                 .for_update())
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" '
            'FROM "users" AS "t1" '
            'WHERE ("t1"."username" = ?) FOR UPDATE'),
            ['huey'], for_update=True)

    def test_for_update_options(self):
        query = User.select().for_update(for_update='FOR SHARE')
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" '
            'FROM "users" AS "t1" FOR SHARE'), [], for_update=True)

        query = User.select().for_update(nowait=True)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" '
            'FROM "users" AS "t1" FOR UPDATE NOWAIT'), [], for_update=True)

        query = User.select().for_update(skip_locked=True)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" '
            'FROM "users" AS "t1" FOR UPDATE SKIP LOCKED'), [],
            for_update=True)

    def test_for_update_unsupported(self):
        """FOR UPDATE on a database that doesn't support it raises."""
        query = User.select().for_update()
        self.assertRaises(ValueError, self.assertSQL, query,
                          '', [])


# ===========================================================================
# ON CONFLICT shortcut SQL (on_conflict_ignore / on_conflict_replace)
# ===========================================================================

class TestOnConflictShortcutSQL(ModelDatabaseTestCase):
    database = get_in_memory_db()
    requires = [User, Emp]

    def test_on_conflict_ignore(self):
        query = User.insert(username='test').on_conflict_ignore()
        self.assertSQL(query, (
            'INSERT OR IGNORE INTO "users" ("username") VALUES (?)'),
            ['test'])

    def test_on_conflict_replace(self):
        query = Emp.insert(first='h', last='c', empno='1').on_conflict_replace()
        self.assertSQL(query, (
            'INSERT OR REPLACE INTO "emp" '
            '("first", "last", "empno") VALUES (?, ?, ?)'),
            ['h', 'c', '1'])

    def test_on_conflict_both_target_and_constraint_raises(self):
        self.assertRaises(
            ValueError,
            User.insert(username='test').on_conflict,
            conflict_target=[User.username],
            conflict_constraint='foo')


# ===========================================================================
# ON CONFLICT / upsert SQL with Models
# ===========================================================================

@requires_pglike
class TestOnConflictSQL(ModelDatabaseTestCase):
    requires = [Emp, OCTest, UKVP]

    def test_atomic_update(self):
        query = OCTest.insert(a='foo', b=1).on_conflict(
            conflict_target=(OCTest.a,),
            update={OCTest.b: OCTest.b + 2})

        self.assertSQL(query, (
            'INSERT INTO "oc_test" ("a", "b", "c") VALUES (?, ?, ?) '
            'ON CONFLICT ("a") '
            'DO UPDATE SET "b" = ("oc_test"."b" + ?) '
            'RETURNING "oc_test"."id"'), ['foo', 1, 0, 2])

    def test_on_conflict_do_nothing(self):
        query = OCTest.insert(a='foo', b=1).on_conflict(action='IGNORE')
        self.assertSQL(query, (
            'INSERT INTO "oc_test" ("a", "b", "c") VALUES (?, ?, ?) '
            'ON CONFLICT DO NOTHING '
            'RETURNING "oc_test"."id"'), ['foo', 1, 0])

        query = OCTest.insert(a='foo', b=1).on_conflict(
            conflict_target=(OCTest.a,),
            action='IGNORE')
        self.assertSQL(query, (
            'INSERT INTO "oc_test" ("a", "b", "c") VALUES (?, ?, ?) '
            'ON CONFLICT ("a") DO NOTHING '
            'RETURNING "oc_test"."id"'), ['foo', 1, 0])

    def test_update_where_clause(self):
        # Add a new row with the given "a" value. If a conflict occurs,
        # re-insert with b=b+2 so long as the original b < 3.
        query = OCTest.insert(a='foo', b=1).on_conflict(
            conflict_target=(OCTest.a,),
            update={OCTest.b: OCTest.b + 2},
            where=(OCTest.b < 3))
        self.assertSQL(query, (
            'INSERT INTO "oc_test" ("a", "b", "c") VALUES (?, ?, ?) '
            'ON CONFLICT ("a") DO UPDATE SET "b" = ("oc_test"."b" + ?) '
            'WHERE ("oc_test"."b" < ?) '
            'RETURNING "oc_test"."id"'), ['foo', 1, 0, 2, 3])

    def test_conflict_target_constraint_where(self):
        fields = [UKVP.key, UKVP.value, UKVP.extra]
        data = [('k1', 1, 2), ('k2', 2, 3)]

        query = (UKVP.insert_many(data, fields)
                 .on_conflict(conflict_target=(UKVP.key, UKVP.value),
                              conflict_where=(UKVP.extra > 1),
                              preserve=(UKVP.extra,),
                              where=(UKVP.key != 'kx')))
        self.assertSQL(query, (
            'INSERT INTO "ukvp" ("key", "value", "extra") '
            'VALUES (?, ?, ?), (?, ?, ?) '
            'ON CONFLICT ("key", "value") WHERE ("extra" > ?) '
            'DO UPDATE SET "extra" = EXCLUDED."extra" '
            'WHERE ("ukvp"."key" != ?) RETURNING "ukvp"."id"'),
            ['k1', 1, 2, 'k2', 2, 3, 1, 'kx'])

    def test_preserve_and_update(self):
        query = (UKVP
                 .insert(key='k1', value=1, extra=10)
                 .on_conflict(
                     conflict_target=(UKVP.key,),
                     preserve=(UKVP.value,),
                     update={UKVP.extra: UKVP.extra + 1}))
        self.assertSQL(query, (
            'INSERT INTO "ukvp" ("key", "value", "extra") '
            'VALUES (?, ?, ?) '
            'ON CONFLICT ("key") DO UPDATE SET '
            '"value" = EXCLUDED."value", '
            '"extra" = ("ukvp"."extra" + ?) '
            'RETURNING "ukvp"."id"'), ['k1', 1, 10, 1])

    def test_preserve_with_where(self):
        query = (UKVP
                 .insert(key='k1', value=1, extra=10)
                 .on_conflict(
                     conflict_target=(UKVP.key,),
                     preserve=(UKVP.value,),
                     where=(UKVP.extra < 100)))
        self.assertSQL(query, (
            'INSERT INTO "ukvp" ("key", "value", "extra") '
            'VALUES (?, ?, ?) '
            'ON CONFLICT ("key") DO UPDATE SET '
            '"value" = EXCLUDED."value" '
            'WHERE ("ukvp"."extra" < ?) '
            'RETURNING "ukvp"."id"'), ['k1', 1, 10, 100])

    @skip_if(IS_CRDB)
    def test_on_conflict_named_constraint(self):
        query = (UKVP
                 .insert(key='k1', value=1)
                 .on_conflict(
                     conflict_constraint='ukvp_key',
                     update={UKVP.value: UKVP.value + 1}))
        self.assertSQL(query, (
            'INSERT INTO "ukvp" ("key", "value") VALUES (?, ?) '
            'ON CONFLICT ON CONSTRAINT "ukvp_key" '
            'DO UPDATE SET "value" = ("ukvp"."value" + ?) '
            'RETURNING "ukvp"."id"'), ['k1', 1, 1])


# ===========================================================================
# String-based field references in queries
# ===========================================================================

class TestStringsForFieldsInsertUpdate(ModelDatabaseTestCase):
    database = get_in_memory_db()
    requires = [Note, Person, Relationship]

    def test_insert(self):
        qkwargs = Person.insert(first='huey', last='kitty')
        qliteral = Person.insert({'first': 'huey', 'last': 'kitty'})
        for query in (qkwargs, qliteral):
            self.assertSQL(query, (
                'INSERT INTO "person" ("first", "last") VALUES (?, ?)'),
                ['huey', 'kitty'])

    def test_insert_many(self):
        data = [
            {'first': 'huey', 'last': 'cat'},
            {'first': 'zaizee', 'last': 'cat'},
            {'first': 'mickey', 'last': 'dog'}]
        query = Person.insert_many(data)
        self.assertSQL(query, (
            'INSERT INTO "person" ("first", "last") VALUES (?, ?), (?, ?), '
            '(?, ?)'), ['huey', 'cat', 'zaizee', 'cat', 'mickey', 'dog'])

    def test_update(self):
        qkwargs = Person.update(last='kitty').where(Person.last == 'cat')
        qliteral = Person.update({'last': 'kitty'}).where(Person.last == 'cat')
        for query in (qkwargs, qliteral):
            self.assertSQL(query, (
                'UPDATE "person" SET "last" = ? WHERE ("person"."last" = ?)'),
                ['kitty', 'cat'])


# ===========================================================================
# Compound SELECT (UNION / INTERSECT / EXCEPT) with Models
# ===========================================================================

compound_db = get_in_memory_db()

class CompoundTestModel(Model):
    class Meta:
        database = compound_db

class Alpha(CompoundTestModel):
    alpha = IntegerField()

class Beta(CompoundTestModel):
    beta = IntegerField()
    other = IntegerField(default=0)

class Gamma(CompoundTestModel):
    gamma = IntegerField()
    other = IntegerField(default=1)


class TestModelCompoundSelect(BaseTestCase):
    def test_unions(self):
        lhs = Alpha.select(Alpha.alpha)
        rhs = Beta.select(Beta.beta)
        self.assertSQL((lhs | rhs), (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" UNION '
            'SELECT "t2"."beta" FROM "beta" AS "t2"'), [])

        rrhs = Gamma.select(Gamma.gamma)
        query = (lhs | (rhs | rrhs))
        self.assertSQL(query, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" UNION '
            'SELECT "t2"."beta" FROM "beta" AS "t2" UNION '
            'SELECT "t3"."gamma" FROM "gamma" AS "t3"'), [])

    def test_union_same_model(self):
        q1 = Alpha.select(Alpha.alpha)
        q2 = Alpha.select(Alpha.alpha)
        q3 = Alpha.select(Alpha.alpha)
        compound = (q1 | q2) | q3
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" UNION '
            'SELECT "t2"."alpha" FROM "alpha" AS "t2" UNION '
            'SELECT "t3"."alpha" FROM "alpha" AS "t3"'), [])

        compound = q1 | (q2 | q3)
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" UNION '
            'SELECT "t2"."alpha" FROM "alpha" AS "t2" UNION '
            'SELECT "t3"."alpha" FROM "alpha" AS "t3"'), [])

    def test_where(self):
        q1 = Alpha.select(Alpha.alpha).where(Alpha.alpha < 2)
        q2 = Alpha.select(Alpha.alpha).where(Alpha.alpha > 5)
        compound = q1 | q2
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "t2"."alpha" FROM "alpha" AS "t2" '
            'WHERE ("t2"."alpha" > ?)'), [2, 5])

        q3 = Beta.select(Beta.beta).where(Beta.beta < 3)
        q4 = Beta.select(Beta.beta).where(Beta.beta > 4)
        compound = q1 | q3
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "t2"."beta" FROM "beta" AS "t2" '
            'WHERE ("t2"."beta" < ?)'), [2, 3])

        compound = q1 | q3 | q2 | q4
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "t2"."beta" FROM "beta" AS "t2" '
            'WHERE ("t2"."beta" < ?) '
            'UNION '
            'SELECT "t3"."alpha" FROM "alpha" AS "t3" '
            'WHERE ("t3"."alpha" > ?) '
            'UNION '
            'SELECT "t4"."beta" FROM "beta" AS "t4" '
            'WHERE ("t4"."beta" > ?)'), [2, 3, 5, 4])

    def test_limit(self):
        lhs = Alpha.select(Alpha.alpha).order_by(Alpha.alpha).limit(3)
        rhs = Beta.select(Beta.beta).order_by(Beta.beta).limit(4)
        compound = (lhs | rhs).limit(5)
        # This may be invalid SQL, but this at least documents the behavior.
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'ORDER BY "t1"."alpha" LIMIT ? UNION '
            'SELECT "t2"."beta" FROM "beta" AS "t2" '
            'ORDER BY "t2"."beta" LIMIT ? LIMIT ?'), [3, 4, 5])

    def test_union_from(self):
        lhs = Alpha.select(Alpha.alpha).where(Alpha.alpha < 2)
        rhs = Alpha.select(Alpha.alpha).where(Alpha.alpha > 5)
        compound = (lhs | rhs).alias('cq')
        query = Alpha.select(compound.c.alpha).from_(compound)
        self.assertSQL(query, (
            'SELECT "cq"."alpha" FROM ('
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "t2"."alpha" FROM "alpha" AS "t2" '
            'WHERE ("t2"."alpha" > ?)) AS "cq"'), [2, 5])

        b = Beta.select(Beta.beta).where(Beta.beta < 3)
        g = Gamma.select(Gamma.gamma).where(Gamma.gamma < 0)
        compound = (lhs | b | g).alias('cq')
        query = Alpha.select(SQL('1')).from_(compound)
        self.assertSQL(query, (
            'SELECT 1 FROM ('
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" < ?) '
            'UNION SELECT "t2"."beta" FROM "beta" AS "t2" '
            'WHERE ("t2"."beta" < ?) '
            'UNION SELECT "t3"."gamma" FROM "gamma" AS "t3" '
            'WHERE ("t3"."gamma" < ?)) AS "cq"'), [2, 3, 0])

    def test_parentheses(self):
        query = (Alpha.select().where(Alpha.alpha < 2) |
                 Beta.select(Beta.id, Beta.beta).where(Beta.beta > 3))
        self.assertSQL(query, (
            '(SELECT "t1"."id", "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" < ?)) '
            'UNION '
            '(SELECT "t2"."id", "t2"."beta" FROM "beta" AS "t2" '
            'WHERE ("t2"."beta" > ?))'),
            [2, 3], compound_select_parentheses=True)

    def test_where_in(self):
        union = (Alpha.select(Alpha.alpha) |
                 Beta.select(Beta.beta))
        query = Alpha.select().where(Alpha.alpha << union)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."alpha" '
            'FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" IN '
            '(SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'UNION '
            'SELECT "t2"."beta" FROM "beta" AS "t2"))'), [])

    def test_union_method(self):
        lhs = Alpha.select(Alpha.alpha).where(Alpha.alpha > 1)
        rhs = Beta.select(Beta.beta).where(Beta.beta < 10)
        query = lhs.union(rhs)
        self.assertSQL(query, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" > ?) '
            'UNION '
            'SELECT "t2"."beta" FROM "beta" AS "t2" '
            'WHERE ("t2"."beta" < ?)'), [1, 10])

    def test_intersect_method(self):
        lhs = Alpha.select(Alpha.alpha)
        rhs = Beta.select(Beta.beta)
        query = lhs.intersect(rhs)
        self.assertSQL(query, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'INTERSECT '
            'SELECT "t2"."beta" FROM "beta" AS "t2"'), [])

    def test_except_method(self):
        lhs = Alpha.select(Alpha.alpha)
        rhs = Beta.select(Beta.beta)
        query = lhs.except_(rhs)
        self.assertSQL(query, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'EXCEPT '
            'SELECT "t2"."beta" FROM "beta" AS "t2"'), [])


# ===========================================================================
# Model index SQL and miscellaneous
# ===========================================================================

class TestModelIndex(BaseTestCase):
    database = SqliteDatabase(None)

    def test_model_index(self):
        class Article(Model):
            name = TextField()
            timestamp = TimestampField()
            status = IntegerField()
            flags = IntegerField()

        aidx = ModelIndex(Article, (Article.name, Article.timestamp),)
        self.assertSQL(aidx, (
            'CREATE INDEX IF NOT EXISTS "article_name_timestamp" ON "article" '
            '("name", "timestamp")'), [])

        aidx = aidx.where(Article.status == 1)
        self.assertSQL(aidx, (
            'CREATE INDEX IF NOT EXISTS "article_name_timestamp" ON "article" '
            '("name", "timestamp") '
            'WHERE ("status" = ?)'), [1])

        aidx = ModelIndex(Article, (Article.timestamp.desc(),
                                    Article.flags.bin_and(4)), unique=True)
        self.assertSQL(aidx, (
            'CREATE UNIQUE INDEX IF NOT EXISTS "article_timestamp" '
            'ON "article" ("timestamp" DESC, ("flags" & ?))'), [4])

    def test_unique_index_nulls(self):
        class A(Model):
            a = CharField()
            b = CharField()
            class Meta:
                database = self.database

        idx = ModelIndex(A, ('a', 'b'), unique=True)
        self.assertSQL(A._schema._create_index(idx), (
            'CREATE UNIQUE INDEX IF NOT EXISTS '
            '"a_a_b" ON "a" (a, b)'))

        idx = idx.nulls_distinct(False)
        self.assertSQL(A._schema._create_index(idx), (
            'CREATE UNIQUE INDEX IF NOT EXISTS '
            '"a_a_b" ON "a" (a, b) NULLS NOT DISTINCT'))

        idx = idx.nulls_distinct(True)
        self.assertSQL(A._schema._create_index(idx), (
            'CREATE UNIQUE INDEX IF NOT EXISTS '
            '"a_a_b" ON "a" (a, b) NULLS DISTINCT'))

        idx._unique = False
        self.assertRaises(ValueError, lambda: idx.nulls_distinct(True))
        self.assertRaises(ValueError, lambda: idx.nulls_distinct(False))


class TestModelArgument(BaseTestCase):
    database = SqliteDatabase(None)

    def test_model_as_argument(self):
        class Post(TestModel):
            content = TextField()
            timestamp = DateTimeField()
            class Meta:
                database = self.database

        query = (Post
                 .select(Post.id, fn.score(Post).alias('score'))
                 .order_by(Post.timestamp))
        self.assertSQL(query, (
            'SELECT "t1"."id", score("t1") AS "score" '
            'FROM "post" AS "t1" ORDER BY "t1"."timestamp"'), [])


# ===========================================================================
# Query cloning behavior and regressions
# ===========================================================================

# Lightweight Table objects for testing query cloning with raw tables.
# NOTE: identical definitions exist in results.py for query execution tests.
QUser = Table('users', ['id', 'username'])
QTweet = Table('tweet', ['id', 'user_id', 'content'])


class TestQueryCloning(BaseTestCase):
    def test_clone_tables(self):
        self._do_test_clone(QUser, QTweet)

    def test_clone_models(self):
        class User(TestModel):
            username = TextField()
            class Meta:
                table_name = 'users'
        class Tweet(TestModel):
            user = ForeignKeyField(User, backref='tweets')
            content = TextField()
        self._do_test_clone(User, Tweet)

    def _do_test_clone(self, User, Tweet):
        query = Tweet.select(Tweet.id)
        base_sql = 'SELECT "t1"."id" FROM "tweet" AS "t1"'
        self.assertSQL(query, base_sql, [])

        qj = query.join(User, on=(Tweet.user_id == User.id))
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qj, (
            'SELECT "t1"."id" FROM "tweet" AS "t1" '
            'INNER JOIN "users" AS "t2" ON ("t1"."user_id" = "t2"."id")'), [])

        qw = query.where(Tweet.id > 3)
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qw, base_sql + ' WHERE ("t1"."id" > ?)', [3])

        qw2 = qw.where(Tweet.id < 6)
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qw, base_sql + ' WHERE ("t1"."id" > ?)', [3])
        self.assertSQL(qw2, base_sql + (' WHERE (("t1"."id" > ?) '
                                        'AND ("t1"."id" < ?))'), [3, 6])

        qo = query.order_by(Tweet.id)
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qo, base_sql + ' ORDER BY "t1"."id"', [])

        qo2 = qo.order_by(Tweet.content, Tweet.id)
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qo, base_sql + ' ORDER BY "t1"."id"', [])
        self.assertSQL(qo2,
                       base_sql + ' ORDER BY "t1"."content", "t1"."id"', [])

        qg = query.group_by(Tweet.id)
        self.assertSQL(query, base_sql, [])
        self.assertSQL(qg, base_sql + ' GROUP BY "t1"."id"', [])


class NLM(TestModel):
    a = IntegerField()
    b = IntegerField()

class TestRegressionNodeListClone(BaseTestCase):
    def test_node_list_clone_expr(self):
        expr = (NLM.a + NLM.b)
        query = NLM.select(expr.alias('expr')).order_by(expr).distinct(expr)
        self.assertSQL(query, (
            'SELECT DISTINCT ON ("t1"."a" + "t1"."b") '
            '("t1"."a" + "t1"."b") AS "expr" '
            'FROM "nlm" AS "t1" '
            'ORDER BY ("t1"."a" + "t1"."b")'), [])


# ===========================================================================
# Gap coverage: NoopModelSelect SQL, model group_by with model arg,
# ModelSelect cross join error, FieldAlias delegation
# ===========================================================================

class TestNoopModelSelectSQL(ModelDatabaseTestCase):
    database = get_in_memory_db()
    requires = [User]

    def test_noop_sql_generation(self):
        query = User.noop()
        sql_str, params = query.sql()
        # SQLite: SELECT 0 WHERE (0)
        self.assertIn('SELECT', sql_str)
        self.assertIn('0', sql_str)

    def test_noop_cursor_wrapper_type(self):
        from peewee import CursorWrapper
        query = User.noop()
        result = query.execute()
        self.assertIsInstance(result, CursorWrapper)


class TestFieldAliasOperators(ModelDatabaseTestCase):
    database = get_in_memory_db()
    requires = [User]

    def test_field_alias_contains(self):
        UA = User.alias('ua')
        query = UA.select().where(UA.username.contains('test'))
        sql, params = query.sql()
        # On SQLite, ILIKE maps to LIKE. Just verify the query is valid.
        self.assertIn('"ua"', sql)
        # The param should contain the wrapped search term.
        self.assertEqual(params, ['%test%'])

    def test_field_alias_is_null(self):
        UA = User.alias('ua')
        query = UA.select().where(UA.username.is_null())
        sql, params = query.sql()
        self.assertIn('IS NULL', sql)

    def test_field_alias_between(self):
        UA = User.alias('ua')
        query = UA.select().where(UA.id.between(1, 10))
        sql, params = query.sql()
        self.assertIn('BETWEEN', sql)
        self.assertEqual(params, [1, 10])

    def test_field_alias_in_(self):
        UA = User.alias('ua')
        query = UA.select().where(UA.id.in_([1, 2, 3]))
        sql, params = query.sql()
        self.assertIn('IN', sql)
        self.assertEqual(params, [1, 2, 3])
