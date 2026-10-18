from app.news import NewsProvider

def test_no_false_positive_substring_matches():
    np = NewsProvider()

    # "ban" in "bank" must not trigger negative sentiment or potentially_material
    h1 = "HDFC Bank announces dividend"
    assert np.materiality(h1) == "unknown"
    assert np.sentiment(h1) == "neutral"

    # "order" in "border" must not trigger potentially_material
    h2 = "Border tensions remain calm today"
    assert np.materiality(h2) == "unknown"
    assert np.sentiment(h2) == "neutral"

    # "fall" in "fallout" must not trigger negative unless exact word
    h3 = "Economic fallout managed well with growth"
    assert np.sentiment(h3) == "positive"

def test_legitimate_keyword_matches():
    np = NewsProvider()

    h1 = "Government announces ban on unregulated imports"
    assert np.materiality(h1) == "potentially_material"
    assert np.sentiment(h1) == "negative"

    h2 = "Company wins major order win and secures approval"
    assert np.materiality(h2) == "potentially_material"
    assert np.sentiment(h2) == "positive"
