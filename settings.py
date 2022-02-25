from pydantic import BaseSettings


class Settings(BaseSettings):
    clickhouse_host: str = "http://127.0.0.1:8123/"
    amqp_url: str = "amqp://guest:guest@localhost:5672/"
    datetime_format: str = "%Y-%m-%d %H:%M:%S"
    debug: bool = False


settings = Settings()
