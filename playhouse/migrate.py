"""
Lightweight schema migrations.

NOTE: Currently tested with SQLite and Postgresql. MySQL may be missing some
features.

Example Usage
-------------

Instantiate a migrator:

    # Postgres example:
    my_db = PostgresqlDatabase(...)
    migrator = PostgresqlMigrator(my_db)

    # SQLite example:
    my_db = SqliteDatabase('my_database.db')
    migrator = SqliteMigrator(my_db)

Then you will use the `migrate` function to run various `Operation`s which
are generated by the migrator:

    migrate(
        migrator.add_column('some_table', 'column_name', CharField(default=''))
    )

Migrations are not run inside a transaction, so if you wish the migration to
run in a transaction you will need to wrap the call to `migrate` in a
transaction block, e.g.:

    with my_db.transaction():
        migrate(...)

Supported Operations
--------------------

Add new field(s) to an existing model:

    # Create your field instances. For non-null fields you must specify a
    # default value.
    pubdate_field = DateTimeField(null=True)
    comment_field = TextField(default='')

    # Run the migration, specifying the database table, field name and field.
    migrate(
        migrator.add_column('comment_tbl', 'pub_date', pubdate_field),
        migrator.add_column('comment_tbl', 'comment', comment_field),
    )

Renaming a field:

    # Specify the table, original name of the column, and its new name.
    migrate(
        migrator.rename_column('story', 'pub_date', 'publish_date'),
        migrator.rename_column('story', 'mod_date', 'modified_date'),
    )

Dropping a field:

    migrate(
        migrator.drop_column('story', 'some_old_field'),
    )

Making a field nullable or not nullable:

    # Note that when making a field not null that field must not have any
    # NULL values present.
    migrate(
        # Make `pub_date` allow NULL values.
        migrator.drop_not_null('story', 'pub_date'),

        # Prevent `modified_date` from containing NULL values.
        migrator.add_not_null('story', 'modified_date'),
    )

Renaming a table:

    migrate(
        migrator.rename_table('story', 'stories_tbl'),
    )

Adding an index:

    # Specify the table, column names, and whether the index should be
    # UNIQUE or not.
    migrate(
        # Create an index on the `pub_date` column.
        migrator.add_index('story', ('pub_date',), False),

        # Create a multi-column index on the `pub_date` and `status` fields.
        migrator.add_index('story', ('pub_date', 'status'), False),

        # Create a unique index on the category and title fields.
        migrator.add_index('story', ('category_id', 'title'), True),
    )

Dropping an index:

    # Specify the index name.
    migrate(migrator.drop_index('story', 'story_pub_date_status'))
"""
from collections import namedtuple
import functools
import re

from peewee import *
from peewee import CommaClause
from peewee import EnclosedClause
from peewee import Entity
from peewee import Expression
from peewee import Node
from peewee import OP


class Operation(object):
    """Encapsulate a single schema altering operation."""

    def __init__(self, migrator, method, *args, **kwargs):
        self.migrator = migrator
        self.method = method
        self.args = args
        self.kwargs = kwargs

    def _parse_node(self, node):
        compiler = self.migrator.database.compiler()
        return compiler.parse_node(node)

    def execute(self, node):
        sql, params = self._parse_node(node)
        self.migrator.database.execute_sql(sql, params)

    def _handle_result(self, result):
        if isinstance(result, Node):
            self.execute(result)
        elif isinstance(result, Operation):
            result.run()
        elif isinstance(result, (list, tuple)):
            for item in result:
                self._handle_result(item)

    def run(self):
        kwargs = self.kwargs.copy()
        kwargs['generate'] = True
        self._handle_result(
            getattr(self.migrator, self.method)(*self.args, **kwargs))


def operation(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        generate = kwargs.pop('generate', False)
        if generate:
            return fn(self, *args, **kwargs)
        return Operation(self, fn.__name__, *args, **kwargs)
    return inner


class SchemaMigrator(object):
    explicit_create_foreign_key = False
    explicit_delete_foreign_key = False

    def __init__(self, database):
        self.database = database

    @classmethod
    def from_database(cls, database):
        if isinstance(database, PostgresqlDatabase):
            return PostgresqlMigrator(database)
        elif isinstance(database, MySQLDatabase):
            return MySQLMigrator(database)
        else:
            return SqliteMigrator(database)

    @operation
    def apply_default(self, table, column_name, field):
        default = field.default
        if callable(default):
            default = default()

        return Clause(
            SQL('UPDATE'),
            Entity(table),
            SQL('SET'),
            Expression(
                Entity(column_name),
                OP.EQ,
                Param(field.db_value(default)),
                flat=True))

    @operation
    def alter_add_column(self, table, column_name, field):
        # Make field null at first.
        field_null, field.null = field.null, True
        field.name = field.db_column = column_name
        field_clause = self.database.compiler().field_definition(field)
        field.null = field_null
        parts = [
            SQL('ALTER TABLE'),
            Entity(table),
            SQL('ADD COLUMN'),
            field_clause]
        if isinstance(field, ForeignKeyField):
            parts.extend(self.get_inline_fk_sql(field))
        return Clause(*parts)

    def get_inline_fk_sql(self, field):
        return [
            SQL('REFERENCES'),
            Entity(field.rel_model._meta.db_table),
            EnclosedClause(Entity(field.to_field.db_column))
        ]

    @operation
    def add_foreign_key_constraint(self, table, column_name, field):
        raise NotImplementedError

    @operation
    def add_column(self, table, column_name, field):
        # Adding a column is complicated by the fact that if there are rows
        # present and the field is non-null, then we need to first add the
        # column as a nullable field, then set the value, then add a not null
        # constraint.
        if not field.null and field.default is None:
            raise ValueError('%s is not null but has no default' % column_name)

        is_foreign_key = isinstance(field, ForeignKeyField)

        # Foreign key fields must explicitly specify a `to_field`.
        if is_foreign_key and not field.to_field:
            raise ValueError('Foreign keys must specify a `to_field`.')

        operations = [self.alter_add_column(table, column_name, field)]

        # In the event the field is *not* nullable, update with the default
        # value and set not null.
        if not field.null:
            operations.extend([
                self.apply_default(table, column_name, field),
                self.add_not_null(table, column_name)])

        if is_foreign_key and self.explicit_create_foreign_key:
            operations.append(
                self.add_foreign_key_constraint(
                    table,
                    column_name,
                    field.rel_model._meta.db_table,
                    field.to_field.db_column))

        if field.index or field.unique:
            operations.append(
                self.add_index(table, (column_name,), field.unique))

        return operations

    @operation
    def drop_foreign_key_constraint(self, table, column_name):
        raise NotImplementedError

    @operation
    def drop_column(self, table, column_name, cascade=True):
        nodes = [
            SQL('ALTER TABLE'),
            Entity(table),
            SQL('DROP COLUMN'),
            Entity(column_name)]
        if cascade:
            nodes.append(SQL('CASCADE'))
        drop_column_node = Clause(*nodes)
        fk_columns = [
            foreign_key.column
            for foreign_key in self.database.get_foreign_keys(table)]
        if column_name in fk_columns and self.explicit_delete_foreign_key:
            return [
                self.drop_foreign_key_constraint(table, column_name),
                drop_column_node]
        else:
            return drop_column_node

    @operation
    def rename_column(self, table, old_name, new_name):
        return Clause(
            SQL('ALTER TABLE'),
            Entity(table),
            SQL('RENAME COLUMN'),
            Entity(old_name),
            SQL('TO'),
            Entity(new_name))

    def _alter_column(self, table, column):
        return [
            SQL('ALTER TABLE'),
            Entity(table),
            SQL('ALTER COLUMN'),
            Entity(column)]

    @operation
    def add_not_null(self, table, column):
        nodes = self._alter_column(table, column)
        nodes.append(SQL('SET NOT NULL'))
        return Clause(*nodes)

    @operation
    def drop_not_null(self, table, column):
        nodes = self._alter_column(table, column)
        nodes.append(SQL('DROP NOT NULL'))
        return Clause(*nodes)

    @operation
    def rename_table(self, old_name, new_name):
        return Clause(
            SQL('ALTER TABLE'),
            Entity(old_name),
            SQL('RENAME TO'),
            Entity(new_name))

    @operation
    def add_index(self, table, columns, unique=False):
        compiler = self.database.compiler()
        statement = 'CREATE UNIQUE INDEX' if unique else 'CREATE INDEX'
        return Clause(
            SQL(statement),
            Entity(compiler.index_name(table, columns)),
            SQL('ON'),
            Entity(table),
            EnclosedClause(*[Entity(column) for column in columns]))

    @operation
    def drop_index(self, table, index_name):
        return Clause(
            SQL('DROP INDEX'),
            Entity(index_name))


class PostgresqlMigrator(SchemaMigrator):
    def _primary_key_columns(self, tbl):
        query = """
            SELECT pg_attribute.attname
            FROM pg_index, pg_class, pg_attribute
            WHERE
                pg_class.oid = '%s'::regclass AND
                indrelid = pg_class.oid AND
                pg_attribute.attrelid = pg_class.oid AND
                pg_attribute.attnum = any(pg_index.indkey) AND
                indisprimary;
        """
        cursor = self.database.execute_sql(query % tbl)
        return [row[0] for row in cursor.fetchall()]

    @operation
    def rename_table(self, old_name, new_name):
        pk_names = self._primary_key_columns(old_name)
        ParentClass = super(PostgresqlMigrator, self)

        operations = [
            ParentClass.rename_table(old_name, new_name, generate=True)]

        if len(pk_names) == 1:
            # Check for existence of primary key sequence.
            seq_name = '%s_%s_seq' % (old_name, pk_names[0])
            query = """
                SELECT 1
                FROM information_schema.sequences
                WHERE LOWER(sequence_name) = LOWER(%s)
            """
            cursor = self.database.execute_sql(query, (seq_name,))
            if bool(cursor.fetchone()):
                new_seq_name = '%s_%s_seq' % (new_name, pk_names[0])
                operations.append(ParentClass.rename_table(
                    seq_name, new_seq_name, generate=True))

        return operations

_column_attributes = ('name', 'definition', 'null', 'pk', 'default', 'extra')


class MySQLColumn(namedtuple('_Column', _column_attributes)):
    @property
    def is_pk(self):
        return self.pk == 'PRI'

    @property
    def is_unique(self):
        return self.pk == 'UNI'

    @property
    def is_null(self):
        return self.null == 'YES'

    def sql(self, column_name=None, is_null=None):
        if is_null is None:
            is_null = self.is_null
        if column_name is None:
            column_name = self.name
        parts = [
            Entity(column_name),
            SQL(self.definition)]
        if self.is_unique:
            parts.append(SQL('UNIQUE'))
        if is_null:
            parts.append(SQL('NULL'))
        else:
            parts.append(SQL('NOT NULL'))
        if self.is_pk:
            parts.append(SQL('PRIMARY KEY'))
        if self.extra:
            parts.append(SQL(self.extra))
        return Clause(*parts)


class MySQLMigrator(SchemaMigrator):
    explicit_create_foreign_key = True
    explicit_delete_foreign_key = True

    @operation
    def rename_table(self, old_name, new_name):
        return Clause(
            SQL('RENAME TABLE'),
            Entity(old_name),
            SQL('TO'),
            Entity(new_name))

    def _get_column_definition(self, table, column_name):
        cursor = self.database.execute_sql('DESCRIBE %s;' % table)
        rows = cursor.fetchall()
        for row in rows:
            column = MySQLColumn(*row)
            if column.name == column_name:
                return column
        return False

    def _add_restrict_foreign_key_constraint(
            self, table, column_name, rel, rel_column):
        constraint = 'fk_%s_%s_refs_%s' % (table, column_name, rel)
        return [
            SQL('ALTER TABLE'),
            Entity(table),
            SQL('ADD CONSTRAINT'),
            Entity(constraint),
            SQL('FOREIGN KEY'),
            EnclosedClause(Entity(column_name)),
            SQL('REFERENCES'),
            Entity(rel),
            EnclosedClause(Entity(rel_column))]

    @operation
    def add_foreign_key_constraint(
            self, table, column_name, rel, rel_column, on_delete='RESTRICT', on_update='RESTRICT'):
        # TODO: refactor, this duplicates QueryCompiler._create_foreign_key
        nodes = self._add_restrict_foreign_key_constraint(
            table, column_name, rel, rel_column)
        if on_delete == 'CASCADE' and on_update == 'RESTRICT':
            nodes.append(SQL('ON DELETE CASCADE ON UPDATE RESTRICT'))
            return Clause(*nodes)
        elif on_update == 'CASCADE' and on_delete == 'RESTRICT':
            nodes.append(SQL('ON DELETE RESTRICT ON UPDATE CASCADE'))
        elif on_delete == 'CASCADE' and on_update == 'CASCADE':
            nodes.append(SQL('ON DELETE CASCADE ON UPDATE CASCADE'))
        else:
            nodes.append(SQL('ON DELETE RESTRICT ON UPDATE RESTRICT'))
        return Clause(*nodes)

    def get_foreign_key_constraint(self, table, column_name):
        cursor = self.database.execute_sql(
            ('SELECT constraint_name '
             'FROM information_schema.key_column_usage '
             'WHERE table_name="%s" AND '
             'constraint_schema="%s" AND '
             'column_name="%s"')
            % (table, self.database.database, column_name))
        result = cursor.fetchone()
        if not result:
            raise AttributeError(
                'Unable to find foreign key constraint for '
                '"%s" on table "%s" %s.' % (column_name, table, result))
        return result[0]

    @operation
    def drop_foreign_key_constraint(self, table, column_name):
        foreign_key = self.get_foreign_key_constraint(table, column_name)
        if foreign_key is not None:
            return Clause(
                SQL('ALTER TABLE'),
                Entity(table),
                SQL('DROP FOREIGN KEY'),
                Entity(foreign_key))

    def get_inline_fk_sql(self, field):
        return []

    @operation
    def add_not_null(self, table, column):
        column = self._get_column_definition(table, column)
        return Clause(
            SQL('ALTER TABLE'),
            Entity(table),
            SQL('MODIFY'),
            column.sql(is_null=False))

    @operation
    def drop_not_null(self, table, column):
        column = self._get_column_definition(table, column)
        if column.is_pk:
            raise ValueError('Primary keys can not be null')
        return Clause(
            SQL('ALTER TABLE'),
            Entity(table),
            SQL('MODIFY'),
            column.sql(is_null=True))

    @operation
    def rename_column(
            self, table, old_name, new_name, on_delete='RESTRICT', on_update='RESTRICT'):
        fk_objects = dict(
            (fk.column, fk)
            for fk in self.database.get_foreign_keys(table))
        is_foreign_key = old_name in fk_objects

        column = self._get_column_definition(table, old_name)
        rename_clause = Clause(
            SQL('ALTER TABLE'),
            Entity(table),
            SQL('CHANGE'),
            Entity(old_name),
            column.sql(column_name=new_name))
        if is_foreign_key:
            fk_metadata = fk_objects[old_name]
            return [
                self.drop_foreign_key_constraint(table, old_name),
                rename_clause,
                self.add_foreign_key_constraint(
                    table,
                    new_name,
                    fk_metadata.dest_table,
                    fk_metadata.dest_column,
                    on_delete,
                    on_update),
            ]
        else:
            return rename_clause

    @operation
    def drop_index(self, table, index_name):
        return Clause(
            SQL('DROP INDEX'),
            Entity(index_name),
            SQL('ON'),
            Entity(table))


class SqliteMigrator(SchemaMigrator):
    """
    SQLite supports a subset of ALTER TABLE queries, view the docs for the
    full details http://sqlite.org/lang_altertable.html
    """
    column_re = re.compile('(.+?)\((.+)\)')
    column_split_re = re.compile(r'(?:[^,(]|\([^)]*\))+')
    column_name_re = re.compile('["`\']?([\w]+)')
    fk_re = re.compile('FOREIGN KEY\s+\("?([\w]+)"?\)\s+', re.I)

    def _get_column_names(self, table):
        res = self.database.execute_sql('select * from "%s" limit 1' % table)
        return [item[0] for item in res.description]

    def _get_create_table(self, table):
        res = self.database.execute_sql(
            ('select name, sql from sqlite_master '
             'where type=? and LOWER(name)=?'),
            ['table', table.lower()])
        return res.fetchone()

    @operation
    def _update_column(self, table, column_to_update, fn):
        columns = set(column.name.lower()
                      for column in self.database.get_columns(table))
        if column_to_update.lower() not in columns:
            raise ValueError('Column "%s" does not exist on "%s"' %
                             (column_to_update, table))

        # Get the SQL used to create the given table.
        table, create_table = self._get_create_table(table)

        # Get the indexes and SQL to re-create indexes.
        indexes = self.database.get_indexes(table)

        # Find any foreign keys we may need to remove.
        self.database.get_foreign_keys(table)

        # Make sure the create_table does not contain any newlines or tabs,
        # allowing the regex to work correctly.
        create_table = re.sub(r'\s+', ' ', create_table)

        # Parse out the `CREATE TABLE` and column list portions of the query.
        raw_create, raw_columns = self.column_re.search(create_table).groups()

        # Clean up the individual column definitions.
        split_columns = self.column_split_re.findall(raw_columns)
        column_defs = [col.strip() for col in split_columns]

        new_column_defs = []
        new_column_names = []
        original_column_names = []

        for column_def in column_defs:
            column_name, = self.column_name_re.match(column_def).groups()

            if column_name == column_to_update:
                new_column_def = fn(column_name, column_def)
                if new_column_def:
                    new_column_defs.append(new_column_def)
                    original_column_names.append(column_name)
                    column_name, = self.column_name_re.match(
                        new_column_def).groups()
                    new_column_names.append(column_name)
            else:
                new_column_defs.append(column_def)
                if not column_name.lower().startswith(('foreign', 'primary')):
                    new_column_names.append(column_name)
                    original_column_names.append(column_name)

        # Create a mapping of original columns to new columns.
        original_to_new = dict(zip(original_column_names, new_column_names))
        new_column = original_to_new.get(column_to_update)

        fk_filter_fn = lambda column_def: column_def
        if not new_column:
            # Remove any foreign keys associated with this column.
            fk_filter_fn = lambda column_def: None
        elif new_column != column_to_update:
            # Update any foreign keys for this column.
            fk_filter_fn = lambda column_def: self.fk_re.sub(
                'FOREIGN KEY ("%s") ' % new_column,
                column_def)

        cleaned_columns = []
        for column_def in new_column_defs:
            match = self.fk_re.match(column_def)
            if match is not None and match.groups()[0] == column_to_update:
                column_def = fk_filter_fn(column_def)
            if column_def:
                cleaned_columns.append(column_def)

        # Update the name of the new CREATE TABLE query.
        temp_table = table + '__tmp__'
        rgx = re.compile('("?)%s("?)' % table, re.I)
        create = rgx.sub(
            '\\1%s\\2' % temp_table,
            raw_create)

        # Create the new table.
        columns = ', '.join(cleaned_columns)
        queries = [
            Clause(SQL('DROP TABLE IF EXISTS'), Entity(temp_table)),
            SQL('%s (%s)' % (create.strip(), columns))]

        # Populate new table.
        populate_table = Clause(
            SQL('INSERT INTO'),
            Entity(temp_table),
            EnclosedClause(*[Entity(col) for col in new_column_names]),
            SQL('SELECT'),
            CommaClause(*[Entity(col) for col in original_column_names]),
            SQL('FROM'),
            Entity(table))
        queries.append(populate_table)

        # Drop existing table and rename temp table.
        queries.append(Clause(
            SQL('DROP TABLE'),
            Entity(table)))
        queries.append(self.rename_table(temp_table, table))

        # Re-create user-defined indexes. User-defined indexes will have a
        # non-empty SQL attribute.
        for index in filter(lambda idx: idx.sql, indexes):
            if column_to_update not in index.columns:
                queries.append(SQL(index.sql))
            elif new_column:
                sql = self._fix_index(index.sql, column_to_update, new_column)
                if sql is not None:
                    queries.append(SQL(sql))

        return queries

    def _fix_index(self, sql, column_to_update, new_column):
        # Split on the name of the column to update. If it splits into two
        # pieces, then there's no ambiguity and we can simply replace the
        # old with the new.
        parts = sql.split(column_to_update)
        if len(parts) == 2:
            return sql.replace(column_to_update, new_column)

        # Find the list of columns in the index expression.
        lhs, rhs = sql.rsplit('(', 1)

        # Apply the same "split in two" logic to the column list portion of
        # the query.
        if len(rhs.split(column_to_update)) == 2:
            return '%s(%s' % (lhs, rhs.replace(column_to_update, new_column))

        # Strip off the trailing parentheses and go through each column.
        parts = rhs.rsplit(')', 1)[0].split(',')
        columns = [part.strip('"`[]\' ') for part in parts]

        # `columns` looks something like: ['status', 'timestamp" DESC']
        # https://www.sqlite.org/lang_keywords.html
        # Strip out any junk after the column name.
        clean = []
        for column in columns:
            if re.match('%s(?:[\'"`\]]?\s|$)' % column_to_update, column):
                column = new_columne + column[len(column_to_update):]
            clean.append(column)

        return '%s(%s)' % (lhs, ', '.join('"%s"' % c for c in clean))

    @operation
    def drop_column(self, table, column_name, cascade=True):
        return self._update_column(table, column_name, lambda a, b: None)

    @operation
    def rename_column(self, table, old_name, new_name):
        def _rename(column_name, column_def):
            return column_def.replace(column_name, new_name)
        return self._update_column(table, old_name, _rename)

    @operation
    def add_not_null(self, table, column):
        def _add_not_null(column_name, column_def):
            return column_def + ' NOT NULL'
        return self._update_column(table, column, _add_not_null)

    @operation
    def drop_not_null(self, table, column):
        def _drop_not_null(column_name, column_def):
            return column_def.replace('NOT NULL', '')
        return self._update_column(table, column, _drop_not_null)


def migrate(*operations, **kwargs):
    for operation in operations:
        operation.run()
