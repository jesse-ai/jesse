import peewee

import jesse.helpers as jh
from jesse.config import config

if not jh.is_unit_testing():
    # connect to the database
    db = peewee.PostgresqlDatabase(config['env']['databases']['postgres_name'],
                                   user=config['env']['databases']['postgres_username'],
                                   password=config['env']['databases']['postgres_password'],
                                   host=str(config['env']['databases']['postgres_host']),
                                   port=int(config['env']['databases']['postgres_port']))


    def close_connection():
        db.close()


    # connect
    db.connect()
else:
    db = None
