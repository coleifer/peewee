import datetime

from peewee import *
from peewee import NodeList

from .base import BaseTestCase
from .base import get_in_memory_db
from .base import IS_SQLITE
from .base import ModelDatabaseTestCase
from .base import ModelTestCase
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


class CacheData(TestModel):
    key = TextField(unique=True)
    value = TextField()

    class Meta:
        schema = 'cache'


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
    requires = [Article, CacheData, Category, Note, Person, Relationship,
                TMUnique, TMSequence, TMIndexes, TMConstraints, User]

    def test_database_required(self):
        class MissingDB(Model):
            data = TextField()

        self.assertRaises(ImproperlyConfigured, MissingDB.create_table)

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

    def test_model_fk_schema(self):
        class Base(TestModel):
            class Meta:
                database = self.database
        class User(Base):
            username = TextField()
            class Meta:
                schema = 'foo'
        class Tweet(Base):
            user = ForeignKeyField(User)
            content = TextField()
            class Meta:
                schema = 'bar'

        self.assertCreateTable(User, [
            ('CREATE TABLE "foo"."user" ("id" INTEGER NOT NULL PRIMARY KEY, '
             '"username" TEXT NOT NULL)')])
        self.assertCreateTable(Tweet, [
            ('CREATE TABLE "bar"."tweet" ("id" INTEGER NOT NULL PRIMARY KEY, '
             '"user_id" INTEGER NOT NULL, "content" TEXT NOT NULL, '
             'FOREIGN KEY ("user_id") REFERENCES "foo"."user" ("id"))'),
            ('CREATE INDEX "bar"."tweet_user_id" ON "tweet" ("user_id")')])

    def test_model_indexes_with_schema(self):
        # Attach cache database so we can reference "cache." as the schema.
        self.database.execute_sql("attach database ':memory:' as cache;")
        self.assertCreateTable(CacheData, [
            ('CREATE TABLE "cache"."cache_data" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, "key" TEXT NOT NULL, '
             '"value" TEXT NOT NULL)'),
            ('CREATE UNIQUE INDEX "cache"."cache_data_key" ON "cache_data" '
             '("key")')])

        # Actually create the table to verify it works correctly.
        CacheData.create_table()

        # Introspect the database and get indexes for the "cache" schema.
        indexes = self.database.get_indexes('cache_data', 'cache')
        self.assertEqual(len(indexes), 1)
        index_metadata = indexes[0]
        self.assertEqual(index_metadata.name, 'cache_data_key')

        # Verify the index does not exist in the main schema.
        self.assertEqual(len(self.database.get_indexes('cache_data')), 0)

        class TestDatabase(Database):
            index_schema_prefix = False

        # When "index_schema_prefix == False", the index name is not prefixed
        # with the schema, and the schema is referenced via the table name.
        with CacheData.bind_ctx(TestDatabase(None)):
            self.assertCreateTable(CacheData, [
                ('CREATE TABLE "cache"."cache_data" ('
                 '"id" INTEGER NOT NULL PRIMARY KEY, "key" TEXT NOT NULL, '
                 '"value" TEXT NOT NULL)'),
                ('CREATE UNIQUE INDEX "cache_data_key" ON "cache"."cache_data"'
                 ' ("key")')])

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

    def test_model_index_types(self):
        class Event(TestModel):
            key = TextField()
            timestamp = TimestampField(index=True, index_type='BRIN')
            class Meta:
                database = self.database

        self.assertIndexes(Event, [
            ('CREATE INDEX "event_timestamp" ON "event" '
             'USING BRIN ("timestamp")', [])])

    def test_model_indexes_custom_tablename(self):
        class KV(TestModel):
            key = TextField()
            value = TextField()
            timestamp = TimestampField(index=True)
            class Meta:
                database = self.database
                indexes = (
                    (('key', 'value'), True),
                )
                table_name = 'kvs'

        self.assertIndexes(KV, [
            ('CREATE INDEX "kvs_timestamp" ON "kvs" ("timestamp")', []),
            ('CREATE UNIQUE INDEX "kvs_key_value" ON "kvs" ("key", "value")',
             [])])

    def test_model_indexes_computed_columns(self):
        class FuncIdx(TestModel):
            a = IntegerField()
            b = IntegerField()
            class Meta:
                database = self.database

        i = FuncIdx.index(FuncIdx.a, FuncIdx.b, fn.SUM(FuncIdx.a + FuncIdx.b))
        FuncIdx.add_index(i)

        self.assertIndexes(FuncIdx, [
            ('CREATE INDEX "func_idx_a_b" ON "func_idx" '
             '("a", "b", SUM("a" + "b"))', []),
        ])

    def test_model_indexes_complex_columns(self):
        class Taxonomy(TestModel):
            name = CharField()
            name_class = CharField()
            class Meta:
                database = self.database

        name = NodeList((fn.LOWER(Taxonomy.name), SQL('varchar_pattern_ops')))
        index = (Taxonomy
                 .index(name, Taxonomy.name_class)
                 .where(Taxonomy.name_class == 'scientific name'))
        Taxonomy.add_index(index)

        self.assertIndexes(Taxonomy, [
            ('CREATE INDEX "taxonomy_name_class" ON "taxonomy" ('
             'LOWER("name") varchar_pattern_ops, "name_class") '
             'WHERE ("name_class" = ?)', ['scientific name']),
        ])

    def test_legacy_model_table_and_indexes(self):
        class Base(Model):
            class Meta:
                database = self.database

        class WebHTTPRequest(Base):
            timestamp = DateTimeField(index=True)
            data = TextField()

        self.assertTrue(WebHTTPRequest._meta.legacy_table_names)
        self.assertCreateTable(WebHTTPRequest, [
            ('CREATE TABLE "webhttprequest" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"timestamp" DATETIME NOT NULL, "data" TEXT NOT NULL)'),
            ('CREATE INDEX "webhttprequest_timestamp" ON "webhttprequest" '
             '("timestamp")')])

        # Table name is explicit, but legacy table names == false, so we get
        # the new index name format.
        class FooBar(Base):
            data = IntegerField(unique=True)
            class Meta:
                legacy_table_names = False
                table_name = 'foobar_tbl'

        self.assertFalse(FooBar._meta.legacy_table_names)
        self.assertCreateTable(FooBar, [
            ('CREATE TABLE "foobar_tbl" ("id" INTEGER NOT NULL PRIMARY KEY, '
             '"data" INTEGER NOT NULL)'),
            ('CREATE UNIQUE INDEX "foobar_tbl_data" ON "foobar_tbl" ("data")'),
        ])

        # Table name is explicit and legacy table names == true, so we get
        # the old index name format.
        class FooBar2(Base):
            data = IntegerField(unique=True)
            class Meta:
                table_name = 'foobar2_tbl'

        self.assertTrue(FooBar2._meta.legacy_table_names)
        self.assertCreateTable(FooBar2, [
            ('CREATE TABLE "foobar2_tbl" ("id" INTEGER NOT NULL PRIMARY KEY, '
             '"data" INTEGER NOT NULL)'),
            ('CREATE UNIQUE INDEX "foobar2_data" ON "foobar2_tbl" ("data")')])

    def test_without_pk(self):
        class NoPK(TestModel):
            data = TextField()
            class Meta:
                database = self.database
                primary_key = False
        self.assertCreateTable(NoPK, [
            ('CREATE TABLE "no_pk" ("data" TEXT NOT NULL)')])

    def test_without_rowid(self):
        class NoRowid(TestModel):
            key = TextField(primary_key=True)
            value = TextField()

            class Meta:
                database = self.database
                without_rowid = True

        self.assertCreateTable(NoRowid, [
            ('CREATE TABLE "no_rowid" ('
             '"key" TEXT NOT NULL PRIMARY KEY, '
             '"value" TEXT NOT NULL) WITHOUT ROWID')])

        # Subclasses do not inherit "without_rowid" setting.
        class SubNoRowid(NoRowid): pass

        self.assertCreateTable(SubNoRowid, [
            ('CREATE TABLE "sub_no_rowid" ('
             '"key" TEXT NOT NULL PRIMARY KEY, '
             '"value" TEXT NOT NULL)')])

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
            'CREATE INDEX "B_tbl_a_id" ON "B_tbl" ("a_id")'])

    def test_temporary_table(self):
        sql, params = User._schema._create_table(temporary=True).query()
        self.assertEqual(sql, (
            'CREATE TEMPORARY TABLE IF NOT EXISTS "users" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"username" VARCHAR(255) NOT NULL)'))

    def test_model_temporary_table(self):
        class TempUser(User):
            class Meta:
                temporary = True

        self.reset_sql_history()
        TempUser.create_table()
        TempUser.drop_table()
        queries = [x.msg for x in self.history]
        self.assertEqual(queries, [
            ('CREATE TEMPORARY TABLE IF NOT EXISTS "temp_user" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"username" VARCHAR(255) NOT NULL)', []),
            ('DROP TABLE IF EXISTS "temp_user"', [])])

    def test_drop_table(self):
        sql, params = User._schema._drop_table().query()
        self.assertEqual(sql, 'DROP TABLE IF EXISTS "users"')

        sql, params = User._schema._drop_table(cascade=True).query()
        self.assertEqual(sql, 'DROP TABLE IF EXISTS "users" CASCADE')

        sql, params = User._schema._drop_table(restrict=True).query()
        self.assertEqual(sql, 'DROP TABLE IF EXISTS "users" RESTRICT')

    def test_table_constraints(self):
        class UKV(TestModel):
            key = TextField()
            value = TextField()
            status = IntegerField()
            class Meta:
                constraints = [
                    SQL('CONSTRAINT ukv_kv_uniq UNIQUE (key, value)'),
                    Check('status > 0')]
                database = self.database
                table_name = 'ukv'

        self.assertCreateTable(UKV, [
            ('CREATE TABLE "ukv" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"key" TEXT NOT NULL, '
             '"value" TEXT NOT NULL, '
             '"status" INTEGER NOT NULL, '
             'CONSTRAINT ukv_kv_uniq UNIQUE (key, value), '
             'CHECK (status > 0))')])

    def test_table_settings(self):
        class KVSettings(TestModel):
            key = TextField(primary_key=True)
            value = TextField()
            timestamp = TimestampField()
            class Meta:
                database = self.database
                table_settings = ('PARTITION BY RANGE (timestamp)',
                                  'WITHOUT ROWID')
        self.assertCreateTable(KVSettings, [
            ('CREATE TABLE "kv_settings" ('
             '"key" TEXT NOT NULL PRIMARY KEY, '
             '"value" TEXT NOT NULL, '
             '"timestamp" INTEGER NOT NULL) '
             'PARTITION BY RANGE (timestamp) '
             'WITHOUT ROWID')])

    def test_table_options(self):
        class TOpts(TestModel):
            key = TextField()
            class Meta:
                database = self.database
                options = {
                    'CHECKSUM': 1,
                    'COMPRESSION': 'lz4'}

        self.assertCreateTable(TOpts, [
            ('CREATE TABLE "t_opts" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"key" TEXT NOT NULL, '
             'CHECKSUM=1, COMPRESSION=lz4)')])

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
            ('CREATE TABLE "tm_unique" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"data" TEXT NOT NULL)'),
            'CREATE UNIQUE INDEX "tm_unique_data" ON "tm_unique" ("data")'])

        self.assertCreateTable(TMSequence, [
            ('CREATE TABLE "tm_sequence" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"value" INTEGER NOT NULL DEFAULT NEXTVAL(\'test_seq\'))')])

        self.assertCreateTable(TMIndexes, [
            ('CREATE TABLE "tm_indexes" ("id" INTEGER NOT NULL PRIMARY KEY, '
             '"alpha" INTEGER NOT NULL, "beta" INTEGER NOT NULL, '
             '"gamma" INTEGER NOT NULL)'),
            ('CREATE UNIQUE INDEX "tm_indexes_alpha_beta" '
             'ON "tm_indexes" ("alpha", "beta")'),
            ('CREATE INDEX "tm_indexes_beta_gamma" '
             'ON "tm_indexes" ("beta", "gamma")')])

        self.assertCreateTable(TMConstraints, [
            ('CREATE TABLE "tm_constraints" ('
             '"id" INTEGER NOT NULL PRIMARY KEY,'
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
            'long_index_a123456789012345678901234567890_b123456789012_9dd2139'
            '" ON "long_index" ('
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

        class SnippetComment(TestModel):
            snippet_long_foreign_key_identifier = ForeignKeyField(Snippet)
            comment = TextField()
            class Meta:
                database = self.database

        sql, params = SnippetComment._schema._create_table(safe=True).query()
        self.assertEqual(sql, (
            'CREATE TABLE IF NOT EXISTS "snippet_comment" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"snippet_long_foreign_key_identifier_id" INTEGER NOT NULL, '
            '"comment" TEXT NOT NULL, '
            'FOREIGN KEY ("snippet_long_foreign_key_identifier_id") '
            'REFERENCES "snippet" ("id"))'))

        sql, params = (SnippetComment._schema
                       ._create_foreign_key(
                           SnippetComment.snippet_long_foreign_key_identifier)
                       .query())
        self.assertEqual(sql, (
            'ALTER TABLE "snippet_comment" ADD CONSTRAINT "'
            'fk_snippet_comment_snippet_long_foreign_key_identifier_i_2a8b87d"'
            ' FOREIGN KEY ("snippet_long_foreign_key_identifier_id") '
            'REFERENCES "snippet" ("id")'))

    def test_deferred_foreign_key_inheritance(self):
        class Base(TestModel):
            class Meta:
                database = self.database
        class WithTimestamp(Base):
            timestamp = TimestampField()
        class Tweet(Base):
            user = DeferredForeignKey('DUser')
            content = TextField()
        class TimestampTweet(Tweet, WithTimestamp): pass
        class DUser(Base):
            username = TextField()

        sql, params = Tweet._schema._create_table(safe=False).query()
        self.assertEqual(sql, (
            'CREATE TABLE "tweet" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"content" TEXT NOT NULL, '
            '"user_id" INTEGER NOT NULL)'))

        sql, params = TimestampTweet._schema._create_table(safe=False).query()
        self.assertEqual(sql, (
            'CREATE TABLE "timestamp_tweet" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, '
            '"timestamp" INTEGER NOT NULL, '
            '"content" TEXT NOT NULL, '
            '"user_id" INTEGER NOT NULL)'))

    def test_identity_field(self):
        class PG10Identity(TestModel):
            id = IdentityField()
            data = TextField()
            class Meta:
                database = self.database

        self.assertCreateTable(PG10Identity, [
            ('CREATE TABLE "pg10_identity" ('
             '"id" INT GENERATED BY DEFAULT AS IDENTITY NOT NULL PRIMARY KEY, '
             '"data" TEXT NOT NULL)'),
        ])

    def test_self_fk_inheritance(self):
        class BaseCategory(TestModel):
            parent = ForeignKeyField('self', backref='children')
            class Meta:
                database = self.database
        class CatA1(BaseCategory):
            name_a1 = TextField()
        class CatA2(CatA1):
            name_a2 = TextField()

        self.assertTrue(CatA1.parent.rel_model is CatA1)
        self.assertTrue(CatA2.parent.rel_model is CatA2)

        self.assertCreateTable(CatA1, [
            ('CREATE TABLE "cat_a1" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"parent_id" INTEGER NOT NULL, '
             '"name_a1" TEXT NOT NULL, '
             'FOREIGN KEY ("parent_id") REFERENCES "cat_a1" ("id"))'),
            ('CREATE INDEX "cat_a1_parent_id" ON "cat_a1" ("parent_id")')])

        self.assertCreateTable(CatA2, [
            ('CREATE TABLE "cat_a2" ('
             '"id" INTEGER NOT NULL PRIMARY KEY, '
             '"parent_id" INTEGER NOT NULL, '
             '"name_a1" TEXT NOT NULL, '
             '"name_a2" TEXT NOT NULL, '
             'FOREIGN KEY ("parent_id") REFERENCES "cat_a2" ("id"))'),
            ('CREATE INDEX "cat_a2_parent_id" ON "cat_a2" ("parent_id")')])


class NoteX(TestModel):
    content = TextField()
    timestamp = TimestampField()
    status = IntegerField()
    flags = IntegerField()


class TestCreateAs(ModelTestCase):
    requires = [NoteX]
    test_data = (
        # name, timestamp, status, flags.
        ('n1', datetime.datetime(2019, 1, 1), 1, 1),
        ('n2', datetime.datetime(2019, 1, 2), 2, 1),
        ('n3', datetime.datetime(2019, 1, 3), 9, 1),
        ('nx', datetime.datetime(2019, 1, 1), 9, 0))

    def setUp(self):
        super(TestCreateAs, self).setUp()
        fields = (NoteX.content, NoteX.timestamp, NoteX.status, NoteX.flags)
        NoteX.insert_many(self.test_data, fields=fields).execute()

    def test_create_as(self):
        status = Case(NoteX.status, (
            (1, 'published'),
            (2, 'draft'),
            (9, 'deleted')))

        query = (NoteX
                 .select(NoteX.id, NoteX.content, NoteX.timestamp,
                         status.alias('status'))
                 .where(NoteX.flags == SQL('1')))
        query.create_table('note2', temporary=True)

        class Note2(TestModel):
            id = IntegerField()
            content = TextField()
            timestamp = TimestampField()
            status = TextField()
            class Meta:
                database = self.database

        query = Note2.select().order_by(Note2.id)
        self.assertEqual(list(query.tuples()), [
            (1, 'n1', datetime.datetime(2019, 1, 1), 'published'),
            (2, 'n2', datetime.datetime(2019, 1, 2), 'draft'),
            (3, 'n3', datetime.datetime(2019, 1, 3), 'deleted')])


class TestModelSetTableName(BaseTestCase):
    def test_set_table_name(self):
        class Foo(TestModel):
            pass

        self.assertEqual(Foo._meta.table_name, 'foo')
        self.assertEqual(Foo._meta.table.__name__, 'foo')

        # Writing the attribute directly does not update the cached Table name.
        Foo._meta.table_name = 'foo2'
        self.assertEqual(Foo._meta.table.__name__, 'foo')

        # Use the helper-method.
        Foo._meta.set_table_name('foo3')
        self.assertEqual(Foo._meta.table.__name__, 'foo3')


class TestTruncateTable(ModelTestCase):
    requires = [User]

    def test_truncate_table(self):
        for i in range(3):
            User.create(username='u%s' % i)

        ctx = User._schema._truncate_table()
        if IS_SQLITE:
            self.assertSQL(ctx, 'DELETE FROM "users"', [])
        else:
            sql, _ = ctx.query()
            self.assertTrue(sql.startswith('TRUNCATE TABLE '))

        User.truncate_table()
        self.assertEqual(User.select().count(), 0)
