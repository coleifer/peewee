"""DataSet integration using Kingbase reflection and Peewee migration dispatch."""

from peewee import Model
from playhouse.dataset import DataSet
from playhouse.kingbase_native import KingbaseMySQLDatabase
from playhouse.kingbase_native import KingbaseOracleDatabase
from playhouse.kingbase_native import KingbaseSQLServerDatabase
from playhouse.kingbase_reflection import KingbaseIntrospector
from playhouse.migrate import SchemaMigrator


class KingbaseDataSet(DataSet):
    def __init__(self, database, include_views=False, **kwargs):
        if not isinstance(database, (KingbaseMySQLDatabase,
                                     KingbaseOracleDatabase,
                                     KingbaseSQLServerDatabase)):
            raise ValueError('KingbaseDataSet requires a Kingbase database')
        self._url = None
        self._database = database
        self._database_path = database.database
        database.connect(reuse_if_open=True)
        self._introspector = KingbaseIntrospector.from_database(database)
        self._include_views = include_views
        self._model_kwargs = kwargs
        self._models = self._introspector.generate_models(
            skip_invalid=True,
            literal_column_names=True,
            include_views=include_views,
            **kwargs)
        self._migrator = SchemaMigrator.from_database(database)

        class BaseModel(Model):
            class Meta:
                database = self._database

        self._base_model = BaseModel
        self._export_formats = self.get_export_formats()
        self._import_formats = self.get_import_formats()


__all__ = ['KingbaseDataSet']
