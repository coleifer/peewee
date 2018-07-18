import os
import platform
import sys
import warnings
from distutils.errors import CompileError
from distutils.errors import DistutilsExecError
from distutils.errors import LinkError

from setuptools import setup
from setuptools.extension import Extension
try:
    from ctypes.util import find_library
except ImportError:
    find_library = lambda x: None

f = open(os.path.join(os.path.dirname(__file__), 'README.rst'))
readme = f.read()
f.close()

extension_support = True  # Assume we are building C extensions.

# Check if Cython is available and use it to generate extension modules. If
# Cython is not installed, we will fall back to using the pre-generated C files
# (so long as we're running on CPython).
try:
    from Cython.Build import cythonize
except ImportError:
    cython_installed = False
else:
    if platform.python_implementation() != 'CPython':
        cython_installed = extension_support = False
        warnings.warn('C extensions disabled as you are not using CPython.')
    else:
        cython_installed = True

if cython_installed:
    src_ext = '.pyx'
else:
    src_ext = '.c'
    cythonize = lambda obj: obj

speedups_ext_module = Extension(
    'playhouse._speedups',
    ['playhouse/_speedups' + src_ext])
sqlite_udf_module = Extension(
    'playhouse._sqlite_udf',
    ['playhouse/_sqlite_udf' + src_ext])
sqlite_ext_module = Extension(
    'playhouse._sqlite_ext',
    ['playhouse/_sqlite_ext' + src_ext],
    libraries=['sqlite3'])

# This is set to True if there is extension support and libsqlite3 is found.
sqlite_extension_support = False

if extension_support:
    if os.environ.get('NO_SQLITE'):
        warnings.warn('SQLite extensions will not be built at users request.')
    elif not find_library('sqlite3'):
        warnings.warn('Could not find libsqlite3, SQLite extensions will not '
                      'be built.')
    else:
        sqlite_extension_support = True

def _do_setup(c_extensions, sqlite_extensions):
    if c_extensions:
        ext_modules = [speedups_ext_module]
        if sqlite_extensions:
            ext_modules.extend([sqlite_udf_module, sqlite_ext_module])
    else:
        ext_modules = None

    setup(
        name='peewee',
        version=__import__('peewee').__version__,
        description='a little orm',
        long_description=readme,
        author='Charles Leifer',
        author_email='coleifer@gmail.com',
        url='http://github.com/coleifer/peewee/',
        packages=['playhouse'],
        py_modules=['peewee', 'pwiz'],
        classifiers=[
            'Development Status :: 5 - Production/Stable',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: MIT License',
            'Operating System :: OS Independent',
            'Programming Language :: Python',
            'Programming Language :: Python :: 3',
        ],
        scripts = ['pwiz.py'],
        zip_safe=False,
        ext_modules=cythonize(ext_modules))


if extension_support:
    try:
        _do_setup(extension_support, sqlite_extension_support)
    except (CompileError, DistutilsExecError, LinkError):
        print('#' * 75)
        print('Error compiling C extensions, C extensions will not be built.')
        print('#' * 75)
        _do_setup(False, False)
else:
    _do_setup(False, False)
