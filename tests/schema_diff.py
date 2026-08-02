import shutil
import tempfile

from peewee import *
from playhouse.migrations import Runner
from playhouse.migrations import template
from playhouse.schema_diff import IndexDiff
from playhouse.schema_diff import diff_models

from .base import IS_CRDB
from .base import IS_MYSQL
from .base import ModelTestCase
from .base import TestModel
from .base import requires_models
from .base import requires_sqlite
from .base import skip_if


class SdUser(TestModel):
    username = CharField(unique=True)
    email = CharField(index=True)

    class Meta:
        table_name = 'sd_user'


class SdTweet(TestModel):
    user = ForeignKeyField(SdUser, backref='tweets')
    content = TextField()
    flags = IntegerField(default=0)

    class Meta:
        table_name = 'sd_tweet'
        indexes = ((('user', 'flags'), False),)


class SdPoints(TestModel):
    user = ForeignKeyField(SdUser)
    key = CharField(max_length=32)

    class Meta:
        table_name = 'sd_points'
        primary_key = CompositeKey('user', 'key')


SD_MODELS = [SdUser, SdTweet, SdPoints]


class SdUser2(TestModel):
    # vs SdUser: email dropped, karma added, unique username index dropped,
    # composite (username, karma) index added.
    username = CharField()
    karma = IntegerField(default=0)

    class Meta:
        table_name = 'sd_user'
        indexes = ((('username', 'karma'), True),)


class SdNote(TestModel):
    user = ForeignKeyField(SdUser)
    content = TextField()

    class Meta:
        table_name = 'sd_note'


class SdPartial(TestModel):
    flags = IntegerField(default=0)

    class Meta:
        table_name = 'sd_partial'

SdPartial.add_index(SdPartial.flags, where=(SdPartial.flags > SQL('0')))


class SdDesc(TestModel):
    ts = IntegerField()

    class Meta:
        table_name = 'sd_desc'

SdDesc.add_index(SdDesc.ts.desc())


@skip_if(IS_CRDB, 'crdb introspection differs')
class TestSchemaDiff(ModelTestCase):
    requires = SD_MODELS

    def test_clean_schema(self):
        # Includes sd_points, whose composite-pk backing index must not
        # read as a change.
        diff = diff_models(self.database, SD_MODELS)
        self.assertFalse(diff)
        for part in diff:
            self.assertEqual(part, [])

    def test_column_add_drop(self):
        diff = diff_models(self.database, [SdUser2, SdTweet, SdPoints])
        self.assertEqual([f.column_name for f in diff.add_columns],
                         ['karma'])
        self.assertTrue(diff.add_columns[0].model is SdUser2)
        self.assertEqual(diff.drop_columns, [('sd_user', 'email')])

        # The email index and unique username index are no longer
        # declared. The composite is new.
        self.assertEqual(diff.add_indexes,
                         [IndexDiff('sd_user', None, ('username', 'karma'),
                                    True)])
        self.assertEqual(diff.drop_indexes,
                         [IndexDiff('sd_user', 'sd_user_email', ('email',),
                                    False),
                          IndexDiff('sd_user', 'sd_user_username',
                                    ('username',), True)])
        self.assertEqual(diff.create_tables, [])

    def test_create_tables_dependency_order(self):
        class SdReply(TestModel):
            note = ForeignKeyField(SdNote)

            class Meta:
                table_name = 'sd_reply'

        diff = diff_models(self.database, [SdReply, SdNote] + SD_MODELS)
        # Referenced tables sort ahead of referencing ones.
        self.assertEqual(diff.create_tables, [SdNote, SdReply])
        self.assertFalse(diff.add_columns or diff.drop_columns or
                         diff.add_indexes or diff.drop_indexes)

    def test_stray_index_dropped(self):
        if IS_MYSQL:  # Mysql requires a prefix length to index TEXT.
            self.database.execute_sql(
                'CREATE INDEX sd_extra ON sd_tweet (content(16))')
        else:
            self.database.execute_sql(
                'CREATE INDEX sd_extra ON sd_tweet (content)')

        diff = diff_models(self.database, SD_MODELS)
        self.assertEqual(diff.add_indexes, [])
        self.assertEqual(diff.drop_indexes,
                         [IndexDiff('sd_tweet', 'sd_extra', ('content',),
                                    False)])

    def test_unique_flag_mismatch(self):
        # Same columns but different uniqueness: reported as add + drop.
        if IS_MYSQL:
            self.database.execute_sql(
                'DROP INDEX sd_tweet_user_id_flags ON sd_tweet')
        else:
            self.database.execute_sql('DROP INDEX sd_tweet_user_id_flags')
        self.database.execute_sql(
            'CREATE UNIQUE INDEX sd_tweet_user_id_flags ON '
            'sd_tweet (user_id, flags)')

        diff = diff_models(self.database, SD_MODELS)
        self.assertEqual(diff.add_indexes,
                         [IndexDiff('sd_tweet', None, ('user_id', 'flags'),
                                    False)])
        self.assertEqual(diff.drop_indexes,
                         [IndexDiff('sd_tweet', 'sd_tweet_user_id_flags',
                                    ('user_id', 'flags'), True)])

    @requires_models(SdDesc)
    def test_descending_index(self):
        # The database reports the ts.desc() index as plain (ts) columns.
        # Pairing it by name keeps both sides from churning.
        self.assertFalse(diff_models(self.database, [SdDesc]))

    @requires_sqlite
    @requires_models(SdPartial)
    def test_partial_indexes_by_name(self):
        # Present on both sides: matched by name.
        self.assertFalse(diff_models(self.database, [SdPartial]))

        # Missing from the database: suggested by name, no details carried.
        self.database.execute_sql('DROP INDEX sd_partial_flags')
        diff = diff_models(self.database, [SdPartial])
        self.assertEqual(diff.add_indexes,
                         [IndexDiff('sd_partial', 'sd_partial_flags', None,
                                    None)])

        # In the database but not declared: suggested for removal.
        self.database.execute_sql(
            'CREATE INDEX sd_partial_flags ON sd_partial (flags) '
            'WHERE (flags > 0)')
        self.database.execute_sql(
            'CREATE INDEX sd_partial_stray ON sd_partial (flags) '
            'WHERE (flags < 0)')
        diff = diff_models(self.database, [SdPartial])
        self.assertEqual(diff.add_indexes, [])
        self.assertEqual(diff.drop_indexes,
                         [IndexDiff('sd_partial', 'sd_partial_stray', None,
                                    None)])

    def test_duplicate_table_name(self):
        # Two models on one table: the first wins, no drift reported.
        diff = diff_models(self.database, [SdUser, SdUser2])
        self.assertFalse(diff)

    def test_display(self):
        diff = diff_models(self.database, [SdUser2, SdNote, SdTweet,
                                           SdPoints])
        lines = str(diff).splitlines()
        self.assertEqual(lines[0], 'create table sd_note')
        self.assertIn('add column sd_user.karma', lines)
        self.assertIn('drop column sd_user.email', lines)
        self.assertIn('add index sd_user (username, karma) unique', lines)
        self.assertIn('drop index sd_user.sd_user_email (email)', lines)

    @requires_sqlite
    def test_virtual_models_skipped(self):
        try:
            from playhouse.sqlite_ext import FTS5Model, SearchField
        except ImportError:
            return self.skipTest('sqlite_ext unavailable')

        class SdIdx(FTS5Model):
            content = SearchField()

            class Meta:
                database = self.database

        if not SdIdx.fts5_installed():
            return self.skipTest('fts5 unavailable')
        self.database.create_tables([SdIdx])
        try:
            self.assertFalse(diff_models(self.database, [SdIdx] + SD_MODELS))
        finally:
            self.database.drop_tables([SdIdx])


@skip_if(IS_CRDB, 'crdb introspection differs')
class TestTemplate(ModelTestCase):
    requires = SD_MODELS

    def test_body(self):
        body = template(diff_models(self.database,
                                    [SdUser2, SdNote, SdTweet, SdPoints]))
        # New table: inline skeleton with fk placeholder, boolean flags.
        self.assertIn('class SdNote(Model):', body)
        self.assertIn('    user = ForeignKeyField(...)', body)
        self.assertIn('    content = TextField()', body)
        self.assertIn('db.create_tables([SdNote])', body)
        # Added column: class name with placeholder args.
        self.assertIn("add_column('sd_user', 'karma', IntegerField(...))",
                      body)
        # Fully-determined operations render runnable, drops active.
        self.assertIn("add_index('sd_user', ('username', 'karma'), "
                      "unique=True", body)
        self.assertIn("drop_column('sd_user', 'email')", body)
        self.assertIn("drop_index('sd_user', 'sd_user_email')", body)
        # down() holds the certain inverses only: the new table and unique
        # username index come back, the dropped email column cannot.
        self.assertIn("drop_column('sd_user', 'karma')", body)
        self.assertIn("migrator.migrate(migrator.drop_table('sd_note'))",
                      body)
        self.assertIn("add_index('sd_user', ('username',), unique=True)",
                      body)
        self.assertIn('# TODO: sd_user.email: dropped column cannot be '
                      'restored by down()', body)
        self.assertIn('sd_user_email cannot be restored by down() '
                      '(column dropped)', body)

    def test_fk_placeholder_alias(self):
        # A non-default fk column name must survive into the placeholder.
        class SdOwned(TestModel):
            owner = ForeignKeyField(SdUser, column_name='owner')
            label = CharField()

            class Meta:
                table_name = 'sd_owned'

        body = template(diff_models(self.database, [SdOwned] + SD_MODELS))
        self.assertIn("owner = ForeignKeyField(..., column_name='owner')",
                      body)

    def test_added_fk_flags(self):
        # unique/null render in an added-fk placeholder. index=True, the
        # fk default, stays out: add_column() indexes the column itself.
        class SdTweetFks(TestModel):
            user = ForeignKeyField(SdUser, backref='tweets')
            content = TextField()
            flags = IntegerField(default=0)
            editor = ForeignKeyField(SdUser, backref='edits', unique=True,
                                     null=True)
            parent = ForeignKeyField('self', null=True)

            class Meta:
                table_name = 'sd_tweet'
                indexes = ((('user', 'flags'), False),)

        body = template(diff_models(self.database,
                                    [SdTweetFks, SdUser, SdPoints]))
        self.assertIn("add_column('sd_tweet', 'editor_id', "
                      "ForeignKeyField(..., unique=True, null=True))", body)
        self.assertIn("add_column('sd_tweet', 'parent_id', "
                      "ForeignKeyField(..., null=True))", body)
        self.assertNotIn('index=True', body)

    @requires_sqlite
    @requires_models(SdPartial)
    def test_partial_index_todo(self):
        # The declaration is known by name only, so up() stays empty.
        self.database.execute_sql('DROP INDEX sd_partial_flags')
        body = template(diff_models(self.database, [SdPartial]))
        self.assertIn('# TODO: sd_partial: create index sd_partial_flags '
                      '(partial/expression, details not detected)', body)
        self.assertIn('def up(migrator, db):\n    pass', body)

    @requires_sqlite
    def test_schema_rendered(self):
        self.database.execute_sql("ATTACH ':memory:' AS aux")

        class SdAux(TestModel):
            label = CharField()

            class Meta:
                table_name = 'sd_aux'
                schema = 'aux'

        body = template(diff_models(self.database, [SdAux]))
        self.assertIn("schema = 'aux'", body)
        self.assertIn("drop_table('sd_aux', schema='aux')", body)


# What a user writes after filling in the fk placeholders rendered for the
# SdProfile model below: a frozen stub for the target plus the real flags.
FK_FLAGS_MIG = """\
from peewee import *

def up(migrator, db):
    class SdUserStub(Model):
        class Meta:
            database = db
            table_name = 'sd_user'

    class SdProfile(Model):
        user = ForeignKeyField(SdUserStub, backref='profiles', unique=True)
        editor = ForeignKeyField(SdUserStub, backref='edited', null=True)

        class Meta:
            database = db
            table_name = 'sd_profile'

    db.create_tables([SdProfile])

def down(migrator, db):
    migrator.migrate(migrator.drop_table('sd_profile'))
"""


@skip_if(IS_CRDB, 'crdb introspection differs')
class TestTemplateRoundTrip(ModelTestCase):
    requires = SD_MODELS

    def setUp(self):
        super(TestTemplateRoundTrip, self).setUp()
        self.dir = tempfile.mkdtemp()
        self.runner = Runner(self.database, self.dir)

    def tearDown(self):
        try:
            shutil.rmtree(self.dir, ignore_errors=True)
            self.database.drop_tables([self.runner.History], safe=True)
            for table in ('sd_tag', 'sd_sku', 'sd_profile', 'sd_alias',
                          'sd_kv'):
                self.database.execute_sql('DROP TABLE IF EXISTS %s' % table)
        finally:
            super(TestTemplateRoundTrip, self).tearDown()
            self.database.close()

    def apply(self, body, name):
        self.runner.create(name, body=body)
        self.assertEqual(self.runner.up(), ['0001_%s' % name])

    def test_round_trip(self):
        # A diff with no fk placeholders is fully runnable as generated:
        # new table, index changes, column drop.
        class SdUser3(TestModel):
            username = CharField(unique=True)

            class Meta:
                table_name = 'sd_user'

        class SdTag(TestModel):
            label = CharField(unique=True)
            position = IntegerField(index=True)

            class Meta:
                table_name = 'sd_tag'
                indexes = ((('label', 'position'), False),)

        models = [SdUser3, SdTag, SdTweet, SdPoints]
        body = template(diff_models(self.database, models))
        self.assertNotIn('(...)', body)

        self.apply(body, 'auto')
        self.assertFalse(diff_models(self.database, models))

        # down() reverts the certain subset: the dropped email column and
        # its index stay gone, everything else returns.
        self.assertEqual(self.runner.down(), ['0001_auto'])
        diff = diff_models(self.database, models)
        self.assertEqual([m.__name__ for m in diff.create_tables],
                         ['SdTag'])
        self.assertFalse(diff.add_columns or diff.drop_columns or
                         diff.drop_indexes)

    def test_field_params(self):
        # Ddl-affecting values (length, precision) are rendered and class
        # defaults are omitted.
        class SdSku(TestModel):
            code = CharField(max_length=32, unique=True)
            price = DecimalField(max_digits=12, decimal_places=2)
            label = CharField()

            class Meta:
                table_name = 'sd_sku'

        body = template(diff_models(self.database, [SdSku] + SD_MODELS))
        self.assertIn('code = CharField(max_length=32, unique=True)', body)
        self.assertIn('price = DecimalField(max_digits=12, '
                      'decimal_places=2)', body)
        self.assertIn('label = CharField()', body)

        self.apply(body, 'sku')
        self.assertFalse(diff_models(self.database, [SdSku] + SD_MODELS))

    def test_unique_flip(self):
        # unique=True -> index=True re-uses the index name. The drop must
        # precede the add or every backend errors.
        class SdUserFlip(TestModel):
            username = CharField(index=True)
            email = CharField(index=True)

            class Meta:
                table_name = 'sd_user'

        models = [SdUserFlip, SdTweet, SdPoints]
        body = template(diff_models(self.database, models))
        self.assertTrue(
            body.index("drop_index('sd_user', 'sd_user_username')") <
            body.index("add_index('sd_user', ('username',))"))

        self.apply(body, 'flip')
        self.assertFalse(diff_models(self.database, models))
        # And the reverse flip on the way down.
        self.assertEqual(self.runner.down(), ['0001_flip'])
        self.assertFalse(diff_models(self.database, SD_MODELS))

    def test_added_indexed_column(self):
        # add_column() creates the field's index itself, so up() carries
        # no separate add_index. down() must still drop the index before
        # the column or sqlite refuses the drop.
        class SdUserKarma(TestModel):
            username = CharField(unique=True)
            email = CharField(index=True)
            karma = IntegerField(index=True)

            class Meta:
                table_name = 'sd_user'

        models = [SdUserKarma, SdTweet, SdPoints]
        body = template(diff_models(self.database, models))
        self.assertIn("add_column('sd_user', 'karma', "
                      "IntegerField(..., index=True))", body)
        self.assertNotIn("add_index('sd_user', ('karma',)", body)
        self.assertTrue(
            body.index("drop_index('sd_user', 'sd_user_karma')") <
            body.index("drop_column('sd_user', 'karma')"))

        # Fill in the placeholder the way a user would.
        body = body.replace('IntegerField(..., index=True)',
                            'IntegerField(default=0, index=True)')
        self.apply(body, 'karma')
        self.assertFalse(diff_models(self.database, models))
        self.assertEqual(self.runner.down(), ['0001_karma'])
        self.assertFalse(diff_models(self.database, SD_MODELS))

    def test_fk_flags(self):
        # unique/null on an fk placeholder: without them the created table
        # never converges (unique) or silently comes out NOT NULL (null).
        class SdProfile(TestModel):
            user = ForeignKeyField(SdUser, backref='profiles', unique=True)
            editor = ForeignKeyField(SdUser, backref='edited', null=True)

            class Meta:
                table_name = 'sd_profile'

        models = [SdProfile] + SD_MODELS
        body = template(diff_models(self.database, models))
        self.assertIn('user = ForeignKeyField(..., unique=True)', body)
        self.assertIn('editor = ForeignKeyField(..., null=True)', body)

        self.apply(FK_FLAGS_MIG, 'profile')
        self.assertFalse(diff_models(self.database, models))
        columns = {c.name: c
                   for c in self.database.get_columns('sd_profile')}
        self.assertTrue(columns['editor_id'].null)
        self.assertFalse(columns['user_id'].null)
        self.assertEqual(self.runner.down(), ['0001_profile'])

    def test_autofield_alias(self):
        class SdAlias(TestModel):
            id = AutoField(column_name='object_id')
            label = CharField()

            class Meta:
                table_name = 'sd_alias'

        models = [SdAlias] + SD_MODELS
        body = template(diff_models(self.database, models))
        self.assertIn("id = AutoField(column_name='object_id')", body)

        self.apply(body, 'alias')
        self.assertFalse(diff_models(self.database, models))

    def test_non_auto_pk(self):
        # primary_key=True must render exactly once or the generated file
        # is a SyntaxError (keyword argument repeated).
        class SdKV(TestModel):
            key = CharField(max_length=32, primary_key=True)
            value = TextField()

            class Meta:
                table_name = 'sd_kv'

        models = [SdKV] + SD_MODELS
        body = template(diff_models(self.database, models))
        self.assertIn('key = CharField(max_length=32, primary_key=True)',
                      body)

        self.apply(body, 'kv')
        self.assertFalse(diff_models(self.database, models))
