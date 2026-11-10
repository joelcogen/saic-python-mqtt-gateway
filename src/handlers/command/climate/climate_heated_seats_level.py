from __future__ import annotations

import json
import logging
from typing import override

from exceptions import MqttGatewayException
from handlers.command.base import (
    RESULT_REFRESH_AND_CLEAR,
    CommandHandlerBase,
    CommandProcessingResult,
    IntCommandHandler,
)
import mqtt_topics

LOG = logging.getLogger(__name__)


class ClimateHeatedSeatsFrontLeftLevelCommand(IntCommandHandler):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEFT_LEVEL_SET

    @override
    async def handle_typed_payload(self, level: int) -> CommandProcessingResult:
        try:
            LOG.info("Setting heated seats front left level to %d", level)
            changed = self.vehicle_state.update_heated_seats_front_left_level(level)
            if changed:
                await self.saic_api.control_heated_seats(
                    self.vin,
                    left_side_level=self.vehicle_state.remote_heated_seats_front_left_level,
                    right_side_level=self.vehicle_state.remote_heated_seats_front_right_level,
                )
            else:
                LOG.info("Heated seats front left level not changed")
        except Exception as e:
            msg = f"Error setting heated seats: {e}"
            raise MqttGatewayException(msg) from e
        return RESULT_REFRESH_AND_CLEAR


class ClimateHeatedSeatsFrontRightLevelCommand(IntCommandHandler):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_RIGHT_LEVEL_SET

    @override
    async def handle_typed_payload(self, level: int) -> CommandProcessingResult:
        try:
            LOG.info("Setting heated seats front right level to %d", level)
            changed = self.vehicle_state.update_heated_seats_front_right_level(level)
            if changed:
                await self.saic_api.control_heated_seats(
                    self.vin,
                    left_side_level=self.vehicle_state.remote_heated_seats_front_left_level,
                    right_side_level=self.vehicle_state.remote_heated_seats_front_right_level,
                )
            else:
                LOG.info("Heated seats front right level not changed")
        except Exception as e:
            msg = f"Error setting heated seats: {e}"
            raise MqttGatewayException(msg) from e
        return RESULT_REFRESH_AND_CLEAR


class ClimateHeatedSeatsFrontLevelsCommand(CommandHandlerBase):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEVELS_SET

    @override
    async def handle(
        self, payload: str, *, retained: bool = False
    ) -> CommandProcessingResult:
        try:
            levels = json.loads(payload)
        except ValueError as exc:
            raise MqttGatewayException(
                "Expected JSON with left and right seat levels"
            ) from exc
        if not isinstance(levels, dict) or set(levels) != {"left", "right"}:
            raise MqttGatewayException("Both left and right seat levels are required")
        vehicle = self.vehicle_state.vehicle
        if not vehicle.has_heated_seats:
            raise MqttGatewayException("Vehicle does not support heated seats")
        maximum = 3 if vehicle.has_level_heated_seats else 1
        if any(
            type(level) is not int or not 0 <= level <= maximum
            for level in levels.values()
        ):
            msg = f"Seat levels must be integers from 0 to {maximum}"
            raise MqttGatewayException(msg)
        left, right = levels["left"], levels["right"]
        if (left, right) != (
            self.vehicle_state.remote_heated_seats_front_left_level,
            self.vehicle_state.remote_heated_seats_front_right_level,
        ):
            await self.saic_api.control_heated_seats(
                self.vin, left_side_level=left, right_side_level=right
            )
            # Preserve the previous levels on failure so a retry is not skipped.
            self.vehicle_state.update_heated_seats_front_left_level(left)
            self.vehicle_state.update_heated_seats_front_right_level(right)
        return RESULT_REFRESH_AND_CLEAR
