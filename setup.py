from setuptools import setup, find_packages

# also change in version.py
VERSION = '0.30.6'
DESCRIPTION = "A trading framework for cryptocurrencies"

REQUIRED_PACKAGES = [
    'arrow',
    'blinker',
    'click',
    'matplotlib',
    'mplfinance',
    'newtulipy',
    'numpy',
    'numpy_groupies',
    'pandas',
    'peewee',
    'psycopg2-binary',
    'pydash',
    'pytest',
    'PyWavelets',
    'quantstats',
    'requests',
    'scipy',
    'statsmodels',
    'TA-Lib',
    'tabulate',
    'timeloop',
    'websocket-client',
    'simplejson',
    'aioredis',
    'redis',
    'fastapi',
    'uvicorn',
    'websockets',
    'python-dotenv',
    'aiofiles'
]

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name='jesse',
    version=VERSION,
    author="Saleh Mir",
    author_email="saleh@jesse.trade",
    packages=find_packages(),
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://jesse.trade",
    project_urls={
        'Documentation': 'https://docs.jesse.trade',
        'Say Thanks!': 'https://jesse.trade/discord',
        'Source': 'https://github.com/jesse-ai/jesse',
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
    python_requires='>=3.8',
    include_package_data=True,
)
