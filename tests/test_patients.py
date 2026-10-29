"""Integration tests for the REST API layer."""


def _valid_payload(**overrides):
    base = dict(
        first_name="Jane",
        last_name="Doe",
        date_of_birth="03/15/1985",
        sex="Female",
        phone_number="512-555-0142",
        address_line_1="100 Congress Ave",
        city="Austin",
        state="TX",
        zip_code="78701",
    )
    base.update(overrides)
    return base


def test_create_and_fetch(client):
    r = client.post("/patients", json=_valid_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["error"] is None
    pid = body["data"]["patient_id"]
    assert body["data"]["phone_number"] == "5125550142"  # normalized

    r2 = client.get(f"/patients/{pid}")
    assert r2.status_code == 200
    assert r2.json()["data"]["first_name"] == "Jane"


def test_envelope_shape(client):
    r = client.get("/patients")
    body = r.json()
    assert "data" in body and "error" in body
    assert isinstance(body["data"], list)


def test_future_dob_rejected(client):
    r = client.post("/patients", json=_valid_payload(date_of_birth="01/01/2999"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == 422


def test_short_phone_rejected(client):
    r = client.post("/patients", json=_valid_payload(phone_number="123"))
    assert r.status_code == 422


def test_bad_state_rejected(client):
    r = client.post("/patients", json=_valid_payload(state="ZZ"))
    assert r.status_code == 422


def test_missing_required_field(client):
    payload = _valid_payload()
    del payload["last_name"]
    r = client.post("/patients", json=payload)
    assert r.status_code == 422


def test_get_missing_returns_404(client):
    r = client.get("/patients/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.json()["data"] is None


def test_partial_update(client):
    pid = client.post("/patients", json=_valid_payload(phone_number="2015550111")).json()["data"]["patient_id"]
    r = client.put(f"/patients/{pid}", json={"city": "Dallas"})
    assert r.status_code == 200
    assert r.json()["data"]["city"] == "Dallas"
    assert r.json()["data"]["first_name"] == "Jane"  # unchanged


def test_soft_delete_hides_record(client):
    pid = client.post("/patients", json=_valid_payload(phone_number="2025550133")).json()["data"]["patient_id"]
    assert client.delete(f"/patients/{pid}").status_code == 200
    assert client.get(f"/patients/{pid}").status_code == 404
    phones = [p["phone_number"] for p in client.get("/patients").json()["data"]]
    assert "2025550133" not in phones


def test_query_filters(client):
    client.post("/patients", json=_valid_payload(last_name="Zimmerman", phone_number="7135550155"))
    r = client.get("/patients", params={"last_name": "zimmerman"})
    assert r.status_code == 200
    assert any(p["last_name"] == "Zimmerman" for p in r.json()["data"])
    r2 = client.get("/patients", params={"phone_number": "(713) 555-0155"})
    assert len(r2.json()["data"]) >= 1


def test_vapi_register_tool_roundtrip(client):
    payload = {
        "message": {
            "type": "tool-calls",
            "toolCalls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "register_patient",
                        "arguments": _valid_payload(phone_number="4085550188"),
                    },
                }
            ],
        }
    }
    r = client.post("/vapi/webhook", json=payload)
    assert r.status_code == 200
    result = r.json()["results"][0]["result"]
    assert "SUCCESS" in result


def test_vapi_register_tool_validation_error(client):
    payload = {
        "message": {
            "type": "tool-calls",
            "toolCalls": [
                {
                    "id": "call_2",
                    "function": {
                        "name": "register_patient",
                        "arguments": _valid_payload(date_of_birth="01/01/2999"),
                    },
                }
            ],
        }
    }
    r = client.post("/vapi/webhook", json=payload)
    assert "VALIDATION_ERROR" in r.json()["results"][0]["result"]
