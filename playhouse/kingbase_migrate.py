"""Kingbase-specific schema migration DDL and legacy factory alias."""

from peewee import ForeignKeyField
from peewee import Entity
from peewee import Index
from peewee import SQL
from peewee import Table

from playhouse.migrate import PostgresqlMigrator
from playhouse.migrate import SchemaMigrator
from playhouse.migrate import make_index_name
from playhouse.migrate import operation


class KingbaseConstraintMigrator(PostgresqlMigrator):
    @operation
    def drop_index(self, table, index_name):
        # Unique constraints own their backing index and must be dropped via
        # ALTER TABLE. Ordinary indexes retain the PostgreSQL-style DDL.
        cursor = self.database.execute_sql(
            'SELECT 1 FROM pg_catalog.pg_constraint c '
            'JOIN pg_catalog.pg_class t ON t.oid = c.conrelid '
            'WHERE t.relname = %s AND c.conname = %s AND c.contype = %s',
            (table.split('.')[-1], index_name, 'u'))
        ctx = self.make_context()
        if cursor.fetchone():
            return (self._alter_table(ctx, table)
                    .literal(' DROP CONSTRAINT ').sql(Entity(index_name)))
        return ctx.literal('DROP INDEX ').sql(self._table(index_name))


class KingbaseOracleMigrator(KingbaseConstraintMigrator):
    pass


class KingbaseMySQLMigrator(KingbaseConstraintMigrator):
    """Use PostgreSQL-style DDL accepted by Kingbase MySQL compatibility mode."""

    explicit_create_foreign_key = True

    def add_inline_fk_sql(self, ctx, field):
        # This mode uses the explicit foreign-key operation.
        pass

    @operation
    def add_index(self, table, columns, unique=False, using=None, where=None,
                  nulls_distinct=None, name=None):
        ctx = self.make_context()
        index_name = name or make_index_name(table, columns)
        table_obj = Table(table)
        cols = [getattr(table_obj.c, column) for column in columns]
        index = Index(index_name, table_obj, cols, unique=unique, using=using,
                      where=where, nulls_distinct=nulls_distinct)
        with ctx(index_using_precedes_table=False):
            ctx.sql(index)
        return ctx

    @operation
    def rename_table(self, old_name, new_name):
        # Do not attempt to rename a PostgreSQL sequence with the table.
        return SchemaMigrator.rename_table(
            self, old_name, new_name)


class KingbaseSQLServerMigrator(KingbaseMySQLMigrator):
    """Use SQL Server's ADD syntax for the public migration entrypoint."""

    @operation
    def alter_column_type(self, table, column, field, cast=None):
        if cast is not None:
            raise ValueError('SQL Server ALTER COLUMN does not support USING.')
        ctx = self.make_context()
        return (self._alter_column(ctx, table, column)
                .literal(' ')
                .sql(field.ddl_datatype(ctx))
                .literal(' NULL' if field.null else ' NOT NULL'))

    @operation
    def alter_add_column(self, table, column_name, field,
                         allow_not_null=False):
        ctx = self.make_context()
        old_null = field.null
        if not allow_not_null:
            field.null = True
        try:
            if field.column_name != column_name:
                field.name = field.column_name = column_name
            self._alter_table(ctx, table).literal(' ADD ').sql(field.ddl(ctx))
            if any(isinstance(item, SQL) and
                   'default' in item.sql.lower() for item in
                   (field.constraints or ())):
                ctx.literal(' WITH VALUES')
            if isinstance(field, ForeignKeyField):
                self.add_inline_fk_sql(ctx, field)
        finally:
            field.null = old_null
        return ctx


class KingbaseSchemaMigrator(SchemaMigrator):
    """Compatibility alias for callers of the previous Kingbase entrypoint."""

    @classmethod
    def from_database(cls, database):
        return SchemaMigrator.from_database(database)


__all__ = ['KingbaseMySQLMigrator', 'KingbaseOracleMigrator',
           'KingbaseSQLServerMigrator',
           'KingbaseSchemaMigrator']
