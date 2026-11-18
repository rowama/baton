---
id: admin.web-access
title: Giving API models web access
audience: admin
order: 62
summary: How a model reached through an API key searches the web and reads pages, and how to give it a search service.
related: [admin.accounts-and-costs, admin.network-and-security, admin.machine-settings]
---

## Here, now {#here-now}

Some steps search the web: research, for example. A coding assistant does them with its own tools. A model reached through an API key does them through Baton: Baton offers it a search and a page fetch, carries out each one, and records it. Run `baton workers status` to see which of your models have web access, and why the others do not.

A model needs two things for web access: it must call tools (most current models do), and it needs a way to search.

## The provider's own search {#provider-search}

Some providers search for their models. Baton uses this where it works beside its own tools: today, Anthropic's models. Nothing needs setting up. The provider bills each search as well as the tokens: the setup page says **web search billed per search** beside the price, and each step's record counts its searches.

Other providers' searches cannot be used this way yet, so their models need a search service.

## Declaring a search service {#declare}

Declare one search service for the machine, and every model that calls tools can search through it:

```
baton workers declare --search tavily --credential secret:tavily_key
```

The provider is any search service that LiteLLM supports, for example `tavily`, `brave`, `exa_ai`, `serper` or `perplexity`. Store its key first, as for any account: see [where keys are kept](admin.secrets#where-keys-are-kept). The key is given only to the process doing the step, and is never recorded. A provider's own search, where a model has one, is used first.

To change the service, declare another. To remove it: `baton workers declare --search <provider> --remove`. The declaration lives under `search:` in `~/.baton/resources.yaml`.

## A free search of your own: SearXNG {#searxng}

SearXNG is an open-source search service you run yourself. It needs no account and no key, only its address:

```
baton workers declare --search searxng --base-url http://localhost:8080
```

Your instance must allow JSON results: in its `settings.yml`, under `search:`, `formats` lists `json`.

## What a model may fetch {#fetch}

A model opens pages only through Baton, and only public `http` and `https` addresses, with limits on size, type and time. On a step that reads the project as well as the web, it opens only addresses that came from a search or are written in the step's inputs. The rules are in [network and security](admin.network-and-security#api-model-web).
