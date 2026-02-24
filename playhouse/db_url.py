try:
    from urlparse import parse_qsl, unquote, urlparse
except ImportError:
    from urllib.parse import parse_qsl, unquote, urlparse

from peewee import *
from playhouse.pool import PooledMySQLDatabase
from playhouse.pool import PooledPostgresqlDatabase
from playhouse.pool import PooledSqliteDatabase


schemes = {
    'mysql': MySQLDatabase,
    'mysql+pool': PooledMySQLDatabase,
    'postgres': PostgresqlDatabase,
    'postgresql': PostgresqlDatabase,
    'postgres+pool': PooledPostgresqlDatabase,
    'postgresql+pool': PooledPostgresqlDatabase,
    'sqlite': SqliteDatabase,
    'sqlite+pool': PooledSqliteDatabase,
}

def register_database(db_class, *names):
    global schemes
    for name in names:
        schemes[name] = db_class

def parseresult_to_dict(parsed, unquote_password=False, unquote_user=False):

    # urlparse in python 2.6 is broken so query will be empty and instead
    # appended to path complete with '?'
    path = parsed.path[1:]  # Ignore leading '/'.
    query = parsed.query

    connect_kwargs = {'database': path}
    if parsed.username:
        connect_kwargs['user'] = parsed.username
        if unquote_user:
            connect_kwargs['user'] = unquote(connect_kwargs['user'])
    if parsed.password:
        connect_kwargs['password'] = parsed.password
        if unquote_password:
            connect_kwargs['password'] = unquote(connect_kwargs['password'])
    if parsed.hostname:
        connect_kwargs['host'] = parsed.hostname
    if parsed.port:
        connect_kwargs['port'] = parsed.port

    # Adjust parameters for MySQL.
    if parsed.scheme == 'mysql' and 'password' in connect_kwargs:
        connect_kwargs['passwd'] = connect_kwargs.pop('password')
    elif 'sqlite' in parsed.scheme and not connect_kwargs['database']:
        connect_kwargs['database'] = ':memory:'

    # Get additional connection args from the query string
    qs_args = parse_qsl(query, keep_blank_values=True)
    for key, value in qs_args:
        if value.lower() == 'false':
            value = False
        elif value.lower() == 'true':
            value = True
        elif value.isdigit():
            value = int(value)
        elif '.' in value and all(p.isdigit() for p in value.split('.', 1)):
            try:
                value = float(value)
            except ValueError:
                pass
        elif value.lower() in ('null', 'none'):
            value = None

        connect_kwargs[key] = value

    return connect_kwargs

def parse(url, unquote_password=False, unquote_user=False):
    parsed = urlparse(url)
    return parseresult_to_dict(parsed, unquote_password, unquote_user)

def connect(url, unquote_password=False, unquote_user=False, **connect_params):
    parsed = urlparse(url)
    connect_kwargs = parseresult_to_dict(parsed, unquote_password, unquote_user)
    connect_kwargs.update(connect_params)
    database_class = schemes.get(parsed.scheme)

    if database_class is None:
        if database_class in schemes:
            raise RuntimeError('Attempted to use "%s" but a required library '
                               'could not be imported.' % parsed.scheme)
        else:
            raise RuntimeError('Unrecognized or unsupported scheme: "%s".' %
                               parsed.scheme)

    return database_class(**connect_kwargs)

# Conditionally register additional databases.

try:
    from playhouse.apsw_ext import APSWDatabase
    register_database(APSWDatabase, 'apsw')
except ImportError:
    pass

try:
    from playhouse.cockroachdb import CockroachDatabase
    from playhouse.cockroachdb import PooledCockroachDatabase
    register_database(CockroachDatabase, 'cockroachdb', 'crdb')
    register_database(PooledCockroachDatabase, 'cockroachdb+pool', 'crdb+pool')
except ImportError:
    pass

try:
    from playhouse.cysqlite_ext import CySqliteDatabase
    from playhouse.cysqlite_ext import PooledCySqliteDatabase

    register_database(CySqliteDatabase, 'cysqlite')
    register_database(PooledCySqliteDatabase, 'cysqlite+pool')
except ImportError:
    pass

try:
    from playhouse.mysql_ext import MariaDBConnectorDatabase
    from playhouse.mysql_ext import MySQLConnectorDatabase
    from playhouse.mysql_ext import PooledMariaDBConnectorDatabase
    from playhouse.mysql_ext import PooledMySQLConnectorDatabase

    register_database(MariaDBConnectorDatabase, 'mariadbconnector')
    register_database(MySQLConnectorDatabase, 'mysqlconnector')
    register_database(PooledMariaDBConnectorDatabase, 'mariadbconnector+pool')
    register_database(PooledMySQLConnectorDatabase, 'mysqlconnector+pool')
except ImportError:
    pass

try:
    from playhouse.postgres_ext import PooledPostgresqlExtDatabase
    from playhouse.postgres_ext import PooledPsycopg3Database
    from playhouse.postgres_ext import PostgresqlExtDatabase
    from playhouse.postgres_ext import Psycopg3Database

    register_database(
        PooledPostgresqlExtDatabase,
        'postgresext+pool', 'postgresqlext+pool')
    register_database(
        PostgresqlExtDatabase,
        'postgresext', 'postgresqlext')

    register_database(PooledPsycopg3Database, 'psycopg3+pool')
    register_database(Psycopg3Database, 'psycopg3')
except ImportError:
    pass
