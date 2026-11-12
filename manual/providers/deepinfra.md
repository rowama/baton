---
id: providers.deepinfra
title: Connect DeepInfra
audience: owner
summary: Get a key for DeepInfra and connect it so its models can do work for you.
order: 13
generated: true
related: [user.connect-an-account, admin.secrets]
---

## Here, now {#here-now}

1. Get a key from [DeepInfra](https://deepinfra.com/dash/api_keys). It opens DeepInfra's own page for creating one.
2. In **Accounts**, find the **DeepInfra** card, paste the key into its box and choose **Connect**.

Baton checks the connection with a quick read of the model list, which never asks a model anything and costs nothing. Then the models appear in **Models**.

If it does not work, see [what a refusal means](user.connect-an-account#key-refused).

## About DeepInfra {#about}

DeepInfra offers models over the OpenAI interface, so Baton needs only a key from DeepInfra. You pay DeepInfra.

Baton talks to it at `https://api.deepinfra.com/v1/openai`.

## From the command line {#command-line}

The same steps without the page. A key is asked for at a hidden prompt, never typed as an argument:

```baton
baton workers connect deepinfra
```
