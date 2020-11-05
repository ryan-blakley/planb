from distutils.core import setup
from glob import glob

setup(
    name='pbr',
    description='Backup and restore utility.',
    author='Ryan Blakley',
    author_email='rblakley@redhat.com',
    maintainer='Ryan Blakley',
    maintainer_email='rblakley@redhat.com',
    version='0.3',
    package_dir={'planb': 'src/modules'},
    packages=['planb'],
    scripts=glob('src/scripts/*'),
    data_files=[('share/planb', glob('src/data-files/*')), ('share/man/man8', glob('src/doc/*.8')),
                ('share/man/man5', glob('src/doc/*.5')),
                ('/etc/planb', glob('src/cfg/*.conf'))]
)
