import re
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from fira.db.session import get_db
from fira.models.client import Client, ClientBranch
from fira.models.tenant import AppUser
from fira.security.audit import log_audit_event
from fira.security.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/clients", tags=["Clients"])

TIN_REGEX = re.compile(r"^\d{9,10}$")

class ClientCreate(BaseModel):
    legal_name: str = Field(..., min_length=2, max_length=255)
    trading_name: Optional[str] = None
    tin_raw: str = Field(..., description="Zimbabwean TIN (9 to 10 digits)")
    vat_number: Optional[str] = None
    vat_category: str = Field(default="C", max_length=10)
    default_currency: str = Field(default="USD", max_length=3)
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    city: Optional[str] = None

class ClientResponse(BaseModel):
    id: uuid.UUID
    legal_name: str
    trading_name: Optional[str]
    tin_raw: str
    tin_normalised: str
    vat_number: Optional[str]
    vat_category: str
    default_currency: str
    contact_name: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    city: Optional[str]

@router.get("", response_model=List[ClientResponse])
def list_clients(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ClientResponse]:
    """List all registered taxpayer clients strictly within caller's tenant (HC-6)."""
    stmt = (
        select(Client)
        .where(Client.tenant_id == current_user.tenant_id, Client.deleted_at.is_(None))
        .order_by(Client.legal_name.asc())
    )
    clients = db.execute(stmt).scalars().all()
    return [
        ClientResponse(
            id=c.id,
            legal_name=c.legal_name,
            trading_name=c.trading_name,
            tin_raw=c.tin_raw,
            tin_normalised=c.tin_normalised,
            vat_number=c.vat_number,
            vat_category=c.vat_category,
            default_currency=c.default_currency,
            contact_name=c.contact_name,
            contact_email=c.contact_email,
            contact_phone=c.contact_phone,
            city=c.city,
        )
        for c in clients
    ]

@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClientResponse:
    """Register a new Zimbabwean taxpayer business unit with TIN validation."""
    clean_tin = re.sub(r"\D", "", payload.tin_raw.strip())
    if not TIN_REGEX.match(clean_tin):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Zimbabwean TIN format. TIN must contain exactly 9 or 10 numeric digits.",
        )

    # Check for duplicate within same tenant
    dup_stmt = select(Client).where(
        Client.tenant_id == current_user.tenant_id,
        Client.tin_normalised == clean_tin,
        Client.deleted_at.is_(None),
    )
    if db.execute(dup_stmt).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A client with TIN '{clean_tin}' already exists in your organization.",
        )

    client = Client(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        legal_name=payload.legal_name.strip(),
        trading_name=payload.trading_name.strip() if payload.trading_name else None,
        tin_raw=payload.tin_raw.strip(),
        tin_normalised=clean_tin,
        vat_number=payload.vat_number.strip() if payload.vat_number else None,
        vat_category=payload.vat_category.upper(),
        default_currency=payload.default_currency.upper(),
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        city=payload.city,
    )
    db.add(client)
    db.flush()

    log_audit_event(
        db=db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="CLIENT_CREATED",
        entity_type="client",
        entity_id=str(client.id),
        after_json={
            "legal_name": client.legal_name,
            "tin": client.tin_normalised,
            "currency": client.default_currency,
        },
    )
    db.commit()

    return ClientResponse(
        id=client.id,
        legal_name=client.legal_name,
        trading_name=client.trading_name,
        tin_raw=client.tin_raw,
        tin_normalised=client.tin_normalised,
        vat_number=client.vat_number,
        vat_category=client.vat_category,
        default_currency=client.default_currency,
        contact_name=client.contact_name,
        contact_email=client.contact_email,
        contact_phone=client.contact_phone,
        city=client.city,
    )
