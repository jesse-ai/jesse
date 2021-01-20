import peewee

import jesse.helpers as jh

if not jh.is_unit_testing():
    # connect to the database
    db = peewee.PostgresqlDatabase(jh.get_config('env.databases.postgres_name'),
                                   user=jh.get_config('env.databases.postgres_username'),
                                   password=jh.get_config('env.databases.postgres_password'),
                                   host=str(jh.get_config('env.databases.postgres_host')),
                                   port=int(jh.get_config('env.databases.postgres_port')))


    def close_connection():
        db.close()


    # connect
    db.connect()
else:
    db = None
