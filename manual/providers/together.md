---
id: providers.together
title: Connect Together AI
audience: owner
summary: Get a key for Together AI and connect it so its models can do work for you.
order: 25
generated: true
related: [user.connect-an-account, admin.secrets]
---

## Here, now {#here-now}

1. Get a key from [Together AI](https://api.together.ai/settings/api-keys). It opens Together AI's own page for creating one.
2. In **Accounts**, find the **Together AI** card, paste the key into its box and choose **Connect**.

Baton checks the connection with a quick read of the model list, which never asks a model anything and costs nothing. Then the models appear in **Models**.

If it does not work, see [what a refusal means](user.connect-an-account#key-refused).

## About Together AI {#about}

Together AI offers models over the OpenAI interface, so Baton needs only a key from Together AI. You pay Together AI.

Baton talks to it at `https://api.together.xyz/v1`.

## From the command line {#command-line}

The same steps without the page. A key is asked for at a hidden prompt, never typed as an argument:

```baton
baton workers connect together
```
