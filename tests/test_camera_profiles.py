import json

import pytest

from laserline3d.camera import CameraRequest
from laserline3d.camera_profiles import CameraProfile, load_camera_profile, save_camera_profile


def test_camera_profile_round_trips_selected_controls(tmp_path) -> None:
    profile = CameraProfile(
        name="Arducam low-light scan",
        camera=CameraRequest(
            index=1,
            backend=700,
            width=3264,
            height=2448,
            fps=15.0,
            pixel_format="MJPG",
        ),
        properties={"Autofocus": 0.0, "Exposure": -7.0, "Gain": 2.0},
    )
    path = tmp_path / "arducam.json"

    save_camera_profile(path, profile)
    loaded = load_camera_profile(path)

    assert loaded.to_dict() == profile.to_dict()
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema_version": 99}, "Unsupported"),
        ({"properties": {"Sensor temperature": 20.0}}, "not writable"),
        ({"properties": {"Exposure": float("nan")}}, "finite"),
    ],
)
def test_camera_profile_rejects_unknown_version_or_unsafe_values(change, message) -> None:
    data = {
        "schema": "laserline3d.camera-profile",
        "schema_version": 1,
        "name": "test",
        "camera": {
            "index": 0,
            "backend": 700,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "pixel_format": "MJPG",
        },
        "properties": {"Exposure": -7.0},
    }
    data.update(change)

    with pytest.raises(ValueError, match=message):
        CameraProfile.from_dict(data)
