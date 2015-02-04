import math
import sys

from flask import abort
from flask import render_template
from flask import request
from peewee import Database as _Database
from peewee import DoesNotExist
from peewee import Model
from peewee import Proxy
from peewee import SelectQuery
from playhouse.db_url import connect as db_url_connect


class PaginatedQuery(object):
    def __init__(self, query_or_model, paginate_by, page_var='page',
                 check_bounds=False):
        self.paginate_by = paginate_by
        self.page_var = page_var
        self.check_bounds = check_bounds

        if isinstance(query_or_model, SelectQuery):
            self.query = query_or_model
            self.model = self.query.model_class
        else:
            self.model = query_or_model
            self.query = self.model.select()

    def get_page(self):
        curr_page = request.args.get(self.page_var)
        if curr_page and curr_page.isdigit():
            return max(1, int(curr_page))
        return 1

    def get_page_count(self):
        return int(math.ceil(float(self.query.count()) / self.paginate_by))

    def get_object_list(self):
        if self.check_bounds and self.get_page() > self.get_page_count():
            abort(404)
        return self.query.paginate(self.get_page(), self.paginate_by)


def get_object_or_404(query_or_model, *query):
    if not isinstance(query_or_model, SelectQuery):
        query_or_model = query_or_model.select()
    try:
        return query_or_model.where(*query).get()
    except DoesNotExist:
        abort(404)

def object_list(template_name, query, context_variable='object_list',
                paginate_by=20, page_var='page', check_bounds=True, **kwargs):
    paginated_query = PaginatedQuery(
        query,
        paginate_by,
        page_var,
        check_bounds)
    kwargs[context_variable] = paginated_query.get_object_list()
    return render_template(
        template_name,
        pagination=paginated_query,
        page=paginated_query.get_page(),
        **kwargs)

def get_current_url():
    if not request.query_string:
        return request.path
    return '%s?%s' % (request.path, request.query_string)

def get_next_url(default='/'):
    if request.args.get('next'):
        return request.args['next']
    elif request.form.get('next'):
        return request.form['next']
    return default

class FlaskDB(object):
    def __init__(self, app=None):
        self._app = app
        self.database = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self._app = app
        self._load_database(app)
        self._register_handlers(app)

    def _load_database(self, app):
        config_value = app.config['DATABASE']
        if isinstance(config_value, dict):
            database = self._load_from_config_dict(dict(config_value))
        else:
            # Assume a database connection URL.
            database = db_url_connect(config_value)

        if isinstance(self.database, Proxy):
            self.database.initialize(database)
        else:
            self.database = database

    def _load_from_config_dict(self, config_dict):
        try:
            name = config_dict.pop('name')
            engine = config_dict.pop('engine')
        except KeyError:
            raise RuntimeError('DATABASE configuration must specify a '
                               '`name` and `engine`.')

        if '.' in engine:
            path, class_name = engine.rsplit('.', 1)
        else:
            path, class_name = 'peewee', engine

        try:
            __import__(path)
            module = sys.modules[path]
            database_class = getattr(module, class_name)
            assert issubclass(database_class, _Database)
        except ImportError:
            raise RuntimeError('Unable to import %s' % engine)
        except AttributeError:
            raise RuntimeError('Database engine not found %s' % engine)
        except AssertionError:
            raise RuntimeError('Database engine not a subclass of '
                               'peewee.Database: %s' % engine)

        return database_class(name, **config_dict)

    def _register_handlers(self, app):
        app.before_request(self.connect_db)
        app.teardown_request(self.close_db)

    def get_model_class(self):
        if self.database is None:
            raise RuntimeError('Database must be initialized.')

        class BaseModel(Model):
            class Meta:
                database = self.database

        return BaseModel

    @property
    def Model(self):
        if self._app is None:
            database = getattr(self, 'database', None)
            if database is None:
                self.database = Proxy()

        if not hasattr(self, '_model_class'):
            self._model_class = self.get_model_class()
        return self._model_class

    def connect_db(self):
        self.database.connect()

    def close_db(self, exc):
        if not self.database.is_closed():
            self.database.close()
