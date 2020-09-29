from distutils.core import setup
from glob import glob

setup(
    name='pbr',
    description='Backup and restore utility.',
    author='Ryan Blakley',
    author_email='rblakley@redhat.com',
    maintainer='Ryan Blakley',
    maintainer_email='rblakley@redhat.com',
    version='0.2',
    package_dir={'planb': 'src/modules'},
    packages=['planb'],
    scripts=glob('src/scripts/*'),
    data_files=[('share/planb', glob('src/data-files/*')), ('/etc/planb', glob('src/cfg/*'))],
)
