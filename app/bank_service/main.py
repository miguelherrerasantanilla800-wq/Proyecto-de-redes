import os
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from bank_service.database import Base, SessionLocal, engine, get_db
from bank_service.models import Account, Transaction
from common.errors import add_bad_request_validation
from common.security import get_current_user, require_role


ALERT_THRESHOLD = Decimal(os.getenv("ALERT_THRESHOLD", "100000"))


class TransferRequest(BaseModel):
    destinatario: str = Field(min_length=1, max_length=80)
    monto: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)


def ensure_account_username_column() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("cuentas")}
    if "username" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE cuentas ADD COLUMN username VARCHAR(80)"))
            connection.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS uq_cuentas_username ON cuentas (username)")
            )


def seed_account_usernames() -> None:
    if os.getenv("SEED_DEMO_DATA", "true").lower() != "true":
        return
    with SessionLocal() as session:
        for account_id in range(1, 6):
            account = session.get(Account, account_id)
            if account is not None and account.username is None:
                account.username = f"cliente{account_id}"
        session.commit()


def seed_transactions() -> None:
    if os.getenv("SEED_DEMO_DATA", "true").lower() != "true":
        return
    with SessionLocal() as session:
        if session.scalar(select(func.count()).select_from(Transaction)):
            return
        for account_id in range(1, 6):
            account = session.get(Account, account_id)
            if account is None:
                session.add(
                    Account(
                        id=account_id,
                        opened_on=date(1995, account_id, 1),
                        username=f"cliente{account_id}",
                    )
                )
            elif account.username is None:
                account.username = f"cliente{account_id}"
            balance = Decimal("250000")
            for month in range(1, 7):
                credit = Decimal("45000") + Decimal(account_id * 1300)
                debit = Decimal("18000") + Decimal(month * 800)
                for day, kind, amount, operation, category in (
                    (1, "credito", credit, "Abono de nómina", "salario"),
                    (8, "debito", debit, "Pago con tarjeta", "alimentacion"),
                ):
                    balance = balance + amount if kind == "credito" else balance - amount
                    session.add(
                        Transaction(
                            account_id=account_id,
                            date=date(2026, month, day),
                            type=kind,
                            operation=operation,
                            amount=amount,
                            balance_after=balance,
                            category=category,
                        )
                    )
            balance -= Decimal("125000")
            session.add(
                Transaction(
                    account_id=account_id,
                    date=date(2026, 6, 20),
                    type="debito",
                    operation="Transferencia extraordinaria",
                    amount=Decimal("125000"),
                    balance_after=balance,
                    category="transferencias",
                )
            )
        session.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    ensure_account_username_column()
    seed_account_usernames()
    seed_transactions()
    yield


app = FastAPI(title="Banco MNM BANCO", version="1.0.0", lifespan=lifespan)
add_bad_request_validation(app)


def money(value: Decimal | int | None) -> float:
    return float(value or 0)


@app.get("/api/cliente/resumen")
def client_summary(
    current_user: dict = Depends(require_role("cliente")), db: Session = Depends(get_db)
):
    account_id = current_user["account_id"]
    if account_id is None:
        raise HTTPException(status_code=403, detail="La cuenta no está asociada al usuario")
    latest_balance = db.scalar(
        select(Transaction.balance_after)
        .where(Transaction.account_id == account_id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(1)
    )
    totals = db.execute(
        select(Transaction.type, func.sum(Transaction.amount))
        .where(Transaction.account_id == account_id)
        .group_by(Transaction.type)
    ).all()
    sums = {kind: amount for kind, amount in totals}
    return {
        "saldo": money(latest_balance),
        "ingresos": money(sums.get("credito")),
        "egresos": money(sums.get("debito")),
    }


@app.get("/api/cliente/mensual")
def client_monthly(
    current_user: dict = Depends(require_role("cliente")), db: Session = Depends(get_db)
):
    month = func.to_char(Transaction.date, "YYYY-MM")
    rows = db.execute(
        select(month, Transaction.type, func.sum(Transaction.amount))
        .where(Transaction.account_id == current_user["account_id"])
        .group_by(month, Transaction.type)
        .order_by(month)
    ).all()
    results: dict[str, dict] = {}
    for month_name, kind, amount in rows:
        item = results.setdefault(month_name, {"mes": month_name, "ingresos": 0.0, "egresos": 0.0})
        item["ingresos" if kind == "credito" else "egresos"] = money(amount)
    return list(results.values())


@app.get("/api/cliente/categorias")
def client_categories(
    current_user: dict = Depends(require_role("cliente")), db: Session = Depends(get_db)
):
    rows = db.execute(
        select(Transaction.category, func.sum(Transaction.amount).label("amount"))
        .where(
            Transaction.account_id == current_user["account_id"],
            Transaction.type == "debito",
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
    ).all()
    return [{"categoria": category, "monto": money(amount)} for category, amount in rows]


@app.get("/api/cliente/transacciones")
def client_transactions(
    desde: date | None = None,
    hasta: date | None = None,
    tipo: str | None = Query(default=None, pattern="^(credito|debito)$"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(require_role("cliente")),
    db: Session = Depends(get_db),
):
    if desde and hasta and desde > hasta:
        raise HTTPException(status_code=400, detail="desde no puede ser posterior a hasta")
    filters = [Transaction.account_id == current_user["account_id"]]
    if desde:
        filters.append(Transaction.date >= desde)
    if hasta:
        filters.append(Transaction.date <= hasta)
    if tipo:
        filters.append(Transaction.type == tipo)
    total = db.scalar(select(func.count()).select_from(Transaction).where(*filters)) or 0
    rows = db.scalars(
        select(Transaction)
        .where(*filters)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    return {
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total": total,
        "items": [transaction_json(row) for row in rows],
    }


@app.get("/api/cliente/destinatarios")
def transfer_recipients(
    current_user: dict = Depends(require_role("cliente")), db: Session = Depends(get_db)
):
    accounts = db.scalars(
        select(Account)
        .where(
            Account.username.is_not(None),
            Account.id != current_user["account_id"],
        )
        .order_by(Account.username)
    ).all()
    return [{"usuario": account.username} for account in accounts]


@app.post("/api/cliente/transferencias")
def transfer_money(
    payload: TransferRequest,
    current_user: dict = Depends(require_role("cliente")),
    db: Session = Depends(get_db),
):
    sender_id = current_user["account_id"]
    if sender_id is None:
        raise HTTPException(status_code=403, detail="La cuenta no está asociada al usuario")

    recipient_name = payload.destinatario.strip().lower()
    recipient = db.scalar(
        select(Account).where(func.lower(Account.username) == recipient_name)
    )
    if recipient is None:
        raise HTTPException(status_code=404, detail="No existe ese usuario destinatario")
    if recipient.id == sender_id:
        raise HTTPException(status_code=400, detail="No puedes transferir a tu propia cuenta")

    locked_accounts = db.scalars(
        select(Account)
        .where(Account.id.in_(sorted((sender_id, recipient.id))))
        .order_by(Account.id)
        .with_for_update()
    ).all()
    accounts = {account.id: account for account in locked_accounts}
    if sender_id not in accounts or recipient.id not in accounts:
        raise HTTPException(status_code=404, detail="No se encontró una de las cuentas")

    sender_balance = db.scalar(
        select(Transaction.balance_after)
        .where(Transaction.account_id == sender_id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(1)
    ) or Decimal("0")
    recipient_balance = db.scalar(
        select(Transaction.balance_after)
        .where(Transaction.account_id == recipient.id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(1)
    ) or Decimal("0")
    if sender_balance < payload.monto:
        raise HTTPException(status_code=400, detail="Saldo insuficiente para realizar la transferencia")

    transfer_date = date.today()
    db.add_all(
        [
            Transaction(
                account_id=sender_id,
                date=transfer_date,
                type="debito",
                operation=f"Transferencia enviada a {recipient.username}",
                amount=payload.monto,
                balance_after=sender_balance - payload.monto,
                category="transferencias",
            ),
            Transaction(
                account_id=recipient.id,
                date=transfer_date,
                type="credito",
                operation=f"Transferencia recibida de {accounts[sender_id].username}",
                amount=payload.monto,
                balance_after=recipient_balance + payload.monto,
                category="transferencias",
            ),
        ]
    )
    db.commit()
    return {
        "estado": "completada",
        "destinatario": recipient.username,
        "monto": money(payload.monto),
        "saldo_restante": money(sender_balance - payload.monto),
    }


@app.get("/api/global/resumen")
def global_summary(
    _: dict = Depends(require_role("analista")), db: Session = Depends(get_db)
):
    total = db.scalar(select(func.count()).select_from(Transaction)) or 0
    amount = db.scalar(select(func.sum(Transaction.amount)))
    return {"total_transacciones": total, "monto_total": money(amount)}


@app.get("/api/global/mensual")
def global_monthly(
    _: dict = Depends(require_role("analista")), db: Session = Depends(get_db)
):
    month = func.to_char(Transaction.date, "YYYY-MM")
    rows = db.execute(
        select(month, func.count(), func.sum(Transaction.amount))
        .group_by(month)
        .order_by(month)
    ).all()
    return [
        {"mes": month_name, "transacciones": count, "monto": money(amount)}
        for month_name, count, amount in rows
    ]


@app.get("/api/global/alertas")
def global_alerts(
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(require_role("analista")),
    db: Session = Depends(get_db),
):
    filters = [Transaction.amount > ALERT_THRESHOLD]
    total = db.scalar(select(func.count()).select_from(Transaction).where(*filters)) or 0
    rows = db.scalars(
        select(Transaction)
        .where(*filters)
        .order_by(Transaction.amount.desc(), Transaction.date.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    return {
        "umbral": money(ALERT_THRESHOLD),
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total": total,
        "items": [transaction_json(row) for row in rows],
    }


def transaction_json(row: Transaction) -> dict:
    return {
        "id_transaccion": row.id,
        "id_cuenta": row.account_id,
        "fecha": row.date.isoformat(),
        "tipo": row.type,
        "operacion": row.operation,
        "monto": money(row.amount),
        "saldo_posterior": money(row.balance_after),
        "categoria": row.category,
    }


@app.get("/health")
def health():
    return {"service": "bank", "status": "ok"}