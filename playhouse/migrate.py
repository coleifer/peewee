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
from peewee import *


# currently only postgres and maybe some sqlite/mysql
class Migrator(object):
    sql_add_column = 'ALTER TABLE %(table)s ADD COLUMN %(column)s'
    sql_drop_column = 'ALTER TABLE %(table)s DROP COLUMN %(column)s CASCADE'
    sql_rename_column = ('ALTER TABLE %(table)s RENAME COLUMN %(column)s TO '
                         '%(new_name)s')

    sql_add_not_null = ('ALTER TABLE %(table)s ALTER COLUMN %(column)s SET '
                        'NOT NULL')
    sql_drop_not_null = ('ALTER TABLE %(table)s ALTER COLUMN %(column)s DROP '
                         'NOT NULL')

    sql_rename_table = 'ALTER TABLE %(table)s RENAME TO %(new_name)s'

    def __init__(self, db):
        self.db = db
        self.compiler = db.compiler()

    def execute(self, sql, params=None):
        return self.db.execute_sql(sql, params, require_commit=False)

    def quote(self, s):
        return self.compiler.quote(s)

    def add_column(self, model_class, field, field_name=None):
        if not field_name and not field.db_column:
            raise AttributeError('Missing required field name')
        elif not field.db_column:
            field.name = field.db_column = field_name
            field.model_class = model_class

        if not field.null and field.default is None:
            raise ValueError('Field %s is not null but has no default' %
                             field.db_column)

        # make field null at first
        field_null, field.null = field.null, True
        table = self.quote(model_class._meta.db_table)
        self.execute(self.sql_add_column % {
            'table': table,
            'column': self.compiler.field_sql(field)})

        if not field_null:
            # update the new column with the provided default
            default = field.default
            if callable(default):
                default = default()
            update = 'UPDATE %s SET %s=%s' % (
                table, self.quote(field.db_column), self.compiler.interpolation
            )
            self.execute(update, (field.coerce(default),))

            # set column as not null
            self.set_nullable(model_class, field, False)

    def drop_column(self, model_class, field_name):
        self.execute(self.sql_drop_column % {
            'table': self.quote(model_class._meta.db_table),
            'column': self.quote(field_name)})

    def rename_column(self, model_class, old_name, new_name):
        self.execute(self.sql_rename_column % {
            'table': self.quote(model_class._meta.db_table),
            'column': old_name,
            'new_name': new_name})

    def set_nullable(self, model_class, field, nullable=False):
        template = nullable and self.sql_drop_not_null or self.sql_add_not_null
        if isinstance(field, Field):
            field.null = nullable
            field = field.db_column
        self.execute(template % {
            'table': self.quote(model_class._meta.db_table),
            'column': self.quote(field)})

    def rename_table(self, model_class, new_name):
        old_name = model_class._meta.db_table
        model_class._meta.db_table = new_name
        self.execute(self.sql_rename_table % {
            'table': self.quote(old_name),
            'new_name': self.quote(new_name)})
