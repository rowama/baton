---
id: providers.lm-studio
title: Use LM Studio
audience: owner
summary: Use LM Studio, running on this computer, so Baton can use its models.
order: 18
generated: true
related: [user.connect-an-account, admin.secrets]
---

## Here, now {#here-now}

1. Start LM Studio on this computer, so it is listening at `http://localhost:1234/v1`.
2. In **Accounts**, find the **LM Studio** card and choose **Connect**. Leave the key box blank unless you set one up.

Baton checks the connection with a quick read of the model list, which never asks a model anything and costs nothing. Then the models appear in **Models**.

If it does not work, see [what a refusal means](user.connect-an-account#key-refused).

## About LM Studio {#about}

LM Studio runs models on your own computer, so there is no account to pay and no key by default. How fast and how good the models are depends on your hardware.

Baton talks to it at `http://localhost:1234/v1`.

## From the command line {#command-line}

The same steps without the page. A key is asked for at a hidden prompt, never typed as an argument:

```baton
baton workers connect lm_studio --no-key
```
