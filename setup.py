import os
import sys
import warnings
from distutils.command.build_ext import build_ext
from distutils.core import setup
from distutils.extension import Extension
from distutils.version import StrictVersion

f = open(os.path.join(os.path.dirname(__file__), 'README.rst'))
readme = f.read()
f.close()

cython_min = '0.22.1'
try:
    from Cython.Distutils import build_ext
    from Cython import __version__ as cython_ver
except ImportError:
    cython_installed = False
else:
    cython_installed = StrictVersion(cython_ver) >= StrictVersion(cython_min)

extensions = (
    ('playhouse._speedups', ('playhouse/_speedups.pyx',
                             'playhouse/_speedups.c')),
    ('playhouse._sqlite_udf', ('playhouse/_sqlite_udf.pyx',
                               'playhouse/_sqlite_udf.c')),
    ('playhouse._sqlite_ext', ('playhouse/_sqlite_ext.pyx',
                               'playhouse/_sqlite_ext.c')),
)

ext_modules = [Extension(module, [pyx if cython_installed else c])
               for module, (pyx, c) in extensions]

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
    cmdclass={'build_ext': build_ext},
    ext_modules=ext_modules,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
    scripts = ['pwiz.py'],
)
