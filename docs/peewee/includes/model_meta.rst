The following attributes can be used to provide additional configuration for your model. Not all values are inheritable by subclasses, as indicated by the *Inheritable* column.

===================   ==============================================   ============
Option                Meaning                                          Inheritable?
===================   ==============================================   ============
``database``          database for model                               yes
``db_table``          name of the table to store data                  no
``indexes``           a list of fields to index                        yes
``order_by``          a list of fields to use for default ordering     yes
``primary_key``       a :py:class:`CompositeKey` instance              yes
``table_alias``       an alias to use for the table in queries         no
===================   ==============================================   ============
