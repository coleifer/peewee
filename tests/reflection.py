import os
import re

from peewee import *
from playhouse.reflection import *

from .base import ModelTestCase
from .base import TestModel
from .base import db
from .base import skip_unless


class ColTypes(TestModel):
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
    f11 = AutoField()
    f12 = TextField()
    f13 = TimeField()

    class Meta:
        indexes = (
            (('f10', 'f11'), True),
            (('f11', 'f8', 'f13'), False),
        )


class Nullable(TestModel):
    nullable_cf = CharField(null=True)
    nullable_if = IntegerField(null=True)


class RelModel(TestModel):
    col_types = ForeignKeyField(ColTypes, backref='foo')
    col_types_nullable = ForeignKeyField(ColTypes, null=True)


class FKPK(TestModel):
    col_types = ForeignKeyField(ColTypes, primary_key=True)


class Underscores(TestModel):
    _id = AutoField()
    _name = CharField()


class Category(TestModel):
    name = CharField(max_length=10)
    parent = ForeignKeyField('self', null=True)


class Nugget(TestModel):
    category_id = ForeignKeyField(Category, column_name='category_id')
    category = CharField()


class TestReflection(ModelTestCase):
    requires = [ColTypes, Nullable, RelModel, FKPK, Underscores, Category,
                Nugget]

    def setUp(self):
        super(TestReflection, self).setUp()
        self.introspector = Introspector.from_database(self.database)

    def test_generate_models(self):
        models = self.introspector.generate_models()
        self.assertTrue(set((
            'category',
            'coltypes',
            'fkpk',
            'nugget',
            'nullable',
            'relmodel',
            'underscores')).issubset(set(models)))

        def assertIsInstance(obj, klass):
            self.assertTrue(isinstance(obj, klass))

        category = models['category']
        self.assertEqual(
            sorted(category._meta.fields),
            ['id', 'name', 'parent'])
        assertIsInstance(category.id, AutoField)
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

    @skip_unless(isinstance(db, SqliteDatabase))
    def test_generate_models_indexes(self):
        models = self.introspector.generate_models()

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
        models = self.introspector.generate_models(table_names=[
            'category',
            'coltypes',
            'foobarbaz'])
        self.assertEqual(sorted(models.keys()), ['category', 'coltypes'])

    @skip_unless(isinstance(db, SqliteDatabase))
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

    def test_make_column_name(self):
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
                self.introspector.make_column_name(col_name), expected)

    def test_make_model_name(self):
        tests = (
            ('Table', 'Table'),
            ('table', 'Table'),
            ('table_baz', 'TableBaz'),
            ('foo__bar__baz2', 'FooBarBaz2'),
            ('foo12_3', 'Foo123'),
        )
        for table_name, expected in tests:
            self.assertEqual(
                self.introspector.make_model_name(table_name), expected)

    def test_col_types(self):
        (columns,
         primary_keys,
         foreign_keys,
         model_names,
         indexes) = self.introspector.introspect()

        expected = (
            ('coltypes', (
                ('f1', (BigIntegerField, IntegerField), False),
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
                ('f11', AutoField, False),
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
                ('_id', AutoField, False),
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
                self.assertTrue(column.field_class in field_class,
                                "%s in %s" % (column.field_class, field_class))
                self.assertEqual(column.nullable, is_null)

    def test_foreign_keys(self):
        (columns,
         primary_keys,
         foreign_keys,
         model_names,
         indexes) = self.introspector.introspect()

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

    def test_table_names(self):
        (columns,
         primary_keys,
         foreign_keys,
         model_names,
         indexes) = self.introspector.introspect()

        names = (
            ('coltypes', 'Coltypes'),
            ('nullable', 'Nullable'),
            ('relmodel', 'Relmodel'),
            ('fkpk', 'Fkpk'))
        for k, v in names:
            self.assertEqual(model_names[k], v)

    def test_column_meta(self):
        (columns,
         primary_keys,
         foreign_keys,
         model_names,
         indexes) = self.introspector.introspect()

        rel_model = columns['relmodel']

        col_types_id = rel_model['col_types_id']
        self.assertEqual(col_types_id.get_field_parameters(), {
            'column_name': "'col_types_id'",
            'model': 'Coltypes',
            'field': "'f11'",
        })

        col_types_nullable_id = rel_model['col_types_nullable_id']
        self.assertEqual(col_types_nullable_id.get_field_parameters(), {
            'column_name': "'col_types_nullable_id'",
            'null': True,
            'backref': "'coltypes_col_types_nullable_set'",
            'model': 'Coltypes',
            'field': "'f11'",
        })

        fkpk = columns['fkpk']
        self.assertEqual(fkpk['col_types_id'].get_field_parameters(), {
            'column_name': "'col_types_id'",
            'model': 'Coltypes',
            'primary_key': True,
            'field': "'f11'"})

        category = columns['category']

        parent_id = category['parent_id']
        self.assertEqual(parent_id.get_field_parameters(), {
            'column_name': "'parent_id'",
            'null': True,
            'model': "'self'",
            'field': "'id'",
        })

        nugget = columns['nugget']
        category_fk = nugget['category_id']
        self.assertEqual(category_fk.name, 'category_id')
        self.assertEqual(category_fk.get_field_parameters(), {
            'field': "'id'",
            'model': 'Category',
            'column_name': "'category_id'",
        })

        category = nugget['category']
        self.assertEqual(category.name, 'category')

    def test_get_field(self):
        (columns,
         primary_keys,
         foreign_keys,
         model_names,
         indexes) = self.introspector.introspect()

        expected = (
            ('coltypes', (
                ('f1', ('f1 = BigIntegerField(index=True)',
                        'f1 = IntegerField(index=True)')),
                ('f2', ('f2 = BlobField()', 'f2 = TextField()')),
                ('f4', 'f4 = CharField()'),
                ('f5', 'f5 = DateField()'),
                ('f6', 'f6 = DateTimeField()'),
                ('f7', 'f7 = DecimalField()'),
                ('f10', 'f10 = IntegerField(unique=True)'),
                ('f11', 'f11 = AutoField()'),
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
                 "column_name='col_types_id', field='f11', model=Coltypes, "
                 'primary_key=True)'),
            )),
            ('nugget', (
                ('category_id', 'category_id = ForeignKeyField('
                 "column_name='category_id', field='id', model=Category)"),
                ('category', 'category = CharField()'),
            )),
            ('relmodel', (
                ('col_types_id', 'col_types = ForeignKeyField('
                 "column_name='col_types_id', field='f11', model=Coltypes)"),
                ('col_types_nullable_id', 'col_types_nullable = '
                 "ForeignKeyField(backref='coltypes_col_types_nullable_set', "
                 "column_name='col_types_nullable_id', field='f11', "
                 'model=Coltypes, null=True)'),
            )),
            ('underscores', (
                ('_id', '_id = AutoField()'),
                ('_name', '_name = CharField()'),
            )),
            ('category', (
                ('name', 'name = CharField()'),
                ('parent_id', 'parent = ForeignKeyField('
                 "column_name='parent_id', field='id', model='self', "
                 'null=True)'),
            )),
        )

        for table, field_data in expected:
            for field_name, fields in field_data:
                if not isinstance(fields, tuple):
                    fields = (fields,)
                actual = columns[table][field_name].get_field()
                self.assertTrue(actual in fields,
                                '%s not in %s' % (actual, fields))
