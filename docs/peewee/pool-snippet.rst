Commonly-used pool implementations:

* :class:`~playhouse.pool.PooledPostgresqlDatabase`
* :class:`~playhouse.pool.PooledMySQLDatabase`
* :class:`~playhouse.pool.PooledSqliteDatabase`

Additional implementations:

* ``playhouse.cysqlite_ext`` - :class:`~playhouse.cysqlite_ext.PooledCySqliteDatabase`
* ``playhouse.mysql_ext`` - :class:`~playhouse.mysql_ext.PooledMariaDBConnectorDatabase`
* ``playhouse.mysql_ext`` - :class:`~playhouse.mysql_ext.PooledMySQLConnectorDatabase`
* ``playhouse.postgres_ext`` - :class:`~playhouse.postgres_ext.PooledPostgresqlExtDatabase`
* ``playhouse.postgres_ext`` - :class:`~playhouse.postgres_ext.PooledPsycopg3Database`
* ``playhouse.cockroachdb`` - :class:`~playhouse.cockroachdb.PooledCockroachDatabase`
