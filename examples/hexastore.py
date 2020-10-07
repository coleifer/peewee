try:
    from functools import reduce
except ImportError:
    pass
import operator

from peewee import *


class Hexastore(object):
    def __init__(self, database=':memory:', **options):
        if isinstance(database, str):
            self.db = SqliteDatabase(database, **options)
        elif isinstance(database, Database):
            self.db = database
        else:
            raise ValueError('Expected database filename or a Database '
                             'instance. Got: %s' % repr(database))

        self.v = _VariableFactory()
        self.G = self.get_model()

    def get_model(self):
        class Graph(Model):
            subj = TextField()
            pred = TextField()
            obj = TextField()
            class Meta:
                database = self.db
                indexes = (
                    (('pred', 'obj'), False),
                    (('obj', 'subj'), False),
                )
                primary_key = CompositeKey('subj', 'pred', 'obj')

        self.db.create_tables([Graph])
        return Graph

    def store(self, s, p, o):
        self.G.create(subj=s, pred=p, obj=o)

    def store_many(self, items):
        fields = [self.G.subj, self.G.pred, self.G.obj]
        self.G.insert_many(items, fields=fields).execute()

    def delete(self, s, p, o):
        return (self.G.delete()
                .where(self.G.subj == s, self.G.pred == p, self.G.obj == o)
                .execute())

    def query(self, s=None, p=None, o=None):
        fields = (self.G.subj, self.G.pred, self.G.obj)
        expressions = [(f == v) for f, v in zip(fields, (s, p, o))
                       if v is not None]
        return self.G.select().where(*expressions)

    def search(self, *conditions):
        accum = []
        binds = {}
        variables = set()
        fields = {'s': 'subj', 'p': 'pred', 'o': 'obj'}

        for i, condition in enumerate(conditions):
            if isinstance(condition, dict):
                condition = (condition['s'], condition['p'], condition['o'])

            GA = self.G.alias('g%s' % i)
            for part, val in zip('spo', condition):
                if isinstance(val, Variable):
                    binds.setdefault(val, [])
                    binds[val].append(getattr(GA, fields[part]))
                    variables.add(val)
                else:
                    accum.append(getattr(GA, fields[part]) == val)

        selection = []
        sources = set()

        for var, fields in binds.items():
            selection.append(fields[0].alias(var.name))
            pairwise = [(fields[i - 1] == fields[i])
                        for i in range(1, len(fields))]
            if pairwise:
                accum.append(reduce(operator.and_, pairwise))
            sources.update([field.source for field in fields])

        return (self.G
                .select(*selection)
                .from_(*list(sources))
                .where(*accum)
                .dicts())


class _VariableFactory(object):
    def __getattr__(self, name):
        return Variable(name)
    __call__ = __getattr__

class Variable(object):
    __slots__ = ('name',)

    def __init__(self, name):
        self.name = name

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return '<Variable: %s>' % self.name


if __name__ == '__main__':
    h = Hexastore()

    data = (
        ('charlie', 'likes', 'beanie'),
        ('charlie', 'likes', 'huey'),
        ('charlie', 'likes', 'mickey'),
        ('charlie', 'likes', 'scout'),
        ('charlie', 'likes', 'zaizee'),

        ('huey', 'likes', 'charlie'),
        ('huey', 'likes', 'scout'),
        ('huey', 'likes', 'zaizee'),

        ('mickey', 'likes', 'beanie'),
        ('mickey', 'likes', 'charlie'),
        ('mickey', 'likes', 'scout'),

        ('zaizee', 'likes', 'beanie'),
        ('zaizee', 'likes', 'charlie'),
        ('zaizee', 'likes', 'scout'),

        ('charlie', 'lives', 'topeka'),
        ('beanie', 'lives', 'heaven'),
        ('huey', 'lives', 'topeka'),
        ('mickey', 'lives', 'topeka'),
        ('scout', 'lives', 'heaven'),
        ('zaizee', 'lives', 'lawrence'),
    )
    h.store_many(data)
    print('added %s items to store' % len(data))

    print('\nwho lives in topeka?')
    for obj in h.query(p='lives', o='topeka'):
        print(obj.subj)

    print('\nmy friends in heaven?')
    X = h.v.x
    results = h.search(('charlie', 'likes', X),
                       (X, 'lives', 'heaven'))
    for result in results:
        print(result['x'])

    print('\nmutual friends?')
    X = h.v.x
    Y = h.v.y
    results = h.search((X, 'likes', Y), (Y, 'likes', X))
    for result in results:
        print(result['x'], ' <-> ', result['y'])

    print('\nliked by both charlie, huey and mickey?')
    X = h.v.x
    results = h.search(('charlie', 'likes', X),
                       ('huey', 'likes', X),
                       ('mickey', 'likes', X))
    for result in results:
        print(result['x'])
