from peewee import create_model_tables
from peewee import drop_model_tables


class test_database(object):
    def __init__(self, db, models, create_tables=True, drop_tables=True,
                 fail_silently=False):
        self.db = db
        self.models = models
        self.create_tables = create_tables
        self.drop_tables = drop_tables
        self.fail_silently = fail_silently

    def __enter__(self):
        self.orig = []
        for m in self.models:
            self.orig.append(m._meta.database)
            m._meta.database = self.db
        if self.create_tables:
            create_model_tables(self.models, fail_silently=self.fail_silently)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.create_tables and self.drop_tables:
            drop_model_tables(self.models, fail_silently=self.fail_silently)
        for i, m in enumerate(self.models):
            m._meta.database = self.orig[i]
