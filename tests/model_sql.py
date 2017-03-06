from peewee import *

from .base import BaseTestCase
from .base import TestModel
from .base import __sql__
from .base_models import Category
from .base_models import Note
from .base_models import Person
from .base_models import Relationship


class TestModelSQL(BaseTestCase):
    def assertCreateTable(self, model_class, expected):
        sql, params = model_class._schema._create_table(False).query()
        self.assertEqual(params, [])

        indexes = []
        for create_index in model_class._schema._create_indexes(False):
            isql, params = create_index.query()
            self.assertEqual(params, [])
            indexes.append(isql)

        self.assertEqual([sql] + indexes, expected)

    def test_table_and_index_creation(self):
        self.assertCreateTable(Person, [
            ('CREATE TABLE "person" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"first" VARCHAR(255) NOT NULL, '
             '"last" VARCHAR(255) NOT NULL, '
             '"dob" DATE NOT NULL)'),
            'CREATE INDEX "person_dob" ON "person" ("dob")',
            ('CREATE UNIQUE INDEX "person_first_last" ON '
             '"person" ("first", "last")'),
        ])

        self.assertCreateTable(Note, [
            ('CREATE TABLE "note" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"author_id" INTEGER NOT NULL, '
             '"content" TEXT NOT NULL, '
             'FOREIGN KEY ("author_id") REFERENCES "person" ("id"))'),
            'CREATE INDEX "note_author" ON "note" ("author_id")',
        ])

        self.assertCreateTable(Category, [
            ('CREATE TABLE "category" ('
             '"name" VARCHAR(20) NOT NULL PRIMARY KEY, '
             '"parent_id" VARCHAR(20), '
             'FOREIGN KEY ("parent_id") REFERENCES "category" ("name"))'),
            'CREATE INDEX "category_parent" ON "category" ("parent_id")',
        ])

        self.assertCreateTable(Relationship, [
            ('CREATE TABLE "relationship" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"from_person_id" INTEGER NOT NULL, '
             '"to_person_id" INTEGER NOT NULL, '
             'FOREIGN KEY ("from_person_id") REFERENCES "person" ("id"), '
             'FOREIGN KEY ("to_person_id") REFERENCES "person" ("id"))'),
            ('CREATE INDEX "relationship_from_person" '
             'ON "relationship" ("from_person_id")'),
            ('CREATE INDEX "relationship_to_person" '
             'ON "relationship" ("to_person_id")'),
        ])

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
            [1, datetime.datetime(2017, 1, 1), '/peewee'])

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
