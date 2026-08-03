import json
import logging
from urllib.parse import ParseResult, parse_qs

from google.cloud import pubsub_v1
from web3._utils.encoding import Web3JsonEncoder

from .outputs import DecodedTxLogs, OutputBase
from .types import DecodeEventError

_logger = logging.getLogger(__name__)


class PubSubOutputBase(OutputBase):
    def __init__(self, url: ParseResult, renv):
        super().__init__(url)
        self.renv = renv

        query_params = parse_qs(url.query)
        self.dry_run = query_params.get("dry_run", ["false"])[0].lower() == "true"
        self.project_id = query_params.get("project_id", [None])[0]
        self.topic = query_params.get("topic", [None])[0]

        if not self.project_id or not self.topic:
            raise RuntimeError("Both 'project_id' and 'topic' must be specified in the query string")

        if self.dry_run:
            _logger.info("Dry run mode activated.")
            self.publisher = PrintToScreenPublisher(self.project_id, self.topic)
            self.topic_path = f"projects/{self.project_id}/topics/{self.topic}"
        else:
            _logger.info("Production mode activated. Using Pub/Sub PublisherClient.")
            self.publisher = pubsub_v1.PublisherClient()
            self.topic_path = self.publisher.topic_path(self.project_id, self.topic)

    def _matching_tags(self, log: DecodedTxLogs) -> set:
        """Tags (from renv.template_rules) of every rule that matches at least one
        decoded event in this tx - regardless of this output's own `tags=` config, so
        that a single publish can carry all of them as attributes and let each Pub/Sub
        subscription filter for the ones it cares about."""
        matched = set()
        for rule in (x for x in self.renv.template_rules if x.tags):
            if any(event is not None and rule.match.filter(event) for event in log.decoded_logs):
                matched.update(rule.tags)
        return matched

    def publish_message(self, message, attributes: dict = None):
        formatted_message = json.dumps(message, cls=Web3JsonEncoder)
        publish = self.publisher.publish(self.topic_path, formatted_message.encode("utf-8"), **(attributes or {}))
        message_id = publish.result()
        _logger.info(f"Published message to Pub/Sub with ID: {message_id}")


@OutputBase.register("pubsubrawlogs")
class PubSubRawLogsOutput(PubSubOutputBase):
    def send_to_output_sync(self, log: DecodedTxLogs):
        message = {
            "transactionHash": log.tx.hash,
            "blockHash": log.tx.block.hash,
            "blockNumber": log.tx.block.number,
            "blockTimestamp": log.tx.block.timestamp,
            "chainId": log.tx.block.chain.id,
            "transactionIndex": log.tx.index,
            "logs": [
                {
                    "address": raw_log["address"],
                    "topics": raw_log["topics"],
                    "data": raw_log["data"],
                    "logIndex": raw_log["logIndex"],
                }
                for raw_log in log.raw_logs
            ],
        }
        attributes = {f"tag_{tag}": "true" for tag in self._matching_tags(log)}
        self.publish_message(message, attributes=attributes)


@OutputBase.register("pubsubdecodedlogs")
class PubSubDecodedLogsOutput(PubSubOutputBase):
    def send_to_output_sync(self, log: DecodedTxLogs):
        message = {
            "transactionHash": log.tx.hash,
            "blockHash": log.tx.block.hash,
            "blockNumber": log.tx.block.number,
            "blockTimestamp": log.tx.block.timestamp,
            "chainId": log.tx.block.chain.id,
            "transactionIndex": log.tx.index,
            "decodedLogs": [
                {
                    "name": decoded_log.name,
                    "address": decoded_log.address,
                    "logIndex": decoded_log.log_index,
                    "args": decoded_log.args._asdict() if decoded_log.args else {},
                    "abi": decoded_log.args._components,
                }
                for decoded_log in log.decoded_logs
                if decoded_log and not isinstance(decoded_log, DecodeEventError)
            ],
        }
        attributes = {f"tag_{tag}": "true" for tag in self._matching_tags(log)}
        self.publish_message(message, attributes=attributes)


class PrintToScreenPublisher:
    def __init__(self, project_id, topic):
        self.project_id = project_id
        self.topic = topic

    def publish(self, topic_path, message, **attributes):
        _logger.info(f"[Dry Run] Publishing to {topic_path}:")
        if attributes:
            _logger.info(f"Attributes: {attributes}")
        if isinstance(message, bytes):
            try:
                decoded_message = json.loads(message.decode("utf-8"))
                _logger.info(json.dumps(decoded_message, indent=2))
            except json.JSONDecodeError:
                _logger.error("Failed to decode message.")
                _logger.info(message)
        else:
            _logger.info(message)
        return DryRunFuture()


class DryRunFuture:
    def result(self):
        return "dry-run-message-id"
