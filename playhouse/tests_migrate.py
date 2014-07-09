import datetime
import os
import unittest

from peewee import *
from peewee import create_model_tables
from peewee import drop_model_tables
from peewee import print_
from playhouse.migrate import *

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    import MySQLdb as mysql
except ImportError:
    try:
        import pymysql as mysql
    except ImportError:
        mysql = None
mysql = None

sqlite_db = SqliteDatabase(':memory:')

TEST_VERBOSITY = int(os.environ.get('PEEWEE_TEST_VERBOSITY') or 1)

class Tag(Model):
    tag = CharField()

class Person(Model):
    first_name = CharField()
    last_name = CharField()
    dob = DateField(null=True)

class User(Model):
    id = CharField(primary_key=True, max_length=20)

class Page(Model):
    name = TextField(unique=True, null=True)
    user = ForeignKeyField(User, null=True, related_name='pages')

MODELS = [
    Person,
    Tag,
    User,
    Page,
]

class BaseMigrationTestCase(object):
    database = None
    migrator_class = None

    # Each database behaves slightly differently.
    _exception_add_not_null = True

    _person_data = [
        ('Charlie', 'Leifer', None),
        ('Huey', 'Kitty', datetime.date(2011, 5, 1)),
        ('Mickey', 'Dog', datetime.date(2008, 6, 1)),
    ]

    def setUp(self):
        for model_class in MODELS:
            model_class._meta.database = self.database

        drop_model_tables(MODELS, fail_silently=True)
        create_model_tables(MODELS)
        self.migrator = self.migrator_class(self.database)

        if 'newpages' in User._meta.reverse_rel:
            del User._meta.reverse_rel['newpages']
            delattr(User, 'newpages')

    def test_add_column(self):
        # Create some fields with a variety of NULL / default values.
        df = DateTimeField(null=True)
        df_def = DateTimeField(default=datetime.datetime(2012, 1, 1))
        cf = CharField(max_length=200, default='')
        bf = BooleanField(default=True)
        ff = FloatField(default=0)

        # Create two rows in the Tag table to test the handling of adding
        # non-null fields.
        t1 = Tag.create(tag='t1')
        t2 = Tag.create(tag='t2')

        # Convenience function for generating `add_column` migrations.
        def add_column(field_name, field_obj):
            return self.migrator.add_column('tag', field_name, field_obj)

        # Run the migration.
        migrate(
            add_column('pub_date', df),
            add_column('modified_date', df_def),
            add_column('comment', cf),
            add_column('is_public', bf),
            add_column('popularity', ff))

        # Create a new tag model to represent the fields we added.
        class NewTag(Model):
            tag = CharField()
            pub_date = df
            modified_date = df_def
            comment = cf
            is_public = bf
            popularity = ff

            class Meta:
                database = self.database
                db_table = Tag._meta.db_table

        query = (NewTag
                 .select(
                     NewTag.id,
                     NewTag.tag,
                     NewTag.pub_date,
                     NewTag.modified_date,
                     NewTag.comment,
                     NewTag.is_public,
                     NewTag.popularity)
                 .order_by(NewTag.tag.asc()))

        # Verify the resulting rows are correct.
        self.assertEqual(list(query.tuples()), [
            (t1.id, 't1', None, datetime.datetime(2012, 1, 1), '', True, 0.0),
            (t2.id, 't2', None, datetime.datetime(2012, 1, 1), '', True, 0.0),
        ])

    def _create_people(self):
        for first, last, dob in self._person_data:
            Person.create(first_name=first, last_name=last, dob=dob)

    def get_column_names(self, tbl):
        cursor = self.database.execute_sql('select * from %s limit 1' % tbl)
        return set([col[0] for col in cursor.description])

    def test_drop_column(self):
        self._create_people()
        migrate(
            self.migrator.drop_column('person', 'last_name'),
            self.migrator.drop_column('person', 'dob'))

        column_names = self.get_column_names('person')
        self.assertEqual(column_names, set(['id', 'first_name']))

    def test_rename_column(self):
        self._create_people()
        migrate(
            self.migrator.rename_column('person', 'first_name', 'first'),
            self.migrator.rename_column('person', 'last_name', 'last'))

        column_names = self.get_column_names('person')
        self.assertEqual(column_names, set(['id', 'first', 'last', 'dob']))

        class NewPerson(Model):
            first = CharField()
            last = CharField()
            dob = DateField()

            class Meta:
                database = self.database
                db_table = Person._meta.db_table

        query = (NewPerson
                 .select(
                     NewPerson.first,
                     NewPerson.last,
                     NewPerson.dob)
                 .order_by(NewPerson.first))
        self.assertEqual(list(query.tuples()), self._person_data)

    def test_rename_gh380(self):
        u1 = User.create(id='charlie')
        u2 = User.create(id='huey')
        p1 = Page.create(name='p1-1', user=u1)
        p2 = Page.create(name='p2-1', user=u1)
        p3 = Page.create(name='p3-2', user=u2)

        migrate(self.migrator.rename_column('page', 'name', 'title'))

        column_names = self.get_column_names('page')
        self.assertEqual(column_names, set(['id', 'title', 'user_id']))

        class NewPage(Model):
            title = TextField(unique=True, null=True)
            user = ForeignKeyField(User, null=True, related_name='newpages')

            class Meta:
                database = self.database
                db_table = Page._meta.db_table

        query = (NewPage
                 .select(
                     NewPage.title,
                     NewPage.user)
                 .order_by(NewPage.title))
        self.assertEqual(
            [(np.title, np.user.id) for np in query],
            [('p1-1', 'charlie'), ('p2-1', 'charlie'), ('p3-2', 'huey')])

    def test_add_not_null(self):
        self._create_people()

        def addNotNull():
            with self.database.transaction():
                migrate(self.migrator.add_not_null('person', 'dob'))

        # We cannot make the `dob` field not null because there is currently
        # a null value there.
        if self._exception_add_not_null:
            self.assertRaises(IntegrityError, addNotNull)

        (Person
         .update(dob=datetime.date(2000, 1, 2))
         .where(Person.dob >> None)
         .execute())

        # Now we can make the column not null.
        addNotNull()

        # And attempting to insert a null value results in an integrity error.
        with self.database.transaction():
            self.assertRaises(
                IntegrityError,
                Person.create,
                first_name='Kirby',
                last_name='Snazebrauer',
                dob=None)

    def test_drop_not_null(self):
        self._create_people()
        migrate(
            self.migrator.drop_not_null('person', 'first_name'),
            self.migrator.drop_not_null('person', 'last_name'))

        p = Person.create(first_name=None, last_name=None)
        query = (Person
                 .select()
                 .where(
                     (Person.first_name >> None) &
                     (Person.last_name >> None)))
        self.assertEqual(query.count(), 1)

    def test_rename_table(self):
        t1 = Tag.create(tag='t1')
        t2 = Tag.create(tag='t2')

        # Move the tag data into a new model/table.
        class Tag_asdf(Tag):
            pass
        self.assertEqual(Tag_asdf._meta.db_table, 'tag_asdf')

        # Drop the new table just to be safe.
        Tag_asdf.drop_table(True)

        # Rename the tag table.
        migrate(self.migrator.rename_table('tag', 'tag_asdf'))

        # Verify the data was moved.
        query = (Tag_asdf
                 .select()
                 .order_by(Tag_asdf.tag))
        self.assertEqual([t.tag for t in query], ['t1', 't2'])

        # Verify the old table is gone.
        with self.database.transaction():
            self.assertRaises(
                DatabaseError,
                Tag.create,
                tag='t3')

    def test_add_index(self):
        # Create a unique index on first and last names.
        columns = ('first_name', 'last_name')
        migrate(self.migrator.add_index('person', columns, True))

        Person.create(first_name='first', last_name='last')
        with self.database.transaction():
            self.assertRaises(
                IntegrityError,
                Person.create,
                first_name='first',
                last_name='last')

    def test_drop_index(self):
        # Create a unique index.
        self.test_add_index()

        # Now drop the unique index.
        migrate(
            self.migrator.drop_index('person', 'person_first_name_last_name'))

        Person.create(first_name='first', last_name='last')
        query = (Person
                 .select()
                 .where(
                     (Person.first_name == 'first') &
                     (Person.last_name == 'last')))
        self.assertEqual(query.count(), 2)

    def test_add_and_remove(self):
        operations = []
        field = CharField(default='foo')
        for i in range(10):
            operations.append(self.migrator.add_column('tag', 'foo', field))
            operations.append(self.migrator.drop_column('tag', 'foo'))

        migrate(*operations)
        col_names = self.get_column_names('tag')
        self.assertEqual(col_names, set(['id', 'tag']))

    def test_multiple_operations(self):
        self.database.execute_sql('drop table if exists person_baze;')
        self.database.execute_sql('drop table if exists person_nugg;')
        self._create_people()

        field_n = CharField(null=True)
        field_d = CharField(default='test')
        operations = [
            self.migrator.add_column('person', 'field_null', field_n),
            self.migrator.drop_column('person', 'first_name'),
            self.migrator.add_column('person', 'field_default', field_d),
            self.migrator.rename_table('person', 'person_baze'),
            self.migrator.rename_table('person_baze', 'person_nugg'),
            self.migrator.rename_column('person_nugg', 'last_name', 'last'),
            self.migrator.add_index('person_nugg', ('last',), True),
        ]
        migrate(*operations)

        class PersonNugg(Model):
            field_null = field_n
            field_default = field_d
            last = CharField()
            dob = DateField(null=True)

            class Meta:
                database = self.database
                db_table = 'person_nugg'

        people = (PersonNugg
                  .select(
                      PersonNugg.field_null,
                      PersonNugg.field_default,
                      PersonNugg.last,
                      PersonNugg.dob)
                  .order_by(PersonNugg.last)
                  .tuples())
        expected = [
            (None, 'test', 'Dog', datetime.date(2008, 6, 1)),
            (None, 'test', 'Kitty', datetime.date(2011, 5, 1)),
            (None, 'test', 'Leifer', None),
        ]
        self.assertEqual(list(people), expected)

        with self.database.transaction():
            self.assertRaises(
                IntegrityError,
                PersonNugg.create,
                last='Leifer',
                field_default='bazer')

    def test_add_foreign_key(self):
        if hasattr(Person, 'newtag_set'):
            delattr(Person, 'newtag_set')
            del Person._meta.reverse_rel['newtag_set']

        field = ForeignKeyField(Person, null=True, to_field=Person.id)
        migrate(self.migrator.add_column('tag', 'person_id', field))

        class NewTag(Tag):
            person = field

            class Meta:
                db_table = 'tag'

        p = Person.create(first_name='First', last_name='Last')
        t1 = NewTag.create(tag='t1', person=p)
        t2 = NewTag.create(tag='t2')

        t1_db = NewTag.get(NewTag.tag == 't1')
        self.assertEqual(t1_db.person, p)

        t2_db = NewTag.get(NewTag.tag == 't2')
        self.assertEqual(t2_db.person, None)


class SqliteMigrationTestCase(BaseMigrationTestCase, unittest.TestCase):
    database = sqlite_db
    migrator_class = SqliteMigrator


if psycopg2:
    pg_db = PostgresqlDatabase('peewee_test')

    class PostgresqlMigrationTestCase(BaseMigrationTestCase, unittest.TestCase):
        database = pg_db
        migrator_class = PostgresqlMigrator
elif TEST_VERBOSITY > 0:
    print_('Skipping postgres migrations, driver not found.')

if mysql:
    mysql_db = MySQLDatabase('peewee_test')

    class MySQLMigrationTestCase(BaseMigrationTestCase, unittest.TestCase):
        database = mysql_db
        migrator_class = MySQLMigrator

        # MySQL does not raise an exception when adding a not null constraint
        # to a column that contains NULL values.
        _exception_add_not_null = False
elif TEST_VERBOSITY > 0:
    print_('Skipping mysql migrations, driver not found.')
