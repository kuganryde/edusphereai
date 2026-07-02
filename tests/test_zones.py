from surveillance.zones import Zone, bbox_feet_point, load_zones, point_in_polygon, save_zones

SQUARE = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]


def test_point_in_polygon_inside():
    assert point_in_polygon((0.5, 0.5), SQUARE) is True


def test_point_in_polygon_outside():
    assert point_in_polygon((0.05, 0.05), SQUARE) is False


def test_point_in_polygon_degenerate():
    assert point_in_polygon((0.5, 0.5), [(0.1, 0.1), (0.2, 0.2)]) is False


def test_bbox_feet_point_is_bottom_center():
    assert bbox_feet_point((10.0, 20.0, 30.0, 60.0)) == (20.0, 60.0)


def test_zone_to_pixels_scales_normalized_coords():
    zone = Zone(name="gate", points=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    assert zone.to_pixels(100, 200) == [(0, 0), (100, 0), (100, 200)]


def test_zone_round_trip_dict():
    zone = Zone(name="gate", points=[(0.1, 0.2)], kind="watch", classes=["car"], color=(1, 2, 3))
    restored = Zone.from_dict(zone.as_dict())
    assert restored == zone


def test_save_and_load_zones(tmp_path):
    path = tmp_path / "zones.json"
    zones = [Zone(name="a", points=SQUARE), Zone(name="b", points=SQUARE, kind="watch")]
    save_zones(zones, path)
    loaded = load_zones(path)
    assert [z.name for z in loaded] == ["a", "b"]
    assert loaded[1].kind == "watch"


def test_load_zones_missing_file_returns_empty(tmp_path):
    assert load_zones(tmp_path / "does_not_exist.json") == []


def test_load_zones_corrupt_file_returns_empty(tmp_path):
    path = tmp_path / "zones.json"
    path.write_text("not json{{{")
    assert load_zones(path) == []
