from data_agent.agent.scope_resolver import resolve_scope


def test_resolve_bkn_without_market_requires_clarification() -> None:
    resolution = resolve_scope("BKN 2026-07-14 销售额")

    assert resolution.ambiguous
    assert resolution.reason == "ambiguous_scope_alias"
    assert "US" in resolution.question
    assert "CA" in resolution.question
    assert "beekeeper_us" in resolution.scopes
    assert "beekeeper_ca" in resolution.scopes


def test_resolve_bkn_us_to_us_scopes() -> None:
    resolution = resolve_scope("BKN US 2026-07-14 销售额")

    assert resolution.resolved
    assert resolution.market == "US"
    assert "beekeeper_us" in resolution.scopes
    assert "beekeeper_ca" not in resolution.scopes
    assert "intermediate_amazon_3p_orders_beekeeper_us_view" in resolution.tables


def test_resolve_bkn_ca_to_ca_scope() -> None:
    resolution = resolve_scope("bkn ca 2026-07-14 广告花费")

    assert resolution.resolved
    assert resolution.market == "CA"
    assert resolution.scopes == ("beekeeper_ca",)
    assert "intermediate_amazon_ams_campaigns_beekeeper_ca_view" in resolution.tables


def test_short_alias_requires_token_boundary() -> None:
    resolution = resolve_scope("这个 notebook 2026-07-14 销售额")

    assert resolution.status == "none"
