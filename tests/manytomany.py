from peewee import *

from .base import ModelTestCase
from .base import TestModel
from .base import get_in_memory_db
from .base import requires_models
from .base_models import Tweet
from .base_models import User


class User(TestModel):
    username = TextField(unique=True)

class Note(TestModel):
    text = TextField()
    users = ManyToManyField(User)

NoteUserThrough = Note.users.get_through_model()

AltThroughDeferred = DeferredThroughModel()

class AltNote(TestModel):
    text = TextField()
    users = ManyToManyField(User, through_model=AltThroughDeferred)

class AltThroughModel(TestModel):
    user = ForeignKeyField(User, backref='_xx_rel')
    note = ForeignKeyField(AltNote, backref='_xx_rel')

    class Meta:
        primary_key = CompositeKey('user', 'note')

AltThroughDeferred.set_model(AltThroughModel)

class Student(TestModel):
    name = TextField()

CourseStudentDeferred = DeferredThroughModel()

class Course(TestModel):
    name = TextField()
    students = ManyToManyField(Student, backref='+')
    students2 = ManyToManyField(Student, through_model=CourseStudentDeferred)

CourseStudent = Course.students.get_through_model()

class CourseStudent2(TestModel):
    course = ForeignKeyField(Course, backref='+')
    student = ForeignKeyField(Student, backref='+')

CourseStudentDeferred.set_model(CourseStudent2)


class Color(TestModel):
    name = TextField(unique=True)

LogoColorDeferred = DeferredThroughModel()

class Logo(TestModel):
    name = TextField(unique=True)
    colors = ManyToManyField(Color, through_model=LogoColorDeferred)

class LogoColor(TestModel):
    logo = ForeignKeyField(Logo, field=Logo.name)
    color = ForeignKeyField(Color, field=Color.name)  # FK to non-PK column.

LogoColorDeferred.set_model(LogoColor)


class TestManyToManyFKtoNonPK(ModelTestCase):
    database = get_in_memory_db()
    requires = [Color, Logo, LogoColor]

    def test_manytomany_fk_to_non_pk(self):
        red = Color.create(name='red')
        green = Color.create(name='green')
        blue = Color.create(name='blue')
        lrg = Logo.create(name='logo-rg')
        lrb = Logo.create(name='logo-rb')
        lrgb = Logo.create(name='logo-rgb')
        lrg.colors.add([red, green])
        lrb.colors.add([red, blue])
        lrgb.colors.add([red, green, blue])

        def assertColors(logo, expected):
            colors = [c.name for c in logo.colors.order_by(Color.name)]
            self.assertEqual(colors, expected)

        assertColors(lrg, ['green', 'red'])
        assertColors(lrb, ['blue', 'red'])
        assertColors(lrgb, ['blue', 'green', 'red'])

        def assertLogos(color, expected):
            logos = [l.name for l in color.logos.order_by(Logo.name)]
            self.assertEqual(logos, expected)

        assertLogos(red, ['logo-rb', 'logo-rg', 'logo-rgb'])
        assertLogos(green, ['logo-rg', 'logo-rgb'])
        assertLogos(blue, ['logo-rb', 'logo-rgb'])

        # Verify we can delete data as well.
        lrg.colors.remove(red)
        self.assertEqual([c.name for c in lrg.colors], ['green'])

        blue.logos.remove(lrb)
        self.assertEqual([c.name for c in lrb.colors], ['red'])

        # Verify we can insert using a SELECT query.
        lrg.colors.add(Color.select().where(Color.name != 'blue'), True)
        assertColors(lrg, ['green', 'red'])

        lrb.colors.add(Color.select().where(Color.name == 'blue'))
        assertColors(lrb, ['blue', 'red'])

        # Verify we can insert logos using a SELECT query.
        black = Color.create(name='black')
        black.logos.add(Logo.select().where(Logo.name != 'logo-rgb'))
        assertLogos(black, ['logo-rb', 'logo-rg'])
        assertColors(lrb, ['black', 'blue', 'red'])
        assertColors(lrg, ['black', 'green', 'red'])
        assertColors(lrgb, ['blue', 'green', 'red'])

        # Verify we can delete using a SELECT query.
        lrg.colors.remove(Color.select().where(Color.name == 'red'))
        assertColors(lrg, ['black', 'green'])

        black.logos.remove(Logo.select().where(Logo.name == 'logo-rg'))
        assertLogos(black, ['logo-rb'])

        # Verify we can clear.
        lrg.colors.clear()
        assertColors(lrg, [])
        assertColors(lrb, ['black', 'blue', 'red'])  # Not affected.

        black.logos.clear()
        assertLogos(black, [])
        assertLogos(red, ['logo-rb', 'logo-rgb'])


class TestManyToManyBackrefBehavior(ModelTestCase):
    database = get_in_memory_db()
    requires = [Student, Course, CourseStudent, CourseStudent2]

    def setUp(self):
        super(TestManyToManyBackrefBehavior, self).setUp()
        math = Course.create(name='math')
        engl = Course.create(name='engl')
        huey, mickey, zaizee = [Student.create(name=name)
                                for name in ('huey', 'mickey', 'zaizee')]
        # Set up relationships.
        math.students.add([huey, zaizee])
        engl.students.add([mickey])
        math.students2.add([mickey])
        engl.students2.add([huey, zaizee])

    def test_manytomanyfield_disabled_backref(self):
        math = Course.get(name='math')
        query = math.students.order_by(Student.name)
        self.assertEqual([s.name for s in query], ['huey', 'zaizee'])

        huey = Student.get(name='huey')
        math.students.remove(huey)
        self.assertEqual([s.name for s in math.students], ['zaizee'])

        # The backref is via the CourseStudent2 through-model.
        self.assertEqual([c.name for c in huey.courses], ['engl'])

    def test_through_model_disabled_backrefs(self):
        # Here we're testing the case where the many-to-many field does not
        # explicitly disable back-references, but the foreign-keys on the
        # through model have disabled back-references.
        engl = Course.get(name='engl')
        query = engl.students2.order_by(Student.name)
        self.assertEqual([s.name for s in query], ['huey', 'zaizee'])

        zaizee = Student.get(Student.name == 'zaizee')
        engl.students2.remove(zaizee)
        self.assertEqual([s.name for s in engl.students2], ['huey'])

        math = Course.get(name='math')
        self.assertEqual([s.name for s in math.students2], ['mickey'])


class TestManyToManyInheritance(ModelTestCase):
    def test_manytomany_inheritance(self):
        class BaseModel(TestModel):
            class Meta:
                database = self.database
        class User(BaseModel):
            username = TextField()
        class Project(BaseModel):
            name = TextField()
            users = ManyToManyField(User, backref='projects')

        def subclass_project():
            class VProject(Project):
                pass

        # We cannot subclass Project, because the many-to-many field "users"
        # will be inherited, but the through-model does not contain a
        # foreign-key to VProject. The through-model in this case is
        # ProjectUsers, which has foreign-keys to project and user.
        self.assertRaises(ValueError, subclass_project)
        PThrough = Project.users.through_model
        self.assertTrue(PThrough.project.rel_model is Project)
        self.assertTrue(PThrough.user.rel_model is User)


class TestManyToMany(ModelTestCase):
    database = get_in_memory_db()
    requires = [User, Note, NoteUserThrough, AltNote, AltThroughModel]

    user_to_note = {
        'gargie': [1, 2],
        'huey': [2, 3],
        'mickey': [3, 4],
        'zaizee': [4, 5],
    }

    def setUp(self):
        super(TestManyToMany, self).setUp()
        for username in sorted(self.user_to_note):
            User.create(username=username)
        for i in range(5):
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

    def _set_data(self):
        for username, notes in self.user_to_note.items():
            user = User.get(User.username == username)
            for note in notes:
                NoteUserThrough.create(
                    note=Note.get(Note.text == 'note-%s' % note),
                    user=user)

    def assertNotes(self, query, expected):
        notes = [note.text for note in query]
        self.assertEqual(sorted(notes),
                         ['note-%s' % i for i in sorted(expected)])

    def assertUsers(self, query, expected):
        usernames = [user.username for user in query]
        self.assertEqual(sorted(usernames), sorted(expected))

    def test_accessor_query(self):
        self._set_data()
        gargie, huey, mickey, zaizee = User.select().order_by(User.username)

        with self.assertQueryCount(1):
            self.assertNotes(gargie.notes, [1, 2])
        with self.assertQueryCount(1):
            self.assertNotes(zaizee.notes, [4, 5])
        with self.assertQueryCount(2):
            self.assertNotes(User.create(username='x').notes, [])

        n1, n2, n3, n4, n5 = Note.select().order_by(Note.text)
        with self.assertQueryCount(1):
            self.assertUsers(n1.users, ['gargie'])
        with self.assertQueryCount(1):
            self.assertUsers(n2.users, ['gargie', 'huey'])
        with self.assertQueryCount(1):
            self.assertUsers(n5.users, ['zaizee'])
        with self.assertQueryCount(2):
            self.assertUsers(Note.create(text='x').users, [])

    def test_prefetch_notes(self):
        self._set_data()
        with self.assertQueryCount(3):
            gargie, huey, mickey, zaizee = prefetch(
                User.select().order_by(User.username),
                NoteUserThrough,
                Note)

        with self.assertQueryCount(0):
            self.assertNotes(gargie.notes, [1, 2])
        with self.assertQueryCount(0):
            self.assertNotes(zaizee.notes, [4, 5])
        with self.assertQueryCount(2):
            self.assertNotes(User.create(username='x').notes, [])

    def test_prefetch_users(self):
        self._set_data()
        with self.assertQueryCount(3):
            n1, n2, n3, n4, n5 = prefetch(
                Note.select().order_by(Note.text),
                NoteUserThrough,
                User)

        with self.assertQueryCount(0):
            self.assertUsers(n1.users, ['gargie'])
        with self.assertQueryCount(0):
            self.assertUsers(n2.users, ['gargie', 'huey'])
        with self.assertQueryCount(0):
            self.assertUsers(n5.users, ['zaizee'])
        with self.assertQueryCount(2):
            self.assertUsers(Note.create(text='x').users, [])

    def test_query_filtering(self):
        self._set_data()
        gargie, huey, mickey, zaizee = User.select().order_by(User.username)

        with self.assertQueryCount(1):
            notes = gargie.notes.where(Note.text != 'note-2')
            self.assertNotes(notes, [1])

    def test_set_value(self):
        self._set_data()
        gargie = User.get(User.username == 'gargie')
        huey = User.get(User.username == 'huey')
        n1, n2, n3, n4, n5 = Note.select().order_by(Note.text)

        with self.assertQueryCount(2):
            gargie.notes = n3
        self.assertNotes(gargie.notes, [3])
        self.assertUsers(n3.users, ['gargie', 'huey', 'mickey'])
        self.assertUsers(n1.users, [])

        gargie.notes = [n3, n4]
        self.assertNotes(gargie.notes, [3, 4])
        self.assertUsers(n3.users, ['gargie', 'huey', 'mickey'])
        self.assertUsers(n4.users, ['gargie', 'mickey', 'zaizee'])

    def test_set_query(self):
        huey = User.get(User.username == 'huey')

        with self.assertQueryCount(2):
            huey.notes = Note.select().where(~Note.text.endswith('4'))
        self.assertNotes(huey.notes, [1, 2, 3, 5])

    def test_add(self):
        gargie = User.get(User.username == 'gargie')
        huey = User.get(User.username == 'huey')
        n1, n2, n3, n4, n5 = Note.select().order_by(Note.text)

        gargie.notes.add([n1, n2])
        self.assertNotes(gargie.notes, [1, 2])
        self.assertUsers(n1.users, ['gargie'])
        self.assertUsers(n2.users, ['gargie'])
        for note in [n3, n4, n5]:
            self.assertUsers(note.users, [])

        with self.assertQueryCount(1):
            huey.notes.add(Note.select().where(
                fn.substr(Note.text, 6, 1) << ['1', '3', '5']))

        self.assertNotes(huey.notes, [1, 3, 5])
        self.assertUsers(n1.users, ['gargie', 'huey'])
        self.assertUsers(n2.users, ['gargie'])
        self.assertUsers(n3.users, ['huey'])
        self.assertUsers(n4.users, [])
        self.assertUsers(n5.users, ['huey'])

        with self.assertQueryCount(1):
            gargie.notes.add(n4)
        self.assertNotes(gargie.notes, [1, 2, 4])

        with self.assertQueryCount(2):
            n3.users.add(
                User.select().where(User.username != 'gargie'),
                clear_existing=True)
        self.assertUsers(n3.users, ['huey', 'mickey', 'zaizee'])

    def test_add_by_pk(self):
        huey = User.get(User.username == 'huey')
        n1, n2, n3 = Note.select().order_by(Note.text).limit(3)
        huey.notes.add([n1.id, n2.id])
        self.assertNotes(huey.notes, [1, 2])
        self.assertUsers(n1.users, ['huey'])
        self.assertUsers(n2.users, ['huey'])
        self.assertUsers(n3.users, [])

    def test_unique(self):
        n1 = Note.get(Note.text == 'note-1')
        huey = User.get(User.username == 'huey')

        def add_user(note, user):
            with self.assertQueryCount(1):
                note.users.add(user)

        add_user(n1, huey)
        self.assertRaises(IntegrityError, add_user, n1, huey)

        add_user(n1, User.get(User.username == 'zaizee'))
        self.assertUsers(n1.users, ['huey', 'zaizee'])

    def test_remove(self):
        self._set_data()
        gargie, huey, mickey, zaizee = User.select().order_by(User.username)
        n1, n2, n3, n4, n5 = Note.select().order_by(Note.text)

        with self.assertQueryCount(1):
            gargie.notes.remove([n1, n2, n3])

        self.assertNotes(gargie.notes, [])
        self.assertNotes(huey.notes, [2, 3])

        with self.assertQueryCount(1):
            huey.notes.remove(Note.select().where(
                Note.text << ['note-2', 'note-4', 'note-5']))

        self.assertNotes(huey.notes, [3])
        self.assertNotes(mickey.notes, [3, 4])
        self.assertNotes(zaizee.notes, [4, 5])

        with self.assertQueryCount(1):
            n4.users.remove([gargie, mickey])
        self.assertUsers(n4.users, ['zaizee'])

        with self.assertQueryCount(1):
            n5.users.remove(User.select())
        self.assertUsers(n5.users, [])

    def test_remove_by_id(self):
        self._set_data()
        gargie, huey = User.select().order_by(User.username).limit(2)
        n1, n2, n3, n4 = Note.select().order_by(Note.text).limit(4)
        gargie.notes.add([n3, n4])

        with self.assertQueryCount(1):
            gargie.notes.remove([n1.id, n3.id])

        self.assertNotes(gargie.notes, [2, 4])
        self.assertNotes(huey.notes, [2, 3])

    def test_clear(self):
        gargie = User.get(User.username == 'gargie')
        huey = User.get(User.username == 'huey')

        gargie.notes = Note.select()
        huey.notes = Note.select()

        self.assertEqual(gargie.notes.count(), 5)
        self.assertEqual(huey.notes.count(), 5)

        gargie.notes.clear()
        self.assertEqual(gargie.notes.count(), 0)
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
        gargie, huey, mickey, zaizee = User.select().order_by(User.username)
        alt_notes = []
        for i in range(5):
            alt_notes.append(AltNote.create(text='note-%s' % (i + 1)))

        self.assertNotes(gargie.altnotes, [])
        for alt_note in alt_notes:
            self.assertUsers(alt_note.users, [])

        n1, n2, n3, n4, n5 = alt_notes

        # Test adding relationships by setting the descriptor.
        gargie.altnotes = [n1, n2]

        with self.assertQueryCount(2):
            huey.altnotes = AltNote.select().where(
                fn.substr(AltNote.text, 6, 1) << ['1', '3', '5'])

        mickey.altnotes.add([n1, n4])

        with self.assertQueryCount(2):
            zaizee.altnotes = AltNote.select()

        # Test that the notes were added correctly.
        with self.assertQueryCount(1):
            self.assertNotes(gargie.altnotes, [1, 2])

        with self.assertQueryCount(1):
            self.assertNotes(huey.altnotes, [1, 3, 5])

        with self.assertQueryCount(1):
            self.assertNotes(mickey.altnotes, [1, 4])

        with self.assertQueryCount(1):
            self.assertNotes(zaizee.altnotes, [1, 2, 3, 4, 5])

        # Test removing notes.
        with self.assertQueryCount(1):
            gargie.altnotes.remove(n1)
        self.assertNotes(gargie.altnotes, [2])

        with self.assertQueryCount(1):
            huey.altnotes.remove([n1, n2, n3])
        self.assertNotes(huey.altnotes, [5])

        with self.assertQueryCount(1):
            sq = (AltNote
                  .select()
                  .where(fn.SUBSTR(AltNote.text, 6, 1) << ['1', '2', '4']))
            zaizee.altnotes.remove(sq)
        self.assertNotes(zaizee.altnotes, [3, 5])

        # Test the backside of the relationship.
        n1.users = User.select().where(User.username != 'gargie')

        with self.assertQueryCount(1):
            self.assertUsers(n1.users, ['huey', 'mickey', 'zaizee'])
        with self.assertQueryCount(1):
            self.assertUsers(n2.users, ['gargie'])
        with self.assertQueryCount(1):
            self.assertUsers(n3.users, ['zaizee'])
        with self.assertQueryCount(1):
            self.assertUsers(n4.users, ['mickey'])
        with self.assertQueryCount(1):
            self.assertUsers(n5.users, ['huey', 'zaizee'])

        with self.assertQueryCount(1):
            n1.users.remove(User.select())
        with self.assertQueryCount(1):
            n5.users.remove([gargie, huey])

        with self.assertQueryCount(1):
            self.assertUsers(n1.users, [])
        with self.assertQueryCount(1):
            self.assertUsers(n5.users, ['zaizee'])


class Person(TestModel):
    name = CharField()

class Account(TestModel):
    person = ForeignKeyField(Person, primary_key=True)

class AccountList(TestModel):
    name = CharField()
    accounts = ManyToManyField(Account, backref='lists')

AccountListThrough = AccountList.accounts.get_through_model()


class TestForeignKeyPrimaryKeyManyToMany(ModelTestCase):
    database = get_in_memory_db()
    requires = [Person, Account, AccountList, AccountListThrough]
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
            a = Account.create(person=p)
            for l in lists:
                if l not in name2list:
                    name2list[l] = AccountList.create(name=l)
                name2list[l].accounts.add(a)

    def account_for(self, name):
        return Account.select().join(Person).where(Person.name == name).get()

    def assertLists(self, l1, l2):
        self.assertEqual(sorted(list(l1)), sorted(list(l2)))

    def test_pk_is_fk(self):
        list2names = {}
        for name, lists in self.test_data:
            account = self.account_for(name)
            self.assertLists([l.name for l in account.lists],
                             lists)
            for l in lists:
                list2names.setdefault(l, [])
                list2names[l].append(name)

        for list_name, names in list2names.items():
            account_list = AccountList.get(AccountList.name == list_name)
            self.assertLists([s.person.name for s in account_list.accounts],
                             names)

    def test_empty(self):
        al = AccountList.create(name='empty')
        self.assertEqual(list(al.accounts), [])
