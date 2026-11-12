---
id: providers.requesty
title: Connect Requesty
audience: owner
summary: Get a key for Requesty and connect it so its models can do work for you.
order: 24
generated: true
related: [user.connect-an-account, admin.secrets]
---

## Here, now {#here-now}

1. Get a key from [Requesty](https://app.requesty.ai). It opens Requesty's own page for creating one.
2. In **Accounts**, find the **Requesty** card, paste the key into its box and choose **Connect**.

Baton checks the connection with a quick read of the model list, which never asks a model anything and costs nothing. Then the models appear in **Models**.

If it does not work, see [what a refusal means](user.connect-an-account#key-refused).

## About Requesty {#about}

Requesty offers models over the OpenAI interface, so Baton needs only a key from Requesty. You pay Requesty.

Baton talks to it at `https://router.requesty.ai/v1`.

## From the command line {#command-line}

The same steps without the page. A key is asked for at a hidden prompt, never typed as an argument:

```baton
baton workers connect requesty
```
