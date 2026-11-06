import pytest

from finbro.web.templating import content_version, plural_filter


@pytest.mark.parametrize(
    "path, active",
    [("/", "Dochody"), ("/settlement", "Rozliczenie"), ("/networth", "Majątek"), ("/settings", "Ustawienia")],
)
def test_navigation_marks_current_view(client, path, active):
    nav = client.get(path).text.split('aria-label="Widoki"')[1].split("</nav>")[0]
    assert f'aria-current="page">{active}<' in nav
    assert nav.count('aria-current="page"') == 1


@pytest.mark.parametrize("path", ["/", "/settlement", "/networth", "/settings"])
def test_header_has_plain_brand_and_theme_toggle(client, path):
    page = client.get(path).text
    assert '<a class="brand" href="/">FinBro</a>' in page
    assert 'id="theme-toggle"' in page and "theme.js" in page


def test_assets_are_addressed_by_content_version(client, tmp_path):
    page = client.get("/").text
    assert 'finbro.css?v=' in page and 'theme.js?v=' in page

    asset = tmp_path / "finbro.css"
    asset.write_text("a", encoding="utf-8")
    before = content_version(asset)
    asset.write_text("b", encoding="utf-8")
    assert content_version(asset) != before


def test_theme_script_is_served(client):
    assert "finbro-theme" in client.get("/static/theme.js").text


@pytest.mark.parametrize(
    "n, text",
    [(1, "1 dochód"), (2, "2 dochody"), (4, "4 dochody"), (5, "5 dochodów"), (12, "12 dochodów"), (22, "22 dochody"), (0, "0 dochodów")],
)
def test_polish_plural(n, text):
    assert plural_filter(n, "dochód", "dochody", "dochodów") == text
