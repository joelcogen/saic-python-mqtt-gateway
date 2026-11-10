from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from saic_ismart_client_ng import SaicApi
from saic_ismart_client_ng.exceptions import SaicApiException

from handlers.vehicle_command import VehicleCommandHandler
import mqtt_topics
from tests.common_mocks import VIN

PREFIX = f"vehicles/{VIN}"
TOPIC = f"saic/{PREFIX}/{mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEVELS_SET}"
RESULT = f"{PREFIX}/{mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEVELS}/result"


class TestCombinedFrontSeats(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.api = AsyncMock(spec=SaicApi)
        self.state = MagicMock()
        self.state.vin = VIN
        self.state.vehicle.has_heated_seats = True
        self.state.vehicle.has_level_heated_seats = True
        self.state.remote_heated_seats_front_left_level = 0
        self.state.remote_heated_seats_front_right_level = 0
        self.handler = VehicleCommandHandler(
            vehicle_state=self.state,
            saic_api=self.api,
            relogin_handler=AsyncMock(),
            mqtt_topic="saic",
            vehicle_prefix=PREFIX,
        )

    async def test_both_seats_use_one_call(self) -> None:
        await self.handler.handle_mqtt_command(
            topic=TOPIC, payload='{"left":3,"right":2}'
        )
        self.api.control_heated_seats.assert_awaited_once_with(
            VIN, left_side_level=3, right_side_level=2
        )
        self.state.update_heated_seats_front_left_level.assert_called_once_with(3)
        self.state.update_heated_seats_front_right_level.assert_called_once_with(2)
        self.state.publisher.publish_str.assert_any_call(
            RESULT, "Success", retain=False
        )
        self.state.set_refresh_mode.assert_called_once()

    async def test_off(self) -> None:
        self.state.remote_heated_seats_front_left_level = 3
        await self.handler.handle_mqtt_command(
            topic=TOPIC, payload='{"left":0,"right":0}'
        )
        self.api.control_heated_seats.assert_awaited_once_with(
            VIN, left_side_level=0, right_side_level=0
        )

    async def test_invalid_payloads_do_not_mutate_or_call(self) -> None:
        for payload in (
            "bad",
            "[]",
            "{}",
            '{"left":3}',
            '{"left":3,"right":4}',
            '{"left":true,"right":1}',
            '{"left":1.5,"right":1}',
            '{"left":-1,"right":1}',
            '{"left":1,"right":1,"extra":0}',
        ):
            with self.subTest(payload=payload):
                await self.handler.handle_mqtt_command(topic=TOPIC, payload=payload)
        self.api.control_heated_seats.assert_not_awaited()
        self.state.update_heated_seats_front_left_level.assert_not_called()
        self.state.update_heated_seats_front_right_level.assert_not_called()
        self.state.set_refresh_mode.assert_not_called()

    async def test_on_off_model_rejects_level_three(self) -> None:
        self.state.vehicle.has_level_heated_seats = False
        await self.handler.handle_mqtt_command(
            topic=TOPIC, payload='{"left":1,"right":3}'
        )
        self.api.control_heated_seats.assert_not_awaited()
        self.state.update_heated_seats_front_left_level.assert_not_called()
        await self.handler.handle_mqtt_command(
            topic=TOPIC, payload='{"left":1,"right":1}'
        )
        self.api.control_heated_seats.assert_awaited_once_with(
            VIN, left_side_level=1, right_side_level=1
        )

    async def test_unsupported_vehicle(self) -> None:
        self.state.vehicle.has_heated_seats = False
        await self.handler.handle_mqtt_command(
            topic=TOPIC, payload='{"left":1,"right":1}'
        )
        self.api.control_heated_seats.assert_not_awaited()

    async def test_failure_preserves_state_for_retry(self) -> None:
        self.api.control_heated_seats.side_effect = SaicApiException("busy")
        await self.handler.handle_mqtt_command(
            topic=TOPIC, payload='{"left":3,"right":3}'
        )
        self.state.update_heated_seats_front_left_level.assert_not_called()
        self.state.update_heated_seats_front_right_level.assert_not_called()
        self.state.set_refresh_mode.assert_not_called()
        self.state.publisher.publish_str.assert_any_call(
            RESULT, "Failed: busy", retain=False
        )
        self.api.control_heated_seats.side_effect = None
        await self.handler.handle_mqtt_command(
            topic=TOPIC, payload='{"left":3,"right":3}'
        )
        assert self.api.control_heated_seats.await_count == 2

    async def test_retained_command_not_replayed(self) -> None:
        await self.handler.handle_mqtt_command(
            topic=TOPIC, payload='{"left":3,"right":3}', retained=True
        )
        self.api.control_heated_seats.assert_not_awaited()

    async def test_unchanged_levels_skip_api(self) -> None:
        await self.handler.handle_mqtt_command(
            topic=TOPIC, payload='{"left":0,"right":0}'
        )
        self.api.control_heated_seats.assert_not_awaited()
