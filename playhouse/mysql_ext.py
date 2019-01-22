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
        conn = mysql_connector.connect(db=self.database, **self.connect_params)
        if self._server_version is None:
            # MySQL-Connector supports getting the version as a tuple, but this
            # method does not return the proper MariaDB version on systems like
            # Ubuntu, which express the version as 5.5.5-10.0.37-MariaDB-...
            version_raw = conn.get_server_info()
            self._server_version = self._extract_server_version(version_raw)
        return conn

    def cursor(self, commit=None):
        if self.is_closed():
            self.connect()
        return self._state.conn.cursor(buffered=True)
