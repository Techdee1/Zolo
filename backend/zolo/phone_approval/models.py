from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, func
from zolo.core.base import Base

class PhoneApprovalEnrolment(Base):
    __tablename__ = 'phone_approval_enrolments'

    customer_id = Column(String(36), primary_key=True)
    phone_e164 = Column(String(20), nullable=False, unique=True)
    language = Column(String(10), nullable=False, default='en')
    pin_hash = Column(String(255), nullable=False)
    failed_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    phone_changed_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())


class PhoneCall(Base):
    __tablename__ = 'phone_calls'

    id = Column(String(36), primary_key=True)
    request_id = Column(String(36), ForeignKey('payment_requests.id'), nullable=False)
    provider_call_id = Column(String(255), nullable=True)
    public_id = Column(String(64), nullable=False, unique=True)
    status = Column(String(32), nullable=False, default='initiated')
    intent_hash = Column(String(64), nullable=True)
    pin_consumed = Column(Boolean, nullable=False, default=False)
    outcome = Column(String(32), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)