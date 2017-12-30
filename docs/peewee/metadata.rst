.. _metadata:

Model Metadata
==============

The following table lists the names of supported ``Meta`` attributes. While
most of these settings are inheritable, some are table-specific and will not be
inherited by subclasses.

===================== =================================================================== ================
Option                Meaning                                                             Inheritable?
===================== =================================================================== ================
``database``          database model is bound to                                          yes
``table_name``        name of the underlying database table                               no
``table_function``    callable used to dynamically generate table name from class         yes
``indexes``           list of indexes for the table                                       yes
``primary_key``       a :py:class:`CompositeKey` object                                   yes
``constraints``       a list of table constraints                                         yes
``schema``            the database schema for the table                                   yes
``only_save_dirty``   when calling ``model.save()``, only save fields that were modified. yes
``table_alias``       an alias to use for the table in queries                            no
``depends_on``        a list of :py:class:`Model` classes this class depends on           no
``options``           a dictionary of options (used by SQLite)                            yes
``without_rowid``     create table without rowid (SQLite only)                            no
===================== =================================================================== ================

Here is an example showing how inheritable and non-inheritable attributes work:

.. code-block:: pycon

    >>> db = SqliteDatabase(':memory:')
    >>> class ModelOne(Model):
    ...     class Meta:
    ...         database = db
    ...         table_name  = 'model_one_tbl'
    ...
    >>> class ModelTwo(ModelOne):
    ...     pass
    ...
    >>> ModelOne._meta.database is ModelTwo._meta.database
    True
    >>> ModelOne._meta.db_table == ModelTwo._meta.db_table
    False

Meta.primary_key
^^^^^^^^^^^^^^^^

The ``Metadata.primary_key`` attribute is used to specify either a
:py:class:`CompositeKey` or to indicate that the model has *no* primary key.

Composite primary keys are keys that consist of more than one column. For
example, a many-to-many through table might declare a primary key like this:

.. code-block:: python

    class Relationship(BaseModel):
        from_user = ForeignKeyField(User, backref='relationships')
        to_user = ForeignKeyField(User, backref='related_to')

        class Meta:
            primary_key = CompositeKey('from_user', 'to_user')

To indicate that a model does not have a primary key, set the attribute to
``False``:

.. code-block:: python

    class NoPrimaryKey(BaseModel):
        data = IntegerField()

        class Meta:
            primary_key = False
