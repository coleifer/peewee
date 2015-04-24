todo
====

* Database column defaults?
* Pre-compute foreign keys, attributes and join types (forward-ref or backref) in the `AggregateQueryResultWrapper.iterate` method.
* Improve the performance of the `QueryCompiler`.

version 3?
==========

* Follow foreign keys through fields, e.g. Tweet.user.username, or Comment.blog.user.username.
* Simplify the node types:
  * Node (base class)
  * Expression
  * Quoted
  * Clause
* Parsing should be context-aware, which would reduce some of the hacks, particularly around `IN` + lists.
