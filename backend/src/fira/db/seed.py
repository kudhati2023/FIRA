import uuid
from datetime import date
from argon2 import PasswordHasher
from sqlalchemy import select
from fira.db.session import SessionLocal
from fira.models import (
    Tenant, AppUser, UserRole, VATRatePeriod, ConfigSetting
)

ph = PasswordHasher()

def seed_database() -> None:
    db = SessionLocal()
    try:
        print("[SEED] Starting database seeding...")

        # 1. Seed VAT Rate Periods (HC-3, FR-VAL-2)
        vat_periods = [
            {
                "jurisdiction": "ZW",
                "rate_basis_points": 1500,
                "effective_from": date(2020, 1, 1),
                "effective_to": date(2025, 12, 31),
                "note": "15.0% standard rate up to 31 Dec 2025"
            },
            {
                "jurisdiction": "ZW",
                "rate_basis_points": 1550,
                "effective_from": date(2026, 1, 1),
                "effective_to": None,
                "note": "15.5% standard rate from 1 Jan 2026"
            },
        ]

        for period_data in vat_periods:
            stmt = select(VATRatePeriod).where(
                VATRatePeriod.jurisdiction == period_data["jurisdiction"],
                VATRatePeriod.effective_from == period_data["effective_from"]
            )
            existing = db.execute(stmt).scalar_one_or_none()
            if not existing:
                db.add(VATRatePeriod(**period_data))
                print(f"  + Added VAT rate period: {period_data['rate_basis_points']/100}% from {period_data['effective_from']}")

        # 2. Seed System Config Settings (FR-EXC-5, §14)
        configs = [
            {
                "key": "match_confidence_threshold",
                "value_json": {"threshold": 90},
                "description": "Matches with confidence below this threshold require human review"
            },
            {
                "key": "amount_tolerance",
                "value_json": {"min_minor_units": 2, "percentage": 0.5},
                "description": "Tolerance for amount matching (greater of minor units or percentage)"
            },
            {
                "key": "e7_non_qualifying_keywords",
                "value_json": {
                    "keywords": [
                        "entertainment",
                        "passenger",
                        "motor vehicle",
                        "hospitality",
                        "club",
                        "lunch",
                        "golf",
                        "beverage",
                        "alcohol",
                        "staff function"
                    ]
                },
                "description": "Configurable non-qualifying expense keywords for advisory E7 flags"
            },
            {
                "key": "valid_status_strings",
                "value_json": {
                    "valid_statuses": ["VALID", "APPROVED", "SUCCESS", "FISCALISED", "ACCEPTED"]
                },
                "description": "Accepted valid status strings in ZIMRA FDMS claim list exports"
            },
            {
                "key": "tin_validation",
                "value_json": {"regex": "^\\d{9,10}$", "description": "9 to 10 numeric digits"},
                "description": "Format structure rule for Zimbabwean Tax Identification Numbers"
            }
        ]

        for cfg in configs:
            stmt = select(ConfigSetting).where(
                ConfigSetting.tenant_id.is_(None),
                ConfigSetting.key == cfg["key"]
            )
            existing = db.execute(stmt).scalar_one_or_none()
            if not existing:
                db.add(ConfigSetting(**cfg))
                print(f"  + Added system config setting: {cfg['key']}")

        # 3. Seed Default Tenant
        stmt = select(Tenant).where(Tenant.slug == "demo")
        demo_tenant = db.execute(stmt).scalar_one_or_none()
        if not demo_tenant:
            demo_tenant = Tenant(
                name="FIRA Advisory & Audit Practice",
                slug="demo",
                retention_months=24,
                settings_json={"default_currency": "USD", "jurisdiction": "ZW"},
                is_active=True
            )
            db.add(demo_tenant)
            db.flush()
            print("  + Added default demo tenant: 'demo'")

        # 4. Seed Default Users
        demo_password = ph.hash("FiraSecure2026!")
        users = [
            {
                "tenant_id": demo_tenant.id,
                "email": "admin@fira.local",
                "full_name": "Takudzwa Kunaka (Admin)",
                "role": UserRole.ADMIN,
                "password_hash": demo_password,
                "is_active": True
            },
            {
                "tenant_id": demo_tenant.id,
                "email": "reviewer@fira.local",
                "full_name": "Senior Tax Reviewer",
                "role": UserRole.REVIEWER,
                "password_hash": demo_password,
                "is_active": True
            },
            {
                "tenant_id": demo_tenant.id,
                "email": "operator@fira.local",
                "full_name": "Reconciliation Operator",
                "role": UserRole.OPERATOR,
                "password_hash": demo_password,
                "is_active": True
            }
        ]

        for user_data in users:
            stmt = select(AppUser).where(AppUser.email == user_data["email"])
            existing_user = db.execute(stmt).scalar_one_or_none()
            if not existing_user:
                db.add(AppUser(**user_data))
                print(f"  + Added app user: {user_data['email']} ({user_data['role'].value})")

        db.commit()
        print("[OK] Database seeding completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Error during database seeding: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
