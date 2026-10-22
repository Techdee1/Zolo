import pytest
from fastapi.testclient import TestClient
from zolo.api.main import app
from zolo.phone_approval.models import PhoneApprovalEnrolment
from zolo.phone_approval.pin import hash_pin

client = TestClient(app)

def test_phone_approval_flow_happy_path(db_session):
    # Setup test customer enrolment with pre-hashed pin '1234'
    enrolment = PhoneApprovalEnrolment(
        customer_id="cust_test_1",
        phone_e164="+2348011112222",
        language="en",
        pin_hash=hash_pin("1234")
    )
    db_session.add(enrolment)
    db_session.commit()

    # Test call initialization simulation webhook callbacks
    # ... Add assertions checking successful state mutation, audio playback TwiML, and settlement results.