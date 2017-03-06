import sys
import unittest

from peewee import *

from .base import ModelTestCase
from .base import TestModel
from .base_models import Note
from .base_models import Person


class TestModelAPIs(ModelTestCase):
    requires = [Person, Note]

    def add_person(self, first, last):
        return Person.create(first=first, last=last,
                             dob=datetime.date(2000, 1, 1))

    def add_notes(self, person, *notes):
        for note in notes:
            Note.create(author=person, content=note)

    def test_assertQueryCount(self):
        self.add_notes(self.add_person('charlie', 'l'), 'foo', 'bar', 'baz')
        def do_test(n):
            with self.assertQueryCount(n):
                authors = [note.author.first for note in Note.select()]

        self.assertRaises(AssertionError, do_test, 1)
        self.assertRaises(AssertionError, do_test, 3)
        do_test(4)
        self.assertRaises(AssertionError, do_test, 5)

    def test_create(self):
        with self.assertQueryCount(1):
            huey = self.add_person('huey', 'cat')
            self.assertEqual(huey.first, 'huey')
            self.assertEqual(huey.last, 'cat')
            self.assertEqual(huey.id, 1)

        with self.assertQueryCount(1):
            note = Note.create(author=huey, content='meow')
            self.assertEqual(note.author.id, huey.id)
            self.assertEqual(note.author.first, 'huey')
            self.assertEqual(note.content, 'meow')
            self.assertEqual(note.id, 1)

    def test_model_select(self):
        query = (Note
                 .select(Note.content, Person.first, Person.last)
                 .join(Person)
                 .order_by(Person.first, Note.content))
        self.assertSQL(query, (
            'SELECT "t1"."content", "t2"."first", "t2"."last" '
            'FROM "note" AS "t1" '
            'INNER JOIN "person" AS "t2" '
            'ON ("t1"."author_id" = "t2"."id") '
            'ORDER BY "t2"."first", "t1"."content"'), [])

        huey = self.add_person('huey', 'cat')
        mickey = self.add_person('mickey', 'dog')
        zaizee = self.add_person('zaizee', 'cat')

        self.add_notes(huey, 'meow', 'hiss', 'purr')
        self.add_notes(mickey, 'woof', 'whine')

        with self.assertQueryCount(1):
            notes = list(query)
            self.assertEqual([(n.content, n.author.first, n.author.last)
                              for n in notes], [
                                  ('hiss', 'huey', 'cat'),
                                  ('meow', 'huey', 'cat'),
                                  ('purr', 'huey', 'cat'),
                                  ('whine', 'mickey', 'dog'),
                                  ('woof', 'mickey', 'dog')])

    def test_multi_join(self):
        class User(TestModel):
            username = CharField()

        class Tweet(TestModel):
            user = ForeignKeyField(User, backref='tweets')
            content = TextField()
            timestamp = TimestampField()

        class Favorite(TestModel):
            user = ForeignKeyField(User, backref='favorites')
            tweet = ForeignKeyField(Tweet, backref='favorites')

        User._schema.create_table()
        Tweet._schema.create_table()
        Favorite._schema.create_table()

        TweetUser = User.alias('u2')

        query = (Favorite
                 .select(Favorite.id,
                         Tweet.content,
                         User.username,
                         TweetUser.username)
                 .join(Tweet)
                 .join(TweetUser, on=(Tweet.user == TweetUser.id))
                 .switch(Favorite)
                 .join(User)
                 .order_by(Tweet.content, Favorite.id))
        self.assertSQL(query, (
            'SELECT '
            '"t1"."id", "t2"."content", "t3"."username", "u2"."username" '
            'FROM "favorite" AS "t1" '
            'INNER JOIN "tweet" AS "t2" ON ("t1"."tweet_id" = "t2"."id") '
            'INNER JOIN "user" AS "u2" ON ("t2"."user_id" = "u2"."id") '
            'INNER JOIN "user" AS "t3" ON ("t1"."user_id" = "t3"."id") '
            'ORDER BY "t2"."content", "t1"."id"'), [])

        u1 = User.create(username='u1')
        u2 = User.create(username='u2')
        u3 = User.create(username='u3')
        t1_1 = Tweet.create(user=u1, content='t1-1')
        t1_2 = Tweet.create(user=u1, content='t1-2')
        t2_1 = Tweet.create(user=u2, content='t2-1')
        t2_2 = Tweet.create(user=u2, content='t2-2')
        favorites = ((u1, t2_1),
                     (u1, t2_2),
                     (u2, t1_1),
                     (u3, t1_2),
                     (u3, t2_2))
        for user, tweet in favorites:
            Favorite.create(user=user, tweet=tweet)

        with self.assertQueryCount(1):
            accum = [(f.tweet.user.username, f.tweet.content, f.user.username)
                     for f in query]
            self.assertEqual(accum, [
                ('u1', 't1-1', 'u2'),
                ('u1', 't1-2', 'u3'),
                ('u2', 't2-1', 'u1'),
                ('u2', 't2-2', 'u1'),
                ('u2', 't2-2', 'u3')])

    def test_compound_select(self):
        class Register(TestModel):
            value = IntegerField()
            class Meta:
                table_name = 'tests_register1'

        Register.create_schema()
        for i in range(10):
            Register.create(value=i)

        q1 = Register.select().where(Register.value < 2)
        q2 = Register.select().where(Register.value > 7)
        c1 = (q1 | q2).order_by(SQL('1'))

        self.assertSQL(c1, (
            'SELECT "t1"."id", "t1"."value" FROM "tests_register1" AS "t1" '
            'WHERE ("t1"."value" < ?) UNION '
            'SELECT "a1"."id", "a1"."value" FROM "tests_register1" AS "a1" '
            'WHERE ("a1"."value" > ?) ORDER BY 1'), [2, 7])

        self.assertEqual([row.value for row in c1], [0, 1, 8, 9])

        q3 = Register.select().where(Register.value == 5)
        c2 = (c1.order_by() | q3).order_by(SQL('"value"'))

        self.assertSQL(c2, (
            'SELECT "t1"."id", "t1"."value" FROM "tests_register1" AS "t1" '
            'WHERE ("t1"."value" < ?) UNION '
            'SELECT "a1"."id", "a1"."value" FROM "tests_register1" AS "a1" '
            'WHERE ("a1"."value" > ?) UNION '
            'SELECT "b1"."id", "b1"."value" FROM "tests_register1" AS "b1" '
            'WHERE ("b1"."value" = ?) ORDER BY "value"'), [2, 7, 5])

        self.assertEqual([row.value for row in c2], [0, 1, 5, 8, 9])
