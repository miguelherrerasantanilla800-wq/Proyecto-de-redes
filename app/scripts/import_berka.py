import argparse
import csv
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from bank_service.database import Base, SessionLocal, engine
from bank_service.models import Account, Transaction


TYPE_MAP = {"PRIJEM": "credito", "VYDAJ": "debito", "VYBER": "debito"}
CATEGORY_MAP = {
    "POJISTNE": "seguro",
    "SIPO": "servicios_hogar",
    "LEASING": "leasing",
    "UVER": "prestamo",
    "DUCHOD": "pension",
    "UROK": "intereses",
    "SLUZBY": "servicios",
}


def parse_date(raw: str):
    return datetime.strptime(raw, "%y%m%d").date()


def load(account_file: Path, transaction_file: Path, account_limit: int) -> tuple[int, int]:
    Base.metadata.create_all(engine)
    with account_file.open(encoding="utf-8-sig", newline="") as source:
        account_rows = list(csv.DictReader(source, delimiter=";"))
    selected_accounts = {
        int(row["account_id"]): parse_date(row["date"])
        for row in account_rows[:account_limit]
    }
    transaction_rows = []
    with transaction_file.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source, delimiter=";"):
            account_id = int(row["account_id"])
            if account_id not in selected_accounts:
                continue
            kind = TYPE_MAP.get(row["type"])
            if kind is None:
                raise ValueError(f"Tipo de transacción desconocido: {row['type']}")
            operation = row.get("operation") or "sin_especificar"
            raw_category = row.get("k_symbol") or "otros"
            transaction_rows.append(
                {
                    "id": int(row["trans_id"]),
                    "account_id": account_id,
                    "date": parse_date(row["date"]),
                    "type": kind,
                    "operation": operation,
                    "amount": Decimal(row["amount"]),
                    "balance_after": Decimal(row["balance"]),
                    "category": CATEGORY_MAP.get(raw_category, raw_category.lower()),
                }
            )

    with SessionLocal.begin() as session:
        for account_id, opened_on in selected_accounts.items():
            session.merge(Account(id=account_id, opened_on=opened_on))
        for start in range(0, len(transaction_rows), 1000):
            batch = transaction_rows[start : start + 1000]
            statement = insert(Transaction).values(batch).on_conflict_do_nothing(index_elements=["id"])
            session.execute(statement)
    return len(selected_accounts), len(transaction_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa una muestra del dataset Berka en banco_db.")
    parser.add_argument("--accounts", type=Path, required=True, help="Ruta a account.asc")
    parser.add_argument("--transactions", type=Path, required=True, help="Ruta a trans.asc")
    parser.add_argument("--account-limit", type=int, default=100)
    args = parser.parse_args()
    if args.account_limit < 1:
        parser.error("--account-limit debe ser mayor que cero")
    accounts, transactions = load(args.accounts, args.transactions, args.account_limit)
    print(f"Cuentas seleccionadas: {accounts}; transacciones leídas: {transactions}")


if __name__ == "__main__":
    main()