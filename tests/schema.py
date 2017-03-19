from peewee import *

from .base import get_in_memory_db
from .base import ModelDatabaseTestCase
from .base import TestModel
from .base_models import Category
from .base_models import Note
from .base_models import Person
from .base_models import Relationship


class TMUnique(TestModel):
    data = TextField(unique=True)


class TMSequence(TestModel):
    value = IntegerField(sequence='test_seq')


class TMIndexes(TestModel):
    alpha = IntegerField()
    beta = IntegerField()
    gamma = IntegerField()

    class Meta:
        indexes = (
            (('alpha', 'beta'), True),
            (('beta', 'gamma'), False))


class TMConstraints(TestModel):
    data = IntegerField(null=True, constraints=[Check('data < 5')])
    value = TextField(collation='NOCASE')


class TestModelDDL(ModelDatabaseTestCase):
    database = get_in_memory_db()
    requires = [Category, Note, Person, Relationship, TMUnique,
                TMSequence, TMIndexes, TMConstraints]

    def assertCreateTable(self, model_class, expected):
        sql, params = model_class._schema._create_table(False).query()
        self.assertEqual(params, [])

        indexes = []
        for create_index in model_class._schema._create_indexes(False):
            isql, params = create_index.query()
            self.assertEqual(params, [])
            indexes.append(isql)

        self.assertEqual([sql] + indexes, expected)

    def test_table_and_index_creation(self):
        self.assertCreateTable(Person, [
            ('CREATE TABLE "person" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"first" VARCHAR(255) NOT NULL, '
             '"last" VARCHAR(255) NOT NULL, '
             '"dob" DATE NOT NULL)'),
            'CREATE INDEX "person_dob" ON "person" ("dob")',
            ('CREATE UNIQUE INDEX "person_first_last" ON '
             '"person" ("first", "last")')])

        self.assertCreateTable(Note, [
            ('CREATE TABLE "note" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"author_id" INTEGER NOT NULL, '
             '"content" TEXT NOT NULL, '
             'FOREIGN KEY ("author_id") REFERENCES "person" ("id"))'),
            'CREATE INDEX "note_author" ON "note" ("author_id")'])

        self.assertCreateTable(Category, [
            ('CREATE TABLE "category" ('
             '"name" VARCHAR(20) NOT NULL PRIMARY KEY, '
             '"parent_id" VARCHAR(20), '
             'FOREIGN KEY ("parent_id") REFERENCES "category" ("name"))'),
            'CREATE INDEX "category_parent" ON "category" ("parent_id")'])

        self.assertCreateTable(Relationship, [
            ('CREATE TABLE "relationship" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"from_person_id" INTEGER NOT NULL, '
             '"to_person_id" INTEGER NOT NULL, '
             'FOREIGN KEY ("from_person_id") REFERENCES "person" ("id"), '
             'FOREIGN KEY ("to_person_id") REFERENCES "person" ("id"))'),
            ('CREATE INDEX "relationship_from_person" '
             'ON "relationship" ("from_person_id")'),
            ('CREATE INDEX "relationship_to_person" '
             'ON "relationship" ("to_person_id")')])

        self.assertCreateTable(TMUnique, [
            ('CREATE TABLE "tmunique" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"data" TEXT NOT NULL)'),
            'CREATE UNIQUE INDEX "tmunique_data" ON "tmunique" ("data")'])

        self.assertCreateTable(TMSequence, [
            ('CREATE TABLE "tmsequence" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"value" INTEGER NOT NULL DEFAULT NEXTVAL(\'test_seq\'))')])

        self.assertCreateTable(TMIndexes, [
            ('CREATE TABLE "tmindexes" ("id" INTEGER NOT NULL PRIMARY KEY, '
             '"alpha" INTEGER NOT NULL, "beta" INTEGER NOT NULL, '
             '"gamma" INTEGER NOT NULL)'),
            ('CREATE UNIQUE INDEX "tmindexes_alpha_beta" '
             'ON "tmindexes" ("alpha", "beta")'),
            ('CREATE INDEX "tmindexes_beta_gamma" '
             'ON "tmindexes" ("beta", "gamma")')])

        self.assertCreateTable(TMConstraints, [
            ('CREATE TABLE "tmconstraints" ("id" INTEGER NOT NULL PRIMARY KEY,'
             ' "data" INTEGER CHECK (data < 5), '
             '"value" TEXT NOT NULL COLLATE NOCASE)')])

    def test_index_name_truncation(self):
        class LongIndex(TestModel):
            a123456789012345678901234567890 = CharField()
            b123456789012345678901234567890 = CharField()
            c123456789012345678901234567890 = CharField()

        fields = LongIndex._meta.sorted_fields[1:]
        self.assertEqual(len(fields), 3)

        ctx = LongIndex._schema._create_index(fields)
        self.assertSQL(ctx, (
            'CREATE INDEX IF NOT EXISTS "'
            'longindex_a123456789012345678901234567890_b1234567890123_5088012'
            '" ON "longindex" ('
            '"a123456789012345678901234567890", '
            '"b123456789012345678901234567890", '
            '"c123456789012345678901234567890")'), [])
