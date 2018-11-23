## Playhouse

The `playhouse` namespace contains numerous extensions to Peewee. These include vendor-specific database extensions, high-level abstractions to simplify working with databases, and tools for low-level database operations and introspection.

### Vendor extensions

* [SQLite extensions](http://docs.peewee-orm.com/en/latest/peewee/sqlite_ext.html)
    * Full-text search (FTS3/4/5)
    * BM25 ranking algorithm implemented as SQLite C extension, backported to FTS4
    * Virtual tables and C extensions
    * Closure tables
    * JSON extension support
    * LSM1 (key/value database) support
    * BLOB API
    * Online backup API
* [APSW extensions](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#apsw): use Peewee with the powerful [APSW](https://github.com/rogerbinns/apsw) SQLite driver.
* [SQLCipher](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#sqlcipher-ext): encrypted SQLite databases.
* [SqliteQ](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#sqliteq): dedicated writer thread for multi-threaded SQLite applications. [More info here](http://charlesleifer.com/blog/multi-threaded-sqlite-without-the-operationalerrors/).
* [Postgresql extensions](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#postgres-ext)
    * JSON and JSONB
    * HStore
    * Arrays
    * Server-side cursors
    * Full-text search
* [MySQL extensions](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#mysql-ext)

### High-level libraries

* [Extra fields](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#extra-fields)
    * Compressed field
    * PickleField
* [Shortcuts / helpers](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#shortcuts)
    * Model-to-dict serializer
    * Dict-to-model deserializer
* [Hybrid attributes](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#hybrid)
* [Signals](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#signals): pre/post-save, pre/post-delete, pre-init.
* [Dataset](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#dataset): high-level API for working with databases popuarlized by the [project of the same name](https://dataset.readthedocs.io/).
* [Key/Value Store](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#kv): key/value store using SQLite. Supports *smart indexing*, for *Pandas*-style queries.

### Database management and framework support

* [pwiz](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#pwiz): generate model code from a pre-existing database.
* [Schema migrations](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#migrate): modify your schema using high-level APIs. Even supports dropping or renaming columns in SQLite.
* [Connection pool](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#pool): simple connection pooling.
* [Reflection](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#reflection): low-level, cross-platform database introspection
* [Database URLs](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#db-url): use URLs to connect to database
* [Test utils](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#test-utils): helpers for unit-testing Peewee applications.
* [Flask utils](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#flask-utils): paginated object lists, database connection management, and more.
