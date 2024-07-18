import os
from typing import Sequence

from jinja2 import Environment, FileSystemLoader, select_autoescape
from web3.types import EventData

from . import jinja2_ext


def init_environment(
    search_path: str | os.PathLike | Sequence[str | os.PathLike],
    env_globals: dict,
) -> Environment:
    env = Environment(
        loader=FileSystemLoader(search_path),
        autoescape=select_autoescape(),
    )
    env.globals.update(env_globals)
    jinja2_ext.add_filters(env)
    return env


def render(env: Environment, event: EventData, template_name: str):
    template = env.get_template(template_name)
    return template.render(evt=event)
