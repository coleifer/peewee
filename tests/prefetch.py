from peewee import *

from .base import get_in_memory_db
from .base import requires_models
from .base import ModelTestCase
from .base import TestModel


class Person(TestModel):
    name = TextField()


class Relationship(TestModel):
    from_person = ForeignKeyField(Person, backref='relationships')
    to_person = ForeignKeyField(Person, backref='related_to')


class Note(TestModel):
    person = ForeignKeyField(Person, backref='notes')
    content = TextField()


class NoteItem(TestModel):
    note = ForeignKeyField(Note, backref='items')
    content = TextField()


class Like(TestModel):
    person = ForeignKeyField(Person, backref='likes')
    note = ForeignKeyField(Note, backref='likes')


class Flag(TestModel):
    note = ForeignKeyField(Note, backref='flags')
    is_spam = BooleanField()


class Category(TestModel):
    name = TextField()
    parent = ForeignKeyField('self', backref='children', null=True)


class Package(TestModel):
    barcode = TextField(unique=True)


class PackageItem(TestModel):
    name = TextField()
    package = ForeignKeyField(Package, backref='items', field=Package.barcode)


class TestPrefetch(ModelTestCase):
    database = get_in_memory_db()
    requires = [Person, Note, NoteItem, Like, Flag]

    def create_test_data(self):
        data = {
            'huey': (
                ('meow', ('meow-1', 'meow-2', 'meow-3')),
                ('purr', ()),
                ('hiss', ('hiss-1', 'hiss-2'))),
            'mickey': (
                ('woof', ()),
                ('bark', ('bark-1', 'bark-2'))),
            'zaizee': (),
        }
        for name, notes in sorted(data.items()):
            person = Person.create(name=name)
            for note, items in notes:
                note = Note.create(person=person, content=note)
                for item in items:
                    NoteItem.create(note=note, content=item)

        Flag.create(note=Note.get(Note.content == 'purr'), is_spam=True)
        Flag.create(note=Note.get(Note.content == 'woof'), is_spam=True)

        Like.create(note=Note.get(Note.content == 'meow'),
                    person=Person.get(Person.name == 'mickey'))
        Like.create(note=Note.get(Note.content == 'woof'),
                    person=Person.get(Person.name == 'huey'))

    def setUp(self):
        super(TestPrefetch, self).setUp()
        self.create_test_data()

    def accumulate_results(self, query, sort_items=False):
        accum = []
        for person in query:
            notes = []
            for note in person.notes:
                items = []
                for item in note.items:
                    items.append(item.content)
                if sort_items:
                    items.sort()
                notes.append((note.content, items))
            if sort_items:
                notes.sort()
            accum.append((person.name, notes))
        return accum

    def test_prefetch_simple(self):
        with self.assertQueryCount(3):
            people = Person.select().order_by(Person.name)
            query = people.prefetch(Note, NoteItem)
            accum = self.accumulate_results(query, sort_items=True)

        self.assertEqual(accum, [
            ('huey', [
                ('hiss', ['hiss-1', 'hiss-2']),
                ('meow', ['meow-1', 'meow-2', 'meow-3']),
                ('purr', [])]),
            ('mickey', [
                ('bark', ['bark-1', 'bark-2']),
                ('woof', [])]),
            ('zaizee', []),
        ])

    def test_prefetch_filter(self):
        with self.assertQueryCount(3):
            people = Person.select().order_by(Person.name)
            notes = (Note
                     .select()
                     .where(Note.content.not_in(('hiss', 'meow', 'woof')))
                     .order_by(Note.content.desc()))
            items = NoteItem.select().where(~NoteItem.content.endswith('-2'))
            query = prefetch(people, notes, items)
            self.assertEqual(self.accumulate_results(query), [
                ('huey', [('purr', [])]),
                ('mickey', [('bark', ['bark-1'])]),
                ('zaizee', []),
            ])

    def test_prefetch_reverse(self):
        with self.assertQueryCount(2):
            people = Person.select().order_by(Person.name)
            notes = Note.select().order_by(Note.content)
            query = prefetch(notes, people)
            accum = [(note.content, note.person.name) for note in query]
            self.assertEqual(accum, [
                ('bark', 'mickey'),
                ('hiss', 'huey'),
                ('meow', 'huey'),
                ('purr', 'huey'),
                ('woof', 'mickey')])

    def test_prefetch_reverse_with_parent_join(self):
        with self.assertQueryCount(2):
            notes = (Note
                     .select(Note, Person)
                     .join(Person)
                     .order_by(Note.content))
            items = NoteItem.select().order_by(NoteItem.content.desc())
            query = prefetch(notes, items)
            accum = [(note.person.name,
                      note.content,
                      [item.content for item in note.items]) for note in query]
            self.assertEqual(accum, [
                ('mickey', 'bark', ['bark-2', 'bark-1']),
                ('huey', 'hiss', ['hiss-2', 'hiss-1']),
                ('huey', 'meow', ['meow-3', 'meow-2', 'meow-1']),
                ('huey', 'purr', []),
                ('mickey', 'woof', []),
            ])

    def test_prefetch_multi_depth(self):
        people = Person.select().order_by(Person.name)
        notes = Note.select().order_by(Note.content)
        items = NoteItem.select().order_by(NoteItem.content)
        flags = Flag.select().order_by(Flag.id)

        LikePerson = Person.alias('lp')
        likes = (Like
                 .select(Like, LikePerson.name)
                 .join(LikePerson, on=(Like.person == LikePerson.id)))

        with self.assertQueryCount(5):
            query = prefetch(people, notes, items, flags, likes)
            accum = []
            for person in query:
                notes = []
                for note in person.notes:
                    items = []
                    likes = []
                    flags = []
                    for item in note.items:
                        items.append(item.content)
                    for like in note.likes:
                        likes.append(like.person.name)
                    for flag in note.flags:
                        flags.append(flag.is_spam)
                    notes.append((note.content, items, likes, flags))
                accum.append((person.name, notes))

        self.assertEqual(accum, [
            ('huey', [
                ('hiss', ['hiss-1', 'hiss-2'], [], []),
                ('meow', ['meow-1', 'meow-2', 'meow-3'], ['mickey'], []),
                ('purr', [], [], [True])]),
            ('mickey', [
                ('bark', ['bark-1', 'bark-2'], [], []),
                ('woof', [], ['huey'], [True])]),
            (u'zaizee', []),
        ])

    def test_prefetch_with_group_by(self):
        people = (Person
                  .select(Person, fn.COUNT(Note.id).alias('note_count'))
                  .join(Note, JOIN.LEFT_OUTER)
                  .group_by(Person)
                  .order_by(Person.name))
        notes = Note.select().order_by(Note.content)
        items = NoteItem.select().order_by(NoteItem.content)
        with self.assertQueryCount(3):
            query = prefetch(people, notes, items)
            self.assertEqual(self.accumulate_results(query), [
                ('huey', [
                    ('hiss', ['hiss-1', 'hiss-2']),
                    ('meow', ['meow-1', 'meow-2', 'meow-3']),
                    ('purr', [])]),
                ('mickey', [
                    ('bark', ['bark-1', 'bark-2']),
                    ('woof', [])]),
                ('zaizee', []),
            ])

            huey, mickey, zaizee = query
            self.assertEqual(huey.note_count, 3)
            self.assertEqual(mickey.note_count, 2)
            self.assertEqual(zaizee.note_count, 0)

    @requires_models(Category)
    def test_prefetch_self_join(self):
        def cc(name, parent=None):
            return Category.create(name=name, parent=parent)
        root = cc('root')
        p1 = cc('p1', root)
        p2 = cc('p2', root)
        for p in (p1, p2):
            for i in range(2):
                cc('%s-%s' % (p.name, i + 1), p)

        Child = Category.alias('child')
        with self.assertQueryCount(2):
            query = prefetch(Category.select().order_by(Category.id), Child)
            names_and_children = [
                (cat.name, [child.name for child in cat.children])
                for cat in query]

        self.assertEqual(names_and_children, [
            ('root', ['p1', 'p2']),
            ('p1', ['p1-1', 'p1-2']),
            ('p2', ['p2-1', 'p2-2']),
            ('p1-1', []),
            ('p1-2', []),
            ('p2-1', []),
            ('p2-2', []),
        ])

    def test_prefetch_specific_model(self):
        # Person -> Note
        #        -> Like (has fks to both person and note)
        Like.create(note=Note.get(Note.content == 'woof'),
                    person=Person.get(Person.name == 'zaizee'))
        NoteAlias = Note.alias('na')

        with self.assertQueryCount(3):
            people = Person.select().order_by(Person.name)
            notes = Note.select().order_by(Note.content)
            likes = (Like
                     .select(Like, NoteAlias.content)
                     .join(NoteAlias, on=(Like.note == NoteAlias.id))
                     .order_by(NoteAlias.content))
            query = prefetch(people, notes, (likes, Person))
            accum = []
            for person in query:
                likes = []
                notes = []
                for note in person.notes:
                    notes.append(note.content)
                for like in person.likes:
                    likes.append(like.note.content)
                accum.append((person.name, notes, likes))

        self.assertEqual(accum, [
            ('huey', ['hiss', 'meow', 'purr'], ['woof']),
            ('mickey', ['bark', 'woof'], ['meow']),
            ('zaizee', [], ['woof']),
        ])

    @requires_models(Relationship)
    def test_multiple_foreign_keys(self):
        Person.delete().execute()
        c, h, z = [Person.create(name=name) for name in
                                 ('charlie', 'huey', 'zaizee')]
        RC = lambda f, t: Relationship.create(from_person=f, to_person=t)
        r1 = RC(c, h)
        r2 = RC(c, z)
        r3 = RC(h, c)
        r4 = RC(z, c)

        def assertRelationships(attr, values):
            for relationship, value in zip(attr, values):
                self.assertEqual(relationship.__data__, value)

        with self.assertQueryCount(2):
            people = Person.select().order_by(Person.name)
            relationships = Relationship.select().order_by(Relationship.id)

            query = prefetch(people, relationships)
            cp, hp, zp = list(query)

            assertRelationships(cp.relationships, [
                {'id': r1.id, 'from_person': c.id, 'to_person': h.id},
                {'id': r2.id, 'from_person': c.id, 'to_person': z.id}])
            assertRelationships(cp.related_to, [
                {'id': r3.id, 'from_person': h.id, 'to_person': c.id},
                {'id': r4.id, 'from_person': z.id, 'to_person': c.id}])

            assertRelationships(hp.relationships, [
                {'id': r3.id, 'from_person': h.id, 'to_person': c.id}])
            assertRelationships(hp.related_to, [
                {'id': r1.id, 'from_person': c.id, 'to_person': h.id}])

            assertRelationships(zp.relationships, [
                {'id': r4.id, 'from_person': z.id, 'to_person': c.id}])
            assertRelationships(zp.related_to, [
                {'id': r2.id, 'from_person': c.id, 'to_person': z.id}])

        with self.assertQueryCount(2):
            query = prefetch(relationships, people)
            accum = []
            for row in query:
                accum.append((row.from_person.name, row.to_person.name))
            self.assertEqual(accum, [
                ('charlie', 'huey'),
                ('charlie', 'zaizee'),
                ('huey', 'charlie'),
                ('zaizee', 'charlie')])

    def test_prefetch_through_manytomany(self):
        Like.create(note=Note.get(Note.content == 'meow'),
                    person=Person.get(Person.name == 'zaizee'))
        Like.create(note=Note.get(Note.content == 'woof'),
                    person=Person.get(Person.name == 'zaizee'))

        with self.assertQueryCount(3):
            people = Person.select().order_by(Person.name)
            notes = Note.select().order_by(Note.content)
            likes = Like.select().order_by(Like.id)
            query = prefetch(people, likes, notes)
            accum = []
            for person in query:
                liked_notes = []
                for like in person.likes:
                    liked_notes.append(like.note.content)
                accum.append((person.name, liked_notes))

        self.assertEqual(accum, [
            ('huey', ['woof']),
            ('mickey', ['meow']),
            ('zaizee', ['meow', 'woof']),
        ])

    @requires_models(Package, PackageItem)
    def test_prefetch_non_pk_fk(self):
        data = (
            ('101', ('a', 'b')),
            ('102', ('a', 'b')),
            ('103', ()),
            ('104', ('a', 'b', 'c', 'd', 'e')),
        )
        for barcode, items in data:
            Package.create(barcode=barcode)
            for item in items:
                PackageItem.create(package=barcode, name=item)

        packages = Package.select().order_by(Package.barcode)
        items = PackageItem.select().order_by(PackageItem.name)

        with self.assertQueryCount(2):
            query = prefetch(packages, items)
            for package, (barcode, items) in zip(query, data):
                self.assertEqual(package.barcode, barcode)
                self.assertEqual([item.name for item in package.items],
                                 list(items))
