---
id: providers.openai-compatible
title: Connect openai_compatible
audience: owner
summary: Use any service that speaks the OpenAI interface.
order: 22
generated: true
related: [user.connect-an-account, admin.secrets]
---

## Here, now {#here-now}

1. Find the address of the service (it ends in `/v1`) and, if it needs one, a key.
2. In **Accounts**, find the **openai_compatible** card, enter the address and the key, and choose **Connect**.

Baton checks the connection with a quick read of the model list, which never asks a model anything and costs nothing. Then the models appear in **Models**.

If it does not work, see [what a refusal means](user.connect-an-account#key-refused).

## About openai_compatible {#about}

Many services copy the OpenAI interface, so Baton can use any of them with just an address and, if the service wants one, a key.

## From the command line {#command-line}

The same steps without the page. A key is asked for at a hidden prompt, never typed as an argument:

```baton
baton workers connect openai_compatible
baton workers connect openai_compatible --base-url https://example.com/v1
```
