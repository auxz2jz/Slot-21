import numpy as np
import pytest

from laserline3d.laser_detection import detect_laser, suggest_laser_settings
from laserline3d.models import LaserSettings
from laserline3d.synthetic import make_synthetic_rig, render_laser_frame


def settings() -> LaserSettings:
    return LaserSettings(
        minimum_red=110,
        minimum_dominance=40,
        threshold=35,
        minimum_component_px=5,
        orientation="horizontal",
    )


def test_synthetic_stripe_is_found_at_subpixel_locations() -> None:
    rig = make_synthetic_rig()
    frame = render_laser_frame(rig, 170.0, noise_sigma=1.0)
    result = detect_laser(frame, settings(), rig.background_bgr)
    assert len(result.points) > 300
    assert result.orientation == "horizontal"
    assert np.isfinite(result.points).all()
    assert result.saturated_fraction < 0.5


def test_background_without_laser_has_no_stripe() -> None:
    rig = make_synthetic_rig()
    result = detect_laser(rig.background_bgr, settings(), rig.background_bgr)
    assert len(result.points) == 0
    assert not result.candidate_mask.any()


def test_resolution_mismatch_background_is_rejected() -> None:
    rig = make_synthetic_rig()
    frame = render_laser_frame(rig, 180.0)
    bad_background = rig.background_bgr[:-1]
    try:
        detect_laser(frame, settings(), bad_background)
    except ValueError as error:
        assert "resolution" in str(error).lower()
    else:
        raise AssertionError("Expected mismatched background to fail")


def test_auto_suggest_finds_working_start_values_on_synthetic_laser() -> None:
    rig = make_synthetic_rig()
    frame = render_laser_frame(rig, 170.0, noise_sigma=1.0)

    suggestion = suggest_laser_settings(frame, rig.background_bgr)
    result = detect_laser(frame, suggestion.settings, rig.background_bgr)

    assert suggestion.separation >= 8.0
    assert suggestion.settings.minimum_red >= 30
    assert suggestion.settings.minimum_dominance >= 3
    assert len(result.points) > 250


def test_auto_suggest_refuses_scene_without_a_separate_laser_population() -> None:
    rig = make_synthetic_rig()
    with pytest.raises(ValueError, match="laser stripe"):
        suggest_laser_settings(rig.background_bgr, rig.background_bgr)


def test_auto_suggest_refuses_changed_room_lighting() -> None:
    rig = make_synthetic_rig()
    changed = np.clip(rig.background_bgr.astype(np.int16) + 30, 0, 255).astype(np.uint8)
    with pytest.raises(ValueError, match="lighting|exposure"):
        suggest_laser_settings(changed, rig.background_bgr)
