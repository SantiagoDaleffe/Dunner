import asyncio
import os
import json
import logging
import aio_pika

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

RABBITMQ_URL = os.environ["RABBITMQ_URL"]
QUEUE_NAME = os.environ["RABBITMQ_QUEUE_NAME"]
EXCHANGE_NAME = os.environ["RABBITMQ_EXCHANGE_NAME"]
ROUTING_KEY = os.environ["RABBITMQ_ROUTING_KEY"]


async def process_message(message: aio_pika.abc.AbstractIncomingMessage):
    """Process a message from the RabbitMQ queue.

    Args:
        message (aio_pika.abc.AbstractIncomingMessage): The incoming RabbitMQ message to process.
    """
    async with message.process(ignore_processed=True):
        payload = json.loads(message.body.decode())
        trace_id = message.headers.get("x-trace-id", "unknown")
        event_id = payload.get("event_id")

        logger.info(
            f"[Trace: {trace_id}] Processing event {event_id} for tenant {payload.get('tenant_id')}"
        )

        try:
            logger.info(f"[Trace: {trace_id}] Event {event_id} processed successfully.")
            await message.ack()

        except Exception as e:
            logger.error(
                f"[Trace: {trace_id}] Error processing event {event_id}: {str(e)}"
            )
            await message.reject(requeue=False)


async def main():
    """Start the RabbitMQ worker, declare exchange and queue, and consume messages."""
    logger.info("Worker starting up and connecting to RabbitMQ.")

    connection = await aio_pika.connect_robust(RABBITMQ_URL)

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True
        )

        queue = await channel.declare_queue(QUEUE_NAME, durable=True)

        await queue.bind(exchange, routing_key=ROUTING_KEY)

        logger.info(f"Worker listening on queue '{QUEUE_NAME}'.")

        await queue.consume(process_message)

        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped manually.")
