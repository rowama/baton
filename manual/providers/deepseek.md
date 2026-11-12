---
id: providers.deepseek
title: Connect DeepSeek
audience: owner
summary: Get a key for DeepSeek and connect it so its models can do work for you.
order: 14
generated: true
related: [user.connect-an-account, admin.secrets]
---

## Here, now {#here-now}

1. Create a key in your DeepSeek account.
2. In **Accounts**, find the **DeepSeek** card, paste the key into its box and choose **Connect**.

Baton checks the connection with a quick read of the model list, which never asks a model anything and costs nothing. Then the models appear in **Models**.

If it does not work, see [what a refusal means](user.connect-an-account#key-refused).

## About DeepSeek {#about}

DeepSeek sells access to its own models directly. You pay DeepSeek, on your own account with them.

## From the command line {#command-line}

The same steps without the page. A key is asked for at a hidden prompt, never typed as an argument:

```baton
baton workers connect deepseek
```
