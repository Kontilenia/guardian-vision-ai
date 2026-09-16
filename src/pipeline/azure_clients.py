"""Factories for the Azure clients used across the pipeline."""
from __future__ import annotations

from functools import lru_cache

from azure.ai.contentsafety import ContentSafetyClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI

from config import Settings, get_settings


def get_credential():
    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def get_openai_client() -> AzureOpenAI:
    settings: Settings = get_settings()
    if settings.use_key_auth:
        return AzureOpenAI(
            azure_endpoint=settings.openai_endpoint,
            api_key=settings.openai_api_key,
            api_version=settings.openai_api_version,
        )
    token_provider = _bearer_token_provider()
    return AzureOpenAI(
        azure_endpoint=settings.openai_endpoint,
        azure_ad_token_provider=token_provider,
        api_version=settings.openai_api_version,
    )


def _bearer_token_provider():
    from azure.identity import get_bearer_token_provider

    return get_bearer_token_provider(
        get_credential(), "https://cognitiveservices.azure.com/.default"
    )


@lru_cache(maxsize=1)
def get_content_safety_client() -> ContentSafetyClient:
    settings = get_settings()
    return ContentSafetyClient(
        endpoint=settings.content_safety_endpoint,
        credential=AzureKeyCredential(settings.content_safety_key),
    )
