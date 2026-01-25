from peewee import *

class ClickHouseDatabase(Database):
    param = "%s"

    def _connect(self):
        return Connection(database=self.database, **self.connect_params)

    def last_insert_id(self, cursor, query_type=None):
        return None
