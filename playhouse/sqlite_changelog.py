from peewee import *
from playhouse.sqlite_ext import JSONField


class BaseChangeLog(Model):
    timestamp = DateTimeField(constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
    action = TextField()
    table = TextField()
    primary_key = IntegerField()
    changes = JSONField()


# table: table name
# action: insert / update / delete
# new_old: NEW or OLD (OLD is for DELETE)
# primary_key: table primary key column name
# column_array: output of build_column_array()
# change_table: changelog table name
template = """CREATE TRIGGER IF NOT EXISTS %(table)s_changes_%(action)s
AFTER %(action)s ON %(table)s
BEGIN
    INSERT INTO %(change_table)s (action, "table", primary_key, changes)
    SELECT '%(action)s', '%(table)s', %(new_old)s."%(primary_key)s", changes
    FROM (
        SELECT json_group_object(col, json_array(oldval, newval)) AS changes
        FROM (
            SELECT json_extract(value, '$[0]') as col,
                   json_extract(value, '$[1]') as oldval,
                   json_extract(value, '$[2]') as newval
            FROM json_each(json_array(%(column_array)s))
            WHERE oldval IS NOT newval
        )
    );
END;"""

drop_template = 'DROP TRIGGER IF EXISTS %(table)s_changes_%(action)s'


def build_column_array(model, use_old, use_new, skip_fields=None):
    column_array = []
    for field in model._meta.sorted_fields:
        if field.primary_key:
            continue

        if skip_fields is not None and field.name in skip_fields:
            continue

        column = field.column_name
        new = 'NULL' if not use_new else 'NEW."%s"' % column
        old = 'NULL' if not use_old else 'OLD."%s"' % column

        column_array.append("json_array('%s', %s, %s)" % (column, old, new))

    return ', '.join(column_array)


def trigger_sql(model, action, skip_fields=None, change_table='changelog'):
    assert action in ('INSERT', 'UPDATE', 'DELETE')
    use_old = action != 'INSERT'
    use_new = action != 'DELETE'
    column_array = build_column_array(model, use_old, use_new, skip_fields)
    return template % {
        'table': model._meta.table_name,
        'action': action,
        'new_old': 'NEW' if action != 'DELETE' else 'OLD',
        'primary_key': model._meta.primary_key.column_name,
        'column_array': column_array,
        'change_table': change_table}

def drop_trigger_sql(model, action):
    assert action in ('INSERT', 'UPDATE', 'DELETE')
    return drop_template % {'table': model._meta.table_name, 'action': action}


def get_changelog_model(db):
    class ChangeLog(BaseChangeLog):
        class Meta:
            database = db
    return ChangeLog


def install_triggers(model, skip_fields=None, db=None, drop=True, insert=True,
                     update=True, delete=True, create_changelog=True):

    if db is None: db = model._meta.database

    ChangeLog = get_changelog_model(db)
    if create_changelog:
        ChangeLog.create_table()

    actions = (
        (insert, 'INSERT'),
        (update, 'UPDATE'),
        (delete, 'DELETE'))

    if drop:
        for _, action in actions:
            db.execute_sql(drop_trigger_sql(model, action))

    change_table = ChangeLog._meta.table_name
    for enabled, action in actions:
        if enabled:
            sql = trigger_sql(model, action, skip_fields, change_table)
            db.execute_sql(sql)

    return ChangeLog
