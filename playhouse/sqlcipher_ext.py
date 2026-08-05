"""
Peewee integration with sqlcipher3.

Example usage:

    from peewee.playground.ciphersql_ext import SqlCipherDatabase
    db = SqlCipherDatabase('/path/to/my.db', passphrase="don'tuseme4real")

Invalid or incorrect passphrases do not get a special exception, unfortunately,
so to catch these in application code you can do something like this:

    try:
        db.get_tables()  # Attempt to read from db.
    except DatabaseError as exc:
        if 'not a database' in exc.args[0]:
            print('Invalid passphrase')
        else:
            raise
"""
import datetime
import decimal
import sys

from peewee import *
from sqlcipher3 import dbapi2 as sqlcipher

sqlcipher.register_adapter(decimal.Decimal, str)
sqlcipher.register_adapter(datetime.date, str)
sqlcipher.register_adapter(datetime.time, str)
__sqlcipher_version__ = sqlcipher.sqlite_version_info


class _SqlCipherDatabase(object):
    server_version = __sqlcipher_version__

    def _connect(self):
        params = dict(self.connect_params)
        passphrase = params.pop('passphrase', '').replace("'", "''")

        conn = sqlcipher.connect(self.database, isolation_level=None, **params)
        try:
            if passphrase:
                conn.execute("PRAGMA key='%s'" % passphrase)
            self._add_conn_hooks(conn)
        except:
            conn.close()
            raise
        return conn

    def set_passphrase(self, passphrase):
        if not self.is_closed():
            raise ImproperlyConfigured('Cannot set passphrase when database '
                                       'is open. To change passphrase of an '
                                       'open database use the rekey() method.')

        self.connect_params['passphrase'] = passphrase

    def rekey(self, passphrase):
        if self.is_closed():
            self.connect()

        self.execute_sql("PRAGMA rekey='%s'" % passphrase.replace("'", "''"))
        self.connect_params['passphrase'] = passphrase
        return True


class SqlCipherDatabase(_SqlCipherDatabase, SqliteDatabase):
    pass
