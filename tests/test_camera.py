from laserline3d.camera import camera_property_ids, read_camera_properties


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
        "Sharpness",
        "Autofocus",
        "Focus",
        "Auto white balance",
        "White balance temperature",
        "Zoom",
    }
    assert set(camera_property_ids()) == expected
    assert set(values) == expected
    assert all(isinstance(value, float) for value in values.values())
