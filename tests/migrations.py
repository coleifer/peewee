import datetime
import os
from functools import partial

from peewee import *
from playhouse.migrate import *
from .base import BaseTestCase
from .base import IS_MYSQL
from .base import IS_POSTGRESQL
from .base import IS_SQLITE
from .base import ModelTestCase
from .base import TestModel
from .base import db
from .base import get_in_memory_db
from .base import requires_models
from .base import requires_postgresql
from .base import requires_sqlite
from .base import skip_if

try:
    from psycopg2cffi import compat
    compat.register()
except ImportError:
    pass


class Tag(TestModel):
    tag = CharField()

class Person(TestModel):
    first_name = CharField()
    last_name = CharField()
    dob = DateField(null=True)

class User(TestModel):
    id = CharField(primary_key=True, max_length=20)
    password = CharField(default='secret')

    class Meta:
        table_name = 'users'

class Page(TestModel):
    name = CharField(max_length=100, unique=True, null=True)
    user = ForeignKeyField(User, null=True, backref='pages')

class Session(TestModel):
    user = ForeignKeyField(User, unique=True, backref='sessions')
    updated_at = DateField(null=True)

class IndexModel(TestModel):
    first_name = CharField()
    last_name = CharField()
    data = IntegerField(unique=True)

    class Meta:
        indexes = (
            (('first_name', 'last_name'), True),
        )

class Category(TestModel):
    name = TextField()


class TestSchemaMigration(ModelTestCase):
    requires = [Person, Tag, User, Page, Session]

    # Each database behaves slightly differently.
    _exception_add_not_null = not IS_MYSQL

    _person_data = [
        ('Charlie', 'Leifer', None),
        ('Huey', 'Kitty', datetime.date(2011, 5, 1)),
        ('Mickey', 'Dog', datetime.date(2008, 6, 1)),
    ]

    def setUp(self):
        super(TestSchemaMigration, self).setUp()
        self.migrator = SchemaMigrator.from_database(self.database)

    def tearDown(self):
        try:
            super(TestSchemaMigration, self).tearDown()
        finally:
            self.database.close()

    @requires_postgresql
    def test_add_table_constraint(self):
        price = FloatField(default=0.)
        migrate(self.migrator.add_column('tag', 'price', price),
                self.migrator.add_constraint('tag', 'price_check',
                                             Check('price >= 0')))
        class Tag2(Model):
            tag = CharField()
            price = FloatField(default=0.)
            class Meta:
                database = self.database
                table_name = Tag._meta.table_name

        with self.database.atomic():
            self.assertRaises(IntegrityError, Tag2.create, tag='t1', price=-1)

        Tag2.create(tag='t1', price=1.0)
        t1_db = Tag2.get(Tag2.tag == 't1')
        self.assertEqual(t1_db.price, 1.0)

    @skip_if(IS_SQLITE)
    def test_add_unique(self):
        alt_id = IntegerField(default=0)
        migrate(
            self.migrator.add_column('tag', 'alt_id', alt_id),
            self.migrator.add_unique('tag', 'alt_id'))

        class Tag2(Model):
            tag = CharField()
            alt_id = IntegerField(default=0)
            class Meta:
                database = self.database
                table_name = Tag._meta.table_name

        Tag2.create(tag='t1', alt_id=1)
        with self.database.atomic():
            self.assertRaises(IntegrityError, Tag2.create, tag='t2', alt_id=1)

    @requires_postgresql
    def test_drop_table_constraint(self):
        price = FloatField(default=0.)
        migrate(
            self.migrator.add_column('tag', 'price', price),
            self.migrator.add_constraint('tag', 'price_check',
                                         Check('price >= 0')))

        class Tag2(Model):
            tag = CharField()
            price = FloatField(default=0.)
            class Meta:
                database = self.database
                table_name = Tag._meta.table_name

        with self.database.atomic():
            self.assertRaises(IntegrityError, Tag2.create, tag='t1', price=-1)

        migrate(self.migrator.drop_constraint('tag', 'price_check'))
        Tag2.create(tag='t1', price=-1)
        t1_db = Tag2.get(Tag2.tag == 't1')
        self.assertEqual(t1_db.price, -1.0)

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
        add_column = partial(self.migrator.add_column, 'tag')

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
                table_name = Tag._meta.table_name

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

    @skip_if(IS_MYSQL, 'mysql does not support CHECK()')
    def test_add_column_constraint(self):
        cf = CharField(null=True, constraints=[SQL('default \'foo\'')])
        ff = FloatField(default=0., constraints=[Check('val < 1.0')])
        t1 = Tag.create(tag='t1')
        migrate(
            self.migrator.add_column('tag', 'misc', cf),
            self.migrator.add_column('tag', 'val', ff))

        class NewTag(Model):
            tag = CharField()
            misc = CharField()
            val = FloatField()
            class Meta:
                database = self.database
                table_name = Tag._meta.table_name

        t1_db = NewTag.get(NewTag.tag == 't1')
        self.assertEqual(t1_db.misc, 'foo')
        self.assertEqual(t1_db.val, 0.)

        with self.database.atomic():
            self.assertRaises(IntegrityError, NewTag.create, tag='t2',
                              misc='bar', val=2.)

        NewTag.create(tag='t3', misc='baz', val=0.9)
        t3_db = NewTag.get(NewTag.tag == 't3')
        self.assertEqual(t3_db.misc, 'baz')
        self.assertEqual(t3_db.val, 0.9)

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
                table_name = Person._meta.table_name

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
            user = ForeignKeyField(User, null=True, backref='newpages')

            class Meta:
                database = self.database
                table_name = Page._meta.table_name

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

        with self.database.transaction():
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
        self.assertEqual(Tag_asdf._meta.table_name, 'tag_asdf')

        # Drop the new table just to be safe.
        Tag_asdf._schema.drop_all(True)

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

        self.database.execute_sql('drop table tag_asdf')

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

    def test_add_unique_column(self):
        uf = CharField(default='', unique=True)

        # Run the migration.
        migrate(self.migrator.add_column('tag', 'unique_field', uf))

        # Create a new tag model to represent the fields we added.
        class NewTag(Model):
            tag = CharField()
            unique_field = uf

            class Meta:
                database = self.database
                table_name = Tag._meta.table_name

        NewTag.create(tag='t1', unique_field='u1')
        NewTag.create(tag='t2', unique_field='u2')
        with self.database.atomic():
            self.assertRaises(IntegrityError, NewTag.create, tag='t3',
                              unique_field='u1')

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
                table_name = 'person_nugg'

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

        self.database.execute_sql('drop table person_nugg;')

    def test_add_foreign_key(self):
        if hasattr(Person, 'newtag_set'):
            delattr(Person, 'newtag_set')

        # Ensure no foreign keys are present at the beginning of the test.
        self.assertEqual(self.database.get_foreign_keys('tag'), [])

        field = ForeignKeyField(Person, field=Person.id, null=True)
        migrate(self.migrator.add_column('tag', 'person_id', field))

        class NewTag(Tag):
            person = field

            class Meta:
                table_name = 'tag'

        p = Person.create(first_name='First', last_name='Last')
        t1 = NewTag.create(tag='t1', person=p)
        t2 = NewTag.create(tag='t2')

        t1_db = NewTag.get(NewTag.tag == 't1')
        self.assertEqual(t1_db.person, p)

        t2_db = NewTag.get(NewTag.tag == 't2')
        self.assertIsNone(t2_db.person)

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

    @requires_postgresql
    @requires_models(Tag)
    def test_add_column_with_index_type(self):
        from playhouse.postgres_ext import BinaryJSONField
        self.reset_sql_history()
        field = BinaryJSONField(default=dict, index=True, null=True)
        migrate(self.migrator.add_column('tag', 'metadata', field))
        queries = [x.msg for x in self.history]
        self.assertEqual(queries, [
            ('ALTER TABLE "tag" ADD COLUMN "metadata" JSONB', []),
            ('CREATE INDEX "tag_metadata" ON "tag" USING GIN ("metadata")',
             []),
        ])

    def test_alter_column_type(self):
        # Convert varchar to text.
        field = TextField()
        migrate(self.migrator.alter_column_type('tag', 'tag', field))
        _, tag = self.database.get_columns('tag')
        # name, type, null?, primary-key?, table, default.
        data_type = 'TEXT' if IS_SQLITE else 'text'
        self.assertEqual(tag, ('tag', data_type, False, False, 'tag', None))

        # Convert date to datetime.
        field = DateTimeField()
        migrate(self.migrator.alter_column_type('person', 'dob', field))
        _, _, _, dob = self.database.get_columns('person')
        if IS_POSTGRESQL:
            self.assertTrue(dob.data_type.startswith('timestamp'))
        else:
            self.assertEqual(dob.data_type.lower(), 'datetime')

        # Convert text to integer.
        field = IntegerField()
        cast = '(tag::integer)' if IS_POSTGRESQL else None
        migrate(self.migrator.alter_column_type('tag', 'tag', field, cast))
        _, tag = self.database.get_columns('tag')
        if IS_SQLITE:
            data_type = 'INTEGER'
        elif IS_MYSQL:
            data_type = 'int'
        else:
            data_type = 'integer'
        self.assertEqual(tag, ('tag', data_type, False, False, 'tag', None))

    @requires_sqlite
    def test_valid_column_required(self):
        self.assertRaises(
            ValueError,
            migrate,
            self.migrator.drop_column('page', 'column_does_not_exist'))

        self.assertRaises(
            ValueError,
            migrate,
            self.migrator.rename_column('page', 'xx', 'yy'))

    @requires_sqlite
    @requires_models(IndexModel)
    def test_table_case_insensitive(self):
        migrate(self.migrator.drop_column('PaGe', 'name'))
        column_names = self.get_column_names('page')
        self.assertEqual(column_names, set(['id', 'user_id']))

        testing_field = CharField(default='xx')
        migrate(self.migrator.add_column('pAGE', 'testing', testing_field))
        column_names = self.get_column_names('page')
        self.assertEqual(column_names, set(['id', 'user_id', 'testing']))

        migrate(self.migrator.drop_column('indeX_mOdel', 'first_name'))
        indexes = self.migrator.database.get_indexes('index_model')
        self.assertEqual(len(indexes), 1)
        self.assertEqual(indexes[0].name, 'index_model_data')

    @requires_sqlite
    @requires_models(IndexModel)
    def test_add_column_indexed_table(self):
        # Ensure that columns can be added to tables that have indexes.
        field = CharField(default='')
        migrate(self.migrator.add_column('index_model', 'foo', field))

        db = self.migrator.database
        columns = db.get_columns('index_model')
        self.assertEqual(sorted(column.name for column in columns),
                         ['data', 'first_name', 'foo', 'id', 'last_name'])

        indexes = db.get_indexes('index_model')
        self.assertEqual(
            sorted((index.name, index.columns) for index in indexes),
            [('index_model_data', ['data']),
             ('index_model_first_name_last_name',
              ['first_name', 'last_name'])])

    @requires_sqlite
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

    @requires_sqlite
    @requires_models(Category)
    def test_add_fk_with_constraints(self):
        self.reset_sql_history()
        field = ForeignKeyField(Category, Category.id, backref='children',
                                null=True, on_delete='SET NULL')
        migrate(self.migrator.add_column(
            Category._meta.table_name,
            'parent_id',
            field))
        queries = [x.msg for x in self.history]
        self.assertEqual(queries, [
            ('ALTER TABLE "category" ADD COLUMN "parent_id" '
             'INTEGER REFERENCES "category" ("id") ON DELETE SET NULL', []),
            ('CREATE INDEX "category_parent_id" ON "category" ("parent_id")',
             []),
        ])

    @requires_sqlite
    @requires_models(IndexModel)
    def test_index_preservation(self):
        self.reset_sql_history()
        migrate(self.migrator.rename_column(
            'index_model',
            'first_name',
            'first'))

        queries = [x.msg for x in self.history]
        self.assertEqual(queries, [
            # Get all the columns.
            ('PRAGMA "main".table_info("index_model")', None),

            # Get the table definition.
            ('select name, sql from sqlite_master '
             'where type=? and LOWER(name)=?',
             ['table', 'index_model']),

            # Get the indexes and indexed columns for the table.
            ('SELECT name, sql FROM "main".sqlite_master '
             'WHERE tbl_name = ? AND type = ? ORDER BY name',
             ('index_model', 'index')),
            ('PRAGMA "main".index_list("index_model")', None),
            ('PRAGMA "main".index_info("index_model_data")', None),
            ('PRAGMA "main".index_info("index_model_first_name_last_name")',
             None),

            # Get foreign keys.
            ('PRAGMA "main".foreign_key_list("index_model")', None),

            # Drop any temporary table, if it exists.
            ('DROP TABLE IF EXISTS "index_model__tmp__"', []),

            # Create a temporary table with the renamed column.
            ('CREATE TABLE "index_model__tmp__" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"first" VARCHAR(255) NOT NULL, '
             '"last_name" VARCHAR(255) NOT NULL, '
             '"data" INTEGER NOT NULL)', []),

            # Copy data from original table into temporary table.
            ('INSERT INTO "index_model__tmp__" '
             '("id", "first", "last_name", "data") '
             'SELECT "id", "first_name", "last_name", "data" '
             'FROM "index_model"', []),

            # Drop the original table.
            ('DROP TABLE "index_model"', []),

            # Rename the temporary table, replacing the original.
            ('ALTER TABLE "index_model__tmp__" RENAME TO "index_model"', []),

            # Re-create the indexes.
            ('CREATE UNIQUE INDEX "index_model_data" '
             'ON "index_model" ("data")', []),
            ('CREATE UNIQUE INDEX "index_model_first_name_last_name" '
             'ON "index_model" ("first", "last_name")', [])
        ])

    @requires_sqlite
    @requires_models(User, Page)
    def test_modify_fk_constraint(self):
        self.reset_sql_history()
        new_fk = ForeignKeyField(User, User.id, null=True, on_delete='CASCADE')
        migrate(
            self.migrator.drop_column('page', 'user_id'),
            self.migrator.add_column('page', 'user_id', new_fk))

        queries = [x.msg for x in self.history]
        self.assertEqual(queries, [
            # Get all columns for table.
            ('PRAGMA "main".table_info("page")', None),

            # Get the SQL used to generate the table and indexes.
            ('select name, sql from sqlite_master '
             'where type=? and LOWER(name)=?', ['table', 'page']),
            ('SELECT name, sql FROM "main".sqlite_master '
             'WHERE tbl_name = ? AND type = ? ORDER BY name',
             ('page', 'index')),

            # Get the indexes and indexed columns for the table.
            ('PRAGMA "main".index_list("page")', None),
            ('PRAGMA "main".index_info("page_name")', None),
            ('PRAGMA "main".index_info("page_user_id")', None),
            ('PRAGMA "main".foreign_key_list("page")', None),

            # Clear out a temp table and create it w/o the user_id FK.
            ('DROP TABLE IF EXISTS "page__tmp__"', []),
            ('CREATE TABLE "page__tmp__" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, "name" VARCHAR(100))', []),

            # Copy data into the temp table, drop the original and rename
            # the temp -> original. Recreate index(es).
            ('INSERT INTO "page__tmp__" ("id", "name") '
             'SELECT "id", "name" FROM "page"', []),
            ('DROP TABLE "page"', []),
            ('ALTER TABLE "page__tmp__" RENAME TO "page"', []),
            ('CREATE UNIQUE INDEX "page_name" ON "page" ("name")', []),

            # Add new foreign-key field with appropriate constraint.
            ('ALTER TABLE "page" ADD COLUMN "user_id" VARCHAR(20) '
             'REFERENCES "users" ("id") ON DELETE CASCADE', []),
            ('CREATE INDEX "page_user_id" ON "page" ("user_id")', []),
        ])

        self.database.pragma('foreign_keys', 1)
        huey = User.create(id='huey')
        huey_page = Page.create(user=huey, name='huey page')
        self.assertEqual(Page.select().count(), 1)

        # Deleting the user will cascade to the associated page.
        User.delete().where(User.id == 'huey').execute()
        self.assertEqual(Page.select().count(), 0)

    def test_make_index_name(self):
        self.assertEqual(make_index_name('table', ['column']), 'table_column')

    def test_make_index_name_long(self):
        columns = [
            'very_long_column_name_number_1',
            'very_long_column_name_number_2',
            'very_long_column_name_number_3',
            'very_long_column_name_number_4'
        ]
        name = make_index_name('very_long_table_name', columns)
        self.assertEqual(len(name), 64)


class BadNames(TestModel):
    primary_data = TextField()
    foreign_data = TextField()
    data = TextField()

    class Meta:
        constraints = [
            SQL('CONSTRAINT const1 UNIQUE (primary_data)'),
            SQL('CONSTRAINT const2 UNIQUE (foreign_data)')]


class TestSqliteColumnNameRegression(ModelTestCase):
    database = get_in_memory_db()
    requires = [BadNames]

    def test_sqlite_column_name_regression(self):
        BadNames.create(primary_data='pd', foreign_data='fd', data='d')

        migrator = SchemaMigrator.from_database(self.database)
        new_data = TextField(default='foo')
        migrate(migrator.add_column('bad_names', 'new_data', new_data),
                migrator.drop_column('bad_names', 'data'))

        columns = self.database.get_columns('bad_names')
        column_names = [column.name for column in columns]
        self.assertEqual(column_names, ['id', 'primary_data', 'foreign_data',
                                        'new_data'])

        BNT = Table('bad_names', ('id', 'primary_data', 'foreign_data',
                                  'new_data')).bind(self.database)
        self.assertEqual([row for row in BNT.select()], [{
            'id': 1,
            'primary_data': 'pd',
            'foreign_data': 'fd',
            'new_data': 'foo'}])

        # Verify constraints were carried over.
        data = {'primary_data': 'pd', 'foreign_data': 'xx', 'new_data': 'd'}
        self.assertRaises(IntegrityError, BNT.insert(data).execute)

        data.update(primary_data='px', foreign_data='fd')
        self.assertRaises(IntegrityError, BNT.insert(data).execute)

        data.update(foreign_data='fx')
        self.assertTrue(BNT.insert(data).execute())
