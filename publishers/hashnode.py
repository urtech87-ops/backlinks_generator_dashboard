"""
Hashnode publisher — a Hashnode publication you own, via its GraphQL API.

Auth is a personal access token (Hashnode → your avatar → Developer Settings
→ Personal Access Tokens) plus the id of the publication to post into
(Hashnode → your publication → Dashboard → Settings → General). Both are
saved as HASHNODE_TOKEN / HASHNODE_PUBLICATION_ID in Settings.

Hashnode's public API is GraphQL, not REST — one endpoint, two mutations:
`publishPost` for a live post, `createDraft` for one that stays a draft on
Hashnode until you publish it from there yourself.
"""

import requests

from core import config
from .base import Article, PublishResult, clean_tags, missing_keys

API_URL = "https://gql.hashnode.com/"
LABEL = "Hashnode"
TIMEOUT = 60

PUBLISH_MUTATION = """
mutation PublishPost($input: PublishPostInput!) {
  publishPost(input: $input) {
    post { id slug url }
  }
}
"""

DRAFT_MUTATION = """
mutation CreateDraft($input: CreateDraftInput!) {
  createDraft(input: $input) {
    draft { id slug }
  }
}
"""


def missing(site=None) -> list:
    """Which settings are still empty. [] means ready to publish."""
    return missing_keys([
        ("Hashnode personal access token", config.is_set("HASHNODE_TOKEN")),
        ("Hashnode publication ID", config.is_set("HASHNODE_PUBLICATION_ID")),
    ])


def _tags(article: Article) -> list:
    """New tags need only a slug + name — Hashnode creates them if they don't exist."""
    return [{"slug": t, "name": t} for t in clean_tags(article.tags, limit=5)]


def _graphql(query: str, variables: dict) -> dict:
    r = requests.post(
        API_URL,
        headers={"Authorization": config.get("HASHNODE_TOKEN"),
                 "Content-Type": "application/json"},
        json={"query": query, "variables": variables}, timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def publish(article: Article, site=None, as_draft: bool = False) -> PublishResult:
    """
    Create the post on your Hashnode publication. `as_draft=True` calls
    `createDraft` instead of `publishPost`, so you can review it on Hashnode
    before it goes live.
    """
    gaps = missing()
    if gaps:
        return PublishResult(False, LABEL, detail=f"Not set up yet — missing: {', '.join(gaps)}.")

    post_input = {
        "title": article.title,
        "publicationId": config.get("HASHNODE_PUBLICATION_ID"),
        "contentMarkdown": article.body_markdown,
        "tags": _tags(article),
    }
    if article.slug:
        post_input["slug"] = article.slug

    try:
        if as_draft:
            data = _graphql(DRAFT_MUTATION, {"input": post_input})
            errors = data.get("errors")
            if errors:
                return PublishResult(False, LABEL,
                                     detail=f"Hashnode refused the draft: "
                                            f"{errors[0].get('message', errors)}")
            draft = (data.get("data") or {}).get("createDraft", {}).get("draft") or {}
            draft_id = draft.get("id", "")
            return PublishResult(
                ok=True, platform=LABEL,
                url=f"https://hashnode.com/draft/{draft_id}" if draft_id else "",
                draft=True,
                detail="Saved as a Hashnode draft — open it there to review and publish.",
            )

        data = _graphql(PUBLISH_MUTATION, {"input": post_input})
        errors = data.get("errors")
        if errors:
            return PublishResult(False, LABEL,
                                 detail=f"Hashnode refused the post: "
                                        f"{errors[0].get('message', errors)}")
        post = (data.get("data") or {}).get("publishPost", {}).get("post") or {}
        return PublishResult(
            ok=True, platform=LABEL, url=post.get("url", ""), draft=False,
            detail="Published live on Hashnode.",
        )
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        if status == 401:
            return PublishResult(False, LABEL,
                                 detail="Hashnode rejected the token (401). Re-issue a "
                                        "personal access token from Hashnode → Developer "
                                        "Settings.")
        return PublishResult(False, LABEL, detail=f"Hashnode returned an error ({status}).")
    except Exception as e:
        return PublishResult(False, LABEL, detail=f"Couldn't reach Hashnode: {e}")
