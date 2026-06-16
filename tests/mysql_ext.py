import datetime

from peewee import *
from playhouse.mysql_ext import JSONField
from playhouse.mysql_ext import Match
from playhouse.mysql_ext import MySQLJSONField

from .base import IS_MYSQL_JSON
from .base import IS_MYSQL_JSON_OVERLAPS
from .base import ModelDatabaseTestCase
from .base import ModelTestCase
from .base import TestModel
from .base import db_loader
from .base import requires_mysql
from .base import skip_if
from .base import skip_unless


try:
    import mariadb
except ImportError:
    mariadb = mariadb_db = None
else:
    mariadb_db = db_loader('mariadb')
try:
    import mysql.connector as mysql_connector
except ImportError:
    mysql_connector = None

mysql_ext_db = db_loader('mysqlconnector')


class Person(TestModel):
    first = CharField()
    last = CharField()
    dob = DateField(default=datetime.date(2000, 1, 1))


class Note(TestModel):
    person = ForeignKeyField(Person, backref='notes')
    content = TextField()
    timestamp = DateTimeField(default=datetime.datetime.now)


class KJ(TestModel):
    key = CharField(primary_key=True, max_length=100)
    data = JSONField()


@requires_mysql
@skip_if(mysql_connector is None, 'mysql-connector not installed')
class TestMySQLConnector(ModelTestCase):
    database = mysql_ext_db
    requires = [Person, Note]

    def test_basic_operations(self):
        with self.database.atomic():
            charlie, huey, zaizee = [Person.create(first=f, last='leifer')
                                     for f in ('charlie', 'huey', 'zaizee')]
            # Use nested-transaction.
            with self.database.atomic():
                data = (
                    (charlie, ('foo', 'bar', 'zai')),
                    (huey, ('meow', 'purr', 'hiss')),
                    (zaizee, ()))
                for person, notes in data:
                    for note in notes:
                        Note.create(person=person, content=note)

            with self.database.atomic() as sp:
                Person.create(first='x', last='y')
                sp.rollback()

        people = Person.select().order_by(Person.first)
        self.assertEqual([person.first for person in people],
                         ['charlie', 'huey', 'zaizee'])

        with self.assertQueryCount(1):
            notes = (Note
                     .select(Note, Person)
                     .join(Person)
                     .order_by(Note.content))
            self.assertEqual([(n.person.first, n.content) for n in notes], [
                ('charlie', 'bar'),
                ('charlie', 'foo'),
                ('huey', 'hiss'),
                ('huey', 'meow'),
                ('huey', 'purr'),
                ('charlie', 'zai')])


@requires_mysql
@skip_if(mariadb is None, 'mariadb connector not installed')
class TestMariaDBConnector(TestMySQLConnector):
    database = mariadb_db


@requires_mysql
class TestMatchExpression(ModelDatabaseTestCase):
    requires = [Person]

    def test_match_expression(self):
        query = (Person
                 .select()
                 .where(Match(Person.first, 'charlie')))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."first", "t1"."last", "t1"."dob" '
            'FROM "person" AS "t1" '
            'WHERE MATCH("t1"."first") AGAINST(?)'), ['charlie'])

        query = (Person
                 .select()
                 .where(Match((Person.first, Person.last), 'huey AND zaizee',
                              'IN BOOLEAN MODE')))
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."first", "t1"."last", "t1"."dob" '
            'FROM "person" AS "t1" '
            'WHERE MATCH("t1"."first", "t1"."last") '
            'AGAINST(? IN BOOLEAN MODE)'), ['huey AND zaizee'])


class OM(TestModel):
    data = MySQLJSONField()


@requires_mysql
@skip_unless(IS_MYSQL_JSON_OVERLAPS,
             'requires JSON_OVERLAPS (MySQL 8.0.17+ / MariaDB 10.9+)')
class TestMySQLJSONOverlaps(ModelTestCase):
    requires = [OM]

    def setUp(self):
        super(TestMySQLJSONOverlaps, self).setUp()
        OM.create(data=['python', 'orm'])
        OM.create(data=['rust', 'go'])
        OM.create(data=[1, 2, 3])
        OM.create(data={'tags': ['python', 'rust']})

    def test_contains_any(self):
        q = OM.select().where(OM.data.contains_any(['python', 'java']))
        self.assertEqual(q.count(), 1)

    def test_contains_any_numbers(self):
        q = OM.select().where(OM.data.contains_any([2, 99]))
        self.assertEqual(q.count(), 1)

    def test_contains_any_path(self):
        q = OM.select().where(OM.data['tags'].contains_any(['python']))
        self.assertEqual(q.count(), 1)
