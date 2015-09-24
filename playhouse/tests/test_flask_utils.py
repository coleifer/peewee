import unittest

from flask import Flask

from peewee import *
from playhouse.flask_utils import FlaskDB
from playhouse.flask_utils import PaginatedQuery
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import test_db
from playhouse.tests.models import *


class TestPaginationHelpers(ModelTestCase):
    requires = [User]

    def setUp(self):
        super(TestPaginationHelpers, self).setUp()
        for i in range(10):
            User.create(username='u%02d' % i)

        self.app = Flask(__name__)

    def test_paginated_query(self):
        query = User.select().order_by(User.username)
        paginated_query = PaginatedQuery(query, 4)

        with self.app.test_request_context('/?page=2'):
            self.assertEqual(paginated_query.get_page(), 2)
            self.assertEqual(paginated_query.get_page_count(), 3)
            users = paginated_query.get_object_list()

        self.assertEqual(
            [user.username for user in users],
            ['u04', 'u05', 'u06', 'u07'])

        with self.app.test_request_context('/'):
            self.assertEqual(paginated_query.get_page(), 1)

        for value in ['1', '0', '-1', 'xxx']:
            with self.app.test_request_context('/?page=%s' % value):
                self.assertEqual(paginated_query.get_page(), 1)

    def test_bounds_checking(self):
        paginated_query = PaginatedQuery(User, 3, 'p', False)
        with self.app.test_request_context('/?p=5'):
            results = paginated_query.get_object_list()
            self.assertEqual(list(results), [])

        paginated_query = PaginatedQuery(User, 3, 'p', True)
        with self.app.test_request_context('/?p=2'):
            self.assertEqual(len(list(paginated_query.get_object_list())), 3)
        with self.app.test_request_context('/?p=4'):
            self.assertEqual(len(list(paginated_query.get_object_list())), 1)
        with self.app.test_request_context('/?p=5'):
            self.assertRaises(Exception, paginated_query.get_object_list)


class TestFlaskDB(PeeweeTestCase):
    def tearDown(self):
        super(TestFlaskDB, self).tearDown()
        if not test_db.is_closed():
            test_db.close()
            test_db.connect()

    def test_database(self):
        app = Flask(__name__)
        app.config.update({
            'DATABASE': {
                'name': ':memory:',
                'engine': 'peewee.SqliteDatabase'}})
        database = FlaskDB(app)

        Model = database.Model
        self.assertTrue(isinstance(Model._meta.database, SqliteDatabase))
        self.assertEqual(Model._meta.database.database, ':memory:')

        # Multiple calls reference the same object.
        self.assertTrue(database.Model is Model)

    def test_database_url(self):
        app = Flask(__name__)
        app.config['DATABASE'] = 'sqlite:///nugget.db'
        database = FlaskDB(app)
        Model = database.Model
        self.assertTrue(isinstance(Model._meta.database, SqliteDatabase))
        self.assertEqual(Model._meta.database.database, 'nugget.db')

        # If a value is specified, it trumps config value.
        database = FlaskDB(app, 'sqlite:///nuglets.db')
        Model = database.Model
        self.assertEqual(Model._meta.database.database, 'nuglets.db')

    def test_database_instance(self):
        app = Flask(__name__)
        db = SqliteDatabase(':memory:')
        flask_db = FlaskDB(app, db)
        Model = flask_db.Model
        self.assertEqual(Model._meta.database, db)

    def test_database_instance_config(self):
        app = Flask(__name__)
        app.config['DATABASE'] = db = SqliteDatabase(':memory:')
        flask_db = FlaskDB(app)
        Model = flask_db.Model
        self.assertEqual(Model._meta.database, db)

    def test_deferred_database(self):
        app = Flask(__name__)
        app.config.update({
            'DATABASE': {
                'name': ':memory:',
                'engine': 'peewee.SqliteDatabase'}})

        # Defer initialization of the database.
        database = FlaskDB()

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
