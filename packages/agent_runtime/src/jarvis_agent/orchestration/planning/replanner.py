"""Dynamic replanner generating versioned PlanDAGs and PlanDiffs."""

from __future__ import annotations

import datetime
import uuid

from jarvis_agent.orchestration.models import (
    NodeStatus,
    PlanDAG,
    PlanDiff,
    PlanNode,
    PlanRevision,
)


class Replanner:
    """Dynamic replanner that adapts PlanDAGs to failures while preserving completed work."""

    def replan(
        self,
        current_plan: PlanDAG,
        failed_node_id: str,
        reason: str,
        substitute_nodes: list[PlanNode] | None = None,
    ) -> tuple[PlanDAG, PlanDiff, PlanRevision]:
        """Generate a revised PlanDAG version, preserving verified completed nodes."""
        preserved_completed: list[str] = []
        for nid, node in current_plan.nodes.items():
            if node.status == NodeStatus.COMPLETED:
                preserved_completed.append(nid)

        new_revision_num = current_plan.revision + 1
        new_nodes: dict[str, PlanNode] = {}

        # 1. Carry over completed nodes intact
        for nid in preserved_completed:
            new_nodes[nid] = current_plan.nodes[nid]

        added_nodes = list(substitute_nodes or [])
        modified_node_ids: list[str] = []
        removed_node_ids: list[str] = []

        if added_nodes:
            # Substitute nodes replace the failed node
            removed_node_ids.append(failed_node_id)
            for sub_node in added_nodes:
                new_nodes[sub_node.node_id] = sub_node

            # Update remaining downstream nodes to depend on new substitute nodes if needed
            sub_ids = [s.node_id for s in added_nodes]
            for nid, node in current_plan.nodes.items():
                if nid in preserved_completed or nid == failed_node_id:
                    continue
                if failed_node_id in node.dependencies:
                    new_deps = [dep for dep in node.dependencies if dep != failed_node_id] + sub_ids
                    new_nodes[nid] = PlanNode.from_dict(
                        {**node.to_dict(), "dependencies": new_deps}
                    )
                    modified_node_ids.append(nid)
                else:
                    new_nodes[nid] = node
        else:
            # No substitutes: reset failed node attempt for a fresh retry approach
            failed_node = current_plan.nodes.get(failed_node_id)
            if failed_node:
                reset_node = PlanNode.from_dict(
                    {
                        **failed_node.to_dict(),
                        "status": NodeStatus.PENDING.value,
                        "error_message": f"Replanned: {reason}",
                    }
                )
                new_nodes[failed_node_id] = reset_node
                modified_node_ids.append(failed_node_id)

            # Retain other pending nodes
            for nid, node in current_plan.nodes.items():
                if nid != failed_node_id and nid not in preserved_completed:
                    new_nodes[nid] = node

        new_plan = PlanDAG(
            plan_id=current_plan.plan_id,
            task_id=current_plan.task_id,
            revision=new_revision_num,
            nodes=new_nodes,
        )

        diff = PlanDiff(
            previous_revision=current_plan.revision,
            new_revision=new_revision_num,
            added_nodes=added_nodes,
            modified_node_ids=modified_node_ids,
            removed_node_ids=removed_node_ids,
            preserved_completed_node_ids=preserved_completed,
            reason=reason,
        )

        revision_record = PlanRevision(
            revision_id=f"rev_{uuid.uuid4().hex[:12]}",
            plan_id=current_plan.plan_id,
            task_id=current_plan.task_id,
            revision=new_revision_num,
            plan_hash=new_plan.compute_plan_hash(),
            diff=diff,
            created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        return new_plan, diff, revision_record


__all__ = ["Replanner"]
