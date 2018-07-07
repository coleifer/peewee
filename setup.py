import os
import platform
import sys
import warnings
from setuptools import setup
from setuptools.extension import Extension

f = open(os.path.join(os.path.dirname(__file__), 'README.rst'))
readme = f.read()
f.close()

setup_kwargs = {}
ext_modules = []

try:
    from Cython.Build import cythonize
except ImportError:
    cython_installed = False
    warnings.warn('Cython C extensions for peewee will NOT be built, because '
                  'Cython does not seem to be installed. To enable Cython C '
                  'extensions, install Cython >=' + cython_min_version + '.')
else:
    if platform.python_implementation() != 'CPython':
        cython_installed = False
        warnings.warn('Cython C extensions disabled as you are not using '
                      'CPython.')
    else:
        cython_installed = True

NO_SQLITE = os.environ.get('NO_SQLITE') or False


speedups_ext_module = Extension(
    'playhouse._speedups',
    ['playhouse/_speedups.pyx'])
sqlite_udf_module = Extension(
    'playhouse._sqlite_udf',
    ['playhouse/_sqlite_udf.pyx'])
sqlite_ext_module = Extension(
    'playhouse._sqlite_ext',
    ['playhouse/_sqlite_ext.pyx'],
    libraries=['sqlite3'])


if cython_installed:
    ext_modules = [speedups_ext_module]
    if not NO_SQLITE:
        ext_modules.extend([
            sqlite_udf_module,
            sqlite_ext_module,
        ])
    else:
        warnings.warn('SQLite extensions will not be built at users request.')

if ext_modules:
    setup_kwargs.update(ext_modules=cythonize(ext_modules))

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
    **setup_kwargs)
