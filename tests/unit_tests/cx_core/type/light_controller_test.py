from typing import Any, Dict, Tuple, Type, Union

import pytest
from _pytest.monkeypatch import MonkeyPatch
from cx_core import LightController, ReleaseHoldController
from cx_core.controller import Controller
from cx_core.feature_support.light import LightSupport
from cx_core.stepper import Stepper
from cx_core.stepper.circular_stepper import CircularStepper
from cx_core.stepper.minmax_stepper import MinMaxStepper
from cx_core.type.light_controller import ColorMode, LightEntity
from pytest_mock.plugin import MockerFixture
from typing_extensions import Literal

from tests.test_utils import fake_fn, wrap_execution

ENTITY_NAME = "light.test"


@pytest.fixture
@pytest.mark.asyncio
async def sut_before_init(mocker: MockerFixture) -> LightController:
    controller = LightController()  # type: ignore
    controller.args = {}
    mocker.patch.object(controller, "get_state", fake_fn(None, async_=True))
    mocker.patch.object(Controller, "init")
    return controller


@pytest.fixture
@pytest.mark.asyncio
async def sut(mocker: MockerFixture) -> LightController:
    controller = LightController()  # type: ignore
    mocker.patch.object(controller, "get_state", fake_fn(None, async_=True))
    mocker.patch.object(Controller, "init")
    controller.args = {"light": ENTITY_NAME}
    await controller.init()
    return controller


@pytest.mark.parametrize(
    "light_input, expected_name, expected_color_mode, error_expected",
    [
        ("light.kitchen", "light.kitchen", "auto", False),
        (
            {"name": "light.kitchen", "color_mode": "auto"},
            "light.kitchen",
            "auto",
            False,
        ),
        (
            {"name": "light.kitchen"},
            "light.kitchen",
            "auto",
            False,
        ),
        (
            {"name": "light.kitchen", "color_mode": "color_temp"},
            "light.kitchen",
            "color_temp",
            False,
        ),
        (0.0, None, None, True),
    ],
)
@pytest.mark.asyncio
async def test_init(
    sut_before_init: LightController,
    light_input: Union[str, Dict[str, str]],
    expected_name: str,
    expected_color_mode: str,
    error_expected: bool,
):
    sut_before_init.args["light"] = light_input

    # SUT
    with wrap_execution(error_expected=error_expected, exception=ValueError):
        await sut_before_init.init()

    # Checks
    if not error_expected:
        assert sut_before_init.entity.name == expected_name
        assert sut_before_init.entity.color_mode == expected_color_mode


@pytest.mark.parametrize(
    "attribute_input, color_mode, supported_features, expected_attribute, error_expected",
    [
        ("color", "auto", LightSupport.COLOR, "xy_color", False),
        ("color", "auto", LightSupport.COLOR_TEMP, "color_temp", False),
        (
            "color",
            "auto",
            LightSupport.COLOR | LightSupport.COLOR_TEMP,
            "xy_color",
            False,
        ),
        ("brightness", "auto", 0, "brightness", False),
        ("brightness", "auto", LightSupport.COLOR, "brightness", False),
        (
            "color",
            "color_temp",
            LightSupport.COLOR | LightSupport.COLOR_TEMP,
            "color_temp",
            False,
        ),
        (
            "color",
            "xy_color",
            LightSupport.COLOR | LightSupport.COLOR_TEMP,
            "xy_color",
            False,
        ),
        ("color", "auto", 0, "not_important", True),
    ],
)
@pytest.mark.asyncio
async def test_get_attribute(
    sut: LightController,
    attribute_input: str,
    color_mode: ColorMode,
    supported_features: int,
    expected_attribute: str,
    error_expected: bool,
):
    sut.feature_support._supported_features = supported_features
    sut.entity = LightEntity(ENTITY_NAME, color_mode=color_mode)

    with wrap_execution(error_expected=error_expected, exception=ValueError):
        output = await sut.get_attribute(attribute_input)

    if not error_expected:
        assert output == expected_attribute


@pytest.mark.parametrize(
    "attribute_input, smooth_power_on_check, expected_output, error_expected",
    [
        ("xy_color", False, 0, False),
        ("brightness", False, 3.0, False),
        ("brightness", False, "3.0", False),
        ("brightness", False, "3", False),
        ("color_temp", False, 1, False),
        ("xy_color", False, 0, False),
        ("brightness", True, 0, False),
        ("brightness", False, "error", True),
        ("brightness", False, None, True),
        ("color_temp", False, None, True),
        ("not_a_valid_attribute", False, None, True),
    ],
)
@pytest.mark.asyncio
async def test_get_value_attribute(
    sut: LightController,
    mocker: MockerFixture,
    attribute_input: str,
    smooth_power_on_check: bool,
    expected_output: Union[int, float, str],
    error_expected: bool,
):
    sut.smooth_power_on = True
    sut.smooth_power_on_check = smooth_power_on_check

    mocker.patch.object(sut, "get_entity_state", fake_fn(expected_output, async_=True))

    with wrap_execution(error_expected=error_expected, exception=ValueError):
        output = await sut.get_value_attribute(attribute_input)

    if not error_expected:
        assert output == float(expected_output)


@pytest.mark.parametrize(
    "old, attribute, direction, stepper, smooth_power_on_check, stop_expected, expected_value_attribute",
    [
        (
            50,
            LightController.ATTRIBUTE_BRIGHTNESS,
            Stepper.UP,
            MinMaxStepper(1, 255, 254),
            False,
            False,
            51,
        ),
        (0, "xy_color", Stepper.UP, CircularStepper(0, 30, 30), False, False, 0),
        (
            499,
            "color_temp",
            Stepper.UP,
            MinMaxStepper(153, 500, 10),
            False,
            True,
            500,
        ),
        (
            0,
            LightController.ATTRIBUTE_BRIGHTNESS,
            Stepper.UP,
            MinMaxStepper(1, 255, 254),
            True,
            True,
            0,
        ),
    ],
)
@pytest.mark.asyncio
async def test_change_light_state(
    sut: LightController,
    mocker: MockerFixture,
    old: int,
    attribute: str,
    direction: Literal["up", "down"],
    stepper: MinMaxStepper,
    smooth_power_on_check: bool,
    stop_expected: bool,
    expected_value_attribute: int,
):
    called_service_patch = mocker.patch.object(sut, "call_service")

    sut.value_attribute = old
    sut.smooth_power_on_check = smooth_power_on_check
    sut.remove_transition_check = False
    sut.manual_steppers = {attribute: stepper}
    sut.automatic_steppers = {attribute: stepper}
    sut.feature_support._supported_features = 0

    stop = await sut.change_light_state(old, attribute, direction, stepper, "hold")

    assert stop == stop_expected
    assert sut.value_attribute == expected_value_attribute
    called_service_patch.assert_called()


@pytest.mark.parametrize(
    "attributes_input, remove_transition_check, attributes_expected",
    [
        (
            {"test": "test"},
            False,
            {"test": "test", "transition": 0.3},
        ),
        ({"test": "test"}, True, {"test": "test"}),
        (
            {"test": "test", "transition": 0.5},
            False,
            {"test": "test", "transition": 0.5},
        ),
        (
            {"test": "test", "transition": 0.5},
            True,
            {"test": "test"},
        ),
    ],
)
@pytest.mark.asyncio
async def test_call_light_service(
    sut: LightController,
    mocker: MockerFixture,
    attributes_input: Dict[str, str],
    remove_transition_check: bool,
    attributes_expected: Dict[str, str],
):
    called_service_patch = mocker.patch.object(sut, "call_service")
    sut.transition = 300
    sut.remove_transition_check = remove_transition_check
    await sut.call_light_service("test_service", **attributes_input)
    called_service_patch.assert_called_once_with(
        "test_service", entity_id=ENTITY_NAME, **attributes_expected
    )


@pytest.mark.parametrize(
    "add_transition, add_transition_turn_toggle, on_from_user, transition_support, expected_remove_transition_check",
    [
        (True, True, True, True, False),
        (True, True, True, False, True),
        (True, True, False, True, False),
        (True, True, False, False, True),
        (True, False, True, True, True),
        (True, False, True, False, True),
        (True, False, False, True, False),
        (True, False, False, False, True),
        (False, True, True, True, True),
        (False, True, True, False, True),
        (False, True, False, True, True),
        (False, True, False, False, True),
        (False, False, True, True, True),
        (False, False, True, False, True),
        (False, False, False, True, True),
        (False, False, False, False, True),
    ],
)
@pytest.mark.asyncio
async def test_check_remove_transition(
    sut: LightController,
    add_transition: bool,
    add_transition_turn_toggle: bool,
    on_from_user: bool,
    transition_support: bool,
    expected_remove_transition_check: bool,
):
    sut.transition = 300
    sut.add_transition = add_transition
    sut.add_transition_turn_toggle = add_transition_turn_toggle
    sut.feature_support._supported_features = (
        LightSupport.TRANSITION if transition_support else 0
    )
    output = await sut.check_remove_transition(on_from_user)
    assert output == expected_remove_transition_check


@pytest.mark.asyncio
async def test_on(
    sut: LightController,
    mocker: MockerFixture,
):
    call_light_service_patch = mocker.patch.object(sut, "call_light_service")

    await sut.on()

    call_light_service_patch.assert_called_once_with("light/turn_on")


@pytest.mark.asyncio
async def test_off(sut: LightController, mocker: MockerFixture):
    call_light_service_patch = mocker.patch.object(sut, "call_light_service")

    await sut.off()

    call_light_service_patch.assert_called_once_with("light/turn_off")


@pytest.mark.asyncio
async def test_toggle(sut: LightController, mocker: MockerFixture):
    call_light_service_patch = mocker.patch.object(sut, "call_light_service")

    await sut.toggle()

    call_light_service_patch.assert_called_once_with("light/toggle")


@pytest.mark.parametrize(
    "attribute, stepper, expected_attribute_value",
    [
        ("brightness", MinMaxStepper(1, 255, 1), 255),
        ("color_temp", MinMaxStepper(153, 500, 1), 500),
        ("test", MinMaxStepper(1, 10, 1), 10),
    ],
)
@pytest.mark.asyncio
async def test_toggle_full(
    sut: LightController,
    mocker: MockerFixture,
    attribute: str,
    stepper: MinMaxStepper,
    expected_attribute_value: int,
):
    call_service_patch = mocker.patch.object(sut, "call_service")
    sut.automatic_steppers = {attribute: stepper}

    await sut.toggle_full(attribute)

    call_service_patch.assert_called_once_with(
        "light/toggle",
        **{"entity_id": ENTITY_NAME, attribute: expected_attribute_value}
    )


@pytest.mark.parametrize(
    "attribute, stepper, expected_attribute_value",
    [
        ("brightness", MinMaxStepper(1, 255, 1), 1),
        ("color_temp", MinMaxStepper(153, 500, 1), 153),
        ("test", MinMaxStepper(1, 10, 1), 1),
    ],
)
@pytest.mark.asyncio
async def test_toggle_min(
    sut: LightController,
    mocker: MockerFixture,
    attribute: str,
    stepper: MinMaxStepper,
    expected_attribute_value: int,
):
    call_service_patch = mocker.patch.object(sut, "call_service")
    sut.automatic_steppers = {attribute: stepper}

    await sut.toggle_min(attribute)

    call_service_patch.assert_called_once_with(
        "light/toggle",
        **{"entity_id": ENTITY_NAME, attribute: expected_attribute_value}
    )


@pytest.mark.parametrize(
    "stepper_cls, min_max, fraction, expected_calls, expected_value",
    [
        (MinMaxStepper, (1, 255), 0, 1, 1),
        (MinMaxStepper, (1, 255), 1, 1, 255),
        (MinMaxStepper, (0, 10), 0.5, 1, 5),
        (MinMaxStepper, (0, 100), 0.2, 1, 20),
        (MinMaxStepper, (0, 100), -1, 1, 0),
        (MinMaxStepper, (0, 100), 1.5, 1, 100),
        (CircularStepper, (0, 100), 0, 0, None),
    ],
)
@pytest.mark.asyncio
async def test_set_value(
    sut: LightController,
    mocker: MockerFixture,
    stepper_cls: Type[Union[MinMaxStepper, CircularStepper]],
    min_max: Tuple[int, int],
    fraction: float,
    expected_calls: int,
    expected_value: int,
):
    attribute = "test_attribute"
    on_patch = mocker.patch.object(sut, "_on")
    stepper = stepper_cls(min_max[0], min_max[1], 1)
    sut.automatic_steppers = {attribute: stepper}

    await sut.set_value(attribute, fraction)

    assert on_patch.call_count == expected_calls
    if expected_calls > 0:
        on_patch.assert_called_with(**{attribute: expected_value})


@pytest.mark.asyncio
async def test_on_full(sut: LightController, mocker: MockerFixture):
    attribute = "test_attribute"
    max_ = 10
    on_patch = mocker.patch.object(sut, "_on")
    stepper = MinMaxStepper(1, max_, 10)
    sut.automatic_steppers = {attribute: stepper}

    await sut.on_full(attribute)

    on_patch.assert_called_once_with(**{attribute: max_})


@pytest.mark.asyncio
async def test_on_min(sut: LightController, mocker: MockerFixture):
    attribute = "test_attribute"
    min_ = 1
    on_patch = mocker.patch.object(sut, "_on")
    stepper = MinMaxStepper(min_, 10, 10)
    sut.automatic_steppers = {attribute: stepper}

    await sut.on_min(attribute)

    on_patch.assert_called_once_with(**{attribute: min_})


@pytest.mark.parametrize(
    "max_brightness, color_attribute, expected_attributes",
    [
        (255, "color_temp", {"brightness": 255, "color_temp": 370}),
        (255, "xy_color", {"brightness": 255, "xy_color": (0.323, 0.329)}),
        (120, "error", {"brightness": 120}),
    ],
)
@pytest.mark.asyncio
async def test_sync(
    sut: LightController,
    monkeypatch: MonkeyPatch,
    mocker: MockerFixture,
    max_brightness: int,
    color_attribute: str,
    expected_attributes: Dict[str, Any],
):
    sut.max_brightness = max_brightness
    sut.add_transition_turn_toggle = True
    sut.feature_support._supported_features = LightSupport.TRANSITION

    async def fake_get_attribute(*args, **kwargs):
        if color_attribute == "error":
            raise ValueError()
        return color_attribute

    monkeypatch.setattr(sut, "get_attribute", fake_get_attribute)
    monkeypatch.setattr(sut, "get_entity_state", fake_fn(async_=True, to_return="on"))
    called_service_patch = mocker.patch.object(sut, "call_service")

    await sut.sync()

    called_service_patch.assert_called_once_with(
        "light/turn_on",
        entity_id=ENTITY_NAME,
        **{"transition": 0.3, **expected_attributes}
    )


@pytest.mark.parametrize(
    "attribute_input, direction_input, light_state, smooth_power_on, expected_calls",
    [
        (LightController.ATTRIBUTE_BRIGHTNESS, Stepper.UP, "off", True, 1),
        (LightController.ATTRIBUTE_COLOR_TEMP, Stepper.UP, "off", True, 0),
        (LightController.ATTRIBUTE_COLOR_TEMP, Stepper.UP, "on", True, 1),
    ],
)
@pytest.mark.asyncio
async def test_click(
    sut: LightController,
    monkeypatch: MonkeyPatch,
    mocker: MockerFixture,
    attribute_input: str,
    direction_input: Literal["up", "down"],
    light_state: Literal["on", "off"],
    smooth_power_on: bool,
    expected_calls: int,
):
    value_attribute = 10
    monkeypatch.setattr(
        sut, "get_entity_state", fake_fn(to_return=light_state, async_=True)
    )
    monkeypatch.setattr(
        sut, "get_value_attribute", fake_fn(to_return=value_attribute, async_=True)
    )
    monkeypatch.setattr(
        sut, "get_attribute", fake_fn(to_return=attribute_input, async_=True)
    )
    change_light_state_patch = mocker.patch.object(sut, "change_light_state")
    sut.smooth_power_on = smooth_power_on
    sut.feature_support._supported_features = 0
    stepper = MinMaxStepper(1, 10, 10)
    sut.manual_steppers = {attribute_input: stepper}

    await sut.click(attribute_input, direction_input)

    assert change_light_state_patch.call_count == expected_calls


@pytest.mark.parametrize(
    "attribute_input, direction_input, previous_direction, light_state, smooth_power_on, expected_calls, expected_direction",
    [
        (
            LightController.ATTRIBUTE_BRIGHTNESS,
            Stepper.UP,
            Stepper.UP,
            "off",
            True,
            1,
            Stepper.UP,
        ),
        ("color_temp", Stepper.UP, Stepper.UP, "off", True, 0, Stepper.UP),
        ("color_temp", Stepper.UP, Stepper.UP, "on", True, 1, Stepper.UP),
        (
            "color_temp",
            Stepper.TOGGLE,
            Stepper.TOGGLE_DOWN,
            "on",
            True,
            1,
            Stepper.TOGGLE_DOWN,
        ),
    ],
)
@pytest.mark.asyncio
async def test_hold(
    sut: LightController,
    monkeypatch: MonkeyPatch,
    mocker: MockerFixture,
    attribute_input: str,
    direction_input: str,
    previous_direction: str,
    light_state: Literal["on", "off"],
    smooth_power_on: bool,
    expected_calls: int,
    expected_direction: str,
):
    value_attribute = 10
    monkeypatch.setattr(
        sut, "get_entity_state", fake_fn(to_return=light_state, async_=True)
    )
    monkeypatch.setattr(
        sut, "get_value_attribute", fake_fn(to_return=value_attribute, async_=True)
    )
    monkeypatch.setattr(
        sut, "get_attribute", fake_fn(to_return=attribute_input, async_=True)
    )
    sut.smooth_power_on = smooth_power_on
    sut.feature_support._supported_features = 0
    stepper = MinMaxStepper(1, 10, 10)
    stepper.previous_direction = previous_direction
    sut.automatic_steppers = {attribute_input: stepper}
    super_hold_patch = mocker.patch.object(ReleaseHoldController, "hold")

    await sut.hold(attribute_input, direction_input)

    assert super_hold_patch.call_count == expected_calls
    if expected_calls > 0:
        super_hold_patch.assert_called_with(attribute_input, expected_direction)


@pytest.mark.parametrize("value_attribute", [10, None])
@pytest.mark.asyncio
async def test_hold_loop(
    sut: LightController, mocker: MockerFixture, value_attribute: int
):
    attribute = "test_attribute"
    direction = Stepper.UP
    sut.smooth_power_on_check = False
    sut.value_attribute = value_attribute
    change_light_state_patch = mocker.patch.object(sut, "change_light_state")
    stepper = MinMaxStepper(1, 10, 10)
    sut.automatic_steppers = {attribute: stepper}

    exceeded = await sut.hold_loop(attribute, direction)

    if value_attribute is None:
        assert exceeded
    else:
        change_light_state_patch.assert_called_once_with(
            sut.value_attribute, attribute, direction, stepper, "hold"
        )
