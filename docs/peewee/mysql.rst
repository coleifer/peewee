.. _mysql:

MySQL and MariaDB
=================

Peewee provides alternate drivers for MySQL through ``playhouse.mysql_ext``.

.. class:: MySQLConnectorDatabase(database, **kwargs)

   Database implementation using the official `mysql-connector-python <https://dev.mysql.com/doc/connector-python/en/>`_
   driver instead of ``pymysql``.

   .. code-block:: python

      from playhouse.mysql_ext import MySQLConnectorDatabase

      db = MySQLConnectorDatabase('my_db', host='1.2.3.4', user='mysql')


.. class:: PooledMySQLConnectorDatabase(database, **kwargs)

   Connection-pooling variant of :class:`MySQLConnectorDatabase`.


.. class:: MariaDBConnectorDatabase(database, **kwargs)

   Database implementation using the `mariadb-connector <https://mariadb-corporation.github.io/mariadb-connector-python/>`_
   driver.

   .. note::
      Does **not** accept ``charset``, ``sql_mode``, or ``use_unicode``
      parameters (charset is always ``utf8mb4``).

   .. code-block:: python

      from playhouse.mysql_ext import MariaDBConnectorDatabase

      db = MariaDBConnectorDatabase('my_db', host='1.2.3.4', user='mysql')

.. class:: PooledMariaDBConnectorDatabase(database, **kwargs)

   Connection-pooling variant of :class:`MariaDBConnectorDatabase`.


MySQL-specific helpers:

.. module:: playhouse.mysql_ext:

.. class:: JSONField()
   :noindex:

   Extends :class:`TextField` with transparent JSON encoding/decoding.

   .. method:: extract(path)

      Extract a value from a JSON document at the given JSON path
      (e.g. ``'$.key'``).

.. function:: Match(columns, expr, modifier=None)
   :noindex:

   Helper for MySQL full-text search using ``MATCH ... AGAINST`` syntax.

   :param columns: A single :class:`Field` or a tuple of fields.
   :param str expr: Full-text search expression.
   :param str modifier: Optional modifier, e.g. ``'IN BOOLEAN MODE'``.

   .. code-block:: python

       from playhouse.mysql_ext import Match

       Post.select().where(
           Match((Post.title, Post.body), 'python asyncio',
                 modifier='IN BOOLEAN MODE'))
