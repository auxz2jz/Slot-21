import math

from laserline3d.camera import (
    camera_property_ids,
    camera_property_value_status,
    decode_fourcc,
    describe_camera_properties,
    read_camera_properties,
)


class FakeCapture:
    def get(self, property_id: int) -> float:
        return float(property_id) + 0.25


def test_camera_property_snapshot_includes_measurement_relevant_controls() -> None:
    values = read_camera_properties(FakeCapture())
    expected = {
        "Auto exposure",
        "Exposure",
        "Gain",
        "Brightness",
        "Contrast",
        "Saturation",
        "Hue",
        "Gamma",
        "Sharpness",
        "Backlight compensation",
        "Autofocus",
        "Focus",
        "Auto white balance",
        "White balance temperature",
        "Sensor temperature",
        "Iris",
        "Zoom",
        "Video FourCC",
        "Capture buffer size",
    }
    assert set(camera_property_ids()) == expected
    assert set(values) == expected
    assert all(isinstance(value, float) for value in values.values())


def test_camera_property_support_evidence_is_honest_about_sentinels() -> None:
    properties = {name: 4.0 for name in camera_property_ids()}
    properties["Gain"] = 0.0
    properties["Gamma"] = float("nan")
    properties["Iris"] = None
    properties["Video FourCC"] = float(
        ord("M") | ord("J") << 8 | ord("P") << 16 | ord("G") << 24
    )

    evidence = describe_camera_properties(properties)

    assert evidence["Gain"]["status"] == "zero_or_unsupported"
    assert evidence["Gamma"] == {
        "property_id": camera_property_ids()["Gamma"],
        "raw_value": None,
        "status": "unavailable",
    }
    assert evidence["Iris"]["status"] == "unavailable"
    assert evidence["Video FourCC"]["decoded_fourcc"] == "MJPG"
    assert camera_property_value_status(-6.0) == "reported"
    assert camera_property_value_status(math.inf) == "unavailable"
    assert decode_fourcc(0.0) is None


class PartiallyUnsupportedCapture:
    def get(self, property_id: int) -> float:
        if property_id == camera_property_ids()["Gamma"]:
            raise RuntimeError("driver refused property")
        return 0.0


def test_camera_property_reader_keeps_failed_properties_as_unavailable() -> None:
    # RuntimeError is deliberately not swallowed: unexpected backend failures
    # should remain visible rather than being mislabeled as unsupported.
    try:
        read_camera_properties(PartiallyUnsupportedCapture())
    except RuntimeError as error:
        assert "driver refused" in str(error)
    else:
        raise AssertionError("unexpected driver failures must propagate")
