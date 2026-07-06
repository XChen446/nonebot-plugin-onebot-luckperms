import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nonebot_plugin_onebot_luckperms.webeditor.bytebin import BytebinClient
from nonebot_plugin_onebot_luckperms.webeditor.websocket import BytesocksClient
from nonebot_plugin_onebot_luckperms.webeditor.session import WebEditorSession
from nonebot_plugin_onebot_luckperms.webeditor.manager import node_to_webeditor, node_from_webeditor
from nonebot_plugin_onebot_luckperms.core.models import PermissionNode, ContextSet


class TestBytebinClient:
    def test_init(self):
        client = BytebinClient()
        assert client.base_url == "https://usercontent.luckperms.net"

    def test_custom_url(self):
        client = BytebinClient("https://custom.example.com")
        assert client.base_url == "https://custom.example.com"

    @pytest.mark.asyncio
    async def test_upload_raises_on_bad_url(self):
        client = BytebinClient("https://httpbin.org/status")
        with pytest.raises(RuntimeError):
            await client.upload({"test": "data"})


class TestBytesocksClient:
    def test_init(self):
        client = BytesocksClient()
        assert client.channel is None
        assert client.is_active is False

    @pytest.mark.asyncio
    async def test_ping_pong(self):
        client = BytesocksClient()
        client.channel = "test-ch"
        sent = []

        async def mock_send(data):
            sent.append(data)

        client._send = mock_send

        inner = json.dumps({"type": "ping"})
        frame = json.dumps({"msg": inner, "signature": ""})
        await client._handle_message(frame)

        assert len(sent) == 1
        assert sent[0]["type"] == "pong"

    @pytest.mark.asyncio
    async def test_change_request_callback(self):
        callback = MagicMock()
        client = BytesocksClient(on_change_request=callback)
        client.channel = "test-ch"

        inner = json.dumps({"type": "change-request", "code": "ABC123"})
        frame = json.dumps({"msg": inner, "signature": ""})
        await client._handle_message(frame)

        callback.assert_called_once_with("ABC123")

    @pytest.mark.asyncio
    async def test_invalid_json_ignored(self):
        client = BytesocksClient()
        client.channel = "test-ch"
        client._ws = MagicMock()

        await client._handle_message("not json")
        if isinstance(client._ws, MagicMock):
            pass


class TestWebEditorSession:
    def test_session_init(self):
        get_payload = MagicMock(return_value={})
        apply_changes = MagicMock()
        session = WebEditorSession(get_payload, apply_changes)
        assert session.is_active is False

    @pytest.mark.asyncio
    async def test_session_url_format(self):
        get_payload = MagicMock(return_value={"metadata": {}})
        apply_changes = MagicMock()
        session = WebEditorSession(get_payload, apply_changes)

        session.bytebin = MagicMock()
        session.bytebin.upload = AsyncMock(return_value="ABC123")

        with patch("nonebot_plugin_onebot_luckperms.webeditor.session.BytesocksClient") as MockClient:
            mock_socks = AsyncMock()
            MockClient.return_value = mock_socks

            url = await session.open()
            assert url.startswith("https://luckperms.net/editor/")
            assert "ABC123" in url
            assert "#" not in url

    @pytest.mark.asyncio
    async def test_session_close(self):
        get_payload = MagicMock(return_value={})
        apply_changes = MagicMock()
        session = WebEditorSession(get_payload, apply_changes)

        with patch("nonebot_plugin_onebot_luckperms.webeditor.session.BytesocksClient") as MockClient:
            mock_socks = AsyncMock()
            MockClient.return_value = mock_socks
            session._socks = mock_socks
            await session.close()
            mock_socks.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_change_request_applied(self):
        get_payload = MagicMock(return_value={"metadata": {}})
        apply_changes = MagicMock()
        session = WebEditorSession(get_payload, apply_changes)
        session._closed = False

        session.bytebin = MagicMock()
        session.bytebin.download = AsyncMock(return_value={"changes": []})
        session.bytebin.upload = AsyncMock(return_value="NEWCODE")
        session._socks = MagicMock()
        session._socks.send_change_response = AsyncMock()

        await session._on_change_request("ABC123")
        apply_changes.assert_called_once()

    @pytest.mark.asyncio
    async def test_change_request_ignored_when_closed(self):
        get_payload = MagicMock(return_value={})
        apply_changes = MagicMock()
        session = WebEditorSession(get_payload, apply_changes)
        session._closed = True

        await session._on_change_request("ABC123")
        apply_changes.assert_not_called()


class TestWebEditorNodeConversion:
    def test_node_to_webeditor_basic(self):
        node = PermissionNode(key="test.node", value=True)
        result = node_to_webeditor(node)
        assert result["key"] == "test.node"
        assert result["value"] is True
        assert result["type"] == "permission"

    def test_node_to_webeditor_with_context(self):
        node = PermissionNode(key="test.node", value=False, contexts=ContextSet({"group_id": "123"}))
        result = node_to_webeditor(node)
        assert result["context"] == {"group_id": ["123"]}

    def test_node_to_webeditor_with_expiry(self):
        node = PermissionNode(key="test.node", value=True, expiry=1234567890)
        result = node_to_webeditor(node)
        assert result["expiry"] == 1234567890

    def test_node_from_webeditor_basic(self):
        data = {"key": "test.node", "value": True}
        node = node_from_webeditor(data)
        assert node.key == "test.node"
        assert node.value is True

    def test_node_from_webeditor_with_context(self):
        data = {"key": "test.node", "value": False, "context": {"group_id": ["123"]}}
        node = node_from_webeditor(data)
        assert node.value is False
        assert node.contexts.data == {"group_id": "123"}

    def test_node_from_webeditor_string_value(self):
        data = {"key": "test", "value": "true"}
        node = node_from_webeditor(data)
        assert node.value is True

    def test_node_roundtrip(self):
        original = PermissionNode(key="a.b", value=False, contexts=ContextSet({"x": "y"}), expiry=9999999999)
        converted = node_from_webeditor(node_to_webeditor(original))
        assert converted.key == original.key
        assert converted.value == original.value
        assert converted.contexts.data == original.contexts.data
