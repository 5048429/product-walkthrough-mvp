from __future__ import annotations

from prodwalk.agents.page_discovery import PageDiscoveryCrawler, normalize_discovery_url


def test_normalize_discovery_url_removes_tracking_and_secret_query_values() -> None:
    normalized = normalize_discovery_url(
        "https://APP.example.test/app/customers/?utm_source=ad&token=secret&view=summary&page=2#/settings?tab=billing&auth=x"
    )

    assert normalized == "https://app.example.test/app/customers?view=summary#/settings?tab=billing"


def test_page_discovery_crawler_filters_external_assets_and_unsafe_routes() -> None:
    crawler = PageDiscoveryCrawler(
        allowed_domains=["app.example.test", "*.example.test"],
        allowed_path_prefixes=["/app", "#/settings"],
        max_pages=10,
        max_depth=2,
        click_navigation=False,
    )

    assert crawler.should_visit("https://app.example.test/app/customers")
    assert crawler.should_visit("https://console.example.test/app/balances?tab=open")
    assert crawler.should_visit("https://app.example.test/#/settings/team")
    assert not crawler.should_visit("https://external.example.org/app/customers")
    assert not crawler.should_visit("https://app.example.test/other")
    assert not crawler.should_visit("https://app.example.test/app/logout")
    assert not crawler.should_visit("https://app.example.test/app/logo.png")


def test_page_discovery_click_candidate_safety_keeps_navigation_only() -> None:
    crawler = PageDiscoveryCrawler(click_navigation=True)

    assert crawler._is_safe_click_candidate(
        {
            "visible": True,
            "disabled": False,
            "inside_form": False,
            "role": "menuitem",
            "tag": "button",
            "text": "Customers",
            "type": "",
            "href": "",
        }
    )
    assert not crawler._is_safe_click_candidate(
        {
            "visible": True,
            "disabled": False,
            "inside_form": False,
            "role": "",
            "tag": "button",
            "text": "Delete customer",
            "type": "button",
            "href": "",
        }
    )
