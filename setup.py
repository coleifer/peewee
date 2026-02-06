import platform
import os
from setuptools import setup
from setuptools.extension import Extension
try:
    from Cython.Build import cythonize
    cython_installed = True
except ImportError:
    cython_installed = False


if platform.python_implementation() != 'CPython':
    extension_support = False
elif os.environ.get('NO_SQLITE'):
    # Retain backward-compat for not building C extensions.
    extension_support = False
else:
    extension_support = True

if cython_installed:
    src_ext = '.pyx'
else:
    src_ext = '.c'
    cythonize = lambda obj: obj

if extension_support:
    sqlite_udf_module = Extension(
        'playhouse._sqlite_udf',
        ['playhouse/_sqlite_udf' + src_ext])
    ext_modules = cythonize([sqlite_udf_module])
else:
    ext_modules = []

setup(
    name='peewee',
    packages=['playhouse'],
    py_modules=['peewee', 'pwiz'],
    ext_modules=ext_modules)
