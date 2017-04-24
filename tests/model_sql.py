from peewee import *

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
            'SELECT "t1"."first", "t1"."last", COUNT("t2"."id") AS ct '
            'FROM "person" AS "t1" '
            'INNER JOIN "note" AS "t2" ON ("t2"."author_id" = "t1"."id") '
            'WHERE ('
            '("t1"."last" = ?) AND '
            '("t1"."id" < ?))'), ['Leifer', 4])

    def test_where_coerce(self):
        query = Person.select(Person.last).where(Person.id == '1337')
        self.assertSQL(query, (
            'SELECT "t1"."last" FROM "person" AS "t1" '
            'WHERE ("t1"."id" = ?)'), [1337])

        query = Person.select(Person.last).where(Person.id < (Person.id - '5'))
        self.assertSQL(query, (
            'SELECT "t1"."last" FROM "person" AS "t1" '
            'WHERE ("t1"."id" < ("t1"."id" - ?))'), [5])

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

    def test_insert_query(self):
        select = (Person
                  .select(Person.id, Person.first)
                  .where(Person.last == 'cat'))
        query = Note.insert_from(select, (Note.author, Note.content))
        self.assertSQL(query, ('INSERT INTO "note" ("author_id", "content") '
                               'SELECT "t1"."id", "t1"."first" '
                               'FROM "person" AS "t1" '
                               'WHERE ("t1"."last" = ?)'), ['cat'])

    def test_insert_returning(self):
        class TestDB(Database):
            options = Database.options + {'returning_clause': True}

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

    def test_update(self):
        class Stat(TestModel):
            url = TextField()
            count = IntegerField()
            timestamp = TimestampField()

        query = (Stat
                 .update({Stat.count: Stat.count + 1,
                          Stat.timestamp: datetime.datetime(2017, 1, 1)})
                 .where(Stat.url == '/peewee'))
        self.assertSQL(query, (
            'UPDATE "stat" SET "count" = ("count" + ?), "timestamp" = ? '
            'WHERE ("url" = ?)'),
            [1, 1483250400, '/peewee'])

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
             '"t1"."user_id" IN ('
             'SELECT "t2"."id" FROM "user" AS "t2" WHERE ("t2"."id" = ?)))))',
             [1]),
            ('DELETE FROM "like" WHERE ("user_id" IN ('
             'SELECT "t1"."id" FROM "user" AS "t1" WHERE ("t1"."id" = ?)))',
             [1]),
            ('DELETE FROM "relationship" WHERE ('
             '"from_user_id" IN ('
             'SELECT "t1"."id" FROM "user" AS "t1" WHERE ("t1"."id" = ?)))',
             [1]),
            ('DELETE FROM "relationship" WHERE ('
             '"to_user_id" IN ('
             'SELECT "t1"."id" FROM "user" AS "t1" WHERE ("t1"."id" = ?)))',
             [1]),
            ('DELETE FROM "tweet" WHERE ('
             '"user_id" IN ('
             'SELECT "t1"."id" FROM "user" AS "t1" WHERE ("t1"."id" = ?)))',
             [1]),
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
            'FROM "huey"."withschema" AS "t1" '
            'WHERE ("t1"."data" = ?)'), ['zaizee'])


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
            'SELECT "a1"."beta" FROM "beta" AS "a1"'), [])

        rrhs = Gamma.select(Gamma.gamma)
        query = (lhs | (rhs | rrhs))
        self.assertSQL(query, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" UNION '
            'SELECT "a1"."beta" FROM "beta" AS "a1" UNION '
            'SELECT "b1"."gamma" FROM "gamma" AS "b1"'), [])

    def test_union_same_model(self):
        q1 = Alpha.select(Alpha.alpha)
        q2 = Alpha.select(Alpha.alpha)
        q3 = Alpha.select(Alpha.alpha)
        compound = (q1 | q2) | q3
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" UNION '
            'SELECT "a1"."alpha" FROM "alpha" AS "a1" UNION '
            'SELECT "b1"."alpha" FROM "alpha" AS "b1"'), [])

        compound = q1 | (q2 | q3)
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" UNION '
            'SELECT "a1"."alpha" FROM "alpha" AS "a1" UNION '
            'SELECT "b1"."alpha" FROM "alpha" AS "b1"'), [])

    def test_where(self):
        q1 = Alpha.select(Alpha.alpha).where(Alpha.alpha < 2)
        q2 = Alpha.select(Alpha.alpha).where(Alpha.alpha > 5)
        compound = q1 | q2
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "a1"."alpha" FROM "alpha" AS "a1" '
            'WHERE ("a1"."alpha" > ?)'), [2, 5])

        q3 = Beta.select(Beta.beta).where(Beta.beta < 3)
        q4 = Beta.select(Beta.beta).where(Beta.beta > 4)
        compound = q1 | q3
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "a1"."beta" FROM "beta" AS "a1" '
            'WHERE ("a1"."beta" < ?)'), [2, 3])

        compound = q1 | q3 | q2 | q4
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" < ?) '
            'UNION '
            'SELECT "a1"."beta" FROM "beta" AS "a1" '
            'WHERE ("a1"."beta" < ?) '
            'UNION '
            'SELECT "b1"."alpha" FROM "alpha" AS "b1" '
            'WHERE ("b1"."alpha" > ?) '
            'UNION '
            'SELECT "c1"."beta" FROM "beta" AS "c1" '
            'WHERE ("c1"."beta" > ?)'), [2, 3, 5, 4])

    def test_limit(self):
        lhs = Alpha.select(Alpha.alpha).order_by(Alpha.alpha).limit(3)
        rhs = Beta.select(Beta.beta).order_by(Beta.beta).limit(4)
        compound = (lhs | rhs).limit(5)
        # This may be invalid SQL, but this at least documents the behavior.
        self.assertSQL(compound, (
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'ORDER BY "t1"."alpha" LIMIT 3 UNION '
            'SELECT "a1"."beta" FROM "beta" AS "a1" '
            'ORDER BY "a1"."beta" LIMIT 4 LIMIT 5'), [])

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
            'SELECT "a1"."alpha" FROM "alpha" AS "a1" '
            'WHERE ("a1"."alpha" > ?)) AS "cq"'), [2, 5])

        b = Beta.select(Beta.beta).where(Beta.beta < 3)
        g = Gamma.select(Gamma.gamma).where(Gamma.gamma < 0)
        compound = (lhs | b | g).alias('cq')
        query = Alpha.select(SQL('1')).from_(compound)
        self.assertSQL(query, (
            'SELECT 1 FROM ('
            'SELECT "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" < ?) '
            'UNION SELECT "a1"."beta" FROM "beta" AS "a1" '
            'WHERE ("a1"."beta" < ?) '
            'UNION SELECT "b1"."gamma" FROM "gamma" AS "b1" '
            'WHERE ("b1"."gamma" < ?)) AS "cq"'), [2, 3, 0])

    def test_parentheses(self):
        query = (Alpha.select().where(Alpha.alpha < 2) |
                 Beta.select(Beta.id, Beta.beta).where(Beta.beta > 3))
        self.assertSQL(query, (
            '(SELECT "t1"."id", "t1"."alpha" FROM "alpha" AS "t1" '
            'WHERE ("t1"."alpha" < ?)) '
            'UNION '
            '(SELECT "a1"."id", "a1"."beta" FROM "beta" AS "a1" '
            'WHERE ("a1"."beta" > ?))'),
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
            'SELECT "a1"."beta" FROM "beta" AS "a1"))'), [])
