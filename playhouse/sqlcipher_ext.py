"""
Peewee integration with pysqlcipher, "same data, nobody's business".

Project page: https://github.com/leapcode/pysqlcipher/

**WARNING!!! EXPERIMENTAL!!!**

* Although this extention's code is short, it has not been propery
  peer-reviewed yet and may have introduced vulnerabilities.
* The code contains minimum values for `passphrase` length and
  `kdf_iter`, as well as a default value for the later.
  **Do not** regard these numbers as advice. Consult the docs at
  http://sqlcipher.net/sqlcipher-api/ and security experts.

Also note that this code relies on pysqlcipher and sqlcipher, and
the code there might have vulnerabilities as well, but since these
are widely used crypto modules, we can expect "short zero days" there.

Example usage:

     from peewee.playground.ciphersql_ext import SqlCipherDatabase
     db=SqlCipherDatabase('/path/to/my.db', passphrase="don'tuseme4real",
         kdf_iter=1000000)

* `passphrase`: should be "long enough".
  Note that *length beats vocabulary* (much exponential), and even
  a lowercase-only passphrase like easytorememberyethardforotherstoguess
  packs more noise than 8 random printable chatacters and *can* be memorized.
* `kdf_iter`: Should be "as much as the weakest target machine can afford".

When opening an existing database, passphrase and kdf_iter should be identical
to the ones used when creating it.  If they're wrong, an exception will only be
raised **when you access the database**.

If you need to ask for an interactive passphrase, here's example code you can
put after the `db = ...` line:

    try:  # Just access the database so that it checks the encryption.
        db.get_tables()
    # We're looking for a DatabaseError with a specific error message.
    except peewee.DatabaseError as e:
        # Check whether the message *means* "passphrase is wrong"
        if e.message=='file is encrypted or is not a database':
            raise Exception('Developer should Prompt user for passphrase again.')
        else:
            # A different DatabaseError. Raise it.
            raise e

See a more elaborate example with this code at
https://gist.github.com/thedod/11048875
"""
from peewee import *

from pysqlcipher import dbapi2 as sqlcipher

class SqlCipherDatabase(SqliteDatabase):
    def _connect(self, database, **kwargs):
        passphrase = kwargs.pop('passphrase', '').strip()
        kdf_iter = kwargs.pop('kdf_iter', 64000)  # Is this a good number?
        if len(passphrase)<8:
            raise ImproperlyConfigured(
                "SqlCipherDatabase passphrase should be at least "
                "8 character long (a lot longer, if you're serious).")
        if kdf_iter and kdf_iter<10000:
            raise ImproperlyConfigured(
                 "SqlCipherDatabase kdf_iter should be at least "
                 "10000 (a lot more, if you're serious).")
        conn = sqlcipher.connect(database, **kwargs)

        # Add the hooks SqliteDatabase needs
        self._add_conn_hooks(conn)
        conn.execute("PRAGMA key='{0}'".format(passphrase.replace("'", "''")))
        conn.execute("PRAGMA kdf_iter={0:d}".format(kdf_iter))
        return conn
