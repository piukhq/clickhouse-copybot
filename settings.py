from pydantic import BaseSettings


class Settings(BaseSettings):
    clickhouse_host: str = "http://127.0.0.1:8123/"
    amqp_url: str = "amqp://guest:guest@localhost:5672/"
    datetime_format: str = "%Y-%m-%d %H:%M:%S.%f"
    debug: bool = False
    database_name: str = "bink"
    table_name: str = "events"


settings = Settings()
