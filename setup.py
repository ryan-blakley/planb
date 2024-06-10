from glob import glob
from setuptools import find_packages, setup

requires = [
    'distro',
    'file-magic',
    'jinja2',
    'pyparted',
    'pyudev',
    'rpm'
]

data_files = [
    ('share/planb', glob('data-files/*')),
    ('share/man/man8', glob('doc/*.8')),
    ('share/man/man5', glob('doc/*.5')),
    ('/etc/planb', glob('cfg/pbr.conf')),
    ('/etc/cron.d', ['cfg/pbr']),
    ('/var/lib/pbr', [])
]

develop = [
    "flake8"
]

entry_points = {
    'console_scripts': [
        'pbr = planb:main'
    ]
}

if __name__ == "__main__":
    setup(
        name='planb',
        description='Backup and restore utility.',
        author='Ryan Blakley',
        author_email='rblakley@redhat.com',
        maintainer='Ryan Blakley',
        maintainer_email='rblakley@redhat.com',
        version='0.7',
        packages=find_packages(),
        entry_points=entry_points,
        data_files=data_files,
        include_package_data=True,
        install_requires=requires,
        extras_require={
            "develop": requires + develop
        },
        classifiers=[
            'Development Status :: 2 - Pre-Alpha',
            'Intended Audience :: System Administrators',
            'Natural Language :: English',
            'License:: OSI Approved:: GNU General Public License v3',
            'Operating System :: POSIX :: Linux',
            'Programming Language :: Python',
            'Programming Language :: Python :: 3.6',
            'Programming Language :: Python :: 3.8',
            'Programming Language :: Python :: 3.9',
            'Programming Language :: Python :: 3.11',
        ],
    )
