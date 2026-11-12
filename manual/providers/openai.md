---
id: providers.openai
title: Connect OpenAI
audience: owner
summary: Get a key for OpenAI and connect it so its models can do work for you.
order: 21
generated: true
related: [user.connect-an-account, admin.secrets]
---

## Here, now {#here-now}

1. Create a key in your OpenAI account.
2. In **Accounts**, find the **OpenAI** card, paste the key into its box and choose **Connect**.

Baton checks the connection with a quick read of the model list, which never asks a model anything and costs nothing. Then the models appear in **Models**.

If it does not work, see [what a refusal means](user.connect-an-account#key-refused).

## About OpenAI {#about}

OpenAI sells access to its own models directly. You pay OpenAI, on your own account with them.

## From the command line {#command-line}

The same steps without the page. A key is asked for at a hidden prompt, never typed as an argument:

```baton
baton workers connect openai
```
