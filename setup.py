from setuptools import setup, find_packages

VERSION = '0.0.12'
DESCRIPTION = "A trading framework for cryptocurrencies"
REQUIRED_PACKAGES = [
    'psycopg2-binary',
    'pytest',
    'Click',
    'arrow',
    'requests',
    'peewee',
    'pydash',
    'numpy',
    'pandas',
    'tabulate',
    'timeloop',
    'websocket-client',
    'TA-Lib',
    'matplotlib',
    'redis',
    'empyrical',
    'blinker',
]

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='jesse',
    version=VERSION,
    author="Saleh Mirnezami",
    author_email="mirnezami.saleh@gmail.com",
    packages=find_packages(),
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://jesse-ai.com",
    project_urls={
        'Documentation': 'https://docs.jesse-ai.com',
        'Say Thanks!': 'http://twitter.com/jesse_ai_com',
        'Source': 'http://github.com/jesse-ai/jesse',
        'Tracker': 'https://github.com/jesse-ai/jesse/issues',
    },
    install_requires=REQUIRED_PACKAGES,
    entry_points='''
        [console_scripts]
        jesse=jesse.__init__:cli
    ''',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    include_package_data=True,
)
