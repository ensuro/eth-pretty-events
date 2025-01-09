from unittest.mock import patch

import pytest
from jinja2 import Environment, FileSystemLoader

from eth_pretty_events.jinja2_ext import add_filters, add_tests
from eth_pretty_events.render import init_environment, render

from . import factories


def test_init_environment():
    search_path = "src/eth_pretty_events/templates/"
    env_globals = {
        "b32_rainbow": {"0xabc": "some_unhashed_value"},
        "chain_id": 137,
        "chains": {137: {"explorers": [{"url": "https://polygonscan.com"}]}},
    }

    with patch("eth_pretty_events.jinja2_ext.add_filters") as mock_add_filters:
        env = init_environment(search_path, env_globals)

        assert isinstance(env, Environment)

        assert isinstance(env.loader, FileSystemLoader)
        assert env.loader.searchpath == [search_path]

        assert env.globals["b32_rainbow"] == env_globals["b32_rainbow"]
        assert env.globals["chain_id"] == env_globals["chain_id"]

        mock_add_filters.assert_called_once_with(env)


def test_render_event():
    template_dir = "src/eth_pretty_events/templates/"
    template_name = "generic-event.md.j2"
    env_globals = {
        "b32_rainbow": {"0xabc": "some_unhashed_value"},
        "chain_id": 137,
        "chains": {137: {"explorers": [{"url": "https://polygonscan.com"}]}},
    }

    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
    env.globals.update(env_globals)
    add_filters(env)
    add_tests(env)
    transfer_event = factories.Event()

    result = render(env, transfer_event, template_name)

    assert "TX:" in result
    assert "Block:" in result
    assert "Contract:" in result
    assert "Arguments" in result
    assert "value:" in result


def test_render_uses_second_template_when_first_fails(caplog):
    template_dir = "src/eth_pretty_events/templates/"
    env_globals = {
        "b32_rainbow": {"0xabc": "some_unhashed_value"},
        "chain_id": 137,
        "chains": {137: {"explorers": [{"url": "https://polygonscan.com"}]}},
    }

    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
    env.globals.update(env_globals)
    add_filters(env)
    add_tests(env)

    transfer_event = factories.Event()
    generic_template = "generic-event.md.j2"
    on_error_template = "generic-event-on-error.md.j2"
    templates = [generic_template, on_error_template]

    with patch.object(
        env,
        "get_template",
        side_effect=lambda name: (
            Exception("Mocked failure") if name == generic_template else Environment.get_template(env, name)
        ),
    ), caplog.at_level("WARNING"):

        result = render(env, transfer_event, templates)

        assert result is not None

        assert (
            f"Failed to render tx: {transfer_event.tx}, log_index: {transfer_event.log_index} "
            f"with template '{generic_template}'" in caplog.text
        )


def test_render_raises_runtimeerror_on_all_templates_failure():
    template_dir = "src/eth_pretty_events/templates/"
    env_globals = {
        "b32_rainbow": {"0xabc": "some_unhashed_value"},
        "chain_id": 137,
        "chains": {137: {"explorers": [{"url": "https://polygonscan.com"}]}},
    }

    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
    env.globals.update(env_globals)
    add_filters(env)
    add_tests(env)

    transfer_event = factories.Event()

    generic_template = "generic-event.md.j2"
    on_error_template = "generic-event-on-error.md.j2"
    templates = [generic_template, on_error_template]

    with patch.object(env, "get_template", side_effect=Exception("Mocked failure")):
        with pytest.raises(RuntimeError) as exc_info:
            render(env, transfer_event, templates)

        assert f"Failed to render all provided templates: {templates}" in str(exc_info.value)
