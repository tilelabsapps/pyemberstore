from datetime import datetime
from functools import cached_property
from typing import Any, List

# from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.async_collection import AsyncCollectionReference

from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1 import AsyncClient, SERVER_TIMESTAMP, ArrayRemove, Query, ArrayUnion, DELETE_FIELD

import asyncio
import aiofiles
from pydantic import AnyHttpUrl, BaseModel, Field
from google.genai import types
from uuid6 import uuid7

from ..model import User
from ..google.model import Authorisation
from . import api
from .. import model


# ----
# Local models
# ----

class Site(BaseModel):
    uri: str

    @staticmethod
    def from_core(core: model.Site) -> "Site":
        return Site(uri=str(core.uri))

    def to_core(self) -> model.Site:
        return model.Site(uri=AnyHttpUrl(self.uri))


class MetricTagTriggerFilter(BaseModel):
    variable: str = Field(description="The variable to filter on, e.g. 'Page URL'.")
    operator: str = Field(
        description="The filter type, e.g. 'contains', 'equals', 'starts_with', 'ends_with'."
    )
    value: str = Field(description="The value to compare to the variable, e.g. '/articles/'.")

    def to_core_model(self) -> model.MetricTagTriggerFilter:
        return model.MetricTagTriggerFilter(
            operation=model.MetricTagTriggerFilterOperator(self.operator),
            variable=model.Variable(self.variable),
            value=self.value
        )

    @staticmethod
    def from_core(core: model.MetricTagTriggerFilter) -> "MetricTagTriggerFilter":
        return MetricTagTriggerFilter(
            variable=core.variable.value,
            operator=core.operation.value,
            value=core.value
        )


class Trigger(BaseModel):
    id: str = Field(default_factory=lambda: uuid7().hex)
    kind: str
    name: str | None = Field(default=None, description="A name for the trigger")
    filters: list[MetricTagTriggerFilter] | None = Field(default=[])
    resource_path: str | None = Field(
        default=None,
        alias="resourcePath",
        description="""The resource path of the trigger in Google Tag Manager, e.g.
        'accounts/1234567890/containers/1234567890/workspaces/1234567890/triggers/1234567890'.
        This is set only when a Google Tag Manager resource has been created for this trigger.
        This is None if no resource have been created yet."""
    )
    gtm_resource_id: str | None = Field(
        default=None,
        alias="gtmResourceId",
        description="""The Google Tag Manager resource ID for this tag.
        This is set only when a Google Tag Manager resource has been created for this tag.
        This is None if no resource have been created yet."""
    )
    is_gtm_resource_owned: bool | None = Field(
        default=False,
        alias="isGtmResourceOwned",
        description="True if the Google Tag Manager resource is owned by this tag. False means it borrowed."
    )
    # Timer
    interval_milliseconds: int | None = Field(default=None)
    limit: int | None = Field(default=None)
    # Scroll depth
    vertical_threshold: int | None = Field(default=None)
    vertical_threshold_units: str | None = Field(default=None)
    vertical_threshold_on: bool | None = Field(default=None)
    horizontal_threshold: int | None = Field(default=None)
    trigger_start_option: str | None = Field(default=None)
    horizontal_threshold_on: bool | None = Field(default=None)

    @staticmethod
    def from_core(core: model.Trigger) -> "Trigger":
        return Trigger(
            id=core.id,
            kind=core.kind.value,
            name=core.name,
            filters=[MetricTagTriggerFilter.from_core(f)
                     for f in core.filters] if core.filters else [],
            resourcePath=core.resource_path,
            gtmResourceId=core.gtm_resource_id,
            isGtmResourceOwned=core.is_gtm_resource_owned,
        )

    def to_core(self) -> model.Trigger:

        class Wrapper(BaseModel):
            data: Trigger

        class CoreWrapper(BaseModel):
            data: model.Trigger

        wrapped = Wrapper(data=self)
        data = wrapped.model_dump(by_alias=True, exclude_unset=True, mode="json")
        core_data = CoreWrapper.model_validate(data).data
        return core_data


class Tag(BaseModel):
    """Definitions of tag needed to provide measurements for a metric."""
    id: str = Field(default_factory=lambda: uuid7().hex)
    name: str = Field(description="The name of the tag in Google Tag Manager, e.g. 'article_view'.")
    resource_path: str | None = Field(
        default=None,
        alias="resourcePath",
        description="""The resource path of the tag in Google Tag Manager, e.g.
        'accounts/1234567890/containers/1234567890/workspaces/1234567890/tags/1234567890'.
        This is set only when a Google Tag Manager resource has been created for this tag.
        This is None if no resource have been created yet."""
    )
    gtm_resource_id: str | None = Field(
        default=None,
        alias="gtmResourceId",
        description="""The Google Tag Manager resource ID for this tag.
        This is set only when a Google Tag Manager resource has been created for this tag.
        This is None if no resource have been created yet."""
    )
    is_gtm_resource_owned: bool | None = Field(
        default=False,
        alias="isGtmResourceOwned",
        description="True if the Google Tag Manager resource is owned by this tag. False means it borrowed."
    )
    triggers: dict[str, Trigger] = Field(
        default_factory=dict,
        description="Map of id to trigger."
    )

    @staticmethod
    def from_core(core: model.MetricTag) -> "Tag":
        return Tag(
            id=core.id,
            name=core.name,
            resourcePath=core.resource_path,
            triggers={t.id: Trigger.from_core(t) for t in core.triggers},
            gtmResourceId=core.gtm_resource_id,
            isGtmResourceOwned=core.is_gtm_resource_owned,
        )

    def to_core(self) -> model.MetricTag:
        return model.MetricTag(
            id=self.id,
            name=self.name,
            resourcePath=self.resource_path,
            triggers=[t.to_core() for t in self.triggers.values()],
            gtmResourceId=self.gtm_resource_id,
            isGtmResourceOwned=self.is_gtm_resource_owned,
        )


class CustomDimension(BaseModel):
    id: str
    name: str
    scope: str
    value: model.CustomVariable

    @staticmethod
    def from_core(core: model.MetricDimension) -> "CustomDimension":
        return CustomDimension(
            id=core.id,
            name=core.name,
            scope=core.scope.value,
            value=core.value,
        )

    def to_core(self) -> model.MetricDimension:
        return model.MetricDimension(
            # id=self.id,
            name=self.name,
            scope=model.MetricParameterDimensionScope(self.scope),
            value=self.value,
        )


class Metric(BaseModel):
    id: str = Field(default_factory=lambda: uuid7().hex)
    description: str | None = Field(
        default=None,
        description="""A high level description of the metric.
        This is what we want to measure. Implementation details
        will go into tags and triggers.
        """
    )
    title: str = Field(
        default="",
        description="A short descriptive title i.e. 'Cart Views'.")
    llm_notes: str | None = Field(
        default=None,
        description="Internal notes, used for LLM wishing to share info over requests.",
        alias="llmNotes"
    )
    parameters: dict[str, model.MetricParameter] = Field(
        default_factory=dict,
        description="List of custom parameters associated with this metric.",
    )
    custom_dimensions: dict[str, model.MetricDimension] = Field(
        default_factory=dict,
        description="List of custom dimensions associated with this metric.",
        alias="customDimensions"
    )
    tags: dict[str, Tag] = Field(
        default_factory=dict,
        description="""Map of id to tag needed to provide measurements
        for this metric.""",
    )
    is_key: bool = Field(
        default=False,
        alias="isKey",
        description="True if this is a key metric, i.e. a metric that is important for the business like checkout or newsletter signups.",
    )
    synced_at: datetime | None = Field(
        default=None,
        alias="syncedAt",
        description="The date and time when the metric was last synced."
    )
    created_at: datetime = Field(default_factory=datetime.now,
                                 alias="createdAt",)
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    deleted_at: datetime | None = Field(default=None, alias="deletedAt")

    def to_core(self) -> model.Metric:
        return model.Metric(
            id=self.id,
            description=self.description,
            title=self.title,
            llmNotes=self.llm_notes,
            tags=[t.to_core() for t in self.tags.values()],
            isKey=self.is_key,
            syncedAt=self.synced_at,
            createdAt=self.created_at,
            updatedAt=self.updated_at,
            deletedAt=self.deleted_at,
            parameters=[model.MetricParameter.model_validate(o) for o in self.parameters.values()],
            customDimensions=[v for v in self.custom_dimensions.values()],
        )

    @staticmethod
    def from_core_partial(metric: model.PartialMetric) -> "Metric":
        return Metric(
            description=metric.description,
            title=metric.title,
            llmNotes=metric.llm_notes,
            tags={t.id: Tag.from_core(t) for t in metric.tags},
            isKey=metric.is_key,
            syncedAt=metric.synced_at,
            parameters={o.id: o for o in metric.parameters},
            customDimensions={o.id: o for o in metric.custom_dimensions},
        )

    @staticmethod
    def from_core(metric: model.Metric) -> "Metric":
        return Metric(
            id=metric.id,
            description=metric.description,
            title=metric.title,
            llmNotes=metric.llm_notes,
            tags={t.id: Tag.from_core(t) for t in metric.tags},
            parameters={o.id: o for o in metric.parameters},
            isKey=metric.is_key,
            syncedAt=metric.synced_at,
            createdAt=metric.created_at,
            deletedAt=metric.deleted_at,
        )


class Workspace(BaseModel):
    """Represents a workspace with minimal information, used for listing or selection purposes.
    """
    owner_sub: str = Field(description="The sub of the user who owns this workspace.",
                           alias="ownerSub")
    title: str = Field(default="New Workspace",)
    collaborator_subs: list[str] = Field(
        default_factory=list,
        description="List of user subs who are collaborators in this workspace.",
        alias="collaboratorSubs"
    )
    ga_property: str = Field(description="The property name from Google Analytics.",
                             alias="gaProperty")  # . #  | None = None
    gtm_container: str = Field(
        description="Google Tag Manager container path.",
        alias="gtmContainer"
    )
    is_gtm_disabled: bool = Field(
        default=False,
        description="True if user have confirmed to disable Google Tag Manager.",
        alias="isGtmDisabled"
    )
    sites: list[Site] = Field(
        default_factory=list,
        description="List of sites associated with this workspace. This is the basis for creating data streams",
        alias="sites")
    metrics: dict[str, Metric] = Field(
        default_factory=dict,
        description="Map of metric goals for this workspace.",
        alias="metrics")
    id: str = Field(default_factory=lambda: uuid7().hex,)
    is_locked: bool = Field(default=False, description="Set to true in case of owner being locked.",
                            alias="isLocked")
    llm_notes: str | None = Field(default=None,
                                  description="Notes from the LLM about this workspace.",
                                  alias="llmNotes")
    created_at: datetime = Field(default_factory=datetime.now,
                                 alias="createdAt",)
    updated_at: datetime | None = Field(default=None,
                                        description="The date when the workspace was last updated.",
                                        alias="updatedAt")
    published_at: datetime | None = Field(
        default=None,
        alias="publishedAt",
        description="The datetime when the workspace was last published in Google Tag Manager.",
    )

    @staticmethod
    def from_core(ws: model.Workspace) -> "Workspace":
        return Workspace(
            id=ws.id,
            ownerSub=ws.owner_sub,
            title=ws.title,
            collaboratorSubs=ws.collaborator_subs,
            gaProperty=ws.ga_property,
            gtmContainer=ws.gtm_container,
            isGtmDisabled=ws.is_gtm_disabled,
            sites=[Site.from_core(site) for site in ws.sites] or [],
            metrics={v.id: Metric.from_core(v) for v in ws.metrics},
            isLocked=ws.is_locked,
            llmNotes=ws.llm_notes,
            createdAt=ws.created_at,
            updatedAt=ws.updated_at,
            publishedAt=ws.published_at,
        )

    @staticmethod
    def from_core_partial(ws: model.PartialWorkspace) -> "Workspace":
        return Workspace(
            ownerSub=ws.owner_sub,
            title=ws.title or "New Workspace",
            collaboratorSubs=ws.collaborator_subs or [],
            gaProperty=ws.ga_property,
            gtmContainer=ws.gtm_container,
            isGtmDisabled=ws.is_gtm_disabled or False,
            sites=[Site.from_core(site) for site in ws.sites] or [],
            metrics={v.id: Metric.from_core_partial(v) for v in ws.metrics} if ws.metrics else {},
        )

    def to_core(self) -> model.Workspace:
        return model.Workspace(
            id=self.id,
            ownerSub=self.owner_sub,
            title=self.title,
            collaboratorSubs=self.collaborator_subs,
            gaProperty=self.ga_property,
            gtmContainer=self.gtm_container,
            isGtmDisabled=self.is_gtm_disabled,
            sites=[site.to_core() for site in self.sites],
            metrics=[metric.to_core() for metric in self.metrics.values()],
            isLocked=self.is_locked,
            llmNotes=self.llm_notes,
            createdAt=self.created_at,
            updatedAt=self.updated_at,
            publishedAt=self.published_at,
        )


class Conversation(BaseModel):
    id: str
    sub: str
    content: list[types.ContentOrDict] = Field(default_factory=list)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(alias="updatedAt", default=None)

    @staticmethod
    def from_core(conversation: model.Conversation) -> "Conversation":
        conv = Conversation(
            id=conversation.id,
            sub=conversation.sub,
            createdAt=conversation.created_at,
            updatedAt=conversation.updated_at,
            content=conversation.content
        )
        return conv

    def to_core(self) -> model.Conversation:
        return model.Conversation(
            id=self.id,
            sub=self.sub,
            content=self.content,
            createdAt=self.created_at,
            updatedAt=self.updated_at
        )


class Feedback(BaseModel):
    id: str
    sub: str
    conversation: list[types.ContentOrDict] = Field(default_factory=list)
    kind: str
    created_at: datetime = Field(alias="createdAt")

    @staticmethod
    def from_core(feedback: model.Feedback) -> "Feedback":
        return Feedback(
            id=feedback.id,
            sub=feedback.sub,
            conversation=feedback.conversation,
            kind=feedback.kind.value,
            createdAt=feedback.created_at
        )

    def to_core(self) -> model.Feedback:
        return model.Feedback(
            id=self.id,
            sub=self.sub,
            conversation=self.conversation,
            kind=model.FeedbackKind(self.kind),
            createdAt=self.created_at
        )


# ----
# Implementations
# ----

class UserStore(api.UserStore):

    cname = "users"

    @cached_property
    def _db(self):
        return AsyncClient()

    async def fetch(
        self,
        sub: str | None = None,
        google_sub: str | None = None,
        discord_sub: str | None = None,
        stripe_sub: str | None = None
    ) -> User | None:
        """
        Parameters
        ----------
        sub : str | None
            The user id to fetch.
        discord_sub : str | None
            If provided, will fetch the user with this discord id.
        stripe_sub : str | None
            If provided, will fetch the user with this stripe id.

        """
        if not (sub or google_sub or discord_sub or stripe_sub):
            raise ValueError("No id provided. Either user_id or google_id must be provided.")
        record: dict | None = None
        db = self._db
        users = db.collection(self.cname)
        if sub is not None:
            record = (await users.document(sub).get()).to_dict()
        if google_sub is not None:
            q = users.where("googleSub", "==", google_sub)
            item = await q.limit(1).get()
            record = item[0].to_dict() if item else None
        if discord_sub is not None:
            q = users.where("discordSub", "==", discord_sub)
            item = await q.limit(1).get()
            record = item[0].to_dict() if item else None
        if stripe_sub is not None:
            q = users.where("stripeSub", "==", stripe_sub)
            item = await q.limit(1).get()
            record = item[0].to_dict() if item else None
        if record is None:
            return None
        return User.model_validate(record)

    async def put(self, user: User):
        db = self._db
        payload = user.model_dump(mode='json', by_alias=True, exclude_none=True)
        payload["createdAt"] = SERVER_TIMESTAMP
        payload["updatedAt"] = SERVER_TIMESTAMP
        await db.collection(self.cname).document(user.sub).create(payload)

    async def patch(self, sub: str, user: model.UserPatch) -> model.User:
        db = self._db
        # Must be JSON first to handle enum serialization.
        payload = user.model_dump(mode='json', by_alias=True, exclude_unset=True)
        payload["updatedAt"] = SERVER_TIMESTAMP
        await db.collection(self.cname).document(sub).update(payload)
        new_user = await self.fetch(sub=sub)
        if not new_user:
            raise ValueError(f"User {sub} not found after patch.")
        return new_user

    async def update_usage(
            self,
            sub: str,
            usage: model.Usage,
            old_usage: model.IntervalUsage | None = None
    ):
        db = self._db
        user_ref = db.collection(self.cname).document(sub)
        
        if old_usage is not None:
            # New month started, archive the old usage
            archive_ref = user_ref.collection("usage_history").document(old_usage.id)
            # Use model_dump(mode='json') to ensure it's JSON serializable for Firestore
            archive_payload = old_usage.model_dump(mode='json', by_alias=True)
            await archive_ref.set(archive_payload)
            
            # The current usage should be reset to the new one passed in
            # (which is the first usage of the new interval). Generate a new
            # stable ID for the new interval.
            payload = {
                "usage": {
                    "id": uuid7().hex,
                    "usage": usage.model_dump(mode='json', by_alias=True),
                    "updatedAt": SERVER_TIMESTAMP
                }
            }
            await user_ref.update(payload)
        else:
            # Normal increment within the current month
            interval_id = None
            doc = await user_ref.get(["usage"])
            if doc.exists:
                try:
                    existing_usage_data = doc.get("usage")
                    if existing_usage_data is not None:
                        current_interval = model.IntervalUsage.model_validate(existing_usage_data)
                        usage += current_interval.usage
                        interval_id = current_interval.id  # preserve the existing stable ID
                except KeyError:
                    pass  # usage field not present yet
            if interval_id is None:
                interval_id = uuid7().hex  # no existing usage found, generate a new ID
            
            payload = {
                "usage": {
                    "id": interval_id,
                    "usage": usage.model_dump(mode='json', by_alias=True),
                    "updatedAt": SERVER_TIMESTAMP
                }
            }
            # Use update if document exists, otherwise set (though document should exist for a user)
            await user_ref.update(payload)


class AuthorisationStore(api.AuthorizationStore):

    cname = "authorisations"

    @cached_property
    def _db(self):
        return AsyncClient()

    def _collection(self, sub: str) -> AsyncCollectionReference:
        return self._db.collection(UserStore.cname).document(sub).collection(self.cname)

    async def current(self, domain: str, sub: str) -> Authorisation | None:
        """
        Fetch the current authorisation for a user.
        Current is the last authorisation for the user.

        Parameters
        ----------
        domain : str
            The domain to fetch the authorisation for.
        sub : str
            The user id/sub to fetch the current authorisation for.
        """
        auths = (await self._collection(sub)
                 .where("domain", "==", domain)
                 .order_by("createdAt", direction=Query.DESCENDING)
                 .limit(1).get())
        if auths:
            return Authorisation.model_validate(auths[0].to_dict())
        return None

    async def put(self, authorisation: Authorisation):
        """
        Set the authorisation as the current authorisation for the user.
        Parameters
        ----------
        authorisation : Authorisation
            The authorisation to set.
        """
        id = uuid7().hex
        payload = authorisation.model_dump(by_alias=True, exclude_none=True)
        payload["createdAt"] = SERVER_TIMESTAMP
        payload["updatedAt"] = SERVER_TIMESTAMP
        await (self._collection(authorisation.sub).document(id).set(payload))


class WorkspaceStore(api.WorkspaceStore):

    cname = "workspaces"

    @cached_property
    def _db(self):
        return AsyncClient()

    @staticmethod
    def _key(sub: str, id: str) -> str:
        return f"{sub}.{id}"

    async def fetch(self, sub: str, id: str | None = None, ga_property: str | None = None) -> model.Workspace | None:
        """
        Fetch a workspace by its id.
        """
        db = self._db
        if id:
            doc = await db.collection(self.cname).document(self._key(sub, id)).get()
            if not doc.exists:
                return None
            return Workspace.model_validate(doc.to_dict()).to_core()
        if ga_property:
            q = (db.collection(self.cname)
                    .where("ownerSub", "==", sub)
                    .where("gaProperty", "==", ga_property))
            doc = await q.limit(1).get()
            if not doc:
                return None
            return Workspace.model_validate(doc[0].to_dict()).to_core()
        return None

    async def find_by_site(self, sub: str, site: str) -> model.Workspace | None:
        """
        Find a workspace for the given user (sub) that contains a site with the specified URI.
        """
        db = self._db
        # Query all workspaces for the user
        q = db.collection(self.cname).where("ownerSub", "==", sub)
        docs = await q.get()
        for doc in docs:
            data = doc.to_dict()
            if not data:
                return None
            # Defensive: skip if no sites
            sites = data.get("sites", [])
            target = str(AnyHttpUrl(site))
            for s in sites:
                if s.get("uri") == target:
                    return Workspace.model_validate(data).to_core()
        return None

    async def update(self, workspace: model.Workspace):        
        """
        Update a workspace.
        """
        db = self._db
        payload = Workspace.from_core(workspace).model_dump()
        payload["updated_at"] = SERVER_TIMESTAMP
        await db.collection(self.cname).document(self._key(workspace.owner_sub, workspace.id)).set(payload)

    async def create(self, workspace: model.PartialWorkspace) -> model.Workspace:
        """
        Create a new workspace.
        """
        db = self._db
        id = uuid7().hex
        payload = Workspace.from_core_partial(workspace).model_dump(
            by_alias=True,
            exclude_none=True,
        )
        payload["id"] = id
        payload["ownerSub"] = workspace.owner_sub
        payload["createdAt"] = SERVER_TIMESTAMP
        payload["updatedAt"] = SERVER_TIMESTAMP
        await db.collection(self.cname).document(self._key(workspace.owner_sub, id)).create(payload)
        new = await db.collection(self.cname).document(self._key(workspace.owner_sub, id)).get()
        return Workspace.model_validate(new.to_dict()).to_core()

    async def patch(self, sub: str, workspace_id: str, patch: model.WorkspacePatch) -> model.Workspace:
        fs = self._db
        doc_ref = fs.collection(self.cname).document(self._key(sub, workspace_id))
        await doc_ref.update(patch.model_dump(by_alias=True, exclude_unset=True))
        updated = await doc_ref.get()
        return Workspace.model_validate(updated.to_dict()).to_core()

    async def append_metrics(self, sub, workspace_id: str, metrics: list[model.PartialMetric]):
        _metrics = [Metric.from_core_partial(metric) for metric in metrics]
        fs = self._db
        collection = fs.collection(self.cname)
        doc_ref = collection.document(self._key(sub, workspace_id))
        for m in _metrics:
            payload = m.model_dump(by_alias=True, exclude_none=True, mode="json")
            payload["updatedAt"] = SERVER_TIMESTAMP
            await doc_ref.update({f"metrics.{m.id}": payload})
        return [m.id for m in _metrics]

    async def patch_metric(
            self,
            sub: str,
            workspace_id: str,
            metric_id: str,
            patch: model.MetricPatch):
        update: dict[str, Any] = {}
        if (name := patch.name) and "name" in patch.model_fields_set:
            update[f"metrics.{metric_id}.title"] = name
        if "description" in patch.model_fields_set:
            update[f"metrics.{metric_id}.description"] = patch.description
        if (is_key := patch.is_key) is not None:
            update[f"metrics.{metric_id}.isKey"] = is_key
        if new_dimensions := patch.new_custom_dimensions:
            for dim in new_dimensions:
                dim_model = CustomDimension.from_core(dim)
                update[f"metrics.{metric_id}.customDimensions.{dim_model.id}"] = dim_model.model_dump(
                    by_alias=True, exclude_none=True, mode="json")
        if dimension_deletes := patch.delete_custom_dimensions:
            for dim_id in dimension_deletes:
                update[f"metrics.{metric_id}.customDimensions.{dim_id}"] = DELETE_FIELD

        if patch.new_triggers or patch.delete_triggers:
            ws = await self.fetch(sub, workspace_id)
            if not ws:
                raise ValueError(f"Workspace with id {workspace_id} not found")
            metric = ws.find_metric(metric_id)
            if not metric:
                raise ValueError(f"Metric with id {metric_id} not found")

            if new_triggers := patch.new_triggers:
                if not metric.tags:
                    # Create default tag logic
                    tag_id = uuid7().hex
                    tech_name = metric.title.lower().replace(" ", "_")
                    new_tag_triggers = {
                        t.id: Trigger.from_core(t) for t in new_triggers
                    }
                    new_tag = Tag(
                        id=tag_id,
                        name=tech_name,
                        triggers=new_tag_triggers
                    )
                    update[f"metrics.{metric_id}.tags.{tag_id}"] = new_tag.model_dump(
                        by_alias=True, exclude_none=True, mode="json")
                else:
                    tag = metric.tags[0]  # model.MetricTag
                    for trigger in new_triggers:
                        trigger_model = Trigger.from_core(trigger)
                        update[f"metrics.{metric_id}.tags.{tag.id}.triggers.{trigger_model.id}"] = trigger_model.model_dump(
                            by_alias=True, exclude_none=True, mode="json")

            if deleted_triggers := patch.delete_triggers:
                for trigger_id in deleted_triggers:
                    for tag in metric.tags:
                        if any(t.id == trigger_id for t in tag.triggers):
                            update[f"metrics.{metric_id}.tags.{tag.id}.triggers.{trigger_id}"] = DELETE_FIELD
                            break

        if not update:
            return
        update["updatedAt"] = SERVER_TIMESTAMP
        update[f"metrics.{metric_id}.updatedAt"] = SERVER_TIMESTAMP
        await self._db.collection(self.cname).document(self._key(sub, workspace_id)).update(update)

    async def patch_metric_parameter(
        self, sub: str,
        workspace_id: str,
        metric_id: str,
        parameter_id: str,
        patch: model.MetricParameterPatch
    ):
        doc_ref = self._db.collection(self.cname).document(self._key(sub, workspace_id))
        payload = patch.model_dump(by_alias=True, exclude_unset=True)
        await doc_ref.update(
            {f"metrics.{metric_id}.parameters.{parameter_id}.{key}": value
             for key, value in payload.items()} |
            {"updatedAt": SERVER_TIMESTAMP,
             f"metrics.{metric_id}.updatedAt": SERVER_TIMESTAMP}
        )

    async def patch_trigger(
            self,
            sub: str,
            workspace_id: str,
            metric_id: str,
            tag_id: str,
            trigger_id: str,
            patch: model.MetricTagTriggerPatch):
        doc_ref = self._db.collection(self.cname).document(self._key(sub, workspace_id))
        payload = patch.model_dump(by_alias=True, exclude_unset=True)
        await doc_ref.update(
            {f"metrics.{metric_id}.tags.{tag_id}.triggers.{trigger_id}.{key}": value
             for key, value in payload.items()} |
            {"updatedAt": SERVER_TIMESTAMP,
             f"metrics.{metric_id}.updatedAt": SERVER_TIMESTAMP,
             f"metrics.{metric_id}.tags.{tag_id}.updatedAt": SERVER_TIMESTAMP,
             f"metrics.{metric_id}.tags.{tag_id}.triggers.{trigger_id}.updatedAt": SERVER_TIMESTAMP,}
        )

    async def patch_tag(self, sub: str, workspace_id: str, metric_id: str, tag_id: str, patch: model.MetricTagPatch):
        doc_ref = self._db.collection(self.cname).document(self._key(sub, workspace_id))
        payload = patch.model_dump(by_alias=True, exclude_unset=True)
        await doc_ref.update(
            {f"metrics.{metric_id}.tags.{tag_id}.{key}": value
             for key, value in payload.items()} |
            {"updatedAt": SERVER_TIMESTAMP,
             f"metrics.{metric_id}.updatedAt": SERVER_TIMESTAMP,
             f"metrics.{metric_id}.tags.{tag_id}.updatedAt": SERVER_TIMESTAMP,}
        )

    async def append_site(self, sub: str, workspace_id: str, uri: str):
        col = self._db.collection(self.cname)
        q = (col
                .where("ownerSub", "==", sub)
                .where("id", "==", workspace_id))
        raw_ws = await q.limit(1).get()

        if not raw_ws:
            raise ValueError(f"Workspace {workspace_id} not found for user {sub}")

        doc_ref = raw_ws[0].reference
        await doc_ref.update({
            "sites": ArrayUnion([model.Site(uri=AnyHttpUrl(uri)).model_dump(by_alias=True)])
        })

    async def remove_site(self, sub: str, workspace_id: str, uri: str):
        fs = self._db
        col = fs.collection(self.cname)
        q = (col
                .where("ownerSub", "==", sub)
                .where("id", "==", workspace_id))
        raw_ws = await q.limit(1).get()

        if not raw_ws:
            raise ValueError(f"Workspace {workspace_id} not found for user {sub}")

        doc_ref = raw_ws[0].reference
        ws = Workspace.model_validate(raw_ws[0].to_dict()).to_core()
        target_uri = AnyHttpUrl(uri)
        target = next(filter(lambda s: s.uri == target_uri, ws.sites), None)
        if target is None:
            raise ValueError(f"Site {uri} not found in workspace {workspace_id} for user {sub}")
        dict_target = target.model_dump(by_alias=True)
        await doc_ref.update({"sites": ArrayRemove([dict_target])})

    async def put_site(self, sub: str, workspace_id: str, site: model.Site) -> None:
        fs = self._db
        col = fs.collection(self.cname)
        q = (col
                .where("ownerSub", "==", sub)
                .where("id", "==", workspace_id))
        raw_ws = await q.limit(1).get()

        if not raw_ws:
            raise ValueError(f"Workspace {workspace_id} not found for user {sub}")

        doc_ref = raw_ws[0].reference
        ws = Workspace.model_validate(raw_ws[0].to_dict())
        for i, s in enumerate(ws.sites):
            if s.uri == site.uri:
                ws.sites[i] = Site.from_core(site)
                await doc_ref.update({
                    "sites": [s.model_dump(by_alias=True, mode="json") for s in ws.sites],
                    "updatedAt": SERVER_TIMESTAMP,
                })
                return

    async def mark_metric_as_synced(self, sub: str, workspace_id: str, metric_id: str):
        doc_ref = self._db.collection(self.cname).document(self._key(sub, workspace_id))
        await doc_ref.update({
            f"metrics.{metric_id}.syncedAt": SERVER_TIMESTAMP
        })

    async def delete_metric(self, sub: str, workspace_id: str, metric_id: str) -> model.Workspace:
        """Mark a metric as deleted by setting its deleted_at timestamp."""
        fs = self._db
        doc_ref = fs.collection(self.cname).document(self._key(sub, workspace_id))
        await doc_ref.update({
            f"metrics.{metric_id}.deletedAt": SERVER_TIMESTAMP,
            f"metrics.{metric_id}.updatedAt": SERVER_TIMESTAMP,
        })
        updated = await doc_ref.get()
        return Workspace.model_validate(updated.to_dict()).to_core()

    async def restore_metric(self, sub: str, workspace_id: str, metric_id: str):
        """Mark a metric as restored by clearing its deleted_at and synced_at timestamp."""
        fs = self._db
        doc_ref = fs.collection(self.cname).document(self._key(sub, workspace_id))
        await doc_ref.update({
            f"metrics.{metric_id}.deletedAt": None,
            f"metrics.{metric_id}.syncedAt": None,
            f"metrics.{metric_id}.updatedAt": SERVER_TIMESTAMP
        })

    async def mark_as_published(self, sub: str, workspace_id: str):
        fs = self._db
        doc_ref = fs.collection(self.cname).document(self._key(sub, workspace_id))
        await doc_ref.update({
            "publishedAt": SERVER_TIMESTAMP
        })

    async def list(self, sub: str, limit: int | None = None) -> list[model.Workspace]:
        """
        List all workspaces for a user.

        Parameters:
        owner_sub : str
            The user id to fetch the workspaces for.
        """
        db = self._db
        q = db.collection(self.cname).where("ownerSub", "==", sub)
        if limit is not None:
            q = q.limit(limit)
        docs = await q.get()
        return [Workspace.model_validate(doc.to_dict()).to_core() for doc in docs]

    async def append_parameters(
            self,
            sub: str,
            workspace_id: str,
            metric_id: str,
            parameters: List[model.MetricParameter]
    ) -> List[str]:
        await self._db.collection(self.cname).document(self._key(sub, workspace_id)).update(
            {f"metrics.{metric_id}.parameters.{custom_parameter.id}": 
                custom_parameter.model_dump(by_alias=True, mode="json")
                for custom_parameter in parameters} |
            {
                "updatedAt": SERVER_TIMESTAMP,
                f"metrics.{metric_id}.updatedAt": SERVER_TIMESTAMP}
        )
        return [custom_parameter.id for custom_parameter in parameters]

    async def delete_parameters(
            self,
            sub: str,
            workspace_id: str,
            metric_id: str,
            parameter_ids: List[str],
    ):
        doc_ref = self._db.collection(self.cname).document(self._key(sub, workspace_id))
        ws_snapshot = (await doc_ref.get({
            f"metrics.`{metric_id}`.parameters"
        })).to_dict()
        if not ws_snapshot:
            return
        # params = ws_snapshot.get("metrics", {}).get(metric_id, {}).get("parameters", [])
        await doc_ref.update({
            f"metrics.{metric_id}.parameters.{param_id}": DELETE_FIELD
            for param_id in parameter_ids
            } | {"updatedAt": SERVER_TIMESTAMP,
                 f"metrics.{metric_id}.updatedAt": SERVER_TIMESTAMP}
        )


class EmbeddingStore(api.EmbeddingStore):

    collection_name = "user_documents"

    def __init__(self):
        self.client = AsyncClient()

    async def _read_doc(self, file_path) -> str:
        async with aiofiles.open(f"docs/{file_path}", "r") as f:
            return await f.read()

    async def query(self, embedding: list[float]) -> list[tuple[str, str]]:
        collection = self.client.collection(self.collection_name)
        vector_query = collection.find_nearest(
            vector_field="vector",
            query_vector=Vector(embedding),
            distance_measure=DistanceMeasure.EUCLIDEAN,
            limit=2)

        search_results = await vector_query.get()
        async def get_path_and_content(doc):
            path = doc.get("path")
            content = await self._read_doc(path)
            return path, content

        tasks = [get_path_and_content(doc) for doc in search_results]
        return await asyncio.gather(*tasks)


class InviteStore(api.InviteStore):
    """Just a dummy for now."""

    async def fetch(self, id: str) -> model.Invite | None:
        return None

    async def activate(self, id: str):
        ...


class FirestoreConversationStore(api.ConversationStore):
    cname = "conversations"

    @cached_property
    def _db(self) -> AsyncClient:
        return AsyncClient()

    async def fetch(self, sub: str, conversation_id: str) -> model.Conversation | None:
        conversation_ref = self._db.collection(UserStore.cname).document(sub).collection(self.cname).document(conversation_id)
        raw_conversation = await conversation_ref.get()
        if not raw_conversation.exists:
            return None
        conversation = Conversation.model_validate(raw_conversation.to_dict())
        return conversation.to_core()

    async def create(self, sub: str, conversation: model.Conversation):
        inner_conversation = Conversation.from_core(conversation)

        payload = inner_conversation.model_dump(by_alias=True, exclude_none=True)
        payload["createdAt"] = SERVER_TIMESTAMP
        await self._db.collection(UserStore.cname).document(sub).collection(self.cname).document(conversation.id).set(payload)

    async def update(self, sub: str, conversation_id: str, patch: model.ConversationPatch):
        conversation_ref = self._db.collection(UserStore.cname).document(sub).collection(self.cname).document(conversation_id)
        await conversation_ref.update(patch.model_dump(by_alias=False, exclude_none=False, exclude_unset=False))


class FirestoreFeedbackStore(api.FeedbackStore):
    cname = "feedback"

    @cached_property
    def _db(self) -> AsyncClient:
        return AsyncClient()

    async def create(self, feedback: model.Feedback):
        inner_feedback = Feedback.from_core(feedback)
        payload = inner_feedback.model_dump(by_alias=True, exclude_none=True)
        payload["createdAt"] = SERVER_TIMESTAMP
        await self._db.collection(self.cname).document(feedback.id).set(payload)

    async def fetch(self, feedback_id: str) -> model.Feedback | None:
        feedback_ref = self._db.collection(self.cname).document(feedback_id)
        raw_feedback = await feedback_ref.get()
        if not raw_feedback.exists:
            return None
        feedback = Feedback.model_validate(raw_feedback.to_dict())
        return feedback.to_core()

    async def list(self, sub: str | None = None) -> list[model.Feedback]:
        query = self._db.collection(self.cname)
        if sub:
            query = query.where("sub", "==", sub)
        docs = await query.get()
        return [Feedback.model_validate(doc.to_dict()).to_core() for doc in docs]


class Store(api.Store):

    def __init__(self,
                 embedding: api.EmbeddingStore):
        self.user = UserStore()
        self.authorisation = AuthorisationStore()
        self.conversation = FirestoreConversationStore()
        self.workspace = WorkspaceStore()
        self.embedding = embedding
        self.invite = InviteStore()
        self.feedback = FirestoreFeedbackStore()
