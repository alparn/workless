import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.bank_account import BankAccount
from app.models.client import Client
from app.schemas.bank_account import BankAccountCreate, BankAccountResponse, BankAccountUpdate

router = APIRouter(prefix="/api/v1/clients/{client_id}/bank-accounts", tags=["bank-accounts"])


async def _get_client_or_404(client_id: uuid.UUID, db: AsyncSession) -> Client:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


async def _get_bank_account_or_404(
    bank_account_id: uuid.UUID, client_id: uuid.UUID, db: AsyncSession
) -> BankAccount:
    result = await db.execute(
        select(BankAccount).where(
            BankAccount.id == bank_account_id, BankAccount.client_id == client_id
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found")
    return account


async def _clear_default_flag(client_id: uuid.UUID, db: AsyncSession, exclude_id: uuid.UUID | None = None) -> None:
    """Reset is_default for all other bank accounts of the client."""
    stmt = select(BankAccount).where(
        BankAccount.client_id == client_id, BankAccount.is_default.is_(True)
    )
    if exclude_id is not None:
        stmt = stmt.where(BankAccount.id != exclude_id)
    result = await db.execute(stmt)
    for account in result.scalars().all():
        account.is_default = False


@router.post("", response_model=BankAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_bank_account(
    client_id: uuid.UUID,
    payload: BankAccountCreate,
    db: AsyncSession = Depends(get_db),
) -> BankAccount:
    await _get_client_or_404(client_id, db)

    if payload.is_default:
        await _clear_default_flag(client_id, db)

    account = BankAccount(client_id=client_id, **payload.model_dump())
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


@router.get("", response_model=list[BankAccountResponse])
async def list_bank_accounts(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[BankAccount]:
    await _get_client_or_404(client_id, db)
    result = await db.execute(
        select(BankAccount)
        .where(BankAccount.client_id == client_id)
        .order_by(BankAccount.account_number)
    )
    return list(result.scalars().all())


@router.get("/{bank_account_id}", response_model=BankAccountResponse)
async def get_bank_account(
    client_id: uuid.UUID,
    bank_account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> BankAccount:
    return await _get_bank_account_or_404(bank_account_id, client_id, db)


@router.patch("/{bank_account_id}", response_model=BankAccountResponse)
async def update_bank_account(
    client_id: uuid.UUID,
    bank_account_id: uuid.UUID,
    payload: BankAccountUpdate,
    db: AsyncSession = Depends(get_db),
) -> BankAccount:
    account = await _get_bank_account_or_404(bank_account_id, client_id, db)

    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("is_default"):
        await _clear_default_flag(client_id, db, exclude_id=bank_account_id)

    for field, value in update_data.items():
        setattr(account, field, value)

    await db.flush()
    await db.refresh(account)
    return account


@router.delete("/{bank_account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank_account(
    client_id: uuid.UUID,
    bank_account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    account = await _get_bank_account_or_404(bank_account_id, client_id, db)
    await db.delete(account)
    await db.flush()
