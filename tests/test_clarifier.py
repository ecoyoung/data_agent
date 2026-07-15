from data_agent.agent.clarifier import needs_clarification


def assert_needs_clarification(text: str, expected_reason: str) -> None:
    clarification = needs_clarification(text)

    assert clarification.needed is True
    assert clarification.reason == expected_reason
    assert clarification.question


def test_clarifier_requires_time_for_sales_questions() -> None:
    assert_needs_clarification("看一下销售额", "missing_time_range")


def test_clarifier_allows_generic_sales_after_time_is_present() -> None:
    clarification = needs_clarification("看一下 2026年7月 销售额")

    assert clarification.needed is False


def test_clarifier_allows_explicit_business_report_sales() -> None:
    clarification = needs_clarification("看 2026年7月 Business Report 销售额和 sessions")

    assert clarification.needed is False


def test_clarifier_asks_ad_scope() -> None:
    assert_needs_clarification("看一下 2026年7月 广告效果", "ambiguous_ad_scope")


def test_clarifier_allows_explicit_sp_ads() -> None:
    clarification = needs_clarification("看一下 2026年7月 SP campaign ACoS 和 ROAS")

    assert clarification.needed is False


def test_clarifier_asks_inventory_scope() -> None:
    assert_needs_clarification("库存有没有风险", "ambiguous_inventory_scope")


def test_clarifier_allows_replenishment_inventory_question() -> None:
    clarification = needs_clarification("哪些 SKU 需要补货，days of supply 低于 14 天")

    assert clarification.needed is False


def test_clarifier_requires_product_identifier_for_this_asin() -> None:
    assert_needs_clarification("这个 ASIN 表现怎么样", "missing_product_identifier")


def test_clarifier_uses_history_for_product_identifier() -> None:
    clarification = needs_clarification(
        "这个 ASIN 表现怎么样",
        [{"role": "user", "content": "先看 B012345678 的情况"}],
    )

    assert clarification.needed is False
