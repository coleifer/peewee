.. _framework-integration:

Framework Integration
=====================

For web applications, it is common to open a connection when a request is
received, and to close the connection when the response is delivered. This
document describes how to add hooks to your web app to ensure the database
connection is handled properly.

These steps will ensure that regardless of whether you're using a simple
:class:`SqliteDatabase` or a :class:`~playhouse.pool.PooledPostgresqlDatabase`,
peewee will handle the connections correctly.

The pattern is always the same:

.. code-block:: python

   # On request start:
   db.connect()

   # On request end (success or error):
   if not db.is_closed():
       db.close()

Every framework exposes hooks for this. The sections below show the idiomatic
approach for each.

.. note::
   Applications that handle significant traffic should use a
   :ref:`connection pool <connection-pooling>` to avoid the overhead of
   establishing a new connection per request. Pooled databases can be used as
   drop-in replacements for their non-pooled counterparts.

.. _flask:

Flask
-----

For a **complete** Flask + Peewee application example, including authentication
and other common webapp functionality, see :ref:`example`. There is also a
full `blog app <https://github.com/coleifer/peewee/tree/master/examples/blog>`__
and an `analytics app <https://github.com/coleifer/peewee/tree/master/examples/analytics>`__
in the project ``examples/`` directory.

The **minimal** Flask integration ensures that database connection lifecycles
are tied to the request/response cycle via ``before_request`` and ``teardown_request``
hooks:

.. code-block:: python

   from flask import Flask
   from peewee import *

   db = SqliteDatabase('my_app.db')
   app = Flask(__name__)

   @app.before_request
   def _db_connect():
       db.connect()

   @app.teardown_request
   def _db_close(exc):
       if not db.is_closed():
           db.close()

``teardown_request`` is called regardless of whether the request succeeded or
raised an exception, making it the correct hook for cleanup.

For applications that receive a large number of requests, a connection pool is
recommended:

.. code-block:: python

   from flask import Flask
   from playhouse.pool import PooledPostgresqlDatabase

   db = PooledPostgresqlDatabase('app', host='10.8.0.1', user='postgres')
   app = Flask(__name__)

   # With the pooled backend the hooks are identical: connect() and close()
   # acquire and release a pooled connection per request.
   @app.before_request
   def _db_connect():
       db.connect()

   @app.teardown_request
   def _db_close(exc):
       if not db.is_closed():
           db.close()

.. seealso::
   The :ref:`flask-utils` extension provides helpers for common tasks like
   declarative database configuration, object retrieval and pagination.

.. _fastapi:

FastAPI
-------

FastAPI is an async framework and can be used with Peewee's :ref:`pwasyncio`
integration or synchronously. Peewee also provides :ref:`pydantic` support,
which works well with FastAPI.

Quick note on SQLModel
^^^^^^^^^^^^^^^^^^^^^^

FastAPI advocates using SQLModel for database access. SQLModel combines
SQLAlchemy and Pydantic into a single class, which may work well for simple
examples. There are a few things to watch out for, though:

* SQLModel's official tutorial uses synchronous endpoints exclusively, which
  FastAPI runs on a threadpool. Async usage is listed as an "advanced" topic
  and is undocumented currently.
* Lazy-loading often breaks in async contexts. SQLAlchemy's implicit lazy-loading
  of relationships can trigger ``MissingGreenlet`` errors when used with async
  sessions. This can also occur with Peewee, but it's straightforward to avoid
  by selecting joined relations.
* Because SQLModel uses synchronous drivers for DDL and certain operations, you
  typically need both a sync AND async driver installed, along with separate
  engine configurations.
* SQLModel uses inheritance to manage input, output and table schemas. In
  practice a single database table often requires three or four model classes,
  e.g. ``UserBase``, ``User``, ``UserCreate`` and ``UserRead``.

Peewee may provide a simpler experience: a single database to manage
with built-in pooling, fewer implicit lazy-load gotchas, and the Pydantic
schemas generated with :func:`~playhouse.pydantic_utils.to_pydantic` can be
configured to include/exclude fields without inheritance. Field metadata is
captured automatically: choice enums, default values, descriptions, titles and
type information are captured in the JSON schema and OpenAPI docs.

Peewee requires far less machinery to provide real asyncio database access, and
works equally well for synchronous FastAPI endpoints.

Async Example using Pydantic
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Below is a full example FastAPI application demonstrating dependency-injection
style hooks, fully :ref:`async query execution <pwasyncio>`, and
:ref:`pydantic integration <pydantic>`:

.. code-block:: python

   # example.py
   from fastapi import Depends, FastAPI, HTTPException
   from contextlib import asynccontextmanager
   from peewee import *
   from playhouse.pwasyncio import AsyncPostgresqlDatabase
   from playhouse.pydantic_utils import to_pydantic


   db = AsyncPostgresqlDatabase('peewee_test')

   class User(db.Model):
       name = CharField(verbose_name='Full Name', help_text='Display name')
       email = CharField(unique=True)
       status = IntegerField(default=1, choices=(
           (1, 'Active'),
           (2, 'Inactive'),
           (3, 'Deleted')))

   # Generate pydantic schemas suitable for create and responses.
   # Schemas will include metadata from verbose_name, help_text, choices, and
   # default settings.
   UserCreate = to_pydantic(User, model_name='UserCreate')
   UserResponse = to_pydantic(User, exclude_autofield=False, model_name='UserResponse')

   async def get_db():
       # Hold a pooled connection open for the duration of the request.
       async with db:
           yield db

   @asynccontextmanager
   async def lifespan(app):
       # Create tables (if they don't exist) at application startup.
       async with db:
           await db.acreate_tables([User])
       yield
       await db.close_pool()  # Shut-down pool and exit.

   app = FastAPI(lifespan=lifespan)

   @app.get('/users', response_model=list[UserResponse])
   async def list_users(db=Depends(get_db)):
       rows = await User.select().dicts().aexecute()
       return [UserResponse(**row) for row in rows]

   @app.post('/users', response_model=UserResponse)
   async def create_user(data: UserCreate, db=Depends(get_db)):
       user = await User.acreate(**data.model_dump())
       return UserResponse.model_validate(user)

   @app.get('/users/{user_id}', response_model=UserResponse)
   async def get_user(user_id: int, db=Depends(get_db)):
       try:
           user = await db.get(User.select().where(User.id == user_id))
       except User.DoesNotExist:
           raise HTTPException(status_code=404, detail='User not found')
       return UserResponse.model_validate(user)

Run the example:

.. code-block:: console

   $ fastapi dev example.py

Populate and query data:

.. code-block:: console

   $ curl -X POST http://localhost:8000/users \
        -H "Content-Type: application/json" \
        -d '{"name": "Alice", "email": "alice@example.com"}'

   {"id":1,"name":"Alice","email":"alice@example.com","status":1}

   $ curl -X POST http://localhost:8000/users \
        -H "Content-Type: application/json" \
        -d '{"name": "Bob", "email": "bob@example.com", "status": 2}'

   {"id":2,"name":"Bob","email":"bob@example.com","status":2}

   $ curl http://localhost:8000/users

   [{"id":1,"name":"Alice","email":"alice@example.com","status":1},
    {"id":2,"name":"Bob","email":"bob@example.com","status":2}]

   $ curl http://localhost:8000/users/1

   {"id":1,"name":"Alice","email":"alice@example.com","status":1}

We can also verify that the pydantic schemas captured our Peewee model
metadata:

.. code-block:: python

   >>> UserCreate.model_json_schema()
   {'properties': {
      'name': {
         'description': 'Display name',
         'title': 'Full Name',
         'type': 'string'},
      'email': {
         'title': 'Email',
         'type': 'string'},
     'status': {
         'default': 1,
         'description': 'Choices: 1 = Active, 2 = Inactive, 3 = Deleted',
         'enum': [1, 2, 3],
         'title': 'Status',
         'type': 'integer'}},
    'required': ['name', 'email'],
    'title': 'UserCreate',
    'type': 'object'}

.. seealso::
   * :ref:`pwasyncio`
   * :ref:`pydantic`

Dependency injection
^^^^^^^^^^^^^^^^^^^^^

The following is a minimal example demonstrating:

* Ensure connection is opened and closed automatically for endpoints that use
  the database.
* Create tables/resources when app server starts.
* Shut-down connection pool when app server exits.

.. code-block:: python

   from contextlib import asynccontextmanager
   from fastapi import Depends, FastAPI
   from peewee import *
   from playhouse.pwasyncio import *


   db = AsyncPostgresqlDatabase('peewee_test')

   class User(db.Model):
       name = TextField()

   async def get_db():
       async with db:
           yield db

   @asynccontextmanager
   async def lifespan(app):
       async with db:
           await db.acreate_tables([User])
       yield
       await db.close_pool()

   app = FastAPI(lifespan=lifespan)

   @app.get('/users')
   async def list_users(db=Depends(get_db)):
       return await db.list(User.select().dicts())

Middleware
^^^^^^^^^^

Connections can also be managed with middleware instead of a dependency. Use a
plain ASGI middleware (a class implementing ``__call__``) and not
``@app.middleware('http')``. The latter uses Starlette's ``BaseHTTPMiddleware``,
which runs the endpoint in a *separate task* from the middleware task. Because
peewee's async connections are task-local, a connection opened there would not
be the one the endpoint uses.

A plain ASGI middleware shares the request task, so the db connection
opened in the middleware is the same one the endpoint sees.

Startup and shutdown are handled by ``lifespan`` (create tables when the server
starts, shut the pool down on exit).

.. code-block:: python

   from contextlib import asynccontextmanager
   from fastapi import FastAPI
   from peewee import *
   from playhouse.pwasyncio import AsyncPostgresqlDatabase


   db = AsyncPostgresqlDatabase('peewee_test')

   class User(db.Model):
       name = TextField()
       email = TextField()

   class PeeweeConnectionMiddleware:
       def __init__(self, app, database):
           self.app = app
           self.database = database

       async def __call__(self, scope, receive, send):
           if scope['type'] != 'http':
               # Pass lifespan / websocket scopes through untouched.
               await self.app(scope, receive, send)
               return
           async with self.database:  # Acquire a pooled connection for the task.
               await self.app(scope, receive, send)

   @asynccontextmanager
   async def lifespan(app):
       async with db:
           await db.acreate_tables([User])
       yield
       await db.close_pool()

   app = FastAPI(lifespan=lifespan)
   app.add_middleware(PeeweeConnectionMiddleware, database=db)

   # Async queries.
   @app.get('/users')
   async def list_users():
       return await db.list(User.select().dicts())

   @app.post('/users')
   async def create_user(name: str, email: str):
       user = await User.acreate(name=name, email=email)
       return {'id': user.id, 'name': user.name}


.. seealso:: :ref:`pydantic`

.. _starlette:

Starlette
---------

Starlette is the ASGI toolkit FastAPI is built on. Connections are managed with
a plain ASGI middleware (which shares the request task) plus a ``lifespan``
handler for startup and shutdown. Do not use ``BaseHTTPMiddleware`` for this as
it runs the endpoint in a separate task, and peewee's async connections are
task-local (so the connection would not be used in the endpoint).

.. code-block:: python

   from contextlib import asynccontextmanager
   from starlette.applications import Starlette
   from starlette.middleware import Middleware
   from peewee import *
   from playhouse.pwasyncio import AsyncPostgresqlDatabase


   db = AsyncPostgresqlDatabase('peewee_test')

   class PeeweeConnectionMiddleware:
       def __init__(self, app, database):
           self.app = app
           self.database = database

       async def __call__(self, scope, receive, send):
           if scope['type'] != 'http':
               # Pass lifespan / websocket scopes through untouched.
               await self.app(scope, receive, send)
               return
           async with self.database:  # Acquire a pooled connection for the task.
               await self.app(scope, receive, send)

   @asynccontextmanager
   async def lifespan(app):
       # Optionally create tables idempotently at startup.
       async with db:
           await db.acreate_tables([...])

       yield
       await db.close_pool()

   app = Starlette(
       lifespan=lifespan,
       routes=[
           ...  # Your routes, etc.
       ],
       middleware=[Middleware(PeeweeConnectionMiddleware, database=db)])

.. seealso:: :ref:`pwasyncio`

.. _quart:

Quart
-----

Quart is an async, Flask-compatible framework. Use the same request hooks as
:ref:`flask`, but ``async`` and with the async connection methods.

.. code-block:: python

   from quart import Quart
   from peewee import *
   from playhouse.pwasyncio import AsyncPostgresqlDatabase


   db = AsyncPostgresqlDatabase('peewee_test')

   app = Quart(__name__)

   @app.before_serving
   async def _create_tables():
       # Optionally create tables idempotently at startup.
       async with db:
           await db.acreate_tables([...])

   @app.after_serving
   async def _close_pool():
       await db.close_pool()

   @app.before_request
   async def _db_connect():
       await db.aconnect()

   @app.teardown_request
   async def _db_close(exc):
       if not db.is_closed():
           await db.aclose()

.. seealso:: :ref:`pwasyncio`

.. _litestar:

Litestar
--------

Litestar is an ASGI framework. The same plain ASGI middleware used for
:ref:`starlette` applies (register it with ``DefineMiddleware``):

.. code-block:: python

   from contextlib import asynccontextmanager
   from litestar import Litestar
   from litestar.middleware import DefineMiddleware
   from peewee import *
   from playhouse.pwasyncio import AsyncPostgresqlDatabase


   db = AsyncPostgresqlDatabase('peewee_test')

   class PeeweeConnectionMiddleware:
       def __init__(self, app, database):
           self.app = app
           self.database = database

       async def __call__(self, scope, receive, send):
           if scope['type'] != 'http':
               # Pass lifespan / websocket scopes through untouched.
               await self.app(scope, receive, send)
               return
           async with self.database:  # Acquire a pooled connection for the task.
               await self.app(scope, receive, send)

   @asynccontextmanager
   async def lifespan(app):
       # Optionally create tables idempotently at startup.
       async with db:
           await db.acreate_tables([...])

       yield
       await db.close_pool()

   app = Litestar(
       route_handlers=[...],  # Your handlers, etc.
       middleware=[DefineMiddleware(PeeweeConnectionMiddleware, database=db)],
       lifespan=[lifespan])

.. seealso:: :ref:`pwasyncio`

.. _aiohttp:

aiohttp
-------

aiohttp has its own server (neither WSGI nor ASGI). Use ``@web.middleware`` to
open the connection per-task.

.. code-block:: python

   from aiohttp import web
   from peewee import *
   from playhouse.pwasyncio import AsyncPostgresqlDatabase


   db = AsyncPostgresqlDatabase('peewee_test')

   @web.middleware
   async def db_middleware(request, handler):
       async with db:  # Acquire a pooled connection for the task.
           return await handler(request)

   async def on_startup(app):
       # Optionally create tables idempotently at startup.
       async with db:
           await db.acreate_tables([...])

   async def on_cleanup(app):
       await db.close_pool()

   app = web.Application(middlewares=[db_middleware])
   app.on_startup.append(on_startup)
   app.on_cleanup.append(on_cleanup)
   app.add_routes([...])  # Your routes, etc.

.. seealso:: :ref:`pwasyncio`

Django
------

Add a middleware that opens the connection before the view runs and closes it
after the response is prepared. Place it first in ``MIDDLEWARE`` so it wraps
all other middleware:

.. code-block:: python

   # myproject/middleware.py
   from myproject.db import database

   def PeeweeConnectionMiddleware(get_response):
       def middleware(request):
           database.connect()
           try:
               response = get_response(request)
           finally:
               if not database.is_closed():
                   database.close()
           return response
       return middleware

.. code-block:: python

   # settings.py
   MIDDLEWARE = [
       'myproject.middleware.PeeweeConnectionMiddleware',
       # ... rest of middleware ...
   ]

Bottle
------

Use the ``before_request`` and ``after_request`` hooks:

.. code-block:: python

   from bottle import hook
   from peewee import *

   db = SqliteDatabase('my_app.db')

   @hook('before_request')
   def _connect_db():
       db.connect()

   @hook('after_request')
   def _close_db():
       if not db.is_closed():
           db.close()

Falcon
------

Add a middleware component:

.. code-block:: python

   import falcon
   from peewee import *

   db = SqliteDatabase('my_app.db')

   class DatabaseMiddleware:
       def process_request(self, req, resp):
           db.connect()

       def process_response(self, req, resp, resource, req_succeeded):
           if not db.is_closed():
               db.close()

   app = falcon.App(middleware=[DatabaseMiddleware()])


Pyramid
-------

Set up a custom ``Request`` factory:

.. code-block:: python

   from pyramid.config import Configurator
   from pyramid.request import Request
   from peewee import *

   db = SqliteDatabase('my_app.db')

   class MyRequest(Request):
       def __init__(self, *args, **kwargs):
           super().__init__(*args, **kwargs)
           db.connect()
           self.add_finished_callback(self._close_db)

       def _close_db(self, request):
           if not db.is_closed():
               db.close()

   # In your application factory:
   def main(global_settings, **settings):
       config = Configurator(settings=settings)
       config.set_request_factory(MyRequest)
       return config.make_wsgi_app()

Sanic
-----

Sanic is an async framework and can be used with Peewee's :ref:`pwasyncio`
integration.

.. code-block:: python

   from sanic import Sanic
   from peewee import *
   from playhouse.pwasyncio import *


   app = Sanic('PeeweeApp')

   db = AsyncPostgresqlDatabase('peewee_test', host='10.8.0.1', user='postgres')

   @app.on_request
   async def open_connection(request):
       await db.aconnect()  # Obtain connection from connection pool.

   @app.on_response
   async def close_connection(request, response):
       await db.aclose()  # Return connection to pool.

   @app.before_server_start
   async def setup_db(app):
       async with db:
           await db.acreate_tables([Model1, Model2, Model3, ...])

   @app.before_server_stop
   async def shutdown_db(app):
       await db.close_pool()

Example demonstrating executing an async query:

.. code-block:: python

   from sanic import json

   @app.get('/message/')
   async def message(request):
       # Get the latest message from the database.
       message = await db.get(Message.select().order_by(Message.id.desc()))
       return json({'content': message.content, 'id': message.id})

.. seealso:: :ref:`pwasyncio`

CherryPy
--------

Subscribe to the engine's before/after request events:

.. code-block:: python

   import cherrypy
   from peewee import *

   db = SqliteDatabase('my_app.db')

   def _db_connect():
       db.connect()

   def _db_close():
       if not db.is_closed():
           db.close()

   cherrypy.engine.subscribe('before_request', _db_connect)
   cherrypy.engine.subscribe('after_request', _db_close)

General Pattern for Any Framework
---------------------------------

If your framework is not listed here, the integration follows the same
structure:

1. Find the hook that runs before every request handler.
2. Call ``db.connect()`` there.
3. Find the hook that runs after every request (success and error both).
4. Call ``db.close()`` there if the connection is open.

Any WSGI middleware that wraps the application callable can also manage this:

.. code-block:: python

   class PeeweeMiddleware:
       def __init__(self, app, database):
           self.app = app
           self.db = database

       def __call__(self, environ, start_response):
           self.db.connect()
           try:
               return self.app(environ, start_response)
           finally:
               if not self.db.is_closed():
                   self.db.close()

   # Wrap your WSGI app:
   application = PeeweeMiddleware(application, db)

This is a synchronous pattern. An async (:ref:`pwasyncio`) database is driven by
an ASGI middleware instead. ``db.connect()`` and ``db.close()`` only work inside
the async bridge. See the ``PeeweeConnectionMiddleware`` in the :ref:`fastapi`
and :ref:`starlette` sections for examples.
