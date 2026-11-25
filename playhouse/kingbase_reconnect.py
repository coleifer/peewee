"""Synchronous reconnect support for KingbaseES MySQL-compatible mode."""

from peewee import InterfaceError
from peewee import OperationalError
from playhouse.kingbase_native import KingbaseMySQLDatabase
from playhouse.shortcuts import ReconnectMixin


class ReconnectKingbaseMySQLDatabase(ReconnectMixin, KingbaseMySQLDatabase):
    """Retry a lost connection once outside a transaction.

    Keep Peewee's MySQL disconnect codes for compatibility while recognizing
    the PostgreSQL-wire errors surfaced by ksycopg2. SQL and constraint
    failures are deliberately excluded from the retry list.
    """

    reconnect_errors = ReconnectMixin.reconnect_errors + (
        (OperationalError, 'server closed the connection'),
        (OperationalError, 'connection already closed'),
        (OperationalError, 'connection not open'),
        (OperationalError, '08003'),
        (OperationalError, '08006'),
        (OperationalError, '57p01'),
        (InterfaceError, 'connection already closed'),
        (InterfaceError, 'connection not open'),
    )
