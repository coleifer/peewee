"""
Querying using an "ISBL"-like syntax, inspired by

https://github.com/akrito/horrorm
http://www.reddit.com/r/programming/comments/2wycq/given_that_ruby_fans_like_the_idea_of_dsls_its/c2x1t2

Example ISBL:
(t1 * t2) : c1 = v1, c2 = v2 % projection

Swee'pea:
(t1 * t2) ** (c1 == v1, c2 == v2) % (t1.f1, t1.f2, t2.f1)
"""
from peewee import *
from peewee import BaseModel
_Model = Model


class T(object):
    def __init__(self, *models):
        self.models = list(models)
        self.query = None
        self.projection = None
        self.ordering = None

    def __mul__(self, rhs):
        if isinstance(rhs, T):
            self.models.extend(rhs.models)
        else:
            self.models.append(rhs)
        return self

    def __pow__(self, rhs):
        self.query = rhs
        return self

    def __mod__(self, rhs):
        if not isinstance(rhs, (list, tuple)):
            rhs = [rhs]
        self.projection = rhs
        return self

    def __lshift__(self, rhs):
        self.ordering = rhs
        return self

    def q(self):
        if self.projection:
            select = {}
            for field in self.projection:
                select.setdefault(field.model, [])
                select[field.model].append(field.name)
        else:
            select = dict((m, ['*']) for m in self.models)

        sq = self.models[0].select(select)
        if self.ordering:
            sq = sq.order_by(self.ordering)

        for model in self.models[1:]:
            sq = sq.join(model)

        if self.query:
            sq = sq.where(self.query)

        return sq.naive()

    def __iter__(self):
        return iter(self.q())


class ISBLBaseModel(BaseModel):
    def __mul__(cls, rhs):
        return T(cls) * rhs

    def __pow__(cls, rhs):
        return T(cls) ** rhs

    def __mod__(cls, rhs):
        return T(cls) % rhs

    def __lshift__(cls, rhs):
        return T(cls) << rhs

class Model(_Model):
    __metaclass__ = ISBLBaseModel
