from unittest.mock import MagicMock, Mock

from specialists.db import (
    create_refund_request,
    create_return_request,
    get_order_status,
    get_return_status,
    get_subscription_status,
    get_warranty_claim_status,
)


class TestDbSpecialist:
    def test_create_refund_request_creates_new(self,mocker):

        fake_order = Mock(id="order-uuid-123")
        fake_refund = Mock(id="refund-uuid-456")

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = fake_order
        mock_db.scalars.return_value.one_or_none.return_value = fake_refund

        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False
        result = create_refund_request.func("order123", "test@example.com", "damaged on arrival")

        assert "successfully submitted" in result
        assert "refund-uuid-456" in result
        mock_db.commit.assert_called_once()

    def test_create_refund_request_dedupes_existing(self,mocker):
        fake_order = Mock(id="order-uuid-123")
        fake_refund = Mock(id="refund-uuid-456")

        mock_db = MagicMock()
        mock_db.execute.side_effect= [
            Mock(scalar_one_or_none = Mock(return_value=fake_order)),Mock(scalar_one_or_none = Mock(return_value=fake_refund))
        ]
        mock_db.scalars.return_value.one_or_none.return_value = None

        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False
        result = create_refund_request.func("order123", "test@example.com", "damaged on arrival")

        assert "successfully submitted" in result
        assert "refund-uuid-456" in result
        mock_db.commit.assert_called_once()

    def test_get_order_status_not_found_message(self,mocker):
        fake_order = Mock(id="order-uuid-123")

        mock_db = MagicMock()

        mock_db.scalar.return_value = None
        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False

        result = get_order_status.func(fake_order,"test@example.com")
        assert "Order not found or email does not match." in result
    def test_get_subscription_status_returns_formatted_list(self,mocker):
        fake_row1 = Mock()
        fake_row1.plan.value = "individual"
        fake_row1.status.value = "active"
        fake_row1.billing_cycle.value = "Monthly"
        fake_row1.current_period_start = "01-02-2026"
        fake_row1.current_period_end = "01-03-2026"

        fake_row2 = Mock()
        fake_row2.plan.value = "family"
        fake_row2.billing_cycle.value = "annual"
        fake_row2.status.value = "inactive"
        fake_row2.current_period_start = "01-02-2026"
        fake_row2.current_period_end = "01-01-2027"

        mock_db = Mock()
        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False
        mock_db.scalars.return_value.all.return_value = [fake_row1,fake_row2]

        lines = [
                f"{sub.plan.value} plan ({sub.billing_cycle.value}): {sub.status.value}, "
                f"period {sub.current_period_start} to {sub.current_period_end}"
                for sub in [fake_row1,fake_row2]
            ]
        assert "\n".join(lines) == get_subscription_status.func("test@exemple.com")

    def test_get_subscription_status_not_found_message(self,mocker):

        mock_db = Mock()
        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False
        mock_db.scalars.return_value.all.return_value = []

        assert "Subscription not found or email does not match." == get_subscription_status.func("test@exemple.com")

    def test_get_warranty_claim_status_returns_formatted_list(self,mocker):
        fake_row1 = Mock()
        fake_row1.order_item.product.name = "wifi"
        fake_row1.status.value = "submitted"
        fake_row1.created_at.date.return_value = "01-02-2026"
        fake_row1.issue_description = "Faulty product"

        fake_row2 = Mock()
        fake_row2.order_item.product.name = "another wifif"
        fake_row2.status.value = "approved"
        fake_row2.created_at.date.return_value = "01-02-2026"
        fake_row2.issue_description = "doesn't work"

        mock_db = Mock()
        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False
        mock_db.scalars.return_value.all.return_value = [fake_row1,fake_row2]

        lines = [
                    f"{claim.order_item.product.name}: {claim.status.value} "
                    f"(filed {claim.created_at.date()}) — \"{claim.issue_description}\""
                    for claim in [fake_row1,fake_row2]
                ]
        assert "\n".join(lines) == get_warranty_claim_status.func("ORD-1234","test@exemple.com")     
    def test_get_warranty_claim_status_not_found_message(self,mocker):
        mock_db = Mock()
        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False
        mock_db.scalars.return_value.all.return_value = []

        assert "warranty claim not found or email does not match." == get_warranty_claim_status.func("ORD-1234","test@exemple.com")  
    def test_get_return_status_returns_formatted_list(self,mocker):
        fake_row1 = Mock()
        fake_row1.order_item.product.name = "wifi"
        fake_row1.status.value = "requested"
        fake_row1.requested_at.date.return_value = "01-02-2026"
        fake_row1.reason = "Faulty product"

        fake_row2 = Mock()
        fake_row2.order_item.product.name = "another wifif"
        fake_row2.status.value = "requested"
        fake_row2.requested_at.date.return_value = "01-02-2026"
        fake_row2.reason = "doesn't work"

        mock_db = Mock()
        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False
        mock_db.scalars.return_value.all.return_value = [fake_row1,fake_row2]

        lines = [
                        f"{r.order_item.product.name}: {r.status.value} "
                        f"(filed {r.requested_at.date()}) — \"{r.reason}\""
                        for r in [fake_row1,fake_row2]
                    ]
        assert "\n".join(lines) == get_return_status.func("ORD-1234","test@exemple.com")

    def test_get_return_status_not_found_message(self,mocker):
        mock_db = Mock()
        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False
        mock_db.scalars.return_value.all.return_value = []

        assert "order return not found or email does not match." == get_return_status.func("ORD-1234","test@exemple.com")

    def test_create_return_request_not_found(self,mocker):
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False

        assert "Order item not found or email does not match." == create_return_request.func("ORD-123","test@exemple.com","lumen wifi","doesn't work")

    def test_create_return_request_creates_new(self,mocker):
        order_item = Mock(id="order-item-uuid-1234")
        order_return = Mock(id="order-return-uuid-1234")
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = order_item
        mock_db.scalars.return_value.one_or_none.return_value = order_return
        mock_db.commit.return_value = None
        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False

        assert  "Return request successfully submitted for product lumen wifi for order 'Ord-123' return id order-return-uuid-1234." == create_return_request.func("Ord-123","test@exemple.com","lumen wifi","doesn't work")

    def test_create_return_request_dedupes_existing(self,mocker):
        order_item = Mock(id="order-item-uuid-1234")
        order_return = Mock(id="order-return-uuid-1234")
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [order_item,order_return]
        mock_db.scalars.return_value.one_or_none.return_value = None
        mock_db.commit.return_value = None
        mock_get_db = mocker.patch("specialists.db.get_db")
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = False

        assert  "Return request successfully submitted for product lumen wifi for order 'Ord-123' return id order-return-uuid-1234." == create_return_request.func("Ord-123","test@exemple.com","lumen wifi","doesn't work")

