from dotenv import load_dotenv, dotenv_values

# load env
load_dotenv()

# create and expose ENV_VALUES
ENV_VALUES = dotenv_values('.env')

# validation for existence of .env file
if len(list(ENV_VALUES.keys())) == 0:
    raise FileNotFoundError('.env file is missing from within your local project. You can create one by running "cp .env.example .env"')
