"""Project reproduction config: validation, secret refusal, and readiness.

The security-critical test in this file is ``TestSecretRefusal``: this config is read back by
the dashboard and compiled into test files, so a stored credential would leak twice. The
module must refuse rather than store.
"""
import pytest

from stepstitch_service.repro_config import (
    DEFAULT_VALUES,
    ReproConfig,
    ReproConfigError,
    endpoint_match_regex,
    infer_input_kind,
    readiness,
    route_params_in,
    synthetic_value,
)


def _nav(route):
    return {"type": "navigation", "route": route}


def _input(target):
    return {"type": "input", "route": "/checkout", "target": target}


class TestValidation:
    def test_empty_config_is_valid_and_empty(self):
        cfg = ReproConfig.from_dict(None)
        assert cfg.is_empty()
        assert cfg.base_url is None
        assert ReproConfig.from_dict({}).is_empty()

    def test_full_config_round_trips(self):
        doc = {
            "base_url": "https://staging.example.test/",
            "auth": {"fixture": "tests/auth.setup.ts", "env_vars": ["E2E_USER_EMAIL"]},
            "route_params": {"id": "1001"},
            "input_values": {"by_selector": {"#amount": "10.00"}, "by_type": {"email": "a@b.test"}},
            "api_overrides": {"/api/x/:id": {"match_regex": "/api/x/[^/]+$"}},
            "verify_workflow_url": "https://github.com/o/r/actions/workflows/s.yml",
        }
        cfg = ReproConfig.from_dict(doc)
        # base_url is normalised (trailing slash stripped), everything else survives.
        assert cfg.base_url == "https://staging.example.test"
        assert cfg.auth.fixture == "tests/auth.setup.ts"
        assert cfg.route_params == {"id": "1001"}
        assert ReproConfig.from_dict(cfg.as_dict()).as_dict() == cfg.as_dict()

    def test_unknown_setting_names_the_supported_ones(self):
        with pytest.raises(ReproConfigError) as exc:
            ReproConfig.from_dict({"basurl": "https://x.test"})
        assert "basurl" in str(exc.value) and "base_url" in str(exc.value)

    def test_base_url_must_be_http_and_says_so(self):
        with pytest.raises(ReproConfigError) as exc:
            ReproConfig.from_dict({"base_url": "staging.example.test"})
        message = str(exc.value)
        assert "http://" in message and "example" in message

    def test_route_param_type_error_shows_an_example(self):
        with pytest.raises(ReproConfigError) as exc:
            ReproConfig.from_dict({"route_params": {"id": ["1001"]}})
        assert "route_params.id" in str(exc.value) and '"id": "1001"' in str(exc.value)

    def test_invalid_api_override_regex_is_rejected(self):
        with pytest.raises(ReproConfigError) as exc:
            ReproConfig.from_dict({"api_overrides": {"/a": {"match_regex": "([unclosed"}}})
        assert "not a valid regex" in str(exc.value)

    def test_api_override_requires_match_regex(self):
        with pytest.raises(ReproConfigError):
            ReproConfig.from_dict({"api_overrides": {"/a": {"regex": "x"}}})

    def test_unknown_input_values_key_is_rejected(self):
        with pytest.raises(ReproConfigError) as exc:
            ReproConfig.from_dict({"input_values": {"by_name": {"a": "b"}}})
        assert "by_selector" in str(exc.value)


class TestSecretRefusal:
    """Config must refuse credentials rather than store them."""

    @pytest.mark.parametrize("doc", [
        {"route_params": {"api_key": "abc123"}},
        {"route_params": {"session_token": "abc123"}},
        {"input_values": {"by_selector": {"#login-password": "hunter2"}}},
        {"input_values": {"by_type": {"password": "hunter2"}}},
    ])
    def test_secret_named_keys_are_refused(self, doc):
        with pytest.raises(ReproConfigError) as exc:
            ReproConfig.from_dict(doc)
        assert "never stores credentials" in str(exc.value)
        assert "env var NAME" in str(exc.value)

    @pytest.mark.parametrize("value", [
        "ssa_AAAAAAAAAAAAAAAAAAAAAAAA",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig",
        "Bearer sk-live-abcdefghijklmnop",
        "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "-----BEGIN RSA PRIVATE KEY-----",
    ])
    def test_secret_shaped_values_are_refused_under_innocent_keys(self, value):
        with pytest.raises(ReproConfigError) as exc:
            ReproConfig.from_dict({"route_params": {"id": value}})
        assert "never stores credentials" in str(exc.value)

    def test_env_var_names_are_allowed_even_when_they_say_password(self):
        cfg = ReproConfig.from_dict(
            {"auth": {"fixture": "tests/auth.setup.ts", "env_vars": ["E2E_USER_PASSWORD"]}}
        )
        assert cfg.auth.env_vars == ("E2E_USER_PASSWORD",)

    def test_an_env_var_VALUE_in_the_names_list_is_refused(self):
        with pytest.raises(ReproConfigError) as exc:
            ReproConfig.from_dict({"auth": {"env_vars": ["hunter2!@#"]}})
        assert "not an env var name" in str(exc.value)


class TestSyntheticValues:
    @pytest.mark.parametrize("selector,kind", [
        ("[data-testid=contact-email]", "email"),
        ("#login-password", "password"),
        ("[data-testid=transfer-amount]", "number"),
        ("#phone", "tel"),
        ("#dob", "date"),
        ("#site-url", "url"),
        ("[data-testid=recipient]", "text"),
    ])
    def test_kind_is_inferred_from_the_structural_selector(self, selector, kind):
        assert infer_input_kind(selector) == kind

    def test_defaults_are_obviously_synthetic(self):
        placeholders = ("1", "555-0100", "2024-01-15")
        for value in DEFAULT_VALUES.values():
            assert (
                "example.test" in value
                or "stepstitch-test" in value
                or value in placeholders
            ), f"{value!r} could be mistaken for real data"

    def test_password_fields_never_get_a_guessed_literal(self):
        value, kind = synthetic_value("#login-password", None)
        assert kind == "password" and value is None

    def test_precedence_is_selector_then_kind_then_default(self):
        cfg = ReproConfig.from_dict({
            "input_values": {"by_selector": {"#amount": "42"}, "by_type": {"number": "7"}}
        })
        assert synthetic_value("#amount", cfg)[0] == "42"
        assert synthetic_value("#other-amount", cfg)[0] == "7"
        assert synthetic_value("[data-testid=name]", cfg)[0] == DEFAULT_VALUES["text"]


class TestEndpointMatching:
    def test_templated_endpoint_becomes_an_anchored_regex(self):
        assert endpoint_match_regex("/api/accounts/:id/transfers") == \
            "/api/accounts/[^/]+/transfers$"

    def test_anchoring_stops_a_sibling_endpoint_binding_the_wait(self):
        import re as _re
        pattern = _re.compile(endpoint_match_regex("/api/accounts/:id/transfers"))
        assert pattern.search("https://app.test/api/accounts/123/transfers")
        # The old prefix match ("/api/accounts/") matched this too — that was the bug.
        assert not pattern.search("https://app.test/api/accounts/123/statements")

    def test_a_leaked_origin_is_stripped(self):
        assert endpoint_match_regex("https://app.test/api/x") == "/api/x$"

    def test_operator_override_wins(self):
        cfg = ReproConfig.from_dict(
            {"api_overrides": {"/api/x/:id": {"match_regex": "custom$"}}}
        )
        assert endpoint_match_regex("/api/x/:id", cfg) == "custom$"

    def test_empty_endpoint_has_no_matcher(self):
        assert endpoint_match_regex("") is None


class TestReadiness:
    def test_route_params_are_collected_in_first_seen_order(self):
        steps = [_nav("/a/:id"), _nav("/b/:orgId/c/:id")]
        assert route_params_in(steps) == ["id", "orgId"]

    def test_unconfigured_trace_reports_what_to_set(self):
        items = {i["id"]: i for i in readiness(None, [_nav("/accounts/:id")])}
        assert items["base_url"]["ready"] is False
        assert "localhost:3000" in items["base_url"]["detail"]
        assert items["route_params"]["ready"] is False
        assert "':id'" in items["route_params"]["detail"]
        assert items["auth"]["ready"] is False

    def test_configured_trace_reports_ready(self):
        cfg = ReproConfig.from_dict({
            "base_url": "https://staging.example.test",
            "auth": {"fixture": "tests/auth.setup.ts"},
            "route_params": {"id": "1001"},
        })
        items = {i["id"]: i for i in readiness(cfg, [_nav("/accounts/:id")])}
        assert items["base_url"]["ready"] and items["route_params"]["ready"]
        assert items["auth"]["ready"] and "tests/auth.setup.ts" in items["auth"]["detail"]

    def test_env_base_url_counts_as_ready_without_stored_config(self):
        items = {i["id"]: i for i in readiness(
            None, [_nav("/a")], fallback_base_url="https://env.example.test")}
        assert items["base_url"]["ready"] is True

    def test_password_field_makes_inputs_not_ready(self):
        items = {i["id"]: i for i in readiness(None, [_input("#login-password")])}
        assert items["input_values"]["ready"] is False
        assert "#login-password" in items["input_values"]["detail"]

    def test_traces_without_inputs_or_params_omit_those_items(self):
        ids = {i["id"] for i in readiness(None, [_nav("/")])}
        assert ids == {"base_url", "auth"}
