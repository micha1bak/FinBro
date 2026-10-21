import pytest

from finbro.web.templating import plural_filter


@pytest.mark.parametrize(
    "path, active",
    [("/", "Dochody"), ("/settlement", "Rozliczenie"), ("/networth", "Majątek"), ("/settings", "Ustawienia")],
)
def test_navigation_marks_current_view(client, path, active):
    nav = client.get(path).text.split('aria-label="Widoki"')[1].split("</nav>")[0]
    assert f'aria-current="page">{active}<' in nav
    assert nav.count('aria-current="page"') == 1


@pytest.mark.parametrize(
    "n, text",
    [(1, "1 dochód"), (2, "2 dochody"), (4, "4 dochody"), (5, "5 dochodów"), (12, "12 dochodów"), (22, "22 dochody"), (0, "0 dochodów")],
)
def test_polish_plural(n, text):
    assert plural_filter(n, "dochód", "dochody", "dochodów") == text
