import unittest

from peewee import *
from peewee import __sqlite_version__

from .base import db
from .base import skip_unless
from .base import IS_SQLITE
from .base import ModelTestCase
from .base import TestModel


class Reg(TestModel):
    k = CharField()
    v = IntegerField()
    x = IntegerField()
    class Meta:
        indexes = (
            (('k', 'v'), True),
        )


returning_support = db.returning_clause or (IS_SQLITE and
                                            __sqlite_version__ >= (3, 35, 0))


@skip_unless(returning_support, 'database does not support RETURNING')
class TestReturningIntegration(ModelTestCase):
    requires = [Reg]

    def test_crud(self):
        iq = Reg.insert_many([('k1', 1, 0), ('k2', 2, 0)]).returning(Reg)
        self.assertEqual([(r.id is not None, r.k, r.v) for r in iq.execute()],
                         [(True, 'k1', 1), (True, 'k2', 2)])

        iq = (Reg
              .insert_many([('k1', 1, 1), ('k2', 2, 1), ('k3', 3, 0)])
              .on_conflict(
                  conflict_target=[Reg.k, Reg.v],
                  preserve=[Reg.x],
                  update={Reg.v: Reg.v + 1},
                  where=(Reg.k != 'k1'))
              .returning(Reg))
        ic = iq.execute()
        self.assertEqual([(r.id is not None, r.k, r.v, r.x) for r in ic], [
            (True, 'k2', 3, 1),
            (True, 'k3', 3, 0)])

        uq = (Reg
              .update({Reg.v: Reg.v - 1, Reg.x: Reg.x + 1})
              .where(Reg.k != 'k1')
              .returning(Reg))
        self.assertEqual([(r.k, r.v, r.x) for r in uq.execute()], [
            ('k2', 2, 2), ('k3', 2, 1)])

        dq = Reg.delete().where(Reg.k != 'k1').returning(Reg)
        self.assertEqual([(r.k, r.v, r.x) for r in dq.execute()], [
            ('k2', 2, 2), ('k3', 2, 1)])

    def test_returning_expression(self):
        Rs = (Reg.v + Reg.x).alias('s')
        iq = (Reg
              .insert_many([('k1', 1, 10), ('k2', 2, 20)])
              .returning(Reg.k, Reg.v, Rs))
        self.assertEqual([(r.k, r.v, r.s) for r in iq.execute()], [
            ('k1', 1, 11), ('k2', 2, 22)])

        uq = (Reg
              .update({Reg.k: Reg.k + 'x', Reg.v: Reg.v + 1})
              .returning(Reg.k, Reg.v, Rs))
        self.assertEqual([(r.k, r.v, r.s) for r in uq.execute()], [
            ('k1x', 2, 12), ('k2x', 3, 23)])

        dq = Reg.delete().returning(Reg.k, Reg.v, Rs)
        self.assertEqual([(r.k, r.v, r.s) for r in dq.execute()], [
            ('k1x', 2, 12), ('k2x', 3, 23)])

    def test_returning_types(self):
        Rs = (Reg.v + Reg.x).alias('s')
        mapping = (
            ((lambda q: q), (lambda r: (r.k, r.v, r.s))),
            ((lambda q: q.dicts()), (lambda r: (r['k'], r['v'], r['s']))),
            ((lambda q: q.tuples()), (lambda r: r)),
            ((lambda q: q.namedtuples()), (lambda r: (r.k, r.v, r.s))))

        for qconv, r2t in mapping:
            iq = (Reg
                  .insert_many([('k1', 1, 10), ('k2', 2, 20)])
                  .returning(Reg.k, Reg.v, Rs))
            self.assertEqual([r2t(r) for r in qconv(iq).execute()], [
                ('k1', 1, 11), ('k2', 2, 22)])

            uq = (Reg
                  .update({Reg.k: Reg.k + 'x', Reg.v: Reg.v + 1})
                  .returning(Reg.k, Reg.v, Rs))
            self.assertEqual([r2t(r) for r in qconv(uq).execute()], [
                ('k1x', 2, 12), ('k2x', 3, 23)])

            dq = Reg.delete().returning(Reg.k, Reg.v, Rs)
            self.assertEqual([r2t(r) for r in qconv(dq).execute()], [
                ('k1x', 2, 12), ('k2x', 3, 23)])
