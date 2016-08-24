from peewee import *
from playhouse.fields import DeferredThroughModel
from playhouse.fields import ManyToManyField
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase


db = database_initializer.get_in_memory_database()

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    username = CharField(unique=True)

class Note(BaseModel):
    text = TextField()
    users = ManyToManyField(User)

NoteUserThrough = Note.users.get_through_model()

AltThroughDeferred = DeferredThroughModel()

class AltNote(BaseModel):
    text = TextField()
    users = ManyToManyField(User, through_model=AltThroughDeferred)

class AltThroughModel(BaseModel):
    user = ForeignKeyField(User, related_name='_xx_rel')
    note = ForeignKeyField(AltNote, related_name='_xx_rel')

    class Meta:
        primary_key = CompositeKey('user', 'note')

AltThroughDeferred.set_model(AltThroughModel)

class TestManyToManyField(ModelTestCase):
    requires = [User, Note, NoteUserThrough, AltThroughModel, AltNote]
    user_to_note = {
        'charlie': [1, 2],
        'huey': [2, 3],
        'mickey': [3, 4],
        'zaizee': [4, 5]}

    def setUp(self):
        super(TestManyToManyField, self).setUp()
        usernames = ['charlie', 'huey', 'mickey', 'zaizee']
        n_notes = 5
        for username in usernames:
            User.create(username=username)
        for i in range(n_notes):
            Note.create(text='note-%s' % (i + 1))

    def test_through_model(self):
        self.assertEqual(len(NoteUserThrough._meta.fields), 3)

        fields = NoteUserThrough._meta.fields
        self.assertEqual(sorted(fields), ['id', 'note', 'user'])

        note_field = fields['note']
        self.assertEqual(note_field.rel_model, Note)
        self.assertFalse(note_field.null)

        user_field = fields['user']
        self.assertEqual(user_field.rel_model, User)
        self.assertFalse(user_field.null)

    def _create_relationship(self):
        for username, notes in self.user_to_note.items():
            user = User.get(User.username == username)
            for note in notes:
                NoteUserThrough.create(
                    note=Note.get(Note.text == 'note-%s' % note),
                    user=user)

    def assertNotes(self, query, expected):
        notes = [note.text for note in query]
        self.assertEqual(
            sorted(notes),
            ['note-%s' % i for i in sorted(expected)])

    def assertUsers(self, query, expected):
        usernames = [user.username for user in query]
        self.assertEqual(sorted(usernames), sorted(expected))

    def test_descriptor_query(self):
        self._create_relationship()

        charlie, huey, mickey, zaizee = User.select().order_by(User.username)

        with self.assertQueryCount(1):
            self.assertNotes(charlie.notes, [1, 2])

        with self.assertQueryCount(1):
            self.assertNotes(zaizee.notes, [4, 5])

        u = User.create(username='beanie')
        self.assertNotes(u.notes, [])

        n1, n2, n3, n4, n5 = Note.select().order_by(Note.text)
        with self.assertQueryCount(1):
            self.assertUsers(n1.users, ['charlie'])

        with self.assertQueryCount(1):
            self.assertUsers(n2.users, ['charlie', 'huey'])

        with self.assertQueryCount(1):
            self.assertUsers(n5.users, ['zaizee'])

        n6 = Note.create(text='note-6')
        self.assertUsers(n6.users, [])

    def test_desciptor_filtering(self):
        self._create_relationship()
        charlie, huey, mickey, zaizee = User.select().order_by(User.username)

        with self.assertQueryCount(1):
            notes = charlie.notes.order_by(Note.text.desc())
            self.assertNotes(notes, [2, 1])

        with self.assertQueryCount(1):
            notes = huey.notes.where(Note.text != 'note-3')
            self.assertNotes(notes, [2])

    def test_set_values(self):
        charlie = User.get(User.username == 'charlie')
        huey = User.get(User.username == 'huey')
        n1, n2, n3, n4, n5 = Note.select().order_by(Note.text)

        with self.assertQueryCount(2):
            charlie.notes = n1
        self.assertNotes(charlie.notes, [1])
        self.assertUsers(n1.users, ['charlie'])

        charlie.notes = [n2, n3]
        self.assertNotes(charlie.notes, [2, 3])
        self.assertUsers(n1.users, [])
        self.assertUsers(n2.users, ['charlie'])
        self.assertUsers(n3.users, ['charlie'])

        with self.assertQueryCount(2):
            huey.notes = Note.select().where(~(Note.text.endswith('4')))
        self.assertNotes(huey.notes, [1, 2, 3, 5])

    def test_add(self):
        charlie = User.get(User.username == 'charlie')
        huey = User.get(User.username == 'huey')
        n1, n2, n3, n4, n5 = Note.select().order_by(Note.text)

        charlie.notes.add([n1, n2])
        self.assertNotes(charlie.notes, [1, 2])
        self.assertUsers(n1.users, ['charlie'])
        self.assertUsers(n2.users, ['charlie'])
        others = [n3, n4, n5]
        for note in others:
            self.assertUsers(note.users, [])

        with self.assertQueryCount(1):
            huey.notes.add(Note.select().where(
                fn.substr(Note.text, 6, 1) << ['1', '3', '5']))
        self.assertNotes(huey.notes, [1, 3, 5])
        self.assertUsers(n1.users, ['charlie', 'huey'])
        self.assertUsers(n2.users, ['charlie'])
        self.assertUsers(n3.users, ['huey'])
        self.assertUsers(n4.users, [])
        self.assertUsers(n5.users, ['huey'])

        with self.assertQueryCount(1):
            charlie.notes.add(n4)
        self.assertNotes(charlie.notes, [1, 2, 4])

        with self.assertQueryCount(2):
            n3.users.add(
                User.select().where(User.username != 'charlie'),
                clear_existing=True)
        self.assertUsers(n3.users, ['huey', 'mickey', 'zaizee'])

    def test_add_by_ids(self):
        charlie = User.get(User.username == 'charlie')
        n1, n2, n3 = Note.select().order_by(Note.text).limit(3)
        charlie.notes.add([n1.id, n2.id])
        self.assertNotes(charlie.notes, [1, 2])
        self.assertUsers(n1.users, ['charlie'])
        self.assertUsers(n2.users, ['charlie'])
        self.assertUsers(n3.users, [])

    def test_unique(self):
        n1 = Note.get(Note.text == 'note-1')
        charlie = User.get(User.username == 'charlie')

        def add_user(note, user):
            with self.assertQueryCount(1):
                note.users.add(user)

        add_user(n1, charlie)
        self.assertRaises(IntegrityError, add_user, n1, charlie)

        add_user(n1, User.get(User.username == 'zaizee'))
        self.assertUsers(n1.users, ['charlie', 'zaizee'])

    def test_remove(self):
        self._create_relationship()
        charlie, huey, mickey, zaizee = User.select().order_by(User.username)
        n1, n2, n3, n4, n5 = Note.select().order_by(Note.text)

        with self.assertQueryCount(1):
            charlie.notes.remove([n1, n2, n3])

        self.assertNotes(charlie.notes, [])
        self.assertNotes(huey.notes, [2, 3])

        with self.assertQueryCount(1):
            huey.notes.remove(Note.select().where(
                Note.text << ['note-2', 'note-4', 'note-5']))

        self.assertNotes(huey.notes, [3])
        self.assertNotes(mickey.notes, [3, 4])
        self.assertNotes(zaizee.notes, [4, 5])

        with self.assertQueryCount(1):
            n4.users.remove([charlie, mickey])
        self.assertUsers(n4.users, ['zaizee'])

        with self.assertQueryCount(1):
            n5.users.remove(User.select())
        self.assertUsers(n5.users, [])

    def test_remove_by_id(self):
        self._create_relationship()
        charlie, huey, mickey, zaizee = User.select().order_by(User.username)
        n1, n2, n3, n4, n5 = Note.select().order_by(Note.text)
        charlie.notes.add([n3, n4])

        with self.assertQueryCount(1):
            charlie.notes.remove([n1.id, n3.id])

        self.assertNotes(charlie.notes, [2, 4])
        self.assertNotes(huey.notes, [2, 3])

    def test_clear(self):
        charlie = User.get(User.username == 'charlie')
        huey = User.get(User.username == 'huey')

        charlie.notes = Note.select()
        huey.notes = Note.select()

        self.assertEqual(charlie.notes.count(), 5)
        self.assertEqual(huey.notes.count(), 5)

        charlie.notes.clear()
        self.assertEqual(charlie.notes.count(), 0)
        self.assertEqual(huey.notes.count(), 5)

        n1 = Note.get(Note.text == 'note-1')
        n2 = Note.get(Note.text == 'note-2')

        n1.users = User.select()
        n2.users = User.select()

        self.assertEqual(n1.users.count(), 4)
        self.assertEqual(n2.users.count(), 4)

        n1.users.clear()
        self.assertEqual(n1.users.count(), 0)
        self.assertEqual(n2.users.count(), 4)

    def test_manual_through(self):
        charlie, huey, mickey, zaizee = User.select().order_by(User.username)
        alt_notes = []
        for i in range(5):
            alt_notes.append(AltNote.create(text='note-%s' % (i + 1)))

        self.assertNotes(charlie.altnotes, [])
        for alt_note in alt_notes:
            self.assertUsers(alt_note.users, [])

        n1, n2, n3, n4, n5 = alt_notes

        # Test adding relationships by setting the descriptor.
        charlie.altnotes = [n1, n2]

        with self.assertQueryCount(2):
            huey.altnotes = AltNote.select().where(
                fn.substr(AltNote.text, 6, 1) << ['1', '3', '5'])

        mickey.altnotes.add([n1, n4])

        with self.assertQueryCount(2):
            zaizee.altnotes = AltNote.select()

        # Test that the notes were added correctly.
        with self.assertQueryCount(1):
            self.assertNotes(charlie.altnotes, [1, 2])

        with self.assertQueryCount(1):
            self.assertNotes(huey.altnotes, [1, 3, 5])

        with self.assertQueryCount(1):
            self.assertNotes(mickey.altnotes, [1, 4])

        with self.assertQueryCount(1):
            self.assertNotes(zaizee.altnotes, [1, 2, 3, 4, 5])

        # Test removing notes.
        with self.assertQueryCount(1):
            charlie.altnotes.remove(n1)
        self.assertNotes(charlie.altnotes, [2])

        with self.assertQueryCount(1):
            huey.altnotes.remove([n1, n2, n3])
        self.assertNotes(huey.altnotes, [5])

        with self.assertQueryCount(1):
            zaizee.altnotes.remove(
                AltNote.select().where(
                    fn.substr(AltNote.text, 6, 1) << ['1', '2', '4']))
        self.assertNotes(zaizee.altnotes, [3, 5])

        # Test the backside of the relationship.
        n1.users = User.select().where(User.username != 'charlie')

        with self.assertQueryCount(1):
            self.assertUsers(n1.users, ['huey', 'mickey', 'zaizee'])
        with self.assertQueryCount(1):
            self.assertUsers(n2.users, ['charlie'])
        with self.assertQueryCount(1):
            self.assertUsers(n3.users, ['zaizee'])
        with self.assertQueryCount(1):
            self.assertUsers(n4.users, ['mickey'])
        with self.assertQueryCount(1):
            self.assertUsers(n5.users, ['huey', 'zaizee'])

        with self.assertQueryCount(1):
            n1.users.remove(User.select())
        with self.assertQueryCount(1):
            n5.users.remove([charlie, huey])

        with self.assertQueryCount(1):
            self.assertUsers(n1.users, [])
        with self.assertQueryCount(1):
            self.assertUsers(n5.users, ['zaizee'])


class Person(BaseModel):
    name = CharField()

class Soul(BaseModel):
    person = ForeignKeyField(Person, primary_key=True)

class SoulList(BaseModel):
    name = CharField()
    souls = ManyToManyField(Soul, related_name='lists')

SoulListThrough = SoulList.souls.get_through_model()

class TestForeignKeyPrimaryKeyManyToMany(ModelTestCase):
    requires = [Person, Soul, SoulList, SoulListThrough]
    test_data = (
        ('huey', ('cats', 'evil')),
        ('zaizee', ('cats', 'good')),
        ('mickey', ('dogs', 'good')),
        ('zombie', ()),
    )

    def setUp(self):
        super(TestForeignKeyPrimaryKeyManyToMany, self).setUp()

        name2list = {}
        for name, lists in self.test_data:
            p = Person.create(name=name)
            s = Soul.create(person=p)
            for l in lists:
                if l not in name2list:
                    name2list[l] = SoulList.create(name=l)
                name2list[l].souls.add(s)

    def soul_for(self, name):
        return Soul.select().join(Person).where(Person.name == name).get()

    def assertLists(self, l1, l2):
        self.assertEqual(sorted(list(l1)), sorted(list(l2)))

    def test_pk_is_fk(self):
        list2names = {}
        for name, lists in self.test_data:
            soul = self.soul_for(name)
            self.assertLists([l.name for l in soul.lists],
                             lists)
            for l in lists:
                list2names.setdefault(l, [])
                list2names[l].append(name)

        for list_name, names in list2names.items():
            soul_list = SoulList.get(SoulList.name == list_name)
            self.assertLists([s.person.name for s in soul_list.souls],
                             names)

    def test_empty(self):
        sl = SoulList.create(name='empty')
        self.assertEqual(list(sl.souls), [])
