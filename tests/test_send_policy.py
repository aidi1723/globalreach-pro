from app.services.secret_store import EphemeralSecretStore
from app.services.send_policy import SendPolicyService
from app.services.send_quota import QuotaDecision, SendQuotaService
from app.services.suppression import SuppressionService
from app.storage.db import AppStorage


class FakeSuppression:
    def __init__(self, suppressed=None):
        self.suppressed = set(suppressed or [])
        self.calls = []

    def is_suppressed(self, recipient_email):
        self.calls.append(recipient_email)
        return recipient_email in self.suppressed


class FakeQuota:
    def __init__(self, decision=None):
        self.decision = decision or QuotaDecision(allowed=True)
        self.calls = []

    def check(self, account_label, daily_limit=0, hourly_limit=0, now=None):
        self.calls.append(
            {
                "account_label": account_label,
                "daily_limit": daily_limit,
                "hourly_limit": hourly_limit,
                "now": now,
            }
        )
        return self.decision


def make_policy(tmp_path):
    storage = AppStorage(tmp_path / "send_policy.db", secret_store=EphemeralSecretStore())
    suppression = SuppressionService(storage)
    quota = SendQuotaService(storage)
    return SendPolicyService(storage, suppression, quota), suppression, quota


def make_fake_policy(suppressed=None, quota_decision=None):
    suppression = FakeSuppression(suppressed=suppressed)
    quota = FakeQuota(decision=quota_decision)
    return SendPolicyService(None, suppression, quota), suppression, quota


def test_policy_blocks_suppressed_recipient(tmp_path):
    policy, suppression, _quota = make_policy(tmp_path)
    suppression.add("Buyer <Blocked@Example.com>", reason="unsubscribe", source="manual")

    decision = policy.evaluate(
        recipient_email="blocked@example.com",
        duplicate_count=0,
        duplicate_policy="send",
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=10,
        now="2026-07-06T11:00:00",
    )

    assert decision.status == "suppressed"
    assert decision.should_send is False
    assert decision.code == "suppression_match"


def test_policy_handles_duplicate_review_and_skip(tmp_path):
    policy, _suppression, _quota = make_policy(tmp_path)

    review_decision = policy.evaluate(
        recipient_email="buyer@example.com",
        duplicate_count=1,
        duplicate_policy="review",
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=10,
        now="2026-07-06T11:00:00",
    )
    skip_decision = policy.evaluate(
        recipient_email="buyer@example.com",
        duplicate_count=2,
        duplicate_policy="skip",
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=10,
        now="2026-07-06T11:00:00",
    )
    send_decision = policy.evaluate(
        recipient_email="buyer@example.com",
        duplicate_count=1,
        duplicate_policy="send",
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=10,
        now="2026-07-06T11:00:00",
    )

    assert review_decision.status == "review_required"
    assert review_decision.should_send is False
    assert skip_decision.status == "skipped_duplicate"
    assert skip_decision.should_send is False
    assert send_decision.status == "send"
    assert send_decision.should_send is True


def test_policy_unknown_duplicate_policy_fails_closed_without_quota():
    policy, _suppression, quota = make_fake_policy()

    decision = policy.evaluate(
        recipient_email="buyer@example.com",
        duplicate_count=1,
        duplicate_policy="unknown",
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=10,
    )

    assert decision.status == "review_required"
    assert decision.should_send is False
    assert quota.calls == []


def test_policy_handles_none_policy_and_string_duplicate_count_without_crashing():
    policy, _suppression, quota = make_fake_policy()

    decision = policy.evaluate(
        recipient_email="buyer@example.com",
        duplicate_count="1",
        duplicate_policy=None,
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=10,
    )

    assert decision.status == "review_required"
    assert decision.should_send is False
    assert quota.calls == []


def test_policy_blocks_rate_limited_account(tmp_path):
    policy, _suppression, quota = make_policy(tmp_path)
    quota.record_sent("acc-1", "prior@example.com", task_id=1, sent_at="2026-07-06T10:30:00")

    decision = policy.evaluate(
        recipient_email="buyer@example.com",
        duplicate_count=0,
        duplicate_policy="send",
        account_label="acc-1",
        daily_limit=0,
        hourly_limit=1,
        now="2026-07-06T11:00:00",
    )

    assert decision.status == "rate_limited"
    assert decision.should_send is False
    assert decision.code == "hourly_limit_reached"
    assert "每小时发送上限" in decision.message


def test_policy_blocks_empty_and_invalid_recipient(tmp_path):
    policy, _suppression, _quota = make_policy(tmp_path)

    empty_decision = policy.evaluate(
        recipient_email="",
        duplicate_count=0,
        duplicate_policy="send",
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=10,
    )
    invalid_decision = policy.evaluate(
        recipient_email="not-an-email",
        duplicate_count=0,
        duplicate_policy="send",
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=10,
    )

    assert empty_decision.status == "failed"
    assert empty_decision.should_send is False
    assert empty_decision.code == "invalid_email"
    assert invalid_decision.status == "failed"
    assert invalid_decision.should_send is False
    assert invalid_decision.code == "invalid_email"


def test_policy_blocks_malformed_recipients():
    policy, suppression, quota = make_fake_policy()

    for recipient_email in (
        "user..x@example.com",
        "user@example-.com",
        "junk buyer@example.com junk",
        "Buyer <buyer@example.com>",
        "mailto:buyer@example.com",
    ):
        decision = policy.evaluate(
            recipient_email=recipient_email,
            duplicate_count=0,
            duplicate_policy="send",
            account_label="acc-1",
            daily_limit=10,
            hourly_limit=10,
        )

        assert decision.status == "failed"
        assert decision.should_send is False
        assert decision.code == "invalid_email"

    assert suppression.calls == []
    assert quota.calls == []


def test_policy_invalid_recipient_does_not_call_suppression_or_quota():
    policy, suppression, quota = make_fake_policy()

    decision = policy.evaluate(
        recipient_email="not-an-email",
        duplicate_count=1,
        duplicate_policy="send",
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=10,
    )

    assert decision.status == "failed"
    assert decision.should_send is False
    assert suppression.calls == []
    assert quota.calls == []


def test_policy_suppression_beats_duplicate_and_quota():
    policy, suppression, quota = make_fake_policy(suppressed={"blocked@example.com"})

    decision = policy.evaluate(
        recipient_email="blocked@example.com",
        duplicate_count=1,
        duplicate_policy="send",
        account_label="acc-1",
        daily_limit=1,
        hourly_limit=1,
    )

    assert decision.status == "suppressed"
    assert decision.should_send is False
    assert suppression.calls == ["blocked@example.com"]
    assert quota.calls == []


def test_policy_duplicate_review_and_skip_do_not_call_quota():
    policy, _suppression, quota = make_fake_policy()

    review_decision = policy.evaluate(
        recipient_email="buyer@example.com",
        duplicate_count=1,
        duplicate_policy="review",
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=10,
    )
    skip_decision = policy.evaluate(
        recipient_email="buyer@example.com",
        duplicate_count=1,
        duplicate_policy="skip",
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=10,
    )

    assert review_decision.status == "review_required"
    assert skip_decision.status == "skipped_duplicate"
    assert quota.calls == []


def test_policy_eligible_send_calls_quota_once():
    policy, _suppression, quota = make_fake_policy()

    decision = policy.evaluate(
        recipient_email="buyer@example.com",
        duplicate_count=0,
        duplicate_policy="send",
        account_label="acc-1",
        daily_limit=10,
        hourly_limit=5,
        now="2026-07-06T11:00:00",
    )

    assert decision.status == "send"
    assert decision.should_send is True
    assert quota.calls == [
        {
            "account_label": "acc-1",
            "daily_limit": 10,
            "hourly_limit": 5,
            "now": "2026-07-06T11:00:00",
        }
    ]
