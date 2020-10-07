import json

try:
    import mysql.connector as mysql_connector
except ImportError:
    mysql_connector = None

from peewee import ImproperlyConfigured
from peewee import MySQLDatabase
from peewee import NodeList
from peewee import SQL
from peewee import TextField
from peewee import fn


class MySQLConnectorDatabase(MySQLDatabase):
    def _connect(self):
        if mysql_connector is None:
            raise ImproperlyConfigured('MySQL connector not installed!')
        return mysql_connector.connect(db=self.database, **self.connect_params)

    def cursor(self, commit=None):
        if self.is_closed():
            if self.autoconnect:
                self.connect()
            else:
                raise InterfaceError('Error, database connection not opened.')
        return self._state.conn.cursor(buffered=True)


class JSONField(TextField):
    field_type = 'JSON'

    def db_value(self, value):
        if value is not None:
            return json.dumps(value)

    def python_value(self, value):
        if value is not None:
            return json.loads(value)


def Match(columns, expr, modifier=None):
    if isinstance(columns, (list, tuple)):
        match = fn.MATCH(*columns)  # Tuple of one or more columns / fields.
    else:
        match = fn.MATCH(columns)  # Single column / field.
    args = expr if modifier is None else NodeList((expr, SQL(modifier)))
    return NodeList((match, fn.AGAINST(args)))
