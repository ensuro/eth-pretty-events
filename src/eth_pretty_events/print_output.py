import logging
import sys
from urllib.parse import parse_qs

from .event_filter import find_template
from .outputs import DecodedTxLogs, OutputBase
from .render import render

_logger = logging.getLogger(__name__)


@OutputBase.register("print")
class PrintOutput(OutputBase):
    def __init__(self, url, renv):
        super().__init__(url)
        query_params = parse_qs(url.query)
        self.filename = query_params.get("file", [None])[0]
        self.output_file = open(self.filename, "w") if self.filename else sys.stdout
        self.renv = renv

    def send_to_output_sync(self, log: DecodedTxLogs):
        for event in log.decoded_logs:
            if event is None:
                _logger.warning(f"Unrecognized event tried to be rendered in tx: {log.tx}.")
                return
            template_name = find_template(self.renv.template_rules, event)
            rendered_event = render(self.renv.jinja_env, event, [template_name, self.renv.args.on_error_template])

            print(rendered_event, file=self.output_file)
            print("--------------------------", file=self.output_file)
