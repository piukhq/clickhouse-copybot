```python
requests.post(settings.clickhouse_host, params={"query": "DROP DATABASE bink;"}).text
```

```python
msg_payload = {'event_type': 'event.user.created.api', 'origin': 'channel', 'channel': 'bink', 'event_date_time': '2022-03-01 17:40:53', 'external_user_ref': '239825255', 'internal_user_ref': 933, 'email': 'cpressland@bink.com'}
```

```python
def _test_insert_record() -> None:
    msg_source = "clickhouse_testing"
    msg_payload = {
        "event_type": "event.user.created.api",
        "origin": "channel",
        "channel": "bink",
        "event_date_time": f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "external_user_ref": str(randint(100000000, 999999999)),
        "internal_user_ref": randint(1, 999),
        "email": "cpressland@bink.com",
    }
    message_type = message_routing[msg_source]["class"]
    destination_database = message_routing[msg_source]["database"]
    msg = message_type(**msg_payload)
    sql, msg_params = msg.insert(destination_database)
    requests.post(settings.clickhouse_host, params={"query": sql, "database": "bink", **msg_params}).raise_for_status()
```
