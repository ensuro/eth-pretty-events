from unittest.mock import patch

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
    assert "Value:" in result