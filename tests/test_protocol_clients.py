from src.services.felix_client import FelixClient
from src.services.hyperlend_client import HyperlendClient
from src.services.hypurrfi_client import HypurrFiClient
from src.services.hyperbeat_client import HyperbeatClient
from unittest.mock import MagicMock, patch

def test_clients_instantiate() -> None:
    """Ensure clients can be instantiated."""
    c1 = FelixClient()
    c2 = HyperlendClient()
    c3 = HypurrFiClient()
    c4 = HyperbeatClient()
    assert c1.PROTOCOL_NAME == "Felix"
    assert c2.PROTOCOL_NAME == "Hyperlend"
    assert c3.PROTOCOL_NAME == "HypurrFi"
    assert c4.PROTOCOL_NAME == "Hyperbeat"

@patch("src.services.hyperlend_client.Web3")
def test_hyperlend_client_returns_list_on_fail(mock_w3) -> None:
    """Ensure clients return empty list on connection failure."""
    c = HyperlendClient()
    # Mock is_connected to return False
    c.w3.is_connected = MagicMock(return_value=False)
    
    assert c.fetch_pools() == []

@patch("src.services.felix_client.Web3")
def test_felix_client_returns_list_on_fail(mock_w3) -> None:
    c = FelixClient()
    c.w3.is_connected = MagicMock(return_value=False)
    assert c.fetch_pools() == []
