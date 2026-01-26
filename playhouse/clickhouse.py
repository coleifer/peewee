from peewee import *
from clickhouse_connect.dbapi.connection import Connection
from clickhouse_connect.cc_sqlalchemy.datatypes.sqltypes import String


class ClickHouseDatabase(Database):
    param = "%s"

    def _connect(self):
        self.connect_params["allow_create_index_without_type"] = 1
        self.connect_params["create_index_ignore_unique"] = 1

        return Connection(database=self.database, **self.connect_params)

    def last_insert_id(self, cursor, query_type=None):
        return None

    def get_binary_type(self):
        return String
