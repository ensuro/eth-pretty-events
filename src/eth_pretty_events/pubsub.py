import asyncio
import json
import logging
from urllib.parse import ParseResult, parse_qs

from google.cloud import pubsub_v1
from web3._utils.encoding import Web3JsonEncoder

from .outputs import DecodedTxLogs, OutputBase

_logger = logging.getLogger(__name__)


@OutputBase.register("pubsubrawlogs")
class PubSubRawLogsOutput(OutputBase):
    def __init__(self, queue: asyncio.Queue, url: ParseResult, renv):
        super().__init__(queue, url)

        query_params = parse_qs(url.query)
        dry_run = query_params.get("dry_run", ["false"])[0].lower() == "true"
        self.project_id = query_params.get("project_id", [None])[0]
        self.topic = query_params.get("topic", [None])[0]

        if not self.project_id or not self.topic:
            raise RuntimeError("Both 'project_id' and 'topic' must be specified in the query string")

        if dry_run:
            _logger.info("Dry run mode activated.")
            self.publisher = PrintToScreenPublisher(self.project_id, self.topic)
            self.topic_path = f"projects/{self.project_id}/topics/{self.topic}"
        else:
            _logger.info("Production mode activated. Using Pub/Sub PublisherClient.")
            self.publisher = pubsub_v1.PublisherClient()
            self.topic_path = self.publisher.topic_path(self.project_id, self.topic)

    async def send_to_output(self, log: DecodedTxLogs):
        try:
            message = {
                "transactionHash": log.tx.hash,
                "blockHash": log.tx.block.hash,
                "blockNumber": log.tx.block.number,
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
            formatted_message = json.dumps(message, cls=Web3JsonEncoder, indent=2)

            publish = self.publisher.publish(self.topic_path, formatted_message.encode("utf-8"))
            message_id = publish.result()
            _logger.info(f"Published raw_log message to Pub/Sub with ID: {message_id}")
        except Exception as e:
            _logger.error(f"Failed to publish raw_log message: {e}")


class PrintToScreenPublisher:
    def __init__(self, project_id, topic):
        self.project_id = project_id
        self.topic = topic

    def publish(self, topic_path, message):
        _logger.info(f"[Dry Run] Publishing to {topic_path}:")
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
