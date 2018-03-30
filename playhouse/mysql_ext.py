try:
    import mysql.connector as mysql_connector
except ImportError:
    mysql_connector = None

from peewee import ImproperlyConfigured
from peewee import MySQLDatabase


class MySQLConnectorDatabase(MySQLDatabase):
    def _connect(self):
        if mysql_connector is None:
            raise ImproperlyConfigured('MySQL connector not installed!')
        return mysql_connector.connect(db=self.database, **self.connect_params)

    def cursor(self, commit=None):
        if self.is_closed():
            self.connect()
        return self._state.conn.cursor(buffered=True)
