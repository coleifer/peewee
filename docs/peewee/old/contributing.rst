.. _contributing:

Contributing
============

In order to continually improve, Peewee needs the help of developers like you. Whether it's contributing patches, submitting bug reports, or just asking and answering questions, you are helping to make Peewee a better library.

In this document I'll describe some of the ways you can help.

Patches
-------

Do you have an idea for a new feature, or is there a clunky API you'd like to improve? Before coding it up and submitting a pull-request, `open a new issue <https://github.com/coleifer/peewee/issues/new>`_ on GitHub describing your proposed changes. This doesn't have to be anything formal, just a description of what you'd like to do and why.

When you're ready, you can submit a pull-request with your changes. Successful patches will have the following:

* Unit tests.
* Documentation, both prose form and general :ref:`API documentation <api>`.
* Code that conforms stylistically with the rest of the Peewee codebase.

Bugs
----

If you've found a bug, please check to see if it has `already been reported <https://github.com/coleifer/peewee/issues/>`_, and if not `create an issue on GitHub <https://github.com/coleifer/peewee/issues/new>`_. The more information you include, the more quickly the bug will get fixed, so please try to include the following:

* Traceback and the error message (please `format your code <https://help.github.com/articles/markdown-basics/>`_!)
* Relevant portions of your code or code to reproduce the error
* Peewee version: ``python -c "from peewee import __version__; print(__version__)"``
* Which database you're using

If you have found a bug in the code and submit a failing test-case, then hats-off to you, you are a hero!

Questions
---------

If you have questions about how to do something with peewee, then I recommend either:

* Ask on StackOverflow. I check SO just about every day for new peewee questions and try to answer them. This has the benefit also of preserving the question and answer for other people to find.
* Ask in IRC, ``#peewee`` on freenode. I always answer questions, but it may take a bit to get to them.
* Ask on the mailing list, https://groups.google.com/group/peewee-orm
