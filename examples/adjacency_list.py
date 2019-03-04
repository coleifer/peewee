from peewee import *


db = SqliteDatabase(':memory:')

class Node(Model):
    name = TextField()
    parent = ForeignKeyField('self', backref='children', null=True)

    class Meta:
        database = db

    def __str__(self):
        return self.name

    def dump(self, _indent=0):
        return ('  ' * _indent + self.name + '\n' +
                ''.join(child.dump(_indent + 1) for child in self.children))

db.create_tables([Node])

tree = ('root', (
    ('n1', (
        ('c11', ()),
        ('c12', ()))),
    ('n2', (
        ('c21', ()),
        ('c22', (
            ('g221', ()),
            ('g222', ()))),
        ('c23', ()),
        ('c24', (
            ('g241', ()),
            ('g242', ()),
            ('g243', ())))))))
stack = [(None, tree)]
while stack:
    parent, (name, children) = stack.pop()
    node = Node.create(name=name, parent=parent)
    for child_tree in children:
        stack.insert(0, (node, child_tree))

# Now that we have created the stack, let's eagerly load 4 levels of children.
# To show that it works, we'll turn on the query debugger so you can see which
# queries are executed.
import logging; logger = logging.getLogger('peewee')
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)

C = Node.alias('c')
G = Node.alias('g')
GG = Node.alias('gg')
GGG = Node.alias('ggg')

roots = Node.select().where(Node.parent.is_null())
pf = prefetch(roots, C, (G, C), (GG, G), (GGG, GG))
for root in pf:
    print(root.dump())
