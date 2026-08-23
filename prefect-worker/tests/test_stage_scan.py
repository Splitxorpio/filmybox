from datetime import date, timedelta

from flows.stage_scan import _bucket, _percentile, detect_stage


def test_bucket_boundaries():
    # Boundary values land in the NEXT higher bucket (thresholds are
    # exclusive upper bounds: roi < threshold), not the one they equal.
    assert _bucket(0.999) == "flop"
    assert _bucket(1.0) == "solid"
    assert _bucket(2.999) == "solid"
    assert _bucket(3.0) == "hit"
    assert _bucket(4.999) == "hit"
    assert _bucket(5.0) == "blockbuster"
    assert _bucket(100.0) == "blockbuster"


def test_percentile_single_value():
    assert _percentile([5.0], 0.25) == 5.0
    assert _percentile([5.0], 0.75) == 5.0


def test_percentile_interpolates():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _percentile(values, 0.5) == 3.0
    assert _percentile(values, 0.0) == 1.0
    assert _percentile(values, 1.0) == 5.0


TODAY = date(2026, 6, 1)


def test_detect_stage_post_release():
    assert detect_stage(date(2026, 5, 1), [], TODAY) == "post_release"
    assert detect_stage(TODAY, [], TODAY) == "post_release"  # releasing today counts


def test_detect_stage_trailer():
    trailers = [{"trailer_type": "trailer", "publish_date": date(2026, 5, 20)}]
    assert detect_stage(date(2026, 7, 1), trailers, TODAY) == "trailer"


def test_detect_stage_clip_counts_as_trailer():
    trailers = [{"trailer_type": "clip", "publish_date": date(2026, 5, 20)}]
    assert detect_stage(date(2026, 7, 1), trailers, TODAY) == "trailer"


def test_detect_stage_teaser():
    trailers = [{"trailer_type": "teaser", "publish_date": date(2026, 5, 20)}]
    assert detect_stage(date(2026, 7, 1), trailers, TODAY) == "teaser"


def test_detect_stage_future_trailer_not_yet_published_is_ignored():
    # publish_date in the future relative to `today` shouldn't count yet.
    trailers = [{"trailer_type": "trailer", "publish_date": date(2026, 6, 15)}]
    assert detect_stage(date(2026, 7, 1), trailers, TODAY) == "pre_release"


def test_detect_stage_pre_release_window():
    assert detect_stage(TODAY + timedelta(days=30), [], TODAY) == "pre_release"
    assert detect_stage(TODAY + timedelta(days=31), [], TODAY) == "announcement"


def test_detect_stage_announcement_default():
    assert detect_stage(date(2027, 1, 1), [], TODAY) == "announcement"
    assert detect_stage(None, [], TODAY) == "announcement"
