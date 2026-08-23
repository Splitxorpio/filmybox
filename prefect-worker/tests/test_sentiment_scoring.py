from sentiment_scoring import summarize_items


def test_empty_items():
    result = summarize_items([])
    assert result == {"volume": 0, "avg_engagement_score": None, "sentiment_score": None, "sample_ids": []}


def test_no_lexicon_hits_gives_none_not_zero():
    items = [{"id": "1", "text": "just a normal sentence with no keywords", "engagement": 5}]
    result = summarize_items(items)
    assert result["sentiment_score"] is None
    assert result["volume"] == 1
    assert result["avg_engagement_score"] == 5.0


def test_positive_only():
    items = [{"id": "1", "text": "This movie was amazing and incredible", "engagement": 10}]
    result = summarize_items(items)
    assert result["sentiment_score"] == 1.0


def test_negative_only():
    items = [{"id": "1", "text": "What a terrible, awful disaster", "engagement": 2}]
    result = summarize_items(items)
    assert result["sentiment_score"] == -1.0


def test_mixed_sentiment_is_averaged():
    # 2 positive words, 1 negative word -> (2-1)/(2+1) = 0.3333
    items = [{"id": "1", "text": "amazing and great, but kind of boring too", "engagement": 0}]
    result = summarize_items(items)
    assert result["sentiment_score"] == round(1 / 3, 4)


def test_engagement_is_averaged_across_items():
    items = [
        {"id": "1", "text": "no keywords here", "engagement": 10},
        {"id": "2", "text": "no keywords here either", "engagement": 20},
    ]
    result = summarize_items(items)
    assert result["avg_engagement_score"] == 15.0
    assert result["volume"] == 2


def test_sample_ids_skip_falsy_ids():
    items = [{"id": "1", "text": "a", "engagement": 0}, {"id": "", "text": "b", "engagement": 0}]
    result = summarize_items(items)
    assert result["sample_ids"] == ["1"]
