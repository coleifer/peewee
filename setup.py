import os
import sys
from distutils.core import setup
from distutils.extension import Extension

f = open(os.path.join(os.path.dirname(__file__), 'README.rst'))
readme = f.read()
f.close()

setup_kwargs = {}
try:
    from Cython.Distutils import build_ext
except ImportError:
    cython_installed = False
else:
    cython_installed = True

speedups_ext_module = Extension(
    'playhouse._speedups',
    ['playhouse/speedups.pyx'])
sqlite_ext_module = Extension(
    'playhouse._sqlite_ext',
    ['playhouse/_sqlite_ext.pyx'])

def check_libsqlite():
    import shutil
    import tempfile
    from textwrap import dedent

    import distutils.ccompiler
    import distutils.sysconfig
    from distutils.errors import CompileError, LinkError

    libraries = ['sqlite3']
    c_code = dedent("""
        #include <sqlite3.h>

        int main(int argc, char **argv) {
            return (sqlite3_libversion_number() > 3080000) ? 0 : 1;
        }""")

    tmp_dir = tempfile.mkdtemp(prefix='tmp_peewee_')
    binary = os.path.join(tmp_dir, 'test_peewee')
    filename = binary + '.c'
    with open(filename, 'w') as fh:
        fh.write(c_code)

    compiler = distutils.ccompiler.new_compiler()
    assert isinstance(compiler, distutils.ccompiler.CCompiler)
    distutils.sysconfig.customize_compiler(compiler)

    try:
        compiler.link_executable(
            compiler.compile([filename]),
            binary,
            libraries=libraries)
    except CompileError:
        print('libsqlite3 compile error')
        return False
    except LinkError:
        print('libsqlite3 link error')
        return False
    finally:
        shutil.rmtree(tmp_dir)
    return True

ext_modules = []
if cython_installed:
    ext_modules.append(speedups_ext_module)
    if check_libsqlite() and sys.version_info[0] == 2:
        # Sorry, no python 3.
        ext_modules.append(sqlite_ext_module)

if ext_modules:
    setup_kwargs.update(
        cmdclass={'build_ext': build_ext},
        ext_modules=ext_modules)

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
    test_suite='tests',
    scripts = ['pwiz.py'],
    **setup_kwargs
)
