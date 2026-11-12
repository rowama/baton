---
id: providers.openrouter
title: Connect OpenRouter
audience: owner
summary: Get a key for OpenRouter and connect it so its models can do work for you.
order: 23
generated: true
related: [user.connect-an-account, admin.secrets]
---

## Here, now {#here-now}

1. Get a key from [OpenRouter](https://openrouter.ai/keys). It opens OpenRouter's own page for creating one.
2. In **Accounts**, find the **OpenRouter** card, paste the key into its box and choose **Connect**.

Baton checks the connection with a quick read of the model list, which never asks a model anything and costs nothing. Then the models appear in **Models**.

If it does not work, see [what a refusal means](user.connect-an-account#key-refused).

## About OpenRouter {#about}

OpenRouter hosts models made by several vendors, so one account reaches several makers' models, which is often the quickest way to get more than one working. You pay OpenRouter.

## Good to know {#good-to-know}

- OpenRouter lists a price for every model, and some are listed as free. In **Models**, tick **free only** to see just those, or leave it off to see every model with its price.
- The card shows OpenRouter's credit or free allowance when OpenRouter reports it.
- Keys are made on OpenRouter's keys page. After you sign in, choose to create a key and give it a name you will recognise.

## From the command line {#command-line}

The same steps without the page. A key is asked for at a hidden prompt, never typed as an argument:

```baton
baton workers connect openrouter
```
