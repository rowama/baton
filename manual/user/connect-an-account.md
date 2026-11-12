---
id: user.connect-an-account
title: Connect an API account
audience: owner
summary: Give Baton a key for a provider such as OpenRouter so its models can do work for you.
related: [user.choose-models, user.connect-a-subscription, admin.secrets]
---

## Here, now {#here-now}

To connect a provider such as OpenRouter:

1. In **Accounts**, find the provider's card and choose **Get a key**. That opens the provider's own page for creating one.
2. Create a key there and copy it.
3. Paste it into the card's key box and choose **Connect**.

Baton checks the key with a quick read of the provider's model list. It never asks a model anything, so checking costs nothing. When the key works, the card shows how many models the provider offers and how many are free, and the models appear in **Models**.

If the key is refused, see [what a refusal means](user.connect-an-account#key-refused).

## What connecting does {#what-connecting-does}

Connecting an account does four things, in order:

1. Checks the key with the provider.
2. Stores the key on this computer, in your system's keyring when there is one, otherwise in a file only your user can read. The card says which. See [where keys are kept](admin.secrets#where-keys-are-kept).
3. Records the account, so Baton knows it may use that provider.
4. Reads the provider's list of models, with their prices where the provider gives them, and sets each one up as something Baton can choose for a step.

Nothing is sent to the provider except the key check and the model list. A key is never shown again after you paste it; the page only says where it is kept.

## Key refused {#key-refused}

The provider says the key is not valid. Check, in this order:

- The key was copied whole, with no space at either end.
- It is a key for **this** provider. Keys from different providers look alike.
- It has not been deleted or switched off in the provider's own account page.
- The account has no hold on it, such as an unpaid balance or an unverified email.

A refused key is never stored. If you were replacing a working key, the old one stays in use.

## Replace or remove a key {#replace-or-remove}

- **Replace key** on a connected card takes a new key, checks it first, and only then swaps it in. A bad new key leaves the working one in place.
- **Disconnect** removes the account from Baton. The stored key stays unless you also tick **also delete the stored key**.

## OpenRouter {#openrouter}

OpenRouter is one account that reaches many vendors' models, so it is often the quickest way to get several models working at once.

1. Create an account at openrouter.ai and add a key on its keys page (the **Get a key** link opens it).
2. Paste the key into the OpenRouter card and choose **Connect**.
3. Open **Models**, tick **free only** to see the models OpenRouter lists as free, or leave it off to see them all with their prices.

Which models cost money, and how much, is OpenRouter's to say; the **Models** table shows the price OpenRouter lists. Credit or free allowance appears on the card when OpenRouter reports it.

## From the command line {#command-line}

The same steps without the page. The key is asked for at a hidden prompt, never typed as an argument:

```baton
baton workers connect openrouter
baton workers connect openrouter --key-stdin
```

Use `--no-key` for a local endpoint that needs no key, and `--base-url` for any service that speaks the OpenAI interface.
