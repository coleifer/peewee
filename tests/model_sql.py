import datetime

from peewee import *
from peewee import Database
from peewee import ModelIndex

from .base import get_in_memory_db
from .base import BaseTestCase
from .base import ModelDatabaseTestCase
from .base import TestModel
from .base import __sql__
from .base_models import *


class TestModelSQL(ModelDatabaseTestCase):
    database = get_in_memory_db()
    requires = [Category, Note, Person, Relationship]

    def test_select(self):
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

    def test_value_flattening(self):
        sql = ('SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
               'WHERE ("t1"."username" IN (?, ?))')
        expected = (sql, ['foo', 'bar'])

        users = User.select().where(User.username.in_(['foo', 'bar']))
        self.assertSQL(users, *expected)

        users = User.select().where(User.username.in_(('foo', 'bar')))
        self.assertSQL(users, *expected)

        users = User.select().where(User.username.in_(set(['foo', 'bar'])))
        # Sets are unordered so params may be in either order:
        sql, params = __sql__(users)
        self.assertEqual(sql, expected[0])
        self.assertTrue(params in (['foo', 'bar'], ['bar', 'foo']))

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

        query = Note.alias().select()
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."content" '
            'FROM "notes"."note" AS "t1"'), [])

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
            'VALUES (?) RETURNING "id"'), ['zaizee'])

        class Person(Model):
            name = CharField()
            ssn = CharField(primary_key=True)
            class Meta:
                database = TestDB(None)

        query = Person.insert({Person.name: 'charlie', Person.ssn: '123'})
        self.assertSQL(query, (
            'INSERT INTO "person" ("ssn", "name") VALUES (?, ?) '
            'RETURNING "ssn"'), ['123', 'charlie'])

        query = Person.insert({Person.name: 'huey'}).returning()
        self.assertSQL(query, (
            'INSERT INTO "person" ("name") VALUES (?)'), ['huey'])

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
            'UPDATE "stat" SET "count" = ("count" + ?), "timestamp" = ? '
            'WHERE ("url" = ?)'),
            [1, 1483228800, '/peewee'])

        query = (Stat
                 .update(count=Stat.count + 1)
                 .where(Stat.url == '/peewee'))
        self.assertSQL(query, (
            'UPDATE "stat" SET "count" = ("count" + ?) '
            'WHERE ("url" = ?)'),
            [1, '/peewee'])

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
            '"contact_first" = "first", '
            '"contact_last" = "last" '
            'FROM "sales_person" AS "t1" '
            'WHERE ("sales_id" = "id")'), [])

        query = (User
                 .update({User.username: QualifiedNames(Tweet.content)})
                 .from_(Tweet)
                 .where(Tweet.content == 'tx'))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = "t1"."content" '
            'FROM "tweet" AS "t1" WHERE ("content" = ?)'), ['tx'])

    def test_update_from_qualnames(self):
        data = [(1, 'u1-x'), (2, 'u2-x')]
        vl = ValuesList(data, columns=('id', 'username'), alias='tmp')
        query = (User
                 .update({User.username: QualifiedNames(vl.c.username)})
                 .from_(vl)
                 .where(QualifiedNames(User.id == vl.c.id)))
        self.assertSQL(query, (
            'UPDATE "users" SET "username" = "tmp"."username" '
            'FROM (VALUES (?, ?), (?, ?)) AS "tmp"("id", "username") '
            'WHERE ("users"."id" = "tmp"."id")'), [1, 'u1-x', 2, 'u2-x'])

    def test_update_from_subselect(self):
        data = [(1, 'u1-x'), (2, 'u2-x')]
        vl = ValuesList(data, columns=('id', 'username'), alias='tmp')
        subq = vl.select(vl.c.id, vl.c.username)
        query = (User
                 .update({User.username: QualifiedNames(subq.c.username)})
                 .from_(subq)
                 .where(QualifiedNames(User.id == subq.c.id)))
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
                               'WHERE ("author_id" IN ('
                               'SELECT "t1"."id" FROM "person" AS "t1" '
                               'WHERE ("t1"."last" = ?)))'), ['cat'])

        query = Note.delete().where(Note.author == Person(id=123))
        self.assertSQL(query, 'DELETE FROM "note" WHERE ("author_id" = ?)',
                       [123])

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
             '"tweet_id" IN ('
             'SELECT "t1"."id" FROM "tweet" AS "t1" WHERE ('
             '"t1"."user_id" = ?)))', [1]),
            ('DELETE FROM "like" WHERE ("user_id" = ?)', [1]),
            ('DELETE FROM "relationship" WHERE ("from_user_id" = ?)', [1]),
            ('DELETE FROM "relationship" WHERE ("to_user_id" = ?)', [1]),
            ('DELETE FROM "tweet" WHERE ("user_id" = ?)', [1]),
        ])

    def test_aliases(self):
        class A(TestModel):
            a = CharField()
            class Meta:
                table_alias = 'a_tbl'
        class B(TestModel):
            b = CharField()
            a_link = ForeignKeyField(A)
        class C(TestModel):
            c = CharField()
            b_link = ForeignKeyField(B)
        class D(TestModel):
            d = CharField()
            c_link = ForeignKeyField(C)
            class Meta:
                table_alias = 'd_tbl'

        query = (D
                 .select(D.d, C.c)
                 .join(C)
                 .where(C.b_link << (
                     B.select(B.id).join(A).where(A.a == 'a'))))
        self.assertSQL(query, (
            'SELECT "d_tbl"."d", "t1"."c" '
            'FROM "d" AS "d_tbl" '
            'INNER JOIN "c" AS "t1" ON ("d_tbl"."c_link_id" = "t1"."id") '
            'WHERE ("t1"."b_link_id" IN ('
            'SELECT "t2"."id" FROM "b" AS "t2" '
            'INNER JOIN "a" AS "a_tbl" ON ("t2"."a_link_id" = "a_tbl"."id") '
            'WHERE ("a_tbl"."a" = ?)))'), ['a'])

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


class TestStringsForFieldsa(ModelDatabaseTestCase):
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
                'UPDATE "person" SET "last" = ? WHERE ("last" = ?)'),
                ['kitty', 'cat'])


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
            'SELECT "t2"."alpha" FROM "alpha" AS "t2"'), [])

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
            'SELECT "t2"."beta" FROM "beta" AS "t2" '
            'WHERE ("t2"."beta" > ?)'), [2, 3, 5, 4])

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
