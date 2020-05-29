import peewee

from jesse.config import config
import jesse.helpers as jh

if not jh.is_unit_testing():
    # connect to the database
    if config['env']['databases']['database'] is 'postgres':
        db = peewee.PostgresqlDatabase(config['env']['databases']['postgres_name'],
                                   user=config['env']['databases']['postgres_username'],
                                   password=config['env']['databases']['postgres_password'],
                                   host=str(config['env']['databases']['postgres_host']),
                                   port=int(config['env']['databases']['postgres_port']))
    elif config['env']['databases']['database'] is 'sqlite':
        db = peewee.SqliteDatabase(config['env']['databases']['sqlite_dbfilename'])


    def close_connection():
        db.close()


    # connect
    db.connect()
else:
    db = None
