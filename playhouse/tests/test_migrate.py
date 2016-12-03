import datetime
import os

from peewee import *
from peewee import print_
from playhouse.migrate import *
from playhouse.test_utils import count_queries
from playhouse.tests.base import database_initializer
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import skip_if

try:
    from psycopg2cffi import compat
    compat.register()
except ImportError:
    pass

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

if mysql:
    mysql_db = database_initializer.get_database('mysql')
else:
    mysql_db = None

if psycopg2:
    pg_db = database_initializer.get_database('postgres')
else:
    pg_db = None

sqlite_db = SqliteDatabase(':memory:')

class Tag(Model):
    tag = CharField()

class Person(Model):
    first_name = CharField()
    last_name = CharField()
    dob = DateField(null=True)

class User(Model):
    id = CharField(primary_key=True, max_length=20)
    password = CharField(default='secret')

    class Meta:
        db_table = 'users'

class Page(Model):
    name = CharField(max_length=100, unique=True, null=True)
    user = ForeignKeyField(User, null=True, related_name='pages')

class Session(Model):
    user = ForeignKeyField(User, unique=True, related_name='sessions')
    updated_at = DateField(null=True)

class IndexModel(Model):
    first_name = CharField()
    last_name = CharField()
    data = IntegerField(unique=True)

    class Meta:
        database = sqlite_db
        indexes = (
            (('first_name', 'last_name'), True),
        )

MODELS = [
    Person,
    Tag,
    User,
    Page,
    Session
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
        super(BaseMigrationTestCase, self).setUp()
        for model_class in MODELS:
            model_class._meta.database = self.database

        self.database.drop_tables(MODELS, True)
        self.database.create_tables(MODELS)
        self.migrator = self.migrator_class(self.database)

        if 'newpages' in User._meta.reverse_rel:
            del User._meta.reverse_rel['newpages']
            delattr(User, 'newpages')

    def tearDown(self):
        super(BaseMigrationTestCase, self).tearDown()
        for model_class in MODELS:
            model_class._meta.database = self.database
        self.database.drop_tables(MODELS, True)

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

        User.create(id='charlie', password='12345')
        User.create(id='huey', password='meow')
        migrate(self.migrator.drop_column('users', 'password'))

        column_names = self.get_column_names('users')
        self.assertEqual(column_names, set(['id']))
        data = [row for row in User.select(User.id).order_by(User.id).tuples()]
        self.assertEqual(data, [
            ('charlie',),
            ('huey',),])

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
            title = CharField(max_length=100, unique=True, null=True)
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
            with self.assertRaisesCtx((IntegrityError, OperationalError)):
                Person.create(
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

    def test_modify_not_null_foreign_key(self):
        user = User.create(id='charlie')
        Page.create(name='null user')
        Page.create(name='charlie', user=user)

        def addNotNull():
            with self.database.transaction():
                migrate(self.migrator.add_not_null('page', 'user_id'))

        if self._exception_add_not_null:
            self.assertRaises(IntegrityError, addNotNull)

        Page.update(user=user).where(Page.user.is_null()).execute()
        addNotNull()

        # And attempting to insert a null value results in an integrity error.
        with self.database.transaction():
            with self.assertRaisesCtx((OperationalError, IntegrityError)):
                Page.create(
                    name='fails',
                    user=None)

        # Now we will drop it.
        with self.database.transaction():
            migrate(self.migrator.drop_not_null('page', 'user_id'))

        self.assertEqual(Page.select().where(Page.user.is_null()).count(), 0)
        Page.create(name='succeeds', user=None)
        self.assertEqual(Page.select().where(Page.user.is_null()).count(), 1)

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

        # Ensure no foreign keys are present at the beginning of the test.
        self.assertEqual(self.database.get_foreign_keys('tag'), [])

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

        foreign_keys = self.database.get_foreign_keys('tag')
        self.assertEqual(len(foreign_keys), 1)
        foreign_key = foreign_keys[0]
        self.assertEqual(foreign_key.column, 'person_id')
        self.assertEqual(foreign_key.dest_column, 'id')
        self.assertEqual(foreign_key.dest_table, 'person')

    def test_drop_foreign_key(self):
        migrate(self.migrator.drop_column('page', 'user_id'))
        columns = self.database.get_columns('page')
        self.assertEqual(
            sorted(column.name for column in columns),
            ['id', 'name'])
        self.assertEqual(self.database.get_foreign_keys('page'), [])

    def test_rename_foreign_key(self):
        migrate(self.migrator.rename_column('page', 'user_id', 'huey_id'))
        columns = self.database.get_columns('page')
        self.assertEqual(
            sorted(column.name for column in columns),
            ['huey_id', 'id', 'name'])

        foreign_keys = self.database.get_foreign_keys('page')
        self.assertEqual(len(foreign_keys), 1)
        foreign_key = foreign_keys[0]
        self.assertEqual(foreign_key.column, 'huey_id')
        self.assertEqual(foreign_key.dest_column, 'id')
        self.assertEqual(foreign_key.dest_table, 'users')

    def test_rename_unique_foreign_key(self):
        migrate(self.migrator.rename_column('session', 'user_id', 'huey_id'))
        columns = self.database.get_columns('session')
        self.assertEqual(
            sorted(column.name for column in columns),
            ['huey_id', 'id', 'updated_at'])

        foreign_keys = self.database.get_foreign_keys('session')
        self.assertEqual(len(foreign_keys), 1)
        foreign_key = foreign_keys[0]
        self.assertEqual(foreign_key.column, 'huey_id')
        self.assertEqual(foreign_key.dest_column, 'id')
        self.assertEqual(foreign_key.dest_table, 'users')

class SqliteMigrationTestCase(BaseMigrationTestCase, PeeweeTestCase):
    database = sqlite_db
    migrator_class = SqliteMigrator

    def setUp(self):
        super(SqliteMigrationTestCase, self).setUp()
        IndexModel.drop_table(True)
        IndexModel.create_table()

    def test_valid_column_required(self):
        self.assertRaises(
            ValueError,
            migrate,
            self.migrator.drop_column('page', 'column_does_not_exist'))

        self.assertRaises(
            ValueError,
            migrate,
            self.migrator.rename_column('page', 'xx', 'yy'))

    def test_table_case_insensitive(self):
        migrate(self.migrator.drop_column('PaGe', 'name'))
        column_names = self.get_column_names('page')
        self.assertEqual(column_names, set(['id', 'user_id']))

        testing_field = CharField(default='xx')
        migrate(self.migrator.add_column('pAGE', 'testing', testing_field))
        column_names = self.get_column_names('page')
        self.assertEqual(column_names, set(['id', 'user_id', 'testing']))

        migrate(self.migrator.drop_column('indeXmOdel', 'first_name'))
        indexes = self.migrator.database.get_indexes('indexmodel')
        self.assertEqual(len(indexes), 1)
        self.assertEqual(indexes[0].name, 'indexmodel_data')

    def test_add_column_indexed_table(self):
        # Ensure that columns can be added to tables that have indexes.
        field = CharField(default='')
        migrate(self.migrator.add_column('indexmodel', 'foo', field))

        db = self.migrator.database
        columns = db.get_columns('indexmodel')
        self.assertEqual(sorted(column.name for column in columns),
                         ['data', 'first_name', 'foo', 'id', 'last_name'])

        indexes = db.get_indexes('indexmodel')
        self.assertEqual(
            sorted((index.name, index.columns) for index in indexes),
            [('indexmodel_data', ['data']),
             ('indexmodel_first_name_last_name', ['first_name', 'last_name'])])

    def test_rename_column_to_table_name(self):
        db = self.migrator.database
        columns = lambda: sorted(col.name for col in db.get_columns('page'))
        indexes = lambda: sorted((idx.name, idx.columns)
                                 for idx in db.get_indexes('page'))

        orig_columns = columns()
        orig_indexes = indexes()

        # Rename "page"."name" to "page"."page".
        migrate(self.migrator.rename_column('page', 'name', 'page'))

        # Ensure that the index on "name" is preserved, and that the index on
        # the user_id foreign key is also preserved.
        self.assertEqual(columns(),  ['id', 'page', 'user_id'])
        self.assertEqual(indexes(), [
            ('page_name', ['page']),
            ('page_user_id', ['user_id'])])

        # Revert the operation and verify
        migrate(self.migrator.rename_column('page', 'page', 'name'))
        self.assertEqual(columns(),  orig_columns)
        self.assertEqual(indexes(), orig_indexes)

    def test_index_preservation(self):
        with count_queries() as qc:
            migrate(self.migrator.rename_column(
                'indexmodel',
                'first_name',
                'first'))

        queries = [log.msg for log in qc.get_queries()]
        self.assertEqual(queries, [
            # Get all the columns.
            ('PRAGMA table_info("indexmodel")', None),

            # Get the table definition.
            ('select name, sql from sqlite_master '
             'where type=? and LOWER(name)=?',
             ['table', 'indexmodel']),

            # Get the indexes and indexed columns for the table.
            ('SELECT name, sql FROM sqlite_master '
             'WHERE tbl_name = ? AND type = ? ORDER BY name',
             ('indexmodel', 'index')),
            ('PRAGMA index_list("indexmodel")', None),
            ('PRAGMA index_info("indexmodel_data")', None),
            ('PRAGMA index_info("indexmodel_first_name_last_name")', None),

            # Get foreign keys.
            ('PRAGMA foreign_key_list("indexmodel")', None),

            # Drop any temporary table, if it exists.
            ('DROP TABLE IF EXISTS "indexmodel__tmp__"', []),

            # Create a temporary table with the renamed column.
            ('CREATE TABLE "indexmodel__tmp__" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"first" VARCHAR(255) NOT NULL, '
             '"last_name" VARCHAR(255) NOT NULL, '
             '"data" INTEGER NOT NULL)', []),

            # Copy data from original table into temporary table.
            ('INSERT INTO "indexmodel__tmp__" '
             '("id", "first", "last_name", "data") '
             'SELECT "id", "first_name", "last_name", "data" '
             'FROM "indexmodel"', []),

            # Drop the original table.
            ('DROP TABLE "indexmodel"', []),

            # Rename the temporary table, replacing the original.
            ('ALTER TABLE "indexmodel__tmp__" RENAME TO "indexmodel"', []),

            # Re-create the indexes.
            ('CREATE UNIQUE INDEX "indexmodel_data" '
             'ON "indexmodel" ("data")', []),
            ('CREATE UNIQUE INDEX "indexmodel_first_name_last_name" '
             'ON "indexmodel" ("first", "last_name")', [])
        ])


@skip_if(lambda: psycopg2 is None)
class PostgresqlMigrationTestCase(BaseMigrationTestCase, PeeweeTestCase):
    database = pg_db
    migrator_class = PostgresqlMigrator


@skip_if(lambda: mysql is None)
class MySQLMigrationTestCase(BaseMigrationTestCase, PeeweeTestCase):
    database = mysql_db
    migrator_class = MySQLMigrator

    # MySQL does not raise an exception when adding a not null constraint
    # to a column that contains NULL values.
    _exception_add_not_null = False
