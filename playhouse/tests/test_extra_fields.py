import random
import sys

from peewee import *
from playhouse.fields import *
try:
    from playhouse.fields import AESEncryptedField
except ImportError:
    AESEncryptedField = None
try:
    from playhouse.fields import PasswordField
except ImportError:
    PasswordField = None
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import skip_if
from playhouse.tests.base import ulit
from playhouse.tests.base import TestModel

PY2 = sys.version_info[0] == 2


db = database_initializer.get_in_memory_database()


class BaseModel(Model):
    class Meta:
        database = db


class CompressedModel(BaseModel):
    data = CompressedField()


class PickledModel(BaseModel):
    data = PickledField()


def convert_to_str(binary_data):
    if PY2:
        return str(binary_data)
    else:
        if isinstance(binary_data, str):
            return bytes(binary_data, 'utf-8')
        return binary_data


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


@skip_if(lambda: PasswordField is None)
class TestPasswordFields(ModelTestCase):
    def setUp(self):
        class PasswordModel(TestModel):
            username = TextField()
            password = PasswordField(iterations=4)

        self.PasswordModel = PasswordModel
        self.requires = [PasswordModel]
        super(TestPasswordFields, self).setUp()

    def test_valid_password(self):
        test_pwd = 'Hello!:)'

        tm = self.PasswordModel.create(username='User', password=test_pwd)
        tm_db = self.PasswordModel.get(self.PasswordModel.id == tm.id)

        self.assertTrue(tm_db.password.check_password(test_pwd),'Correct password did not match')

    def test_invalid_password(self):
        test_pwd = 'Hello!:)'

        tm = self.PasswordModel.create(username='User', password=test_pwd)
        tm_db = self.PasswordModel.get(self.PasswordModel.id == tm.id)

        self.assertFalse(tm_db.password.check_password('a'+test_pwd),'Incorrect password did match')

    def test_unicode(self):
        test_pwd = ulit('H\u00c3l\u00c5o!:)')

        tm = self.PasswordModel.create(username='User', password=test_pwd)
        tm_db = self.PasswordModel.get(self.PasswordModel.id == tm.id)

        self.assertTrue(tm_db.password.check_password(test_pwd),'Correct unicode password did not match')


class TestPickledField(ModelTestCase):
    requires = [PickledModel]

    def test_pickled_field(self):
        test_1 = {'foo': [0, 1, '2']}
        test_2 = ['bar', ('nuggie', 'baze')]

        p1 = PickledModel.create(data=test_1)
        p2 = PickledModel.create(data=test_2)

        p1_db = PickledModel.get(PickledModel.id == p1.id)
        self.assertEqual(p1_db.data, test_1)

        p2_db = PickledModel.get(PickledModel.id == p2.id)
        self.assertEqual(p2_db.data, test_2)

        p1_db_g = PickledModel.get(PickledModel.data == test_1)
        self.assertEqual(p1_db_g.id, p1_db.id)
