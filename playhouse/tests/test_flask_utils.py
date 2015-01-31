import unittest

from flask import Flask

from peewee import *
from playhouse.flask_utils import Database
from playhouse.flask_utils import PaginatedQuery
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.models import *


class TestPaginationHelpers(ModelTestCase):
    requires = [User]

    def setUp(self):
        super(TestPaginationHelpers, self).setUp()
        for i in range(40):
            User.create(username='u%02d' % i)

        self.app = Flask(__name__)

    def test_paginated_query(self):
        query = User.select().order_by(User.username)
        paginated_query = PaginatedQuery(query, 5)

        with self.app.test_request_context('/?page=2'):
            self.assertEqual(paginated_query.get_page(), 2)
            self.assertEqual(paginated_query.get_page_count(), 8)
            users = paginated_query.get_object_list()

        self.assertEqual(
            [user.username for user in users],
            ['u05', 'u06', 'u07', 'u08', 'u09'])


class TestDatabase(PeeweeTestCase):
    def test_database(self):
        app = Flask(__name__)
        app.config.update({
            'DATABASE': {
                'name': ':memory:',
                'engine': 'peewee.SqliteDatabase'}})
        database = Database(app)

        Model = database.Model
        self.assertTrue(isinstance(Model._meta.database, SqliteDatabase))
        self.assertEqual(Model._meta.database.database, ':memory:')

        # Multiple calls reference the same object.
        self.assertTrue(database.Model is Model)

    def test_deferred_database(self):
        app = Flask(__name__)
        app.config.update({
            'DATABASE': {
                'name': ':memory:',
                'engine': 'peewee.SqliteDatabase'}})

        # Defer initialization of the database.
        database = Database()

        # Ensure we can access the Model attribute.
        Model = database.Model
        model_db = Model._meta.database

        # Because the database is not initialized, the models will point
        # to an uninitialized Proxy object.
        self.assertTrue(isinstance(model_db, Proxy))
        self.assertRaises(AttributeError, lambda: model_db.database)

        class User(database.Model):
            username = CharField(unique=True)

        # Initialize the database with our Flask app.
        database.init_app(app)

        # Ensure the `Model` property points to the same object as it
        # did before.
        PostInitModel = database.Model
        self.assertTrue(Model is PostInitModel)

        # Ensure that the proxy is initialized.
        self.assertEqual(model_db.database, ':memory:')

        # Ensure we can use our database.
        User.create_table()
        for username in ['charlie', 'huey', 'zaizee']:
            User.create(username=username)

        self.assertEqual(User.select().count(), 3)
        users = User.select().order_by(User.username)
        self.assertEqual(
            [user.username for user in users],
            ['charlie', 'huey', 'zaizee'])

        self.assertEqual(User._meta.database, database.database)
