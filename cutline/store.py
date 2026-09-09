from __future__ import annotations

import threading
from copy import deepcopy
from typing import Protocol

from cutline.domain import DomainError, Mutation, Project, commit_mutation


class ProjectStore(Protocol):
    def create(self, project: Project) -> Project: ...

    def get(self, owner_hash: str, project_id: str) -> Project: ...

    def count(self, owner_hash: str) -> int: ...

    def mutate(
        self,
        owner_hash: str,
        project_id: str,
        expected_revision: int,
        mutation: Mutation,
    ) -> Project: ...

    def delete(self, owner_hash: str, project_id: str) -> None: ...

    def ready(self) -> bool: ...


class MemoryProjectStore:
    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}
        self._lock = threading.RLock()

    def create(self, project: Project) -> Project:
        with self._lock:
            self._projects[project["id"]] = deepcopy(project)
            return deepcopy(project)

    def get(self, owner_hash: str, project_id: str) -> Project:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None or project["owner_hash"] != owner_hash:
                raise DomainError("NOT_FOUND", "Project not found.", 404)
            return deepcopy(project)

    def count(self, owner_hash: str) -> int:
        with self._lock:
            return sum(1 for project in self._projects.values() if project["owner_hash"] == owner_hash)

    def mutate(
        self,
        owner_hash: str,
        project_id: str,
        expected_revision: int,
        mutation: Mutation,
    ) -> Project:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None or project["owner_hash"] != owner_hash:
                raise DomainError("NOT_FOUND", "Project not found.", 404)
            if project["revision"] != expected_revision:
                raise DomainError("REVISION_CONFLICT", "Reload the current revision and retry.", 409)
            updated = deepcopy(project)
            commit_mutation(updated, mutation)
            self._projects[project_id] = updated
            return deepcopy(updated)

    def delete(self, owner_hash: str, project_id: str) -> None:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None or project["owner_hash"] != owner_hash:
                raise DomainError("NOT_FOUND", "Project not found.", 404)
            del self._projects[project_id]

    def ready(self) -> bool:
        return True


class FirestoreProjectStore:
    """Firestore-backed store with transactional revision checks."""

    def __init__(self, project_id: str, collection: str = "cutline_projects") -> None:
        from google.cloud import firestore

        self._firestore = firestore
        self._client = firestore.Client(project=project_id)
        self._collection = self._client.collection(collection)

    @staticmethod
    def _owned(project: Project | None, owner_hash: str) -> Project:
        if project is None or project.get("owner_hash") != owner_hash:
            raise DomainError("NOT_FOUND", "Project not found.", 404)
        return project

    def create(self, project: Project) -> Project:
        reference = self._collection.document(project["id"])
        reference.create(deepcopy(project))
        return deepcopy(project)

    def get(self, owner_hash: str, project_id: str) -> Project:
        snapshot = self._collection.document(project_id).get()
        project = snapshot.to_dict() if snapshot.exists else None
        return deepcopy(self._owned(project, owner_hash))

    def count(self, owner_hash: str) -> int:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self._collection.where(filter=FieldFilter("owner_hash", "==", owner_hash))
        return sum(1 for _ in query.stream())

    def mutate(
        self,
        owner_hash: str,
        project_id: str,
        expected_revision: int,
        mutation: Mutation,
    ) -> Project:
        reference = self._collection.document(project_id)
        transaction = self._client.transaction(max_attempts=5)

        @self._firestore.transactional
        def update(transaction_object):
            snapshot = reference.get(transaction=transaction_object)
            current = snapshot.to_dict() if snapshot.exists else None
            project = deepcopy(self._owned(current, owner_hash))
            if project["revision"] != expected_revision:
                raise DomainError("REVISION_CONFLICT", "Reload the current revision and retry.", 409)
            commit_mutation(project, mutation)
            transaction_object.set(reference, project)
            return project

        return deepcopy(update(transaction))

    def delete(self, owner_hash: str, project_id: str) -> None:
        project = self.get(owner_hash, project_id)
        if project:
            self._collection.document(project_id).delete()

    def ready(self) -> bool:
        try:
            next(self._collection.limit(1).stream(), None)
            return True
        except Exception:
            return False
