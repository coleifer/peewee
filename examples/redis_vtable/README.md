### SQLite Virtual Table Example

SQLite's virtual table mechanism allows applications to define external data-sources that are mapped to SQLite tables and queried using SQL. The stdlib `sqlite3` module does not support this functionality, but [apsw](https://github.com/rogerbinns/apsw), an alternative driver, does.

This example shows a very basic implementation of a virtual table that exposes a Redis database as a SQL table.
