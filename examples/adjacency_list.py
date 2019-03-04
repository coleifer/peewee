from collections import deque
from peewee import *


db = SqliteDatabase(':memory:')


class TreeNode(Model):
    parent = ForeignKeyField('self', backref='children', null=True)
    name = TextField()

    class Meta:
        database = db

    def __str__(self):
        return 'name=%s' % self.name

    def dump(self, _indent=0):
        return ('  ' * _indent + repr(self) + '\n' +
                ''.join(c.dump(_indent + 1) for c in self.children))


if __name__ == '__main__':
    db.create_tables([TreeNode])
    tree = (
        'root', (
            ('node-1', (
                ('sub-1-1', ()),
                ('sub-1-2', ()))),
            ('node-2', (
                ('sub-2-1', (
                    ('sub-sub-2-1-1', ()),
                    ('sub-sub-2-1-2', ()))),
                ('sub-2-2', (
                    ('sub-sub-2-2-1', ()),
                    ('sub-sub-2-2-2', ()))))),
            ('node-3', ()),
            ('node-4', (
                ('sub-4-1', ()),
                ('sub-4-2', ()),
                ('sub-4-3', ()),
                ('sub-4-4', ())))))

    with db.atomic():
        stack = deque([(None, tree)])
        while stack:
            parent, t = stack.pop()
            name, children = t
            node = TreeNode.create(name=name, parent=parent)
            for childdef in children:
                stack.appendleft((node, childdef))

    root = TreeNode.get(name='root')
    print(root.dump())
