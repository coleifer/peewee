import os
import re

from peewee import *
from peewee import create_model_tables
from peewee import drop_model_tables
from peewee import mysql
from peewee import print_
from playhouse.reflection import *
from playhouse.tests.base import database_initializer
from playhouse.tests.base import PeeweeTestCase


sqlite_db = database_initializer.get_database('sqlite')
DATABASES = [sqlite_db]

if mysql:
    DATABASES.append(database_initializer.get_database('mysql'))

try:
    import psycopg2
    DATABASES.append(database_initializer.get_database('postgres'))
except ImportError:
    pass

class BaseModel(Model):
    class Meta:
        database = sqlite_db

class ColTypes(BaseModel):
    f1 = BigIntegerField(index=True)
    f2 = BlobField()
    f3 = BooleanField()
    f4 = CharField(max_length=50)
    f5 = DateField()
    f6 = DateTimeField()
    f7 = DecimalField()
    f8 = DoubleField()
    f9 = FloatField()
    f10 = IntegerField(unique=True)
    f11 = PrimaryKeyField()
    f12 = TextField()
    f13 = TimeField()

    class Meta:
        indexes = (
            (('f10', 'f11'), True),
            (('f11', 'f8', 'f13'), False),
        )

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

class Nugget(BaseModel):
    category_id = ForeignKeyField(Category, db_column='category_id')
    category = CharField()

class NumericColumn(BaseModel):
    three = CharField(db_column='3data')
    five = CharField(db_column='555_value')
    seven = CharField(db_column='7 eleven')

MODELS = (
    ColTypes,
    Nullable,
    RelModel,
    FKPK,
    Underscores,
    Category,
    Nugget)

class TestReflection(PeeweeTestCase):
    def setUp(self):
        super(TestReflection, self).setUp()
        if os.path.exists(sqlite_db.database):
            os.unlink(sqlite_db.database)
        sqlite_db.connect()

        for model in MODELS:
            model._meta.database = sqlite_db

    def tearDown(self):
        sqlite_db.close()

    def test_generate_models(self):
        introspector = self.get_introspector()
        self.assertEqual(introspector.generate_models(), {})

        for model in MODELS:
            model.create_table()

        models = introspector.generate_models()
        self.assertEqual(sorted(models.keys()), [
            'category',
            'coltypes',
            'fkpk',
            'nugget',
            'nullable',
            'relmodel',
            'underscores'])

        def assertIsInstance(obj, klass):
            self.assertTrue(isinstance(obj, klass))

        category = models['category']
        self.assertEqual(
            sorted(category._meta.fields),
            ['id', 'name', 'parent'])
        assertIsInstance(category.id, PrimaryKeyField)
        assertIsInstance(category.name, CharField)
        assertIsInstance(category.parent, ForeignKeyField)
        self.assertEqual(category.parent.rel_model, category)

        fkpk = models['fkpk']
        self.assertEqual(sorted(fkpk._meta.fields), ['col_types'])
        assertIsInstance(fkpk.col_types, ForeignKeyField)
        self.assertEqual(fkpk.col_types.rel_model, models['coltypes'])
        self.assertTrue(fkpk.col_types.primary_key)

        relmodel = models['relmodel']
        self.assertEqual(
            sorted(relmodel._meta.fields),
            ['col_types', 'col_types_nullable', 'id'])
        assertIsInstance(relmodel.col_types, ForeignKeyField)
        assertIsInstance(relmodel.col_types_nullable, ForeignKeyField)
        self.assertFalse(relmodel.col_types.null)
        self.assertTrue(relmodel.col_types_nullable.null)
        self.assertEqual(relmodel.col_types.rel_model,
                         models['coltypes'])
        self.assertEqual(relmodel.col_types_nullable.rel_model,
                         models['coltypes'])

    def test_generate_models_indexes(self):
        introspector = self.get_introspector()
        self.assertEqual(introspector.generate_models(), {})

        for model in MODELS:
            model.create_table()

        models = introspector.generate_models()

        self.assertEqual(models['fkpk']._meta.indexes, [])
        self.assertEqual(models['relmodel']._meta.indexes, [])
        self.assertEqual(models['category']._meta.indexes, [])

        col_types = models['coltypes']
        indexed = set(['f1'])
        unique = set(['f10'])
        for field in col_types._meta.sorted_fields:
            self.assertEqual(field.index, field.name in indexed)
            self.assertEqual(field.unique, field.name in unique)
        indexes = col_types._meta.indexes
        self.assertEqual(sorted(indexes), [
            (['f10', 'f11'], True),
            (['f11', 'f8', 'f13'], False),
        ])

    def test_table_subset(self):
        for model in MODELS:
            model.create_table()

        introspector = self.get_introspector()
        models = introspector.generate_models(table_names=[
            'category',
            'coltypes',
            'foobarbaz'])
        self.assertEqual(sorted(models.keys()), ['category', 'coltypes'])

    def test_invalid_python_field_names(self):
        NumericColumn.create_table()
        introspector = self.get_introspector()
        models = introspector.generate_models(table_names=['numericcolumn'])
        NC = models['numericcolumn']
        self.assertEqual(sorted(NC._meta.fields),
                         ['_3data', '_555_value', '_7_eleven', 'id'])

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
        return Introspector.from_database(sqlite_db)

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
            for database in DATABASES:
                try:
                    introspector = Introspector.from_database(database)
                    self.create_tables(database)
                    fn(self, introspector)
                finally:
                    drop_model_tables(MODELS)
        return inner

    @generative_test
    def test_col_types(self, introspector):
        columns, primary_keys, foreign_keys, model_names, indexes =\
                introspector.introspect()

        expected = (
            ('coltypes', (
                ('f1', BigIntegerField, False),
                # There do not appear to be separate constants for the blob and
                # text field types in MySQL's drivers. See GH#1034.
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
            ('nugget', (
                ('category_id', ForeignKeyField, False),
                ('category', CharField, False))),
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
        columns, primary_keys, foreign_keys, model_names, indexes =\
                introspector.introspect()

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
        columns, primary_keys, foreign_keys, model_names, indexes =\
                introspector.introspect()

        names = (
            ('coltypes', 'Coltypes'),
            ('nullable', 'Nullable'),
            ('relmodel', 'Relmodel'),
            ('fkpk', 'Fkpk'))
        for k, v in names:
            self.assertEqual(model_names[k], v)

    @generative_test
    def test_column_meta(self, introspector):
        columns, primary_keys, foreign_keys, model_names, indexes =\
                introspector.introspect()

        rel_model = columns['relmodel']

        col_types_id = rel_model['col_types_id']
        self.assertEqual(col_types_id.get_field_parameters(), {
            'db_column': "'col_types_id'",
            'rel_model': 'Coltypes',
            'to_field': "'f11'",
        })

        col_types_nullable_id = rel_model['col_types_nullable_id']
        self.assertEqual(col_types_nullable_id.get_field_parameters(), {
            'db_column': "'col_types_nullable_id'",
            'null': True,
            'related_name': "'coltypes_col_types_nullable_set'",
            'rel_model': 'Coltypes',
            'to_field': "'f11'",
        })

        fkpk = columns['fkpk']
        self.assertEqual(fkpk['col_types_id'].get_field_parameters(), {
            'db_column': "'col_types_id'",
            'rel_model': 'Coltypes',
            'primary_key': True,
            'to_field': "'f11'"})

        category = columns['category']

        parent_id = category['parent_id']
        self.assertEqual(parent_id.get_field_parameters(), {
            'db_column': "'parent_id'",
            'null': True,
            'rel_model': "'self'",
            'to_field': "'id'",
        })

        nugget = columns['nugget']
        category_fk = nugget['category_id']
        self.assertEqual(category_fk.name, 'category_id')
        self.assertEqual(category_fk.get_field_parameters(), {
            'to_field': "'id'",
            'rel_model': 'Category',
            'db_column': "'category_id'",
        })

        category = nugget['category']
        self.assertEqual(category.name, 'category')

    @generative_test
    def test_get_field(self, introspector):
        columns, primary_keys, foreign_keys, model_names, indexes =\
                introspector.introspect()

        expected = (
            ('coltypes', (
                ('f1', 'f1 = BigIntegerField(index=True)'),
                ('f2', 'f2 = BlobField()'),
                ('f4', 'f4 = CharField()'),
                ('f5', 'f5 = DateField()'),
                ('f6', 'f6 = DateTimeField()'),
                ('f7', 'f7 = DecimalField()'),
                ('f10', 'f10 = IntegerField(unique=True)'),
                ('f11', 'f11 = PrimaryKeyField()'),
                ('f12', ('f12 = TextField()', 'f12 = BlobField()')),
                ('f13', 'f13 = TimeField()'),
            )),
            ('nullable', (
                ('nullable_cf', 'nullable_cf = '
                 'CharField(null=True)'),
                ('nullable_if', 'nullable_if = IntegerField(null=True)'),
            )),
            ('fkpk', (
                ('col_types_id', 'col_types = ForeignKeyField('
                 'db_column=\'col_types_id\', primary_key=True, '
                 'rel_model=Coltypes, to_field=\'f11\')'),
            )),
            ('nugget', (
                ('category_id', 'category_id = ForeignKeyField('
                 'db_column=\'category_id\', rel_model=Category, '
                 'to_field=\'id\')'),
                ('category', 'category = CharField()'),
            )),
            ('relmodel', (
                ('col_types_id', 'col_types = ForeignKeyField('
                 'db_column=\'col_types_id\', rel_model=Coltypes, '
                 'to_field=\'f11\')'),
                ('col_types_nullable_id', 'col_types_nullable = '
                 'ForeignKeyField(db_column=\'col_types_nullable_id\', '
                 'null=True, rel_model=Coltypes, '
                 'related_name=\'coltypes_col_types_nullable_set\', '
                 'to_field=\'f11\')'),
            )),
            ('underscores', (
                ('_id', '_id = PrimaryKeyField()'),
                ('_name', '_name = CharField()'),
            )),
            ('category', (
                ('name', 'name = CharField()'),
                ('parent_id', 'parent = ForeignKeyField('
                 'db_column=\'parent_id\', null=True, rel_model=\'self\', '
                 'to_field=\'id\')'),
            )),
        )

        for table, field_data in expected:
            for field_name, fields in field_data:
                if not isinstance(fields, tuple):
                    fields = (fields,)
                self.assertTrue(columns[table][field_name].get_field(), fields)
