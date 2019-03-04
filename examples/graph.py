from peewee import *


db = SqliteDatabase(':memory:')


class Base(Model):
    class Meta:
        database = db


class Node(Base):
    name = TextField(primary_key=True)

    def outgoing(self):
        return (Node
                .select(Node, Edge.weight)
                .join(Edge, on=Edge.dest)
                .where(Edge.src == self)
                .objects())

    def incoming(self):
        return (Node
                .select(Node, Edge.weight)
                .join(Edge, on=Edge.src)
                .where(Edge.dest == self)
                .objects())


class Edge(Base):
    src = ForeignKeyField(Node, backref='outgoing_edges')
    dest = ForeignKeyField(Node, backref='incoming_edges')
    weight = FloatField()


db.create_tables([Node, Edge])


nodes = [Node.create(name=c) for c in 'abcde']
g = (
    ('a', 'b', -1),
    ('a', 'c', 4),
    ('b', 'c', 3),
    ('b', 'd', 2),
    ('b', 'e', 2),
    ('d', 'b', 1),
    ('d', 'c', 5),
    ('e', 'd', -3))
for src, dest, wt in g:
    src_n, dest_n = nodes[ord(src) - ord('a')], nodes[ord(dest) - ord('a')]
    Edge.create(src=src_n, dest=dest_n, weight=wt)


def bellman_ford(s):
    dist = {}
    pred = {}
    all_nodes = Node.select()
    for node in all_nodes:
        dist[node] = float('inf')
        pred[node] = None
    dist[s] = 0

    for _ in range(len(all_nodes) - 1):
        for u in all_nodes:
            for v in u.outgoing():
                potential = dist[u] + v.weight
                if dist[v] > potential:
                    dist[v] = potential
                    pred[v] = u

    # Verify no negative-weight cycles.
    for u in all_nodes:
        for v in u.outgoing():
            assert dist[v] <= dist[u] + v.weight

    return dist, pred

def print_path(s, e):
    dist, pred = bellman_ford(s)
    distance = dist[e]
    route = [e]
    while e != s:
        route.append(pred[e])
        e = pred[e]

    print(' -> '.join(v.name for v in route[::-1]) + ' (%s)' % distance)

print_path(Node['a'], Node['c'])  # a -> b -> c
print_path(Node['a'], Node['d'])  # a -> b -> e -> d
print_path(Node['b'], Node['d'])  # b -> e -> d
