from scripts.profile_intermediate_field_values import should_enumerate_column


def test_should_not_enumerate_high_cardinality_business_keys() -> None:
    excluded = [
        "asin",
        "advertised_asin",
        "sku",
        "campaign_id",
        "campaign_name",
        "search_term",
        "targeting",
        "product_name",
    ]

    for column in excluded:
        should_enum, reason = should_enumerate_column(column, "text")
        assert not should_enum, column
        assert reason == "high-cardinality business key"


def test_should_enumerate_low_cardinality_dimension_fields() -> None:
    included = [
        "brand",
        "country_code",
        "ams_type",
        "report_type",
        "order_status",
        "placement_classification",
    ]

    for column in included:
        should_enum, _ = should_enumerate_column(column, "character varying")
        assert should_enum, column


def test_should_not_enumerate_dates_or_metrics() -> None:
    assert should_enumerate_column("report_date", "date")[0] is False
    assert should_enumerate_column("ordered_revenue", "numeric")[0] is False
