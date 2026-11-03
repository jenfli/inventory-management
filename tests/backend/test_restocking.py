"""
Tests for restocking order API endpoints.
"""
import pytest

from mock_data import restocking_orders


@pytest.fixture(autouse=True)
def clear_restocking_orders():
    """Restocking orders live in a module-level list; reset it so tests stay independent."""
    restocking_orders.clear()
    yield
    restocking_orders.clear()


def _forecast(client, sku):
    return next(f for f in client.get("/api/demand").json() if f["item_sku"] == sku)


class TestRestockingEndpoints:
    """Test suite for restocking-related endpoints."""

    def test_demand_exposes_restocking_fields(self, client):
        """Demand forecasts carry cost, lead time and supplier."""
        data = client.get("/api/demand").json()
        assert len(data) > 0
        for f in data:
            assert isinstance(f["unit_cost"], (int, float))
            assert f["unit_cost"] > 0
            assert isinstance(f["lead_time_days"], int)
            assert f["lead_time_days"] > 0
            assert f["supplier"]

    def test_get_restocking_orders_empty(self, client):
        """No orders exist before anything is submitted."""
        response = client.get("/api/restocking-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restocking_order(self, client):
        """A valid order is accepted and totals are computed server-side."""
        f = _forecast(client, "WDG-001")
        payload = {"budget": 10000, "items": [{"item_sku": "WDG-001", "quantity": 100}]}

        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 200

        order = response.json()
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Submitted"
        assert abs(order["total_cost"] - 100 * f["unit_cost"]) < 0.01
        assert order["lead_time_days"] == f["lead_time_days"]
        assert "T" in order["created_date"]
        assert "T" in order["expected_delivery"]

    def test_order_lead_time_is_max_of_items(self, client):
        """Order lead time equals the slowest line item."""
        a = _forecast(client, "FLT-405")
        b = _forecast(client, "WDG-001")
        payload = {
            "budget": 100000,
            "items": [
                {"item_sku": "FLT-405", "quantity": 10},
                {"item_sku": "WDG-001", "quantity": 10},
            ],
        }
        order = client.post("/api/restocking-orders", json=payload).json()
        assert order["lead_time_days"] == max(a["lead_time_days"], b["lead_time_days"])

    def test_create_order_empty_items(self, client):
        response = client.post("/api/restocking-orders", json={"budget": 100, "items": []})
        assert response.status_code == 400

    def test_create_order_unknown_sku(self, client):
        payload = {"budget": 100000, "items": [{"item_sku": "NOPE-999", "quantity": 1}]}
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 400
        assert "unknown sku" in response.json()["detail"].lower()

    def test_create_order_non_positive_quantity(self, client):
        payload = {"budget": 100000, "items": [{"item_sku": "WDG-001", "quantity": 0}]}
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 400

    def test_create_order_duplicate_sku(self, client):
        payload = {
            "budget": 100000,
            "items": [
                {"item_sku": "WDG-001", "quantity": 1},
                {"item_sku": "WDG-001", "quantity": 2},
            ],
        }
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 400

    def test_create_order_over_budget(self, client):
        payload = {"budget": 1, "items": [{"item_sku": "WDG-001", "quantity": 100}]}
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()

    def test_orders_listed_newest_first(self, client):
        """Submitted orders are returned newest first."""
        for qty in (1, 2):
            client.post(
                "/api/restocking-orders",
                json={"budget": 100000, "items": [{"item_sku": "WDG-001", "quantity": qty}]},
            )
        data = client.get("/api/restocking-orders").json()
        assert len(data) == 2
        assert data[0]["items"][0]["quantity"] == 2
        assert data[1]["items"][0]["quantity"] == 1
