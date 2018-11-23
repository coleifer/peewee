from peewee import *

from .base import IS_MYSQL
from .base import IS_SQLITE
from .base import ModelTestCase
from .base import TestModel
from .base import db
from .base import requires_sqlite


class Package(TestModel):
    barcode = CharField(unique=True)


class PackageItem(TestModel):
    title = CharField()
    package = ForeignKeyField(Package, Package.barcode, backref='items')


class Manufacturer(TestModel):
    name = CharField()


class Component(TestModel):
    name = CharField()
    manufacturer = ForeignKeyField(Manufacturer, null=True)


class Computer(TestModel):
    hard_drive = ForeignKeyField(Component, backref='c1')
    memory = ForeignKeyField(Component, backref='c2')
    processor = ForeignKeyField(Component, backref='c3')


class User(TestModel):
    username = CharField()

    class Meta:
        table_name = 'users'


class Relationship(TestModel):
    from_user = ForeignKeyField(User, backref='relationships')
    to_user = ForeignKeyField(User, backref='related_to')


class Note(TestModel):
    user = ForeignKeyField(User, backref='notes')
    content = TextField()


class CompositeKeyModel(TestModel):
    f1 = CharField()
    f2 = IntegerField()
    f3 = FloatField()

    class Meta:
        primary_key = CompositeKey('f1', 'f2')


class UserThing(TestModel):
    thing = CharField()
    user = ForeignKeyField(User, backref='things')

    class Meta:
        primary_key = CompositeKey('thing', 'user')


class Post(TestModel):
    title = CharField()


class Tag(TestModel):
    tag = CharField()


class TagPostThrough(TestModel):
    tag = ForeignKeyField(Tag, backref='posts')
    post = ForeignKeyField(Post, backref='tags')

    class Meta:
        primary_key = CompositeKey('tag', 'post')


class TagPostThroughAlt(TestModel):
    tag = ForeignKeyField(Tag, backref='posts_alt')
    post = ForeignKeyField(Post, backref='tags_alt')


class TestForeignKeyToNonPrimaryKey(ModelTestCase):
    requires = [Package, PackageItem]

    def setUp(self):
        super(TestForeignKeyToNonPrimaryKey, self).setUp()

        for barcode in ['101', '102']:
            Package.create(barcode=barcode)
            for i in range(2):
                PackageItem.create(
                    package=barcode,
                    title='%s-%s' % (barcode, i))

    def test_fk_resolution(self):
        pi = PackageItem.get(PackageItem.title == '101-0')
        self.assertEqual(pi.__data__['package'], '101')
        self.assertEqual(pi.package, Package.get(Package.barcode == '101'))

    def test_select_generation(self):
        p = Package.get(Package.barcode == '101')
        self.assertEqual(
            [item.title for item in p.items.order_by(PackageItem.title)],
            ['101-0', '101-1'])


class TestMultipleForeignKey(ModelTestCase):
    requires = [Manufacturer, Component, Computer]
    test_values = [
        ['3TB', '16GB', 'i7'],
        ['128GB', '1GB', 'ARM'],
    ]

    def setUp(self):
        super(TestMultipleForeignKey, self).setUp()
        intel = Manufacturer.create(name='Intel')
        amd = Manufacturer.create(name='AMD')
        kingston = Manufacturer.create(name='Kingston')
        for hard_drive, memory, processor in self.test_values:
            c = Computer.create(
                hard_drive=Component.create(name=hard_drive),
                memory=Component.create(name=memory, manufacturer=kingston),
                processor=Component.create(name=processor, manufacturer=intel))

        # The 2nd computer has an AMD processor.
        c.processor.manufacturer = amd
        c.processor.save()

    def test_multi_join(self):
        HDD = Component.alias('hdd')
        HDDMf = Manufacturer.alias('hddm')
        Memory = Component.alias('mem')
        MemoryMf = Manufacturer.alias('memm')
        Processor = Component.alias('proc')
        ProcessorMf = Manufacturer.alias('procm')
        query = (Computer
                 .select(
                     Computer,
                     HDD,
                     Memory,
                     Processor,
                     HDDMf,
                     MemoryMf,
                     ProcessorMf)
                 .join(HDD, on=(
                     Computer.hard_drive_id == HDD.id).alias('hard_drive'))
                 .join(
                     HDDMf,
                     JOIN.LEFT_OUTER,
                     on=(HDD.manufacturer_id == HDDMf.id))
                 .switch(Computer)
                 .join(Memory, on=(
                     Computer.memory_id == Memory.id).alias('memory'))
                 .join(
                     MemoryMf,
                     JOIN.LEFT_OUTER,
                     on=(Memory.manufacturer_id == MemoryMf.id))
                 .switch(Computer)
                 .join(Processor, on=(
                     Computer.processor_id == Processor.id).alias('processor'))
                 .join(
                     ProcessorMf,
                     JOIN.LEFT_OUTER,
                     on=(Processor.manufacturer_id == ProcessorMf.id))
                 .order_by(Computer.id))

        with self.assertQueryCount(1):
            vals = []
            manufacturers = []
            for computer in query:
                components = [
                    computer.hard_drive,
                    computer.memory,
                    computer.processor]
                vals.append([component.name for component in components])
                for component in components:
                    if component.manufacturer:
                        manufacturers.append(component.manufacturer.name)
                    else:
                        manufacturers.append(None)

            self.assertEqual(vals, self.test_values)
            self.assertEqual(manufacturers, [
                None, 'Kingston', 'Intel',
                None, 'Kingston', 'AMD',
            ])


class TestMultipleForeignKeysJoining(ModelTestCase):
    requires = [User, Relationship]

    def test_multiple_fks(self):
        a = User.create(username='a')
        b = User.create(username='b')
        c = User.create(username='c')

        self.assertEqual(list(a.relationships), [])
        self.assertEqual(list(a.related_to), [])

        r_ab = Relationship.create(from_user=a, to_user=b)
        self.assertEqual(list(a.relationships), [r_ab])
        self.assertEqual(list(a.related_to), [])
        self.assertEqual(list(b.relationships), [])
        self.assertEqual(list(b.related_to), [r_ab])

        r_bc = Relationship.create(from_user=b, to_user=c)

        following = User.select().join(
            Relationship, on=Relationship.to_user
        ).where(Relationship.from_user == a)
        self.assertEqual(list(following), [b])

        followers = User.select().join(
            Relationship, on=Relationship.from_user
        ).where(Relationship.to_user == a.id)
        self.assertEqual(list(followers), [])

        following = User.select().join(
            Relationship, on=Relationship.to_user
        ).where(Relationship.from_user == b.id)
        self.assertEqual(list(following), [c])

        followers = User.select().join(
            Relationship, on=Relationship.from_user
        ).where(Relationship.to_user == b.id)
        self.assertEqual(list(followers), [a])

        following = User.select().join(
            Relationship, on=Relationship.to_user
        ).where(Relationship.from_user == c.id)
        self.assertEqual(list(following), [])

        followers = User.select().join(
            Relationship, on=Relationship.from_user
        ).where(Relationship.to_user == c.id)
        self.assertEqual(list(followers), [b])


class TestCompositePrimaryKey(ModelTestCase):
    requires = [Tag, Post, TagPostThrough, CompositeKeyModel, User, UserThing]

    def setUp(self):
        super(TestCompositePrimaryKey, self).setUp()
        tags = [Tag.create(tag='t%d' % i) for i in range(1, 4)]
        posts = [Post.create(title='p%d' % i) for i in range(1, 4)]
        p12 = Post.create(title='p12')
        for t, p in zip(tags, posts):
            TagPostThrough.create(tag=t, post=p)
        TagPostThrough.create(tag=tags[0], post=p12)
        TagPostThrough.create(tag=tags[1], post=p12)

    def test_create_table_query(self):
        query, params = TagPostThrough._schema._create_table().query()
        sql = ('CREATE TABLE IF NOT EXISTS "tag_post_through" ('
               '"tag_id" INTEGER NOT NULL, '
               '"post_id" INTEGER NOT NULL, '
               'PRIMARY KEY ("tag_id", "post_id"), '
               'FOREIGN KEY ("tag_id") REFERENCES "tag" ("id"), '
               'FOREIGN KEY ("post_id") REFERENCES "post" ("id"))')
        if IS_MYSQL:
            sql = sql.replace('"', '`')
        self.assertEqual(query, sql)

    def test_get_set_id(self):
        tpt = (TagPostThrough
               .select()
               .join(Tag)
               .switch(TagPostThrough)
               .join(Post)
               .order_by(Tag.tag, Post.title)).get()
        # Sanity check.
        self.assertEqual(tpt.tag.tag, 't1')
        self.assertEqual(tpt.post.title, 'p1')

        tag = Tag.select().where(Tag.tag == 't1').get()
        post = Post.select().where(Post.title == 'p1').get()
        self.assertEqual(tpt._pk, (tag, post))

        # set_id is a no-op.
        with self.assertRaisesCtx(TypeError):
            tpt._pk = None

        self.assertEqual(tpt._pk, (tag, post))
        t3 = Tag.get(Tag.tag == 't3')
        p3 = Post.get(Post.title == 'p3')
        tpt._pk = (t3, p3)
        self.assertEqual(tpt.tag.tag, 't3')
        self.assertEqual(tpt.post.title, 'p3')

    def test_querying(self):
        posts = (Post.select()
                 .join(TagPostThrough)
                 .join(Tag)
                 .where(Tag.tag == 't1')
                 .order_by(Post.title))
        self.assertEqual([p.title for p in posts], ['p1', 'p12'])

        tags = (Tag.select()
                .join(TagPostThrough)
                .join(Post)
                .where(Post.title == 'p12')
                .order_by(Tag.tag))
        self.assertEqual([t.tag for t in tags], ['t1', 't2'])

    def test_composite_key_model(self):
        CKM = CompositeKeyModel
        values = [
            ('a', 1, 1.0),
            ('a', 2, 2.0),
            ('b', 1, 1.0),
            ('b', 2, 2.0)]
        c1, c2, c3, c4 = [
            CKM.create(f1=f1, f2=f2, f3=f3) for f1, f2, f3 in values]

        # Update a single row, giving it a new value for `f3`.
        CKM.update(f3=3.0).where((CKM.f1 == 'a') & (CKM.f2 == 2)).execute()

        c = CKM.get((CKM.f1 == 'a') & (CKM.f2 == 2))
        self.assertEqual(c.f3, 3.0)

        # Update the `f3` value and call `save()`, triggering an update.
        c3.f3 = 4.0
        c3.save()

        c = CKM.get((CKM.f1 == 'b') & (CKM.f2 == 1))
        self.assertEqual(c.f3, 4.0)

        # Only 1 row updated.
        query = CKM.select().where(CKM.f3 == 4.0)
        self.assertEqual(query.count(), 1)

        # Unfortunately this does not work since the original value of the
        # PK is lost (and hence cannot be used to update).
        c4.f1 = 'c'
        c4.save()
        self.assertRaises(
            CKM.DoesNotExist,
            lambda: CKM.get((CKM.f1 == 'c') & (CKM.f2 == 2)))

    def test_count_composite_key(self):
        CKM = CompositeKeyModel
        values = [
            ('a', 1, 1.0),
            ('a', 2, 2.0),
            ('b', 1, 1.0),
            ('b', 2, 1.0)]
        for f1, f2, f3 in values:
            CKM.create(f1=f1, f2=f2, f3=f3)

        self.assertEqual(CKM.select().count(), 4)
        self.assertTrue(CKM.select().where(
            (CKM.f1 == 'a') &
            (CKM.f2 == 1)).exists())
        self.assertFalse(CKM.select().where(
            (CKM.f1 == 'a') &
            (CKM.f2 == 3)).exists())

    def test_delete_instance(self):
        u1, u2 = [User.create(username='u%s' % i) for i in range(2)]
        ut1 = UserThing.create(thing='t1', user=u1)
        ut2 = UserThing.create(thing='t2', user=u1)
        ut3 = UserThing.create(thing='t1', user=u2)
        ut4 = UserThing.create(thing='t3', user=u2)

        res = ut1.delete_instance()
        self.assertEqual(res, 1)
        self.assertEqual(
            [x.thing for x in UserThing.select().order_by(UserThing.thing)],
            ['t1', 't2', 't3'])

    def test_composite_key_inheritance(self):
        class Person(TestModel):
            first = TextField()
            last = TextField()

            class Meta:
                primary_key = CompositeKey('first', 'last')

        self.assertTrue(isinstance(Person._meta.primary_key, CompositeKey))
        self.assertEqual(Person._meta.primary_key.field_names,
                         ('first', 'last'))

        class Employee(Person):
            title = TextField()

        self.assertTrue(isinstance(Employee._meta.primary_key, CompositeKey))
        self.assertEqual(Employee._meta.primary_key.field_names,
                         ('first', 'last'))
        sql = ('CREATE TABLE IF NOT EXISTS "employee" ('
               '"first" TEXT NOT NULL, "last" TEXT NOT NULL, '
               '"title" TEXT NOT NULL, PRIMARY KEY ("first", "last"))')
        if IS_MYSQL:
            sql = sql.replace('"', '`')
        self.assertEqual(Employee._schema._create_table().query(), (sql, []))


class TestForeignKeyConstraints(ModelTestCase):
    requires = [User, Note]

    def setUp(self):
        super(TestForeignKeyConstraints, self).setUp()
        self.set_foreign_key_pragma(True)

    def tearDown(self):
        self.set_foreign_key_pragma(False)
        super(TestForeignKeyConstraints, self).tearDown()

    def set_foreign_key_pragma(self, is_enabled):
        if IS_SQLITE:
            self.database.foreign_keys = 'on' if is_enabled else 'off'

    def test_constraint_exists(self):
        max_id = User.select(fn.MAX(User.id)).scalar() or 0
        with self.assertRaisesCtx(IntegrityError):
            with self.database.atomic():
                Note.create(user=max_id + 1, content='test')

    @requires_sqlite
    def test_disable_constraint(self):
        self.set_foreign_key_pragma(False)
        Note.create(user=0, content='test')
