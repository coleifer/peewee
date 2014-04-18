"""
Peewee integration with pysqlcipher, "same data, nobody's business".

Project page: https://github.com/leapcode/pysqlcipher/

usage: db=peewee.SqlCipherDatabase('/path/to/my.db',passphrase="don'tuseme4real"[,kdf_iter=1000000])
       Passphrase: Should be long enough
           (IMHO length beats vocbulary (much exponential). Forget MixedcasE, l337 and @%$^& special characters:
           Even a lowercase-only passphrase like easytorememberyethardforotherstoguess
           packs more noise than 8 random printable chatacters AND it's possible to remember it)
       Kdf_iter: Should be "as much as the weakest target machine can afford".

When opening an existing database, passphrase and kbf_iter should be identical to the ones used when creating it.
If they're wrong, an exception will only be raised *when you access the database*.

If you need to ask for an interactive passphrase, here's example code you can put after the "db = ..." line:
    try:
        db.get_tables() # just access the database so that it checks the encryption
    except peewee.DatabaseError,e: # We're looking for a specific [somewhat cryptic] error message
        if e.message=='file is encrypted or is not a database': # indication that passphrase is wrong
            raise Exception('We need to prompt for a password and do "db = ..." again... Sorry.')
        raise e # Some other DatabaseError
See a more elaborate example with this code at https://gist.github.com/thedod/11048875
"""
from peewee import *
from pysqlcipher import dbapi2 as sqlcipher
class SqlCipherDatabase(SqliteDatabase):
    def _connect(self, database, **kwargs):
        passphrase = kwargs.pop('passphrase','').strip()
        kdf_iter = kwargs.pop('kdf_iter',64000) # is this a good number?
        if len(passphrase)<8:
            raise ImproperlyConfigured("SqlCipherDatabase passphrase should be at least 8 character long (a lot longer, if you're serious)")
        if kdf_iter and (type(kdf_iter) != type(0) or kdf_iter<10000):
            raise ImproperlyConfigured("SqlCipherDatabase kdf_iter should be at least 10000 (a lot more, if you're serious)")
        conn = sqlcipher.connect(database, **kwargs)
        # Add the hooks SqliteDatabase needs
        self._add_conn_hooks(conn)
        conn.execute("PRAGMA key='{0}'".format(passphrase.replace("'","''")))
        conn.execute("PRAGMA kdf_iter={0}".format(kdf_iter))
        return conn
