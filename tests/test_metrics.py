import re


def _value(text, metric, **labels):
    """Read one sample from Prometheus text output (0 if absent)."""
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    for line in text.splitlines():
        m = re.match(rf"{metric}\{{(.*)\}} (\S+)$", line)
        if m and ",".join(sorted(m.group(1).split(","))) == label_str:
            return float(m.group(2))
    return 0.0


def test_metrics_endpoint_format(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in r.text
    assert "http_request_duration_seconds" in r.text


def test_request_count_increments(client):
    labels = {"method": "GET", "path": "/health", "status": "200"}
    before = _value(client.get("/metrics").text, "http_requests_total", **labels)
    client.get("/health")
    client.get("/health")
    after = _value(client.get("/metrics").text, "http_requests_total", **labels)
    assert after - before == 2


def test_latency_is_recorded_per_route_template(client):
    client.get("/weather", params={"city": "id:50"})
    text = client.get("/metrics").text
    count = _value(text, "http_request_duration_seconds_count", method="GET", path="/weather")
    assert count >= 1
    # Query strings never become label values
    assert "id:50" not in text


def test_unknown_paths_share_one_label(client):
    client.get("/no-such-page-123")
    text = client.get("/metrics").text
    assert "no-such-page-123" not in text
    assert _value(text, "http_requests_total", method="GET", path="unmatched", status="404") >= 1
