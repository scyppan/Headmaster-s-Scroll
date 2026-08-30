import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from headmasters_scroll.game_board import ADMIN_API_REVISION
from headmasters_scroll.game_board.desktop import AdminClient, LocalServer


def client_settings() -> dict:
    return {
        "admin_host": "127.0.0.1",
        "admin_port": 8764,
        "player_host": "127.0.0.1",
        "player_port": 8765,
        "admin_key": "test-admin-key",
    }


class LocalServerRecoveryTests(unittest.TestCase):
    def test_current_health_requires_both_ports_and_restart_capability(self):
        client = AdminClient(client_settings())
        current = {
            "service": "game-board",
            "ready": True,
            "api_revision": ADMIN_API_REVISION,
            "build": ADMIN_API_REVISION,
            "capabilities": ["session-restart", "verified-server-recovery"],
            "pid": 123,
        }

        with patch.object(
            client, "player_health", return_value={"service": "game-board"}
        ), patch.object(client, "admin_health", return_value=current):
            self.assertEqual(client.health(), current)

        with patch.object(
            client, "player_health", return_value={"service": "game-board"}
        ), patch.object(
            client,
            "admin_health",
            return_value={"service": "game-board", "ready": True},
        ):
            with self.assertRaisesRegex(RuntimeError, "older"):
                client.health()

    def test_legacy_health_404_can_be_authenticated_by_admin_state(self):
        client = AdminClient(client_settings())
        with patch.object(
            client,
            "player_health",
            return_value={"service": "game-board", "available": True},
        ), patch.object(
            client, "admin_health", side_effect=RuntimeError("Not Found")
        ), patch.object(
            client,
            "request",
            return_value={"settings": {}, "sessions": []},
        ) as request:
            self.assertTrue(client.identifies_game_board_service())

        request.assert_called_once_with(
            "GET", "/api/admin/state", timeout=2.0
        )

    def test_verified_dual_port_legacy_server_is_stopped(self):
        client = Mock(
            admin_port=8764,
            player_port=8765,
            identifies_game_board_service=Mock(return_value=True),
        )
        server = LocalServer(client)
        owners = {8764: {4321}, 8765: {4321}}
        released = {8764: set(), 8765: set()}
        with patch.object(
            server,
            "_listener_pids_by_port",
            side_effect=[owners, owners, released],
        ), patch.object(
            server, "_process_executable", return_value=sys.executable
        ), patch(
            "headmasters_scroll.game_board.desktop.os.kill"
        ) as kill:
            recovered = server._recover_stale_server(timeout=0.1)

        self.assertTrue(recovered)
        kill.assert_called_once_with(4321, signal.SIGTERM)
        self.assertEqual(
            client.identifies_game_board_service.call_count, 2
        )

    def test_recovery_never_stops_an_unverified_or_different_executable(self):
        client = Mock(
            admin_port=8764,
            player_port=8765,
            identifies_game_board_service=Mock(return_value=True),
        )
        server = LocalServer(client)
        owners = {8764: {4321}, 8765: {4321}}
        with patch.object(
            server, "_listener_pids_by_port", return_value=owners
        ), patch.object(
            server, "_process_executable", return_value="C:/Other/python.exe"
        ), patch(
            "headmasters_scroll.game_board.desktop.os.kill"
        ) as kill:
            with self.assertRaisesRegex(RuntimeError, "For safety"):
                server._recover_stale_server(timeout=0.1)

        kill.assert_not_called()

    def test_recovery_never_stops_split_port_owners(self):
        client = Mock(
            admin_port=8764,
            player_port=8765,
            identifies_game_board_service=Mock(return_value=True),
        )
        server = LocalServer(client)
        owners = {8764: {4321}, 8765: {9876}}
        with patch.object(
            server, "_listener_pids_by_port", return_value=owners
        ), patch(
            "headmasters_scroll.game_board.desktop.os.kill"
        ) as kill:
            with self.assertRaisesRegex(RuntimeError, "For safety"):
                server._recover_stale_server(timeout=0.1)

        kill.assert_not_called()

    def test_offline_start_launches_current_module_and_waits_for_health(self):
        client = Mock(admin_port=8764, player_port=8765)
        server = LocalServer(client)
        process = Mock()
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as temporary:
            server.log_path = Path(temporary) / "server.log"
            try:
                with patch.object(
                    server, "ready", side_effect=[False, True]
                ), patch.object(
                    server, "_recover_stale_server", return_value=False
                ), patch(
                    "headmasters_scroll.game_board.desktop.subprocess.Popen",
                    return_value=process,
                ) as popen:
                    server.start(timeout=0.2)
            finally:
                if server._log_stream is not None:
                    server._log_stream.close()
                    server._log_stream = None

        command = popen.call_args.args[0]
        self.assertEqual(
            command,
            [sys.executable, "-B", "-m", "headmasters_scroll.game_board.server"],
        )


if __name__ == "__main__":
    unittest.main()
