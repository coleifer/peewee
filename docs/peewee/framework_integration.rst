.. _framework-integration:

Framework Integration
=====================

For web applications, it is common to open a connection when a request is
received, and to close the connection when the response is delivered. This
document describes how to add hooks to your web app to ensure the database
connection is handled properly.

These steps will ensure that regardless of whether you're using a simple
:class:`SqliteDatabase` or a :class:`PooledPostgresqlDatabase`, peewee will
handle the connections correctly.

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

Use ``before_request`` and ``teardown_request``:

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

For a complete Flask + Peewee application example, see :ref:`example`.

.. seealso:: :ref:`flask-utils`

.. _fastapi:

FastAPI
-------

FastAPI is an async framework and can be used with Peewee's :ref:`asyncio`
integration.

The following example demonstrates how to:

* Ensure connection is opened and closed for each request.
* Create tables/resources when app server starts.
* Shut-down connection pool when app server exits.

.. code-block:: python

   from fastapi import FastAPI
   from peewee import *
   from playhouse.pwasyncio import *


   app = FastAPI()

   db = AsyncPostgresqlDatabase('peewee_test', host='10.8.0.1', user='postgres')

   @app.middleware('http')
   async def database_connection(request, call_next):
       await db.aconnect()  # Obtain connection from connection pool.
       try:
           response = await call_next(request)
       finally:
           await db.aclose()  # Release connection back to pool.
       return response

   @app.on_event('startup')
   async def on_startup():
       async with db:
           await db.acreate_tables([Model1, Model2, Model3, ...])

   @app.on_event('shutdown')
   async def on_shutdown():
       await db.close_pool()

Example demonstrating executing an async query:

.. code-block:: python

   @app.get('/users')
   async def list_users():
       return await db.list(User.select().dicts())

   @app.post('/users')
   async def create_user(name: str):
       user = await db.run(User.create, name=name)
       return {'id': user.id, 'name': user.name}

.. seealso:: :ref:`asyncio`

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

Sanic
-----

Sanic is an async framework and can be used with Peewee's :ref:`asyncio`
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

.. seealso:: :ref:`asyncio`

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

Any WSGI or ASGI middleware that wraps the application callable can also
manage this:

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
