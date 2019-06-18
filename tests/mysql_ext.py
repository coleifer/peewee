import datetime

from peewee import *
from playhouse.mysql_ext import JSONField
from playhouse.mysql_ext import Match

from .base import IS_MYSQL_JSON
from .base import ModelDatabaseTestCase
from .base import ModelTestCase
from .base import TestModel
from .base import db_loader
from .base import requires_mysql
from .base import skip_unless


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
class TestMySQLConnector(ModelTestCase):
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
@skip_unless(IS_MYSQL_JSON, 'requires MySQL 5.7+ or 8.x')
class TestMySQLJSONField(ModelTestCase):
    requires = [KJ]

    def test_mysql_json_field(self):
        values = (
            0, 1.0, 2.3,
            True, False,
            'string',
            ['foo', 'bar', 'baz'],
            {'k1': 'v1', 'k2': 'v2'},
            {'k3': [0, 1.0, 2.3], 'k4': {'x1': 'y1', 'x2': 'y2'}})
        for i, value in enumerate(values):
            # Verify data can be written.
            kj = KJ.create(key='k%s' % i, data=value)

            # Verify value is deserialized correctly.
            kj_db = KJ['k%s' % i]
            self.assertEqual(kj_db.data, value)

        with self.assertRaises(IntegrityError):
            KJ.create(key='kx', data=None)


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
