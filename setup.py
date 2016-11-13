import os
import platform
import sys
import warnings
from distutils.core import setup
from distutils.extension import Extension
from distutils.version import StrictVersion

f = open(os.path.join(os.path.dirname(__file__), 'README.rst'))
readme = f.read()
f.close()

setup_kwargs = {}
cython_min_version = '0.22.1'

try:
    from Cython.Distutils import build_ext
    from Cython import __version__ as cython_version
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
    elif StrictVersion(cython_version) < StrictVersion(cython_min_version):
        cython_installed = False
        warnings.warn('Cython C extensions for peewee will NOT be built, '
                      'because the installed Cython version '
                      '(' + cython_version + ') is too old. To enable Cython '
                      'C extensions, install Cython >=' + cython_min_version +
                      '.')
    else:
        cython_installed = True

speedups_ext_module = Extension(
    'playhouse._speedups',
    ['playhouse/_speedups.pyx'])
sqlite_udf_module = Extension(
    'playhouse._sqlite_udf',
    ['playhouse/_sqlite_udf.pyx'])
sqlite_ext_module = Extension(
    'playhouse._sqlite_ext',
    ['playhouse/_sqlite_ext.pyx'])


ext_modules = []
if cython_installed:
    ext_modules.extend([
        speedups_ext_module,
        sqlite_udf_module,
        sqlite_ext_module])

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
    scripts = ['pwiz.py', 'playhouse/pskel'],
    **setup_kwargs
)
