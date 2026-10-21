import math

from laserline3d.camera import (
    CameraRequest,
    assess_camera_mode,
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


def test_camera_mode_negotiation_accepts_normal_fractional_fps() -> None:
    result = assess_camera_mode(
        CameraRequest(width=3264, height=2448, fps=15.0, pixel_format="MJPG"),
        actual_width=3264,
        actual_height=2448,
        actual_fps=14.985,
        actual_format="MJPG",
        set_results={"pixel_format": True, "width": True, "height": True, "fps": True},
    )

    assert result["accepted"] is True
    assert result["mismatches"] == {}
    assert result["unverified"] == []
    assert result["actual"] == {
        "resolution": [3264, 2448],
        "fps": 14.985,
        "pixel_format": "MJPG",
    }


def test_camera_mode_negotiation_reports_driver_substitution() -> None:
    result = assess_camera_mode(
        CameraRequest(width=3264, height=2448, fps=30.0, pixel_format="MJPG"),
        actual_width=1920,
        actual_height=1080,
        actual_fps=30.0,
        actual_format="YUY2",
    )

    assert result["accepted"] is False
    assert result["mismatches"] == {
        "resolution": {"requested": [3264, 2448], "actual": [1920, 1080]},
        "pixel_format": {"requested": "MJPG", "actual": "YUY2"},
    }


def test_camera_mode_negotiation_does_not_claim_unreported_values() -> None:
    result = assess_camera_mode(
        CameraRequest(width=1920, height=1080, fps=30.0, pixel_format="MJPG"),
        actual_width=1920,
        actual_height=1080,
        actual_fps=0.0,
        actual_format=None,
    )

    assert result["accepted"] is False
    assert result["mismatches"] == {}
    assert result["unverified"] == ["fps", "pixel_format"]
