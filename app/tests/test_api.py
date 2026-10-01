import os

os.environ["AUTH_DATABASE_URL"] = "sqlite://"
os.environ["BANK_DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-with-more-than-32-characters"

from fastapi.testclient import TestClient

from auth_service.main import app as auth_app
from bank_service.main import app as bank_app


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["token"]


def test_login_me_and_invalid_credentials():
    with TestClient(auth_app) as client:
        token = login(client, "cliente1@bancomnm.xyz", "Cliente123!")
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["rol"] == "cliente"
        assert me.json()["id_cuenta"] == 1
        assert client.post(
            "/api/auth/login", json={"email": "cliente1@bancomnm.xyz", "password": "wrong"}
        ).status_code == 401


def test_client_dashboard_filters_and_role_boundaries():
    with TestClient(auth_app) as auth, TestClient(bank_app) as bank:
        client_token = login(auth, "cliente1@bancomnm.xyz", "Cliente123!")
        analyst_token = login(auth, "analista1@bancomnm.xyz", "Analista123!")
        client_headers = {"Authorization": f"Bearer {client_token}"}
        analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

        summary = bank.get("/api/cliente/resumen", headers=client_headers)
        assert summary.status_code == 200
        assert summary.json()["ingresos"] > 0
        assert bank.get("/api/global/resumen", headers=client_headers).status_code == 403
        assert bank.get("/api/cliente/resumen", headers=analyst_headers).status_code == 403

        transactions = bank.get(
            "/api/cliente/transacciones?tipo=debito&pagina=1&por_pagina=2",
            headers=client_headers,
        )
        assert transactions.status_code == 200
        assert transactions.json()["total"] > 0
        assert len(transactions.json()["items"]) == 2
        assert all(item["tipo"] == "debito" for item in transactions.json()["items"])
        invalid_filters = bank.get(
            "/api/cliente/transacciones?tipo=otro",
            headers=client_headers,
        )
        assert invalid_filters.status_code == 400

        alerts = bank.get("/api/global/alertas", headers=analyst_headers)
        assert alerts.status_code == 200
        assert alerts.json()["total"] > 0
        assert bank.get("/api/global/resumen").status_code == 401


def test_client_can_transfer_between_users_atomically():
    with TestClient(auth_app) as auth, TestClient(bank_app) as bank:
        sender_token = login(auth, "cliente1@bancomnm.xyz", "Cliente123!")
        recipient_token = login(auth, "cliente2@bancomnm.xyz", "Cliente123!")
        sender_headers = {"Authorization": f"Bearer {sender_token}"}
        recipient_headers = {"Authorization": f"Bearer {recipient_token}"}

        recipients = bank.get("/api/cliente/destinatarios", headers=sender_headers)
        assert recipients.status_code == 200
        assert {item["usuario"] for item in recipients.json()} == {
            "cliente2",
            "cliente3",
            "cliente4",
            "cliente5",
        }

        sender_before = bank.get("/api/cliente/resumen", headers=sender_headers).json()["saldo"]
        recipient_before = bank.get("/api/cliente/resumen", headers=recipient_headers).json()["saldo"]
        transfer = bank.post(
            "/api/cliente/transferencias",
            headers=sender_headers,
            json={"destinatario": "cliente2", "monto": "125.50"},
        )
        assert transfer.status_code == 200
        assert transfer.json()["estado"] == "completada"
        assert transfer.json()["saldo_restante"] == sender_before - 125.5

        sender_after = bank.get("/api/cliente/resumen", headers=sender_headers).json()["saldo"]
        recipient_after = bank.get("/api/cliente/resumen", headers=recipient_headers).json()["saldo"]
        assert sender_after == sender_before - 125.5
        assert recipient_after == recipient_before + 125.5
        sender_ledger = bank.get(
            "/api/cliente/transacciones?tipo=debito&por_pagina=1",
            headers=sender_headers,
        ).json()["items"][0]
        recipient_ledger = bank.get(
            "/api/cliente/transacciones?tipo=credito&por_pagina=1",
            headers=recipient_headers,
        ).json()["items"][0]
        assert sender_ledger["operacion"] == "Transferencia enviada a cliente2"
        assert recipient_ledger["operacion"] == "Transferencia recibida de cliente1"
        assert sender_ledger["monto"] == recipient_ledger["monto"] == 125.5


def test_transfers_reject_invalid_targets_insufficient_funds_and_analysts():
    with TestClient(auth_app) as auth, TestClient(bank_app) as bank:
        client_token = login(auth, "cliente1@bancomnm.xyz", "Cliente123!")
        analyst_token = login(auth, "analista1@bancomnm.xyz", "Analista123!")
        client_headers = {"Authorization": f"Bearer {client_token}"}
        analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

        assert bank.post(
            "/api/cliente/transferencias",
            headers=client_headers,
            json={"destinatario": "cliente1", "monto": "1.00"},
        ).status_code == 400
        assert bank.post(
            "/api/cliente/transferencias",
            headers=client_headers,
            json={"destinatario": "desconocido", "monto": "1.00"},
        ).status_code == 404
        assert bank.post(
            "/api/cliente/transferencias",
            headers=client_headers,
            json={"destinatario": "cliente2", "monto": "999999999.00"},
        ).status_code == 400
        assert bank.get("/api/cliente/destinatarios", headers=analyst_headers).status_code == 403
        assert bank.post(
            "/api/cliente/transferencias",
            headers=analyst_headers,
            json={"destinatario": "cliente1", "monto": "1.00"},
        ).status_code == 403