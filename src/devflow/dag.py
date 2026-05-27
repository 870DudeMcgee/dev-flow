import os
from typing import Dict, List, Set, Tuple, Any, Optional
from devflow.manager import parse_task_file

class TaskDAG:
    def __init__(self, tasks: List[Dict[str, Any]], root_dir: str = "."):
        self.root_dir = root_dir
        # Store tasks as a dictionary for easy lookup: id -> task_dict
        self.tasks = {str(t["id"]): dict(t) for t in tasks}
        self.dependencies: Dict[str, List[str]] = {
            str(t["id"]): [str(dep) for dep in t.get("depends_on", [])]
            for t in tasks
        }
        
        # Cycle detection
        self._validate_acyclic()
        
        # Load statuses from filesystem
        self._sync_with_filesystem()

    def _validate_acyclic(self) -> None:
        """Validates that the task dependencies do not contain cycles using DFS."""
        visited: Dict[str, int] = {}  # 0 = unvisited, 1 = visiting, 2 = visited
        
        def dfs(node: str) -> None:
            visited[node] = 1
            for neighbor in self.dependencies.get(node, []):
                # If neighbor is not in self.tasks, ignore cycle check for it
                if neighbor not in self.tasks:
                    continue
                state = visited.get(neighbor, 0)
                if state == 1:
                    raise ValueError(f"Dependency cycle detected: circular path involves task '{node}' -> '{neighbor}'.")
                elif state == 0:
                    dfs(neighbor)
            visited[node] = 2

        for task_id in self.tasks:
            if visited.get(task_id, 0) == 0:
                dfs(task_id)

    def _sync_with_filesystem(self) -> None:
        """Overwrites planned task status and other properties with live task md file values."""
        tasks_dir = os.path.join(self.root_dir, ".devflow", "tasks")
        if not os.path.isdir(tasks_dir):
            return

        for filename in os.listdir(tasks_dir):
            if not filename.endswith(".md"):
                continue
            path = os.path.join(tasks_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    content = handle.read()
                parsed = parse_task_file(content)
                task_id = str(parsed.get("task_id", ""))
                if task_id in self.tasks:
                    # Update status, assigned agent, owner lock, branch, etc.
                    self.tasks[task_id]["status"] = str(parsed.get("status", "PENDING")).upper()
                    if parsed.get("assigned_agent"):
                        self.tasks[task_id]["assigned_agent"] = parsed.get("assigned_agent")
                    if parsed.get("owner_lock"):
                        self.tasks[task_id]["owner_lock"] = parsed.get("owner_lock")
                    if parsed.get("branch"):
                        self.tasks[task_id]["branch"] = parsed.get("branch")
                    if parsed.get("verification_commands"):
                        self.tasks[task_id]["verification"] = parsed.get("verification_commands")
            except Exception:
                pass

    def get_status(self, task_id: str) -> str:
        task_id = str(task_id)
        if task_id in self.tasks:
            return self.tasks[task_id].get("status", "PENDING")
        return "PENDING"

    def update_task_status(self, task_id: str, status: str) -> None:
        task_id = str(task_id)
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = status.upper()

    def get_ready_tasks(self, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns all dependency-ready tasks:
        - Status is not COMPLETED/FAILED/BLOCKED
        - All dependencies are COMPLETED
        """
        ready_tasks = []
        for task_id, task in self.tasks.items():
            status = task.get("status", "PENDING").upper()
            if status in ("COMPLETED", "FAILED", "BLOCKED"):
                continue
            
            # Check dependencies
            deps = self.dependencies.get(task_id, [])
            deps_completed = True
            for dep in deps:
                dep_status = self.get_status(dep)
                if dep_status != "COMPLETED":
                    deps_completed = False
                    break
            
            if deps_completed:
                assigned = task.get("assigned_agent", "")
                if agent:
                    if assigned and assigned.lower() != agent.lower():
                        continue
                ready_tasks.append(task)
                
        return ready_tasks

    def get_blocked_tasks(self) -> List[Dict[str, Any]]:
        """
        Returns tasks that are blocked because one or more of their dependencies failed or is blocked.
        """
        blocked_tasks = []
        for task_id, task in self.tasks.items():
            status = task.get("status", "PENDING").upper()
            if status in ("COMPLETED", "FAILED", "BLOCKED"):
                continue
            
            def is_dep_blocked(dep_id: str) -> bool:
                dep_status = self.get_status(dep_id)
                if dep_status in ("FAILED", "BLOCKED"):
                    return True
                for sub_dep in self.dependencies.get(dep_id, []):
                    if is_dep_blocked(sub_dep):
                        return True
                return False
                
            deps = self.dependencies.get(task_id, [])
            blocked = False
            for dep in deps:
                if is_dep_blocked(dep):
                    blocked = True
                    break
            
            if blocked:
                blocked_tasks.append(task)
                
        return blocked_tasks

    def get_next_task(self, agent: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Selects the single next ready task to work on.
        Prioritizes tasks assigned to the agent, then unassigned tasks if no direct match is found.
        """
        ready = self.get_ready_tasks(agent=agent)
        if not ready:
            return None
        
        if agent:
            for t in ready:
                assigned = t.get("assigned_agent", "")
                if assigned and assigned.lower() == agent.lower():
                    return t
        
        for t in ready:
            assigned = t.get("assigned_agent", "")
            if not assigned:
                return t
                
        return ready[0]

    def get_graph_structure(self) -> Dict[str, List[str]]:
        return self.dependencies
