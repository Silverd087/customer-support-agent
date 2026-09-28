from specialists.db import create_refund_request, get_order_status
from unittest.mock import Mock,MagicMock

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
        