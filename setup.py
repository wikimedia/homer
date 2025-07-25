"""Package configuration."""

from setuptools import find_packages, setup


with open('README.rst', 'r') as readme:
    LONG_DESCRIPTION = readme.read()


INSTALL_REQUIRES = [
    'Jinja2>=2.10',
    'junos-eznc>=2.2.1,<3',
    'paramiko',
    'pynetbox',
    'pyyaml>=3.11',
    'aerleon',
    'python-dateutil>=2.8.1',
    'pytz>=2021.1'
]

# Extra dependencies
EXTRAS_REQUIRE = {
    # Test dependencies
    'tests': [
        'bandit>=1.1.0',
        'flake8>=3.2.1',
        'flake8-import-order>=0.18.1',
        'mypy>=0.470',
        'pytest-cov>=1.8.0',
        'pytest-xdist>=1.15.0',
        'pytest>=3.3.0',
        'requests-mock',
        'sphinx_rtd_theme>=0.1.6',
        'sphinx-argparse>=0.1.15',
        "sphinx-autodoc-typehints>=1.9.0",
        'Sphinx>=1.4.9',
        'types-PyYAML',
        'types-requests',
    ],
    'prospector': [
        'prospector[with_everything]==1.16.1',  # Pinned
        'pytest>=3.3.0',
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
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
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
    package_data={'homer': ['py.typed', 'graphql/*.gql']},
    packages=find_packages(exclude=['*.tests', '*.tests.*', 'homer_plugins']),
    platforms=['GNU/Linux'],
    python_requires='>=3.9',
    setup_requires=SETUP_REQUIRES,
    use_scm_version=True,
    url='https://gerrit.wikimedia.org/r/plugins/gitiles/operations/software/homer',
    zip_safe=False,
)
