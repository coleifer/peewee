import os
import re
import unittest

from peewee import *
from peewee import create_model_tables
from peewee import drop_model_tables
from peewee import mysql
from pwiz import *
from peewee import print_


TEST_VERBOSITY = int(os.environ.get('PEEWEE_TEST_VERBOSITY') or 1)

# test databases
sqlite_db = SqliteDatabase('tmp.db')
if mysql:
    mysql_db = MySQLDatabase('peewee_test')
else:
    mysql_db = None
try:
    import psycopg2
    postgres_db = PostgresqlDatabase('peewee_test')
except ImportError:
    postgres_db = None

class BaseModel(Model):
    class Meta:
        database = sqlite_db

class ColTypes(BaseModel):
    f1 = BigIntegerField()
    f2 = BlobField()
    f3 = BooleanField()
    f4 = CharField(max_length=50)
    f5 = DateField()
    f6 = DateTimeField()
    f7 = DecimalField()
    f8 = DoubleField()
    f9 = FloatField()
    f10 = IntegerField()
    f11 = PrimaryKeyField()
    f12 = TextField()
    f13 = TimeField()

class Nullable(BaseModel):
    nullable_cf = CharField(null=True)
    nullable_if = IntegerField(null=True)

class RelModel(BaseModel):
    col_types = ForeignKeyField(ColTypes, related_name='foo')
    col_types_nullable = ForeignKeyField(ColTypes, null=True)

class FKPK(BaseModel):
    col_types = ForeignKeyField(ColTypes, primary_key=True)

class Underscores(BaseModel):
    _id = PrimaryKeyField()
    _name = CharField()

class Category(BaseModel):
    name = CharField(max_length=10)
    parent = ForeignKeyField('self', null=True)


DATABASES = (
    ('sqlite', sqlite_db),
    ('mysql', mysql_db),
    ('postgres', postgres_db))

MODELS = (
    ColTypes,
    Nullable,
    RelModel,
    FKPK,
    Underscores,
    Category)

class TestPwiz(unittest.TestCase):
    def test_sqlite_fk_re(self):
        user_id_tests = [
            'FOREIGN KEY("user_id") REFERENCES "users"("id")',
            'FOREIGN KEY(user_id) REFERENCES users(id)',
            'FOREIGN KEY  ([user_id])  REFERENCES  [users]  ([id])',
            '"user_id" NOT NULL REFERENCES "users" ("id")',
            'user_id not null references users (id)',
        ]
        fk_pk_tests = [
            ('"col_types_id" INTEGER NOT NULL PRIMARY KEY REFERENCES '
             '"coltypes" ("f11")'),
            'FOREIGN KEY ("col_types_id") REFERENCES "coltypes" ("f11")',
        ]
        regex = SqliteMetadata.re_foreign_key

        for test in user_id_tests:
            match = re.search(regex, test, re.I)
            self.assertEqual(match.groups(), (
                'user_id', 'users', 'id',
            ))

        for test in fk_pk_tests:
            match = re.search(regex, test, re.I)
            self.assertEqual(match.groups(), (
                'col_types_id', 'coltypes', 'f11',
            ))

    def get_introspector(self):
        return Introspector(SqliteMetadata(sqlite_db))

    def test_make_column_name(self):
        introspector = self.get_introspector()
        tests = (
            ('Column', 'column'),
            ('Foo_iD', 'foo'),
            ('foo_id', 'foo'),
            ('foo_id_id', 'foo_id'),
            ('foo', 'foo'),
            ('_id', '_id'),
            ('a123', 'a123'),
            ('and', 'and_'),
            ('Class', 'class_'),
            ('Class_ID', 'class_'),
        )
        for col_name, expected in tests:
            self.assertEqual(
                introspector.make_column_name(col_name), expected)

    def test_make_model_name(self):
        introspector = self.get_introspector()
        tests = (
            ('Table', 'Table'),
            ('table', 'Table'),
            ('table_baz', 'TableBaz'),
            ('foo__bar__baz2', 'FooBarBaz2'),
            ('foo12_3', 'Foo123'),
        )
        for table_name, expected in tests:
            self.assertEqual(
                introspector.make_model_name(table_name), expected)

    def create_tables(self, db):
        for model in MODELS:
            model._meta.database = db

        drop_model_tables(MODELS, fail_silently=True)
        create_model_tables(MODELS)

    def generative_test(fn):
        def inner(self):
            for database_type, database in DATABASES:
                if database:
                    introspector = make_introspector(
                        database_type,
                        database.database)
                    self.create_tables(database)
                    fn(self, introspector)
                elif TEST_VERBOSITY > 0:
                    print_('Skipping %s, driver not found' % database_type)
        return inner

    @generative_test
    def test_col_types(self, introspector):
        columns, foreign_keys, model_names = introspector.introspect()
        expected = (
            ('coltypes', (
                ('f1', BigIntegerField, False),
                ('f2', (BlobField, TextField), False),
                ('f3', (BooleanField, IntegerField), False),
                ('f4', CharField, False),
                ('f5', DateField, False),
                ('f6', DateTimeField, False),
                ('f7', DecimalField, False),
                ('f8', (DoubleField, FloatField), False),
                ('f9', FloatField, False),
                ('f10', IntegerField, False),
                ('f11', PrimaryKeyField, False),
                ('f12', TextField, False),
                ('f13', TimeField, False))),
            ('relmodel', (
                ('col_types_id', ForeignKeyField, False),
                ('col_types_nullable_id', ForeignKeyField, True))),
            ('nullable', (
                ('nullable_cf', CharField, True),
                ('nullable_if', IntegerField, True))),
            ('fkpk', (
                ('col_types_id', ForeignKeyField, False),)),
            ('underscores', (
                ('_id', PrimaryKeyField, False),
                ('_name', CharField, False))),
            ('category', (
                ('name', CharField, False),
                ('parent_id', ForeignKeyField, True))),
        )

        for table_name, expected_columns in expected:
            introspected_columns = columns[table_name]

            for field_name, field_class, is_null in expected_columns:
                if not isinstance(field_class, (list, tuple)):
                    field_class = (field_class,)
                column = introspected_columns[field_name]
                self.assertTrue(column.field_class in field_class)
                self.assertEqual(column.nullable, is_null)

    @generative_test
    def test_foreign_keys(self, introspector):
        columns, foreign_keys, model_names = introspector.introspect()
        self.assertEqual(foreign_keys['coltypes'], [])

        rel_model = foreign_keys['relmodel']
        self.assertEqual(len(rel_model), 2)

        fkpk = foreign_keys['fkpk']
        self.assertEqual(len(fkpk), 1)

        fkpk_fk = fkpk[0]
        self.assertEqual(fkpk_fk.table, 'fkpk')
        self.assertEqual(fkpk_fk.column, 'col_types_id')
        self.assertEqual(fkpk_fk.dest_table, 'coltypes')
        self.assertEqual(fkpk_fk.dest_column, 'f11')

        category = foreign_keys['category']
        self.assertEqual(len(category), 1)

        category_fk = category[0]
        self.assertEqual(category_fk.table, 'category')
        self.assertEqual(category_fk.column, 'parent_id')
        self.assertEqual(category_fk.dest_table, 'category')
        self.assertEqual(category_fk.dest_column, 'id')

    @generative_test
    def test_table_names(self, introspector):
        columns, foreign_keys, model_names = introspector.introspect()
        names = (
            ('coltypes', 'Coltypes'),
            ('nullable', 'Nullable'),
            ('relmodel', 'Relmodel'),
            ('fkpk', 'Fkpk'))
        for k, v in names:
            self.assertEqual(model_names[k], v)

    @generative_test
    def test_column_meta(self, introspector):
        columns, foreign_keys, model_names = introspector.introspect()
        rel_model = columns['relmodel']

        col_types_id = rel_model['col_types_id']
        self.assertEqual(col_types_id.get_field_parameters(), {
            'db_column': "'col_types_id'",
            'rel_model': 'Coltypes',
        })

        col_types_nullable_id = rel_model['col_types_nullable_id']
        self.assertEqual(col_types_nullable_id.get_field_parameters(), {
            'db_column': "'col_types_nullable_id'",
            'null': True,
            'rel_model': 'Coltypes',
        })

        fkpk = columns['fkpk']
        self.assertEqual(fkpk['col_types_id'].get_field_parameters(), {
            'db_column': "'col_types_id'",
            'rel_model': 'Coltypes',
            'primary_key': True})

    @generative_test
    def test_get_field(self, introspector):
        columns, foreign_keys, model_names = introspector.introspect()
        expected = (
            ('coltypes', (
                ('f1', 'f1 = BigIntegerField()'),
                #('f2', 'f2 = BlobField()'),
                ('f4', 'f4 = CharField(max_length=50)'),
                ('f5', 'f5 = DateField()'),
                ('f6', 'f6 = DateTimeField()'),
                ('f7', 'f7 = DecimalField()'),
                ('f10', 'f10 = IntegerField()'),
                ('f11', 'f11 = PrimaryKeyField()'),
                ('f12', 'f12 = TextField()'),
                ('f13', 'f13 = TimeField()'),
            )),
            ('nullable', (
                ('nullable_cf', 'nullable_cf = '
                 'CharField(max_length=255, null=True)'),
                ('nullable_if', 'nullable_if = IntegerField(null=True)'),
            )),
            ('fkpk', (
                ('col_types_id', 'col_types = ForeignKeyField('
                 'db_column=\'col_types_id\', primary_key=True, '
                 'rel_model=Coltypes)'),
            )),
            ('relmodel', (
                ('col_types_id', 'col_types = ForeignKeyField('
                 'db_column=\'col_types_id\', rel_model=Coltypes)'),
                ('col_types_nullable_id', 'col_types_nullable = '
                 'ForeignKeyField(db_column=\'col_types_nullable_id\', '
                 'null=True, rel_model=Coltypes)'),
            )),
            ('underscores', (
                ('_id', '_id = PrimaryKeyField()'),
                ('_name', '_name = CharField(max_length=255)'),
            )),
            ('category', (
                ('name', 'name = CharField(max_length=10)'),
                ('parent_id', 'parent = ForeignKeyField('
                 'db_column=\'parent_id\', null=True, rel_model=\'self\')'),
            )),
        )

        for table, field_data in expected:
            for field_name, field_str in field_data:
                self.assertEqual(
                    columns[table][field_name].get_field(),
                    field_str)
