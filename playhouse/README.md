## Playhouse

The `playhouse` namespace contains numerous extensions to Peewee. These include vendor-specific database extensions, high-level abstractions to simplify working with databases, and tools for low-level database operations and introspection.

### Vendor extensions

* [SQLite extensions](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#sqlite-ext)
    * User-defined aggregates, collations, and functions
    * Full-text search (FTS3/4/5)
    * BM25 ranking algorithm implemented as SQLite C extension, backported to FTS4
    * Virtual tables and C extensions
    * Closure tables
* [APSW extensions](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#apsw-an-advanced-sqlite-driver): use Peewee with the powerful [APSW](https://github.com/rogerbinns/apsw) SQLite driver.
* [BerkeleyDB](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#berkeleydb-backend): compile BerkeleyDB with SQLite compatibility API, then use with Peewee.
* [SQLCipher](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#sqlcipher-backend): encrypted SQLite databases.
* [Postgresql extensions](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#postgresql-extensions)
    * JSON and JSONB
    * HStore
    * Arrays
    * Server-side cursors
    * Full-text search

### High-level libraries

* [Extra fields](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#extra-fields)
    * Many-to-many field
    * Compressed field
    * Password field
    * AES encrypted field
* [Shortcuts / helpers](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#shortcuts)
    * `CASE` statement constructor
    * `CAST`
    * Model to dict serializer
    * Dict to model deserializer
    * Retry query with backoff
* [Hybrid attributes](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#hybrid)
* [Signals](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#signals): pre/post-save, pre/post-delete, pre/post-init.
* [Dataset](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#dataset): high-level API for working with databases popuarlized by the [project of the same name](https://dataset.readthedocs.io/).
* [Key/Value Store](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#kv): key/value store using SQLite. Supports *smart indexing*, for *Pandas*-style queries.
* [Generic foreign key](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#gfk): made popular by Django.
* [CSV utilities](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#csv-utils): load CSV directly into database, generate models from CSV, and more.

### Database management and framework support

* [pwiz](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#pwiz): generate model code from a pre-existing database.
* [Schema migrations](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#migrate): modify your schema using high-level APIs. Even supports dropping or renaming columns in SQLite.
* [Connection pool](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#pool): simple connection pooling.
* [Reflection](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#reflection): low-level, cross-platform database introspection
* [Database URLs](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#db-url): use URLs to connect to database
* [Read slave](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#read-slaves)
* [Flask utils](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#flask-utils): paginated object lists, database connection management, and more.
* [Django integration](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#djpeewee): generate peewee models from Django models, use Peewee alongside your Django ORM code.
