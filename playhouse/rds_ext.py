import boto3
from botocore.exceptions import ClientError

try:
    from urlparse import ParseResult
except ImportError:
    from urllib.parse import ParseResult


class UnsupportedRdsEngine(Exception):
    """
    Raised when the RDS DB engine is not supported by the URL building code.
    """
    pass


def _db_from_boto3_cluster_response(response, read_only=False):
    cluster = response['DBClusters'][0]
    hkey = 'ReaderEndpoint' if read_only else 'Endpoint'
    fields = ['Engine', hkey, 'Port', 'DatabaseName', 'MasterUsername']
    return tuple(cluster[a] for a in fields)


def _db_from_boto3_instance_response(response, **kwargs):
    instance = response['DBInstances'][0]
    db0 = tuple(instance[a] for a in ['Engine', 'DBName', 'MasterUsername'])
    db1 = tuple(instance['Endpoint'][a] for a in ['Address', 'Port'])
    return (db0[0], db1[0], db1[1], db0[1], db0[2])


def parse_from_rds(parsed):
    """
    Retrieve the parsed database endpoint URL from a parsed rds:// or rdsro://
    URL.

    The RDS cluster or RDS instance id is read from parsed.hostname (it is case
    insensitive), then boto3 is used to retrieve the DB information (db engine,
    db name, db endpoint address and port) so that the parsed database URL can
    be built.

    The rds:// scheme retrieves the read-write endpoint of the RDS cluster or
    RDS instance, while rdsro:// retrieves the read-only endpoint of the RDS
    cluster. Since there are no read-only endpoints for an RDS instance, in
    this case rdsro:// is equivalent to rds:// .

    See also:
    https://boto3.readthedocs.io/en/latest/reference/services/rds.html#client

    :type parsed: urlparse.ParseResult
    :param parsed: rds:// or rdsro:// parsed URL.
    :rtype: urlparse.ParseResult
    :returns: Parsed URL for the RDS database.
    """
    assert parsed.scheme in ['rds', 'rdsro'], "rds_ext only supports the " \
        "rds:// and rdsro:// schemes: '{}://' provided".format(parsed.scheme)
    db_id = parsed.hostname
    ro = (parsed.scheme == 'rdsro')

    # query boto3's rds client for DB description
    rds = boto3.client('rds')
    try:
        response = rds.describe_db_clusters(DBClusterIdentifier=db_id)
        dbinfo = _db_from_boto3_cluster_response
    except ClientError:
        response = rds.describe_db_instances(DBInstanceIdentifier=db_id)
        dbinfo = _db_from_boto3_instance_response
    engine, hostname, port, dbname, username = dbinfo(response, read_only=ro)

    # recover playhouse-compatible scheme from RDS engine
    # RDS engines not supported yet: 'oracle-ee' and 'sqlserver-*'
    rds_scheme_map = {
        'aurora': 'mysql',
        'mysql': 'mysql',
        'mariadb': 'mysql',
        'postgres': 'postgres',
    }
    try:
        scheme = rds_scheme_map[engine]
    except KeyError:
        raise UnsupportedRdsEngine('Unsupported RDS Engine "{}"'.format(engine))
    # 1. hostname and port are provided by RDS
    netloc = '{}:{}'.format(hostname, port)
    # 2. if dbname or username was provided, overwrite the default ones from RDS
    dbname = parsed.path if parsed.path else '/'+dbname
    username = parsed.username if parsed.username else username
    # 3. the password is never provided by RDS
    if parsed.password:
        netloc = '{}:{}@{}'.format(username, parsed.password, netloc)
    else:
        netloc = '{}@{}'.format(username, netloc)
    return ParseResult(scheme, netloc, dbname, *parsed[3:])
