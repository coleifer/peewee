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


class TestPrefetch(ModelTestCase):
    database = get_in_memory_db()
    requires = [Person, Relationship, Note, NoteItem]

    def create_test_data(self):
        data = {
            'huey': (
                ('meow', ('meow-1', 'meow-2', 'meow-3')),
                ('purr', ()),
                ('hiss', ('hiss-1', 'hiss-2'))),
            'mickey': (
                ('woof', ()),
                ('bark', ('bark-1', 'bark-2'))),
        }
        for name, notes in sorted(data.items()):
            person = Person.create(name=name)
            for note, items in notes:
                note = Note.create(person=person, content=note)
                for item in items:
                    NoteItem.create(note=note, content=item)

    def setUp(self):
        super(TestPrefetch, self).setUp()
        self.create_test_data()

    def test_prefetch_simple(self):
        with self.assertQueryCount(3):
            people = Person.select().order_by(Person.name)
            query = prefetch(people, Note, NoteItem)
            accum = []
            for person in query:
                notes = []
                for note in person.notes:
                    items = []
                    for item in note.items:
                        items.append(item.content)
                    notes.append((note.content, sorted(items)))
                accum.append((person.name, sorted(notes)))

        self.assertEqual(accum, [
            ('huey', [
                ('hiss', ['hiss-1', 'hiss-2']),
                ('meow', ['meow-1', 'meow-2', 'meow-3']),
                ('purr', [])]),
            ('mickey', [
                ('bark', ['bark-1', 'bark-2']),
                ('woof', [])]),
        ])
