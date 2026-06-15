"""GitHubBridge — orchestrates the Repair Loop write side.

Idempotent per trace (keyed by trace_id) via a dict-like store, exactly like
``delivery.DeliveryService``. Never merges.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..integrations.base import TraceSummary
from .client import GitHubClient
from .content import (
    LABEL_BASE,
    LABEL_FIX_CANDIDATE,
    branch_name,
    build_body,
    build_issue,
    regression_test_path,
)


@dataclass(frozen=True)
class BridgeReceipt:
    trace_id: str
    issue_number: Optional[int] = None
    pr_number: Optional[int] = None
    branch: Optional[str] = None
    labels: Optional[List[str]] = None
    deduped: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "issue_number": self.issue_number,
            "pr_number": self.pr_number,
            "branch": self.branch,
            "labels": self.labels,
            "deduped": self.deduped,
        }


class GitHubBridge:
    def __init__(
        self,
        client: GitHubClient,
        *,
        base_branch: str = "main",
        idempotency_store: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self._client = client
        self._base = base_branch
        self._store: Dict[str, Dict[str, Any]] = (
            {} if idempotency_store is None else idempotency_store
        )

    def _cached(self, key: str) -> Optional[BridgeReceipt]:
        raw = self._store.get(key)
        if raw is None:
            return None
        data = dict(raw)
        data["deduped"] = True
        return BridgeReceipt(**data)

    async def create_issue(self, summary: TraceSummary) -> BridgeReceipt:
        key = f"issue:{summary.trace_id}"
        hit = self._cached(key)
        if hit is not None:
            return hit
        content = build_issue(summary)
        for label in content.labels:
            await self._client.ensure_label(label)
        issue = await self._client.create_issue(
            content.title, content.body, content.labels
        )
        receipt = BridgeReceipt(
            trace_id=summary.trace_id,
            issue_number=issue["number"],
            labels=content.labels,
        )
        self._store[key] = receipt.as_dict()
        return receipt

    async def open_regression_pr(
        self, summary: TraceSummary, repro_code: str
    ) -> BridgeReceipt:
        key = f"pr:{summary.trace_id}"
        hit = self._cached(key)
        if hit is not None:
            return hit
        branch = branch_name(summary.trace_id)
        sha = await self._client.default_branch_sha(self._base)
        await self._client.create_branch(branch, sha)
        await self._client.put_file(
            branch,
            regression_test_path(summary.trace_id),
            repro_code,
            f"test: add StepStitch regression for {summary.trace_id}",
        )
        pr = await self._client.open_pull_request(
            branch,
            self._base,
            f"[StepStitch] regression + repro for {summary.route}",
            build_body(summary),
        )
        receipt = BridgeReceipt(
            trace_id=summary.trace_id,
            pr_number=pr["number"],
            branch=branch,
            labels=[LABEL_BASE, LABEL_FIX_CANDIDATE],
        )
        self._store[key] = receipt.as_dict()
        return receipt
