"""
Lightweight schema migrations, currently only support for Postgresql.

Example Usage
-------------

Instantiate a migrator:

    my_db = PostgresqlDatabase(...)
    migrator = Migrator(my_db)

Adding a field to a model:

    # declare a field instance
    new_pubdate_field = DateTimeField(null=True)

    # in a transaction, add the column to your model
    with my_db.transaction():
        migrator.add_column(Story, new_pubdate_field, 'pub_date')

Renaming a field:

    # specify the original name of the field and its new name
    with my_db.transaction():
        migrator.rename_column(Story, 'pub_date', 'publish_date')

Dropping a field:

   # specify the field name to drop
   with my_db.transaction():
       migrator.drop_column(Story, 'some_old_field')

Setting nullable / not nullable

    with my_db.transaction():
        # make pubdate not nullable
        migrator.set_nullable(Story, Story.pub_date, False)

Renaming a table

    with my_db.transaction():
        migrator.rename_table(Story, 'stories')
"""
import re

from peewee import *
from peewee import CommaClause
from peewee import EnclosedClause
from peewee import Entity
from peewee import Expression
from peewee import OP_EQ


class SchemaMigrator(object):
    def __init__(self, database):
        self.database = database

    def add_column(self, table, column_name, field):
        if not field.null and field.default is None:
            raise ValueError('%s is not null but has no default' % column_name)

        clauses = []

        # Make field null at first.
        field_null, field.null = field.null, True
        field.name = field.db_column = column_name
        field_clause = self.database.compiler().field_definition(field)
        clauses.append(Clause(
            SQL('ALTER TABLE'),
            Entity(table),
            SQL('ADD COLUMN'),
            field_clause))

        # In the event the field is *not* nullable, update with the default
        # value and set not null.
        if not field_null:
            default = field.default
            if callable(default):
                default = default()

            clauses.append(Clause(
                SQL('UPDATE'),
                Entity(table),
                SQL('SET'),
                Expression(
                    Entity(column_name),
                    OP_EQ,
                    Param(field.db_value(default)),
                    flat=True)))

            clauses.append(self.add_not_null(table, column_name))

        return clauses

    def drop_column(self, table, column_name, cascade=True):
        nodes = [
            SQL('ALTER TABLE'),
            Entity(table),
            SQL('DROP COLUMN'),
            Entity(column_name)]
        if cascade:
            nodes.append(SQL('CASCADE'))
        return Clause(*nodes)

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

    def add_not_null(self, table, column):
        nodes = self._alter_column(table, column)
        nodes.append(SQL('SET NOT NULL'))
        return Clause(*nodes)

    def drop_not_null(self, table, column):
        nodes = self._alter_column(table, column)
        nodes.append(SQL('DROP NOT NULL'))
        return Clause(*nodes)

    def rename_table(self, old_name, new_name):
        return Clause(
            SQL('ALTER TABLE'),
            Entity(old_name),
            SQL('RENAME TO'),
            Entity(new_name))

    def add_index(self, table, columns, unique=False):
        compiler = database.compiler()
        statement = 'CREATE UNIQUE INDEX' if unique else 'CREATE INDEX'
        return Clause(
            SQL(statement),
            Entity(compiler.index_name(table, columns)),
            SQL('ON'),
            Entity(table),
            EnclosedClause(*columns))

    def drop_index(self, table, index_name):
        return Clause(
            SQL('DROP INDEX'),
            Entity(index_name))


class PostgresqlMigrator(SchemaMigrator):
    pass


class MySQLMigrator(SchemaMigrator):
    def rename_column(self, table, old_name, new_name):
        raise NotImplementedError


class SqliteMigrator(SchemaMigrator):
    """
    SQLite supports a subset of ALTER TABLE queries, view the docs for the
    full details http://sqlite.org/lang_altertable.html
    """
    column_re = re.compile('(.+?)\((.+)\)')
    column_split_re = re.compile(r'(?:[^,(]|\([^)]*\))+')
    column_name_re = re.compile('"?([\w]+)')

    def _get_column_names(self, table):
        res = self.database.execute_sql('select * from "%s" limit 1' % table)
        return [item[0] for item in res.description]

    def _get_create_table(self, table):
        res = self.database.execute_sql(
            'select sql from sqlite_master where type=? and name=? limit 1',
            ['table', table])
        return res.fetchone()[0]

    def _update_column(self, table, column_to_update, fn):
        # Get the SQL used to create the given table.
        create_table = self._get_create_table(table)

        # Parse out the `CREATE TABLE` and column list portions of the query.
        raw_create, raw_columns = self.column_re.search(create_table).groups()

        # Clean up the individual column definitions.
        column_defs = [
            col.strip() for col in self.column_split_re.findall(raw_columns)]

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
                new_column_names.append(column_name)
                original_column_names.append(column_name)

        # Update the name of the new CREATE TABLE query.
        temp_table = table + '__tmp__'
        create = re.sub(
            '("?)%s("?)' % table,
            '\\1%s\\2' % temp_table,
            raw_create)

        # Create the new table.
        columns = ', '.join(new_column_defs)
        queries = [SQL('%s (%s)' % (create.strip(), columns))]

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

        return queries

    def drop_column(self, table, column_name, cascade=True):
        return self._update_column(table, column_name, lambda a, b: None)

    def rename_column(self, table, old_name, new_name):
        def _rename(column_name, column_def):
            return column_def.replace(column_name, new_name)
        return self._update_column(table, old_name, _rename)

    def add_not_null(self, table, column):
        def _add_not_null(column_name, column_def):
            return column_def + ' NOT NULL'
        return self._update_column(table, column, _add_not_null)

    def drop_not_null(self, table, column):
        def _drop_not_null(column_name, column_def):
            return column_def.replace('NOT NULL', '')
        return self._update_column(table, column, _drop_not_null)


class Migration(object):
    def __init__(self, database, *operations):
        self.database = database
        if not operations:
            raise ValueError('Migrations must include at least one operation.')
        self.operations = self.flatten_operations(operations)

    def flatten_operations(self, operations):
        accum = []
        for operation in operations:
            if isinstance(operation, list):
                accum.extend(self.flatten_operations(operation))
            else:
                accum.append(operation)
        return accum

    def run(self, in_transaction=True):
        if in_transaction:
            with self.database.transaction():
                self._run()
        else:
            self._run()

    def _run(self):
        compiler = self.database.compiler()
        for operation in self.operations:
            sql, params = compiler.parse_node(operation)
            self.database.execute_sql(sql, params)
