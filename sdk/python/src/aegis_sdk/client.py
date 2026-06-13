"""Sync and async Aegis API clients."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx

from aegis_sdk.models import ResumeResponse, RunCreateResponse, RunStatusResponse


class AegisClient:
    """Synchronous Aegis API client."""

    def __init__(
        self,
        base_url: str = "http://localhost:8767",
        api_key: str = "",
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        kwargs: dict[str, Any] = {"base_url": base_url, "headers": headers}
        if transport is not None:
            kwargs["transport"] = transport
        self._client = httpx.Client(**kwargs)

    def create_run(
        self,
        messages: list[dict[str, str]],
        *,
        route: str = "default",
        background: bool = False,
        approvers: list[str] | None = None,
    ) -> RunCreateResponse:
        body = {
            "messages": messages,
            "route": route,
            "background": background,
            "approvers": approvers or [],
        }
        resp = self._client.post("/v1/runs", json=body)
        resp.raise_for_status()
        return RunCreateResponse(**resp.json())

    def get_run(self, run_id: str) -> RunStatusResponse:
        resp = self._client.get(f"/v1/runs/{run_id}")
        resp.raise_for_status()
        return RunStatusResponse(**resp.json())

    def resume_run(self, run_id: str, decision: str) -> ResumeResponse:
        resp = self._client.post(f"/v1/runs/{run_id}/resume", json={"decision": decision})
        resp.raise_for_status()
        return ResumeResponse(**resp.json())

    def list_runs(
        self,
        *,
        principal: str | None = None,
        route: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if principal:
            params["principal"] = principal
        if route:
            params["route"] = route
        if since:
            params["since"] = since
        resp = self._client.get("/v1/audit", params=params)
        resp.raise_for_status()
        result: list[dict[str, Any]] = resp.json()["runs"]
        return result

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "default",
    ) -> dict[str, Any]:
        body = {"model": model, "messages": messages, "stream": False}
        resp = self._client.post("/v1/chat/completions", json=body)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "default",
    ) -> Iterator[dict[str, Any]]:
        body = {"model": model, "messages": messages, "stream": True}
        with self._client.stream("POST", "/v1/chat/completions", json=body) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    yield json.loads(data)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AegisClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class AsyncAegisClient:
    """Asynchronous Aegis API client."""

    def __init__(
        self,
        base_url: str = "http://localhost:8767",
        api_key: str = "",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        kwargs: dict[str, Any] = {"base_url": base_url, "headers": headers}
        if transport is not None:
            kwargs["transport"] = transport
        self._client = httpx.AsyncClient(**kwargs)

    async def create_run(
        self,
        messages: list[dict[str, str]],
        *,
        route: str = "default",
        background: bool = False,
        approvers: list[str] | None = None,
    ) -> RunCreateResponse:
        body = {
            "messages": messages,
            "route": route,
            "background": background,
            "approvers": approvers or [],
        }
        resp = await self._client.post("/v1/runs", json=body)
        resp.raise_for_status()
        return RunCreateResponse(**resp.json())

    async def get_run(self, run_id: str) -> RunStatusResponse:
        resp = await self._client.get(f"/v1/runs/{run_id}")
        resp.raise_for_status()
        return RunStatusResponse(**resp.json())

    async def resume_run(self, run_id: str, decision: str) -> ResumeResponse:
        resp = await self._client.post(f"/v1/runs/{run_id}/resume", json={"decision": decision})
        resp.raise_for_status()
        return ResumeResponse(**resp.json())

    async def list_runs(
        self,
        *,
        principal: str | None = None,
        route: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if principal:
            params["principal"] = principal
        if route:
            params["route"] = route
        if since:
            params["since"] = since
        resp = await self._client.get("/v1/audit", params=params)
        resp.raise_for_status()
        result: list[dict[str, Any]] = resp.json()["runs"]
        return result

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "default",
    ) -> dict[str, Any]:
        body = {"model": model, "messages": messages, "stream": False}
        resp = await self._client.post("/v1/chat/completions", json=body)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "default",
    ) -> AsyncIterator[dict[str, Any]]:
        body = {"model": model, "messages": messages, "stream": True}
        async with self._client.stream("POST", "/v1/chat/completions", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    yield json.loads(data)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncAegisClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
