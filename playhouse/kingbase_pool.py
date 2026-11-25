"""Synchronous KingbaseES connection pools for the PostgreSQL wire driver."""

from playhouse.kingbase_native import KingbaseMySQLDatabase
from playhouse.kingbase_native import KingbasePsycopg2Adapter
from playhouse.pool import PooledDatabase


class PooledKingbaseMySQLDatabase(PooledDatabase, KingbaseMySQLDatabase):
    """Reuse Kingbase MySQL-mode connections without PyMySQL-specific ping."""

    _pool_adapter = KingbasePsycopg2Adapter()

    def _is_closed(self, conn):
        return bool(conn.closed) or self._pool_adapter.is_connection_closed(conn)

    def _can_reuse(self, conn):
        return self._pool_adapter.is_connection_reusable(conn)
