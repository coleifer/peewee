import os
import platform
import sys
try:
    from distutils.errors import CCompilerError
    from distutils.errors import DistutilsExecError
    from distutils.errors import DistutilsPlatformError
except ImportError:
    from setuptools._distutils.errors import CCompilerError
    from setuptools._distutils.errors import DistutilsExecError
    from setuptools._distutils.errors import DistutilsPlatformError

from setuptools import setup
from setuptools.extension import Extension

extension_support = True  # Assume we are building C extensions.

# Check if Cython is available and use it to generate extension modules. If
# Cython is not installed, we will fall back to using the pre-generated C files
# (so long as we're running on CPython).
try:
    from Cython.Build import cythonize
    from Cython.Distutils.extension import Extension
except ImportError:
    cython_installed = False
else:
    if platform.python_implementation() != 'CPython':
        cython_installed = extension_support = False
    else:
        cython_installed = True

if sys.version_info[0] < 3:
    FileNotFoundError = EnvironmentError

if cython_installed:
    src_ext = '.pyx'
else:
    src_ext = '.c'
    cythonize = lambda obj: obj

sqlite_udf_module = Extension(
    'playhouse._sqlite_udf',
    ['playhouse/_sqlite_udf' + src_ext])
sqlite_ext_module = Extension(
    'playhouse._sqlite_ext',
    ['playhouse/_sqlite_ext' + src_ext],
    libraries=['sqlite3'])

ext_modules = cythonize([sqlite_udf_module, sqlite_ext_module])

def _have_sqlite_extension_support():
    import shutil
    import tempfile
    try:
        from distutils.ccompiler import new_compiler
        from distutils.sysconfig import customize_compiler
    except ImportError:
        from setuptools.command.build_ext import customize_compiler
        from setuptools.command.build_ext import new_compiler

    libraries = ['sqlite3']
    c_code = ('#include <sqlite3.h>\n\n'
              'int main(int argc, char **argv) { return 0; }')
    tmp_dir = tempfile.mkdtemp(prefix='tmp_pw_sqlite3_')
    bin_file = os.path.join(tmp_dir, 'test_pw_sqlite3')
    src_file = bin_file + '.c'
    with open(src_file, 'w') as fh:
        fh.write(c_code)

    compiler = new_compiler()
    customize_compiler(compiler)
    success = False
    try:
        compiler.link_shared_object(
            compiler.compile([src_file], output_dir=tmp_dir),
            bin_file,
            libraries=['sqlite3'])
    except CCompilerError:
        print('unable to compile sqlite3 C extensions - missing headers?')
    except DistutilsExecError:
        print('unable to compile sqlite3 C extensions - no c compiler?')
    except DistutilsPlatformError:
        print('unable to compile sqlite3 C extensions - platform error')
    except FileNotFoundError:
        print('unable to compile sqlite3 C extensions - no compiler!')
    else:
        success = True
    shutil.rmtree(tmp_dir)
    return success

if extension_support:
    if os.environ.get('NO_SQLITE'):
        print('SQLite extensions will not be built at users request.')
        ext_modules = []
    elif not _have_sqlite_extension_support():
        print('Could not find libsqlite3, extensions will not be built.')
        ext_modules = []
else:
    ext_modules = []

setup(name='peewee',
      packages=['playhouse'],
      py_modules=['peewee', 'pwiz'],
      ext_modules=ext_modules)
