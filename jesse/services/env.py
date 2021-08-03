from dotenv import load_dotenv, dotenv_values
import jesse.helpers as jh


# load env
load_dotenv()

# create and expose ENV_VALUES
ENV_VALUES = dotenv_values('.env')

if jh.is_unit_testing():
    ENV_VALUES['POSTGRES_HOST'] = '127.0.0.1'
    ENV_VALUES['POSTGRES_NAME'] = 'jesse_db'
    ENV_VALUES['POSTGRES_PORT'] = '5432'
    ENV_VALUES['POSTGRES_USERNAME'] = 'jesse_user'
    ENV_VALUES['POSTGRES_PASSWORD'] = 'password'
    ENV_VALUES['REDIS_HOST'] = 'localhost'
    ENV_VALUES['REDIS_PORT'] = '6379'
    ENV_VALUES['REDIS_PASSWORD'] = ''

# validation for existence of .env file
if len(list(ENV_VALUES.keys())) == 0:
    raise FileNotFoundError('.env file is missing from within your local project. You can create one by running "cp .env.example .env"')
