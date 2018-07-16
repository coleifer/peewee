
.. image:: http://media.charlesleifer.com/blog/photos/p1423749536.32.png

peewee
======
This is just `peewee-2.10.2 <https://github.com/coleifer/peewee>` with some changes we need:

* Simple LEFT JOIN LATERAL. No need make subquery, just join to model.
.. code-block:: python

    # make some compound select query
    subq = ModelB.select(ModelB.id).where(ModelB.id > ModelA.id).limit(1)
    # make query lateral joining subquery
    ModelA.select(ModelA, subq.c.id).join(subq, join_type=JOIN.LATERAL)

* Add off argument to for_update method
.. code-block:: python
	# Lock books of author name == John
	Book.select().join(Author).where(Author.name == 'John').for_update(of=Book)