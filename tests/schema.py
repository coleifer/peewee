from peewee import *

from .base import get_in_memory_db
from .base import ModelDatabaseTestCase
from .base import TestModel
from .base_models import Category
from .base_models import Note
from .base_models import Person
from .base_models import Relationship
from .base_models import User


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


class NoRowid(TestModel):
    key = TextField(primary_key=True)
    value = TextField()

    class Meta:
        without_rowid = True


class NoPK(TestModel):
    data = TextField()

    class Meta:
        primary_key = False


class Article(TestModel):
    name = TextField(unique=True)
    timestamp = TimestampField()
    status = IntegerField()
    flags = IntegerField()


Article.add_index(Article.timestamp.desc(), Article.status)

idx = (Article
       .index(Article.name, Article.timestamp, Article.flags.bin_and(4))
       .where(Article.status == 1))
Article.add_index(idx)
Article.add_index(SQL('CREATE INDEX "article_foo" ON "article" ("flags" & 3)'))


class TestModelDDL(ModelDatabaseTestCase):
    database = get_in_memory_db()
    requires = [Article, Category, Note, Person, Relationship, TMUnique,
                TMSequence, TMIndexes, TMConstraints, User]

    def assertCreateTable(self, model_class, expected):
        sql, params = model_class._schema._create_table(False).query()
        self.assertEqual(params, [])

        indexes = []
        for create_index in model_class._schema._create_indexes(False):
            isql, params = create_index.query()
            self.assertEqual(params, [])
            indexes.append(isql)

        self.assertEqual([sql] + indexes, expected)

    def assertIndexes(self, model_class, expected):
        indexes = []
        for create_index in model_class._schema._create_indexes(False):
            indexes.append(create_index.query())

        self.assertEqual(indexes, expected)

    def test_model_indexes(self):
        self.assertIndexes(Article, [
            ('CREATE UNIQUE INDEX "article_name" ON "article" ("name")', []),
            ('CREATE INDEX "article_timestamp_status" ON "article" ('
             '"timestamp" DESC, "status")', []),
            ('CREATE INDEX "article_name_timestamp" ON "article" ('
             '"name", "timestamp", ("flags" & ?)) '
             'WHERE ("status" = ?)', [4, 1]),
            ('CREATE INDEX "article_foo" ON "article" ("flags" & 3)', []),
        ])

    def test_without_pk(self):
        NoPK._meta.database = self.database
        self.assertCreateTable(NoPK, [
            ('CREATE TABLE "nopk" ("data" TEXT NOT NULL)')])

    def test_without_rowid(self):
        NoRowid._meta.database = self.database
        self.assertCreateTable(NoRowid, [
            ('CREATE TABLE "norowid" ('
             '"key" TEXT NOT NULL PRIMARY KEY, '
             '"value" TEXT NOT NULL) WITHOUT ROWID')])

        NoRowid._meta.database = None

    def test_db_table(self):
        class A(TestModel):
            class Meta:
                database = self.database
                db_table = 'A_tbl'
        class B(TestModel):
            a = ForeignKeyField(A, backref='bs')
            class Meta:
                database = self.database
                db_table = 'B_tbl'
        self.assertCreateTable(A, [
            'CREATE TABLE "A_tbl" ("id" INTEGER NOT NULL PRIMARY KEY)'])
        self.assertCreateTable(B, [
            ('CREATE TABLE "B_tbl" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"a_id" INTEGER NOT NULL, '
             'FOREIGN KEY ("a_id") REFERENCES "A_tbl" ("id"))'),
            'CREATE INDEX "b_a_id" ON "B_tbl" ("a_id")'])

    def test_temporary_table(self):
        sql, params = User._schema._create_table(temporary=True).query()
        self.assertEqual(sql, (
            'CREATE TEMPORARY TABLE IF NOT EXISTS "users" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"username" VARCHAR(255) NOT NULL)'))

        sql, params = User._schema._drop_table(temporary=True).query()
        self.assertEqual(sql, 'DROP TEMPORARY TABLE IF EXISTS "users"')

    def test_drop_table(self):
        sql, params = User._schema._drop_table().query()
        self.assertEqual(sql, 'DROP TABLE IF EXISTS "users"')

        sql, params = User._schema._drop_table(cascade=True).query()
        self.assertEqual(sql, 'DROP TABLE IF EXISTS "users" CASCADE')

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
            'CREATE INDEX "note_author_id" ON "note" ("author_id")'])

        self.assertCreateTable(Category, [
            ('CREATE TABLE "category" ('
             '"name" VARCHAR(20) NOT NULL PRIMARY KEY, '
             '"parent_id" VARCHAR(20), '
             'FOREIGN KEY ("parent_id") REFERENCES "category" ("name"))'),
            'CREATE INDEX "category_parent_id" ON "category" ("parent_id")'])

        self.assertCreateTable(Relationship, [
            ('CREATE TABLE "relationship" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"from_person_id" INTEGER NOT NULL, '
             '"to_person_id" INTEGER NOT NULL, '
             'FOREIGN KEY ("from_person_id") REFERENCES "person" ("id"), '
             'FOREIGN KEY ("to_person_id") REFERENCES "person" ("id"))'),
            ('CREATE INDEX "relationship_from_person_id" '
             'ON "relationship" ("from_person_id")'),
            ('CREATE INDEX "relationship_to_person_id" '
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
            class Meta:
                database = self.database

        fields = LongIndex._meta.sorted_fields[1:]
        self.assertEqual(len(fields), 3)

        idx = ModelIndex(LongIndex, fields)
        ctx = LongIndex._schema._create_index(idx)
        self.assertSQL(ctx, (
            'CREATE INDEX IF NOT EXISTS "'
            'longindex_a123456789012345678901234567890_b1234567890123_5088012'
            '" ON "longindex" ('
            '"a123456789012345678901234567890", '
            '"b123456789012345678901234567890", '
            '"c123456789012345678901234567890")'), [])

    def test_fk_non_pk_ddl(self):
        class A(Model):
            cf = CharField(max_length=100, unique=True)
            df = DecimalField(
                max_digits=4,
                decimal_places=2,
                auto_round=True,
                unique=True)
            class Meta:
                database = self.database

        class CF(TestModel):
            a = ForeignKeyField(A, field='cf')
            class Meta:
                database = self.database

        class DF(TestModel):
            a = ForeignKeyField(A, field='df')
            class Meta:
                database = self.database

        sql, params = CF._schema._create_table(safe=False).query()
        self.assertEqual(sql, (
            'CREATE TABLE "cf" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"a_id" VARCHAR(100) NOT NULL, '
            'FOREIGN KEY ("a_id") REFERENCES "a" ("cf"))'))

        sql, params = DF._schema._create_table(safe=False).query()
        self.assertEqual(sql, (
            'CREATE TABLE "df" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"a_id" DECIMAL(4, 2) NOT NULL, '
            'FOREIGN KEY ("a_id") REFERENCES "a" ("df"))'))

    def test_deferred_foreign_key(self):
        class Language(TestModel):
            name = CharField()
            selected_snippet = DeferredForeignKey('Snippet', null=True)
            class Meta:
                database = self.database

        class Snippet(TestModel):
            code = TextField()
            language = ForeignKeyField(Language, backref='snippets')
            class Meta:
                database = self.database

        self.assertEqual(Snippet._meta.fields['language'].rel_model, Language)
        self.assertEqual(Language._meta.fields['selected_snippet'].rel_model,
                         Snippet)

        sql, params = Snippet._schema._create_table(safe=False).query()
        self.assertEqual(sql, (
            'CREATE TABLE "snippet" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"code" TEXT NOT NULL, '
            '"language_id" INTEGER NOT NULL, '
            'FOREIGN KEY ("language_id") REFERENCES "language" ("id"))'))

        sql, params = Language._schema._create_table(safe=False).query()
        self.assertEqual(sql, (
            'CREATE TABLE "language" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"name" VARCHAR(255) NOT NULL, '
            '"selected_snippet_id" INTEGER)'))

        sql, params = (Language
                       ._schema
                       ._create_foreign_key(Language.selected_snippet)
                       .query())
        self.assertEqual(sql, (
            'ALTER TABLE "language" ADD CONSTRAINT '
            '"fk_language_selected_snippet_id_refs_snippet" '
            'FOREIGN KEY ("selected_snippet_id") REFERENCES "snippet" ("id")'))
