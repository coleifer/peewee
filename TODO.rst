todo
====

* Join and .join() are very model-centric, but *should* be able to accept an
  arbitrary single-source (table or select).
* Clean up pwiz...it's a ghetto.

Queries to support?

* create index <myidx> on table (some_col COLLATE NOCASE ASC) where foo > 3
* create (temp) [table/view] <tblname> as select ...
