import os
import platform
import sys
import warnings
try:
    from distutils.command.build_ext import build_ext
    from distutils.errors import CCompilerError
    from distutils.errors import DistutilsExecError
    from distutils.errors import DistutilsPlatformError
except ImportError:
    from setuptools._distutils.command.build_ext import build_ext
    from setuptools._distutils.errors import CCompilerError
    from setuptools._distutils.errors import DistutilsExecError
    from setuptools._distutils.errors import DistutilsPlatformError

from setuptools import setup
from setuptools.extension import Extension

f = open(os.path.join(os.path.dirname(__file__), 'README.rst'))
readme = f.read()
f.close()

extension_support = True  # Assume we are building C extensions.

# Check if Cython is available and use it to generate extension modules. If
# Cython is not installed, we will fall back to using the pre-generated C files
# (so long as we're running on CPython).
try:
    from Cython.Build import cythonize
    from Cython.Distutils import build_ext
    from Cython.Distutils.extension import Extension
except ImportError:
    cython_installed = False
else:
    if platform.python_implementation() != 'CPython':
        cython_installed = extension_support = False
        warnings.warn('C extensions disabled as you are not using CPython.')
    else:
        cython_installed = True

if 'sdist' in sys.argv and not cython_installed:
    raise Exception('Building sdist requires that Cython be installed.')

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


# This is set to True if there is extension support and libsqlite3 is found.
sqlite_extension_support = False

if extension_support:
    if os.environ.get('NO_SQLITE'):
        warnings.warn('SQLite extensions will not be built at users request.')
    elif not _have_sqlite_extension_support():
        warnings.warn('Could not find libsqlite3, SQLite extensions will not '
                      'be built.')
    else:
        sqlite_extension_support = True

# Exception we will raise to indicate a failure to build C extensions.
class BuildFailure(Exception): pass

class _PeeweeBuildExt(build_ext):
    def run(self):
        try:
            build_ext.run(self)
        except DistutilsPlatformError:
            raise BuildFailure()

    def build_extension(self, ext):
        try:
            build_ext.build_extension(self, ext)
        except (CCompilerError, DistutilsExecError, DistutilsPlatformError):
            raise BuildFailure()

def _do_setup(c_extensions, sqlite_extensions):
    if c_extensions and sqlite_extensions:
        ext_modules = [sqlite_udf_module, sqlite_ext_module]
    else:
        ext_modules = None

    setup(
        name='peewee',
        version=__import__('peewee').__version__,
        description='a little orm',
        long_description=readme,
        author='Charles Leifer',
        author_email='coleifer@gmail.com',
        url='https://github.com/coleifer/peewee/',
        packages=['playhouse'],
        py_modules=['peewee', 'pwiz'],
        classifiers=[
            'Development Status :: 5 - Production/Stable',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: MIT License',
            'Operating System :: OS Independent',
            'Programming Language :: Python',
            'Programming Language :: Python :: 2',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.4',
            'Programming Language :: Python :: 3.5',
            'Programming Language :: Python :: 3.6',
            'Programming Language :: Python :: 3.7',
            'Topic :: Software Development :: Libraries :: Python Modules',
        ],
        license='MIT License',
        platforms=['any'],
        scripts=['pwiz.py'],
        zip_safe=False,
        cmdclass={'build_ext': _PeeweeBuildExt},
        ext_modules=cythonize(ext_modules))


if extension_support:
    try:
        _do_setup(extension_support, sqlite_extension_support)
    except BuildFailure:
        print('#' * 75)
        print('Error compiling C extensions, C extensions will not be built.')
        print('#' * 75)
        _do_setup(False, False)
else:
    _do_setup(False, False)
