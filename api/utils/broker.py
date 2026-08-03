import os
import json
import aio_pika
from aio_pika.abc import AbstractChannel, AbstractConnection
from api.utils.logger import logger

RABBITMQ_URL = os.environ["RABBITMQ_URL"]
EXCHANGE_NAME = os.environ["RABBITMQ_EXCHANGE_NAME"]


class RabbitMQClient:
    """Client wrapper for publishing events to RabbitMQ."""

    def __init__(self):
        """Initialize the client with no active connection or channel."""
        self.connection: AbstractConnection | None = None
        self.channel: AbstractChannel | None = None
        self.exchange_name = EXCHANGE_NAME

    async def connect(self):
        """Connect to RabbitMQ and declare the event exchange if needed."""
        if not self.connection or self.connection.is_closed:
            logger.info("Connecting to RabbitMQ.")
            self.connection = await aio_pika.connect_robust(RABBITMQ_URL)
            self.channel = await self.connection.channel()

            self.exchange = await self.channel.declare_exchange(
                self.exchange_name,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            logger.info("Connected to RabbitMQ and exchange declared.")

    async def publish_message(self, routing_key: str, message: dict, trace_id: str):
        """Publish a JSON-encoded message to the configured RabbitMQ exchange.

        Args:
            routing_key (str): Routing key used to deliver the message.
            message (dict): Payload to publish.
            trace_id (str): Trace identifier added to the message headers.
        """
        if not self.exchange:
            await self.connect()
        message_body = json.dumps(message).encode("utf-8")

        await self.exchange.publish(
            aio_pika.Message(
                body=message_body,
                headers={"x-trace-id": trace_id},
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )
        logger.info(f"Message published with routing_key: {routing_key}")

    async def close(self):
        """Close the RabbitMQ connection when it is open."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()


rabbitmq_client = RabbitMQClient()


async def get_broker():
    """Return a connected RabbitMQ client instance.

    Returns:
        RabbitMQClient: The shared broker client ready for publishing.
    """
    await rabbitmq_client.connect()
    return rabbitmq_client
