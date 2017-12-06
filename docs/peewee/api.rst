.. _api:

.. py:module:: peewee

API Documentation
=================

This document specifies Peewee's APIs.

Database
--------

.. autoclass:: Database

.. autoclass:: SqliteDatabase

.. autoclass:: PostgresqlDatabase

.. autoclass:: MySQLDatabase

Query-builder
-------------

.. autoclass:: Context

.. autoclass:: Source

.. autoclass:: Table

    .. py:method:: join(dest[, join_type='INNER'[, on=None]]):

        :param Source dest: Join the table with the given destination.
        :param str join_type: Join type.
        :param on: Expression to use as join predicate.
        :returns: a :py:class:`Join` instance.

        Join this source with the destination object.

.. autoclass:: Join

.. autoclass:: CTE

.. autoclass:: ColumnBase
    :special-members:

Constants and Helpers
---------------------

.. autoclass:: Proxy

.. autodata:: JOIN
