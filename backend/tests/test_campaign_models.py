import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import (
    User,
    Bot,
    Contact,
    Campaign,
    CampaignEmail,
)


@pytest.fixture
def db_session():
    """Provides a transactional database session for tests."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_contact_creation_and_user_relationship(db_session: Session):
    # 1. Create User
    test_email = f"lead_owner_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=test_email,
        password_hash="hashed_secret_test",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # 2. Create Contact under User
    contact = Contact(
        user_id=user.id,
        name="Sarah Connor",
        first_name="Sarah",
        email="sarah@cyberdyne.example.com",
        company="Cyberdyne Systems",
        role="Chief Security Officer",
        custom_variables={"industry": "Robotics", "lead_score": 95},
    )
    db_session.add(contact)
    db_session.commit()
    db_session.refresh(contact)

    # 3. Assertions
    assert contact.id is not None
    assert contact.user_id == user.id
    assert contact.name == "Sarah Connor"
    assert contact.first_name == "Sarah"
    assert contact.email == "sarah@cyberdyne.example.com"
    assert contact.company == "Cyberdyne Systems"
    assert contact.role == "Chief Security Officer"
    assert contact.custom_variables["industry"] == "Robotics"
    assert contact.created_at is not None
    assert contact.updated_at is not None

    # Relationship assertions
    assert contact.user.email == test_email
    assert len(user.contacts) == 1
    assert user.contacts[0].id == contact.id

    # Cleanup via cascade
    db_session.delete(user)
    db_session.commit()

    assert db_session.get(Contact, contact.id) is None


def test_campaign_creation_and_bot_relationship(db_session: Session):
    # 1. Create User and Bot (Website Knowledge Source)
    user = User(
        email=f"camp_user_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed_pw",
    )
    db_session.add(user)
    db_session.flush()

    bot = Bot(
        user_id=user.id,
        name="AI Outreach Source",
        website_url="https://outreach.example.com",
        status="READY",
    )
    db_session.add(bot)
    db_session.flush()

    # 2. Create Campaign linked to User and Bot
    campaign = Campaign(
        user_id=user.id,
        bot_id=bot.id,
        name="Q3 Product Announcement",
        status="DRAFT",
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    # 3. Assertions
    assert campaign.id is not None
    assert campaign.user_id == user.id
    assert campaign.bot_id == bot.id
    assert campaign.name == "Q3 Product Announcement"
    assert campaign.status == "DRAFT"
    assert campaign.created_at is not None
    assert campaign.updated_at is not None

    # Relationships
    assert campaign.user.id == user.id
    assert campaign.bot.id == bot.id
    assert len(user.campaigns) == 1
    assert user.campaigns[0].id == campaign.id
    assert len(bot.campaigns) == 1
    assert bot.campaigns[0].id == campaign.id

    # Cleanup
    db_session.delete(user)
    db_session.commit()

    assert db_session.get(Campaign, campaign.id) is None
    assert db_session.get(Bot, bot.id) is None


def test_campaign_email_creation_and_relationships(db_session: Session):
    # 1. Setup User, Bot, Contact, Campaign
    user = User(
        email=f"email_flow_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed_pw",
    )
    db_session.add(user)
    db_session.flush()

    bot = Bot(
        user_id=user.id,
        name="Knowledge Bot",
        website_url="https://knowledge.example.com",
        status="READY",
    )
    db_session.add(bot)
    db_session.flush()

    contact = Contact(
        user_id=user.id,
        name="John Doe",
        first_name="John",
        email="john@example.com",
        company="Acme Corp",
        role="VP Engineering",
    )
    db_session.add(contact)
    db_session.flush()

    campaign = Campaign(
        user_id=user.id,
        bot_id=bot.id,
        name="Summer Outreach",
        status="READY",
    )
    db_session.add(campaign)
    db_session.flush()

    # 2. Create CampaignEmail
    camp_email = CampaignEmail(
        campaign_id=campaign.id,
        contact_id=contact.id,
        subject="Personalized AI solutions for Acme Corp",
        body="Hi John, noticed Acme Corp is scaling engineering...",
        status="GENERATED",
    )
    db_session.add(camp_email)
    db_session.commit()
    db_session.refresh(camp_email)

    # 3. Assertions
    assert camp_email.id is not None
    assert camp_email.campaign_id == campaign.id
    assert camp_email.contact_id == contact.id
    assert camp_email.subject == "Personalized AI solutions for Acme Corp"
    assert "scaling engineering" in camp_email.body
    assert camp_email.status == "GENERATED"
    assert camp_email.sent_at is None
    assert camp_email.created_at is not None

    # Relationship verification
    assert camp_email.campaign.name == "Summer Outreach"
    assert camp_email.contact.name == "John Doe"
    assert len(campaign.campaign_emails) == 1
    assert campaign.campaign_emails[0].id == camp_email.id
    assert len(contact.campaign_emails) == 1
    assert contact.campaign_emails[0].id == camp_email.id

    # Cleanup
    db_session.delete(user)
    db_session.commit()


def test_cascade_delete_campaign_deletes_emails(db_session: Session):
    user = User(
        email=f"cascade_camp_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed_pw",
    )
    db_session.add(user)
    db_session.flush()

    bot = Bot(
        user_id=user.id,
        name="Bot for cascade test",
        website_url="https://cascade.example.com",
    )
    db_session.add(bot)
    db_session.flush()

    contact = Contact(
        user_id=user.id,
        name="Jane Doe",
        email="jane@example.com",
    )
    db_session.add(contact)
    db_session.flush()

    campaign = Campaign(
        user_id=user.id,
        bot_id=bot.id,
        name="Campaign to Delete",
    )
    db_session.add(campaign)
    db_session.flush()

    email_record = CampaignEmail(
        campaign_id=campaign.id,
        contact_id=contact.id,
        subject="Test subject",
        body="Test body",
    )
    db_session.add(email_record)
    db_session.commit()

    # Deleting campaign should cascade-delete campaign_email, but contact and bot survive
    db_session.delete(campaign)
    db_session.commit()

    assert db_session.get(CampaignEmail, email_record.id) is None
    assert db_session.get(Contact, contact.id) is not None
    assert db_session.get(Bot, bot.id) is not None

    # Cleanup
    db_session.delete(user)
    db_session.commit()


def test_cascade_delete_bot_deletes_campaigns(db_session: Session):
    user = User(
        email=f"cascade_bot_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed_pw",
    )
    db_session.add(user)
    db_session.flush()

    bot = Bot(
        user_id=user.id,
        name="Bot to Delete",
        website_url="https://deletebot.example.com",
    )
    db_session.add(bot)
    db_session.flush()

    contact = Contact(
        user_id=user.id,
        name="Bob Smith",
        email="bob@example.com",
    )
    db_session.add(contact)
    db_session.flush()

    campaign = Campaign(
        user_id=user.id,
        bot_id=bot.id,
        name="Campaign dependent on Bot",
    )
    db_session.add(campaign)
    db_session.flush()

    email_record = CampaignEmail(
        campaign_id=campaign.id,
        contact_id=contact.id,
        subject="Test",
        body="Test",
    )
    db_session.add(email_record)
    db_session.commit()

    # Deleting Bot should delete the Campaign and CampaignEmail
    db_session.delete(bot)
    db_session.commit()

    assert db_session.get(Campaign, campaign.id) is None
    assert db_session.get(CampaignEmail, email_record.id) is None
    assert db_session.get(Contact, contact.id) is not None
    assert db_session.get(User, user.id) is not None

    # Cleanup
    db_session.delete(user)
    db_session.commit()


def test_campaign_email_unique_constraint(db_session: Session):
    user = User(
        email=f"uniq_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed_pw",
    )
    db_session.add(user)
    db_session.flush()

    bot = Bot(
        user_id=user.id,
        name="Bot Unique",
        website_url="https://unique.example.com",
    )
    db_session.add(bot)
    db_session.flush()

    contact = Contact(
        user_id=user.id,
        name="Unique Contact",
        email="unique@example.com",
    )
    db_session.add(contact)
    db_session.flush()

    campaign = Campaign(
        user_id=user.id,
        bot_id=bot.id,
        name="Campaign Unique",
    )
    db_session.add(campaign)
    db_session.flush()

    email1 = CampaignEmail(
        campaign_id=campaign.id,
        contact_id=contact.id,
        subject="First Email",
        body="Body 1",
    )
    db_session.add(email1)
    db_session.commit()

    # Attempting to add a second CampaignEmail for same (campaign_id, contact_id) must fail
    email2 = CampaignEmail(
        campaign_id=campaign.id,
        contact_id=contact.id,
        subject="Duplicate Email",
        body="Body 2",
    )
    db_session.add(email2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Cleanup
    db_session.delete(user)
    db_session.commit()

