"""Stream type classes for tap-hubspot."""
# from black import Report
from asyncio.log import logger
from math import inf
import requests
import json

from dateutil import parser
import datetime, pytz
import time
from datetime import datetime

from pathlib import Path
from typing import Any, Dict, Optional, Union, List, Iterable

from singer_sdk import typing as th  # JSON Schema typing helpers
from pathlib import Path
from typing import Any, Dict, Optional, Union, List, Iterable

from memoization import cached

from singer_sdk.helpers.jsonpath import extract_jsonpath
from singer_sdk.streams import RESTStream
from singer_sdk.authenticators import BearerTokenAuthenticator
from singer_sdk import typing as th  # JSON schema typing helpers
from tap_hubspot.client import HubspotStream
from tap_hubspot.schemas.marketing import CampaignIds

SCHEMAS_DIR = Path(__file__).parent / Path("./schemas")

utc=pytz.UTC

from tap_hubspot.schemas.marketing import (
    Emails,
    CampaignIds,
    Campaigns,
    Forms,
    EmailSubscriptions,
)

class MarketingStream(HubspotStream):
    records_jsonpath = "$.results[*]"  # Or override `parse_response`.
    next_page_token_jsonpath = "$.paging.next.after"  # Or override `get_next_page_token`.
    replication_key = "updatedAt"
    replication_method = "INCREMENTAL"
    cached_schema = None
    properties = []
    schema_filepath = ""


class MarketingEmailsStream(MarketingStream):
    records_jsonpath = "$.objects[*]"  # Or override `parse_response`.
    next_page_token_jsonpath = "$.offset"  # Or override `get_next_page_token`.
    version = "v1"
    name = "marketing_emails_v1"
    path = f"/marketing-emails/{version}/emails/with-statistics"
    # primary_keys = ["id"]
    replication_key = "updated"
    total_emails = inf

    def parse_response(self, response: requests.Response) -> Iterable[dict]:
        """Parse the response and return an iterator of result rows."""
        self.total_emails = response.json()['total']
        data = response.json()
        ret = [dict(d, updated=datetime.fromtimestamp(d["updated"]/1000, tz=utc)) for d in data["objects"]]
        data["objects"] = ret
        yield from extract_jsonpath(self.records_jsonpath, input=data)

    def post_process(self, row: dict, context: Optional[dict]) -> dict:
        """As needed, append or transform raw data to match expected structure.
        Returns row, or None if row is to be excluded"""

        if self.replication_key:
            if row[self.replication_key].timestamp() <= self.get_starting_timestamp(context).astimezone(pytz.utc).timestamp():
                return None
        return row

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params = super().get_url_params(context, next_page_token)
        if not next_page_token:
            next_page_token = 0
        params["offset"] = params["limit"] + next_page_token
        params['orderBy'] = "created"
        if params["offset"] > self.total_emails:
            params["offset"] = None
            next_page_token = None
        return params

    schema = Emails.schema


class MarketingCampaignIdsStream(MarketingStream):
    version = "v1"
    records_jsonpath = "$.campaigns[*]"
    next_page_token_jsonpath = "$.offset"  # Or override `get_next_page_token`.
    name = "email_campaigns"
    path = f"/email/public/{version}/campaigns/by-id"
    # primary_keys = ["id"]
    replication_method = "FULL_TABLE"
    replication_key = ""

    schema = CampaignIds.schema


    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params = super().get_url_params(context, next_page_token)
        if next_page_token:
            params["offset"] = next_page_token
        params['orderBy'] = "created"

        return params

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        """Return a context dictionary for child streams."""
        return {
            "campaign_id": record["id"],
        }

class MarketingCampaignsStream(MarketingStream):
    records_jsonpath = "$.[*]"
    next_page_token_jsonpath = "$.offset"  # Or override `get_next_page_token`.
    name = "email_campaigns_details"
    path = "/email/public/v1/campaigns/{campaign_id}"
    # primary_keys = ["id"]
    replication_method = "FULL_TABLE"
    replication_key = ""
    parent_stream_type = MarketingCampaignIdsStream

    schema = Campaigns.schema

    def post_process(self, row: dict, context: Optional[dict]) -> dict:
        """As needed, append or transform raw data to match expected structure.
        Returns row, or None if row is to be excluded"""

        if self.replication_key:
            if row[self.replication_key] <= int(self.get_starting_timestamp(context).astimezone(pytz.utc).strftime('%s')):
                return None
        return row

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params = super().get_url_params(context, next_page_token)
        if next_page_token:
            params["offset"] = next_page_token
        params['orderBy'] = "created"
        return params

class EmailEventsStream(MarketingStream):
    """Define custom stream."""
    next_page_token_jsonpath = "$.offset"
    replication_method = "INCREMENTAL"
    name = "email_events"
    path = "/email/public/v1/events"
    records_jsonpath = "$.events[*]"
    # primary_keys = ["id"]
    replication_key = "created"

    @property
    def schema_filepath(self) -> Path:
        return SCHEMAS_DIR / f"{self.name}.json"

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params = super().get_url_params(context, next_page_token)

        start_replication_key_value = self.get_starting_replication_key_value(context)

        if start_replication_key_value:
            start_date = start_replication_key_value
            if type(start_date) == str:
                start_date = str(int(datetime.timestamp(datetime.strptime(start_replication_key_value, '%Y-%m-%dT%H:%M:%SZ')))) + '000'
            params["startTimestamp"] = start_date

        end_date = self.config.get("end_date")
        if end_date:
            end_date = str(int(datetime.timestamp(datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ")))) + '000'
            params["endTimestamp"] = end_date

        if next_page_token:
            params["offset"] = next_page_token
        params['orderBy'] = "created"
        params["limit"] = 500

        return params

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        """Return a context dictionary for child streams."""
        return {"created": record["created"], "email_id": record["id"]}


class EmailEventsDetailsStream(MarketingStream):
    name = "email_events_details"
    path = "/email/public/v1/events/{created}/{email_id}"
    deal_id = ""
    replication_method = "INCREMENTAL"
    # primary_keys = ["id", "toObjectId"]
    state_partitioning_keys = ["id", "created"]
    replication_key = ""
    parent_stream_type = EmailEventsStream

    ignore_parent_replication_keys = True

    @property
    def schema_filepath(self) -> Path:
        return SCHEMAS_DIR / f"{self.name}.json"

    def post_process(self, row: dict, context: Optional[dict]) -> dict:
        """As needed, append or transform raw data to match expected structure.
        Returns row, or None if row is to be excluded"""

        if self.replication_key:
            if row[self.replication_key] <= int(self.get_starting_timestamp(context).astimezone(pytz.utc).strftime('%s')):
                return None
        return row

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params = super().get_url_params(context, next_page_token)
        self.email_id = context["email_id"]
        self.created = context["created"]

        return params

class MarketingFormsStream(MarketingStream):
    name = "forms_v3"
    path = "/marketing/v3/forms/"
    # primary_keys = ["id"]
    schema = Forms.schema

    def get_url_params(
            self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params: dict = {}
        if next_page_token:
            params["after"] = next_page_token
        params["count"] = 100
        params["formTypes"] = "all"
        return params


class MarketingListsStream(HubspotStream):
    """Define stream for Marketing Lists."""

    # todo: update when Hubspot updates API to v3
    name = "lists_v1"
    path = "/contacts/v1/lists"
    # primary_keys = ["listId"]
    replication_method = "FULL_TABLE"
    replication_key = ""
    next_page_token_jsonpath = "$.offset"
    records_jsonpath = "$.lists[*]"

    def get_next_page_token(
            self, response: requests.Response, previous_token: Optional[Any]
    ) -> Optional[Any]:
        """Return a token for identifying next page or None if no more pages."""
        all_matches = extract_jsonpath("$.has-more", response.json())
        has_more = next(iter(all_matches), None)
        if has_more:
            all_matches = extract_jsonpath(
                self.next_page_token_jsonpath
                , response.json()
            )
            first_offset_match = next(iter(all_matches), None)
            return first_offset_match
        else:
            return None

    def get_url_params(self, context: Optional[dict], next_page_token: Optional[Any]) -> Dict[str, Any]:
        params = super().get_url_params(context, next_page_token)
        params['count'] = 100
        params['offset'] = next_page_token if next_page_token else 0
        return params

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        """Return a context dictionary for child streams."""
        return {"listId": record["listId"]}


class MarketingListContactsStream(MarketingListsStream):
    records_jsonpath = "$.contacts[*]"
    name = "list_contacts_v1"
    path = "/contacts/v1/lists/{listId}/contacts/all"
    # primary_keys = ["canonical-vid", "listId"]
    replication_method = "FULL_TABLE"
    replication_key = ""
    parent_stream_type = MarketingListsStream
    next_page_token_jsonpath = "$.vid-offset"

    def get_url_params(self, context: Optional[dict], next_page_token: Optional[Any]) -> Dict[str, Any]:
        params = super().get_url_params(context, next_page_token)
        params['count'] = 100
        params['vidOffset'] = next_page_token if next_page_token else 0
        return params

    def post_process(self, row: dict, context: Optional[dict]) -> dict:
        """As needed, append or transform raw data to match expected structure.
        Returns row, or None if row is to be excluded"""

        row["listId"] = context["listId"]
        return row


class FormsStream(MarketingStream):
    records_jsonpath = "$.[*]"
    next_page_token_jsonpath = "$.offset"
    name = "forms"
    path = "/forms/v2/forms"
    # primary_keys = ["id"]
    replication_method = "FULL_TABLE"
    replication_key = ""

    schema = CampaignIds.schema

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params = super().get_url_params(context, next_page_token)
        if next_page_token:
            params["offset"] = next_page_token
        params['orderBy'] = "created"
        return params

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        """Return a context dictionary for child streams."""
        return {
            "guid": record["guid"],
        }


class FormSubmissionsStream(MarketingStream):
    records_jsonpath = "$.[*]"
    next_page_token_jsonpath = "$.offset"  # Or override `get_next_page_token`.
    name = "form_submissions"

    path = "/form-integrations/v1/submissions/forms/{guid}"
    # primary_keys = ["guid"]
    replication_method = "FULL_TABLE"
    replication_key = ""
    parent_stream_type = FormsStream

    schema_filepath = SCHEMAS_DIR / "form_submissions.json"

    def post_process(self, row: dict, context: Optional[dict]) -> dict:
        """As needed, append or transform raw data to match expected structure.
        Returns row, or None if row is to be excluded"""

        row["id"] = context["guid"]
        return row

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params = super().get_url_params(context, next_page_token)
        if next_page_token:
            params["offset"] = next_page_token
        params['orderBy'] = "created"
        params["limit"] = 50
        return params

class EmailSubscriptionsStream(MarketingStream):
    # records_jsonpath = "$.[*]"
    # next_page_token_jsonpath = "$.offset"
    name = "email_subscriptions"
    path = "/communication-preferences/v4/definitions"
    # primary_keys = ["id"]
    replication_method = "FULL_TABLE"
    replication_key = ""
    schema = EmailSubscriptions.schema

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params = super().get_url_params(context, next_page_token)
        if next_page_token:
            params["offset"] = next_page_token
        params['orderBy'] = "created"
        return params

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        """Return a context dictionary for child streams."""
        return {
            "id": record["id"],
        }

