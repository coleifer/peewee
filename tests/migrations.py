import datetime
import io
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from functools import partial

from peewee import *
from playhouse.migrate import *
from playhouse.migrations import MigrationError
from playhouse.migrations import Runner
from playhouse.migrations import main as migrations_cli
from .base import BaseTestCase
from .base import IS_CRDB
from .base import IS_MYSQL
from .base import IS_POSTGRESQL
from .base import IS_PSYCOPG3
from .base import IS_SQLITE
from .base import IS_SQLITE_25
from .base import IS_SQLITE_35
from .base import IS_SQLITE_53
from .base import ModelTestCase
from .base import TestModel
from .base import db
from .base import get_in_memory_db
from .base import requires_models
from .base import requires_pglike
from .base import requires_postgresql
from .base import requires_sqlite
from .base import skip_if
from .base import skip_unless

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

class FKPage(TestModel):
    user = ForeignKeyField(User, null=True, backref='fk_pages',
                           on_delete='CASCADE', on_update='CASCADE')
    name = CharField(null=True)

    class Meta:
        table_name = 'fk_page'

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

    @skip_unless(IS_POSTGRESQL or IS_CRDB or IS_SQLITE_53,
                 'requires pg-like or sqlite 3.53+')
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

    @skip_if(IS_SQLITE, 'sqlite cannot ALTER TABLE ADD CONSTRAINT UNIQUE')
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

    @skip_unless(IS_POSTGRESQL or IS_CRDB or IS_SQLITE_53,
                 'requires pg-like or sqlite 3.53+')
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

    def test_add_column_not_null_explicit(self):
        # allow_not_null emits the column NOT NULL directly, no default
        # needed. Existing rows are the caller's responsibility.
        migrate(self.migrator.add_column('tag', 'points', IntegerField(),
                                         allow_not_null=True))
        column = dict((c.name, c)
                      for c in self.database.get_columns('tag'))['points']
        self.assertFalse(column.null)

        # Without the flag the default requirement stands.
        self.assertRaises(ValueError, migrate,
                          self.migrator.add_column('tag', 'p2',
                                                   IntegerField()))

    def test_add_column_not_null_default(self):
        # A server-side default makes the one-statement NOT NULL add valid
        # even with rows present: the database backfills.
        Tag.create(tag='t1')
        field = IntegerField(constraints=[SQL('DEFAULT 0')])
        with self.assertQueryCount(1):
            migrate(self.migrator.add_column('tag', 'karma', field,
                                             allow_not_null=True))

        column = dict((c.name, c)
                      for c in self.database.get_columns('tag'))['karma']
        self.assertFalse(column.null)
        curs = self.database.execute_sql('SELECT karma FROM tag')
        self.assertEqual(curs.fetchone()[0], 0)
        self.database.execute_sql("INSERT INTO tag (tag) VALUES ('t2')")
        curs = self.database.execute_sql(
            "SELECT karma FROM tag WHERE tag = 't2'")
        self.assertEqual(curs.fetchone()[0], 0)

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

    def test_drop_column(self, legacy=False):
        kw = {'legacy': legacy} if IS_SQLITE else {}
        self._create_people()
        migrate(
            self.migrator.drop_column('person', 'last_name', **kw),
            self.migrator.drop_column('person', 'dob', **kw))

        column_names = self.get_column_names('person')
        self.assertEqual(column_names, set(['id', 'first_name']))

        User.create(id='charlie', password='12345')
        User.create(id='huey', password='meow')
        migrate(self.migrator.drop_column('users', 'password', **kw))

        column_names = self.get_column_names('users')
        self.assertEqual(column_names, set(['id']))
        data = [row for row in User.select(User.id).order_by(User.id).tuples()]
        self.assertEqual(data, [
            ('charlie',),
            ('huey',),])

    @skip_unless(IS_SQLITE_35, 'Requires sqlite 3.35 or newer')
    def test_drop_column_sqlite_legacy(self):
        self.test_drop_column(legacy=True)

    def test_rename_column(self, legacy=False):
        kw = {'legacy': legacy} if IS_SQLITE else {}
        self._create_people()
        migrate(
            self.migrator.rename_column('person', 'first_name', 'first', **kw),
            self.migrator.rename_column('person', 'last_name', 'last', **kw))

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

    @skip_unless(IS_SQLITE_25, 'Requires sqlite 3.25 or newer')
    def test_rename_column_sqlite_legacy(self):
        self.test_rename_column(legacy=True)

    def test_rename_gh380(self, legacy=False):
        kw = {'legacy': legacy} if IS_SQLITE else {}
        u1 = User.create(id='charlie')
        u2 = User.create(id='huey')
        p1 = Page.create(name='p1-1', user=u1)
        p2 = Page.create(name='p2-1', user=u1)
        p3 = Page.create(name='p3-2', user=u2)

        migrate(self.migrator.rename_column('page', 'name', 'title', **kw))

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

    @skip_unless(IS_SQLITE_25, 'Requires sqlite 3.25 or newer')
    def test_rename_gh380_sqlite_legacy(self):
        self.test_rename_gh380(legacy=True)

    @skip_if(IS_PSYCOPG3, 'Psycopg3 chokes on the default value.')
    def test_add_default_drop_default(self):
        with self.database.transaction():
            migrate(self.migrator.add_column_default('person', 'first_name',
                                                     default='x'))

        p = Person.create(last_name='Last')
        p_db = Person.get(Person.last_name == 'Last')
        self.assertEqual(p_db.first_name, 'x')

        with self.database.transaction():
            migrate(self.migrator.drop_column_default('person', 'first_name'))

        if IS_MYSQL:
            # MySQL, even though the column is NOT NULL, does not seem to be
            # enforcing the constraint(?).
            Person.create(last_name='Last2')
            p_db = Person.get(Person.last_name == 'Last2')
            self.assertEqual(p_db.first_name, '')
        else:
            with self.assertRaises(IntegrityError):
                with self.database.transaction():
                    Person.create(last_name='Last2')

    def test_add_not_null(self, legacy=False):
        kw = {'legacy': legacy} if IS_SQLITE else {}
        self._create_people()

        def addNotNull():
            with self.database.transaction():
                migrate(self.migrator.add_not_null('person', 'dob', **kw))

        # We cannot make the `dob` field not null because there is currently
        # a null value there.
        if self._exception_add_not_null:
            with self.assertRaisesCtx((IntegrityError, InternalError)):
                addNotNull()

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

    @skip_unless(IS_SQLITE_53, 'Requires sqlite 3.53 or newer')
    def test_add_not_null_sqlite_legacy(self):
        self.test_add_not_null(legacy=True)

    def test_drop_not_null(self, legacy=False):
        kw = {'legacy': legacy} if IS_SQLITE else {}
        self._create_people()
        migrate(
            self.migrator.drop_not_null('person', 'first_name', **kw),
            self.migrator.drop_not_null('person', 'last_name', **kw))

        p = Person.create(first_name=None, last_name=None)
        query = (Person
                 .select()
                 .where(
                     Person.first_name.is_null(True) &
                     Person.last_name.is_null(True)))
        self.assertEqual(query.count(), 1)

    @skip_unless(IS_SQLITE_53, 'Requires sqlite 3.53 or newer')
    def test_drop_not_null_sqlite_legacy(self):
        self.test_drop_not_null(legacy=True)

    def test_modify_not_null_foreign_key(self, legacy=False):
        kw = {'legacy': legacy} if IS_SQLITE else {}
        user = User.create(id='charlie')
        Page.create(name='null user')
        Page.create(name='charlie', user=user)

        def addNotNull():
            with self.database.transaction():
                migrate(self.migrator.add_not_null('page', 'user_id', **kw))

        if self._exception_add_not_null:
            with self.assertRaisesCtx((IntegrityError, InternalError)):
                addNotNull()

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
            migrate(self.migrator.drop_not_null('page', 'user_id', **kw))

        self.assertEqual(Page.select().where(Page.user.is_null()).count(), 0)
        Page.create(name='succeeds', user=None)
        self.assertEqual(Page.select().where(Page.user.is_null()).count(), 1)

    @skip_unless(IS_SQLITE_53, 'Requires sqlite 3.53 or newer')
    def test_modify_not_null_foreign_key_sqlite_legacy(self):
        self.test_modify_not_null_foreign_key(legacy=True)

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

    def test_drop_table(self):
        Tag.create(tag='t1')
        migrate(self.migrator.drop_table('tag'))
        self.assertFalse('tag' in self.database.get_tables())
        # Missing table is fine when safe.
        migrate(self.migrator.drop_table('tag', safe=True))

    @requires_pglike
    def test_drop_table_cascade(self):
        self.database.execute_sql('CREATE VIEW tag_v AS SELECT id FROM tag')
        self.assertTrue('tag_v' in [v.name for v in self.database.get_views()])

        migrate(self.migrator.drop_table('tag', cascade=True))
        self.assertFalse('tag' in self.database.get_tables())
        self.assertFalse('tag_v' in [v.name for v in
                                     self.database.get_views()])

    @skip_unless(IS_SQLITE, 'sqlite-specific')
    def test_drop_table_cascade_sqlite(self):
        self.assertRaises(NotImplementedError, migrate,
                          self.migrator.drop_table('tag', cascade=True))

    @requires_sqlite
    def test_drop_table_schema(self):
        self.database.execute_sql("ATTACH ':memory:' AS aux")
        self.database.execute_sql('CREATE TABLE aux.dt (id INTEGER)')
        migrate(self.migrator.drop_table('dt', schema='aux'))
        self.assertFalse('dt' in self.database.get_tables('aux'))

    def test_add_index(self):
        # Create a unique index on first and last names.
        columns = ('first_name', 'last_name')
        migrate(self.migrator.add_index('person', columns, True))

        Person.create(first_name='first', last_name='last')
        with self.database.transaction():
            with self.assertRaisesCtx((IntegrityError, InternalError)):
                Person.create(first_name='first', last_name='last')

    @skip_if(IS_MYSQL, 'requires partial-index support')
    def test_add_index_where(self):
        # Unique only within the predicate.
        tbl = Table('person')
        migrate(self.migrator.add_index(
            'person', ('last_name',), True,
            where=(tbl.c.first_name == 'live')))

        Person.create(first_name='live', last_name='x')
        Person.create(first_name='draft', last_name='x')
        with self.database.transaction():
            with self.assertRaisesCtx((IntegrityError, InternalError)):
                Person.create(first_name='live', last_name='x')

    @requires_postgresql
    def test_add_index_nulls_distinct(self):
        if self.database.server_version < 150000:
            self.skipTest('requires postgres 15')
        migrate(self.migrator.add_index('person', ('dob',), True,
                                        nulls_distinct=False))
        Person.create(first_name='a', last_name='a')
        with self.database.transaction():
            with self.assertRaisesCtx((IntegrityError, InternalError)):
                Person.create(first_name='b', last_name='b')

    def test_sql_operation(self):
        Person.create(first_name='f', last_name='l')
        migrate(
            self.migrator.add_column('person', 'karma',
                                     IntegerField(null=True)),
            self.migrator.sql('UPDATE person SET karma = %s'
                              % self.database.param, (90,)),
            self.migrator.add_not_null('person', 'karma'))

        curs = self.database.execute_sql('SELECT karma FROM person')
        self.assertEqual([karma for karma, in curs.fetchall()], [90])
        karma, = [c for c in self.database.get_columns('person')
                  if c.name == 'karma']
        self.assertFalse(karma.null)

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
        kw = {'legacy': True} if IS_SQLITE else {}
        migrate(self.migrator.drop_column('page', 'user_id', **kw))
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

    @skip_unless(IS_MYSQL, 'FK ON DELETE/UPDATE reconstruction is MySQL-only')
    @requires_models(FKPage)
    def test_fk_actions_preserved(self):
        def fk():
            fks = self.database.get_foreign_keys('fk_page')
            self.assertEqual(len(fks), 1)
            return fks[0]

        self.assertEqual((fk().on_delete, fk().on_update),
                         ('CASCADE', 'CASCADE'))

        migrate(self.migrator.add_not_null('fk_page', 'user_id'))
        self.assertEqual((fk().on_delete, fk().on_update),
                         ('CASCADE', 'CASCADE'))

        migrate(self.migrator.rename_column('fk_page', 'user_id', 'owner_id'))
        renamed = fk()
        self.assertEqual(renamed.column, 'owner_id')
        self.assertEqual((renamed.on_delete, renamed.on_update),
                         ('CASCADE', 'CASCADE'))

    @requires_pglike
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

    @skip_if(IS_CRDB, 'crdb is still finnicky about changing types.')
    def test_alter_column_type(self):
        # Convert varchar to text.
        field = TextField()
        migrate(self.migrator.alter_column_type('tag', 'tag', field))
        _, tag = self.database.get_columns('tag')
        # name, type, null?, primary-key?, table, default.
        data_type = 'TEXT' if IS_SQLITE else 'text'
        self.assertEqual(tag, ('tag', data_type, False, False, 'tag', None,
                               data_type, False))

        # Convert date to datetime.
        field = DateTimeField()
        migrate(self.migrator.alter_column_type('person', 'dob', field))
        _, _, _, dob = self.database.get_columns('person')
        if IS_POSTGRESQL or IS_CRDB:
            self.assertTrue(dob.data_type.startswith('timestamp'))
        else:
            self.assertEqual(dob.data_type.lower(), 'datetime')

        # Convert text to integer.
        field = IntegerField()
        cast = '(tag::integer)' if IS_POSTGRESQL or IS_CRDB else None
        migrate(self.migrator.alter_column_type('tag', 'tag', field, cast))
        _, tag = self.database.get_columns('tag')
        if IS_SQLITE:
            d = 'INTEGER'
        elif IS_MYSQL:
            d = 'int'
        else:
            d = 'integer'
        self.assertEqual(tag[:6], ('tag', d, False, False, 'tag', None))

    @requires_sqlite
    def test_valid_column_required(self):
        self.assertRaises(
            (OperationalError, ValueError),
            migrate,
            self.migrator.drop_column('page', 'column_does_not_exist'))

        self.assertRaises(
            (OperationalError, ValueError),
            migrate,
            self.migrator.rename_column('page', 'xx', 'yy'))

    @requires_sqlite
    @requires_models(IndexModel)
    def test_table_case_insensitive(self):
        migrate(self.migrator.drop_column('PaGe', 'name', legacy=True))
        column_names = self.get_column_names('page')
        self.assertEqual(column_names, set(['id', 'user_id']))

        testing_field = CharField(default='xx')
        migrate(self.migrator.add_column('pAGE', 'testing', testing_field))
        column_names = self.get_column_names('page')
        self.assertEqual(column_names, set(['id', 'user_id', 'testing']))

        migrate(self.migrator.drop_column('indeX_mOdel', 'first_name',
                                          legacy=True))
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
    def test_rebuild_preserves_bare_unique(self):
        db = self.database
        db.execute_sql('DROP TABLE IF EXISTS "uc"')
        db.execute_sql('CREATE TABLE "uc" ("id" INTEGER PRIMARY KEY, '
                       '"a" TEXT, "b" TEXT, UNIQUE (a, b))')
        try:
            # Without the 'unique ' constraint term, the rebuild treats the
            # bare UNIQUE (a, b) as a column and raises OperationalError.
            migrate(self.migrator.add_not_null('uc', 'a', legacy=True))
            row = db.execute_sql('SELECT sql FROM sqlite_master '
                                 "WHERE type='table' AND name='uc'").fetchone()
            self.assertIn('UNIQUE', row[0].upper())
        finally:
            db.execute_sql('DROP TABLE IF EXISTS "uc"')

    @requires_sqlite
    def test_rebuild_substring_table_name(self):
        db = self.database
        db.execute_sql('DROP TABLE IF EXISTS "ab"')
        db.execute_sql('CREATE TABLE "ab" ("id" INTEGER PRIMARY KEY, '
                       '"x" INTEGER)')
        try:
            db.execute_sql('INSERT INTO "ab" ("id", "x") VALUES (1, 10)')
            # 'ab' is a substring of "CREATE TABLE". An unanchored rename
            # rewrites the keyword and produces a syntax error.
            migrate(self.migrator.add_not_null('ab', 'x', legacy=True))
            self.assertEqual(
                db.execute_sql('SELECT "x" FROM "ab"').fetchall(), [(10,)])
        finally:
            db.execute_sql('DROP TABLE IF EXISTS "ab"')

    @requires_sqlite
    @requires_models(IndexModel)
    def test_index_preservation(self):
        self.reset_sql_history()
        migrate(self.migrator.rename_column(
            'index_model',
            'first_name',
            'first',
            legacy=True))

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
            self.migrator.drop_column('page', 'user_id', legacy=True),
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
            #('PRAGMA "main".foreign_key_list("page")', None),

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

    def test_from_database_proxy(self):
        proxy = DatabaseProxy()
        proxy.initialize(self.database)
        migrator = SchemaMigrator.from_database(proxy)
        self.assertTrue(type(migrator) is type(self.migrator))
        self.assertTrue(migrator.database is self.database)
        self.assertRaises(ValueError, SchemaMigrator.from_database,
                          DatabaseProxy())

    def test_migration_context(self):
        with self.migrator.migration_context():
            self.assertEqual(self.database.in_transaction(),
                             self.migrator.transactional_ddl)
        self.assertFalse(self.database.in_transaction())
        with self.migrator.migration_context(atomic=False):
            self.assertFalse(self.database.in_transaction())

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


class HasChecks(TestModel):
    key = TextField()
    value = IntegerField()
    class Meta:
        constraints = [
            SQL("CHECK (key != '')"),
            SQL('CHECK (value > 0)')]


class TestSqliteColumnNameRegression(ModelTestCase):
    database = get_in_memory_db()
    requires = [BadNames, HasChecks]

    def test_sqlite_check_constraints(self):
        HasChecks.create(key='k1', value=1)

        migrator = SchemaMigrator.from_database(self.database)
        extra = TextField(default='')
        migrate(migrator.add_column('has_checks', 'extra', extra))

        columns = self.database.get_columns('has_checks')
        self.assertEqual([c.name for c in columns],
                         ['id', 'key', 'value', 'extra'])

        HC = Table('has_checks', ('id', 'key', 'value', 'extra'))
        HC = HC.bind(self.database)

        # Sanity-check: ensure we can create a new row.
        data = {'key': 'k2', 'value': 2, 'extra': 'x2'}
        self.assertTrue(HC.insert(data).execute())

        # Check constraints preserved.
        data = {'key': 'k0', 'value': 0, 'extra': 'x0'}
        self.assertRaises(IntegrityError, HC.insert(data).execute)

        data = {'key': '', 'value': 3, 'extra': 'x3'}
        self.assertRaises(IntegrityError, HC.insert(data).execute)

    def test_sqlite_column_name_constraint_regression(self):
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


class FKMA(TestModel):
    name = TextField()

class FKMB(TestModel):
    name = TextField()
    fkma = ForeignKeyField(FKMA, backref='fkmb_set', null=True)


class TestFKMigrationRegression(ModelTestCase):
    requires = [FKMA, FKMB]

    def test_fk_migration(self):
        migrator = SchemaMigrator.from_database(self.database)
        kw = {'legacy': True} if IS_SQLITE else {}
        migrate(migrator.drop_column(
            FKMB._meta.table_name,
            FKMB.fkma.column_name, **kw))

        migrate(migrator.add_column(
            FKMB._meta.table_name,
            FKMB.fkma.column_name,
            FKMB.fkma))

        fa = FKMA.create(name='fa')
        FKMB.create(name='fb', fkma=fa)
        obj = FKMB.select().first()
        self.assertEqual(obj.name, 'fb')


# Migration runner (playhouse.migrations).

def add_column_mig(column):
    return (
        "from peewee import *\n"
        "def up(migrator, db):\n"
        "    migrator.migrate(\n"
        "        migrator.add_column('person', %r, TextField(null=True)))\n"
        "def down(migrator, db):\n"
        "    migrator.migrate(migrator.drop_column('person', %r))\n"
        % (column, column))

RUNNER_MIG_NO_DOWN = (
    "from peewee import *\n"
    "def up(migrator, db):\n"
    "    migrator.add_column('person', 'nickname', "
    "TextField(null=True)).run()\n")

RUNNER_MIG_BAD = (
    "from peewee import *\n"
    "def up(migrator, db):\n"
    "    migrator.add_column('person', 'notes', TextField(null=True)).run()\n"
    "    db.execute_sql('select bad_column from person')\n")

RUNNER_MIG_TABLE = (
    "from peewee import *\n"
    "def up(migrator, db):\n"
    "    class Widget(Model):\n"
    "        name = CharField(default='')\n"
    "        class Meta:\n"
    "            database = db\n"
    "            table_name = 'runner_widget'\n"
    "    db.create_tables([Widget])\n"
    "def down(migrator, db):\n"
    "    db.execute_sql('drop table runner_widget')\n")


class TestMigrationRunner(ModelTestCase):
    requires = [Person]

    def setUp(self):
        super(TestMigrationRunner, self).setUp()
        self.dir = tempfile.mkdtemp()
        self.runner = Runner(self.database, self.dir)

    def tearDown(self):
        try:
            shutil.rmtree(self.dir, ignore_errors=True)
            self.database.drop_tables([self.runner.History], safe=True)
            self.database.execute_sql('DROP TABLE IF EXISTS runner_widget')
        finally:
            super(TestMigrationRunner, self).tearDown()
            self.database.close()

    def write(self, filename, body):
        with open(os.path.join(self.dir, filename), 'w') as fh:
            fh.write(body)

    def write_chain(self):
        self.write('0001_notes.py', add_column_mig('notes'))
        self.write('0002_email.py', add_column_mig('email'))
        self.write('0003_phone.py', add_column_mig('phone'))

    def columns(self):
        return set(c.name for c in self.database.get_columns('person'))

    def applied(self):
        return [m.name for m in self.runner.status() if m.applied]

    def pending(self):
        return [m.name for m in self.runner.status() if not m.applied]

    def test_up_down_status(self):
        self.write('0001_notes.py', add_column_mig('notes'))
        self.write('0002_email.py', add_column_mig('email'))

        self.assertEqual(self.pending(), ['0001_notes', '0002_email'])
        self.assertEqual(self.runner.up(), ['0001_notes', '0002_email'])
        self.assertIn('notes', self.columns())
        self.assertIn('email', self.columns())
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.runner.up(), [])  # Idempotent.

        # One step at a time.
        self.assertEqual(self.runner.down(), ['0002_email'])
        self.assertNotIn('email', self.columns())
        self.assertIn('notes', self.columns())
        self.assertEqual(self.runner.down(), ['0001_notes'])
        self.assertEqual(self.runner.down(), [])

    def test_numeric_ordering(self):
        # Lexicographic filename sort would run 10 before 2.
        self.write('2_notes.py', add_column_mig('notes'))
        self.write('10_email.py', add_column_mig('email'))
        self.assertEqual(self.runner.up(), ['2_notes', '10_email'])

    def test_create_table_inline_model(self):
        self.write('0001_widget.py', RUNNER_MIG_TABLE)
        self.assertEqual(self.runner.up(), ['0001_widget'])
        self.assertIn('runner_widget', self.database.get_tables())
        self.assertEqual(self.runner.down(), ['0001_widget'])
        self.assertNotIn('runner_widget', self.database.get_tables())

    def test_down_requires_down(self):
        self.write('0001_nickname.py', RUNNER_MIG_NO_DOWN)
        self.assertEqual(self.runner.up(), ['0001_nickname'])
        self.assertRaises(MigrationError, self.runner.down)

    def test_down_plan_requires_down(self):
        self.write('0001_nickname.py', RUNNER_MIG_NO_DOWN)
        self.write('0002_email.py', add_column_mig('email'))
        self.write('0003_phone.py', add_column_mig('phone'))
        self.runner.up()
        self.assertRaises(MigrationError, self.runner.down, '0001_nickname')
        # Verified before reverting any: everything is still applied.
        self.assertEqual(self.applied(),
                         ['0001_nickname', '0002_email', '0003_phone'])
        self.assertIn('email', self.columns())
        self.assertIn('phone', self.columns())

    def test_down_missing_file(self):
        self.write('0001_notes.py', add_column_mig('notes'))
        self.runner.up()
        os.remove(os.path.join(self.dir, '0001_notes.py'))
        self.assertRaises(MigrationError, self.runner.down)

    def test_status_missing_file(self):
        self.write_chain()
        self.runner.up('0002_email')
        os.remove(os.path.join(self.dir, '0001_notes.py'))
        # Applied rows whose files are gone keep their numeric position.
        self.assertEqual([m.name for m in self.runner.status()],
                         ['0001_notes', '0002_email', '0003_phone'])
        self.assertEqual(self.pending(), ['0003_phone'])

    def test_status_orphan_ordering(self):
        self.write('2_notes.py', add_column_mig('notes'))
        self.write('10_email.py', add_column_mig('email'))
        self.write('30_phone.py', add_column_mig('phone'))
        self.runner.up()
        os.remove(os.path.join(self.dir, '2_notes.py'))
        os.remove(os.path.join(self.dir, '10_email.py'))
        # Orphaned rows sort numerically, like everything else.
        self.assertEqual([m.name for m in self.runner.status()],
                         ['2_notes', '10_email', '30_phone'])

    def test_fake(self):
        self.write('0001_notes.py', add_column_mig('notes'))
        self.write('0002_email.py', add_column_mig('email'))
        self.assertEqual(self.runner.fake(), ['0001_notes', '0002_email'])
        self.assertEqual(self.runner.up(), [])
        self.assertNotIn('notes', self.columns())
        self.assertEqual(self.runner.fake(), [])
        self.assertRaises(MigrationError, self.runner.fake, '0009_nope')

    def test_fake_target(self):
        self.write_chain()
        # Fakes everything pending through the target, like up().
        self.assertEqual(self.runner.fake('0002_email'),
                         ['0001_notes', '0002_email'])
        self.assertEqual(self.runner.up(), ['0003_phone'])
        self.assertNotIn('notes', self.columns())
        self.assertNotIn('email', self.columns())
        self.assertIn('phone', self.columns())

    def test_create_scaffold(self):
        path = self.runner.create('add user email!')
        self.assertEqual(os.path.basename(path), '0001_add_user_email.py')
        path = self.runner.create('another')
        self.assertEqual(os.path.basename(path), '0002_another.py')
        # Scaffolds apply cleanly (up() is a no-op).
        self.assertEqual(self.runner.up(),
                         ['0001_add_user_email', '0002_another'])

    def test_failed_migration(self):
        self.write('0001_bad.py', RUNNER_MIG_BAD)
        self.assertRaises(DatabaseError, self.runner.up)
        if self.runner.migrator.transactional_ddl:
            self.assertNotIn('notes', self.columns())  # Rolled back.
        else:
            # Partial DDL persists, but the history row was never written.
            self.assertIn('notes', self.columns())
        self.assertEqual(self.applied(), [])

    def test_atomic_optout(self):
        self.write('0001_notes.py',
                   'atomic = False\n' + add_column_mig('notes'))
        self.assertEqual(self.runner.up(), ['0001_notes'])
        self.assertIn('notes', self.columns())

    @requires_sqlite
    def test_sqlite_rewrite_cascade_regression(self):
        # A table-rewrite migration with foreign_keys enforcement enabled
        # must not cascade-delete child rows, and must restore the pragma.
        db = get_in_memory_db(pragmas={'foreign_keys': 1})
        db.execute_sql('CREATE TABLE parent (id INTEGER NOT NULL PRIMARY '
                       'KEY, name TEXT, extra INTEGER DEFAULT 0)')
        db.execute_sql('CREATE TABLE child (id INTEGER NOT NULL PRIMARY '
                       'KEY, parent_id INTEGER NOT NULL REFERENCES parent '
                       '(id) ON DELETE CASCADE)')
        db.execute_sql('INSERT INTO parent (name) VALUES (?)', ('p1',))
        db.execute_sql('INSERT INTO child (parent_id) VALUES (?)', (1,))

        self.write('0001_drop_extra.py', (
            "def up(migrator, db):\n"
            "    migrator.drop_column('parent', 'extra', legacy=True)"
            ".run()\n"))
        runner = Runner(db, self.dir)
        self.assertEqual(runner.up(), ['0001_drop_extra'])
        curs = db.execute_sql('SELECT COUNT(*) FROM child')
        self.assertEqual(curs.fetchone()[0], 1)
        self.assertEqual(db.pragma('foreign_keys'), 1)

    def test_up_target(self):
        self.write_chain()
        self.assertEqual(self.runner.up('0002_email'),
                         ['0001_notes', '0002_email'])
        self.assertIn('email', self.columns())
        self.assertNotIn('phone', self.columns())
        self.assertEqual(self.runner.up(), ['0003_phone'])
        self.assertRaises(MigrationError, self.runner.up, '0009_nope')

    def test_down_series(self):
        self.write_chain()
        self.runner.up()
        # Reverts newest back through the target, inclusive.
        self.assertEqual(self.runner.down('0002_email'),
                         ['0003_phone', '0002_email'])
        self.assertIn('notes', self.columns())
        self.assertNotIn('email', self.columns())
        self.assertNotIn('phone', self.columns())
        self.assertEqual(self.runner.down('0001_notes'), ['0001_notes'])
        self.assertEqual(self.applied(), [])

    def test_down_target_validation(self):
        self.write_chain()
        self.runner.up('0002_email')
        # Not applied and unknown are both errors.
        self.assertRaises(MigrationError, self.runner.down, '0003_phone')
        self.assertRaises(MigrationError, self.runner.down, '0009_nope')

        # A missing file anywhere in the plan aborts before reverting.
        os.remove(os.path.join(self.dir, '0002_email.py'))
        self.assertRaises(MigrationError, self.runner.down, '0001_notes')
        self.assertIn('email', self.columns())  # Nothing reverted.

    def test_run_convenience(self):
        from playhouse.migrations import run
        self.write('0001_notes.py', add_column_mig('notes'))
        self.assertEqual(run(self.database, self.dir), ['0001_notes'])
        self.assertEqual(run(self.database, self.dir), [])
        self.assertIn('notes', self.columns())

    def test_runner_proxy(self):
        proxy = DatabaseProxy()
        proxy.initialize(self.database)
        self.write('0001_notes.py', add_column_mig('notes'))
        runner = Runner(proxy, self.dir)
        self.assertEqual(runner.up(), ['0001_notes'])
        self.assertIn('notes', self.columns())
        self.assertEqual(runner.down(), ['0001_notes'])
        self.assertNotIn('notes', self.columns())


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = migrations_cli(list(args))
    return rc, out.getvalue(), err.getvalue()


class TestMigrationRunnerCLI(BaseTestCase):
    def setUp(self):
        super(TestMigrationRunnerCLI, self).setUp()
        self.dir = tempfile.mkdtemp()
        self.migdir = os.path.join(self.dir, 'migrations')
        self.url = 'sqlite:///%s' % os.path.join(self.dir, 'cli.db')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        super(TestMigrationRunnerCLI, self).tearDown()

    def test_cli_database_spec(self):
        dbfile = os.path.join(self.dir, 'spec.db')
        with open(dbfile, 'wb'):
            pass
        rc, out, err = run_cli(dbfile, 'status', '-d', self.migdir)
        self.assertEqual(rc, 0)

        rc, out, err = run_cli('nope.db', 'status', '-d', self.migdir)
        self.assertEqual(rc, 2)
        self.assertIn('error:', err)

    def test_cli_database_proxy(self):
        dbfile = os.path.join(self.dir, 'proxy.db')
        with open(os.path.join(self.dir, 'cli_proxy_mod.py'), 'w') as fh:
            fh.write("from peewee import *\n"
                     "db = DatabaseProxy()\n"
                     "db.initialize(SqliteDatabase(%r))\n"
                     "raw = DatabaseProxy()\n"
                     "deferred = SqliteDatabase(None)\n" % dbfile)
        sys.path.insert(0, self.dir)
        try:
            rc, out, err = run_cli('cli_proxy_mod.db', 'status',
                                   '-d', self.migdir)
            self.assertEqual(rc, 0)

            rc, out, err = run_cli('cli_proxy_mod.raw', 'status',
                                   '-d', self.migdir)
            self.assertEqual(rc, 2)
            self.assertIn('uninitialized', err)

            rc, out, err = run_cli('cli_proxy_mod.deferred', 'status',
                                   '-d', self.migdir)
            self.assertEqual(rc, 2)
            self.assertIn('deferred', err)
        finally:
            sys.path.remove(self.dir)
            sys.modules.pop('cli_proxy_mod', None)

    def test_cli_ambiguous_file_module_spec(self):
        # "app.db" reads as both a filename and a dotted module path. The
        # module interpretation wins when no such file exists. Say so.
        dbfile = os.path.join(self.dir, 'clash.db')
        with open(os.path.join(self.dir, 'cli_clash_mod.py'), 'w') as fh:
            fh.write("from peewee import *\n"
                     "db = SqliteDatabase(%r)\n" % dbfile)
        sys.path.insert(0, self.dir)
        try:
            rc, out, err = run_cli('cli_clash_mod.db', 'status',
                                   '-d', self.migdir)
            self.assertEqual(rc, 0)
            self.assertIn('note: no file "cli_clash_mod.db" exists', err)
        finally:
            sys.path.remove(self.dir)
            sys.modules.pop('cli_clash_mod', None)

    def test_cli_workflow(self):
        rc, out, err = run_cli(self.url, 'create', 'add widget',
                               '-d', self.migdir)
        self.assertEqual(rc, 0)
        path = os.path.join(self.migdir, '0001_add_widget.py')
        self.assertTrue(os.path.exists(path))

        with open(path, 'w') as fh:
            fh.write(
                "def up(migrator, db):\n"
                "    db.execute_sql('CREATE TABLE widget ('\n"
                "                   'id INTEGER NOT NULL PRIMARY KEY, "
                "name TEXT)')\n"
                "def down(migrator, db):\n"
                "    db.execute_sql('DROP TABLE widget')\n")

        rc, out, err = run_cli(self.url, 'up', '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('applied: 0001_add_widget', out)

        rc, out, err = run_cli(self.url, 'status', '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('[x] 0001_add_widget', out)

        rc, out, err = run_cli(self.url, 'down', '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('reverted: 0001_add_widget', out)

        rc, out, err = run_cli(self.url, 'status', '-d', self.migdir)
        self.assertEqual(rc, 1)  # Pending migrations gate the exit code.
        self.assertIn('[ ] 0001_add_widget', out)

        rc, out, err = run_cli(self.url, 'fake', '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('faked: 0001_add_widget', out)
        rc, out, err = run_cli(self.url, 'up', '-d', self.migdir)
        self.assertIn('nothing to do.', out)

    def test_cli_status_missing_file(self):
        os.makedirs(self.migdir)
        path = os.path.join(self.migdir, '0001_gone.py')
        with open(path, 'w') as fh:
            fh.write('def up(migrator, db):\n    pass\n')
        rc, out, err = run_cli(self.url, 'up', '-d', self.migdir)
        self.assertEqual(rc, 0)
        os.remove(path)

        rc, out, err = run_cli(self.url, 'status', '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('[?] 0001_gone', out)

    def test_cli_import_error_attribution(self):
        # A missing dependency inside the module names the dependency,
        # not the spec.
        with open(os.path.join(self.dir, 'cli_dep_mod.py'), 'w') as fh:
            fh.write('import missing_dep_xyz\ndb = None\n')
        sys.path.insert(0, self.dir)
        try:
            rc, out, err = run_cli('cli_dep_mod.db', 'status',
                                   '-d', self.migdir)
            self.assertEqual(rc, 2)
            self.assertIn('cannot import "cli_dep_mod"', err)
            self.assertIn("No module named 'missing_dep_xyz'", err)

            rc, out, err = run_cli('no_such_mod.db', 'status',
                                   '-d', self.migdir)
            self.assertEqual(rc, 2)
            self.assertIn('cannot import "no_such_mod"', err)
        finally:
            sys.path.remove(self.dir)
            sys.modules.pop('cli_dep_mod', None)

    def test_cli_config_file(self):
        conf = os.path.join(self.dir, 'pw.conf')
        with open(conf, 'w') as fh:
            fh.write('# project defaults\n'
                     'database = %s\n'
                     'directory = %s\n' % (self.url, self.migdir))
        rc, out, err = run_cli('-c', conf, 'create', 'add widget')
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(
            os.path.join(self.migdir, '0001_add_widget.py')))

        rc, out, err = run_cli('-c', conf, 'up')
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'applied: 0001_add_widget\n')

        # Explicit arguments override the file.
        rc, out, err = run_cli(self.url, 'status', '-d', self.migdir,
                               '-c', conf)
        self.assertEqual(rc, 0)
        self.assertIn('[x] 0001_add_widget', out)

    def test_cli_config_dotfile(self):
        cwd = os.getcwd()
        os.chdir(self.dir)
        try:
            with open('.pwmigrate', 'w') as fh:
                fh.write('database = %s\ndirectory = %s\n'
                         % (self.url, self.migdir))
            rc, out, err = run_cli('status')
            self.assertEqual(rc, 0)
        finally:
            os.chdir(cwd)

    def test_cli_config_errors(self):
        # Bare command with no config in the working directory.
        rc, out, err = run_cli('up')
        self.assertEqual(rc, 2)
        self.assertIn('no database given', err)

        rc, out, err = run_cli('-c', 'nonexistent.conf', 'up')
        self.assertEqual(rc, 2)
        self.assertIn('not found', err)

        conf = os.path.join(self.dir, 'typo.conf')
        with open(conf, 'w') as fh:
            fh.write('database = %s\ntabel = x\n' % self.url)
        rc, out, err = run_cli('-c', conf, 'status', '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('unknown key "tabel"', err)

    def test_cli_bad_url(self):
        # Two slashes instead of three: the database name lands in the
        # host slot.
        rc, out, err = run_cli('sqlite://cli.db', 'status', '-d', self.migdir)
        self.assertEqual(rc, 2)
        self.assertIn('cannot connect to "sqlite://cli.db"', err)

        rc, out, err = run_cli('postgres://clidb', 'status',
                               '-d', self.migdir)
        self.assertEqual(rc, 2)
        self.assertIn('no database name', err)
        self.assertIn('postgres:///', err)

        rc, out, err = run_cli('sqlitex:///cli.db', 'status',
                               '-d', self.migdir)
        self.assertEqual(rc, 2)
        self.assertIn('Unrecognized', err)

    def test_cli_error_exit_codes(self):
        # Unreachable database exits 2, distinct from pending's exit 1.
        url = 'sqlite:///%s' % os.path.join(self.dir, 'missing', 'cli.db')
        rc, out, err = run_cli(url, 'status', '-d', self.migdir)
        self.assertEqual(rc, 2)
        self.assertIn('error:', err)

        # A migration whose SQL fails exits 2.
        os.makedirs(self.migdir)
        path = os.path.join(self.migdir, '0001_boom.py')
        with open(path, 'w') as fh:
            fh.write("def up(migrator, db):\n"
                     "    db.execute_sql('ALTER TABLE nope ADD COLUMN x')\n")
        rc, out, err = run_cli(self.url, 'up', '-d', self.migdir)
        self.assertEqual(rc, 2)
        self.assertIn('error:', err)


CLI_INITIAL_BODY = """\
from peewee import *

def up(migrator, db):
    class Widget(Model):
        name = CharField(unique=True)
        class Meta:
            database = db
            table_name = 'widget'
    db.create_tables([Widget])


def down(migrator, db):
    migrator.migrate(migrator.drop_table('widget'))
"""


class TestMigrationsCLIDiff(BaseTestCase):
    def setUp(self):
        super(TestMigrationsCLIDiff, self).setUp()
        self.dir = tempfile.mkdtemp()
        self.migdir = os.path.join(self.dir, 'migrations')
        self.url = 'sqlite:///%s' % os.path.join(self.dir, 'cli.db')
        sys.path.insert(0, self.dir)
        with open(os.path.join(self.dir, 'cli_diff_models.py'), 'w') as fh:
            fh.write(
                "from peewee import *\n"
                "from playhouse.sqlite_ext import FTS5Model, SearchField\n\n"
                "class Base(Model):\n"
                "    pass\n\n"
                "class Widget(Base):\n"
                "    name = CharField(unique=True)\n"
                "    class Meta:\n"
                "        table_name = 'widget'\n\n"
                "class Notes(FTS5Model):\n"
                "    content = SearchField()\n"
                "    class Meta:\n"
                "        table_name = 'notes'\n\n"
                "MODELS = [Widget]\n")

    def tearDown(self):
        sys.path.remove(self.dir)
        sys.modules.pop('cli_diff_models', None)
        shutil.rmtree(self.dir, ignore_errors=True)
        super(TestMigrationsCLIDiff, self).tearDown()

    def test_cli_initial(self):
        # initial assumes an empty database: no introspection, so it also
        # works against a database that already has the schema.
        rc, out, err = run_cli(self.url, 'initial', 'cli_diff_models',
                               '-d', self.migdir)
        self.assertEqual(rc, 0)
        path = os.path.join(self.migdir, '0001_initial.py')
        self.assertEqual(out, '%s\n' % path)
        self.assertEqual(err, 'skipped: Base (no fields)\n'
                              'skipped: Notes (virtual table)\n')
        with open(path) as fh:
            body = fh.read()
        # Compare below the timestamped header comment.
        self.assertEqual(body.split('\n', 1)[1], CLI_INITIAL_BODY)

        rc, out, err = run_cli(self.url, 'up', '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'applied: 0001_initial\n')
        rc, out, err = run_cli(self.url, 'diff', 'cli_diff_models',
                               '-d', self.migdir)
        self.assertEqual(out, 'schema matches models.\n')

        # A second initial refuses.
        rc, out, err = run_cli(self.url, 'initial', 'cli_diff_models',
                               '-d', self.migdir)
        self.assertEqual(rc, 2)
        self.assertEqual(err, 'error: migrations already exist in "%s".\n'
                         % self.migdir)

    def test_cli_config_models(self):
        conf = os.path.join(self.dir, 'pw.conf')
        with open(conf, 'w') as fh:
            fh.write('database = %s\nmodels = cli_diff_models\n' % self.url)
        rc, out, err = run_cli('-c', conf, 'diff', '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('create table widget', out)

        # Without config or argument, diff has no models module.
        rc, out, err = run_cli(self.url, 'diff', '-d', self.migdir)
        self.assertEqual(rc, 2)
        self.assertEqual(err, 'error: diff requires a models module.\n')

    def test_cli_diff_and_generate(self):
        # diff: field-less base skipped and reported, drift printed.
        rc, out, err = run_cli(self.url, 'diff', 'cli_diff_models',
                               '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('create table widget', out)
        self.assertIn('skipped: Base (no fields)', err)

        # The explicit-list form bypasses discovery.
        rc, out, err = run_cli(self.url, 'diff',
                               'cli_diff_models:MODELS',
                               '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('create table widget', out)
        self.assertEqual(err, '')

        # generate: build from diff, apply, converge.
        rc, out, err = run_cli(self.url, 'generate', 'initial',
                               'cli_diff_models', '-d', self.migdir)
        self.assertEqual(rc, 0)
        path = os.path.join(self.migdir, '0001_initial.py')
        self.assertTrue(os.path.exists(path))
        with open(path) as fh:
            body = fh.read()
        self.assertIn('db.create_tables([Widget])', body)

        rc, out, err = run_cli(self.url, 'up', '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('applied: 0001_initial', out)

        rc, out, err = run_cli(self.url, 'diff', 'cli_diff_models',
                               '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('schema matches models.', out)

        rc, out, err = run_cli(self.url, 'generate', 'noop',
                               'cli_diff_models', '-d', self.migdir)
        self.assertEqual(rc, 0)
        self.assertIn('Nothing to generate', out)
        self.assertFalse(os.path.exists(
            os.path.join(self.migdir, '0002_noop.py')))
