---
id: providers.groq
title: Connect Groq
audience: owner
summary: Get a key for Groq and connect it so its models can do work for you.
order: 17
generated: true
related: [user.connect-an-account, admin.secrets]
---

## Here, now {#here-now}

1. Create a key in your Groq account.
2. In **Accounts**, find the **Groq** card, paste the key into its box and choose **Connect**.

Baton checks the connection with a quick read of the model list, which never asks a model anything and costs nothing. Then the models appear in **Models**.

If it does not work, see [what a refusal means](user.connect-an-account#key-refused).

## About Groq {#about}

Groq hosts models made by several vendors, so one account reaches several makers' models, which is often the quickest way to get more than one working. You pay Groq.

## From the command line {#command-line}

The same steps without the page. A key is asked for at a hidden prompt, never typed as an argument:

```baton
baton workers connect groq
```
