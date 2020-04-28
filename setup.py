"""Package configuration."""

from setuptools import find_packages, setup


with open('README.rst', 'r') as readme:
    LONG_DESCRIPTION = readme.read()


INSTALL_REQUIRES = [
    'Jinja2>=2.10',
    'junos-eznc>=2.2.1,<3',
    'pynetbox>=4.0.6',
    'pyyaml>=3.11',
]

# Extra dependencies
EXTRAS_REQUIRE = {
    # Test dependencies
    'tests': [
        'bandit>=1.1.0',
        'flake8>=3.2.1',
        'flake8-import-order>=0.18.1',
        'mypy>=0.470',
        'prospector[with_everything]>=0.12.4',
        'pytest-cov>=1.8.0',
        'pytest-xdist>=1.15.0',
        'pytest>=3.3.0',
        'sphinx_rtd_theme>=0.1.6',
        'sphinx-argparse>=0.1.15',
        'Sphinx>=1.4.9',
    ],
}

SETUP_REQUIRES = [
    'pytest-runner>=2.7.1',
    'setuptools_scm>=1.15.0',
]

setup(
    author='Riccardo Coccioli',
    author_email='rcoccioli@wikimedia.org',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX :: BSD',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Networking',
    ],
    description='Configuration manager for network devices',
    entry_points={
        'console_scripts': [
            'homer = homer.cli:main',
        ],
    },
    extras_require=EXTRAS_REQUIRE,
    install_requires=INSTALL_REQUIRES,
    keywords=['network', 'switch', 'router', 'configuration', 'deploy'],
    license='GPLv3+',
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/x-rst',
    name='homer',  # Must be the same used for __version__ in __init__.py
    packages=find_packages(exclude=['*.tests', '*.tests.*']),
    platforms=['GNU/Linux'],
    setup_requires=SETUP_REQUIRES,
    use_scm_version=True,
    url='https://gerrit.wikimedia.org/r/plugins/gitiles/operations/software/homer',
    zip_safe=False,
)
