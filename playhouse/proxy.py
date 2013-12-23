"""
Proxy class useful for situations when you wish to defer the initialization of
an object.

Example:

    from peewee import *
    from playhouse.proxy import Proxy

    database_proxy = Proxy()  # Create a proxy for our db.

    class BaseModel(Model):
        class Meta:
            database = database_proxy  # Use proxy for our DB.

    class User(BaseModel):
        username = CharField()

    # Based on configuration, use a different database.
    if app.config['DEBUG']:
        database = SqliteDatabase('local.db')
    elif app.config['TESTING']:
        database = SqliteDatabase(':memory:')
    else:
        database = PostgresqlDatabase('mega_production_db')

    # Configure our proxy to use the db we specified in config.
    database_proxy.initialize(database)
"""

from peewee import Proxy  # Moved into peewee, here for backwards-compat.
