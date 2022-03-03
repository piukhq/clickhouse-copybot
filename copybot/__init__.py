import json
import logging
from ast import Bytes
from dataclasses import dataclass
from datetime import datetime
from random import randint

import pika
import requests
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties
from pythonjsonlogger import jsonlogger

from settings import settings

logger = logging.getLogger()
logHandler = logging.StreamHandler()
logFmt = jsonlogger.JsonFormatter(timestamp=True)
logHandler.setFormatter(logFmt)
logger.addHandler(logHandler)

# maps python types to clickhouse column types
clickhouse_key_types = {
    int: "Int64",
    float: "Float64",
    str: "String",
    bool: "UInt8",
    datetime: "DateTime64(6, 'UTC')",
}


# functions to convert values off the queue into python objects.
deserializers = {
    datetime: lambda s: datetime.strptime(s, settings.datetime_format),
}

# functions to convert python values into clickhouse formats.
serializers = {
    datetime: lambda dt: dt.strftime(settings.datetime_format),
    bool: lambda b: 1 if b else 0,
}


@dataclass(frozen=True)
class Message:
    def insert(self, table: str) -> tuple[str, dict]:
        """Returns an INSERT query for this message."""
        field_types = {}
        params = {}
        for key, key_type in self.__annotations__.items():
            attr = getattr(self, key)
            if not isinstance(attr, key_type):
                value = deserializers.get(key_type, key_type)(attr)
            else:
                value = attr
            field_types[key] = clickhouse_key_types[key_type]
            if key_type in serializers:
                value = serializers[key_type](value)
            params[f"param_{key}"] = value
        placeholders = ", ".join(f"{{{key}:{field_type}}}" for key, field_type in field_types.items())
        sql = f"INSERT INTO {table} VALUES({placeholders})"
        return sql, params

    @classmethod
    def create(cls, table: str, order_by: str) -> str:
        """Returns a CREATE TABLE query for a given table"""
        field_types = {}
        for key, key_type in cls.__annotations__.items():
            field_types[key] = clickhouse_key_types[key_type]
        placeholders = ", ".join(f"`{key}` {field_type}" for key, field_type in field_types.items())
        return f"CREATE TABLE IF NOT EXISTS {table} ({placeholders}) ENGINE = MergeTree() ORDER BY {order_by}"


@dataclass(frozen=True)
class HermesMessage(Message):
    event_type: str
    origin: str
    channel: str
    event_date_time: datetime
    external_user_ref: str
    internal_user_ref: int
    email: str


message_routing = {
    "clickhouse_testing": {"class": HermesMessage, "database": "bink.hermes"},
    "clickhouse_hermes": {"class": HermesMessage, "database": "bink.hermes"},
}


def migrate() -> None:
    try:
        logging.warning(msg="Creating Bink Database")
        requests.post(
            settings.clickhouse_host,
            params={"query": "CREATE DATABASE IF NOT EXISTS bink"},
        ).raise_for_status()
    except Exception as ex:
        logging.warning(msg="Creating Bink Database Failed", exc_info=ex)
        exit(1)
    try:
        hermes_table = HermesMessage.create(table="bink.hermes", order_by="event_date_time")
        logging.warning(msg="Creating Hermes Table", extra={})
        requests.post(settings.clickhouse_host, params={"query": hermes_table}).raise_for_status()
    except Exception as ex:
        logging.warning(msg="Failed to Migrate Hermes Tables", exc_info=ex)
        exit(1)


def dead_letter(msg: dict) -> None:
    with pika.BlockingConnection(pika.URLParameters(settings.amqp_url)) as connection:
        channel = connection.channel()
        channel.queue_declare(queue="clickhouse_deadletter", durable=True)
        channel.basic_publish(exchange="", routing_key="clickhouse_deadletter", body=json.dumps(msg))


def process_message(
    ch: BlockingChannel,
    method: Basic.Deliver,
    properties: BasicProperties,
    message: Bytes,
) -> None:
    """
    Process Message from RabbitMQ Queue and Push to ClickHouse
    """
    raw_msg = json.loads(message.decode())
    try:
        message_type = message_routing[method.routing_key]["class"]
        destination_database = message_routing[method.routing_key]["database"]
    except KeyError as ex:
        raise KeyError(f"Queue {method.routing_key} not found in message_routing dict.") from ex
    msg = message_type(**raw_msg)
    sql, msg_params = msg.insert(destination_database)
    retries = 3
    if settings.debug:
        logging_extras = {
            "sql": sql,
            "params": msg_params,
            "database": destination_database,
        }
    else:
        logging_extras = {}
    while True:
        try:
            logging.warning(msg="Processing Message", extra=logging_extras)
            requests.post(settings.clickhouse_host, params={"query": sql, **msg_params}).raise_for_status()
            ch.basic_ack(delivery_tag=method.delivery_tag)
            break
        except Exception as ex:
            retries -= 1
            if retries < 1:
                logging.warning(msg="Dead Letter Event", extra=logging_extras, exc_info=ex)
                ch.basic_ack(delivery_tag=method.delivery_tag)
                break
            else:
                logging.warning(msg="Retry Message", extra=logging_extras, exc_info=ex)
                continue


def rabbitmq_message_put(count: int, queue: str) -> None:
    """
    Puts n messages onto RabbitMQ queue for later consumption
    """
    with pika.BlockingConnection(pika.URLParameters(settings.amqp_url)) as connection:
        channel = connection.channel()
        channel.queue_declare(queue=queue)
        logging.warning(
            msg="Pushing Messages to Message Bus",
            extra={"count": count, "queue": queue},
        )
        for _ in range(count):
            msg_payload = {
                "event_type": "event.user.created.api",
                "origin": "channel",
                "channel": "bink",
                "event_date_time": f"{datetime.now().strftime(settings.datetime_format)}",
                "external_user_ref": str(randint(100000000, 999999999)),
                "internal_user_ref": randint(1, 999),
                "email": "cpressland@bink.com",
            }
            logging.warning(msg="Pushing Message", extra={"payload": msg_payload, "queue": queue})
            channel.basic_publish(
                exchange="",
                routing_key=queue,
                body=json.dumps(msg_payload),
            )


def rabbitmq_message_get(queue: str) -> None:
    """
    Gets Messages from RabbitMQ Forever
    """
    with pika.BlockingConnection(pika.URLParameters(settings.amqp_url)) as connection:
        channel = connection.channel()
        channel.basic_consume(
            queue=queue,
            on_message_callback=process_message,
            auto_ack=False,
        )
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
