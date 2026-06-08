.. _json-field:

Cross-backend JSONField
=======================

.. module:: playhouse.json_field

The ``playhouse.json_field`` module provides a single :class:`JSONField` that
works across SQLite (3.38+), Postgresql, and MySQL/MariaDB with a uniform
API and a chainable :class:`JSONPath` for sub-element access.

It is intentionally small and opinionated - see :ref:`json-field-backend-specific`
for the per-backend modules with atomic mutation and engine-specific operators.

.. contents:: On this page
   :local:
   :depth: 1

Getting Started
---------------

.. code-block:: python

   from peewee import *
   from playhouse.json_field import JSONField

   db = SqliteDatabase(':memory:')

   class Doc(Model):
       data = JSONField(null=True)

       class Meta:
           database = db

   db.connect()
   db.create_tables([Doc])

   Doc.create(data={
       'name': 'huey',
       'tags': ['cat', 'white', 'fluffy'],
       'age': 14,
       'profile': {'social': {'fb': 'huey.cat'}}})

   # Read the whole document.
   m = Doc.select().get()
   m.data  # {'name': 'huey', 'tags': [...], 'profile': {...}}

Path access uses ``__getitem__`` (chainable) or :meth:`~JSONField.path`
to extract sub-elements. The result is a :class:`JSONPath` you can use in
``SELECT``, ``WHERE``, ``ORDER BY``, etc.:

.. code-block:: python

   # Equivalent - both return a JSONPath.
   Doc.data['profile']['social']['fb']
   Doc.data.path('profile', 'social', 'fb')

   # Filter rows by a nested value.
   Doc.select().where(Doc.data['name'] == 'huey')
   Doc.select().where(Doc.data['tags'][0] == 'cat')

   # Pull out a sub-document.
   for doc in Doc.select(Doc.data['profile'].alias('profile')):
       print(doc.profile['fb'])  # 'huey.cat'

Equality on a path is structural where the backend supports it (Postgresql
``jsonb``, MySQL ``JSON``) and canonical-text byte-compare on SQLite. Lists,
dictionaries, integers, booleans, and strings all work as right-hand-side
values:

.. code-block:: python

   Doc.select().where(Doc.data['profile'] == {'social': {'fb': 'huey.cat'}})
   Doc.select().where(Doc.data['tags'] == ['cat', 'white', 'fluffy'])
   Doc.select().where(Doc.data['age'] == 14)

For typed comparisons, ordering, or string operators on a path, see
:ref:`typed access <json-field-typed-access>` and :ref:`json-field-text-mode` below.

.. _json-field-api:

JSONField
---------

.. class:: JSONField(dumps=None, loads=None, **kwargs)

   :param dumps: Custom JSON serializer. Defaults to ``json.dumps``.
   :param loads: Custom JSON deserializer. Defaults to ``json.loads``.

   Stores Python ``dict``, ``list``, scalar (``str``/``int``/``float``/``bool``),
   or ``None`` values as JSON. The column type used by ``CREATE TABLE`` is
   chosen per backend:

   * SQLite: ``TEXT`` (avoids SQLite's ``NUMERIC`` affinity coercing
     numeric-looking JSON to integers).
   * Postgresql: ``JSONB``.
   * MySQL / MariaDB: ``JSON``.

   .. note::
      On SQLite, the field requires SQLite 3.38+ (for the ``->`` / ``->>``
      operators). Use :class:`playhouse.sqlite_ext.JSONField` on older SQLite
      installs.

      For Postgresql, to specify a ``GIN`` or ``GIST`` index use ``index_type``:

      .. code-block:: python

          # Postgres only.
          data = JSONField(index=True, index_type='GIN')  # or GIST.

   .. method:: __getitem__(key)

      :param key: a dict key (``str``) or array index (``int``).
      :rtype: JSONPath

      Return a :class:`JSONPath` rooted at the given key. Chains:

      .. code-block:: python

         Doc.data['profile']['social']['fb']
         Doc.data['tags'][0]
         Doc.data['tags'][-1]  # negative indices supported on SQLite + Postgresql

   .. method:: path(*keys)

      :rtype: JSONPath

      Equivalent to chained :meth:`__getitem__`:

      .. code-block:: python

         Doc.data.path('profile', 'social', 'fb')
         # Same as Doc.data['profile']['social']['fb']

   .. method:: __eq__(rhs)
               __ne__(rhs)

      Equality on the full document. The right-hand side is serialized
      through ``dumps`` and compared structurally on Postgresql (``jsonb =
      jsonb``) and MySQL (``JSON_EQUALS`` on MariaDB-aware comparators). On
      SQLite the comparison is byte-compare against the canonical JSON
      representation produced by ``json()``.

      .. code-block:: python

         Doc.select().where(Doc.data == {'k': 'v'})  # structural where supported
         Doc.select().where(Doc.data == None)        # column IS NULL

   .. note::

      On SQLite, MySQL, and MariaDB, the full-document equality is a byte
      comparison of the canonical JSON text. Two dictionaries with the
      same contents but different insertion order may *not* match. If you
      need order-insensitive document equality on those backends, pass
      ``dumps=functools.partial(json.dumps, sort_keys=True)`` so both sides
      are canonicalized. On Postgresql the comparison is structural and
      key order does not matter.

   .. method:: length()

      Return the array length of the root document. See
      :meth:`JSONPath.length` for the per-backend behavior on non-arrays.

   .. method:: update(value)

      Return an UPDATE-clause expression that merges ``value`` into the root
      document. **The semantics intentionally diverge by backend** -
      see the "update divergence" note below.

      .. code-block:: python

         Doc.update(data=Doc.data.update({'new_field': 1})).execute()

   .. method:: contains(value)
               contained_by(value)
               has_key(key)
               has_keys(key_list)
               has_any_keys(key_list)

      JSON structural containment and key-existence predicates. Postgresql
      uses ``@>`` / ``<@`` / ``?`` / ``?&`` / ``?|``; MySQL / MariaDB use
      ``JSON_CONTAINS`` / ``JSON_CONTAINS_PATH``. **Not supported on
      SQLite** - calling any of these on a SQLite-backed model raises
      :class:`peewee.NotSupportedError`.

      .. code-block:: python

         Doc.select().where(Doc.data.contains({'env': 'prod'}))
         Doc.select().where(Doc.data.has_key('email'))
         Doc.select().where(Doc.data.has_keys(['env', 'region']))

.. warning::

   :meth:`update` has intentionally **divergent semantics across backends**:

   * **SQLite, MySQL, MariaDB** - RFC-7396 deep merge via ``json_patch`` /
     ``JSON_MERGE_PATCH``. Nested objects are merged recursively;
     ``null`` values **delete** the key.
   * **Postgresql** - shallow concat via the ``||`` operator. Top-level
     keys are overwritten; **nested objects are replaced wholesale**;
     ``null`` is stored as JSON null and does **not** delete the key.

   Concrete example - same Python call, three different results:

   .. code-block:: python

      Doc.create(data={'k': 'v', 'nested': {'a': 1, 'b': 2}})
      Doc.update(data=Doc.data.update({'k': None,
                                       'nested': {'b': 99}})).execute()

      # SQLite / MySQL / MariaDB:
      #   {'nested': {'a': 1, 'b': 99}}      ('k' deleted; nested merged)
      # Postgresql:
      #   {'k': None, 'nested': {'b': 99}}   ('k' kept as null; nested overwritten)

   If you write portable code, prefer top-level key adds (where all three
   agree) and avoid relying on either semantic for nested objects or null
   deletion.

JSONPath
--------

.. class:: JSONPath

   Returned by :meth:`JSONField.__getitem__` and :meth:`JSONField.path`.
   Represents an extraction at a path within the JSON document. SQL emission
   uses ``->`` on SQLite and Postgresql or ``JSON_EXTRACT`` on MySQL by
   default. Text-mode uses ``->>`` or ``JSON_UNQUOTE(JSON_EXTRACT(...))``.

   .. method:: __getitem__(key)

      Extend the path with another key:

      .. code-block:: python

         Doc.data['profile']['social']     # path = ('profile', 'social')
         Doc.data['tags'][0]               # path = ('tags', 0)

   .. method:: path(*keys)

      Variadic equivalent of chained :meth:`__getitem__`:

      .. code-block:: python

         Doc.data.path('profile', 'social', 'fb')

   .. method:: as_text(as_text=True)

      :rtype: JSONPath

      Return the path value in *text mode*. SQL emission switches to the
      text-extract operator (``->>`` on SQLite/Postgresql,
      ``JSON_UNQUOTE(JSON_EXTRACT(...))`` on MySQL). In text mode, the returned
      value is a raw scalar (no JSON quoting) and equality is byte-text
      compare.

      .. code-block:: python

         Doc.data['name'].as_text() == 'huey'
         Doc.data['name'].as_text().ilike('h%')

      Pattern-matching operators (:meth:`like`, :meth:`ilike`,
      :meth:`startswith`, :meth:`endswith`, :meth:`contains`, :meth:`regexp`,
      :meth:`iregexp`) automatically apply ``as_text()`` so calling them on
      a path does the right thing without needing ``.as_text()`` explicitly.

   .. _json-field-typed-access:

   .. method:: as_int()

      :rtype: peewee.Cast

      Return the path's text extract cast to the backend's integer type. Use
      for numeric comparisons:

      .. code-block:: python

         Doc.select().where(Doc.data['count'].as_int() > 10)
         Doc.select().order_by(Doc.data['count'].as_int())

   .. method:: as_float()

      :rtype: peewee.Cast

      Return the path's text extract cast to the backend's floating-point
      type.

      .. code-block:: python

         Doc.select().where(Doc.data['rating'].as_float() > 4.5)

   .. method:: __eq__(rhs)
               __ne__(rhs)

      Equality on the path. In default (JSON) mode the right-hand side is
      canonicalized through the field's value wrapper (``fn.json(...)`` on
      SQLite, the psycopg ``Jsonb`` adapter on Postgresql, ``JSON_COMPACT``
      on MySQL) so the comparison works across backends:

      .. code-block:: python

         Doc.select().where(Doc.data['name'] == 'huey')
         Doc.select().where(Doc.data['count'] == 42)
         Doc.select().where(Doc.data['profile'] == {'fb': 'huey.cat'})

      In ``.as_text()`` mode the right-hand side is compared as plain text.

      Comparison against ``None`` is special, see :meth:`is_null`.

   .. method:: is_null(is_null=True)

      Path-level "is empty" check. Matches rows where the extracted value
      is effectively absent, covering three distinct storage states:

      * Underlying column is SQL ``NULL``.
      * The key is missing from the JSON document.
      * The key is present but the stored value is JSON ``null``.

      All three return Python ``None`` when extracted, and ``is_null()``
      matches them uniformly. ``is_null(False)`` matches rows where the
      path resolves to a non-null Python value.

      .. code-block:: python

         # Rows where data['profile'] is missing, null, or column is NULL.
         Doc.select().where(Doc.data['profile'].is_null())

         # Rows where data['profile'] has a non-null value.
         Doc.select().where(Doc.data['profile'].is_null(False))

      ``path == None`` and ``path != None`` are equivalent to ``is_null()``
      and ``is_null(False)`` respectively.

   .. note::

      On MariaDB and MySQL prior to 8.0.24, ``JSON_UNQUOTE`` of a stored
      JSON ``null`` returns the literal string ``'null'`` instead of SQL
      ``NULL``, so :meth:`is_null` does not match stored JSON null on
      those versions. Missing keys and column SQL NULL are still matched.

   .. method:: in_(rhs)
               not_in(rhs)

      Membership test. In default mode each right-hand-side element is
      canonicalized through the field's value wrapper. In ``.as_text()``
      mode elements are compared as plain text.

      .. code-block:: python

         Doc.select().where(Doc.data['name'].in_(['huey', 'mickey']))

   .. method:: __lt__
               __le__
               __gt__
               __ge__
               between(lo, hi)

      Ordering and range comparisons. The right-hand side is canonicalized
      through the field's value wrapper. Per-backend behavior:

      * **Postgresql** - structural ``jsonb`` ordering (type class then value).
      * **MySQL / MariaDB** - JSON-typed comparison rules.
      * **SQLite** - byte-text comparison after wrapping in ``json()``;
        ``'10' > '2'`` is lexicographic, **which is rarely what you want**.

      For portable strict-numeric ordering, use :meth:`as_int` or
      :meth:`as_float` first:

      .. code-block:: python

         # Backend-native ordering (lexicographic on SQLite!)
         Doc.select().where(Doc.data['count'] > 10)

         # Strict numeric ordering on every backend.
         Doc.select().where(Doc.data['count'].as_int() > 10)

   .. method:: like(rhs)
               ilike(rhs)
               regexp(rhs)
               iregexp(rhs)

      Pattern-matching operators. Each automatically applies ``as_text()``
      to the path before comparing.

      .. code-block:: python

         Doc.select().where(Doc.data['name'].ilike('h%'))
         Doc.select().where(Doc.data['name'].regexp(r'^h'))

   .. method:: startswith(rhs)
               endswith(rhs)

      Substring shortcuts that wrap the right-hand side in ``%`` wildcards.
      Like :meth:`like`, they auto-route through ``as_text()``:

      .. code-block:: python

         Doc.select().where(Doc.data['name'].startswith('h'))

   .. method:: contains(rhs)

      JSON structural containment. Dispatches through the helper: ``@>`` on
      Postgresql, ``JSON_CONTAINS`` on MySQL / MariaDB.

      Raises :class:`NotImplementedError` on SQLite.

      .. code-block:: python

         # Text substring.
         Doc.select().where(Doc.data['name'].contains('uey'))

         # JSON structural containment (sub-array membership).
         Doc.select().where(Doc.data['tags'].contains(['python']))

   .. method:: set(value)

      Return an UPDATE-clause expression that writes ``value`` at this path.
      Uses ``json_set`` / ``jsonb_set`` / ``JSON_SET`` per backend. Existing
      values are replaced; ``value=None`` writes JSON ``null`` (not SQL
      NULL):

      .. code-block:: python

         Doc.update(data=Doc.data['count'].set(99)).execute()
         Doc.update(data=Doc.data['profile'].set({'env': 'prod'})).execute()

      .. note::

         **Missing intermediate keys silently no-op on all three backends.**
         ``data['a']['b']['c'].set(1)`` on ``data={}`` returns ``data``
         unchanged. The leaf is created only when the parent exists.

   .. method:: remove()

      Return an UPDATE-clause expression that removes the value at this path.
      Uses ``json_remove`` / ``#-`` / ``JSON_REMOVE`` per backend.

      .. code-block:: python

         Doc.update(data=Doc.data['stale_key'].remove()).execute()

   .. method:: length()

      Return the array length at this path. On non-array values the result
      diverges by backend:

      * **SQLite** - returns ``0`` for non-arrays.
      * **Postgresql** - raises ``cannot get array length of a non-array``.
      * **MySQL / MariaDB** - returns object key count for objects,
        ``1`` for scalars.

      Use only on values you know are arrays, or be prepared for the
      backend-specific semantics.

      .. code-block:: python

         Doc.select(Doc.data['tags'].length().alias('n_tags'))

   .. method:: contained_by(value)

      Inverse of :meth:`contains` - test whether the value at this path is a
      subset of ``value``. Postgresql ``<@``, MySQL / MariaDB
      ``JSON_CONTAINS(value, lhs)``. Not supported on SQLite.

      .. code-block:: python

         Doc.select().where(Doc.data['tags'].contained_by(
             ['python', 'orm', 'sql']))

   .. method:: has_key(key)
               has_keys(key_list)
               has_any_keys(key_list)

      Test whether the value at this path is an object containing the given
      key(s). Postgresql uses the ``?`` / ``?&`` / ``?|`` operators; MySQL /
      MariaDB use ``JSON_CONTAINS_PATH``. Not supported on SQLite.

      .. code-block:: python

         Doc.select().where(Doc.data.has_key('email'))
         Doc.select().where(Doc.data['profile'].has_keys(['env', 'region']))
         Doc.select().where(Doc.data.has_any_keys(['admin', 'staff']))

.. _json-field-null-semantics:

NULL semantics
--------------

A JSON document has three distinct "absent" states, all of which collapse to
Python ``None`` when extracted:

1. **Column SQL ``NULL``** - ``data=None`` was stored.
2. **Missing key** - the document doesn't contain the path being queried.
3. **JSON ``null``** - the path resolves to a literal JSON ``null`` value
   (e.g., ``data={'k': None}``).

Path-level queries treat all three uniformly:

.. code-block:: python

   Doc.create(data={'k': 'value'})      # row A: key present, non-null
   Doc.create(data={'k': None})         # row B: key present, JSON null
   Doc.create(data={})                  # row C: key missing
   Doc.create(data=None)                # row D: column SQL NULL

   # Matches B, C, D (all three null-ish cases):
   Doc.select().where(Doc.data['k'].is_null())
   Doc.select().where(Doc.data['k'] == None)

   # Matches A only:
   Doc.select().where(Doc.data['k'].is_null(False))
   Doc.select().where(Doc.data['k'] != None)

Field-level NULL checks **only** match column SQL NULL:

.. code-block:: python

   # Matches D only (the column itself is NULL):
   Doc.select().where(Doc.data.is_null())
   Doc.select().where(Doc.data == None)

If you need to distinguish JSON ``null`` from a missing key, drop down to
the backend's ``JSON_TYPE`` / ``jsonb_typeof`` function:

.. code-block:: python

   # Postgresql
   from peewee import fn
   Doc.select().where(fn.jsonb_typeof(Doc.data['k']) == 'null')

   # SQLite
   Doc.select().where(fn.json_type(Doc.data, '$.k') == 'null')

   # MySQL
   Doc.select().where(fn.json_type(Doc.data['k']) == 'NULL')

.. _json-field-text-mode:

Text mode and typed casts
-------------------------

The default path mode returns the value in *JSON form* - JSON-encoded text
(SQLite/MySQL) or a deserialized Python value via the driver (Postgresql).
Equality, ordering, and ``in_`` work against this form.

``.as_text()`` flips the path to *text mode*, returning the raw scalar text
(``->>`` / ``JSON_UNQUOTE``). Text mode is appropriate for:

* String comparisons against plain text columns (e.g., joins).
* Pattern matching (``LIKE``, regex). The pattern operators auto-apply
  ``as_text()`` so this is usually implicit.
* Numeric or boolean comparison after an explicit cast (or use
  :meth:`~JSONPath.as_int` / :meth:`~JSONPath.as_float`).

.. code-block:: python

   # Join a JSON-path value to a plain text column.
   Doc.select().join(Tag, on=(Tag.name == Doc.data['tag'].as_text()))

   # Pattern match (ilike is auto-text).
   Doc.select().where(Doc.data['name'].ilike('h%'))

   # Strict numeric comparison.
   Doc.select().where(Doc.data['count'].as_int() > 10)

Mutation
--------

The field and path expose a portable subset of atomic mutation primitives
suitable for use inside ``UPDATE`` statements:

============= ==================== ==================== =============================
Method        On JSONField (root)  On JSONPath          Cross-backend?
============= ==================== ==================== =============================
``set(v)``    -                    yes                  yes
``remove()``  -                    yes                  yes
``length()``  yes                  yes                  yes (with caveats - see method)
``update(v)`` yes                  -                    yes (**divergent semantics**)
============= ==================== ==================== =============================

.. code-block:: python

   # Set a path (creates or replaces).
   Doc.update(data=Doc.data['count'].set(99)).execute()

   # Remove a path.
   Doc.update(data=Doc.data['stale'].remove()).execute()

   # Array length.
   Doc.select(Doc.data['tags'].length())

   # Document-level merge (see the warning above about divergence).
   Doc.update(data=Doc.data.update({'last_seen': '2026-01-01'})).execute()

For mutation patterns outside this subset (path-level update, ``insert``
vs. ``replace`` semantics, ``json_each`` / ``jsonb_path_query``, etc.),
either read-modify-save the row in Python:

.. code-block:: python

   doc = Doc.get_by_id(1)
   doc.data['tags'].append('new')
   doc.data['count'] = 5
   doc.save()

or drop down to ``fn.*`` directly:

.. code-block:: python

   from peewee import fn, Value

   # SQLite
   Doc.update(data=fn.json_set(Doc.data, '$.count', 99)).execute()

   # Postgresql
   Doc.update(data=fn.jsonb_set(Doc.data, '{count}', Value('99'))).execute()

   # MySQL / MariaDB
   Doc.update(data=fn.JSON_SET(Doc.data, '$.count', 99)).execute()

.. _json-field-backend-specific:

Backend-specific Modules
------------------------

This module is deliberately the portable subset. For engine-specific operators
such as atomic mutation methods, ``jsonb`` operators, ``json_each`` /
``json_tree``, ``JSON_TABLE``, etc. use the corresponding playhouse module:

* :class:`playhouse.postgres_ext.BinaryJSONField` - full ``jsonb`` operator
  surface (``jsonb_path_query*``, etc.) plus the engine-specific mutation
  helpers.
* :class:`playhouse.sqlite_ext.JSONField` - SQLite-specific
  ``replace`` / ``insert`` / ``append`` on the field and path, plus
  ``children`` / ``tree`` for recursion via ``json_each`` and ``json_tree``.
* :class:`playhouse.mysql_ext.JSONField` - basic MySQL ``JSON_EXTRACT`` access.
