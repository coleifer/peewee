Commonly-used pool implementations:

* :class:`PooledPostgresqlDatabase`
* :class:`PooledMySQLDatabase`
* :class:`PooledSqliteDatabase`

Additional implementations:

* ``playhouse.cysqlite_ext`` - :class:`PooledCySqliteDatabase`
* ``playhouse.mysql_ext`` - :class:`PooledMariaDBConnectorDatabase`
* ``playhouse.mysql_ext`` - :class:`PooledMySQLConnectorDatabase`
* ``playhouse.postgres_ext`` - :class:`PooledPostgresqlExtDatabase`
* ``playhouse.postgres_ext`` - :class:`PooledPsycopg3Database`
* ``playhouse.cockroachdb`` - :class:`PooledCockroachDatabase`
