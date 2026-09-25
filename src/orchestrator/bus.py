# src/orchestrator/bus.py
"""
Local In-Memory Message Bus for Multi-Agent Swarms.
Enables non-blocking asynchronous communication between edge micro-agents.
Operates with sub-millisecond latency and zero network overhead.
Language: STE (Simplified Technical English).
"""

import asyncio
from typing import Dict, List, Callable, Any, Optional
import time


class Message:
    """Standard message structure passed on the local bus."""
    def __init__(self, topic: str, payload: Any, sender: str = "anonymous"):
        self.topic = topic
        self.payload = payload
        self.sender = sender
        self.timestamp = time.time()


class LocalMessageBus:
    """
    Asynchronous event bus for local micro-agents.
    Provides publish/subscribe and request/response mechanisms without polling.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Message], Any]]] = {}
        self._response_futures: Dict[str, asyncio.Future] = {}

    def subscribe(self, topic: str, handler: Callable[[Message], Any]):
        """Subscribes an agent callback handler to a specific topic."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable[[Message], Any]):
        """Removes a subscribed handler from a topic."""
        if topic in self._subscribers and handler in self._subscribers[topic]:
            self._subscribers[topic].remove(handler)

    async def publish(self, topic: str, payload: Any, sender: str = "anonymous"):
        """
        Publishes an event to all subscribed handlers asynchronously.
        Executes callbacks without blocking the caller.
        """
        message = Message(topic=topic, payload=payload, sender=sender)
        handlers = self._subscribers.get(topic, [])
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                asyncio.create_task(handler(message))
            else:
                handler(message)

    async def request(self, topic: str, payload: Any, sender: str = "client", timeout: float = 2.0) -> Any:
        """
        Sends a request to a topic and waits asynchronously for a matching response.
        Uses request correlation IDs to eliminate polling.
        """
        correlation_id = f"{topic}_{time.time()}_{id(payload)}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._response_futures[correlation_id] = future

        request_payload = {
            "correlation_id": correlation_id,
            "data": payload
        }
        await self.publish(topic, request_payload, sender=sender)

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._response_futures.pop(correlation_id, None)
            raise TimeoutError(f"LocalMessageBus: Request to topic '{topic}' timed out after {timeout}s")

    async def reply(self, correlation_id: str, response_data: Any):
        """Resolves a pending request future using its correlation ID."""
        future = self._response_futures.pop(correlation_id, None)
        if future and not future.done():
            future.set_result(response_data)
