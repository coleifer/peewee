===================   =================   =================   =================
Field Type            Sqlite              Postgresql          MySQL
===================   =================   =================   =================
``CharField``         varchar             varchar             varchar
``TextField``         text                text                longtext
``DateTimeField``     datetime            timestamp           datetime
``IntegerField``      integer             integer             integer
``BooleanField``      smallint            boolean             bool
``FloatField``        real                real                real
``DoubleField``       real                double precision    double precision
``BigIntegerField``   integer             bigint              bigint
``DecimalField``      decimal             numeric             numeric
``PrimaryKeyField``   integer             serial              integer
``ForeignKeyField``   integer             integer             integer
``DateField``         date                date                date
``TimeField``         time                time                time
``BlobField``         blob                bytea               blob
``UUIDField``         not supported       uuid                not supported
===================   =================   =================   =================

Field initialization parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Parameters accepted by all field types and their default values:

* ``null = False`` -- boolean indicating whether null values are allowed to be stored
* ``index = False`` -- boolean indicating whether to create an index on this column
* ``unique = False`` -- boolean indicating whether to create a unique index on this column. See also :ref:`adding composite indexes <model_indexes>`.
* ``verbose_name = None`` -- string representing the "user-friendly" name of this field
* ``help_text = None`` -- string representing any helpful text for this field
* ``db_column = None`` -- string representing the underlying column to use if different, useful for legacy databases
* ``default = None`` -- any value to use as a default for uninitialized models
* ``choices = None`` -- an optional iterable containing 2-tuples of ``value``, ``display``
* ``primary_key = False`` -- whether this field is the primary key for the table
* ``sequence = None`` -- sequence to populate field (if backend supports it)
* ``constraints = None`` - a list of one or more constraints, e.g. ``[Check('price > 0')]``
* ``schema = None`` -- optional name of the schema to use, if your db supports this.

Some fields take special parameters...
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

+--------------------------------+------------------------------------------------+
| Field type                     | Special Parameters                             |
+================================+================================================+
| :py:class:`CharField`          | ``max_length``                                 |
+--------------------------------+------------------------------------------------+
| :py:class:`DateTimeField`      | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`DateField`          | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`TimeField`          | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`DecimalField`       | ``max_digits``, ``decimal_places``,            |
|                                | ``auto_round``, ``rounding``                   |
+--------------------------------+------------------------------------------------+
| :py:class:`ForeignKeyField`    | ``rel_model``, ``related_name``, ``to_field``, |
|                                | ``on_delete``, ``on_update``, ``extra``        |
+--------------------------------+------------------------------------------------+


A note on validation
^^^^^^^^^^^^^^^^^^^^

Both ``default`` and ``choices`` could be implemented at the database level as
``DEFAULT`` and ``CHECK CONSTRAINT`` respectively, but any application change would
require a schema change.  Because of this, ``default`` is implemented purely in
python and ``choices`` are not validated but exist for metadata purposes only.

To add database (server-side) constraints, use the ``constraints`` parameter.
