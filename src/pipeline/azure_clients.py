"""Factories for the Azure clients used across the pipeline."""
from __future__ import annotations

from functools import lru_cache

from azure.ai.contentsafety import ContentSafetyClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from openai import OpenAI

from config import Settings, get_settings


def get_credential():
    return DefaultAzureCredential()


def _foundry_account_endpoint(settings: Settings) -> str:
    project_path = "/api/projects/"
    if project_path not in settings.foundry_project_endpoint:
        raise RuntimeError(
            "FOUNDRY_PROJECT_ENDPOINT must end with /api/projects/<project-name>"
        )
    return settings.foundry_project_endpoint.split(project_path, 1)[0]


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    settings: Settings = get_settings()
    api_key = (
        settings.openai_api_key
        if settings.use_key_auth
        else _bearer_token_provider()
    )
    return OpenAI(
        base_url=f"{_foundry_account_endpoint(settings)}/openai/v1/",
        api_key=api_key,
    )


def _bearer_token_provider():
    from azure.identity import get_bearer_token_provider

    return get_bearer_token_provider(
        get_credential(), "https://cognitiveservices.azure.com/.default"
    )


@lru_cache(maxsize=1)
def get_content_safety_client() -> ContentSafetyClient:
    settings = get_settings()
    credential = (
        AzureKeyCredential(settings.openai_api_key)
        if settings.use_key_auth
        else get_credential()
    )
    return ContentSafetyClient(
        endpoint=_foundry_account_endpoint(settings),
        credential=credential,
    )
