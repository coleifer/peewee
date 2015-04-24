import random
import sys

from peewee import *
from playhouse.shortcuts import *
try:
    from playhouse.shortcuts import AESEncryptedField
except ImportError:
    AESEncryptedField = None
from playhouse.test_utils import assert_query_count
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import skip_if

PY2 = sys.version_info[0] == 2


db = database_initializer.get_in_memory_database()


class BaseModel(Model):
    class Meta:
        database = db


class TestModel(BaseModel):
    name = CharField()
    number = IntegerField()


class Category(BaseModel):
    name = CharField()
    parent = ForeignKeyField('self', null=True, related_name='children')


class User(BaseModel):
    username = CharField()


class Note(BaseModel):
    user = ForeignKeyField(User, related_name='notes')
    text = TextField()


class Tag(BaseModel):
    tag = CharField()


class NoteTag(BaseModel):
    note = ForeignKeyField(Note)
    tag = ForeignKeyField(Tag)


MODELS = [
    Category,
    User,
    Note,
    Tag,
    NoteTag]


class CompressedModel(BaseModel):
    data = CompressedField()


def convert_to_str(binary_data):
    if PY2:
        return str(binary_data)
    else:
        if isinstance(binary_data, str):
            return bytes(binary_data, 'utf-8')
        return binary_data


class TestCastShortcut(ModelTestCase):
    requires = [User]

    def test_cast_shortcut(self):
        for username in ['100', '001', '101']:
            User.create(username=username)

        query = (User
                 .select(
                     User.username,
                     cast(User.username, 'int').alias('username_i'))
                 .order_by(SQL('username_i')))
        results = [(user.username, user.username_i) for user in query]
        self.assertEqual(results, [
            ('001', 1),
            ('100', 100),
            ('101', 101),
        ])


class TestCaseShortcut(ModelTestCase):
    requires = [TestModel]
    values = (
        ('alpha', 1),
        ('beta', 2),
        ('gamma', 3))

    expected = [
        {'name': 'alpha', 'number_string': 'one'},
        {'name': 'beta', 'number_string': 'two'},
        {'name': 'gamma', 'number_string': '?'},
    ]

    def setUp(self):
        super(TestCaseShortcut, self).setUp()

        for name, number in self.values:
            TestModel.create(name=name, number=number)

    def test_predicate(self):
        query = (TestModel
                 .select(TestModel.name, case(TestModel.number, (
                     (1, "one"),
                     (2, "two")), "?").alias('number_string'))
                 .order_by(TestModel.id))
        self.assertEqual(list(query.dicts()), self.expected)

    def test_no_predicate(self):
        query = (TestModel
                 .select(TestModel.name, case(None, (
                     (TestModel.number == 1, "one"),
                     (TestModel.number == 2, "two")), "?").alias('number_string'))
                 .order_by(TestModel.id))
        self.assertEqual(list(query.dicts()), self.expected)


class TestCompressedField(ModelTestCase):
    requires = [CompressedModel]

    def get_raw(self, cm):
        curs = db.execute_sql('SELECT data FROM %s WHERE id = %s;' %
                              (CompressedModel._meta.db_table, cm.id))
        return convert_to_str(curs.fetchone()[0])

    def test_compressed_field(self):
        a_kb = 'a' * 1024
        b_kb = 'b' * 1024
        c_kb = 'c' * 1024
        d_kb = 'd' * 1024
        four_kb = ''.join((a_kb, b_kb, c_kb, d_kb))
        data = four_kb * 16  # 64kb of data.
        cm = CompressedModel.create(data=data)
        cm_db = CompressedModel.get(CompressedModel.id == cm.id)
        self.assertEqual(cm_db.data, data)

        db_data = self.get_raw(cm)
        compressed = len(db_data) / float(len(data))
        self.assertTrue(compressed < .01)

    def test_compress_random_data(self):
        data = ''.join(
            chr(random.randint(ord('A'), ord('z')))
            for i in range(1024))
        cm = CompressedModel.create(data=data)
        cm_db = CompressedModel.get(CompressedModel.id == cm.id)
        self.assertEqual(cm_db.data, data)


@skip_if(lambda: AESEncryptedField is None)
class TestAESEncryptedField(ModelTestCase):
    def setUp(self):
        class EncryptedModel(BaseModel):
            data = AESEncryptedField(key='testing')

        self.EncryptedModel = EncryptedModel
        self.requires = [EncryptedModel]
        super(TestAESEncryptedField, self).setUp()

    def test_encrypt_decrypt(self):
        field = self.EncryptedModel.data

        keys = ['testing', 'abcdefghijklmnop', 'a' * 31, 'a' * 32]
        for key in keys:
            field.key = key
            for i in range(128):
                data = ''.join(chr(65 + (j % 26)) for j in range(i))
                encrypted = field.encrypt(data)
                decrypted = field.decrypt(encrypted)
                self.assertEqual(len(decrypted), i)
                if PY2:
                    self.assertEqual(decrypted, data)
                else:
                    self.assertEqual(decrypted, convert_to_str(data))

    def test_encrypted_field(self):
        EM = self.EncryptedModel
        test_str = 'abcdefghij'
        em = EM.create(data=test_str)
        em_db = EM.get(EM.id == em.id)
        self.assertEqual(em_db.data, convert_to_str(test_str))

        curs = db.execute_sql('SELECT data FROM %s WHERE id = %s' %
                              (EM._meta.db_table, em.id))
        raw_data = curs.fetchone()[0]
        self.assertNotEqual(raw_data, test_str)
        decrypted = EM.data.decrypt(raw_data)
        if PY2:
            self.assertEqual(decrypted, test_str)
        else:
            self.assertEqual(decrypted, convert_to_str(test_str))

        EM.data.key = 'testingX'
        em_db_2 = EM.get(EM.id == em.id)
        self.assertNotEqual(em_db_2.data, test_str)

        # Because we pad the key with spaces until it is 32 bytes long, a
        # trailing space looks like the same key we used to encrypt with.
        EM.data.key = 'testing  '
        em_db_3 = EM.get(EM.id == em.id)
        self.assertEqual(em_db_3.data, convert_to_str(test_str))


class TestModelToDict(ModelTestCase):
    requires = MODELS

    def setUp(self):
        super(TestModelToDict, self).setUp()
        self.user = User.create(username='peewee')

    def test_simple(self):
        with assert_query_count(0):
            self.assertEqual(model_to_dict(self.user), {
                'id': self.user.id,
                'username': self.user.username})

    def test_simple_recurse(self):
        note = Note.create(user=self.user, text='note-1')

        with assert_query_count(0):
            self.assertEqual(model_to_dict(note), {
                'id': note.id,
                'text': note.text,
                'user': {
                    'id': self.user.id,
                    'username': self.user.username}})

        with assert_query_count(0):
            self.assertEqual(model_to_dict(note, recurse=False), {
                'id': note.id,
                'text': note.text,
                'user': self.user.id,
            })

    def test_simple_backref(self):
        with assert_query_count(1):
            self.assertEqual(model_to_dict(self.user, backrefs=True), {
                'id': self.user.id,
                'notes': [],
                'username': self.user.username})

        # Create a note to populate backrefs list.
        note = Note.create(user=self.user, text='note-1')

        expected = {
            'id': self.user.id,
            'notes': [
                {'id': note.id, 'notetag_set': [], 'text': note.text},
            ],
            'username': self.user.username}

        # Two queries: one to get related notes, one to get related notetags.
        with assert_query_count(2):
            self.assertEqual(
                model_to_dict(self.user, backrefs=True),
                expected)

        query = (User
                 .select(User, Note, NoteTag)
                 .join(Note, JOIN.LEFT_OUTER)
                 .join(NoteTag, JOIN.LEFT_OUTER)
                 .aggregate_rows())
        user = query.get()

        with assert_query_count(0):
            self.assertEqual(model_to_dict(user, backrefs=True), expected)

    def test_recurse_backrefs(self):
        note = Note.create(user=self.user, text='note-1')

        # One query to retrieve the note-tag set.
        with assert_query_count(1):
            self.assertEqual(model_to_dict(note, backrefs=True), {
                'id': note.id,
                'notetag_set': [],
                'text': note.text,
                'user': {
                    'id': self.user.id,
                    'username': self.user.username,
                },
            })

    def test_recursive_fk(self):
        root = Category.create(name='root')
        child = Category.create(name='child', parent=root)
        grandchild = Category.create(name='grandchild', parent=child)

        with assert_query_count(0):
            self.assertEqual(model_to_dict(root), {
                'id': root.id,
                'name': root.name,
                'parent': {},
            })

        with assert_query_count(0):
            self.assertEqual(model_to_dict(root, recurse=False), {
                'id': root.id,
                'name': root.name,
                'parent': None,
            })

        with assert_query_count(1):
            self.assertEqual(model_to_dict(root, backrefs=True), {
                'children': [{'id': child.id, 'name': child.name}],
                'id': root.id,
                'name': root.name,
                'parent': {},
            })

        with assert_query_count(1):
            self.assertEqual(model_to_dict(child, backrefs=True), {
                'children': [{'id': grandchild.id, 'name': grandchild.name}],
                'id': child.id,
                'name': child.name,
                'parent': {
                    'id': root.id,
                    'name': root.name,
                },
            })

        with assert_query_count(0):
            self.assertEqual(model_to_dict(child, backrefs=False), {
                'id': child.id,
                'name': child.name,
                'parent': {
                    'id': root.id,
                    'name': root.name,
                },
            })

    def test_many_to_many(self):
        note = Note.create(user=self.user, text='note-1')
        t1 = Tag.create(tag='t1')
        t2 = Tag.create(tag='t2')
        Tag.create(tag='tx')  # Note used on any notes.
        nt1 = NoteTag.create(note=note, tag=t1)
        nt2 = NoteTag.create(note=note, tag=t2)

        expected = {
            'id': self.user.id,
            'notes': [{
                'id': note.id,
                'notetag_set': [
                    {'id': nt1.id, 'tag': {'id': t1.id, 'tag': t1.tag}},
                    {'id': nt2.id, 'tag': {'id': t2.id, 'tag': t2.tag}},
                ],
                'text': note.text,
            }],
            'username': self.user.username,
        }

        # Query to retrieve notes, note-tags, and 2 tag queries.
        with assert_query_count(4):
            self.assertEqual(
                model_to_dict(self.user, backrefs=True),
                expected)

    def test_only(self):
        expected = {'username': self.user.username}
        self.assertEqual(
            model_to_dict(self.user, only=[User.username]),
            expected)

        self.assertEqual(
            model_to_dict(self.user, backrefs=True, only=[User.username]),
            expected)

        note = Note.create(user=self.user, text='note-1')
        expected = {'text': note.text, 'user': {
            'username': self.user.username}}
        self.assertEqual(
            model_to_dict(note, only=[Note.text, Note.user, User.username]),
            expected)
        self.assertEqual(
            model_to_dict(
                note,
                backrefs=True,
                only=[Note.text, Note.user, User.username]),
            expected)

        expected['user'] = self.user.id
        self.assertEqual(
            model_to_dict(
                note,
                backrefs=True,
                recurse=False,
                only=[Note.text, Note.user, User.username]),
            expected)

    def test_exclude(self):
        self.assertEqual(
            model_to_dict(self.user, exclude=[User.id]),
            {'username': self.user.username})

        self.assertEqual(
            model_to_dict(
                self.user,
                backrefs=True,
                exclude=[User.id, Note.user]),
            {'username': self.user.username})

        self.assertEqual(
            model_to_dict(
                self.user,
                backrefs=True,
                exclude=[User.id, User.notes]),
            {'username': self.user.username})

        note = Note.create(user=self.user, text='note-1')
        self.assertEqual(
            model_to_dict(
                note,
                backrefs=True,
                exclude=[Note.user, Note.notetag_set, Note.id]),
            {'text': note.text})

        self.assertEqual(
            model_to_dict(
                note,
                backrefs=True,
                exclude=[User.id, Note.notetag_set, Note.id]),
            {'text': note.text, 'user': {'username': self.user.username}})


class TestDictToModel(ModelTestCase):
    requires = MODELS

    def setUp(self):
        super(TestDictToModel, self).setUp()
        self.user = User.create(username='charlie')

    def test_simple(self):
        data = {'username': 'charlie', 'id': self.user.id}
        inst = dict_to_model(User, data)
        self.assertTrue(isinstance(inst, User))
        self.assertEqual(inst.username, 'charlie')
        self.assertEqual(inst.id, self.user.id)

    def test_related(self):
        data = {
            'id': 2,
            'text': 'note-1',
            'user': {
                'id': self.user.id,
                'username': 'charlie'}}

        with assert_query_count(0):
            inst = dict_to_model(Note, data)
            self.assertTrue(isinstance(inst, Note))
            self.assertEqual(inst.id, 2)
            self.assertEqual(inst.text, 'note-1')
            self.assertTrue(isinstance(inst.user, User))
            self.assertEqual(inst.user.id, self.user.id)
            self.assertEqual(inst.user.username, 'charlie')

        data['user'] = self.user.id

        with assert_query_count(0):
            inst = dict_to_model(Note, data)

        with assert_query_count(1):
            self.assertEqual(inst.user, self.user)

    def test_backrefs(self):
        data = {
            'id': self.user.id,
            'username': 'charlie',
            'notes': [
                {'id': 1, 'text': 'note-1'},
                {'id': 2, 'text': 'note-2'},
            ]}

        with assert_query_count(0):
            inst = dict_to_model(User, data)
            self.assertEqual(inst.id, self.user.id)
            self.assertEqual(inst.username, 'charlie')
            self.assertTrue(isinstance(inst.notes, list))

            note_1, note_2 = inst.notes
            self.assertEqual(note_1.id, 1)
            self.assertEqual(note_1.text, 'note-1')
            self.assertEqual(note_1.user, self.user)

            self.assertEqual(note_2.id, 2)
            self.assertEqual(note_2.text, 'note-2')
            self.assertEqual(note_2.user, self.user)

    def test_unknown_attributes(self):
        data = {
            'id': self.user.id,
            'username': 'peewee',
            'xx': 'does not exist'}
        self.assertRaises(
            AttributeError,
            dict_to_model,
            User,
            data)

        inst = dict_to_model(User, data, ignore_unknown=True)
        self.assertEqual(inst.xx, 'does not exist')


def add(lhs, rhs):
    return lhs + rhs

def sub(lhs, rhs):
    return lhs - rhs

P = Infix(add)
S = Infix(sub)

class TestInfix(PeeweeTestCase):
    def test_infix(self):
        result = 1 |P| 2
        self.assertEqual(result, 3)
        self.assertEqual(3 |P| 6, 9)

        result = 4 |S| 5
        self.assertEqual(result, -1)
        self.assertEqual(4 |S| 1, 3)

        result = 1 |P| 3 |S| 5 |P| 2 |S| 4
        self.assertEqual(result, -3)
