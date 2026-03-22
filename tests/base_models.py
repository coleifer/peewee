"""
Shared model definitions for the core Peewee test suite.

These models form a curated library of relational patterns used by the
SQL-generation tests (model_sql.py), integration tests (models.py), and
supporting test modules (schema.py, fields.py, db_tests.py, results.py,
transactions.py). They are the "Tier 1" models in the test suite's tiered
model strategy:

  Tier 1 — Shared core models (this file). Stable, well-known models used
           across many test modules. Changing a name or field here affects
           SQL assertions in dozens of tests, so changes should be rare.

  Tier 2 — Module-local shared models. Defined at the top of individual
           test modules, used by multiple TestCase classes within that module.

  Tier 3 — TestCase-local models. Defined immediately before the single
           TestCase class that uses them, for testing specific field types
           or edge cases not covered by the shared set.

Design principles:
  - Each model exists to exercise a specific relational pattern or ORM feature.
  - Names are kept short for readability in SQL assertions.
  - All models inherit from TestModel (base.py), which sets database=db and
    legacy_table_names=False.
  - Models are ordered by dependency: independent models first, then models
    with foreign keys to earlier models.

WARNING: Renaming a model or field changes the generated table/column names,
which will break SQL assertion strings in model_sql.py and other SQL-gen tests.
Always grep for the old name across the entire test suite before renaming.
"""
from peewee import *

from .base import TestModel


# ---------------------------------------------------------------------------
# Person / Note — basic FK relationship with indexes and nullable date field.
#
# Person exercises: CharField fields, DateField with index and null=True,
# compound unique index on (first, last). Used heavily in model_sql.py for
# SELECT/INSERT/UPDATE/DELETE SQL generation, in schema.py for DDL tests,
# and in fields.py for FK constraint tests.
#
# Note exercises: ForeignKeyField to Person, TextField. The simplest
# parent-child FK pattern. Used for join SQL generation and FK constraint
# tests.
#
# NOTE: db_tests.py and prefetch_tests.py define their own local Person
# and Note models with different fields — those are intentionally separate.
# ---------------------------------------------------------------------------

class Person(TestModel):
    first = CharField()
    last = CharField()
    dob = DateField(index=True, null=True)

    class Meta:
        indexes = (
            (('first', 'last'), True),
        )


class Note(TestModel):
    author = ForeignKeyField(Person)
    content = TextField()


# ---------------------------------------------------------------------------
# Category — self-referential FK with non-integer primary key.
#
# Exercises: ForeignKeyField('self'), CharField as primary_key, nullable
# self-FK (parent=null for root nodes). This is the primary model for
# recursive CTE tests (TestCTEIntegration) and self-referential query tests.
# Also used in schema.py DDL tests and db_tests.py introspection tests.
# ---------------------------------------------------------------------------

class Category(TestModel):
    parent = ForeignKeyField('self', backref='children', null=True)
    name = CharField(max_length=20, primary_key=True)


# ---------------------------------------------------------------------------
# Relationship — multiple foreign keys to the same model.
#
# Exercises: two ForeignKeyField columns pointing to the same model (Person),
# with distinct backrefs. Tests multi-FK join resolution, delete cascading
# through multiple FK paths, and subquery joins.
# ---------------------------------------------------------------------------

class Relationship(TestModel):
    from_person = ForeignKeyField(Person, backref='relations')
    to_person = ForeignKeyField(Person, backref='related_to')


# ---------------------------------------------------------------------------
# Register — minimal single-field model.
#
# Exercises: the simplest possible model (one IntegerField). Used as the
# workhorse for transaction tests (transactions.py) where the test logic
# needs a trivial INSERT/SELECT cycle without FK complexity. Also used
# in compound SELECT tests (UNION of Register values).
# ---------------------------------------------------------------------------

class Register(TestModel):
    value = IntegerField()


# ---------------------------------------------------------------------------
# User / Account / Tweet / Favorite — social media graph.
#
# This is the most heavily used model group in the test suite (~66 TestCase
# classes reference User). It provides the canonical "has-many" and
# "many-to-many-like" patterns.
#
# User exercises: CharField, explicit table_name override ('users'). The
# explicit table_name is important — many SQL assertions reference "users"
# rather than the default "user" that legacy_table_names=False would produce.
#
# Account exercises: nullable ForeignKeyField (user is optional). Tests
# LEFT OUTER JOIN behavior and nullable FK handling.
#
# Tweet exercises: ForeignKeyField to User, TextField, TimestampField.
# The primary "child" model for join, subquery, window function, RETURNING,
# and compound SELECT tests.
#
# Favorite exercises: two ForeignKeyFields (to User and Tweet) forming a
# many-to-many join table. Tests multi-table joins, delete cascading
# through intermediate tables, and subquery filtering.
# ---------------------------------------------------------------------------

class User(TestModel):
    username = CharField()

    class Meta:
        table_name = 'users'


class Account(TestModel):
    email = CharField()
    user = ForeignKeyField(User, backref='accounts', null=True)


class Tweet(TestModel):
    user = ForeignKeyField(User, backref='tweets')
    content = TextField()
    timestamp = TimestampField()


class Favorite(TestModel):
    user = ForeignKeyField(User, backref='favorites')
    tweet = ForeignKeyField(Tweet, backref='favorites')


# ---------------------------------------------------------------------------
# Sample / SampleMeta — numeric aggregation models.
#
# Sample exercises: IntegerField + FloatField with default. The primary model
# for window function tests (partition by counter, aggregate over value),
# function coercion tests, and numeric aggregation (AVG, SUM, COUNT).
#
# SampleMeta exercises: FK parent-child with FloatField default=0.0. Tests
# default value insertion and parent-child SELECT with defaults.
# ---------------------------------------------------------------------------

class Sample(TestModel):
    counter = IntegerField()
    value = FloatField(default=1.0)


class SampleMeta(TestModel):
    sample = ForeignKeyField(Sample, backref='metadata')
    value = FloatField(default=0.0)


# ---------------------------------------------------------------------------
# A / B / C — three-level FK chain.
#
# Exercises: deep join traversal (A -> B -> C) through a linear FK chain.
# Each model has a TextField and a FK to the previous level. Used in
# model_sql.py for multi-join SQL generation, in models.py for deep
# join integration tests, and in schema.py for DDL ordering tests.
#
# NOTE: prefetch_tests.py defines its own A/B/C with different fields
# and additional FK to an X model — those are intentionally separate.
# ---------------------------------------------------------------------------

class A(TestModel):
    a = TextField()
class B(TestModel):
    a = ForeignKeyField(A, backref='bs')
    b = TextField()
class C(TestModel):
    b = ForeignKeyField(B, backref='cs')
    c = TextField()


# ---------------------------------------------------------------------------
# Emp — ON CONFLICT / upsert testing with unique constraint.
#
# Exercises: CharField with unique=True (empno), compound unique index on
# (first, last). This is the primary model for REPLACE and ON CONFLICT
# tests across all database backends. The compound unique index exercises
# multi-column conflict targets, while the single unique column (empno)
# exercises single-column conflict targets.
# ---------------------------------------------------------------------------

class Emp(TestModel):
    first = CharField()
    last = CharField()
    empno = CharField(unique=True)

    class Meta:
        indexes = (
            (('first', 'last'), True),
        )


# ---------------------------------------------------------------------------
# OCTest — ON CONFLICT with atomic update expressions.
#
# Exercises: unique CharField (a) with IntegerField defaults. Designed for
# testing ON CONFLICT DO UPDATE with arithmetic expressions (e.g.,
# SET b = b + 2). The defaults (b=0, c=0) ensure predictable starting
# values for atomic increment tests.
# ---------------------------------------------------------------------------

class OCTest(TestModel):
    a = CharField(unique=True)
    b = IntegerField(default=0)
    c = IntegerField(default=0)


# ---------------------------------------------------------------------------
# UKVP — ON CONFLICT with partial unique index.
#
# Exercises: partial index (unique on (key, value) WHERE extra > 1). This
# tests the advanced PostgreSQL/SQLite pattern where ON CONFLICT must
# include a conflict_where clause matching the partial index predicate.
# The raw SQL index definition (rather than a tuple) exercises the
# SQL-literal index path.
# ---------------------------------------------------------------------------

class UKVP(TestModel):
    key = TextField()
    value = IntegerField()
    extra = IntegerField()

    class Meta:
        # Partial index, the WHERE clause must be reflected in the conflict
        # target.
        indexes = [
            SQL('CREATE UNIQUE INDEX "ukvp_kve" ON "ukvp" ("key", "value") '
                'WHERE "extra" > 1')]


# ---------------------------------------------------------------------------
# DfltM — default value variants.
#
# Exercises three kinds of field defaults: static value (dflt1=1), callable
# default (dflt2=lambda: 2), and nullable with no default (dfltn). Used in
# model_sql.py to test INSERT SQL generation with defaults omitted, and in
# models.py (via @requires_models) to verify that defaults are applied
# correctly at the database and Python levels.
# ---------------------------------------------------------------------------

class DfltM(TestModel):
    name = CharField()
    dflt1 = IntegerField(default=1)
    dflt2 = IntegerField(default=lambda: 2)
    dfltn = IntegerField(null=True)
